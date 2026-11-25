"""One run of one flow, written down as it runs and read back afterwards."""

from __future__ import annotations

import datetime
import fcntl
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import backends, machines
from hmz.coganchor.machines import store
from hmz.runtime import epic
from hmz.runtime.epic import (
    CHATTED,
    JOURNAL,
    LOCAL,
    RESUME,
    SESSIONS,
    Called,
    Drove,
    Epic,
    Session,
)
from hmz.runtime.tracing import profile

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.coganchor.agents import AgentBase


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    at = tmp_path / "project"
    at.mkdir()
    return at


def _respelled(spec: str) -> str:
    """An environment kept the old way, as `-e` spells it now."""
    return spec.replace("@local", "")


def _lines(at: Path) -> list[dict[str, Any]]:
    return [json.loads(one) for one in at.read_text().splitlines()]


def _journal(at: Path, *records: dict[str, Any] | str) -> None:
    at.write_text(
        "".join(
            (one if isinstance(one, str) else json.dumps(one)) + "\n" for one in records
        )
    )


# ------------------------------------------------------------------ naming


@pytest.mark.parametrize(
    ("parts", "name"),
    [
        (("NeiKos496", "claude", "work", "abc-123"), "NeiKos496-claude@work-abc-123"),
        (("NeiKos496", "claude", "", "abc"), f"NeiKos496-claude@{LOCAL}-abc"),
        (("a b/c", "co dex", "me!", "x/y"), "a-b-c-co-dex@me-x-y"),
        (("", "", "", "id"), "agent-cli@local-id"),
    ],
)
def test_a_session_is_named_for_whose_it_was(
    parts: tuple[str, str, str, str], name: str
) -> None:
    assert epic.called(*parts) == name


def test_a_session_with_no_id_is_named_all_the_same() -> None:
    said = epic.called("builder", "claude", "", "")

    assert said.startswith("builder-claude@local-")
    assert len(said) > len("builder-claude@local-")


@pytest.mark.parametrize(
    ("drove", "spec"),
    [
        (Drove("b", "claude", "opus", "high"), "claude/opus:high"),
        (Drove("b", "claude", "opus", ""), "claude/opus:auto"),
        (Drove("b", "codex", "o3", "low", "team"), "codex@team/o3:low"),
    ],
)
def test_an_agent_given_is_spelled_as_dash_a_spells_it(drove: Drove, spec: str) -> None:
    assert drove.spec == spec


def test_runs_are_kept_under_the_workspace_they_ran_in(workspace: Path) -> None:
    under = epic.under(workspace)

    assert under.parent == Path(os.environ["XDG_DATA_HOME"]) / "humanize" / "epics"
    assert "/" not in under.name
    assert under == epic.under(str(workspace))
    assert epic.under(workspace / "other") != under


def test_a_workspace_nobody_named_is_this_directory(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace)

    assert epic.under() == epic.under(workspace)


# ---------------------------------------------------------------- writing one


def test_an_epic_opens_saying_what_it_is_a_run_of(workspace: Path) -> None:
    with Epic(
        "ralph",
        "fix it",
        workspace,
        ref="official/ralph",
        agents=[Drove("builder", "claude", "opus", "high", "work", "NeiKos496")],
        envs=["box=docker/srv"],
        params={"rounds": 3},
        budget={"cost": 5.0},
        resumable=True,
    ) as one:
        assert one.path.parent == epic.under(workspace)
        assert one.journal == one.path / JOURNAL
        assert one.record == JOURNAL
        assert one.workspace == workspace.resolve()
        assert one.resume == one.path / RESUME
        assert one.keeps == one.path / SESSIONS

    began, ended = _lines(one.journal)
    assert began["event"] == "began"
    assert began["kind"] == "flow"
    assert began["flow"] == "ralph"
    assert began["task"] == "fix it"
    assert began["workspace"] == str(workspace.resolve())
    assert began["ref"] == "official/ralph"
    assert began["resumable"] is True
    assert began["agents"] == [
        {
            "agent": "builder",
            "backend": "claude",
            "model": "opus",
            "effort": "high",
            "provider": "work",
            "name": "NeiKos496",
        }
    ]
    assert began["envs"] == ["box=docker/srv"]
    assert "used" not in began
    assert began["params"] == {"rounds": 3}
    assert began["budget"] == {"cost": 5.0}
    assert began["spelling"] == store.SPELLING
    assert "profile_flow" not in began
    assert "profile_environment" not in began
    assert began["at"].endswith("Z")
    assert ended["event"] == "ended"
    assert ended["how"] == "done"


@pytest.mark.parametrize(
    ("raised", "how"),
    [
        (RuntimeError, "failed"),
        (KeyboardInterrupt, "stopped"),
        (__import__("asyncio").CancelledError, "stopped"),
    ],
)
def test_an_epic_ends_saying_how_the_run_ended(
    raised: type[BaseException], how: str, workspace: Path
) -> None:
    one = Epic("ralph", "t", workspace)
    with pytest.raises(raised), one:
        raise raised

    assert _lines(one.journal)[-1]["how"] == how


def test_a_run_said_to_be_stopped_ends_stopped_whatever_raised(workspace: Path) -> None:
    one = Epic("ralph", "t", workspace)

    def stops() -> None:
        with one:
            one.stopped()
            raise RuntimeError

    with pytest.raises(RuntimeError):
        stops()

    assert _lines(one.journal)[-1]["how"] == "stopped"


def test_where_each_role_was_put_is_written_only_where_it_moved(
    workspace: Path,
) -> None:
    with Epic("f", "t", workspace, envs=["a=x"], used=["a=y"]) as moved:
        pass
    with Epic("f", "t", workspace, envs=["a=x"], used=["a=x"]) as stayed:
        pass

    assert _lines(moved.journal)[0]["used"] == ["a=y"]
    assert "used" not in _lines(stayed.journal)[0]


