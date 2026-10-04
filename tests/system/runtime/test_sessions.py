"""Every session humanize runs, kept where humanize keeps it and nowhere else.

A turn keeps its CLI's sessions in a directory of humanize's own -- the run's epic for an agent a
run drives -- by being run under the supervisor that answers a turn's credential paths for an
account, answering its session paths too. So the whole of this needs a kernel that will hand
over a tracee, which CI is not promised: `tests/integration/runtime/test_epics.py` is the half
that keeps nothing and reads back where a session was left instead.

The CLI is the stand-in `claude` of :mod:`tests.recording`, which keeps each conversation where
Claude Code keeps one and refuses to resume one it cannot find there -- so a fork that opens is
a fork that read its parent back out of the run, and nothing else. The real CLIs, one turn each,
are `tests/system/agents/test_kept_sessions.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.runtime.epic import SESSIONS, epics, logs, sessions, where
from hmz.runtime.exporting import bundle
from hmz.runtime.runner import Runner
from tests.recording import AGENT, ONE, TASK, held, logged, standing_in
from tests.stubs import written
from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _links(under: Path) -> list[Path]:
    """Every symlink anywhere under a directory, which an epic no longer holds any of."""
    return [one for one in under.rglob("*") if one.is_symlink()]


@traced
def test_a_run_keeps_its_session_in_its_epic_and_nothing_of_it_at_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transcript is written into the epic, as the only copy there is, and read from it."""
    config = standing_in(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)

    Runner(tmp_path / "flow", agents={"builder": AGENT}, budget={"cost": 1}).run(TASK)

    (epic,) = epics()
    (one,) = sessions(epic)
    kept = epic / SESSIONS / "claude"
    log = logged(kept, tmp_path.resolve(), one.ident)
    assert one.where == f"{SESSIONS}/claude"
    assert where(epic, one) == kept
    assert "single word: done" in log.read_text()
    assert logs(epic, one) == {log.relative_to(kept).as_posix(): log}
    # Nothing at the CLI's own home -- not the transcript, not the directory it goes in --
    # and nothing in the epic that points anywhere else.
    assert not (config / "projects").exists()
    assert not _links(epic)
    # And a bundle carries it as what it says.
    inside = held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert (
        "single word: done" in inside[f"{SESSIONS}/{one.name}/{log.relative_to(kept)}"]
    )


@traced
def test_a_fork_into_another_agent_reads_its_parent_back_where_it_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a read-only side question does to a run's session, with no run behind the side.

    The fork is a second process resuming the first conversation by id, which the stand-in
    refuses unless it finds that conversation where it looks: so the fork answering at all is
    the parent read back out of where it was kept -- and the child written there beside it.
    """
    config = standing_in(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    agent.keeps = tmp_path / "kept"
    first = agent.new()
    assert first("Reply with the single word: one") == "one"
    side = agent.clone()

    forked = first.fork(into=side)

    assert forked("Reply with the single word: two") == "two"
    assert side.keeps == tmp_path / "kept"
    projects = tmp_path / "kept" / "claude" / "projects"
    assert {one.stem for one in projects.glob("*/*.jsonl")} == {first.id, forked.id}
    assert not (config / "projects").exists()
    agent.stop()
    side.stop()


@traced
def test_an_agent_no_run_drives_keeps_its_sessions_where_its_cli_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driven by hand is nobody's run, and nothing of humanize's own is kept for it."""
    from hmz import home

    config = standing_in(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))

    session = agent.new()
    assert session("Reply with the single word: alone") == "alone"

    assert agent.keeps is None
    assert agent.kept() == config
    assert logged(config, tmp_path.resolve(), session.id).is_file()
    assert not (home() / "sessions").exists()
    agent.stop()
