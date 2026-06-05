"""
Herramientas que usan los agentes especializados.

Cuatro herramientas, cada una pensada para ser **fácil de entender y sin riesgo**:

    - web_search(query):  busca en la web (DuckDuckGo, sin API key).
    - read_url(url):       descarga una página y la convierte a texto limpio.
    - calc(expression):    evalúa una expresión aritmética con un parser seguro
                           (solo números y + - * / ( ) y ** ); NO ejecuta código.
    - run_sql(query):      consulta de SOLO LECTURA sobre el SQLite de ejemplo.

Las dos primeras son idénticas a las de multi-agent-research (misma convención de
portfolio). `calc` evita que el modelo "alucine" cuentas, y `run_sql` está acotada
a SELECT para que no haya forma de modificar ni dañar la base.
"""

from __future__ import annotations

import ast
import operator
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - nombre antiguo del mismo paquete
    from duckduckgo_search import DDGS  # type: ignore


# Límites para no inundar el contexto del modelo.
MAX_SEARCH_RESULTS = 6
MAX_PAGE_CHARS = 8_000
REQUEST_TIMEOUT = 15
MAX_SQL_ROWS = 50

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]

# Ruta por defecto de la base de ejemplo (data/demo.db junto al repo).
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "demo.db"


# ---------------------------------------------------------------------------
# Registro de fuentes (para citas [1], [2], … igual que en multi-agent-research)
# ---------------------------------------------------------------------------
@dataclass
class Source:
    url: str
    title: str


@dataclass
class SourceRegistry:
    sources: list[Source] = field(default_factory=list)

    def add(self, url: str, title: str) -> int:
        for i, src in enumerate(self.sources, start=1):
            if src.url == url:
                return i
        self.sources.append(Source(url=url, title=title or url))
        return len(self.sources)

    def bibliography(self) -> str:
        if not self.sources:
            return ""
        lines = [f"[{i}] {s.title}\n    {s.url}" for i, s in enumerate(self.sources, start=1)]
        return "Fuentes:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Herramientas web (idénticas a multi-agent-research)
# ---------------------------------------------------------------------------
class WebTools:
    def __init__(self, registry: SourceRegistry | None = None) -> None:
        self.registry = registry or SourceRegistry()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def web_search(self, query: str, max_results: int = MAX_SEARCH_RESULTS) -> str:
        """Busca en la web y devuelve los mejores resultados (título, URL, snippet)."""
        query = (query or "").strip()
        if not query:
            return "Error: la búsqueda está vacía."
        n = max(1, min(int(max_results or MAX_SEARCH_RESULTS), MAX_SEARCH_RESULTS))
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=n))
        except Exception as exc:  # noqa: BLE001 — el resultado vuelve al modelo
            return f"Error al buscar '{query}': {exc}"

        if not results:
            return f"Sin resultados para '{query}'."

        lines = [f"Resultados para '{query}':"]
        for r in results:
            title = r.get("title", "").strip()
            url = r.get("href") or r.get("url") or ""
            snippet = (r.get("body") or "").strip()
            lines.append(f"- {title}\n  URL: {url}\n  {snippet[:200]}")
        return "\n".join(lines)

    def read_url(self, url: str) -> str:
        """Descarga una página web y devuelve su texto principal (limpio y truncado)."""
        url = (url or "").strip()
        if not re.match(r"^https?://", url):
            return f"Error: URL inválida '{url}' (debe empezar con http:// o https://)."
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            return f"Error al leer '{url}': {exc}"

        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type and "text" not in content_type:
            return f"Error: '{url}' no es una página de texto ({content_type})."

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(_NOISE_TAGS):
            tag.decompose()

        title = (soup.title.string or "").strip() if soup.title else url
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        cite = self.registry.add(url, title)
        truncated = len(text) > MAX_PAGE_CHARS
        body = text[:MAX_PAGE_CHARS]
        suffix = "\n… (truncado)" if truncated else ""
        return f"[Fuente {cite}] {title}\nURL: {url}\n\n{body}{suffix}"


# ---------------------------------------------------------------------------
# Calculadora segura: evalúa una expresión con AST, sin ejecutar código.
# ---------------------------------------------------------------------------
# Solo permitimos estos operadores. Nada de nombres, llamadas, atributos, etc.
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalcError(ValueError):
    """La expresión no es una operación aritmética válida y segura."""