def test_a_run_picked_up_is_handed_a_copy_of_the_journal(workspace: Path) -> None:
    with Epic("f", "t", workspace, resumable=True) as first:
        _journal(first.resume, {"t": "call", "id": 1, "parent": 0})

    with Epic("f", "t", workspace, resumable=True, picked_up=first.path) as second:
        assert second.resume.read_text() == first.resume.read_text()

    assert _lines(second.journal)[0]["picked_up"] == first.path.name


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_a_journal_that_cannot_be_copied_leaves_no_run_picked_up(
    workspace: Path,
) -> None:
    with Epic("f", "t", workspace, resumable=True) as first:
        _journal(first.resume, {"t": "call", "id": 1, "parent": 0})
    first.resume.chmod(0)

    # Refused, saying why, and leaving no epic behind that says it picked the first one up
    # while going on from nothing.
    with pytest.raises(epic.Uncarried, match="could not be copied") as refused:
        Epic("f", "t", workspace, resumable=True, picked_up=first.path)
    assert isinstance(refused.value.__cause__, PermissionError)
    assert [one for one in epic.under(workspace).iterdir() if one.is_dir()] == [
        first.path
    ]

    # So the first is still there to be picked up, and is, from all it kept.
    first.resume.chmod(0o600)
    assert epic.picks_up(first.path)
    with Epic("f", "t", workspace, resumable=True, picked_up=first.path) as second:
        assert second.resume.read_text() == first.resume.read_text()


ASSISTANT = Drove("assistant", "claude", "haiku", "low", "", "NeiKos496")


def test_a_chat_is_written_down_with_no_flow_and_read_back_as_one(
    workspace: Path,
) -> None:
    with Epic(
        "", "hi", workspace, kind="chat", agents=[ASSISTANT], prefer="flow"
    ) as one:
        pass

    # Under `chats/` of Humanize's home, in a record of its own, and no epic of the workspace.
    under = epic.under(workspace)
    assert one.path.parent == under.parent.parent / "chats" / under.name
    assert one.journal == one.path / CHATTED
    assert epic.journal(one.path) == one.journal
    assert (epic.chats(workspace), epic.chats()) == ([one.path], [one.path])
    assert (epic.epics(workspace), epic.every()) == ([], [])
    began, _ = _lines(one.journal)
    assert "kind" not in began
    assert (began["task"], began["workspace"]) == ("hi", str(workspace.resolve()))
    assert began["agents"] == [ASSISTANT._asdict()]
    assert began["prefer"] == "flow"
    for absent in (
        "flow",
        "ref",
        "picked_up",
        "envs",
        "used",
        "params",
        "budget",
        "profile_flow",
        "profile_environment",
    ):
        assert absent not in began
    ran = epic.read(one.path)
    assert ran is not None
    assert (ran.kind, ran.chat, ran.flow, ran.prefer) == ("chat", True, "", "flow")
    assert ran.agents == (ASSISTANT,)
    assert (ran.title, ran.archived, ran.workdir, ran.forked) == ("hi", False, "", "")
    assert ran.updated == _lines(one.journal)[-1]["at"]


def test_a_chat_goes_by_the_last_line_to_set_its_agent_and_its_preference(
    workspace: Path,
) -> None:
    changed = ASSISTANT._replace(model="opus")
    with Epic("", "hi", workspace, kind="chat", agents=[ASSISTANT]) as one:
        one.write("set", prefer="flow")
        one.write("set", agents=[changed._asdict()])
        one.write("set", prefer="native")

    ran = epic.read(one.path)
    assert ran is not None
    assert (ran.agents, ran.prefer) == ((changed,), "native")


def test_an_epic_that_says_no_kind_is_a_flows_but_one_of_the_flow_chat(
    workspace: Path,
) -> None:
    for flow, kind in (("chat", "chat"), ("ralph", "flow")):
        at = epic.under(workspace) / f"20260101T000000.000Z-{flow}"
        at.mkdir(parents=True)
        _journal(
            at / JOURNAL,
            {"event": "began", "flow": flow, "task": "t", "resumable": True},
        )
        ran = epic.read(at)
        assert ran is not None
        assert ran.kind == kind
    # Nor is the chat a flow's run to resume, any more than one written with its kind is.
    assert epic.resumed("chat", workspace) is None


def test_a_flow_named_chat_is_an_ordinary_flow(workspace: Path) -> None:
    with Epic("chat", "hi", workspace) as one:
        pass
    ran = epic.read(one.path)
    assert ran is not None
    assert (ran.kind, ran.chat, ran.flow) == ("flow", False, "chat")


def test_a_chat_reopened_goes_on_in_the_record_it_picks_up(workspace: Path) -> None:
    with Epic("", "hi", workspace, kind="chat", agents=[ASSISTANT]) as first:
        first.write("usage", cost=1.0, output_tokens=7, seconds=2.0)
        first.stopped()
    done = epic.read(first.path)
    assert done is not None
    assert (done.how, done.reopened) == ("stopped", "")

    with Epic(
        "", "again", workspace, kind="chat", picked_up=first.path, reopened=True
    ) as second:
        assert second.path == first.path
        going = epic.read(first.path)
        assert going is not None
        # Going again: its last end is the one before it was opened again.
        assert (going.task, going.how, going.ended) == ("hi", "", "")
        assert going.reopened
        second.write("usage", cost=0.5, output_tokens=3, seconds=1.0)
        second.stopped()

    again = epic.read(first.path)
    assert again is not None
    assert again.how == "stopped"
    assert again.spent == {"cost": 1.5, "output_tokens": 10, "seconds": 3.0}
    events = [one["event"] for one in _lines(first.journal)]
    assert (events.count("began"), events.count("reopened")) == (1, 1)
    assert (epic.chats(), epic.every()) == ([first.path], [])


def test_a_chat_is_titled_by_its_first_line_until_it_is_set_and_says_where_it_works(
    workspace: Path,
) -> None:
    with Epic(
        "",
        "\n fix the parser \nand then the tests",
        workspace,
        kind="chat",
        agents=[ASSISTANT],
        workdir="/somewhere/else",
    ) as one:
        one.stopped()

    began = _lines(one.journal)[0]
    assert began["workdir"] == "/somewhere/else"
    ran = epic.read(one.path)
    assert ran is not None
    assert (ran.title, ran.archived) == ("fix the parser", False)
    assert ran.workdir == "/somewhere/else"

    epic.note(one.path, "set", title="Parser")
    epic.note(one.path, "set", archived=True)
    ran = epic.read(one.path)
    assert ran is not None
    assert (ran.title, ran.archived, ran.how) == ("Parser", True, "stopped")
    assert ran.updated == _lines(one.journal)[-1]["at"]

    # Carried on, it is the chat it was named, and archived until it is said not to be.
    with Epic(
        "", "more", workspace, kind="chat", picked_up=one.path, reopened=True
    ) as again:
        again.stopped()
    epic.note(one.path, "set", archived=False)
    ran = epic.read(one.path)
    assert ran is not None
    assert (ran.title, ran.archived) == ("Parser", False)
    assert ran.task == "\n fix the parser \nand then the tests"


