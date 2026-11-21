"""`hmz.daemon.api.chats`: a chat as `chat.*` says it by name, off its own record."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon import hosts, reach, where
from hmz.daemon.api import chats, runs, workspaces
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from hmz.rpc import Call

ROW = {
    "id",
    "title",
    "workspace",
    "folderless",
    "workdir",
    "env",
    "agent",
    "model",
    "began",
    "updated",
    "state",
    "slot",
    "asking",
    "permission",
    "archived",
    "spent",
}

WORKSPACE = str(Path("/w").resolve())


def _ran(name: str = "20260101-abc", **said: Any) -> Any:
    """A chat read back, as far as a row and a detail read one."""
    assistant = SimpleNamespace(
        name="NeiKos496",
        agent="assistant",
        spec="claude@work/opus:high",
        backend="claude",
        model="opus",
        effort="high",
        provider="work",
    )
    read: dict[str, Any] = {
        "name": name,
        "at": Path("/chats/-w") / name,
        "workspace": "/w",
        "flow": "",
        "ref": "",
        "task": "fix the parser\nand then the tests",
        "title": "fix the parser",
        "began": "2026-01-01T00:00:00.000Z",
        "updated": "2026-01-01T00:05:00.000Z",
        "ended": "2026-01-01T00:05:00.000Z",
        "how": "stopped",
        "reopened": "",
        "agents": (assistant,),
        "sessions": (),
        "resumable": False,
        "spent": None,
        "backup": (),
        "backed": {},
        "envs": (),
        "used": (),
        "params": {},
        "budget": {},
        "picked_up": "",
        "profile_flow": False,
        "profile_environment": False,
        "kind": "chat",
        "chat": True,
        "prefer": "",
        "permission": "",
        "archived": False,
        "workdir": "",
        "env": "",
        "forked": "",
        "adopted": "",
    }
    return SimpleNamespace(**read | said)


def _session(ident: str, at: str) -> Any:
    return SimpleNamespace(
        agent="NeiKos496",
        backend="claude",
        provider="work",
        ident=ident,
        name=f"NeiKos496-claude@work-{ident}",
        at=at,
        flow="",
        parent="",
        harness="claude",
    )


def _status(**said: Any) -> dict[str, Any]:
    """How a chat's host stands, as it says of itself."""
    return {
        "state": "running",
        "run": 1,
        "epic_kind": "chat",
        "epic": "",
        "chat": "20260101-abc",
        "turn": "done",
        "pending": [{"question": "q1", "mode": "listen"}],
        "workspace": WORKSPACE,
        "slot": "chat:1a",
    } | said


# ------------------------------------------------------------------ a chat's row


def test_every_method_that_names_a_chat_is_served() -> None:
    assert set(chats.METHODS) == {
        f"chat.{one}"
        for one in (
            "list",
            "get",
            "rename",
            "fork",
            "archive",
            "unarchive",
            "backup",
            "delete",
            "harness.list",
            "harness.get",
            "harness.adopt",
        )
    }


@pytest.mark.parametrize(
    ("ran", "status", "going", "state"),
    [
        # No host holds it: it rests, however it last ended short of failing.
        (_ran(), None, False, "resting"),
        (_ran(how=""), None, False, "resting"),
        (_ran(how="failed"), None, False, "failed"),
        (_ran(how="failed"), None, True, "failed"),
        # Another process holds it, which says no more of it than that it goes.
        (_ran(how=""), None, True, "going"),
        # On a host: between turns, in a turn, and waiting on an answer mid-turn.
        (_ran(how=""), _status(), False, "going"),
        (_ran(how=""), _status(turn="running", pending=[]), False, "turn"),
        (
            _ran(how=""),
            _status(turn="running", pending=[{"question": "q2", "mode": "ask"}]),
            False,
            "asking",
        ),
        # A host carrying it on holds it, whatever its record last said.
        (_ran(how="failed"), _status(turn="running", pending=[]), False, "turn"),
        (_ran(), _status(turn=""), True, "going"),
    ],
)
def test_a_chat_stands_as_its_host_says_else_as_it_was_written(
    ran: Any, status: dict[str, Any] | None, going: bool, state: str
) -> None:
    assert chats.state(ran, status, going=going) == state
    assert chats.row(ran, status, going=going)["state"] == state


