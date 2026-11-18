"""`hmz.flows.faces`: the face a flow ships, how it is made, and what an agent writes one to."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import textwrap
from typing import TYPE_CHECKING, Any, Literal
from unittest import mock

import pydantic
import pytest

from hmz.flows import FACE_GUIDE, Face, Outworlder

if TYPE_CHECKING:
    from pathlib import Path

PAGE = "<!doctype html><title>Review</title><p>hi</p>"


class Review(pydantic.BaseModel):
    verdict: Literal["approve", "reject"] = "approve"
    notes: str


def writer(said: str) -> mock.Mock:
    """An agent whose one turn says `said`."""
    double = mock.Mock(name="designer", role="designer")
    double.run = mock.AsyncMock(return_value=said)
    return double


# ---------------------------------------------------------------------------- the face


def test_a_face_is_its_html_and_title() -> None:
    face = Face(html=PAGE, title="Review")

    assert face.html == PAGE
    assert face.title == "Review"
    assert Face(PAGE).title == ""


def test_face_html_makes_a_face_of_the_text() -> None:
    assert Face.html(PAGE, title="Review") == Face(html=PAGE, title="Review")
    assert Face.html(PAGE) == Face(PAGE)


def test_a_faces_hash_is_the_sha256_of_its_html() -> None:
    assert Face(PAGE).hash == hashlib.sha256(PAGE.encode()).hexdigest()
    assert Face(PAGE, title="a").hash == Face(PAGE, title="b").hash


def test_faces_of_the_same_html_and_title_are_equal() -> None:
    assert Face(PAGE, "a") == Face(PAGE, "a")
    assert hash(Face(PAGE, "a")) == hash(Face(PAGE, "a"))
    assert Face(PAGE, "a") != Face(PAGE, "b")
    assert Face(PAGE) != Face(PAGE + " ")
    assert Face(PAGE) != PAGE


def test_a_face_is_frozen() -> None:
    face = Face(PAGE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        face.title = "other"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        face.html = "other"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(dataclasses.FrozenInstanceError):
        del face.title  # pyright: ignore[reportAttributeAccessIssue]


def test_a_faces_repr_names_it_without_its_html() -> None:
    face = Face(PAGE * 100, title="Review")
    assert repr(face) == f"Face(title='Review', hash={face.hash[:12]!r})"


# ---------------------------------------------------------------------------- Face.file


def test_a_relative_file_is_read_from_the_calling_modules_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "faces").mkdir()
    (tmp_path / "faces" / "review.html").write_text(PAGE, encoding="utf-8")
    module: dict[str, Any] = {"__file__": str(tmp_path / "flow.py"), "Face": Face}

    exec("made = Face.file('faces/review.html', title='Review')", module)  # noqa: S102

    assert module["made"] == Face(PAGE, title="Review")


def test_an_absolute_file_is_read_where_it_is(tmp_path: Path) -> None:
    (tmp_path / "review.html").write_text(PAGE, encoding="utf-8")

    assert Face.file(tmp_path / "review.html") == Face(PAGE)


def test_a_file_from_no_module_is_read_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "review.html").write_text(PAGE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    module: dict[str, Any] = {"Face": Face}

    exec("made = Face.file('review.html')", module)  # noqa: S102

    assert module["made"] == Face(PAGE)


def test_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Face.file(tmp_path / "none.html")


# -------------------------------------------------------------------------- Face.design


async def test_design_takes_the_fenced_html_and_its_title() -> None:
    agent = writer(f"Here it is:\n\n```html\n{PAGE}\n```\n\nEnjoy.")
    session = mock.sentinel.session

    face = await Face.design(agent, session=session, about="a code review")

    assert face == Face(PAGE, title="Review")
    agent.run.assert_awaited_once()
    assert agent.run.await_args is not None
    assert agent.run.await_args.kwargs == {"session": session, "env": None}


async def test_design_takes_the_whole_answer_where_nothing_is_fenced() -> None:
    face = await Face.design(writer(f"  {PAGE}\n"), session=mock.sentinel.s, about="x")

    assert face.html == PAGE


async def test_design_takes_the_first_fenced_block() -> None:
    said = "```html\n<p>one</p>\n```\n```html\n<p>two</p>\n```"

    face = await Face.design(writer(said), session=mock.sentinel.s, about="x")

    assert face == Face("<p>one</p>")


async def test_design_tells_the_agent_the_guide_the_purpose_and_the_schema() -> None:
    agent = writer(PAGE)
    env = mock.sentinel.env

    await Face.design(
        agent,
        session=mock.sentinel.s,
        about="review a pull request",
        output_schema=Review,
        env=env,
    )

    assert agent.run.await_args is not None
    prompt = agent.run.await_args.args[0]
    assert prompt.startswith(FACE_GUIDE)
    assert "review a pull request" in prompt
    assert json.dumps(Review.model_json_schema(), indent=2) in prompt
    assert agent.run.await_args.kwargs["env"] is env


async def test_design_for_text_answers_says_so() -> None:
    agent = writer(PAGE)

    await Face.design(agent, session=mock.sentinel.s, about="x")

    assert agent.run.await_args is not None
    assert "takes a string" in agent.run.await_args.args[0]


async def test_design_keeps_a_fence_inside_the_page() -> None:
    page = '<script>\nconst fence = "```";\nconst diff = "```diff";\n</script>'

    face = await Face.design(
        writer(f"```html\n{page}\n```\nDone."), session=mock.sentinel.s, about="x"
    )

    assert face.html == page


async def test_designs_title_is_the_documents_as_read() -> None:
    page = "<title>\n  Review &amp;\n  merge </title><p>hi</p>"

    face = await Face.design(writer(page), session=mock.sentinel.s, about="x")

    assert face.title == "Review & merge"


@pytest.mark.parametrize(
    "said",
    [
        "",
        "I could not do that.",
        "```html\n\n```",
        "Here is the face: <p>hi</p>",
    ],
)
async def test_design_with_no_html_back_raises(said: str) -> None:
    with pytest.raises(ValueError, match="no HTML"):
        await Face.design(writer(said), session=mock.sentinel.s, about="x")


async def test_design_lets_the_agents_error_through() -> None:
    agent = writer("")
    agent.run.side_effect = RuntimeError("turn failed")

    with pytest.raises(RuntimeError, match="turn failed"):
        await Face.design(agent, session=mock.sentinel.s, about="x")


# ---------------------------------------------------------------------------- the guide


@pytest.mark.parametrize(
    "part",
    [
        'hmz.on("ask"',
        'hmz.on("show"',
        'hmz.on("theme"',
        "hmz.submit(",
        "hmz.resize(",
        "{ok: false, errors",
        "--paper",
        "--ink",
        "/vendor/markdown.js",
        "no network",
        "```html",
    ],
)
def test_the_guide_covers_the_bridge_and_the_theme(part: str) -> None:
    assert part in FACE_GUIDE


# ------------------------------------------------------------------- what an outworlder takes


def test_an_outworlder_spawns_a_session_with_a_face() -> None:
    face = inspect.signature(Outworlder.spawn).parameters["face"]
    assert face.kind is inspect.Parameter.KEYWORD_ONLY
    assert face.default is None


def test_an_outworlders_turn_takes_context() -> None:
    # A protocol's overloads leave nothing at run time but their source.
    declared = ast.parse(textwrap.dedent(inspect.getsource(Outworlder))).body[0]
    assert isinstance(declared, ast.ClassDef)
    runs = [
        one
        for one in declared.body
        if isinstance(one, ast.AsyncFunctionDef) and one.name == "run"
    ]
    assert len(runs) == 2
    for run in runs:
        named = dict(zip(run.args.kwonlyargs, run.args.kw_defaults, strict=True))
        context = {arg.arg: default for arg, default in named.items()}["context"]
        assert isinstance(context, ast.Tuple)
        assert context.elts == []


def test_an_outworlder_shows_context_with_nothing_to_answer() -> None:
    show = inspect.signature(Outworlder.show)
    assert inspect.iscoroutinefunction(Outworlder.show)
    assert list(show.parameters) == ["self", "context", "session"]
    assert show.parameters["session"].kind is inspect.Parameter.KEYWORD_ONLY
