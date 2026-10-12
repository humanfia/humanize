"""`hmz.tui.pick.Does`: what there is to do with one epic, and why resuming is not it."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from hmz.tui import pick

if TYPE_CHECKING:
    from hmz.runtime.epic import Ran


def _does(*, resumable: bool, foreign: str = "") -> pick.Does:
    ran = SimpleNamespace(
        at=Path("/epics/one"),
        began="2026-10-12T01:02:03Z",
        flow="ralph",
        how="done",
        agents={},
        sessions=[],
    )
    return pick.Does(cast("Ran", ran), resumable=resumable, foreign=foreign)


@pytest.mark.parametrize(
    ("resumable", "foreign", "rows", "said"),
    [
        (True, "", ["resume", "export", "exomyth"], ""),
        (
            False,
            "",
            ["export", "exomyth"],
            "ralph is not resumable, so this run cannot be resumed",
        ),
        (
            True,
            "the workspace it ran in, /w, is not on this machine",
            ["export", "exomyth"],
            (
                "this epic cannot be resumed here: "
                "the workspace it ran in, /w, is not on this machine"
            ),
        ),
    ],
)
def test_does_offers_resume_only_where_it_can_and_says_why_not(
    *, resumable: bool, foreign: str, rows: list[str], said: str
) -> None:
    does = _does(resumable=resumable, foreign=foreign)

    assert [one[0] for one in does.rows()] == rows
    assert does.nothing() == said
