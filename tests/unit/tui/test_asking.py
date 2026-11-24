"""`hmz.tui.asking`: a question asked as a form -- its fields, its context, its sheet."""

from __future__ import annotations

import enum
from typing import Any, Literal, cast

import pytest
from pydantic import BaseModel, Field
from rich.console import Console
from textual.app import App
from textual.widgets import Label

from hmz.tui import asking


class Colour(enum.Enum):
    """A colour, which pydantic writes as a `$ref` to an enum."""

    RED = "red"
    BLUE = "blue"


class Review(BaseModel):
    """Every kind of field a form asks."""

    verdict: Literal["approve", "reject"] = Field(description="what to do")
    notes: str
    count: int = 3
    ratio: float | None = None
    tests: bool = Field(default=True, description="Write tests.")
    colour: Colour = Colour.RED
    tags: list[str] = Field(default_factory=list[str])
    extra: dict[str, int] = Field(default_factory=dict[str, int])


def _drawn(*things: object) -> str:
    """What some things look like, drawn as plain text."""
    console = Console(width=100, record=True, color_system=None)
    for one in things:
        console.print(one)
    return console.export_text()


# -- Fields -------------------------------------------------------------------------------------


def test_fields_are_read_off_the_schema_in_order() -> None:
    by = {one.name: one for one in asking.fields(Review.model_json_schema())}

    assert list(by) == [
        "verdict",
        "notes",
        "count",
        "ratio",
        "tests",
        "colour",
        "tags",
        "extra",
    ]
    assert by["verdict"].kind == "choice"
    assert by["verdict"].required
    assert by["verdict"].choices == (("approve", "approve"), ("reject", "reject"))
    assert (by["notes"].kind, by["notes"].required) == ("text", True)
    assert (by["count"].kind, by["count"].default) == ("integer", 3)
    assert by["ratio"].kind == "number"
    assert not by["ratio"].required
    assert by["colour"].choices == (("red", "red"), ("blue", "blue"))
    assert (by["tags"].kind, by["tags"].items) == ("list", "text")
    assert by["extra"].kind == "json"


def test_a_field_is_named_by_its_own_title_not_by_its_type_s() -> None:
    class Limits(BaseModel):
        turns: int = 3

    class Triage(BaseModel):
        severity: Colour
        confidence: Colour
        actor_limits: Limits
        shade: Colour = Field(title="Which shade")

    titles = {one.name: one.title for one in asking.fields(Triage.model_json_schema())}

    assert titles == {
        "severity": "severity",
        "confidence": "confidence",
        "actor_limits": "actor limits",
        "shade": "Which shade",
    }


def test_a_yes_or_no_is_worded_from_a_short_description() -> None:
    (tests,) = [
        one for one in asking.fields(Review.model_json_schema()) if one.name == "tests"
    ]

    assert tests.choices == (("Yes, write tests", True), ("No", False))


def test_a_long_description_leaves_a_plain_yes() -> None:
    schema = {
        "type": "object",
        "properties": {"go": {"type": "boolean", "description": "x" * 80}},
    }

    (go,) = asking.fields(schema)

    assert go.choices[0] == ("Yes", True)


def test_a_schema_that_is_not_an_object_is_one_unnamed_field() -> None:
    (whole,) = asking.fields({"type": "integer"})

    assert (whole.name, whole.kind, whole.required) == ("", "integer", True)


def test_no_schema_is_no_fields() -> None:
    assert asking.fields(None) == []


# -- Values -------------------------------------------------------------------------------------


def test_a_form_s_answer_is_typed_as_the_schema_says() -> None:
    fields = asking.fields(Review.model_json_schema())

    answer, wrong = asking.valued(
        fields,
        {
            "verdict": "approve",
            "notes": "fine",
            "count": "4",
            "ratio": "0.5",
            "tests": "No",
            "colour": "blue",
            "tags": "a\n\nb",
            "extra": '{"x": 1}',
        },
    )

    assert wrong == {}
    assert answer == {
        "verdict": "approve",
        "notes": "fine",
        "count": 4,
        "ratio": 0.5,
        "tests": False,
        "colour": "blue",
        "tags": ["a", "b"],
        "extra": {"x": 1},
    }


