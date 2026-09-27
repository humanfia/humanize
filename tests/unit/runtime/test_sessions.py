"""Where a run's sessions are, read back off the epic: kept in it, left at home, or linked.

A run keeps the sessions its agents open in its own `sessions/<cli>/`, laid out as each CLI lays
out its home; a session a turn could not keep there stays where its CLI keeps it, and the line
that opened it says where; and an epic written before either holds a directory of links per
session, which still reads back. All three are directories and lines here -- written under
`tmp_path` the way a run writes them -- so nothing is run to read them.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from hmz.runtime.epic import JOURNAL, SESSIONS, Epic, logs, sessions, where

if TYPE_CHECKING:
    from pathlib import Path

#: What the backend called the one session each test opens.
IDENT = "0b1c-2d3e"


def _opened(epic: Path, **said: str) -> None:
    """Writes an epic by hand: began, and one session opened, saying what it is told to."""
    epic.mkdir(parents=True, exist_ok=True)
    lines = [
        {"event": "began", "flow": "f", "task": "t"},
        {
            "event": "opened",
            "agent": "builder",
            "backend": "claude",
            "provider": "local",
            "session": IDENT,
            "name": f"builder-claude@local-{IDENT}",
            **said,
        },
    ]
    (epic / JOURNAL).write_text("".join(json.dumps(one) + "\n" for one in lines))


def test_a_session_kept_in_the_run_is_read_back_out_of_it(tmp_path: Path) -> None:
    with Epic("f", "t", tmp_path) as epic:
        epic.session("builder", "claude", "", IDENT)
    at = epic.path / SESSIONS / "claude"
    log = at / "projects" / "-w" / f"{IDENT}.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("{}\n")

    (one,) = sessions(epic.path)
    assert one.where == f"{SESSIONS}/claude"
    assert where(epic.path, one) == at
    assert logs(epic.path, one) == {f"projects/-w/{IDENT}.jsonl": log}


def test_a_session_left_where_its_cli_keeps_it_is_read_from_there(
    tmp_path: Path,
) -> None:
    home = tmp_path / "claude-home"
    log = home / "projects" / "-w" / f"{IDENT}.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("{}\n")
    _opened(tmp_path / "epic", where=str(home))

    (one,) = sessions(tmp_path / "epic")
    assert where(tmp_path / "epic", one) == home
    assert logs(tmp_path / "epic", one) == {f"projects/-w/{IDENT}.jsonl": log}


def test_an_epic_written_before_sessions_were_kept_is_read_through_its_links(
    tmp_path: Path,
) -> None:
    """A directory of symlinks per session, each followed; one that leads nowhere is not."""
    log = tmp_path / "claude-home" / "projects" / "-w" / f"{IDENT}.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("{}\n")
    name = f"builder-claude@local-{IDENT}"
    links = tmp_path / "epic" / SESSIONS / name
    _opened(tmp_path / "epic", where=f"{SESSIONS}/{name}")
    links.mkdir(parents=True)
    (links / log.name).symlink_to(log)
    (links / "gone.jsonl").symlink_to(tmp_path / "nowhere.jsonl")

    (one,) = sessions(tmp_path / "epic")
    assert where(tmp_path / "epic", one) == links
    assert logs(tmp_path / "epic", one) == {log.name: log}


def test_a_session_of_a_backend_that_logs_nothing_has_nothing_to_read(
    tmp_path: Path,
) -> None:
    with Epic("f", "t", tmp_path) as epic:
        epic.session("builder", "opencode", "", "ses_1")

    (one,) = sessions(epic.path)
    assert logs(epic.path, one) == {}
