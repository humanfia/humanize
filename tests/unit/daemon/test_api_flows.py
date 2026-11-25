"""`hmz.daemon.api`: the flows family -- flows, flowverses, workspaces, paths and notices.

Each family against stand-ins for Humanize's one object and for a call: what it answers, and
what it refuses with which code and sentence.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, Field

from hmz.daemon.api import flows, flowverses, notices, paths, workspaces
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Callable

#: The OpenRPC document the families are served against.
OPENRPC = Path(__file__).resolve().parents[3] / "protocol" / "openrpc.json"


class Peer:
    """The end a call arrived at, as far as a family reads it."""

    closed = False


def _call(**params: Any) -> Any:
    return SimpleNamespace(params=params, peer=Peer())


def test_each_family_serves_every_method_the_document_lists_for_it() -> None:
    listed = json.loads(OPENRPC.read_text())["methods"]
    for family in (flows, flowverses, workspaces, paths, notices):
        prefix = family.__name__.rpartition(".")[2]
        named = {
            one["name"]
            for one in listed
            if one["name"].startswith(f"{prefix}.") and not one.get("x-notification")
        }
        assert set(family.METHODS) == named


def test_a_workspace_is_a_whole_path_to_a_directory(tmp_path: Path) -> None:
    assert workspaces.place(str(tmp_path)) == tmp_path.resolve()
    with pytest.raises(RpcError) as relative:
        workspaces.place("here")
    assert relative.value.code == Code.REFUSED
    assert relative.value.message == "Say the workspace as a whole path, not here."
    with pytest.raises(RpcError) as missing:
        workspaces.place(str(tmp_path / "gone"))
    assert missing.value.code == Code.NOT_FOUND
    assert missing.value.message == f"There is no directory {tmp_path / 'gone'}."
    assert workspaces.place(str(tmp_path / "gone"), made=True).name == "gone"


def test_workspaces_list_here_then_going_then_epics_then_written(
    tmp_path: Path,
) -> None:
    here, going, ran, written = (tmp_path / one for one in "hgrw")
    for one in (here, going, ran):
        one.mkdir()
    epics = [
        SimpleNamespace(workspace=str(ran), began="2026-02-01"),
        SimpleNamespace(workspace=str(ran), began="2026-01-01"),
        SimpleNamespace(workspace=str(here), began="2025-12-01"),
    ]

    rows = workspaces.listed(
        str(here.resolve()),
        epics,
        [str(going.resolve())],
        [str(written), str(ran.resolve())],
    )

    assert [one["path"] for one in rows] == [
        str(here.resolve()),
        str(going.resolve()),
        str(ran.resolve()),
        str(written),
    ]
    by = {one["path"]: one for one in rows}
    assert by[str(ran.resolve())]["epics"] == 2
    assert by[str(ran.resolve())]["last"] == "2026-02-01"
    assert by[str(going.resolve())]["running"] is True
    assert by[str(here.resolve())]["here"] is True
    assert by[str(written)]["there"] is False


def test_a_directory_lists_folders_first_and_one_not_there_is_not_found(
    tmp_path: Path,
) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "a.txt").write_text("")
    (tmp_path / ".hid").mkdir()

    said = paths.METHODS["paths.list"](_call(at=str(tmp_path), files=True))
    assert [one["name"] for one in said["entries"]] == ["b", "a.txt"]
    assert said["more"] == 0
    with pytest.raises(RpcError) as missing:
        paths.listed(str(tmp_path / "gone"), files=False, hidden=False)
    assert missing.value.code == Code.NOT_FOUND
    completed = paths.METHODS["paths.complete"](_call(typed=f"{tmp_path}/"))
    assert completed == {"paths": [f"{tmp_path}/b/"]}


#: The one flowverse a stand-in holds.
THEIRS = SimpleNamespace(name="theirs", fetched=True, fixed=False)


def _whence(*_: object) -> str:
    return "https://example.com/theirs"


def _edited(_: object) -> bool:
    return False


def _find(name: str) -> object:
    return THEIRS if name == "theirs" else None


def _verses(*, raising: Exception | None = None) -> Any:
    """Humanize, holding one flowverse `theirs` whose every change does as `raising` says."""
    one = THEIRS

    def changes(*_: Any) -> Any:
        if raising is not None:
            raise raising
        return one

    verses = SimpleNamespace(
        all=lambda: [one],
        installed=list,
        updates=list,
        whence=_whence,
        edited=_edited,
        find=_find,
        add=changes,
        fetch=changes,
        remove=changes,
    )
    return SimpleNamespace(flows=SimpleNamespace(verses=verses))


def test_a_flowverse_change_waits_for_no_epic_and_says_what_it_did() -> None:
    hmz = _verses()

    fetched = flowverses.changed(hmz, "fetch", {"name": "theirs"}, running=True)
    assert fetched["said"] == "fetched theirs"
    assert [one["name"] for one in fetched["verses"]] == ["theirs"]
    with pytest.raises(RpcError) as busy:
        flowverses.changed(hmz, "remove", {"name": "theirs"}, running=True)
    assert busy.value.code == Code.CONFLICT
    assert busy.value.message == "An epic is running: flows change once none is."
    with pytest.raises(RpcError) as refused:
        flowverses.changed(
            _verses(raising=ValueError("not a URL")), "add", {"url": "x"}, running=False
        )
    assert (refused.value.code, refused.value.message) == (Code.REFUSED, "not a URL")
    with pytest.raises(RpcError) as missing:
        flowverses.index(hmz, "nowhere")
    assert missing.value.code == Code.NOT_FOUND
    assert missing.value.message == "There is no flowverse nowhere."


def _flows(*names: str) -> Any:
    """Humanize for a workspace offering `names`, each declaring one required agent role."""
    role = SimpleNamespace(name="coder", required=True, auto=False)

    def declared(_: str) -> object:
        return SimpleNamespace(agents=[role])

    def entry(said: str) -> str:
        if said != "smart":
            raise ValueError(f"{said!r} is no nous written down")
        return "claude/opus"

    return SimpleNamespace(
        workspace="/w",
        flows=SimpleNamespace(
            all=lambda: [SimpleNamespace(name=one) for one in names],
            declared=declared,
        ),
        nous=SimpleNamespace(entry=entry),
        backups=SimpleNamespace(targets=list),
    )


def test_a_flow_not_on_offer_is_not_found() -> None:
    with pytest.raises(RpcError) as missing:
        flows.offered(_flows("chat"), "./mine")
    assert missing.value.code == Code.NOT_FOUND
    assert missing.value.message == "./mine is not a flow on offer here."


def _offering(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Stands in for Humanize: every workspace offers `theirs`, `@local/mine` and `@user/own`."""
    import hmz.runtime

    made: list[Path] = []

    def built(at: Path) -> Any:
        made.append(at)
        offers = [
            SimpleNamespace(whose=whose, name=name, about="")
            for whose, name in (
                ("official", "theirs"),
                ("local", "@local/mine"),
                ("user", "@user/own"),
            )
        ]
        return SimpleNamespace(
            workspace=str(at),
            flows=SimpleNamespace(all=lambda: offers, running=list),
            settings=SimpleNamespace(flow="theirs"),
        )

    monkeypatch.setattr(hmz.runtime, "Hmz", built, raising=False)
    monkeypatch.setattr(hmz.runtime, "Holding", built, raising=False)
    return made