def test_blank_fields_that_are_not_required_are_left_to_their_defaults() -> None:
    fields = asking.fields(Review.model_json_schema())

    answer, wrong = asking.valued(fields, {"verdict": "reject", "notes": "no"})

    assert wrong == {}
    assert answer == {"verdict": "reject", "notes": "no"}


def test_what_is_wrong_is_said_field_by_field_in_plain_words() -> None:
    fields = asking.fields(Review.model_json_schema())

    answer, wrong = asking.valued(
        fields, {"verdict": "", "notes": "x", "count": "three", "extra": "{"}
    )

    assert answer is None
    assert wrong["verdict"] == "This needs an answer."
    assert wrong["count"] == "This needs a whole number."
    assert wrong["extra"].startswith("This is not valid JSON")


def test_the_one_value_of_a_schema_that_is_not_an_object_is_the_answer() -> None:
    assert asking.valued(asking.fields({"type": "integer"}), {"": "7"}) == (7, {})


# -- Saying the answer --------------------------------------------------------------------------


def test_an_answer_is_said_as_the_choices_picked_and_the_words_written() -> None:
    schema = Review.model_json_schema()

    said = asking.summary(
        {"verdict": "approve", "notes": "LGTM", "tests": True}, schema
    )

    assert said == "approve · 'LGTM' · Yes, write tests"


def test_a_secret_is_typed_as_bullets_and_said_back_as_stars() -> None:
    class Login(BaseModel):
        user: str
        token: str = Field(json_schema_extra={"hmz:widget": "secret"})

    schema = Login.model_json_schema()

    (_, token) = asking.fields(schema)
    assert token.secret
    assert asking.summary({"user": "ann", "token": "s3cret"}, schema) == "'ann' · ***"


def test_a_long_answer_is_shortened() -> None:
    said = asking.summary("word " * 40)

    assert said.endswith("…'")
    assert len(said) < 50


# -- Context ------------------------------------------------------------------------------------


PATCH = """\
--- a/a.py
+++ b/a.py
-old
+new
+more
--- a/b.py
+++ b/b.py
+x
"""


def test_a_diff_says_what_it_changes_before_it_is_shown() -> None:
    drawn = _drawn(*asking.blocks([{"kind": "diff", "patch": PATCH, "title": "fix"}]))

    assert "fix · diff · +3 \N{MINUS SIGN}1 in 2 files" in drawn
    assert "+more" in drawn


def test_a_long_table_is_counted_and_collapsed() -> None:
    rows = [[str(at), "ok"] for at in range(40)]
    drawn = _drawn(
        *asking.blocks(
            [
                {"kind": "markdown", "text": "first"},
                {"kind": "table", "columns": ["n", "state"], "rows": rows},
            ],
            web="http://here",
        )
    )

    assert "table · 40 rows" in drawn
    assert "… 30 more rows -- read all at http://here" in drawn
    assert "39" not in drawn


def test_an_image_or_a_chart_is_a_line_saying_where_to_see_it() -> None:
    drawn = _drawn(
        *asking.blocks(
            [
                {"kind": "image", "mime": "image/png", "data": "", "alt": "the plot"},
                {"kind": "chart", "spec": {"title": "speed"}},
            ],
            web="http://here",
        )
    )

    assert "image · the plot · see in web page: http://here" in drawn
    assert "chart · speed · see in web page: http://here" in drawn


def test_without_the_web_page_it_says_how_to_open_one() -> None:
    drawn = _drawn(*asking.blocks([{"kind": "chart", "spec": {}}]))

    assert "open in web page (hmz web)" in drawn


def test_code_and_json_say_how_long_they_are() -> None:
    drawn = _drawn(
        *asking.blocks(
            [
                {"kind": "code", "text": "a = 1\nb = 2", "language": "python"},
                {"kind": "json", "value": {"a": 1}},
            ]
        )
    )

    assert "python · 2 lines" in drawn
    assert "json · 3 lines" in drawn


# -- The sheet ----------------------------------------------------------------------------------


