"""
Agentes especializados.

Cada agente tiene **una sola responsabilidad**, su propio prompt y su propio
juego (pequeño) de herramientas. Esa es la idea central del patrón orquestador:
en vez de un único agente con 15 herramientas que se confunde, varios agentes
enfocados a los que un supervisor les delega.

Todos comparten el mismo motor de ejecución (`Agent._run`): un loop de
tool-calling con la API de DeepSeek (compatible OpenAI). El modelo pide ejecutar
una herramienta, la corremos, le devolvemos el resultado, y repetimos hasta que
responde con texto final (o se agota el tope de pasos).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .llm import DeepSeekClient
from .tools import (
    CALC_SCHEMA,
    READ_URL_SCHEMA,
    RUN_SQL_SCHEMA,
    WEB_SEARCH_SCHEMA,
    SourceRegistry,
    SQLTool,
    WebTools,
    calc,
)

# Tope de iteraciones de tool-calling por agente (evita loops infinitos).
MAX_TOOL_STEPS = 6


@dataclass
class AgentResult:
    """Lo que devuelve un agente al orquestador."""
    agent: str
    output: str
    tool_calls: list[str] = field(default_factory=list)  # traza legible: "web_search(...)"
    ok: bool = True


class Agent:
    """Base: un rol + un prompt de sistema + un conjunto de herramientas."""

    name: str = "agent"
    description: str = ""

    def __init__(
        self,
        client: DeepSeekClient,
        system_prompt: str,
        tool_schemas: list[dict[str, Any]],
        tool_impls: dict[str, Callable[..., str]],
    ) -> None:
        self.client = client
        self.system_prompt = system_prompt
        self.tool_schemas = tool_schemas
        self.tool_impls = tool_impls

    def run(self, task: str, context: str = "") -> AgentResult:
        """Resuelve `task` (con `context` opcional de resultados previos)."""
        user = task if not context else f"{task}\n\n--- Contexto de pasos previos ---\n{context}"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user},
        ]
        return self._run(messages)

    def _run(self, messages: list[dict[str, Any]]) -> AgentResult:
        trace: list[str] = []
        for _ in range(MAX_TOOL_STEPS):
            msg = self.client.chat(messages, tools=self.tool_schemas or None)
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                return AgentResult(agent=self.name, output=(msg.get("content") or "").strip(),
                                   tool_calls=trace)
            # El asistente pidió herramientas: las ejecutamos y devolvemos resultados.
            messages.append(msg)
            for call in tool_calls:
                fn = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                impl = self.tool_impls.get(fn)
                if impl is None:
                    result = f"Error: herramienta desconocida '{fn}'."
                else:
                    result = impl(**args)
                trace.append(f"{fn}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", fn),
                    "content": str(result),
                })
        # Si llegamos aquí, agotamos los pasos sin respuesta final.
        return AgentResult(
            agent=self.name,
            output="(El agente agotó el máximo de pasos sin una respuesta final.)",
            tool_calls=trace,
            ok=False,
        )


# ---------------------------------------------------------------------------
# Fábricas de cada agente especializado
# ---------------------------------------------------------------------------
def make_research_agent(client: DeepSeekClient, web: WebTools) -> Agent:
    a = Agent(
        client,
        system_prompt=(
            "Sos un agente de investigación web. Buscás y leés páginas para "
            "responder con hechos concretos. Citá cada afirmación con [N] usando "
            "el número de fuente que devuelven las herramientas. No inventes datos: "
            "si no lo encontrás, decilo. Sé breve y factual."
        ),
        tool_schemas=[WEB_SEARCH_SCHEMA, READ_URL_SCHEMA],
        tool_impls={"web_search": web.web_search, "read_url": web.read_url},
    )
    a.name = "research"
    a.description = "Busca información en la web y devuelve hechos con citas."
    return a


def make_math_agent(client: DeepSeekClient) -> Agent:
    a = Agent(
        client,
        system_prompt=(
            "Sos un agente de cálculo. Para CUALQUIER operación numérica usás la "
            "herramienta `calc` (no calcules de memoria). Explicá brevemente qué "
            "calculaste y mostrá el resultado exacto."
        ),
        tool_schemas=[CALC_SCHEMA],
        tool_impls={"calc": calc},
    )
    a.name = "math"
    a.description = "Resuelve cálculos numéricos de forma exacta."
    return a


def make_data_agent(client: DeepSeekClient, sql: SQLTool) -> Agent:
    a = Agent(
        client,
        system_prompt=(
            "Sos un agente de datos. Respondés preguntas consultando una base "
            "SQLite de SOLO LECTURA con la herramienta `run_sql`. El esquema de la "
            "base es:\n\n" + sql.schema() + "\n\n"
            "Escribe SELECT correctos para SQLite. Si una consulta falla, corrígela "
            "y reintentá. Resumí el resultado en lenguaje natural."
        ),
        tool_schemas=[RUN_SQL_SCHEMA],
        tool_impls={"run_sql": sql.run_sql},
    )
    a.name = "data"
    a.description = "Consulta la base de datos de ejemplo con SQL de solo lectura."
    return a


def make_writer_agent(client: DeepSeekClient) -> Agent:
    a = Agent(
        client,
        system_prompt=(
            "Sos un agente redactor. Recibís los resultados de otros agentes y los "
            "sintetizás en una respuesta final clara y bien estructurada en Markdown. "
            "Conservá las citas [N] que vengan de la investigación. No agregues datos "
            "que no estén en el contexto recibido."
        ),
        tool_schemas=[],
        tool_impls={},
    )
    a.name = "writer"
    a.description = "Sintetiza los resultados de los demás en la respuesta final."
    return a


@dataclass
class AgentTeam:
    """Conjunto de agentes disponibles + recursos compartidos (registro de fuentes)."""
    agents: dict[str, Agent]
    registry: SourceRegistry

    @classmethod
    def build(cls, client: DeepSeekClient, db_path: str | None = None) -> "AgentTeam":
        registry = SourceRegistry()
        web = WebTools(registry)
        sql = SQLTool(db_path)
        agents = {
            "research": make_research_agent(client, web),
            "math": make_math_agent(client),
            "data": make_data_agent(client, sql),
            "writer": make_writer_agent(client),
        }
        return cls(agents=agents, registry=registry)

    def catalog(self) -> str:
        """Descripción de los agentes, para que el planner sepa a quién rutear."""
        return "\n".join(f"- {name}: {a.description}" for name, a in self.agents.items())
