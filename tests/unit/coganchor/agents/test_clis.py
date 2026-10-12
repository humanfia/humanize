"""A flow's own command line: parsed from pydantic models, answered as a program would be."""

from __future__ import annotations

import enum
import json
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from hmz.coganchor.agents.clis import Cli, Command, Shelf


class Colour(enum.Enum):
    RED = "red"
    BLUE = "blue"


class File(BaseModel):
    title: str = Field(description="what the ticket says, 100% of it")
    points: int = Field(3, description="how big it is")
    urgent: bool = False
    tags: list[str] = Field(default_factory=list)
    kind: Literal["bug", "feature"] = "bug"
    colour: Colour = Colour.RED
    owner: str | None = None


def _filed(ticket: File) -> File:
    return ticket


def _tix(*more: Command) -> Cli:
    return Cli(
        "tix", "Track tickets.", (Command("file", "File one.", _filed, File), *more)
    )


def test_help_lists_what_it_is_for_and_every_command() -> None:
    code, out, err = _tix(Command("list", "List them.", lambda: None)).run(["--help"])
    assert (code, err) == (0, "")
    assert out.startswith("usage: tix ")
    assert "Track tickets." in out
    assert "File one." in out
    assert "List them." in out


def test_a_commands_help_has_a_flag_for_every_field() -> None:
    code, out, _ = _tix().run(["file", "--help"])
    assert code == 0
    assert "usage: tix file" in out
    assert "--title TITLE" in out
    assert "what the ticket says, 100% of it" in out
    assert "how big it is (default: 3)" in out
    assert "--urgent, --no-urgent" in out
    assert "--tags [TAGS ...]" in out
    assert "{bug,feature}" in out
    assert "{red,blue}" in out
    assert "(default: red)" in out


def test_every_field_is_typed_as_words_and_made_into_the_model() -> None:
    code, out, err = _tix().run(
        [
            "file",
            "--title",
            "red build",
            "--points",
            "5",
            "--urgent",
            "--tags",
            "ci",
            "flaky",
            "--kind",
            "feature",
            "--colour",
            "blue",
            "--owner",
            "ann",
        ]
    )
    assert (code, err) == (0, "")
    assert json.loads(out) == {
        "title": "red build",
        "points": 5,
        "urgent": True,
        "tags": ["ci", "flaky"],
        "kind": "feature",
        "colour": "blue",
        "owner": "ann",
    }


def test_what_is_left_out_is_the_models_default() -> None:
    code, out, _ = _tix().run(["file", "--title", "x"])
    assert code == 0
    assert json.loads(out)["points"] == 3
    assert json.loads(out)["tags"] == []


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        ([], "the following arguments are required: COMMAND"),
        (["nope"], "invalid choice: 'nope'"),
        (["file"], "the following arguments are required: --title"),
        (["file", "--title", "x", "--kind", "chore"], "invalid choice: 'chore'"),
        (["file", "--title", "x", "--points", "many"], "--points: Input should be"),
        (["file", "--title", "x", "--bogus"], "unrecognized arguments: --bogus"),
    ],
)
def test_a_line_it_will_not_take_is_a_usage_error(argv: list[str], said: str) -> None:
    code, out, err = _tix().run(argv)
    assert (code, out) == (2, "")
    assert err.startswith("usage: tix")
    assert said in err


@pytest.mark.parametrize(
    ("answers", "printed"),
    [
        ("done", "done\n"),
        ("done\n", "done\n"),
        ("", ""),
        (None, ""),
        ({"n": 1}, '{\n  "n": 1\n}\n'),
        (File(title="t", points=3), None),
    ],
)
def test_what_the_function_answers_is_what_is_printed(
    answers: object, printed: str | None
) -> None:
    cli = Cli("one", "One.", (Command("go", "Go.", lambda: answers),))
    code, out, err = cli.run(["go"])
    assert (code, err) == (0, "")
    if printed is None:
        assert json.loads(out)["title"] == "t"
    else:
        assert out == printed


def test_a_function_leaving_with_a_status_exits_with_it() -> None:
    def leaves(code: object) -> None:
        raise SystemExit(code)

    cli = Cli(
        "one",
        "One.",
        (
            Command("four", "4.", lambda: leaves(4)),
            Command("none", "0.", lambda: leaves(None)),
            Command("said", "1.", lambda: leaves("out of tickets")),
        ),
    )
    assert cli.run(["four"]) == (4, "", "")
    assert cli.run(["none"]) == (0, "", "")
    assert cli.run(["said"]) == (1, "", "out of tickets\n")


def test_a_function_that_raises_is_a_program_that_failed() -> None:
    cli = Cli("one", "One.", (Command("go", "Go.", lambda: 1 / 0),))
    assert cli.run(["go"]) == (1, "", "one: ZeroDivisionError: division by zero\n")


@pytest.mark.parametrize("name", ["", "a/b", "-x", ".x", "a b"])
def test_a_name_no_shell_could_run_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="not a name"):
        Cli(name, "No.", (Command("go", "Go.", lambda: None),))


def test_a_command_line_needs_commands_each_named_once() -> None:
    with pytest.raises(ValueError, match="no commands"):
        Cli("one", "One.", ())
    with pytest.raises(ValueError, match="twice"):
        Cli("one", "One.", (Command("go", "a", print), Command("go", "b", print)))


def test_a_shelf_nothing_was_shelved_on_has_nowhere_and_adds_nothing() -> None:
    shelf = Shelf()
    shelf.shelves(1, ())
    assert shelf.empty()
    assert shelf.shelved() == ()
    assert shelf.where() == ""
    assert shelf.environ({"PATH": "/bin"}) == {}
    shelf.close()
    shelf.close()


class Size(enum.Enum):
    SMALL = 1
    LARGE = 2


class Sized(BaseModel):
    n: Literal[1, 2]
    size: Size = Size.SMALL
    from_: str = Field("here", alias="from")


def _sized(one: Sized) -> Sized:
    return one


def test_choices_that_are_not_words_and_aliased_fields_are_taken_as_typed() -> None:
    cli = Cli("one", "One.", (Command("go", "Go.", _sized, Sized),))
    code, out, err = cli.run(["go", "--n", "2", "--size", "2", "--from-", "there"])
    assert (code, err) == (0, "")
    assert json.loads(out) == {"n": 2, "size": 2, "from_": "there"}
    code, _, err = cli.run(["go", "--n", "3"])
    assert code == 2
    assert "invalid choice: '3'" in err
