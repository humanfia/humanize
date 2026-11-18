"""A run asking for a schema whole, with context beside it, answered through the daemon.

The host is started for real by `hmz.daemon.host()` and the frontend is a `hmz.daemon.Link`.
The flow drives no agent: it shows its reviewer a table, asks it for a `Review` beside a diff,
and writes down what it was answered. The frontend answers once with a value that does not fit,
is refused with every way it does not, and then answers with one that does.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.runtime import Refused
from tests.integration.doubles_daemon import (
    REVIEWS,
    Heard,
    hosting,
    project,
    until,
    written,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(90)]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    written(at, "reviews", REVIEWS)
    with hosting():
        yield at


def test_a_schema_asked_with_context_is_answered_once_the_answer_fits(
    workspace: Path,
) -> None:
    held = daemon.host()
    heard = Heard()
    with held.link(name="alice") as link:
        link.heard(heard)
        link.start("./reviews", "the parser", budget={"cost": 1})
        assert until(lambda: heard.of("asked"))

        (shown,) = heard.of("shown")
        assert (shown["role"], shown["session"]) == ("reviewer", "reviewer/1")
        assert [one["kind"] for one in shown["context"]] == ["table"]
        assert shown["context"][0]["rows"] == [["lint", "passed"]]

        (asked,) = heard.of("asked")
        assert asked["text"] == "review the parser"
        assert (asked["options"], asked["face"], asked["session"]) == (
            [],
            None,
            "reviewer/1",
        )
        assert asked["schema"]["required"] == ["verdict"]
        assert [one["kind"] for one in asked["context"]] == ["diff"]
        assert "+new" in asked["context"][0]["patch"]

        with pytest.raises(Refused, match="the answer does not fit") as refused:
            link.answer(asked["question"], value={"verdict": "maybe"})
        assert refused.value.code == 400
        assert refused.value.data is not None
        errors = refused.value.data["errors"]
        assert errors[0]["path"] == ["verdict"]
        assert not heard.of("answered")

        link.answer(asked["question"], '{"verdict": "approve", "notes": "LGTM"}')
        assert until(lambda: heard.of("ended"))

    assert heard.of("ended")[0]["how"] == "done", heard.of("ended")[0]["why"]
    assert json.loads((workspace / "result.json").read_text()) == {
        "verdict": "approve",
        "notes": "LGTM",
    }
    (answered,) = heard.of("answered")
    assert json.loads(answered["text"]) == {"verdict": "approve", "notes": "LGTM"}
