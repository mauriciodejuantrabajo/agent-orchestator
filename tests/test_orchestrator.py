"""Test del orquestador completo con un LLM falso (sin red ni API).

El cliente falso responde distinto según el rol que detecta en el system prompt:
hace de planner (devuelve un DAG) y de cada agente (responde y/o pide tools).
Así cubrimos el flujo entero: planificar -> ejecutar con dependencias -> unificar.
"""

from __future__ import annotations

import json

from src.orchestrator import Event, Orchestrator


PLAN_JSON = json.dumps({
    "steps": [
        {"id": "s1", "agent": "data", "task": "contar ventas", "depends_on": []},
        {"id": "s2", "agent": "math", "task": "sumar", "depends_on": []},
        {"id": "s3", "agent": "writer", "task": "redactar", "depends_on": ["s1", "s2"]},
    ]
})


class FakeClient:
    """Hace de planner y de todos los agentes según el system prompt recibido."""

    def chat(self, messages, tools=None):
        system = messages[0]["content"]
        last_role = messages[-1]["role"]

        # ¿Quién pregunta?
        if "planificador" in system:
            return {"content": PLAN_JSON}

        # Si el último mensaje es un resultado de tool, ya respondemos texto final.
        if last_role == "tool":
            return {"content": "Listo, con el dato de la herramienta."}

        if "agente de datos" in system:
            # Pide ejecutar run_sql una vez (probamos el loop de tool-calling).
            return {
                "content": "",
                "tool_calls": [{
                    "id": "c1",
                    "function": {"name": "run_sql", "arguments": '{"query": "SELECT 1"}'},
                }],
            }
        if "agente de cálculo" in system:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "c2",
                    "function": {"name": "calc", "arguments": '{"expression": "2+2"}'},
                }],
            }
        if "agente redactor" in system:
            return {"content": "# Respuesta final\nSíntesis de s1 y s2."}
        return {"content": "ok"}


def test_orquestador_flujo_completo():
    events: list[Event] = []
    orch = Orchestrator(client=FakeClient(), on_event=events.append)
    result = orch.run("una petición que combina datos y cálculo")

    # La respuesta final viene del writer.
    assert "Respuesta final" in result.answer

    # Se ejecutaron los tres pasos.
    assert set(result.results) == {"s1", "s2", "s3"}
    assert all(r.ok for r in result.results.values())

    # El writer dependía de s1 y s2: debe haber recibido sus salidas como contexto.
    # (lo verificamos indirectamente: terminó ok y produjo la síntesis)
    kinds = [e.kind for e in events]
    assert "plan" in kinds
    assert kinds.count("step_done") == 3


def test_orquestador_paraleliza_pasos_independientes():
    """s1 y s2 no dependen entre sí: deben arrancar antes de que s3 (que depende
    de ambos) arranque."""
    events: list[Event] = []
    orch = Orchestrator(client=FakeClient(), on_event=events.append)
    orch.run("x")

    starts = [e.step_id for e in events if e.kind == "step_start"]
    # s3 siempre arranca después de s1 y s2.
    assert starts.index("s3") > starts.index("s1")
    assert starts.index("s3") > starts.index("s2")


def test_fallback_cuando_plan_es_invalido():
    """Si el planner devuelve basura, el orquestador debe responder igual vía writer."""
    class BadPlanClient(FakeClient):
        def chat(self, messages, tools=None):
            if "planificador" in messages[0]["content"]:
                return {"content": "no es json"}
            return super().chat(messages, tools)

    orch = Orchestrator(client=BadPlanClient())
    result = orch.run("algo")
    # El fallback crea un único paso writer; debe producir respuesta.
    assert result.answer
    assert len(result.plan.steps) == 1