def _old_chat(workspace: Path, **began: Any) -> Path:
    """A chat as an earlier Humanize wrote it: an epic, of a workspace's epics."""
    at = epic.under(workspace) / "20260101T000000.000Z-0ldc4a"
    (at / SESSIONS / "claude").mkdir(parents=True)
    _journal(
        at / JOURNAL,
        {
            "event": "began",
            "at": "2026-01-01T00:00:00.000Z",
            "task": "hi",
            "workspace": str(workspace.resolve()),
            "agents": [ASSISTANT._asdict()],
            **began,
        },
        {
            "event": "opened",
            "at": "2026-01-01T00:00:01.000Z",
            "agent": "NeiKos496",
            "backend": "claude",
            "session": "old",
            "where": "sessions/claude",
        },
        {"event": "ended", "at": "2026-01-01T00:00:02.000Z", "how": "stopped"},
    )
    return at


_OLD = [{"kind": "chat"}, {"flow": "chat", "resumable": True}]


def _moved(workspace: Path, name: str = "20260101T000000.000Z-0ldc4a") -> Path:
    """Where a chat an earlier Humanize wrote as an epic of a workspace is moved to."""
    return (
        epic.under(workspace).parents[1] / "chats" / epic.under(workspace).name / name
    )


@pytest.mark.parametrize("began", _OLD)
def test_a_chat_an_earlier_humanize_wrote_is_an_epic_until_it_is_moved(
    workspace: Path, began: dict[str, Any]
) -> None:
    at = _old_chat(workspace, **began)

    ran = epic.read(at)
    assert ran is not None
    # A chat's record, which is of no flow whatever it was written as.
    assert (ran.kind, ran.chat, ran.flow) == ("chat", True, "")
    assert epic.chatted(at)
    assert epic.journal(at) == at / JOURNAL
    assert (epic.epics(workspace), epic.every()) == ([at], [at])
    assert (epic.chats(workspace), epic.chats()) == ([], [])
    with pytest.raises(ValueError, match="is not a chat"):
        epic.forked(at)


@pytest.mark.parametrize("began", _OLD)
def test_a_chat_an_earlier_humanize_wrote_is_moved_among_the_chats_as_it_stands(
    workspace: Path, began: dict[str, Any]
) -> None:
    at = _old_chat(workspace, **began)
    (at / SESSIONS / "claude" / "old.jsonl").write_text("said\n")
    (at / "host.log").write_text("logged\n")
    written = (at / JOURNAL).read_bytes()
    with Epic("ralph", "a run", workspace) as flow:
        pass
    into = _moved(workspace)

    assert epic.migrated() == ([at.name], {})

    # The directory it was, by the name it had, and its record the bytes it was.
    assert not at.exists()
    assert (into / CHATTED).read_bytes() == written
    assert not (into / JOURNAL).exists()
    assert (into / SESSIONS / "claude" / "old.jsonl").read_text() == "said\n"
    assert (into / "host.log").read_text() == "logged\n"
    assert (epic.chats(workspace), epic.chats()) == ([into], [into])
    # And the epic of a flow is where it was.
    assert (epic.epics(workspace), epic.every()) == ([flow.path], [flow.path])
    ran = epic.read(into)
    assert ran is not None
    assert (ran.kind, ran.chat, ran.flow, ran.task, ran.how) == (
        "chat",
        True,
        "",
        "hi",
        "stopped",
    )
    assert [one.ident for one in ran.sessions] == ["old"]
    assert epic.where(into, ran.sessions[0]) == into / SESSIONS / "claude"

    # A second time there is nothing to move, and nothing is touched.
    assert epic.migrated() == ([], {})
    assert (into / CHATTED).read_bytes() == written

    # Carried on, it goes on in the record it has, as any chat does.
    with Epic("", "more", workspace, kind="chat", picked_up=into, reopened=True) as on:
        assert on.journal == into / CHATTED
    assert [one["event"] for one in _lines(into / CHATTED)][-2:] == [
        "reopened",
        "ended",
    ]
    assert epic.forked(into).parent == into.parent


def test_a_move_cut_short_is_finished_by_the_next(workspace: Path) -> None:
    at = _old_chat(workspace, kind="chat")
    written = (at / JOURNAL).read_bytes()
    # As a daemon killed between the two steps leaves it: its record renamed, and no more.
    (at / JOURNAL).rename(at / CHATTED)
    assert (epic.every(), epic.chats()) == ([], [])
    assert epic.chatted(at)

    assert epic.migrated() == ([at.name], {})

    into = _moved(workspace)
    assert (into / CHATTED).read_bytes() == written
    assert (epic.every(), epic.chats()) == ([], [into])
    assert epic.migrated() == ([], {})