def test_flows_are_listed_without_a_workspace_and_for_one_since_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = _offering(monkeypatch)
    gone = tmp_path / "gone"

    bare = flows.METHODS["flows.list"](_call())
    # No project is named: its own flows are not on offer, and the home's are the user's.
    assert [one["name"] for one in bare["flows"]] == ["theirs", "@user/own"]
    assert (bare["flow"], bare["running"]) == ("theirs", [])
    with pytest.raises(RpcError) as local:
        flows.METHODS["flows.get"](_call(name="@local/mine"))
    assert local.value.message == "@local/mine is not a flow on offer here."
    removed = flows.METHODS["flows.list"](_call(workspace=str(gone)))
    assert [one["whose"] for one in removed["flows"]] == ["official", "local", "user"]
    assert made == [Path.home(), Path.home(), gone.resolve()]
    with pytest.raises(RpcError) as relative:
        flows.METHODS["flows.list"](_call(workspace="here"))
    assert relative.value.code == Code.REFUSED


@pytest.mark.parametrize("method", ["flows.setup", "flows.fork", "flows.check"])
def test_a_flow_is_set_up_copied_and_checked_only_where_the_directory_is(
    method: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = _offering(monkeypatch)

    with pytest.raises(RpcError) as missing:
        flows.METHODS[method](_call(workspace=str(tmp_path / "gone"), flow="theirs"))
    assert missing.value.code == Code.NOT_FOUND
    assert missing.value.message == f"There is no directory {tmp_path / 'gone'}."
    assert made == []


def test_a_flows_params_carry_a_title_only_where_the_flow_wrote_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Params(BaseModel):
        rounds: int = Field(default=3, title="Review rounds", description="how many")
        focus: str = "tests"

    class Kept:
        """A workspace that has run nothing yet."""

        def agents(self, _: str) -> dict[str, Any]:
            return {}

        def __getattr__(self, _: str) -> Callable[[str], None]:
            return lambda _flow: None

    def opened(_: object) -> object:
        return SimpleNamespace(settings=Kept())

    def declared(_: str) -> object:
        return SimpleNamespace(
            ref="mine",
            description="",
            resumable=False,
            agents=[],
            envs=[],
            params=Params,
        )

    monkeypatch.setattr("hmz.runtime.Hmz", opened)
    hmz = SimpleNamespace(
        workspace="/w",
        flows=SimpleNamespace(
            all=lambda: [SimpleNamespace(name="mine")], declared=declared
        ),
        installed=list,
    )

    fields = flows.offered(hmz, "mine")["params"]["properties"]

    assert fields["rounds"]["title"] == "Review rounds"
    assert fields["rounds"]["description"] == "how many"
    assert "title" not in fields["focus"]


@pytest.mark.parametrize(
    ("said", "sentence"),
    [
        (
            {"flow": "loop", "agents": "coder"},
            "agents is an object of agents as -a spells them.",
        ),
        (
            {"flow": "loop", "agents": {"coder": "nothing"}},
            "coder is not given an agent as -a spells one: nothing.",
        ),
        ({"flow": "loop"}, "loop needs an agent for coder."),
        (
            {"flow": "loop", "agents": {"coder": "claude/opus"}},
            "loop needs at least one limit on what it may spend.",
        ),
        # A flow named chat is a flow like any other, with a budget like any other's.
        (
            {"flow": "chat", "agents": {"coder": "claude/opus"}},
            "chat needs at least one limit on what it may spend.",
        ),
    ],
)
def test_a_set_up_that_cannot_run_is_refused(
    said: dict[str, Any], sentence: str
) -> None:
    with pytest.raises(RpcError) as refused:
        flows.remembers(_flows("loop", "chat"), said)
    assert (refused.value.code, refused.value.message) == (Code.REFUSED, sentence)


def test_a_set_up_takes_a_virtual_nous_as_an_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept: dict[str, Any] = {}

    def remember(flow: str, agents: dict[str, Any], *_: object, **__: object) -> None:
        kept[flow] = {role: tuple(runs) for role, runs in agents.items()}

    def opened(_: object) -> object:
        return SimpleNamespace(settings=SimpleNamespace(remember=remember))

    monkeypatch.setattr("hmz.runtime.Hmz", opened)
    said = {"flow": "loop", "agents": {"coder": "smart"}, "budget": {"cost": 1.0}}

    flows.remembers(_flows("loop"), said)()

    # As `-a` spells it and `epic.start` takes it: the name alone, no harness in front.
    assert kept == {"loop": {"coder": ("smart", "")}}


def test_a_check_reaches_no_other_machine_and_takes_specs_as_text() -> None:
    hmz = _flows("chat")
    with pytest.raises(RpcError) as fetched:
        flows.checked(hmz, {"flow": "git+https://example.com/flows#loop"})
    assert fetched.value.code == Code.REFUSED
    with pytest.raises(RpcError) as untyped:
        flows.checked(hmz, {"flow": "chat", "agents": {"assistant": 3}})
    assert untyped.value.message == "agents is each role's spec, as text."
    with pytest.raises(RpcError) as targets:
        flows.checked(hmz, {"flow": "chat", "backup": [1]})
    assert targets.value.message == "backup is a list of backup target names."


def test_a_fork_refused_says_why() -> None:
    def fork(_: str) -> str:
        raise ValueError("loop is yours already")

    hmz = SimpleNamespace(flows=SimpleNamespace(fork=fork))
    with pytest.raises(RpcError) as refused:
        flows.forked(hmz, "loop")
    assert (refused.value.code, refused.value.message) == (
        Code.REFUSED,
        "loop is yours already",
    )

    def forks(flow: str) -> str:
        return f"/w/.hmz/flows/{flow}"

    hmz.flows.fork = forks
    assert flows.forked(hmz, "loop") == {
        "said": "copied loop to /w/.hmz/flows/loop",
        "at": "/w/.hmz/flows/loop",
    }


def test_notices_are_read_after_a_whole_number() -> None:
    def since(after: int) -> list[dict[str, int]]:
        return [{"id": after + 1}]

    kept: Any = SimpleNamespace(since=since, last=7)

    assert notices.listed(kept, "3") == {"notices": [{"id": 4}], "last": 7}
    assert notices.listed(kept) == {"notices": [{"id": 1}], "last": 7}
    for after in ("x", -1):
        with pytest.raises(RpcError) as refused:
            notices.listed(kept, after)
        assert refused.value.code == Code.REFUSED
        assert refused.value.message == "Say after as a whole number."


def test_a_subscription_not_open_is_unknown() -> None:
    with pytest.raises(RpcError) as unknown:
        notices.METHODS["notices.unsubscribe"](_call(sub="notices-0"))
    assert unknown.value.code == Code.UNKNOWN_SUBSCRIPTION
    assert unknown.value.message == "There is no subscription notices-0."


def _made_for_none(at: str | Path) -> bool:
    """Whether a path is folderless, for a test that keeps such directories under its own."""
    return Path(at).parent.name == "nofolder"


def test_a_folderless_workspace_is_never_listed_and_is_made_again_where_it_went(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.daemon import where

    mine, made = tmp_path / "mine", tmp_path / "nofolder" / "tmp1"
    mine.mkdir()
    made.mkdir(parents=True)
    monkeypatch.setattr(where, "folderless", _made_for_none)
    epics = [
        SimpleNamespace(workspace=str(made), began="2026-02-01"),
        SimpleNamespace(workspace=str(mine), began="2026-01-01"),
    ]

    # Section 4.17.5.6: whatever ran or goes in it, or wrote it down.
    rows = workspaces.listed("", epics, [str(made.resolve())], [str(made.resolve())])
    assert [one["path"] for one in rows] == [str(mine.resolve())]

    # Section 4.5.2: the machine cleans its temporary directory, and it is made again.
    gone = tmp_path / "nofolder" / "tmp2"
    assert workspaces.place(str(gone)) == gone.resolve()
    assert gone.is_dir()
    assert not any(gone.iterdir())
    with pytest.raises(RpcError) as missing:
        workspaces.place(str(tmp_path / "gone"))
    assert missing.value.code == Code.NOT_FOUND