class _Host(App[None]):
    """Puts a form up, and keeps what it sent and what it kept."""

    def __init__(self, question: dict[str, Any], **given: Any) -> None:
        super().__init__()
        self.sent: list[Any] = []
        self.kept: list[object] = []
        self.sheet = asking.Asks(
            question,
            send=lambda _, value: self.sent.append(value),
            keep=self.kept.append,
            **given,
        )

    def on_mount(self) -> None:
        self.push_screen(self.sheet)


def _question() -> dict[str, Any]:
    return {
        "question": "q1",
        "role": "human",
        "text": "Ship it?",
        "schema": Review.model_json_schema(),
    }


def _tuning(host: _Host) -> str:
    return str(host.sheet.query_one("#tuning", Label).content)


async def test_answering_with_required_fields_left_says_how_many_and_sends_nothing() -> (
    None
):
    host = _Host(_question())
    async with host.run_test() as pilot:
        await pilot.pause()
        assert host.sheet.actions()[-1].label == "Answer · 2 required left"

        host.sheet.action_done()
        await pilot.pause()

        assert host.sent == []
        assert "2 required left" in _tuning(host)


async def test_a_digit_picks_a_choice_and_the_suggestions_go_with_the_answer() -> None:
    host = _Host(_question(), typed="ship it")
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")
        assert host.sheet.actions()[-1].label == "Answer"

        host.sheet.action_done()
        await pilot.pause()

    assert host.sent == [
        {
            "verdict": "reject",
            "notes": "ship it",
            "count": 3,
            "tests": True,
            "colour": "red",
        }
    ]


async def test_a_refusal_is_said_beside_the_field_it_is_about() -> None:
    host = _Host(_question(), typed="x")
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("1")
        host.sheet.action_done()
        await pilot.pause()

        host.sheet.refused(
            "the answer does not fit: too short",
            [{"path": ["notes"], "message": "too short"}],
        )
        await pilot.pause()

        assert host.sheet.under() == "notes"
        assert "One answer needs another look." in _tuning(host)


async def test_a_refusal_about_no_field_is_said_under_the_form() -> None:
    host = _Host(_question(), typed="x")
    async with host.run_test() as pilot:
        await pilot.pause()
        host.sheet.refused(
            "the answer does not fit: bad", [{"path": [], "message": "bad"}]
        )
        await pilot.pause()

        assert "bad" in _tuning(host)


async def test_esc_keeps_the_draft_for_next_time() -> None:
    host = _Host(_question(), typed="half done")
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    (draft,) = host.kept
    again = asking.Asks(
        _question(), send=lambda _, __: None, keep=lambda _: None, draft=draft
    )
    assert again.draft() == draft


@pytest.mark.parametrize("key", ["right", "left"])
async def test_the_arrows_across_move_a_choice_along_its_segments(key: str) -> None:
    host = _Host(_question(), typed="ok")
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press(key)
        host.sheet.action_done()
        await pilot.pause()

    assert host.sent[0]["verdict"] == ("approve" if key == "right" else "reject")


@pytest.mark.parametrize("typed", ["reject", "Reject", "2"])
async def test_words_typed_that_name_a_choice_pick_it(typed: str) -> None:
    host = _Host(_question(), typed=typed)
    async with host.run_test() as pilot:
        await pilot.pause()

        held = cast("tuple[dict[str, str], bool]", host.sheet.draft())[0]
        assert held["verdict"] == "reject"
        assert "notes" not in held


async def test_words_that_answer_no_field_are_said_rather_than_dropped() -> None:
    question = {
        "question": "q1",
        "text": "Go?",
        "schema": {
            "type": "object",
            "properties": {"go": {"type": "boolean"}},
            "required": ["go"],
        },
    }
    host = _Host(question, typed="maybe")
    async with host.run_test() as pilot:
        await pilot.pause()

        assert '"maybe" answers no field' in _tuning(host)


def test_a_required_field_that_may_be_null_is_answered_blank() -> None:
    schema = {
        "type": "object",
        "properties": {"why": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        "required": ["why"],
    }

    assert asking.valued(asking.fields(schema), {"why": ""}) == ({"why": None}, {})
