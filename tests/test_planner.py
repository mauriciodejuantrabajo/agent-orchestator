"""Tests del planner: parseo del JSON del plan y validación del DAG (sin red)."""

from __future__ import annotations

import pytest

from src.planner import Plan, Planner, Step


VALID = {"research", "math", "data", "writer"}


class FakeClient:
    """LLM falso que devuelve un contenido fijo cuando se le pide un plan."""
    def __init__(self, content: str):
        self.content = content

    def chat(self, messages, tools=None):
        return {"content": self.content}


def _planner(content: str) -> Planner:
    return Planner(FakeClient(content), catalog="(catálogo)", valid_agents=VALID)


def test_parse_plan_valido():
    raw = (
        '{"steps": ['
        '{"id":"s1","agent":"research","task":"buscar","depends_on":[]},'
        '{"id":"s2","agent":"writer","task":"redactar","depends_on":["s1"]}'
        ']}'
    )
    plan = _planner(raw).plan("lo que sea")
    assert [s.id for s in plan.steps] == ["s1", "s2"]
    assert plan.steps[1].depends_on == ["s1"]


def test_parse_tolera_fences_markdown():
    raw = '```json\n{"steps":[{"id":"s1","agent":"math","task":"2+2","depends_on":[]}]}\n```'
    plan = _planner(raw).plan("x")
    assert plan.steps[0].agent == "math"


def test_plan_invalido_cae_a_fallback_writer():
    # JSON roto -> debe devolver un plan trivial con writer.
    plan = _planner("esto no es json").plan("pregunta")
    assert len(plan.steps) == 1
    assert plan.steps[0].agent == "writer"


def test_validate_detecta_agente_desconocido():
    plan = Plan(steps=[Step(id="s1", agent="inexistente", task="x")])
    with pytest.raises(ValueError):
        plan.validate(VALID)


def test_validate_detecta_dependencia_inexistente():
    plan = Plan(steps=[Step(id="s1", agent="math", task="x", depends_on=["s9"])])
    with pytest.raises(ValueError):
        plan.validate(VALID)


def test_validate_detecta_ciclo():
    plan = Plan(steps=[
        Step(id="s1", agent="math", task="x", depends_on=["s2"]),
        Step(id="s2", agent="math", task="y", depends_on=["s1"]),
    ])
    with pytest.raises(ValueError):
        plan.validate(VALID)