def test_a_chat_kept_as_an_epic_that_is_going_is_left_for_the_next_time(
    workspace: Path,
) -> None:
    at = _old_chat(workspace, kind="chat")
    written = (at / JOURNAL).read_bytes()
    held = os.open(at / ".held", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert epic.going(at)
        assert epic.migrated() == ([], {at.name: "it is going"})
        # As it was, to the byte: neither its record nor its directory was touched.
        assert (at / JOURNAL).read_bytes() == written
        assert not (at / CHATTED).exists()
        assert epic.chats() == []
    finally:
        os.close(held)

    assert epic.migrated() == ([at.name], {})
    assert (_moved(workspace) / CHATTED).read_bytes() == written


def test_a_chat_kept_as_an_epic_is_left_where_a_chat_has_its_name(
    workspace: Path,
) -> None:
    at = _old_chat(workspace, kind="chat")
    written = (at / JOURNAL).read_bytes()
    into = _moved(workspace)
    into.mkdir(parents=True)
    (into / CHATTED).write_text('{"event": "began", "task": "another"}\n')

    moved, left = epic.migrated()

    assert (moved, list(left)) == ([], [at.name])
    assert str(into) in left[at.name]
    assert (at / JOURNAL).read_bytes() == written
    assert not (at / CHATTED).exists()
    assert (into / CHATTED).read_text() == '{"event": "began", "task": "another"}\n'


def test_a_chat_kept_as_an_epic_that_holds_a_chat_record_too_is_left(
    workspace: Path,
) -> None:
    at = _old_chat(workspace, kind="chat")
    (at / CHATTED).write_text("another\n")

    moved, left = epic.migrated()

    assert (moved, list(left)) == ([], [at.name])
    assert (at / CHATTED).read_text() == "another\n"
    assert (at / JOURNAL).is_file()


def test_a_move_that_fails_leaves_the_epic_as_it_was(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = _old_chat(workspace, kind="chat")
    written = (at / JOURNAL).read_bytes()
    rename = Path.rename
    fails = [True]

    def renamed(self: Path, target: Path) -> Path:
        if self == at and fails[0]:
            raise OSError(18, "Cross-device link")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", renamed)

    assert epic.migrated() == ([], {at.name: "Cross-device link"})

    assert (at / JOURNAL).read_bytes() == written
    assert not (at / CHATTED).exists()
    assert (epic.every(), epic.chats()) == ([at], [])
    fails[0] = False
    assert epic.migrated() == ([at.name], {})


def test_only_a_chat_kept_as_an_epic_is_moved(workspace: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    # Nothing to move where nothing was ever run.
    assert epic.migrated() == ([], {})
    with Epic("ralph", "a run", workspace) as flow:
        pass
    # A flow named `chat` is an ordinary flow, and its epic stays one.
    with Epic("chat", "a run", workspace) as named:
        pass
    with Epic("", "hi", workspace, kind="chat") as chat:
        pass
    first = _old_chat(workspace, kind="chat")
    second = epic.under(other) / "20250101T000000.000Z-0lder1"
    second.mkdir(parents=True)
    _journal(
        second / JOURNAL,
        "cut off mid-li",
        {"event": "began", "flow": "chat", "task": "t", "workspace": str(other)},
    )
    # What an import stages there, and what somebody put there, are no epic to move.
    staged = (
        epic.under(workspace) / ".20260101T000000.000Z-st4ged.x" / "20260101-st4ged"
    )
    staged.mkdir(parents=True)
    _journal(staged / JOURNAL, {"event": "began", "kind": "chat", "task": "t"})
    (epic.under(workspace) / "notes").mkdir()
    (epic.under(workspace) / "a-file").write_text("{}")

    moved, left = epic.migrated()

    assert (sorted(moved), left) == ([second.name, first.name], {})
    assert epic.every() == [flow.path, named.path]
    assert epic.chats() == [
        _moved(other, second.name),
        _moved(workspace),
        chat.path,
    ]
    assert (staged / JOURNAL).is_file()
    assert (epic.under(workspace) / "notes").is_dir()


def test_chats_are_listed_oldest_first_of_one_workspace_or_of_every_one(
    workspace: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    assert epic.chats() == []
    assert epic.chats(workspace) == []
    with Epic("", "one", workspace, kind="chat") as first:
        pass
    with Epic("", "two", other, kind="chat") as second:
        pass
    with Epic("", "three", workspace, kind="chat") as third:
        pass
    with Epic("f", "a run", workspace):
        pass
    # A directory that holds no record is no chat.
    (first.path.parent / "20200101T000000.000Z-000000").mkdir()

    assert epic.chats(workspace) == [first.path, third.path]
    assert epic.chats(str(other)) == [second.path]
    assert epic.chats() == [first.path, second.path, third.path]


def _conversed(one: Epic, ident: str = "s1") -> Path:
    """Writes a conversation kept in a chat, as its harness's session files."""
    kept = one.path / SESSIONS / "claude"
    kept.mkdir(parents=True, exist_ok=True)
    (kept / f"{ident}.jsonl").write_text(f"what was said in {ident}\n")
    one.write(
        "opened",
        agent="NeiKos496",
        backend="claude",
        session=ident,
        where="sessions/claude",
    )
    return kept


def test_a_chat_forked_is_a_new_chat_going_on_from_a_copy_of_its_conversation(
    workspace: Path,
) -> None:
    with Epic(
        "",
        "hi\nthere",
        workspace,
        kind="chat",
        agents=[ASSISTANT],
        prefer="flow",
        permission="read-only",
        workdir="/a/worktree",
        backup=["mine"],
    ) as one:
        kept = _conversed(one)
        one.write("usage", cost=1.0, output_tokens=7, seconds=2.0)
        one.stopped()
    epic.note(one.path, "set", title="Greeting")
    before = one.journal.read_text()

    at = epic.forked(one.path)

    # Beside it, a chat of the same workspace; the one forked is as it was.
    assert at.parent == one.path.parent
    assert at != one.path
    assert epic.chats(workspace) == [one.path, at]
    assert one.journal.read_text() == before
    copy = at / SESSIONS / "claude" / "s1.jsonl"
    assert copy.read_text() == "what was said in s1\n"
    copy.write_text("and what the fork said\n")
    assert (kept / "s1.jsonl").read_text() == "what was said in s1\n"

    ran, was = epic.read(at), epic.read(one.path)
    assert ran is not None
    assert was is not None
    assert (ran.forked, was.forked) == (one.path.name, "")
    assert (ran.kind, ran.task, ran.title, ran.how) == (
        "chat",
        "hi\nthere",
        "Greeting",
        "stopped",
    )
    assert (ran.workspace, ran.agents) == (was.workspace, was.agents)
    assert (ran.prefer, ran.permission, ran.workdir, ran.backup) == (
        "flow",
        "read-only",
        "/a/worktree",
        ("mine",),
    )
    # It goes on from the copy: its sessions are its own, and it has spent nothing.
    assert [session.ident for session in ran.sessions] == ["s1"]
    assert epic.where(at, ran.sessions[-1]) == at / SESSIONS / "claude"
    assert not ran.spent
    assert not epic.going(at)


def test_a_chat_with_no_conversation_kept_in_it_is_not_forked(
    workspace: Path, tmp_path: Path
) -> None:
    with Epic("", "hi", workspace, kind="chat", agents=[ASSISTANT]) as none:
        none.stopped()
    with Epic("", "hi", workspace, kind="chat", agents=[ASSISTANT]) as away:
        # Kept where its harness keeps it, which is none of the chat's.
        away.write(
            "opened",
            agent="NeiKos496",
            backend="claude",
            session="s1",
            where=str(tmp_path / "elsewhere"),
        )
        away.stopped()
    with Epic("f", "t", workspace) as flow:
        pass

    for chat in (none.path, away.path):
        with pytest.raises(
            ValueError, match="its conversation is not kept in the chat"
        ):
            epic.forked(chat)
    with pytest.raises(ValueError, match="is not a chat"):
        epic.forked(flow.path)
    with pytest.raises(ValueError, match="is not a chat"):
        epic.forked(workspace / "nothing")
    assert epic.chats(workspace) == [none.path, away.path]


def test_a_run_picked_up_from_nothing_to_copy_still_opens(workspace: Path) -> None:
    with Epic("f", "t", workspace, picked_up=workspace / "gone") as one:
        assert not one.resume.exists()


@dataclass
class Profiler:
    at: Path
    started: bool = False
    stopped: bool = False
    refuses: bool = False
    made: list[Profiler] = field(default_factory=list["Profiler"])

    def start(self) -> None:
        if self.refuses:
            raise OSError("no /proc")
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_a_profiled_run_is_sampled_while_it_runs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[Profiler] = []

    def making(at: Path) -> Profiler:
        made.append(Profiler(at))
        return made[-1]

    monkeypatch.setattr(profile, "Profiler", making)

    with Epic("f", "t", workspace, profile_environment=True) as one:
        assert made[0].started
        assert not made[0].stopped

    assert made[0].at == one.path / profile.PROFILE
    assert made[0].stopped
    assert _lines(one.journal)[0]["profile_environment"] is True
    assert "profile_flow" not in _lines(one.journal)[0]


def test_a_run_whose_flow_is_profiled_samples_it_while_it_runs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[Profiler] = []

    def making(at: Path) -> Profiler:
        made.append(Profiler(at))
        return made[-1]

    monkeypatch.setattr(profile, "Sampler", making)
    monkeypatch.setattr(profile, "Profiler", making)

    with Epic("f", "t", workspace, profile_flow=True) as one:
        assert made[0].started
        assert not made[0].stopped

    assert [one.at for one in made] == [one.path / profile.FLOW_PROFILE]
    assert made[0].stopped
    assert _lines(one.journal)[0]["profile_flow"] is True
    assert "profile_environment" not in _lines(one.journal)[0]


def test_a_machine_that_cannot_be_profiled_still_runs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refusing(at: Path) -> Profiler:
        return Profiler(at, refuses=True)

    monkeypatch.setattr(profile, "Profiler", refusing)
    monkeypatch.setattr(profile, "Sampler", refusing)

    with Epic("f", "t", workspace, profile_flow=True, profile_environment=True) as one:
        pass

    assert _lines(one.journal)[-1]["how"] == "done"


def test_a_session_is_written_down_where_it_is_kept(workspace: Path) -> None:
    with Epic("f", "t", workspace) as one:
        one.session("builder", "claude", "", "s1")
        one.session("builder", "claude", "work", "s2", "s1", harness="self")
        one.session("rev", "codex", "", "s3", where=workspace / "elsewhere")

    opened = [line for line in _lines(one.journal) if line["event"] == "opened"]
    assert opened[0] == {
        "event": "opened",
        "at": opened[0]["at"],
        "agent": "builder",
        "backend": "claude",
        "provider": LOCAL,
        "session": "s1",
        "name": "builder-claude@local-s1",
        "where": "sessions/claude",
    }
    assert opened[1]["parent"] == "s1"
    assert opened[1]["harness"] == "self"
    assert opened[1]["provider"] == "work"
    assert opened[2]["where"] == str(workspace / "elsewhere")


class Agent:
    """A coganchor agent, as far as an epic reads one."""

    def __init__(
        self,
        provider: object = None,
        configured: str = "",
        machine: object = None,
        kept: Path | None = None,
    ) -> None:
        self.id = "builder"
        self.backend = "claude"
        self._provider = provider
        self.config = type("Config", (), {"provider": configured, "machine": machine})()
        self._kept = kept

    @property
    def provider(self) -> object:
        if isinstance(self._provider, Exception):
            raise self._provider
        return self._provider

    def kept(self) -> Path | None:
        return self._kept


def _opened(one: Epic, agent: Agent, session: str, parent: str = "") -> dict[str, Any]:
    one.opened(cast("AgentBase", agent), session, parent)
    return _lines(one.journal)[-1]


def test_an_agent_opening_a_session_is_written_under_the_account_it_ran_as(
    workspace: Path,
) -> None:
    with Epic("f", "t", workspace) as one:
        here = _opened(one, Agent(), "s1")
        named = _opened(one, Agent(provider=type("P", (), {"name": "team"})()), "s2")
        missing = _opened(
            one, Agent(provider=ValueError("gone"), configured="old"), "s3"
        )
        forked = _opened(one, Agent(), "s4", parent="s1")

    assert here["provider"] == LOCAL
    assert "harness" not in here
    assert named["provider"] == "team"
    assert missing["provider"] == "old"
    assert forked["parent"] == "s1"


@dataclass
class Anchor:
    native: bool = False
    harness: str = "local"


@dataclass
class Anchored:
    anchor: Anchor


@pytest.fixture
def harbored() -> Iterator[str]:
    """A machine said to be a runtime, said again to be itself once the test is done."""
    target = "ssh://u12-box"
    epic.harbor(target, "docker:u12-gpu")
    yield target
    epic.harbor(target, target)


def test_where_a_harness_ran_is_said_as_a_harness_setting_says_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, harbored: str
) -> None:
    monkeypatch.setattr(machines, "AnchoredConfig", Anchored)

    assert epic.harnessed(None) == store.HERE
    assert epic.harnessed(cast("Any", object())) == store.HERE
    assert epic.harnessed(cast("Any", Anchored(Anchor(native=True)))) == store.ENV
    assert epic.harnessed(cast("Any", Anchored(Anchor()))) == store.HERE
    assert (
        epic.harnessed(cast("Any", Anchored(Anchor(harness="ssh://u12-box"))))
        == "docker:u12-gpu"
    )
    assert (
        epic.harnessed(cast("Any", Anchored(Anchor(harness="ssh://u12-unknown"))))
        == "ssh://u12-unknown"
    )

    with Epic("f", "t", workspace) as one:
        said = _opened(one, Agent(machine=Anchored(Anchor(native=True))), "s1")
    assert said["harness"] == store.ENV


# ----------------------------------------------------------- calling a flow


def test_a_called_flow_is_written_in_a_record_of_its_own(workspace: Path) -> None:
    with Epic("outer", "t", workspace) as one:
        inner = one.called("@verse/inner flow", "do a part", resumable=True)
        assert inner.path == one.path
        assert inner.record.startswith("epic.@verse-inner-flow_")
        assert inner.record.endswith(".jsonl")
        inner.session("helper", "codex", "", "s9")
        deeper = inner.called("deep")
        deeper.ended()
        inner.ended(RuntimeError)

    called, *_ = (line for line in _lines(one.journal) if line["event"] == "called")
    assert called["flow"] == "@verse/inner flow"
    assert called["task"] == "do a part"
    assert called["epic"] == inner.record
    returned = [line for line in _lines(one.journal) if line["event"] == "returned"]
    assert returned[0]["epic"] == inner.record
    began = _lines(inner.journal)[0]
    assert began["under"] == JOURNAL
    assert began["resumable"] is True
    assert _lines(inner.journal)[-1]["how"] == "failed"
    assert _lines(deeper.journal)[0]["under"] == inner.record


def test_a_called_flow_stopped_says_so_whatever_raised(workspace: Path) -> None:
    with Epic("outer", "t", workspace) as one:
        inner = one.called("inner")
        inner.ended(RuntimeError, "stopped")

    assert _lines(inner.journal)[-1]["how"] == "stopped"


# ----------------------------------------------------------- reading back


def test_a_run_reads_back_as_what_it_was(workspace: Path) -> None:
    with Epic(
        "ralph",
        "fix it",
        workspace,
        ref="official/ralph",
        agents=[Drove("builder", "claude", "opus", "high", name="NeiKos496")],
        envs=["box=docker/srv"],
        used=["box=ssh@gpu/srv"],
        params={"rounds": 3},
        budget={"cost": 1.0},
        resumable=True,
    ) as one:
        one.session("NeiKos496", "claude", "", "s1")
        inner = one.called("inner", "part")
        inner.session("helper", "codex", "team", "s2")
        inner.ended()
        one.stopped()
        one.write("usage", cost=0.5, output_tokens=1200, seconds=61.5)

    ran = epic.read(one.path)
    assert ran is not None
    assert ran.name == one.path.name
    assert (ran.flow, ran.task, ran.ref) == ("ralph", "fix it", "official/ralph")
    assert ran.workspace == str(workspace.resolve())
    assert ran.began
    assert ran.ended
    assert ran.how == "stopped"
    # The role, and what the agent filling it is called.
    assert ran.agents == (Drove("builder", "claude", "opus", "high", "", "NeiKos496"),)
    assert ran.envs == ("box=docker/srv",)
    assert ran.used == ("box=ssh@gpu/srv",)
    assert ran.params == {"rounds": 3}
    assert ran.budget == {"cost": 1.0}
    assert ran.resumable is True
    assert ran.picked_up == ""
    assert (ran.profile_flow, ran.profile_environment) == (False, False)
    assert ran.spent == {"cost": 0.5, "output_tokens": 1200, "seconds": 61.5}
    assert [(one.agent, one.ident) for one in ran.sessions] == [
        ("NeiKos496", "s1"),
        ("helper", "s2"),
    ]
    assert ran.sessions[1].flow == "inner"
    assert ran.sessions[1].record == inner.record
    assert ran.sessions[1].provider == "team"
    assert [(one.flow, one.task, one.record) for one in ran.called] == [
        ("inner", "part", inner.record)
    ]
    assert ran.called[0].ended


def test_a_run_still_going_has_not_ended(workspace: Path) -> None:
    with Epic("f", "t", workspace) as one:
        ran = epic.read(one.path)

    assert ran is not None
    assert (ran.ended, ran.how) == ("", "")
    assert ran.used == ran.envs == ()
    assert ran.budget is None
    assert ran.spent is None


def test_where_a_run_is_backed_up_and_how_it_went_read_back(workspace: Path) -> None:
    with Epic("ralph", "fix it", workspace, backup=["lab", "home"]) as one:
        pass
    epic.note(one.path, epic.BACKED, to="lab", ok=False, error="no", why="end")
    epic.note(one.path, epic.BACKED, to="lab", ok=True, error="", why="manual")

    ran = epic.read(one.path)

    assert ran is not None
    assert ran.backup == ("lab", "home")
    assert ran.how == "done"
    assert set(ran.backed) == {"lab"}
    assert ran.backed["lab"]["ok"] is True
    assert ran.backed["lab"]["why"] == "manual"
    assert ran.backed["lab"]["at"]


def test_an_imported_run_reads_back_only_its_backups_here(
    workspace: Path,
) -> None:
    with Epic("ralph", "fix it", workspace, backup=["lab"]) as one:
        pass
    epic.note(one.path, epic.BACKED, to="lab", ok=True, error="", why="end")
    epic.note(one.path, "imported", **{"from": "x.hmzepic"})

    ran = epic.read(one.path)
    assert ran is not None
    assert ran.backup == ()
    assert ran.backed == {}

    epic.note(one.path, epic.BACKED, to="home", ok=True, error="", why="manual")
    ran = epic.read(one.path)
    assert ran is not None
    assert set(ran.backed) == {"home"}


def test_a_run_given_no_backup_says_none(workspace: Path) -> None:
    with Epic("ralph", "fix it", workspace) as one:
        pass

    ran = epic.read(one.path)

    assert ran is not None
    assert ran.backup == ()
    assert ran.backed == {}
    assert "backup" not in json.loads(one.journal.read_text().splitlines()[0])


def test_what_this_did_not_write_reads_as_no_run(tmp_path: Path) -> None:
    assert epic.read(tmp_path) is None
    _journal(tmp_path / JOURNAL, "not json", "[1]", {"event": "opened"})
    assert epic.read(tmp_path) is None


def test_a_journal_written_by_hand_reads_back_what_it_can(tmp_path: Path) -> None:
    _journal(
        tmp_path / JOURNAL,
        {
            "event": "began",
            "flow": "f",
            "agents": ["junk", {"agent": "b"}],
            "envs": "nope",
            "params": [1],
            "budget": 3,
            "spelling": store.SPELLING,
        },
        "{half a line",
        {"event": "opened", "agent": "b"},
    )

    ran = epic.read(tmp_path)
    assert ran is not None
    assert ran.agents == (Drove("b", "", "", "", ""),)
    assert ran.envs == ()
    assert ran.params == {}
    assert ran.budget is None
    assert ran.sessions == ()


def test_environments_written_the_old_way_read_back_as_spelled_now(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "respelled", _respelled)
    _journal(
        tmp_path / JOURNAL,
        {"event": "began", "flow": "f", "envs": ["box=docker@local/srv", "bare"]},
    )

    ran = epic.read(tmp_path)
    assert ran is not None
    assert ran.envs == ("box=docker/srv", "bare")
    assert ran.used == ran.envs


def test_sessions_across_records_read_oldest_first(tmp_path: Path) -> None:
    _journal(
        tmp_path / JOURNAL,
        {"event": "began", "flow": "outer"},
        {"event": "opened", "agent": "b", "session": "late", "at": "2026-01-02"},
        {"event": "opened", "agent": "b", "session": ""},
    )
    _journal(
        tmp_path / "epic.inner_abc.jsonl",
        {"event": "began", "flow": "inner"},
        {
            "event": "opened",
            "agent": "h",
            "backend": "codex",
            "session": "early",
            "at": "2026-01-01",
        },
    )

    found = epic.sessions(tmp_path)

    assert [(one.ident, one.flow, one.record) for one in found] == [
        ("early", "inner", "epic.inner_abc.jsonl"),
        ("late", "outer", JOURNAL),
    ]
    assert found[1].provider == LOCAL
    assert epic.opened(tmp_path) == {"h": ["early"], "b": ["late"]}
    assert epic.records(tmp_path) == [
        tmp_path / JOURNAL,
        tmp_path / "epic.inner_abc.jsonl",
    ]


def test_an_epic_with_no_record_has_none(tmp_path: Path) -> None:
    assert epic.records(tmp_path) == []
    assert epic.records(tmp_path / "gone") == []
    assert epic.sessions(tmp_path) == []
    assert epic.opened(tmp_path) == {}


def test_the_calls_of_a_run_read_back_as_the_tree_they_were(workspace: Path) -> None:
    with Epic("outer", "t", workspace) as one:
        first = one.called("a")
        nested = first.called("b")
        nested.ended(RuntimeError)
        first.ended()
        second = one.called("a")
        # Killed under it: never returned, never ended.

    calls = epic.tree(one.path)

    assert [(call.flow, call.how) for call in calls] == [("a", "done"), ("a", "")]
    assert calls[1].ended == ""
    assert calls[1].record == second.record
    assert [(call.flow, call.how) for call in calls[0].calls] == [("b", "failed")]
    assert calls[0].calls[0].calls == ()
    # A run read as a list says what it called, not what those called in turn.
    ran = epic.read(one.path)
    assert ran is not None
    assert [call.calls for call in ran.called] == [(), ()]


def test_a_ring_written_by_hand_is_read_once(tmp_path: Path) -> None:
    ring = "epic.r_1.jsonl"
    _journal(tmp_path / JOURNAL, {"event": "called", "flow": "r", "epic": ring})
    _journal(tmp_path / ring, {"event": "called", "flow": "r", "epic": ring})
    _journal(tmp_path / "x", {"event": "called", "flow": "nowhere"})

    (call,) = epic.tree(tmp_path)

    assert call.calls == (Called("r", "", ring, call.calls[0].began),)
    assert call.calls[0].calls == ()


def _kept(
    workspace: Path,
    when: str,
    flow: str = "ralph",
    *,
    resumable: bool = True,
    call: bool = True,
) -> Path:
    """An epic as a run that started at `when` left it, written by hand so the order is known."""
    at = epic.under(workspace) / f"2026010{when}T000000.000Z-abcdef"
    at.mkdir(parents=True)
    _journal(
        at / JOURNAL,
        {
            "event": "began",
            "flow": flow,
            "ref": f"official/{flow}",
            "resumable": resumable,
        },
    )
    if call:
        _journal(at / RESUME, {"t": "call", "id": 1, "parent": 0})
    return at


def test_the_epics_of_a_workspace_are_listed_oldest_first(workspace: Path) -> None:
    assert epic.epics(workspace) == []
    second = _kept(workspace, "2")
    first = _kept(workspace, "1")
    (epic.under(workspace) / "not-an-epic").mkdir()

    assert epic.epics(workspace) == [first, second]


def test_an_epic_made_now_is_listed_after_one_made_before(workspace: Path) -> None:
    before = _kept(workspace, "1")

    with Epic("f", "t", workspace) as now:
        pass

    assert epic.epics(workspace) == [before, now.path]


def test_epics_begun_inside_one_millisecond_are_listed_as_they_began(
    workspace: Path,
) -> None:
    begun: list[Path] = []
    for _ in range(20):
        with Epic("f", "t", workspace) as one:
            begun.append(one.path)

    assert epic.epics(workspace) == begun


# ----------------------------------------------------------- picking up


def test_only_a_journal_holding_a_call_can_be_picked_up(tmp_path: Path) -> None:
    assert epic.picks_up(tmp_path) is False

    _journal(tmp_path / RESUME, "garbage", "[1]", {"t": "set", "id": 1})
    assert epic.picks_up(tmp_path) is False

    _journal(tmp_path / RESUME, {"t": "call", "id": 1, "parent": 0})
    assert epic.picks_up(tmp_path) is True


def test_a_run_still_going_cannot_be_picked_up(workspace: Path) -> None:
    with Epic("f", "t", workspace, resumable=True) as going:
        _journal(going.resume, {"t": "call", "id": 1, "parent": 0})
        assert epic.picks_up(going.path) is False

    assert epic.picks_up(going.path) is True


def test_a_run_is_going_while_its_epic_is_held(workspace: Path) -> None:
    with Epic("f", "t", workspace) as held:
        assert epic.going(held.path) is True

    assert epic.going(held.path) is False
    assert epic.going(workspace / "never") is False


def test_what_a_flow_kept_is_read_back_key_by_key(tmp_path: Path) -> None:
    _journal(
        tmp_path / RESUME,
        {"t": "call", "id": 1, "parent": 0, "ref": "outer"},
        {"t": "set", "id": 1, "key": "round", "value": 1},
        {"t": "set", "id": 1, "key": "gone", "value": True},
        {"t": "call", "id": 2, "parent": 1, "ref": "inner"},
        {"t": "set", "id": 2, "key": "x", "value": "inner's"},
        {"t": "set", "id": 1, "key": "round", "value": 2},
        {"t": "del", "id": 1, "key": "gone"},
        {"t": "set", "id": "bad"},
        {"t": "set", "id": 9, "key": "orphan", "value": 0},
    )

    assert epic.state(tmp_path) == {"round": 2}
    assert epic.state(tmp_path, "inner") == {"x": "inner's"}
    assert epic.state(tmp_path, "nobody") == {}
    assert epic.state(tmp_path / "gone") == {}


def test_the_run_picked_up_is_the_newest_that_can_be(workspace: Path) -> None:
    _kept(workspace, "1")
    newer = _kept(workspace, "2")
    _kept(workspace, "3", call=False)
    _kept(workspace, "4", resumable=False)
    _kept(workspace, "5", "other")
    (nothing := epic.under(workspace) / "6-nothing-began").mkdir()
    _journal(nothing / JOURNAL, {"event": "x"})

    assert epic.resumed("ralph", workspace) == newer
    assert epic.resumed("official/ralph", workspace) == newer
    assert epic.resumed("nothing", workspace) is None


# ----------------------------------------------------------- where it is kept


@dataclass
class Profile:
    logs: tuple[str, ...] = ("projects/*/{ident}.jsonl",)

    def logged(self, ident: str) -> tuple[str, ...]:
        return tuple(one.format(ident=ident) for one in self.logs)


def test_a_sessions_logs_are_found_as_its_cli_lays_them_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backends, "named", {"claude": Profile()}.get)
    kept = tmp_path / SESSIONS / "claude" / "projects" / "p"
    kept.mkdir(parents=True)
    (kept / "s1.jsonl").write_text("{}")
    (kept / "s2.jsonl").write_text("{}")
    one = Session(
        "b", "claude", LOCAL, "s1", "b-claude@local-s1", where="sessions/claude"
    )

    assert epic.where(tmp_path, one) == tmp_path / SESSIONS / "claude"
    assert epic.logs(tmp_path, one) == {"projects/p/s1.jsonl": kept / "s1.jsonl"}
    assert epic.logs(tmp_path, one._replace(backend="nobody")) == {}
    assert epic.logs(tmp_path, one._replace(ident="none")) == {}


def test_an_epic_from_before_sessions_were_kept_reads_its_links(
    tmp_path: Path,
) -> None:
    one = Session("b", "claude", LOCAL, "s1", "b-claude@local-s1")
    links = tmp_path / SESSIONS / one.name
    links.mkdir(parents=True)
    target = tmp_path / "log.jsonl"
    target.write_text("{}")
    (links / "log.jsonl").symlink_to(target)
    (links / "dangling.jsonl").symlink_to(tmp_path / "gone")

    assert epic.where(tmp_path, one) == links
    assert epic.logs(tmp_path, one) == {"log.jsonl": target.resolve()}
    assert epic.logs(tmp_path, one._replace(name="other")) == {}


# ------------------------------------------------------------------ spending


def test_spending_counts_each_day_and_flow_and_how_each_run_ended() -> None:
    def ran(began: str = "2026-10-08T10:00:00+00:00", **said: Any) -> epic.Ran:
        return epic.Ran(Path("e"), flow=said.pop("flow", "ralph"), began=began, **said)

    said = epic.spending(
        [
            ran(how="done", spent={"cost": 1.5, "output_tokens": 300, "seconds": 60}),
            ran(
                "2026-10-07T23:59:00+00:00",
                flow="goal",
                how="failed",
                spent={"cost": 2.0, "output_tokens": 100, "seconds": 30},
            ),
            # Still going: a run, and nothing spent yet.
            ran("2026-10-08T11:00:00+00:00"),
            # Before the days asked about.
            ran("2026-10-01T10:00:00+00:00", how="done", spent={"cost": 9.0}),
            ran("not a moment", how="done", spent={"cost": 9.0}),
        ],
        days=2,
        now=datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.UTC),
    )

    assert [(one["day"], one["runs"], one["cost"]) for one in said["days"]] == [
        ("2026-10-07", 1, 2.0),
        ("2026-10-08", 2, 1.5),
    ]
    assert [(one["flow"], one["runs"]) for one in said["flows"]] == [
        ("goal", 1),  # the costliest first
        ("ralph", 2),
    ]
    assert said["ended"] == {"done": 1, "failed": 1, epic.UNFINISHED: 1}
    assert said["whole"] == {
        "runs": 3,
        "cost": 3.5,
        "output_tokens": 400,
        "seconds": 90.0,
    }


def test_how_a_run_went_is_its_end_or_whether_it_is_still_going(
    workspace: Path,
) -> None:
    ended = epic.Ran(workspace, how="stopped")
    still = epic.Ran(workspace)

    assert epic.ending(ended, going=True) == "stopped"
    assert epic.ending(still, going=True) == epic.RUNNING
    assert epic.ending(still, going=False) == epic.UNFINISHED
    assert set(epic.ENDINGS) >= {"done", "failed", "stopped", epic.RUNNING}


def test_a_run_is_found_by_how_it_went_its_flow_and_its_task(workspace: Path) -> None:
    ran = epic.Ran(workspace / "20260101T000000.000Z-ab", flow="ralph", task="Fix it")

    assert epic.found(ran, "done")
    assert epic.found(ran, "done", how="done", flow="ralph", text="fix")
    assert epic.found(ran, "done", text="RALPH")
    assert epic.found(ran, "done", text="000z-ab")
    assert not epic.found(ran, "done", how="failed")
    assert not epic.found(ran, "done", flow="chat")
    assert not epic.found(ran, "done", text="break")


def test_a_btw_event_an_earlier_release_wrote_says_nothing(workspace: Path) -> None:
    with Epic("ralph", "fix it", workspace) as one:
        pass
    assert (before := epic.read(one.path)) is not None

    epic.note(one.path, "btw", agent="claude@work/opus:high")

    # Nothing of it but when its record was last written.
    after = epic.read(one.path)
    assert after is not None
    assert after == before._replace(updated=after.updated)
    assert not hasattr(before, "btw")