def test_a_resting_chats_row_is_what_its_record_says() -> None:
    said = chats.row(_ran())

    assert set(said) == ROW
    assert said == {
        "id": "20260101-abc",
        "title": "fix the parser",
        "workspace": WORKSPACE,
        "folderless": False,
        # Where its assistant works: the workspace, for one in no worktree.
        "workdir": WORKSPACE,
        "env": f"local/{WORKSPACE.lstrip('/')}",
        "agent": "claude@work/opus:high",
        "model": "opus",
        "began": "2026-01-01T00:00:00.000Z",
        "updated": "2026-01-01T00:05:00.000Z",
        "state": "resting",
        "slot": "",
        "asking": [],
        # A chat whose record gives none has a chat's own.
        "permission": "workspace-write",
        "archived": False,
        "spent": None,
    }


def test_a_row_says_a_chat_started_in_no_folder_is_folderless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Section 4.25.5.2 of daemon.md: told by the daemon, which made its directory.
    asked: list[str] = []

    def folderless(workspace: str) -> bool:
        asked.append(workspace)
        return True

    monkeypatch.setattr(where, "folderless", folderless)

    assert chats.row(_ran())["folderless"] is True
    assert asked == [WORKSPACE]


def test_a_row_says_the_worktree_the_permission_the_spending_and_the_host() -> None:
    ran = _ran(
        workdir="/home/envs/w/worktrees/x",
        permission="read-only",
        archived=True,
        spent={"cost": 1.5, "output_tokens": 2000, "seconds": 61.0},
        title="t" * 500,
        agents=(),
    )
    status = _status(
        turn="running",
        run=3,
        pending=[
            {"question": "q7", "mode": "ask"},
            {"question": "q8", "mode": "listen"},
        ],
    )

    said = chats.row(ran, status)

    assert set(said) == ROW
    assert (said["workdir"], said["permission"], said["archived"]) == (
        "/home/envs/w/worktrees/x",
        "read-only",
        True,
    )
    assert said["env"] == "local/home/envs/w/worktrees/x"
    # Moved to a runtime, it works in the directory there, whatever worktree it began in.
    moved = chats.row(
        _ran(workdir="/home/envs/w/worktrees/x", env="ssh@gpu-box/~/repo")
    )
    assert (moved["env"], moved["workdir"], moved["workspace"]) == (
        "ssh@gpu-box/~/repo",
        "~/repo",
        WORKSPACE,
    )
    assert chats.row(_ran(env="docker/srv/repo"))["workdir"] == "/srv/repo"
    assert (said["state"], said["slot"], said["asking"]) == (
        "asking",
        "chat:1a",
        ["3:q7"],
    )
    # As an epic's row says what it spent: the figures, and each as it is read.
    assert said["spent"]["cost"] == 1.5
    assert {"money", "tokens", "worked"} <= set(said["spent"])
    assert all(said["spent"][one] for one in ("money", "tokens", "worked"))
    assert said["title"] == "t" * 240
    # One whose record names no assistant says none.
    assert (said["agent"], said["model"]) == ("", "")


