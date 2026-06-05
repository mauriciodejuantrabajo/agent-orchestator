"""
El planificador (parte "supervisora" del orquestador).

Recibe la petición del usuario y la descompone en un **grafo de sub-tareas**
(DAG): cada sub-tarea dice qué agente la resuelve y de qué otras sub-tareas
depende. El orquestador después ejecuta ese grafo respetando dependencias y
corriendo en paralelo lo que se pueda.

Esto es lo que diferencia a un orquestador serio de un simple `if/else`: el
supervisor *planifica* el trabajo antes de ejecutarlo.

El planner le pide al LLM un JSON con la forma:

    {
      "steps": [
        {"id": "s1", "agent": "research", "task": "...", "depends_on": []},
        {"id": "s2", "agent": "math",     "task": "...", "depends_on": ["s1"]},
        {"id": "s3", "agent": "writer",   "task": "...", "depends_on": ["s1","s2"]}
      ]
    }

Si el LLM devuelve algo inválido, hay un fallback: un único paso al writer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .llm import DeepSeekClient


@dataclass
class Step:
    """Un nodo del DAG: una sub-tarea asignada a un agente."""
    id: str
    agent: str
    task: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Plan:
    steps: list[Step]

    def validate(self, valid_agents: set[str]) -> None:
        """Verifica que el DAG sea coherente: agentes válidos, dependencias existentes,
        sin ciclos. Lanza ValueError si algo no cierra."""
        ids = {s.id for s in self.steps}
        if len(ids) != len(self.steps):
            raise ValueError("Hay IDs de paso duplicados en el plan.")
        for s in self.steps:
            if s.agent not in valid_agents:
                raise ValueError(f"El paso {s.id} usa un agente desconocido: {s.agent!r}.")
            for dep in s.depends_on:
                if dep not in ids:
                    raise ValueError(f"El paso {s.id} depende de {dep!r}, que no existe.")
                if dep == s.id:
                    raise ValueError(f"El paso {s.id} depende de sí mismo.")
        self._check_acyclic()

    def _check_acyclic(self) -> None:
        """Orden topológico de Kahn; si quedan nodos, hay un ciclo."""
        deps = {s.id: set(s.depends_on) for s in self.steps}
        resolved: list[str] = []
        while True:
            ready = [sid for sid, d in deps.items() if not d - set(resolved)]
            ready = [sid for sid in ready if sid not in resolved]
            if not ready:
                break
            resolved.extend(ready)
        if len(resolved) != len(self.steps):
            raise ValueError("El plan tiene un ciclo de dependencias.")


PLANNER_SYSTEM = """Sos el planificador de un sistema multi-agente. Descomponés la \
petición del usuario en sub-tareas y asignás cada una al agente más adecuado.

Agentes disponibles:
{catalog}

Reglas:
- Devolvé SOLO un objeto JSON, sin texto alrededor ni ```.
- Forma: {{"steps": [{{"id": "s1", "agent": "<nombre>", "task": "<qué hacer>", "depends_on": []}}]}}
- Usá pocos pasos (1 a 5). No inventes agentes que no estén en la lista.
- `depends_on` lista los IDs de pasos cuyos resultados necesita este paso.
- Si la respuesta final combina varios resultados, agregá un paso final con el \
agente "writer" que dependa de los pasos que aporten información.
- Los pasos independientes (sin dependencias entre sí) se ejecutarán en paralelo: \
aprovéchalo cuando dos búsquedas o cálculos no se necesiten mutuamente.
"""


class Planner:
    def __init__(self, client: DeepSeekClient, catalog: str, valid_agents: set[str]) -> None:
        self.client = client
        self.catalog = catalog
        self.valid_agents = valid_agents

    def plan(self, request: str) -> Plan:
        """Pide un plan al LLM y lo valida; ante error, cae a un plan trivial."""
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM.format(catalog=self.catalog)},
            {"role": "user", "content": request},
        ]
        msg = self.client.chat(messages)
        raw = (msg.get("content") or "").strip()
        try:
            plan = self._parse(raw)
            plan.validate(self.valid_agents)
            return plan
        except (ValueError, KeyError, json.JSONDecodeError):
            # Fallback robusto: si el plan no sirve, que al menos el writer responda.
            agent = "writer" if "writer" in self.valid_agents else next(iter(self.valid_agents))
            return Plan(steps=[Step(id="s1", agent=agent, task=request, depends_on=[])])

    @staticmethod
    def _parse(raw: str) -> Plan:
        """Extrae el JSON (tolerando ``` o texto alrededor) y arma el Plan."""
        text = raw
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fence:
            text = fence.group(1)
        else:
            brace = re.search(r"\{.*\}", text, re.DOTALL)
            if brace:
                text = brace.group(0)
        data: dict[str, Any] = json.loads(text)
        steps_raw = data.get("steps")
        if not isinstance(steps_raw, list) or not steps_raw:
            raise ValueError("El plan no tiene 'steps'.")
        steps = [
            Step(
                id=str(s["id"]),
                agent=str(s["agent"]),
                task=str(s["task"]),
                depends_on=[str(d) for d in s.get("depends_on", [])],
            )
            for s in steps_raw
        ]
        return Plan(steps=steps)
