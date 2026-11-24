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
    kind: str | None = None,
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
    if kind is not None:
        ran.kind = kind
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
            "the flow ralph is not resumable, so this epic cannot be resumed",
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
        "lab: uploaded 2026-10-12 01:05",
        "home: failed, denied 2026-10-12 01:06",
    ]


@pytest.mark.parametrize(
    ("flow", "kind"),
    [
        ("", "chat"),
        # Written by an hmz that ran a chat as the flow `chat`, and so saying no kind.
        ("chat", None),
        ("./flows/chat", None),
        ("git+https://x/flows#chat", None),
    ],
)
def test_what_an_earlier_hmz_kept_of_a_chat_is_read_and_never_carried_on(
    flow: str, kind: str | None
) -> None:
    does = _does(resumable=True, flow=flow, kind=kind)

    assert [one[0] for one in does.rows()] == ["graph", "export", *_COPIES]
    assert does.asked == "2026-10-12 01:02 · chat"
    assert does.nothing() == (
        "this epic is of a chat an earlier hmz had, and cannot be carried on"
    )


@pytest.mark.parametrize(
    ("epic", "chat"),
    [
        ({"kind": "chat", "flow": ""}, True),
        ({"epic_kind": "chat", "kind": "host", "flow": ""}, True),
        ({"kind": "flow", "flow": "ralph"}, False),
        # A flow that happens to be called `chat` is a flow, once its kind says so.
        ({"kind": "flow", "flow": "chat"}, False),
        ({"flow": "chat"}, True),
        ({"ref": "chat:chat"}, True),
        ("chat", True),
        ("ralph", False),
    ],
)
def test_chatting_reads_the_kind_and_an_old_chat_by_its_flow(
    epic: dict[str, str] | str, chat: bool
) -> None:
    assert pick.chatting(epic) is chat


def test_an_epic_of_a_flow_called_chat_is_no_chat_where_its_kind_says_so() -> None:
    does = _does(resumable=True, flow="chat", kind="flow")

    assert [one[0] for one in does.rows()][:1] == ["resume"]
    assert "exomyth" in [one[0] for one in does.rows()]


def test_a_flow_merely_named_like_chat_is_not_a_chat() -> None:
    assert not pick.chatting("chatter")
    assert not pick.chatting("./chat/ralph")