def test_a_chat_whole_is_its_row_and_what_it_opened() -> None:
    ran = _ran(
        how="",
        reopened="2026-01-02T00:00:00.000Z",
        sessions=(
            _session("s1", "2026-01-01T00:00:01.000Z"),
            _session("s2", "2026-01-01T00:02:00.000Z"),
            _session("s3", "2026-01-02T00:00:01.000Z"),
        ),
        prefer="flow",
        forked="20251231-0ld",
        backup=("mine",),
        backed={"mine": {"at": "x", "ok": True, "error": "", "why": "ended"}},
    )

    said = chats.detail(ran, _status())

    assert set(said) == ROW | {
        "at",
        "task",
        "prefer",
        "forked",
        "adopted",
        "agents",
        "sessions",
        "earlier",
        "backup",
        "backed",
    }
    assert {key: said[key] for key in ROW} == chats.row(ran, _status())
    assert (said["at"], said["task"]) == (
        str(Path("/chats/-w/20260101-abc")),
        "fix the parser\nand then the tests",
    )
    assert (said["prefer"], said["forked"]) == ("flow", "20251231-0ld")
    assert said["agents"] == [
        {
            "name": "NeiKos496",
            "role": "assistant",
            "runs": "claude@work/opus:high",
            "backend": "claude",
            "model": "opus",
            "effort": "high",
            "provider": "work",
        }
    ]
    assert [one["ident"] for one in said["sessions"]] == ["s1", "s2", "s3"]
    assert set(said["sessions"][0]) == {
        "agent",
        "backend",
        "provider",
        "ident",
        "name",
        "at",
        "flow",
        "parent",
        "harness",
    }
    # The sessions it opened before it was last carried on are its earlier ones.
    assert said["earlier"] == 2
    assert (said["backup"], said["backed"]) == (["mine"], ran.backed)
    # Nothing of an epic's that a chat has none of.
    for absent in ("flow", "kind", "params", "budget", "picks_up", "how", "held"):
        assert absent not in said


# ------------------------------------------------------------------ the list


class _Chats:
    """The chats, as far as `chat.*` reads them: newest first, and by name."""

    def __init__(self, *held: Any) -> None:
        self.held = list(held)
        self.goes: set[str] = set()
        self.asked: list[str] = []
        self.pushed: list[tuple[str, Any]] = []
        self.queued: list[str] = ["mine"]

    def all(self, workspace: str = "") -> list[Any]:
        self.asked.append(workspace)
        return [
            one
            for one in self.held
            if not workspace or str(Path(one.workspace).resolve()) == workspace
        ]

    def named(self, name: str) -> Any:
        for one in self.held:
            if one.name == name:
                return one
        raise RpcError(404, f"There is no chat {name}.")

    def going(self, ran: Any) -> bool:
        return ran.name in self.goes

    def traced(self, ran: Any) -> list[dict[str, Any]]:
        return [{"key": f"{ran.name}/1", "actions": []}]

    def hmz(self, ran: Any) -> Any:
        def push(ran: Any, to: Any) -> list[str]:
            self.pushed.append((ran.name, to))
            if to == ["nowhere"]:
                raise ValueError("there is no backup target nowhere")
            return self.queued

        return SimpleNamespace(backups=SimpleNamespace(push=push))


def test_a_page_of_chats_is_those_not_archived_newest_first() -> None:
    held = _Chats(
        _ran("c4", title="Parser"),
        _ran("c3", archived=True, title="Old parser"),
        _ran("c2", task="tidy the PARSER docs", title="Docs"),
        _ran("c1", title="Lexer", how=""),
    )
    held.goes = {"c1"}
    hosts = {"c4": _status(chat="c4", turn="running", pending=[])}

    said = chats.listed(cast("Any", held), hosts)

    assert [one["id"] for one in said["chats"]] == ["c4", "c2", "c1"]
    assert (said["total"], said["offset"], said["limit"]) == (3, 0, 50)
    assert all(set(one) == ROW for one in said["chats"])
    assert [(one["state"], one["slot"]) for one in said["chats"]] == [
        ("turn", "chat:1a"),
        ("resting", ""),
        ("going", ""),
    ]
    # The archived ones are listed in place of the others, never among them.
    archived = chats.listed(cast("Any", held), hosts, archived=True)
    assert [one["id"] for one in archived["chats"]] == ["c3"]
    assert (archived["chats"][0]["archived"], archived["total"]) == (True, 1)


