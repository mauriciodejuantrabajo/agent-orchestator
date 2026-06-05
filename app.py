"""
Interfaz web del orquestador (Streamlit).

Escribes una petición y ves, en vivo, cómo el supervisor la descompone en un plan
y delega cada sub-tarea a un agente especializado (con su traza de herramientas).
Al final muestra la respuesta unificada y las fuentes.

Ejecutar:
    streamlit run app.py
"""

from __future__ import annotations

from dotenv import load_dotenv

import streamlit as st

from src.llm import LLMError
from src.orchestrator import Event, Orchestrator

load_dotenv()

st.set_page_config(page_title="Agent Orchestrator", page_icon="🧭", layout="centered")

_AGENT_EMOJI = {"research": "🔎", "math": "🧮", "data": "🗄️", "writer": "✍️"}

st.title("🧭 Agent Orchestrator")
st.caption(
    "Un supervisor que **planifica** y **rutea** cada sub-tarea al agente adecuado "
    "(investigación web, cálculo, datos SQL, redacción), en paralelo cuando puede."
)

with st.sidebar:
    st.header("Ejemplos")
    st.markdown(
        "- ¿Cuántas notebooks se vendieron y cuánto facturaron en total?\n"
        "- Busca la población de Uruguay y de Paraguay y calcula la diferencia.\n"
        "- ¿Qué región vendió más unidades? Resúmelo en un párrafo.\n"
        "- ¿Qué es el Model Context Protocol y cuántas letras tiene su sigla?"
    )
    st.divider()
    st.markdown(
        "Los agentes usan herramientas reales: búsqueda web (DuckDuckGo), una "
        "calculadora segura (sin ejecutar código) y SQL de **solo lectura** sobre "
        "una base de ejemplo."
    )

question = st.text_input(
    "Tu petición",
    placeholder="Ej: ¿Qué región vendió más unidades y cuánto facturó?",
)
go = st.button("Ejecutar", type="primary")

if go and question.strip():
    try:
        progress_box = st.container()
        events: list[Event] = []

        def on_event(ev: Event) -> None:
            events.append(ev)
            with progress_box:
                if ev.kind == "plan":
                    st.info(f"🧭 **Plan:** {ev.message}")
                elif ev.kind == "step_start":
                    emoji = _AGENT_EMOJI.get(ev.agent, "•")
                    st.write(f"{emoji} **{ev.agent}** [{ev.step_id}] → {ev.message}")
                elif ev.kind == "step_done":
                    st.caption(f"   herramientas: {ev.message}")
                elif ev.kind == "step_failed":
                    st.warning(f"   ✗ {ev.agent} falló ({ev.message})")
                elif ev.kind == "info":
                    st.caption(f"   ℹ {ev.message}")

        orch = Orchestrator(on_event=on_event)
        with st.spinner("El orquestador está trabajando…"):
            result = orch.run(question.strip())

        st.divider()
        st.subheader("Respuesta")
        st.markdown(result.answer)
        if result.bibliography:
            with st.expander("Fuentes"):
                st.text(result.bibliography)
    except LLMError as exc:
        st.error(str(exc))
elif go:
    st.warning("Escribe una petición primero.")
