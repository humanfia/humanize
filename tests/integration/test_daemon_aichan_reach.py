"""Ai-chan conversations over JSON-RPC, and the reach the daemon holds her scoped link to.

A daemon of the test's own makes, lists and forgets conversations (Section 4.22 of daemon.md);
each conversation's host runs a stand-in for the flow `ai_chan`, which writes down the scoped
link it was told of and waits. The test then reaches the daemon over that link as Ai-chan would,
and is refused 403 as Section 4.21.3 states, in its order, and answered lists cut to the scope.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.reach.pipes import SocketPipe
from hmz.rpc import PROTOCOL, Peer, RpcError
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
    network: bool = False


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
        "    from hmz.runtime import flowing\n"
        f"    reach.FLOW = {str(flow)!r}\n"
        # Spends without a budget, as `ai_chan` does (Section 14.4.3 of core.md).
        "    was = flowing.privileged\n"
        "    flowing.privileged = lambda impl: was(impl) or impl.name == 'ai_chan'\n"
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
            _refused(ai, "hosts.stop", {"workspace": str(other), "slot": slot})
            == "Ai-chan cannot reach an Ai-chan conversation."
        )
        assert (
            _refused(ai, "hosts.stop", {"workspace": str(other)})
            == f"hosts.stop is out of Ai-chan's scope: the host  of {elsewhere}."
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
        assert until(lambda: len(_epics(user)) == 3)
        ours_epic = ours.asked({"do": "status"})["epic"]
        # Her own epic is left out once its host has named it, a moment after it starts.
        assert until(lambda: _epics(ai) == {ours_epic})
        assert ai.call("runs.list", {}, timeout=30)["total"] == 1

        # Forgotten: her host goes, her link with it, and her scratch directory.
        assert user.call("aichan.forget", {"id": 1}, timeout=30) == {}
        assert user.call("aichan.list", {}, timeout=30) == {"conversations": []}
        assert until(lambda: not link.exists())
        assert until(lambda: ai.closed)
        with pytest.raises(RpcError, match=r"There is no Ai-chan #1\."):
            user.call("aichan.forget", {"id": 1}, timeout=30)
        user.close()
    finally:
        ours.stop()
        theirs.stop()
        ours.close()
        theirs.close()


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
        assert user.call("aichan.list", {}, timeout=30) == {"conversations": []}

        # A daemon scope lives in the daemon's own directory under the home.
        made = user.call(
            "aichan.create",
            {"scope": "daemon", "nous": AGENT, "task": "hi"},
            timeout=60,
        )
        assert "/humanize-home/ai/" in made["workspace"]
        with pytest.raises(RpcError, match="There is no Ai-chan conversation ai:0"):
            user.call(
                "hosts.open",
                {"workspace": made["workspace"], "slot": "ai:0"},
                timeout=30,
            )
        user.call("aichan.forget", {"id": made["id"]}, timeout=30)
        user.close()