def test_a_list_is_searched_paged_and_cut_to_what_may_be_seen() -> None:
    held = _Chats(
        _ran("c5", title="Parser"),
        _ran("c4", task="tidy the PARSER docs", title="Docs"),
        _ran("c3-parser", title="Lexer", task="lex"),
        _ran("c2", title="Lexer", task="lex"),
        _ran("c1", title="parser again", workspace="/elsewhere"),
    )

    def names(**said: Any) -> list[str]:
        return [
            one["id"] for one in chats.listed(cast("Any", held), {}, **said)["chats"]
        ]

    # By its title, its first message or its name, in any case.
    assert names(q="pArSeR") == ["c5", "c4", "c3-parser", "c1"]
    assert names(q="nothing") == []
    # What is found is what is counted, whatever the page holds.
    page = chats.listed(cast("Any", held), {}, q="parser", offset=1, limit=2)
    assert [one["id"] for one in page["chats"]] == ["c4", "c3-parser"]
    assert (page["total"], page["offset"], page["limit"]) == (4, 1, 2)
    # One workspace's alone.
    assert names(workspace=WORKSPACE) == ["c5", "c4", "c3-parser", "c2"]
    assert held.asked[-1] == WORKSPACE
    # Ai-chan's conversations are none of them, nor what her reach does not reach.
    assert names(hers={"c5", "c2"}) == ["c4", "c3-parser", "c1"]

    def reached(name: str, workspace: str) -> bool:
        return workspace == "/elsewhere" or name == "c4"

    assert names(kept=reached) == ["c4", "c1"]
    assert chats.listed(cast("Any", held), {}, kept=reached)["total"] == 2


# ------------------------------------------------------------------ the methods


class _Conversations:
    def __init__(self, *hers: str) -> None:
        self.hers = set(hers)

    def epics(self) -> set[str]:
        return set(self.hers)


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> _Chats:
    """The daemon's chats, its hosts and Ai-chan's conversations, as a test sets them."""
    fake = _Chats()
    hosts: dict[str, dict[str, Any]] = {}
    fake.hosts = hosts  # pyright: ignore[reportAttributeAccessIssue]
    kept = _Conversations()
    fake.kept = kept  # pyright: ignore[reportAttributeAccessIssue]

    def statuses() -> dict[str, dict[str, Any]]:
        return dict(hosts)

    def conversations() -> _Conversations:
        return kept

    monkeypatch.setattr(chats, "CHATS", fake)
    monkeypatch.setattr(workspaces, "statuses", statuses)
    monkeypatch.setattr(reach, "conversations", conversations)
    return fake


def _call(method: str, **params: Any) -> Any:
    call = cast("Call", SimpleNamespace(method=method, params=params))
    return chats.METHODS[method](call)


def _refused(method: str, **params: Any) -> tuple[int, str]:
    with pytest.raises(RpcError) as refused:
        _call(method, **params)
    return refused.value.code, refused.value.message


def _hosts(held: _Chats) -> dict[str, dict[str, Any]]:
    return cast("Any", held).hosts


def test_the_chats_hosts_go_with_are_those_going_by_name(held: _Chats) -> None:
    _hosts(held).update(
        {
            "a": _status(chat="c1"),
            "b": _status(chat="c2", state="stopping", slot="chat:2b"),
            # One that has ended, whose host still stands, and a flow's host.
            "c": _status(chat="c3", state="idle"),
            "d": _status(chat="", epic="e1", epic_kind="flow", slot=""),
        }
    )

    said = chats.hosted()

    assert set(said) == {"c1", "c2"}
    assert said["c2"]["slot"] == "chat:2b"


