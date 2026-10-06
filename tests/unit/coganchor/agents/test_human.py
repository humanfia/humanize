"""`hmz.coganchor.agents.human`: the person at the prompt, driven as an agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import BaseModel, Field, model_validator

from hmz.coganchor.agents.allowance import Allowance, Ledger
from hmz.coganchor.agents.board import Board
from hmz.coganchor.agents.human import HumanAgent, HumanSession
from tests.unit.coganchor.agents.doubles_core import heard

if TYPE_CHECKING:
    from hmz.coganchor.agents.event import Question


class _Plan(BaseModel):
    title: str = Field(description="What to call it")
    kind: Literal["bug", "feature"]
    urgent: bool = False
    tags: list[str] = Field(default_factory=list[str])
    size: int = 1


def _answering(*answers: str) -> tuple[HumanAgent, list[Question]]:
    """A person who types these answers in turn, and what they were asked."""
    person = HumanAgent()
    asked: list[Question] = []
    left = iter(answers)

    def ask(question: Question) -> str | None:
        asked.append(question)
        return next(left, None)

    person.ask = ask
    return person, asked


def test_a_person_is_an_agent_that_spends_nothing() -> None:
    person = HumanAgent()
    assert person.id == "human"
    assert not HumanAgent.spends
    assert HumanAgent.moments == frozenset()
    assert isinstance(person.board, Board)
    assert person.board is person.board
    assert isinstance(person.new(), HumanSession)
    assert HumanAgent(name="alice").id == "alice"


def test_a_clone_is_another_person_with_another_board() -> None:
    person = HumanAgent(name="alice")
    person.board.put("todo", "x")
    other = person.clone()
    assert isinstance(other, HumanAgent)
    assert other.board.items() == ()
    assert other.id == "human"
    assert person.clone(name="bob").id == "bob"


def test_said_to_they_answer_what_they_type() -> None:
    person = HumanAgent()
    person.prompting = lambda: "  sounds good  "
    said = heard(person)
    assert person("here is the plan") == "sounds good"
    assert said == []  # their turn is nobody's to watch


def test_with_nobody_there_they_answer_nothing() -> None:
    assert HumanAgent()("anyone?") == ""


def test_a_shape_is_put_a_field_at_a_time() -> None:
    person, asked = _answering("Fix login", "bug", "yes", "auth, ui , ", "3")
    plan = person("What should we do?", schema=_Plan)
    assert plan == _Plan(
        title="Fix login", kind="bug", urgent=True, tags=["auth", "ui"], size=3
    )
    assert [one.text for one in asked] == [
        "What should we do?\n\nWhat to call it",
        "kind",
        "urgent -- or `-` for no",
        "tags (several, separated by commas) -- or `-` for nothing",
        "size (a number) -- or `-` for 1",
    ]
    assert [one.options for one in asked] == [
        (),
        ("bug", "feature"),
        ("yes", "no"),
        (),
        (),
    ]


def test_a_dash_leaves_a_field_at_its_default() -> None:
    person, _ = _answering("t", "feature", "-", "-", "-")
    assert person("?", schema=_Plan) == _Plan(title="t", kind="feature")


def test_a_wrong_answer_is_put_back_in_the_models_words() -> None:
    person, asked = _answering("t", "chore", "no", "", "2", "bug")
    assert person("?", schema=_Plan) == _Plan(title="t", kind="bug", size=2)
    assert asked[-1].options == ("bug", "feature")
    assert asked[-1].text.endswith("\n\nkind")
    assert asked[-1].text != "kind"


def test_somebody_who_will_not_answer_is_given_up_on() -> None:
    person, asked = _answering("t", "x", "no", "", "1", "y", "z", "w")
    assert person("?", schema=_Plan, suppress=True) is None
    assert len(asked) == 8


def test_somebody_who_walks_away_answers_nothing() -> None:
    person, _ = _answering("t")
    assert person("?", schema=_Plan, suppress=True) is None
    person, _ = _answering("t", "x", "no", "", "1")
    assert person("?", schema=_Plan, suppress=True) is None


class _Range(BaseModel):
    low: int
    high: int

    @model_validator(mode="after")
    def _ordered(self) -> _Range:
        if self.low > self.high:
            raise ValueError("low above high")
        return self


def test_a_rule_over_several_fields_has_nothing_to_put_back() -> None:
    person, asked = _answering("5", "1")
    assert person("?", schema=_Range, suppress=True) is None
    assert len(asked) == 2


def test_the_person_is_never_stopped_by_the_runs_allowance() -> None:
    person = HumanAgent()
    person.allowance = Ledger(Allowance(tokens=1e-9), [person])
    person.prompting = lambda: "still here"
    assert person("hello") == "still here"
    assert not person.stopped


@pytest.mark.parametrize("answer", ["", "nothing"])
def test_an_empty_default_is_said_as_nothing(answer: str) -> None:
    class Note(BaseModel):
        text: str = ""

    person, asked = _answering(answer)
    person("?", schema=Note)
    assert asked[0].text == "?\n\ntext -- or `-` for nothing"
