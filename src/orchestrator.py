"""
El orquestador: ejecuta el plan (DAG) que produjo el planner.

Responsabilidades —lo que lo hace un orquestador "de verdad" y no un pipeline:

  1. **Dependencias**: un paso solo corre cuando terminaron aquellos de los que
     depende, y recibe sus salidas como contexto.
  2. **Paralelismo**: todos los pasos "listos" (con dependencias cumplidas) se
     ejecutan a la vez con un pool de hilos. Las llamadas al LLM son I/O, así que
     el paralelismo acorta el tiempo real.
  3. **Presupuesto**: tope global de pasos ejecutados, para no entrar en loops
     caros (la preocupación #1 de producción es el costo).
  4. **Re-planificación**: si un paso falla, el supervisor decide reintentar y, si
     se agota, sigue con lo que tenga en vez de explotar.

Emite eventos (`on_event`) para que la CLI y la web muestren el progreso en vivo.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from .agents import AgentResult, AgentTeam
from .llm import DeepSeekClient
from .planner import Plan, Planner, Step

# Presupuesto global: cuántas ejecuciones de agente permitimos como mucho.
MAX_TOTAL_STEPS = 12
# Reintentos por paso que falla antes de rendirse con ese paso.
MAX_RETRIES_PER_STEP = 1


@dataclass
class Event:
    """Un evento del progreso, para mostrar en vivo (CLI/web)."""
    kind: str   # "plan" | "step_start" | "step_done" | "step_failed" | "final" | "info"
    step_id: str = ""
    agent: str = ""
    message: str = ""


@dataclass
class OrchestrationResult:
    answer: str
    plan: Plan
    results: dict[str, AgentResult] = field(default_factory=dict)
    bibliography: str = ""


class Orchestrator:
    def __init__(
        self,
        client: DeepSeekClient | None = None,
        db_path: str | None = None,
        max_workers: int = 4,
        on_event: Callable[[Event], None] | None = None,
    ) -> None:
        self.client = client or DeepSeekClient()
        self.team = AgentTeam.build(self.client, db_path=db_path)
        self.planner = Planner(
            self.client,
            catalog=self.team.catalog(),
            valid_agents=set(self.team.agents),
        )
        self.max_workers = max_workers
        self.on_event = on_event or (lambda e: None)

    def run(self, request: str) -> OrchestrationResult:
        """Planifica y ejecuta la petición completa."""
        plan = self.planner.plan(request)
        self.on_event(Event(
            kind="plan",
            message=" → ".join(f"{s.id}:{s.agent}" for s in plan.steps),
        ))

        results: dict[str, AgentResult] = {}
        done: set[str] = set()
        steps_used = 0
        pending = {s.id: s for s in plan.steps}

        # Bucle por "olas": en cada vuelta ejecutamos en paralelo todo lo que está listo.
        while pending:
            ready = [s for s in pending.values() if set(s.depends_on) <= done]
            if not ready:
                # No hay nada listo y aún queda pendiente: dependencias rotas. Cortamos.
                self.on_event(Event(kind="info", message="Sin pasos ejecutables; se detiene."))
                break

            if steps_used + len(ready) > MAX_TOTAL_STEPS:
                ready = ready[: max(0, MAX_TOTAL_STEPS - steps_used)]
                self.on_event(Event(kind="info", message="Se alcanzó el presupuesto de pasos."))
            if not ready:
                break

            wave_results = self._run_wave(ready, results)
            steps_used += len(ready)
            for step in ready:
                res = wave_results[step.id]
                results[step.id] = res
                done.add(step.id)
                del pending[step.id]

            if steps_used >= MAX_TOTAL_STEPS and pending:
                self.on_event(Event(kind="info", message="Presupuesto agotado; se finaliza."))
                break

        answer = self._final_answer(plan, results)
        return OrchestrationResult(
            answer=answer,
            plan=plan,
            results=results,
            bibliography=self.team.registry.bibliography(),
        )

    # ---- ejecución de una ola de pasos en paralelo ----
    def _run_wave(self, steps: list[Step], prior: dict[str, AgentResult]) -> dict[str, AgentResult]:
        out: dict[str, AgentResult] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._run_step, s, prior): s for s in steps}
            for fut in as_completed(futures):
                step = futures[fut]
                out[step.id] = fut.result()
        return out

    def _run_step(self, step: Step, prior: dict[str, AgentResult]) -> AgentResult:
        """Ejecuta un paso, pasándole como contexto las salidas de sus dependencias.
        Reintenta si falla (re-planificación simple a nivel de paso)."""
        agent = self.team.agents[step.agent]
        context = self._context_for(step, prior)
        self.on_event(Event(kind="step_start", step_id=step.id, agent=step.agent,
                            message=step.task))

        result = agent.run(step.task, context=context)
        attempts = 0
        while not result.ok and attempts < MAX_RETRIES_PER_STEP:
            attempts += 1
            self.on_event(Event(kind="info", step_id=step.id, agent=step.agent,
                                message=f"Reintentando ({attempts})…"))
            result = agent.run(step.task, context=context)

        kind = "step_done" if result.ok else "step_failed"
        self.on_event(Event(kind=kind, step_id=step.id, agent=step.agent,
                            message=", ".join(result.tool_calls) or "(sin herramientas)"))
        return result

    @staticmethod
    def _context_for(step: Step, prior: dict[str, AgentResult]) -> str:
        """Arma el texto de contexto con las salidas de los pasos de los que depende."""
        if not step.depends_on:
            return ""
        chunks = []
        for dep in step.depends_on:
            res = prior.get(dep)
            if res:
                chunks.append(f"[Resultado de {dep} ({res.agent})]\n{res.output}")
        return "\n\n".join(chunks)

    def _final_answer(self, plan: Plan, results: dict[str, AgentResult]) -> str:
        """La respuesta final es la salida del último paso writer; si no hay writer,
        concatena las salidas de los pasos hoja (los que nadie usa como dependencia)."""
        writer_steps = [s for s in plan.steps if s.agent == "writer" and s.id in results]
        if writer_steps:
            return results[writer_steps[-1].id].output

        depended_on = {d for s in plan.steps for d in s.depends_on}
        leaves = [s for s in plan.steps if s.id not in depended_on and s.id in results]
        leaves = leaves or list(plan.steps)
        return "\n\n".join(
            results[s.id].output for s in leaves if s.id in results
        ).strip() or "(Sin respuesta.)"