def test_chat_list_reads_every_workspaces_chats_or_one_s(
    held: _Chats, tmp_path: Path
) -> None:
    here = str(tmp_path.resolve())
    held.held = [_ran("c2", workspace=here), _ran("c1"), _ran("hers")]
    cast("Any", held).kept.hers = {"hers"}
    _hosts(held)["x"] = _status(chat="c2", turn="running", pending=[])

    said = _call("chat.list")

    assert [(one["id"], one["state"]) for one in said["chats"]] == [
        ("c2", "turn"),
        ("c1", "resting"),
    ]
    assert (said["total"], said["offset"], said["limit"]) == (2, 0, 50)
    only = _call("chat.list", workspace=here)
    assert [one["id"] for one in only["chats"]] == ["c2"]
    # A workspace since removed still names its chats.
    assert _call("chat.list", workspace=str(tmp_path / "gone"))["chats"] == []
    assert _call("chat.list", archived=True, q="c", limit=1, offset=0)["chats"] == []
    assert _refused("chat.list", limit=0) == (
        -32602,
        "chat.list takes limit as integer from 1 to 200.",
    )
    assert _refused("chat.list", offset=-1) == (
        -32602,
        "chat.list takes offset as integer from 0.",
    )
    assert _refused("chat.list", workspace="w") == (
        400,
        "Say the workspace as a whole path, not w.",
    )


def test_an_ai_chan_conversation_her_host_has_only_just_named_is_not_listed(
    held: _Chats,
) -> None:
    held.held = [_ran("new"), _ran("c1")]
    _hosts(held)["x"] = _status(chat="new", slot="ai:3")

    assert [one["id"] for one in _call("chat.list")["chats"]] == ["c1"]
    assert _refused("chat.rename", chat="new", title="mine") == (
        404,
        "There is no chat new.",
    )


def test_chat_get_reads_one_chat_and_its_trace_where_asked(held: _Chats) -> None:
    held.held = [_ran("c1", how="")]
    _hosts(held)["x"] = _status(chat="c1")

    said = _call("chat.get", chat="c1")

    assert (said["id"], said["state"], said["slot"]) == ("c1", "going", "chat:1a")
    assert "trace" not in said
    assert "trace" not in _call("chat.get", chat="c1", trace=False)
    traced = _call("chat.get", chat="c1", trace=True)
    assert traced["trace"] == [{"key": "c1/1", "actions": []}]
    assert _refused("chat.get", chat="nothing") == (404, "There is no chat nothing.")


