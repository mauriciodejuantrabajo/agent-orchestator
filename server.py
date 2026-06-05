"""
Backend HTTP del orquestador (FastAPI).

Expone el orquestador multi-agente a un frontend web (React + shadcn/Tailwind):

    GET  /api/health          → ping simple.
    POST /api/run             → ejecuta una petición y devuelve el resultado final.
    GET  /api/stream?q=...     → ejecuta y transmite el progreso EN VIVO por SSE
                                 (Server-Sent Events): plan, inicio/fin de cada paso,
                                 y por último la respuesta unificada.

El orquestador (src/) no cambia: emite eventos por un callback `on_event` que aquí
empujamos a una cola thread-safe (porque los pasos corren en un ThreadPoolExecutor),
y un generador los va leyendo y mandando al navegador como eventos SSE.

Ejecutar:
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict
from typing import Iterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.llm import LLMError
from src.orchestrator import Event, Orchestrator

load_dotenv()

app = FastAPI(title="Agent Orchestrator API")

# El frontend de Vite corre en otro puerto (5173) durante el desarrollo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    question: str


def _sse(event: str, data: dict) -> str:
    """Formatea un mensaje en el protocolo SSE."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    """Ejecuta sin streaming: devuelve el resultado final en un solo JSON."""
    try:
        orch = Orchestrator()
        result = orch.run(req.question)
    except LLMError as exc:
        return {"error": str(exc)}
    return {
        "answer": result.answer,
        "bibliography": result.bibliography,
        "plan": [asdict_step(s) for s in result.plan.steps],
    }


def asdict_step(step) -> dict:
    return {"id": step.id, "agent": step.agent, "task": step.task,
            "depends_on": step.depends_on}


@app.get("/api/stream")
def stream(q: str) -> StreamingResponse:
    """Ejecuta y transmite el progreso en vivo como SSE."""

    def generate() -> Iterator[str]:
        events: queue.Queue = queue.Queue()
        SENTINEL = object()

        def on_event(ev: Event) -> None:
            events.put(asdict(ev))

        def worker() -> None:
            try:
                orch = Orchestrator(on_event=on_event)
                result = orch.run(q)
                events.put({
                    "_final": True,
                    "answer": result.answer,
                    "bibliography": result.bibliography,
                    "plan": [asdict_step(s) for s in result.plan.steps],
                })
            except LLMError as exc:
                events.put({"_error": True, "message": str(exc)})
            except Exception as exc:  # noqa: BLE001 — reportamos cualquier fallo al cliente
                events.put({"_error": True, "message": f"Error inesperado: {exc}"})
            finally:
                events.put(SENTINEL)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            item = events.get()
            if item is SENTINEL:
                break
            if isinstance(item, dict) and item.get("_final"):
                yield _sse("final", item)
            elif isinstance(item, dict) and item.get("_error"):
                yield _sse("error", item)
            else:
                yield _sse("progress", item)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
