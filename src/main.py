"""
CLI del orquestador (rich): muestra en vivo cómo el supervisor planifica y
delega a los agentes, y al final imprime la respuesta unificada.

Uso:
    python -m src.main "¿Cuántas notebooks se vendieron y cuánto facturaron?"
    python -m src.main                      # modo interactivo
    python -m src.main "tu pregunta" -o respuesta.md
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .llm import LLMError
from .orchestrator import Event, Orchestrator

console = Console()

# Color/emoji por agente para que la traza se lea de un vistazo.
_AGENT_STYLE = {
    "research": ("🔎", "cyan"),
    "math": ("🧮", "yellow"),
    "data": ("🗄️", "green"),
    "writer": ("✍️", "magenta"),
}


def _print_event(ev: Event) -> None:
    if ev.kind == "plan":
        console.print(Panel(ev.message, title="🧭 Plan del orquestador", border_style="blue"))
    elif ev.kind == "step_start":
        emoji, color = _AGENT_STYLE.get(ev.agent, ("•", "white"))
        console.print(f"  [{color}]{emoji} {ev.agent}[/] [{ev.step_id}] → {ev.message}")
    elif ev.kind == "step_done":
        console.print(f"     [dim]herramientas: {ev.message}[/]")
    elif ev.kind == "step_failed":
        console.print(f"     [red]✗ falló[/] [dim]({ev.message})[/]")
    elif ev.kind == "info":
        console.print(f"  [dim]ℹ {ev.message}[/]")


def answer_once(orch: Orchestrator, question: str) -> str:
    console.print(f"\n[bold]?[/]  {question}\n")
    result = orch.run(question)
    console.print()
    console.print(Panel(Markdown(result.answer), title="Respuesta", border_style="green"))
    if result.bibliography:
        console.print(Panel(result.bibliography, title="Fuentes", border_style="cyan"))
    text = result.answer
    if result.bibliography:
        text += "\n\n" + result.bibliography
    return text


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Orquestador multi-agente (DeepSeek).")
    parser.add_argument("question", nargs="?", help="La petición a resolver.")
    parser.add_argument("-o", "--output", help="Guardar la respuesta en un archivo .md.")
    args = parser.parse_args(argv)

    try:
        orch = Orchestrator(on_event=_print_event)
    except LLMError as exc:
        console.print(f"[red]{exc}[/]")
        return 1

    try:
        if args.question:
            text = answer_once(orch, args.question)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as fh:
                    fh.write(text)
                console.print(f"[dim]Guardado en {args.output}[/]")
            return 0

        console.print("[bold]Orquestador multi-agente[/] — escribe tu pregunta ('salir' para terminar).")
        while True:
            try:
                question = console.input("\n[bold cyan]?[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\nHasta luego.")
                return 0
            if question.lower() in {"salir", "exit", "quit"}:
                console.print("Hasta luego.")
                return 0
            if not question:
                continue
            try:
                answer_once(orch, question)
            except LLMError as exc:
                console.print(f"[red]{exc}[/]")
    except LLMError as exc:
        console.print(f"[red]{exc}[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