def test_an_ai_chan_conversation_is_read_by_chat_get_and_nothing_else(
    held: _Chats, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.daemon.api import runs

    epics = _Chats(_ran("old", at=Path("/epics/-w/old")))
    monkeypatch.setattr(runs, "RUNS", epics)
    held.held = [_ran("hers", task="what is going on?", title="what is going on?")]
    cast("Any", held).kept.hers = {"hers", "old"}

    assert _call("chat.get", chat="hers")["task"] == "what is going on?"
    for method, more in (
        ("chat.rename", {"title": "mine"}),
        ("chat.fork", {}),
        ("chat.archive", {}),
        ("chat.unarchive", {}),
        ("chat.backup", {}),
        ("chat.delete", {}),
    ):
        assert _refused(method, chat="hers", **more) == (
            404,
            "There is no chat hers.",
        )
    # An epic is no chat for `chat.get` to read, were it named as one of hers: one an
    # earlier hmz began for her is a chat once the daemon has moved it, and none before.
    assert _refused("chat.get", chat="old") == (404, "There is no chat old.")


@pytest.fixture
def noted(monkeypatch: pytest.MonkeyPatch, held: _Chats) -> list[tuple[Any, ...]]:
    """What is written into a chat's record, which is read back as written."""
    import hmz.runtime.epic

    written: list[tuple[Any, ...]] = []

    def note(at: Path, event: str, **said: Any) -> None:
        written.append((at, event, said))
        for one in held.held:
            if one.at == at:
                for key, value in said.items():
                    setattr(one, key, value)

    monkeypatch.setattr(hmz.runtime.epic, "note", note)
    return written


def test_a_chat_is_renamed_to_a_title_that_says_something(
    held: _Chats, noted: list[tuple[Any, ...]]
) -> None:
    ran = _ran("c1")
    held.held = [ran]

    said = _call("chat.rename", chat="c1", title="  The\n parser \t rewrite ")

    assert noted == [(ran.at, "set", {"title": "The parser rewrite"})]
    assert set(said) == ROW
    assert (said["id"], said["title"]) == ("c1", "The parser rewrite")
    _call("chat.rename", chat="c1", title="x" * 300)
    assert noted[-1][2] == {"title": "x" * 240}
    assert _refused("chat.rename", chat="c1", title=" \n ") == (
        400,
        "A chat's title says something.",
    )
    assert len(noted) == 2
    assert _refused("chat.rename", chat="none", title="t") == (
        404,
        "There is no chat none.",
    )


def test_a_chat_is_archived_and_unarchived_once_each(
    held: _Chats, noted: list[tuple[Any, ...]]
) -> None:
    ran = _ran("c1")
    held.held = [ran]

    assert _call("chat.archive", chat="c1")["archived"] is True
    # Archived already: nothing more is written.
    assert _call("chat.archive", chat="c1")["archived"] is True
    assert noted == [(ran.at, "set", {"archived": True})]
    assert [one["id"] for one in _call("chat.list", archived=True)["chats"]] == ["c1"]
    assert _call("chat.list")["chats"] == []

    assert _call("chat.unarchive", chat="c1")["archived"] is False
    assert _call("chat.unarchive", chat="c1")["archived"] is False
    assert noted[1:] == [(ran.at, "set", {"archived": False})]
    assert [one["id"] for one in _call("chat.list")["chats"]] == ["c1"]
    for method in ("chat.archive", "chat.unarchive"):
        assert _refused(method, chat="none") == (404, "There is no chat none.")


def test_a_chat_is_forked_between_turns_and_never_in_one(
    held: _Chats, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hmz.runtime.epic

    forks: list[Path] = []

    def forked(at: Path) -> Path:
        forks.append(at)
        if at.name == "c2":
            raise ValueError(
                "c2 cannot be forked: its conversation is not kept in the chat"
            )
        return at.parent / "20260102-new"

    monkeypatch.setattr(hmz.runtime.epic, "forked", forked)
    held.held = [_ran("c1"), _ran("c2")]

    assert _call("chat.fork", chat="c1") == {"chat": "20260102-new"}
    # Between turns on a host, its conversation stands still, and is forked all the same.
    _hosts(held)["x"] = _status(chat="c1")
    assert _call("chat.fork", chat="c1") == {"chat": "20260102-new"}

    open_ = (409, "Chat c1 has a turn open; fork it once it is done.")
    _hosts(held)["x"] = _status(chat="c1", turn="running", pending=[])
    assert _refused("chat.fork", chat="c1") == open_
    _hosts(held)["x"] = _status(
        chat="c1", turn="running", pending=[{"question": "q", "mode": "ask"}]
    )
    assert _refused("chat.fork", chat="c1") == open_
    assert len(forks) == 2

    assert _refused("chat.fork", chat="c2") == (
        409,
        "C2 cannot be forked: its conversation is not kept in the chat.",
    )
    assert _refused("chat.fork", chat="none") == (404, "There is no chat none.")


def test_a_chat_is_backed_up_as_a_run_is(held: _Chats) -> None:
    held.held = [_ran("c1")]

    assert _call("chat.backup", chat="c1") == {"queued": ["mine"]}
    assert _call("chat.backup", chat="c1", to=["mine"]) == {"queued": ["mine"]}
    assert held.pushed == [("c1", None), ("c1", ["mine"])]
    assert _refused("chat.backup", chat="c1", to=["nowhere"]) == (
        400,
        "There is no backup target nowhere.",
    )
    held.queued = []
    assert _refused("chat.backup", chat="c1") == (
        409,
        "There is no backup target: add one in Settings.",
    )
    assert _refused("chat.backup", chat="none") == (404, "There is no chat none.")


def test_a_resting_chat_is_deleted_with_all_it_kept_and_a_going_one_never(
    held: _Chats, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hmz.runtime.epic

    held_elsewhere: set[Path] = set()

    def going(at: Path) -> bool:
        return at in held_elsewhere

    monkeypatch.setattr(hmz.runtime.epic, "going", going)
    swept: list[tuple[str, set[str]]] = []

    def sweeps(workspace: str, held: set[str]) -> None:
        swept.append((workspace, held))

    monkeypatch.setattr(hosts, "swept", sweeps)
    worktree = tmp_path / "envs" / "worktrees" / "x"
    worktree.mkdir(parents=True)
    made: dict[str, Path] = {}
    for name in ("c1", "c2", "c3"):
        made[name] = tmp_path / "chats" / "-w" / name
        (made[name] / "sessions" / "claude").mkdir(parents=True)
        (made[name] / "chat.jsonl").write_text("{}\n")
    held.held = [
        _ran("c1", at=made["c1"], workdir=str(worktree)),
        _ran("c2", at=made["c2"], how=""),
        _ran("c3", at=made["c3"], how=""),
    ]
    _hosts(held)["x"] = _status(chat="c2")
    held_elsewhere.add(made["c3"])

    for name in ("c2", "c3"):
        assert _refused("chat.delete", chat=name) == (
            409,
            f"Chat {name} has a turn open; delete it once it is done.",
        )
    assert _refused("chat.delete", chat="none") == (404, "There is no chat none.")
    assert all(one.is_dir() for one in made.values())
    assert swept == []

    assert _call("chat.delete", chat="c1") == {}

    # Its workspace is swept, which removes the directory of a folderless one alone, where
    # no host stands in it: the hosts standing are said with it.
    assert swept == [(WORKSPACE, {WORKSPACE})]

    # Its record and the sessions kept beside it; the worktree it worked in stays.
    assert not made["c1"].exists()
    assert (made["c2"].is_dir(), made["c3"].is_dir()) == (True, True)
    assert worktree.is_dir()


# ------------------------------------------------------------------ a harness's own sessions


def _found(harness: str, ident: str, **said: Any) -> Any:
    """A harness session, as `hmz.runtime.doing.adopting` finds one."""
    found: dict[str, Any] = {
        "harness": harness,
        "ident": ident,
        "title": f"said in {ident}",
        "began": "2026-01-01T00:00:00Z",
        "updated": "2026-01-02T00:00:00+00:00",
        "cwd": "/w",
        "model": "opus",
        "log": Path("/homes") / harness / ident,
    }
    return SimpleNamespace(**found | said)


class _Adopting:
    """`hmz.runtime.doing.adopting`, as far as `chat.harness.*` asks it."""

    CARRIED = ("claude", "codex")

    def __init__(self) -> None:
        self.found: list[Any] = []
        self.asked: list[tuple[Path, set[tuple[str, str]]]] = []
        self.adopted: list[tuple[str, Path, str]] = []
        self.refuses = ""

    def listed(self, workspace: Path, owned: set[tuple[str, str]]) -> list[Any]:
        self.asked.append((workspace, owned))
        return [one for one in self.found if (one.harness, one.ident) not in owned]

    def said(self, one: Any) -> list[dict[str, Any]]:
        return [{"key": f"{one.harness}:{one.ident}", "agent": "", "actions": []}]

    def adopt(self, one: Any, workspace: Path, agent: str = "") -> Path:
        if self.refuses:
            raise ValueError(self.refuses)
        self.adopted.append((one.ident, workspace, agent))
        return Path("/chats/-w/20260103-new")


@pytest.fixture
def harnessed(monkeypatch: pytest.MonkeyPatch, held: _Chats) -> _Adopting:
    """What each harness had of its own, as a test says it, beside the chats and no epic."""
    import hmz.runtime.doing

    fake = _Adopting()
    monkeypatch.setattr(hmz.runtime.doing, "adopting", fake, raising=False)
    monkeypatch.setattr(runs, "RUNS", _Chats())
    return fake


def test_the_harness_sessions_of_a_workspace_are_paged_as_rows(
    held: _Chats, harnessed: _Adopting
) -> None:
    del held
    harnessed.found = [_found("codex", "x-1"), _found("opencode", "o-1", title="")]

    said = _call("chat.harness.list", workspace="/w")

    assert said == {
        "sessions": [
            {
                "id": "x-1",
                "harness": "codex",
                "title": "said in x-1",
                "workspace": WORKSPACE,
                "model": "opus",
                "began": "2026-01-01T00:00:00Z",
                "updated": "2026-01-02T00:00:00+00:00",
                "continuable": True,
            },
            {
                "id": "o-1",
                "harness": "opencode",
                "title": "",
                "workspace": WORKSPACE,
                "model": "opus",
                "began": "2026-01-01T00:00:00Z",
                "updated": "2026-01-02T00:00:00+00:00",
                # Listed and read, and not carried on: its row says so.
                "continuable": False,
            },
        ],
        "total": 2,
        "offset": 0,
        "limit": 50,
    }
    paged = _call("chat.harness.list", workspace="/w", offset=1, limit=1)
    assert ([one["id"] for one in paged["sessions"]], paged["total"]) == (["o-1"], 2)
    # Asked of the workspace as it was said, which is what a harness wrote down.
    assert harnessed.asked[0][0] == Path("/w")
    assert _refused("chat.harness.list", workspace="w") == (
        400,
        "Say the workspace as a whole path, not w.",
    )


def test_what_a_chat_or_an_epic_opened_is_no_harness_session(
    held: _Chats, harnessed: _Adopting
) -> None:
    harnessed.found = [_found("claude", "c-1"), _found("claude", "c-2")]
    opened = SimpleNamespace(backend="claude", ident="c-1")
    # A chat of another workspace, an Ai-chan conversation among them, owns its sessions too.
    held.held = [_ran("c1", workspace="/elsewhere", sessions=(opened,))]

    said = _call("chat.harness.list", workspace="/w")

    assert [one["id"] for one in said["sessions"]] == ["c-2"]
    assert harnessed.asked[0][1] == {("claude", "c-1")}
    assert (
        _refused("chat.harness.get", workspace="/w", harness="claude", session="c-1")[0]
        == 404
    )


def test_a_harness_session_is_read_with_what_was_said_where_asked(
    held: _Chats, harnessed: _Adopting
) -> None:
    del held
    harnessed.found = [_found("claude", "c-1")]
    named = {"workspace": "/w", "harness": "claude", "session": "c-1"}

    assert "trace" not in _call("chat.harness.get", **named)
    whole = _call("chat.harness.get", **named, trace=True)

    assert (whole["id"], whole["harness"]) == ("c-1", "claude")
    assert whole["trace"] == [{"key": "claude:c-1", "agent": "", "actions": []}]
    assert _refused("chat.harness.get", **named | {"harness": "codex"}) == (
        404,
        "There is no codex session c-1 of /w.",
    )


def test_a_harness_session_is_adopted_as_a_chat_or_refused_saying_why(
    held: _Chats, harnessed: _Adopting
) -> None:
    del held
    harnessed.found = [_found("claude", "c-1"), _found("opencode", "c-1")]
    named = {"workspace": "/w", "harness": "claude", "session": "c-1"}

    assert _call("chat.harness.adopt", **named) == {"chat": "20260103-new"}
    assert _call("chat.harness.adopt", **named, agent="claude/sonnet") == {
        "chat": "20260103-new"
    }
    assert harnessed.adopted == [
        ("c-1", Path("/w"), ""),
        ("c-1", Path("/w"), "claude/sonnet"),
    ]

    harnessed.refuses = (
        "c-1 does not say the model it ran on: name an agent for the chat"
    )
    assert _refused("chat.harness.adopt", **named) == (
        409,
        "C-1 does not say the model it ran on: name an agent for the chat.",
    )
    # One that is listed, of a harness that carries none on.
    assert _refused("chat.harness.adopt", **named | {"harness": "opencode"}) == (
        409,
        "A session of opencode cannot be continued in a chat.",
    )
    assert len(harnessed.adopted) == 2
    assert _refused("chat.harness.adopt", **named | {"session": "c-0"})[0] == 404
