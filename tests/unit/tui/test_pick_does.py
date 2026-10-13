"""`hmz.tui.pick.Does`: what there is to do with one epic, and why resuming is not it."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from hmz.tui import pick

if TYPE_CHECKING:
    from hmz.runtime.epic import Ran


#: What every epic offers last: copying what it is called, what it was asked, and where it is.
_COPIES = ["copy-name", "copy-task", "copy-path"]


def _does(
    *,
    flow: str = "ralph",
    resumable: bool,
    foreign: str = "",
    uploads: bool = False,
    backed: dict[str, dict[str, object]] | None = None,
) -> pick.Does:
    ran = SimpleNamespace(
        at=Path("/epics/one"),
        began="2026-10-12T01:02:03Z",
        flow=flow,
        how="done",
        agents={},
        sessions=[],
        backed=backed or {},
    )
    return pick.Does(
        cast("Ran", ran), resumable=resumable, foreign=foreign, uploads=uploads
    )


@pytest.mark.parametrize(
    ("resumable", "foreign", "rows", "said"),
    [
        (True, "", ["resume", "graph", "export", "exomyth", *_COPIES], ""),
        (
            False,
            "",
            ["graph", "export", "exomyth", *_COPIES],
            "ralph is not resumable, so this run cannot be resumed",
        ),
        (
            True,
            "the workspace it ran in, /w, is not on this machine",
            ["graph", "export", "exomyth", *_COPIES],
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


def test_does_offers_upload_where_there_is_a_target_and_says_how_backups_went() -> None:
    does = _does(
        resumable=False,
        uploads=True,
        backed={
            "lab": {"at": "2026-10-12T01:05:00Z", "ok": True, "error": ""},
            "home": {"at": "2026-10-12T01:06:00Z", "ok": False, "error": "denied"},
        },
    )

    assert [one[0] for one in does.rows()] == [
        "graph",
        "export",
        "exomyth",
        "upload",
        *_COPIES,
    ]
    assert does.about.splitlines()[-2:] == [
        "lab: backed up 2026-10-12 01:05",
        "home: failed 2026-10-12 01:06: denied",
    ]


@pytest.mark.parametrize("flow", ["chat", "./flows/chat", "git+https://x/flows#chat"])
def test_a_chat_is_not_offered_in_exomyth_which_draws_no_conversation(
    flow: str,
) -> None:
    assert pick.chatting(flow)
    assert [one[0] for one in _does(resumable=False, flow=flow).rows()] == [
        "graph",
        "export",
        *_COPIES,
    ]


def test_a_flow_merely_named_like_chat_is_not_a_chat() -> None:
    assert not pick.chatting("chatter")
    assert not pick.chatting("./chat/ralph")
