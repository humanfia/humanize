"""One run of one flow, written down as it runs and read back afterwards."""

from __future__ import annotations

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
        (("builder", "claude", "work", "abc-123"), "builder-claude@work-abc-123"),
        (("builder", "claude", "", "abc"), f"builder-claude@{LOCAL}-abc"),
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

    assert under.parent == Path(os.environ["HUMANIZE_HOME"]) / "epics"
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
        agents=[Drove("builder", "claude", "opus", "high", "work")],
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
        }
    ]
    assert began["envs"] == ["box=docker/srv"]
    assert "used" not in began
    assert began["params"] == {"rounds": 3}
    assert began["budget"] == {"cost": 5.0}
    assert began["spelling"] == store.SPELLING
    assert "profile" not in began
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

    with Epic("f", "t", workspace, profile=True) as one:
        assert made[0].started
        assert not made[0].stopped

    assert made[0].at == one.path / profile.PROFILE
    assert made[0].stopped
    assert _lines(one.journal)[0]["profile"] is True


def test_a_machine_that_cannot_be_profiled_still_runs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refusing(at: Path) -> Profiler:
        return Profiler(at, refuses=True)

    monkeypatch.setattr(profile, "Profiler", refusing)

    with Epic("f", "t", workspace, profile=True) as one:
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


def test_where_a_harness_ran_is_said_as_an_affinity_says_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, harbored: str
) -> None:
    monkeypatch.setattr(machines, "AnchoredConfig", Anchored)

    assert epic.harnessed(None) == store.HERE
    assert epic.harnessed(cast("Any", object())) == store.HERE
    assert epic.harnessed(cast("Any", Anchored(Anchor(native=True)))) == store.SELF
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
    assert said["harness"] == store.SELF


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
        agents=[Drove("builder", "claude", "opus", "high")],
        envs=["box=docker/srv"],
        used=["box=ssh@gpu/srv"],
        params={"rounds": 3},
        budget={"cost": 1.0},
        resumable=True,
    ) as one:
        one.session("builder", "claude", "", "s1")
        inner = one.called("inner", "part")
        inner.session("helper", "codex", "team", "s2")
        inner.ended()
        one.stopped()

    ran = epic.read(one.path)
    assert ran is not None
    assert ran.name == one.path.name
    assert (ran.flow, ran.task, ran.ref) == ("ralph", "fix it", "official/ralph")
    assert ran.workspace == str(workspace.resolve())
    assert ran.began
    assert ran.ended
    assert ran.how == "stopped"
    assert ran.agents == (Drove("builder", "claude", "opus", "high", ""),)
    assert ran.envs == ("box=docker/srv",)
    assert ran.used == ("box=ssh@gpu/srv",)
    assert ran.params == {"rounds": 3}
    assert ran.budget == {"cost": 1.0}
    assert ran.resumable is True
    assert ran.picked_up == ""
    assert ran.profile is False
    assert [one.ident for one in ran.sessions] == ["s1", "s2"]
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
