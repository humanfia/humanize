"""Ai-chan conversations over JSON-RPC, and the reach the daemon holds her scoped link to.

A daemon of the test's own makes, lists and forgets conversations (Section 4.22 of daemon.md);
each conversation's host runs a stand-in for the flow `ai_chan`, which writes down the scoped
link it was told of and waits. The test then reaches the daemon over that link as Ai-chan would,
and is refused 403 as Section 4.21.3 states, in its order, and answered lists cut to the scope.
"""

from __future__ import annotations

import re
import socket
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.reach.pipes import SocketPipe
from hmz.rpc import PROTOCOL, Peer, RpcError
from hmz.runtime.epic import every
from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_daemon import WAITS, hosting, until, written

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(120),
]

#: Stands in for `ai_chan`: writes down the link it was told of, and waits.
_AI_CHAN = """
import asyncio
import os
from pathlib import Path

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    ai_chan: Agent


class Envs(EnvCollection):
    scratch: LocalEnv


class Params(FlowParams):
    id: int = 0
    scope: str = ""
    workspace: str = ""
    epic: str = ""
    preset: str = ""


@flow(agents=Agents, envs=Envs, params=Params, name="ai_chan")
async def ai_chan(task, *, agents, envs, params, ctx):
    told = Path(os.environ["HUMANIZE_HOME"]) / f"link-{params.id}"
    told.write_text(os.environ.get("HUMANIZE_AICHAN_LINK", ""))
    while True:
        await asyncio.sleep(0.05)
"""


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Path]]:
    """The test's project, another workspace, and a daemon whose `ai:` hosts run the stand-in."""
    at = install(tmp_path, monkeypatch)
    other = tmp_path / "other"
    other.mkdir()
    flow = tmp_path / "fakes" / "ai_chan"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_AI_CHAN)
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "sitecustomize.py").write_text(
        "import sys\n"
        "if 'hmz.daemon.detached' in sys.orig_argv:\n"
        "    from hmz.daemon import reach\n"
        f"    reach.FLOW = {str(flow)!r}\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(custom))
    with hosting():
        yield at, other


def _session(path: Path, kind: str = "cli") -> Peer:
    """A session over a socket, which has said hello as `kind`."""
    one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    one.connect(str(path))
    peer = Peer(SocketPipe(one, trusted=True), name="test-session")
    peer.call(
        "session.hello",
        {"protocol": PROTOCOL, "client": {"name": "test", "kind": kind}},
        timeout=10,
    )
    return peer


def _refused(peer: Peer, method: str, params: dict[str, Any] | None = None) -> str:
    """What a call was refused 403 with."""
    with pytest.raises(RpcError) as refused:
        peer.call(method, params or {}, timeout=30)
    assert refused.value.code == 403, refused.value.message
    return refused.value.message


def _epics(peer: Peer) -> set[str]:
    return {one["name"] for one in peer.call("runs.list", {}, timeout=30)["runs"]}


def _workspaces(peer: Peer) -> dict[str, int]:
    """How many epics each workspace listed has, by its path."""
    listed = peer.call("workspaces.list", {}, timeout=30)["workspaces"]
    return {one["path"]: one["epics"] for one in listed}


def test_a_workspace_scoped_ai_chan_is_held_to_her_reach(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    project, other = workspace
    written(project, "waits", WAITS)
    written(other, "waits", WAITS)
    ours = daemon.attach("sdk", workspace=project)
    theirs = daemon.attach("sdk", workspace=other)
    try:
        ours.start("./waits", "ours", budget={"cost": 1})
        theirs.start("./waits", "theirs", budget={"cost": 1})
        user = _session(where.at() / where.SOCKET)
        mine, elsewhere = where.workspace(project), where.workspace(other)

        made = user.call(
            "aichan.create",
            {
                "scope": "workspace",
                "workspace": str(project),
                "nous": AGENT,
                "task": "hi",
            },
            timeout=60,
        )
        assert (made["id"], made["workspace"]) == (1, mine)
        slot = made["slot"]
        assert slot.startswith("ai:")
        (listed,) = user.call("aichan.list", {}, timeout=30)["conversations"]
        assert {key: listed[key] for key in ("id", "scope", "slot", "preset")} == {
            "id": 1,
            "scope": "workspace",
            "slot": slot,
            "preset": "read-only",
        }
        assert listed["state"] in ("running", "waiting")
        assert listed["title"] == "hi"

        # Her host was told its scoped link, which only she says hello on.
        link = where.at() / f"ai-{slot.removeprefix('ai:')}.sock"
        told = tmp_path / "humanize-home" / "link-1"
        assert until(lambda: told.exists() and told.read_text() == str(link))
        assert link.stat().st_mode & 0o777 == 0o600
        with pytest.raises(RpcError, match=r"Only Ai-chan says hello as ai-chan\."):
            _session(where.at() / where.SOCKET, "ai-chan")
        with pytest.raises(RpcError, match=r"This link is Ai-chan.s\."):
            _session(link)
        ai = _session(link, "ai-chan")

        # Each refusal, and the first of them that holds where more than one does.
        assert _refused(ai, "devices.list") == "Ai-chan cannot call devices.list."
        assert _refused(ai, "aichan.list") == "Ai-chan cannot call aichan.list."
        assert (
            _refused(ai, "aichan.rename", {"id": 1, "title": "mine"})
            == "Ai-chan cannot call aichan.rename."
        )
        assert (
            _refused(ai, "hosts.stop", {"workspace": str(other), "slot": slot})
            == "Ai-chan cannot reach an Ai-chan conversation."
        )
        assert (
            _refused(ai, "hosts.stop", {"workspace": str(other)})
            == f"hosts.stop is out of Ai-chan's scope: the host of {elsewhere}."
        )
        assert (
            _refused(ai, "flows.list", {"workspace": str(other)})
            == f"flows.list is out of Ai-chan's scope: the workspace {elsewhere}."
        )
        assert (
            _refused(ai, "settings.set", {"workspace": str(project), "details": True})
            == "settings.set is out of Ai-chan's scope: the daemon."
        )
        assert (
            _refused(ai, "hosts.stop", {"workspace": str(project)})
            == "Ai-chan is read-only, and hosts.stop changes things."
        )
        # A side conversation of an agent and a directory she chooses would be confined by
        # nothing of hers: it is not opened, on a host she reaches or any other.
        sub = ai.call("epic.attach", {"workspace": str(project)}, timeout=30)["sub"]
        assert (
            _refused(ai, "epic.aside", {"sub": sub, "runs": AGENT, "cwd": str(other)})
            == "Ai-chan cannot call epic.aside."
        )
        assert ai.call("epic.detach", {"sub": sub}, timeout=30) == {}
        # What she reaches and only reads, she is answered.
        assert ai.call("hosts.status", {"workspace": str(project)}, timeout=30)
        assert ai.call("flows.list", {"workspace": str(project)}, timeout=30)

        # Lists cut to her workspace, her own conversation left out.
        assert {
            (one["workspace"], one["slot"])
            for one in user.call("hosts.list", {}, timeout=30)["held"]
        } == {(mine, ""), (elsewhere, ""), (mine, slot)}
        assert [
            (one["workspace"], one["slot"])
            for one in ai.call("hosts.list", {}, timeout=30)["held"]
        ] == [(mine, "")]
        assert [
            one["path"]
            for one in ai.call("workspaces.list", {}, timeout=30)["workspaces"]
        ] == [mine]
        assert until(lambda: len(every()) == 3)
        ours_epic = ours.asked({"do": "status"})["epic"]
        theirs_epic = theirs.asked({"do": "status"})["epic"]
        # Her own epic is an epic, and on nobody's list of them: not hers, not the user's.
        assert until(lambda: _epics(ai) == {ours_epic})
        assert ai.call("runs.list", {}, timeout=30)["total"] == 1
        assert _epics(user) == {ours_epic, theirs_epic}
        assert user.call("runs.list", {}, timeout=30)["total"] == 2

        # An epic is hers by where it was run, not by the workspace the call names.
        for method in ("btw.list", "btw.ask"):
            asked = (
                {"to": "nobody/1", "aside": "x", "question": "?"}
                if method == "btw.ask"
                else {}
            )
            assert (
                _refused(
                    ai,
                    method,
                    {"workspace": str(project), "epic": theirs_epic, **asked},
                )
                == f"{method} is out of Ai-chan's scope: the epic {theirs_epic}."
            )
            assert (
                _refused(
                    ai, method, {"workspace": str(other), "epic": ours_epic, **asked}
                )
                == f"{method} is out of Ai-chan's scope: the workspace {elsewhere}."
            )
        for epic in (ours_epic, ""):
            assert ai.call(
                "btw.list", {"workspace": str(project), "epic": epic}, timeout=30
            ) == {"asides": []}

        # Nor is anything of hers a workspace's: her epics, her hosts, her own directory.
        user.call("aichan.create", {"scope": "daemon", "nous": AGENT, "task": "all"})
        assert until(lambda: len(every()) == 4)
        assert _epics(user) == {ours_epic, theirs_epic}
        assert _workspaces(user) == {mine: 1, elsewhere: 1}

        # Forgotten: her host goes, her link with it, and her scratch directory.
        assert user.call("aichan.forget", {"id": 1}, timeout=30) == {}
        assert user.call("aichan.forget", {"id": 2}, timeout=30) == {}
        assert user.call("aichan.list", {}, timeout=30) == {"conversations": []}
        assert until(lambda: not link.exists())
        assert until(lambda: ai.closed)
        with pytest.raises(RpcError, match=r"There is no Ai-chan #1\."):
            user.call("aichan.forget", {"id": 1}, timeout=30)
        # Her epics are kept, and stay off both lists.
        assert len(every()) == 4
        assert _epics(user) == {ours_epic, theirs_epic}
        assert _workspaces(user) == {mine: 1, elsewhere: 1}
        user.close()
    finally:
        ours.stop()
        theirs.stop()
        ours.close()
        theirs.close()


#: A flow whose module, once loaded, writes down the process that loaded it.
_MARKS = """
import os
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

Path({marker!r}).write_text(str(os.getpid()))


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, name="marks")
async def marks(task, *, agents, envs, params, ctx):
    pass
"""


def test_a_read_only_ai_chan_has_no_flow_loaded_by_its_path(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    project, other = workspace
    daemon.start()
    user = _session(where.at() / where.SOCKET)

    def made(preset: str) -> tuple[Peer, Path]:
        """Ai-chan's session of a new conversation of the project, and its scratch directory."""
        said = user.call(
            "aichan.create",
            {
                "scope": "workspace",
                "workspace": str(project),
                "nous": AGENT,
                "preset": preset,
                "task": "hi",
            },
            timeout=60,
        )
        link = where.at() / f"ai-{said['slot'].removeprefix('ai:')}.sock"
        assert until(link.exists)
        (machine,) = (tmp_path / "humanize-home" / "ai").iterdir()
        return _session(link, "ai-chan"), machine / str(said["id"])

    # Her scratch directory is hers to write, whatever her preset: a flow she wrote there is
    # not loaded, which would run it as the daemon, outside her confinement.
    ai, scratch = made("read-only")
    marker = other / "loaded-by"
    written(scratch, "marks", _MARKS.format(marker=str(marker)))
    at = str(scratch / "marks")
    # However a path is spelled, and a repository too: what the loader strips is not a name.
    for flow in (
        at,
        "~/marks",
        "./marks",
        f" {at}",
        f"\t{at}:marks",
        f" git+file://{at}",
    ):
        assert (
            _refused(ai, "flows.check", {"workspace": str(project), "flow": flow})
            == "Ai-chan is read-only, and flows.check changes things."
        )
    assert not marker.exists()
    # A flow by its name is found only among those on offer, and is still checked.
    with pytest.raises(RpcError) as none:
        ai.call("flows.check", {"workspace": str(project), "flow": "marks"}, timeout=30)
    assert none.value.code == 400, none.value.message
    assert not marker.exists()

    # One who may change her workspace may start an epic of that flow there, and so check it.
    full, _ = made("danger-full-access")
    with pytest.raises(RpcError) as checked:
        full.call(
            "flows.check",
            {"workspace": str(project), "flow": str(scratch / "marks")},
            timeout=30,
        )
    assert checked.value.code == 400, checked.value.message
    assert "requires a budget" in checked.value.message
    assert marker.exists()
    user.close()


def test_an_epic_scoped_ai_chan_reaches_her_epic_alone(
    workspace: tuple[Path, Path],
) -> None:
    project, _ = workspace
    written(project, "waits", WAITS)
    with daemon.attach("sdk", workspace=project) as ours:
        ours.start("./waits", "ours", budget={"cost": 1})
        assert until(lambda: ours.asked({"do": "status"})["epic"])
        epic = ours.asked({"do": "status"})["epic"]
        user = _session(where.at() / where.SOCKET)
        mine = where.workspace(project)
        made = user.call(
            "aichan.create",
            {
                "scope": "epic",
                "workspace": str(project),
                "epic": epic,
                "nous": AGENT,
                "preset": "danger-full-access",
                "task": "look",
            },
            timeout=60,
        )
        link = where.at() / f"ai-{made['slot'].removeprefix('ai:')}.sock"
        assert until(link.exists)
        ai = _session(link, "ai-chan")
        assert (
            _refused(ai, "flows.list", {"workspace": str(project)})
            == f"flows.list is out of Ai-chan's scope: the workspace {mine}."
        )
        assert (
            _refused(ai, "runs.get", {"name": "nothing-like-it"})
            == "runs.get is out of Ai-chan's scope: the epic nothing-like-it."
        )
        assert ai.call("runs.get", {"name": epic}, timeout=30)["name"] == epic
        assert ai.call("hosts.status", {"workspace": str(project)}, timeout=30)
        assert [
            (one["workspace"], one["slot"])
            for one in ai.call("hosts.list", {}, timeout=30)["held"]
        ] == [(mine, "")]
        assert ai.call("workspaces.list", {}, timeout=30)["workspaces"] == []
        ai.close()
        user.call("aichan.forget", {"id": made["id"]}, timeout=30)
        user.close()
        ours.stop()


def test_a_conversation_is_made_only_as_said(workspace: tuple[Path, Path]) -> None:
    project, _ = workspace
    with daemon.attach("sdk", workspace=project):
        user = _session(where.at() / where.SOCKET)

        def refused(**said: Any) -> str:
            with pytest.raises(RpcError) as why:
                user.call("aichan.create", {"task": "hi", **said}, timeout=30)
            return f"{why.value.code} {why.value.message}"

        assert refused(scope="room") == (
            "400 An Ai-chan's scope is daemon, workspace or epic."
        )
        assert refused(scope="epic") == "400 A epic scope names its workspace."
        assert refused(scope="daemon", workspace=str(project)) == (
            "400 A daemon scope names no workspace and no epic."
        )
        assert refused(scope="workspace", workspace=str(project), epic="e") == (
            "400 A workspace scope names no epic."
        )
        assert refused(scope="epic", workspace=str(project)) == (
            "400 An epic scope names its epic."
        )
        assert refused(scope="daemon", preset="workspace-write") == (
            "400 An Ai-chan's preset is read-only or danger-full-access."
        )
        assert refused(scope="daemon") == (
            "400 Name Ai-chan's nous: the ai_chan setting names none."
        )
        assert refused(scope="daemon", nous="no/such:thing:at:all") == (
            "400 no/such:thing:at:all is not a nous or an agent spec."
        )
        assert refused(scope="daemon", nous=AGENT, task=" ") == (
            "400 Tell Ai-chan something to start with."
        )
        assert refused(
            scope="epic", workspace=str(project), epic="none", nous=AGENT
        ) == (f"404 There is no epic none in {where.workspace(project)}.")
        # Her network is hers always, and her title what was first said: neither is said.
        for unsaid in ("network", "title"):
            with pytest.raises(RpcError, match=rf"aichan\.create takes no {unsaid}\."):
                user.call(
                    "aichan.create",
                    {"scope": "daemon", "nous": AGENT, "task": "hi", unsaid: "on"},
                    timeout=30,
                )
        assert user.call("aichan.list", {}, timeout=30) == {"conversations": []}
        # None was made: no nous is remembered as the one last used.
        assert user.call("settings.get", {}, timeout=30)["ai_chan"] == ""

        # A daemon scope lives in the daemon's own directory under the home.
        made = user.call(
            "aichan.create",
            {"scope": "daemon", "nous": AGENT, "task": "hi"},
            timeout=60,
        )
        assert "/humanize-home/ai/" in made["workspace"]
        # Its nous is the one the next conversation is made with, where it names none.
        assert user.call("settings.get", {}, timeout=30)["ai_chan"] == AGENT
        (listed,) = user.call("aichan.list", {}, timeout=30)["conversations"]
        assert (listed["latest"], listed["updated"]) == ("hi", listed["created"])
        assert "network" not in listed
        # Titled by what was first said, until it is given another.
        assert listed["title"] == "hi"
        renamed = {"id": made["id"], "title": "  The   plan "}
        assert user.call("aichan.rename", renamed, timeout=30) == {}
        (listed,) = user.call("aichan.list", {}, timeout=30)["conversations"]
        assert (listed["title"], listed["latest"]) == ("The plan", "hi")
        for said, why in (
            (
                {"id": made["id"], "title": " "},
                "A conversation's title says something.",
            ),
            ({"id": 99, "title": "x"}, "There is no Ai-chan #99."),
        ):
            with pytest.raises(RpcError, match=re.escape(why)):
                user.call("aichan.rename", said, timeout=30)
        again = user.call("aichan.create", {"scope": "daemon", "task": "x"}, timeout=60)
        assert [
            one["nous"]
            for one in user.call("aichan.list", {}, timeout=30)["conversations"]
        ] == [AGENT, AGENT]
        user.call("aichan.forget", {"id": again["id"]}, timeout=30)
        with pytest.raises(RpcError, match="There is no Ai-chan conversation ai:0"):
            user.call(
                "hosts.open",
                {"workspace": made["workspace"], "slot": "ai:0"},
                timeout=30,
            )
        user.call("aichan.forget", {"id": made["id"]}, timeout=30)
        user.close()