def _eval_node(node: ast.AST) -> float:
    """Evalúa recursivamente un nodo del AST permitiendo solo aritmética."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):  # números (3.10+: Constant en vez de Num)
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalcError(f"Valor no numérico: {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise CalcError("Solo se permiten números y los operadores + - * / // % ** ( ).")


def calc(expression: str) -> str:
    """Evalúa una expresión aritmética de forma segura (sin ejecutar código).

    Ejemplos válidos: "(8.2 - 6.5) / 6.5 * 100", "2 ** 10", "100 / 7".
    Cualquier otra cosa (variables, funciones, imports) se rechaza.
    """
    expression = (expression or "").strip()
    if not expression:
        return "Error: la expresión está vacía."
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree)
    except CalcError as exc:
        return f"Error: {exc}"
    except ZeroDivisionError:
        return "Error: división por cero."
    except (SyntaxError, ValueError, TypeError) as exc:
        return f"Error: expresión inválida ({exc})."
    # Mostramos enteros sin el .0 sobrante.
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"{expression} = {result}"


# ---------------------------------------------------------------------------
# SQL de solo lectura sobre el SQLite de ejemplo.
# ---------------------------------------------------------------------------
class SQLTool:
    """Ejecuta consultas SELECT (solo lectura) sobre una base SQLite."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH

    def schema(self) -> str:
        """Devuelve el esquema (tablas y columnas) para que el agente sepa qué consultar."""
        if not self.db_path.exists():
            return f"Error: no existe la base en {self.db_path}. Genérala con scripts/seed_db.py."
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            tables = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            parts = []
            for (name,) in tables:
                cols = con.execute(f"PRAGMA table_info({name})").fetchall()
                col_desc = ", ".join(f"{c[1]} {c[2]}" for c in cols)
                parts.append(f"{name}({col_desc})")
            return "Esquema:\n" + "\n".join(parts)
        finally:
            con.close()

    def run_sql(self, query: str) -> str:
        """Ejecuta una consulta SELECT y devuelve las filas (acotadas)."""
        query = (query or "").strip().rstrip(";")
        if not query:
            return "Error: la consulta está vacía."
        # Defensa simple: solo permitimos una sentencia y que empiece con SELECT/WITH.
        lowered = query.lower()
        if ";" in query:
            return "Error: solo se permite una sentencia SELECT por consulta."
        if not (lowered.startswith("select") or lowered.startswith("with")):
            return "Error: solo se permiten consultas de lectura (SELECT / WITH)."
        forbidden = (
            "insert", "update", "delete", "drop", "alter",
            "create", "replace", "attach", "pragma",
        )
        if any(re.search(rf"\b{kw}\b", lowered) for kw in forbidden):
            return "Error: la consulta contiene una operación no permitida (solo lectura)."
        if not self.db_path.exists():
            return f"Error: no existe la base en {self.db_path}. Genérala con scripts/seed_db.py."

        # Conexión en modo de solo lectura: aunque algo se escape, no puede escribir.
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            cur = con.execute(query)
            rows = cur.fetchmany(MAX_SQL_ROWS)
            headers = [d[0] for d in cur.description] if cur.description else []
        except sqlite3.Error as exc:
            return f"Error de SQL: {exc}"
        finally:
            con.close()

        if not rows:
            return "Sin resultados."
        lines = [" | ".join(headers)]
        lines.append("-" * len(lines[0]))
        for row in rows:
            lines.append(" | ".join(str(v) for v in row))
        more = "\n… (más filas truncadas)" if len(rows) == MAX_SQL_ROWS else ""
        return "\n".join(lines) + more


# ---------------------------------------------------------------------------
# Esquemas de tools en formato DeepSeek/OpenAI
# ---------------------------------------------------------------------------
WEB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Busca en la web y devuelve una lista de resultados (título, URL, "
            "snippet). Usar para descubrir qué páginas leer sobre un tema."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta en lenguaje natural."},
                "max_results": {"type": "integer", "description": "Máximo de resultados (1-6)."},
            },
            "required": ["query"],
        },
    },
}

READ_URL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_url",
        "description": (
            "Descarga una página web y devuelve su texto principal limpio. "
            "Usar para leer en detalle una URL encontrada con web_search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL completa (http/https)."},
            },
            "required": ["url"],
        },
    },
}

CALC_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calc",
        "description": (
            "Evalúa una expresión aritmética de forma exacta (no estimar mentalmente). "
            "Solo números y operadores + - * / // % ** y paréntesis. "
            'Ejemplo: "(8.2 - 6.5) / 6.5 * 100".'
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "La expresión a calcular."},
            },
            "required": ["expression"],
        },
    },
}

RUN_SQL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": (
            "Ejecuta una consulta SELECT (solo lectura) sobre la base de ejemplo y "
            "devuelve las filas. Consultá el esquema antes para conocer tablas y columnas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Una sentencia SELECT/WITH."},
            },
            "required": ["query"],
        },
    },
}
