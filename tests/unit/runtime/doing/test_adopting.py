"""The sessions a harness had of its own: listed off made-up homes, and adopted as a chat.

Every home here is made up under the test's own directory, and what is known of each CLI
(`hmz.coganchor.backends`) is stood in for: no harness of whoever runs this is read.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from hmz import home
from hmz.runtime.doing import adopting
from hmz.runtime.epic import CHATTED, SESSIONS, read

if TYPE_CHECKING:
    from pathlib import Path

#: What each CLI keeps a session in, as its profile says it.
KEEPS = {
    "claude": ("projects", "file-history"),
    "codex": ("sessions", "archived_sessions"),
    "grok": ("sessions",),
    "pi": ("sessions",),
    "omp": ("sessions",),
    "qwen": ("projects",),
    "opencode": ("opencode.db*",),
}


class Backends:
    """What `hmz.coganchor.backends` says of each CLI, of homes under one directory."""

    def __init__(self, homes: Path) -> None:
        self.homes = homes
        self.installed = set(KEEPS)
        self.forks = set(KEEPS) - {"qwen"}
        self.unread: set[str] = set()

    def named(self, name: str) -> Any:
        if name not in KEEPS:
            return None

        def directory() -> Path:
            if name in self.unread:
                raise OSError("unreadable")
            return self.homes / name

        return SimpleNamespace(
            name=name,
            sessions=KEEPS[name],
            forks=name in self.forks,
            directory=directory,
        )

    def program(self, name: str) -> str | None:
        return f"/bin/{name}" if name in self.installed else None


@pytest.fixture
def clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Backends:
    stood = Backends(tmp_path / "homes")
    monkeypatch.setattr(adopting, "backends", stood)
    return stood


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    at = tmp_path / "project"
    at.mkdir()
    return at.resolve()


def _written(path: Path, rows: list[dict[str, Any]], at: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(one) + "\n" for one in rows))
    if at:
        os.utime(path, (at, at))
    return path


def _plain(at: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", str(at))


def _claude(
    clis: Backends, cwd: Path, ident: str, said: str, at: float = 0, model: str = "m1"
) -> Path:
    return _written(
        clis.homes / "claude" / "projects" / _plain(cwd) / f"{ident}.jsonl",
        [
            {
                "type": "user",
                "isMeta": True,
                "cwd": str(cwd),
                "message": {"content": "x"},
            },
            {
                "type": "user",
                "cwd": str(cwd),
                "timestamp": "2026-01-01T00:00:01Z",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": said}],
                },
            },
            {
                "type": "assistant",
                "cwd": str(cwd),
                "timestamp": "2026-01-01T00:00:02Z",
                "message": {"role": "assistant", "model": model, "content": []},
            },
        ],
        at,
    )


def _codex(
    clis: Backends, cwd: Path, ident: str, said: str, at: float = 0, **meta: str
) -> Path:
    return _written(
        clis.homes
        / "codex"
        / "sessions"
        / "2026"
        / "01"
        / "02"
        / f"rollout-2026-01-02T03-04-05-{ident}.jsonl",
        [
            {
                "timestamp": "2026-01-02T03:04:05Z",
                "type": "session_meta",
                "payload": {"id": ident, "cwd": str(cwd), **meta},
            },
            {"type": "turn_context", "payload": {"model": "g1"}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "<environment_context>"},
            },
            {"type": "event_msg", "payload": {"type": "user_message", "message": said}},
        ],
        at,
    )


def test_each_harness_lists_its_own_sessions_of_the_workspace_newest_first(
    clis: Backends, workspace: Path, tmp_path: Path
) -> None:
    _claude(clis, workspace, "c-1", "tidy the parser\nand the tests", 100)
    _codex(clis, workspace, "x-1", "sketch a changelog", 300)
    _written(
        clis.homes / "pi" / "sessions" / "--project--" / "2026_p-1.jsonl",
        [
            {
                "type": "session",
                "cwd": str(workspace),
                "timestamp": "2026-01-03T00:00:00Z",
            },
            {"type": "model_change", "modelId": "p1"},
            {"message": {"role": "user", "content": "ask pi"}},
        ],
        200,
    )
    _written(
        clis.homes / "qwen" / "projects" / _plain(workspace) / "chats" / "q-1.jsonl",
        [
            {
                "type": "user",
                "cwd": str(workspace),
                "message": {"parts": [{"text": "ask qwen"}]},
            }
        ],
        50,
    )
    quoted = urllib.parse.quote(str(workspace), safe="")
    _written(
        clis.homes / "grok" / "sessions" / quoted / "g-1" / "updates.jsonl",
        [
            {
                "params": {
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "_meta": {"modelId": "k1"},
                        "content": {"type": "text", "text": "ask grok"},
                    }
                }
            }
        ],
        25,
    )
    # Another directory's, which are none of this workspace's.
    other = tmp_path / "other"
    _claude(clis, other, "c-2", "elsewhere", 400)
    _codex(clis, other, "x-2", "elsewhere", 400)

    found = adopting.listed(workspace)

    assert [(one.harness, one.ident, one.title, one.model) for one in found] == [
        ("codex", "x-1", "sketch a changelog", "g1"),
        ("pi", "p-1", "ask pi", "p1"),
        ("claude", "c-1", "tidy the parser", "m1"),
        ("qwen", "q-1", "ask qwen", ""),
        ("grok", "g-1", "ask grok", "k1"),
    ]
    assert {one.cwd for one in found} == {str(workspace)}
    assert found[0].began == "2026-01-02T03:04:05Z"
    assert found[2].began == "2026-01-01T00:00:01Z"
    assert found[2].updated.startswith("1970-01-01T00:01:40")


def test_a_session_a_chat_or_an_epic_opened_is_left_out(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _claude(clis, workspace, "c-2", "two")
    _codex(clis, workspace, "c-1", "the same id, of another harness")

    found = adopting.listed(workspace, {("claude", "c-1")})

    assert sorted((one.harness, one.ident) for one in found) == [
        ("claude", "c-2"),
        ("codex", "c-1"),
    ]


def test_a_thread_another_started_or_was_cut_from_is_no_session_of_its_own(
    clis: Backends, workspace: Path
) -> None:
    _codex(clis, workspace, "x-1", "the thread")
    _codex(clis, workspace, "x-2", "its sub-agent", parent_thread_id="x-1")
    _codex(clis, workspace, "x-3", "its fork", forked_from_id="x-1")

    assert [one.ident for one in adopting.listed(workspace)] == ["x-1"]


def test_only_a_harness_installed_here_and_kept_outside_humanize_is_listed(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _codex(clis, workspace, "x-1", "two")

    clis.installed.discard("codex")
    assert [one.harness for one in adopting.listed(workspace)] == ["claude"]

    # One whose home is Humanize's own keeps what Humanize ran, which is no harness session.
    clis.homes = home() / "kept"
    _claude(clis, workspace, "c-9", "kept by humanize")
    assert adopting.listed(workspace) == []


def test_a_harness_that_cannot_be_read_does_not_fail_the_listing(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _codex(clis, workspace, "x-1", "two")
    clis.unread.add("claude")

    assert [one.harness for one in adopting.listed(workspace)] == ["codex"]


def test_only_the_head_and_the_tail_of_a_log_are_read(
    clis: Backends, workspace: Path
) -> None:
    padding = {"type": "progress", "cwd": str(workspace), "data": "x" * 1024}
    said = {"type": "user", "message": {"role": "user", "content": "said too late"}}
    last: dict[str, Any] = {"type": "assistant", "message": {"model": "m9"}}
    _written(
        clis.homes / "claude" / "projects" / _plain(workspace) / "c-1.jsonl",
        [*[padding] * 600, said, *[padding] * 600, last],
    )

    (one,) = adopting.listed(workspace)

    # What is said past the head is not what it is titled by; its tail says its model.
    assert (one.title, one.model) == ("", "m9")


def test_a_log_changed_is_read_again(clis: Backends, workspace: Path) -> None:
    log = _claude(clis, workspace, "c-1", "first", 100)
    assert adopting.listed(workspace)[0].title == "first"

    _claude(clis, workspace, "c-1", "second, and longer", 200)

    assert log.is_file()
    assert adopting.listed(workspace)[0].title == "second, and longer"


def test_the_files_of_a_session_are_those_its_cli_keeps_that_name_it(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    _claude(clis, workspace, "c-2", "two")
    under = clis.homes / "claude"
    project = under / "projects" / _plain(workspace)
    _written(project / "c-1" / "subagents" / "agent-a.jsonl", [{}])
    _written(under / "file-history" / "c-1" / "a@v1", [{}])
    _written(under / "settings" / "c-1.json", [{}])
    (one,) = [each for each in adopting.listed(workspace) if each.ident == "c-1"]

    assert sorted(adopting.files(one)) == [
        "file-history/c-1/a@v1",
        f"projects/{project.name}/c-1.jsonl",
        f"projects/{project.name}/c-1/subagents/agent-a.jsonl",
    ]


def test_adopting_copies_a_session_into_a_chat_that_rests_and_leaves_it_as_it_was(
    clis: Backends, workspace: Path
) -> None:
    log = _claude(clis, workspace, "c-1", "tidy the parser", 100, model="opus-9")
    before = (log.read_bytes(), log.stat().st_mtime_ns)
    (one,) = adopting.listed(workspace)

    at = adopting.adopt(one, workspace)

    assert (log.read_bytes(), log.stat().st_mtime_ns) == before
    assert at.parent.parent == home() / "chats"
    copy = at / SESSIONS / "claude" / "projects" / log.parent.name / "c-1.jsonl"
    assert copy.read_bytes() == before[0]
    ran = read(at)
    assert ran is not None
    assert (ran.chat, ran.adopted, ran.title, ran.task, ran.how, ran.forked) == (
        True,
        "claude:c-1",
        "tidy the parser",
        "tidy the parser",
        "stopped",
        "",
    )
    assert ran.workspace == str(workspace)
    assert [one.spec for one in ran.agents] == ["claude/opus-9:auto"]
    assert [(s.backend, s.ident, s.where) for s in ran.sessions] == [
        ("claude", "c-1", f"{SESSIONS}/claude")
    ]
    assert sorted(one.name for one in at.iterdir()) == [CHATTED, SESSIONS]
    # Opened by a chat now, it is no harness session any more.
    owned = {(s.backend, s.ident) for s in ran.sessions}
    assert adopting.listed(workspace, owned) == []


def test_adopting_takes_another_agent_of_the_same_harness(
    clis: Backends, workspace: Path
) -> None:
    _claude(clis, workspace, "c-1", "one")
    (one,) = adopting.listed(workspace)

    ran = read(adopting.adopt(one, workspace, "claude/sonnet-9:high"))

    assert ran is not None
    assert [each.spec for each in ran.agents] == ["claude/sonnet-9:high"]
    with pytest.raises(ValueError, match="c-1 is a session of claude, not of codex/g1"):
        adopting.adopt(one, workspace, "codex/g1")


def test_a_session_that_says_no_line_is_titled_by_its_id(
    clis: Backends, workspace: Path
) -> None:
    _written(
        clis.homes / "claude" / "projects" / _plain(workspace) / "c-1.jsonl",
        [{"type": "summary", "cwd": str(workspace), "message": {"model": "m1"}}],
    )
    (one,) = adopting.listed(workspace)
    assert one.title == ""

    ran = read(adopting.adopt(one, workspace))

    assert ran is not None
    assert (ran.title, ran.task) == ("c-1", "c-1")


def test_adopting_is_refused_where_a_copy_could_not_be_carried_on(
    clis: Backends, workspace: Path
) -> None:
    _written(
        clis.homes / "qwen" / "projects" / _plain(workspace) / "chats" / "q-1.jsonl",
        [
            {
                "type": "user",
                "cwd": str(workspace),
                "message": {"parts": [{"text": "q"}]},
            }
        ],
    )
    _written(
        clis.homes / "claude" / "projects" / _plain(workspace) / "c-1.jsonl",
        [{"type": "user", "cwd": str(workspace), "message": {"content": "no model"}}],
    )
    qwen, claude = sorted(adopting.listed(workspace), key=lambda one: one.harness)[::-1]

    with pytest.raises(ValueError, match="qwen cannot carry a session of its own on"):
        adopting.adopt(qwen, workspace)
    with pytest.raises(ValueError, match="c-1 does not say the model it ran on"):
        adopting.adopt(claude, workspace)
    gone = claude._replace(ident="c-0", model="m1")
    with pytest.raises(ValueError, match="c-0 cannot be continued: its files are gone"):
        adopting.adopt(gone, workspace)
    assert not (home() / "chats").exists()
