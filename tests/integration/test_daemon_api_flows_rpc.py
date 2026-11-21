"""The daemon's flows family served over a real socket pair, as a client calls it.

`flows.*`, `paths.*` and `notices.*` registered on an `hmz.rpc.Dispatcher` the way the daemon
discovers them, each family's `METHODS`, and called from a `Peer` at the other end of a
`socket.socketpair()`: the flows and backends of a workspace, `flows.check` refusing what
`hmz exec` refuses in the same words, a directory listed, and notices followed, dropped and
taken up again from the last one heard.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

import hmz.daemon
from hmz.cli import main
from hmz.daemon.api import flows, flowverses, notices, paths, workspaces
from hmz.rpc import PROTOCOL, Call, Code, Dispatcher, Peer, RpcError, admit, hello
from tests.integration.doubles_core import AGENT, MODEL, install, started

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


pytestmark = pytest.mark.usefixtures("loops")

#: An agent run as an account nobody made.
NOBODY = f"claude@nobody/{MODEL}"


class Shut(socket.socket):
    """A stream socket shut down before it is closed, so that closing it wakes its reader."""

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.shutdown(socket.SHUT_RDWR)
        super().close()


class Client:
    """A session with a daemon end serving the flows family, and what it was sent."""

    def __init__(self) -> None:
        self.told: list[dict[str, Any]] = []
        self.heard = threading.Condition()
        daemon_end, client_end = socket.socketpair()
        serving = Dispatcher()
        serving.register("session.hello", self._hello)
        for family in (flows, flowverses, workspaces, paths, notices):
            for name, handler in family.METHODS.items():
                serving.register(name, handler)
        listening = Dispatcher()
        listening.register("notices.event", self._told)
        self.daemon = Peer(Shut(fileno=daemon_end.detach()), serving, name="daemon")
        self.peer = Peer(client_end, listening, name="client")
        hello(self.peer, "test", "cli", timeout=10)

    def call(self, method: str, **params: Any) -> Any:
        return self.peer.call(method, params, timeout=30)

    def refused(self, method: str, **params: Any) -> RpcError:
        with pytest.raises(RpcError) as refused:
            self.call(method, **params)
        return refused.value

    def notices(self, count: int) -> list[dict[str, Any]]:
        """Waits for `count` notices in all to have been sent, and answers them."""
        with self.heard:
            assert self.heard.wait_for(lambda: len(self.told) >= count, 10)
            return list(self.told)

    def close(self) -> None:
        self.peer.close()
        self.daemon.close()

    def _hello(self, call: Call) -> dict[str, Any]:
        admit(call.params["protocol"])
        return {"daemon_id": "d", "protocol": PROTOCOL, "paired": True}

    def _told(self, call: Call) -> None:
        with self.heard:
            self.told.append(call.params)
            self.heard.notify_all()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


@pytest.fixture
def client(project: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Client]:
    # Called from elsewhere: the workspace a call names is where it is about.
    monkeypatch.chdir(project.parent)
    made = Client()
    yield made
    made.close()


def _exec_refuses(project: Path, capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    """What `hmz exec` prints after `hmz exec: error: ` for a line, run in the workspace."""
    with contextlib.chdir(project), pytest.raises(SystemExit) as stopped:
        main(["exec", *argv])
    assert stopped.value.code == 2
    said = capsys.readouterr().err.strip()
    assert said.startswith("hmz exec: error: ")
    return said.removeprefix("hmz exec: error: ")


def test_a_workspace_lists_its_flows_and_the_backends_installed(
    client: Client, project: Path
) -> None:
    listed = client.call("flows.list", workspace=str(project))
    names = {one["name"] for one in listed["flows"]}
    assert {"goal", "ralph_loop"} <= names
    # A chat is no flow, and is not offered as one (Section 8.3 of core.md).
    assert "chat" not in names
    assert listed["running"] == []

    goal = client.call("flows.get", workspace=str(project), name="goal")
    assert goal["name"] == "goal"
    assert "worker" in [one["name"] for one in goal["agents"]]

    backends = client.call("flows.backends")
    assert set(backends) == {"clis", "installable", "envs"}
    assert "claude" in backends["clis"]

    missing = client.refused("flows.get", workspace=str(project), name="./elsewhere")
    assert missing.code == Code.NOT_FOUND
    assert missing.message == "./elsewhere is not a flow on offer here."

    relative = client.refused("flows.list", workspace="project")
    assert relative.code == Code.REFUSED
    assert relative.message == "Say the workspace as a whole path, not project."


def test_flows_are_read_with_no_workspace_and_for_one_since_removed(
    client: Client, project: Path, tmp_path: Path
) -> None:
    client.call("flows.fork", workspace=str(project), flow="goal")
    listed = client.call("flows.list", workspace=str(project))["flows"]
    assert "local" in {one["whose"] for one in listed}
    mine = next(one["name"] for one in listed if one["whose"] == "local")

    # Naming no workspace reads what is on offer whatever the project: none of its own.
    bare = client.call("flows.list")
    assert set(bare) == {"flows", "flow", "running"}
    assert {"goal", "ralph_loop"} <= {one["name"] for one in bare["flows"]}
    assert "local" not in {one["whose"] for one in bare["flows"]}
    assert client.call("flows.get", name="goal")["name"] == "goal"
    assert client.call("flows.get", workspace=str(project), name=mine)["name"] == mine
    assert client.refused("flows.get", name=mine).code == Code.NOT_FOUND

    # A directory since removed is a workspace with no flows of its own, not a refusal.
    gone = tmp_path / "gone"
    removed = client.call("flows.list", workspace=str(gone))
    assert {"goal", "ralph_loop"} <= {one["name"] for one in removed["flows"]}
    assert "local" not in {one["whose"] for one in removed["flows"]}
    assert client.call("flows.get", workspace=str(gone), name="goal")["name"] == "goal"
    for method in ("flows.fork", "flows.setup", "flows.check"):
        missing = client.refused(method, workspace=str(gone), flow="goal")
        assert missing.code == Code.NOT_FOUND
        assert missing.message == f"There is no directory {gone}."


def test_a_line_checks_as_hmz_exec_would_without_starting_anything(
    client: Client, project: Path, tmp_path: Path
) -> None:
    checked = client.call(
        "flows.check",
        workspace=str(project),
        flow="goal",
        agents={"worker": AGENT},
        # A limit every model can be held to, priced or not.
        budget={"duration": 3600},
    )

    assert checked["flow"] == "goal"
    # A check says nothing of chats, which are no flows (Section 4.17.8.2 of daemon.md).
    assert "chats" not in checked
    assert checked["names"]["worker"]
    assert checked["declared"]["name"] == "goal"
    assert checked["unreadable"] == ""
    assert not started(tmp_path)


def test_a_relative_path_names_a_flow_of_the_workspace_the_call_names(
    client: Client, project: Path
) -> None:
    # The daemon is run in one directory and holds every workspace of its machine
    # (Section 3.3.2 of daemon.md), so `./done` is the workspace's and not the daemon's.
    (project / "done").mkdir()
    (project / "done" / "__init__.py").write_text(
        "from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow\n\n\n"
        "@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)\n"
        "async def done(task, *, agents, envs, params, ctx):\n"
        '    return "did " + task\n'
    )

    checked = client.call(
        "flows.check", workspace=str(project), flow="./done", budget={"duration": 3600}
    )

    assert checked["flow"] == "./done"
    assert checked["ref"] == "done:done"


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (
            ["-f", "ralph_loop", "-a", f"agent={AGENT}", "work"],
            {"flow": "ralph_loop", "agents": {"agent": AGENT}},
        ),
        (
            [
                "-f",
                "goal",
                "-a",
                f"worker={AGENT},stranger={AGENT}",
                "-p",
                "budget.cost=1",
                "hello",
            ],
            {
                "flow": "goal",
                "agents": {"worker": AGENT, "stranger": AGENT},
                "budget": {"cost": 1},
            },
        ),
        (
            ["-f", "goal", "-a", f"worker={NOBODY}", "-p", "budget.cost=1", "hello"],
            {"flow": "goal", "agents": {"worker": NOBODY}, "budget": {"cost": 1}},
        ),
        (
            ["-f", "./no_such_flow", "-p", "budget.cost=1", "work"],
            {"flow": "./no_such_flow", "budget": {"cost": 1}},
        ),
        (
            [
                "-f",
                "goal",
                "-a",
                f"worker={AGENT}",
                "-p",
                "budget.cost=1",
                "--backup",
                "nowhere",
                "x",
            ],
            {
                "flow": "goal",
                "agents": {"worker": AGENT},
                "budget": {"cost": 1},
                "backup": ["nowhere"],
            },
        ),
    ],
)
def test_a_line_is_refused_in_the_words_hmz_exec_refuses_it(
    client: Client,
    project: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    said: dict[str, Any],
) -> None:
    refused = client.refused("flows.check", workspace=str(project), **said)

    assert refused.code == Code.REFUSED
    assert refused.message == _exec_refuses(project, capsys, *argv)
    assert not started(tmp_path)


def test_a_directory_is_listed_and_a_typed_path_completed(
    client: Client, project: Path
) -> None:
    (project / "src").mkdir()
    (project / "README").write_text("")

    listed = client.call("paths.list", at=str(project), files=True)
    assert listed["whole"] == str(project.resolve())
    assert [one["name"] for one in listed["entries"]] == ["src", "README"]

    completed = client.call("paths.complete", typed=f"{project}/s")
    assert completed == {"paths": [f"{project}/src/"]}

    gone = client.refused("paths.list", at=str(project / "nowhere"))
    assert gone.code == Code.NOT_FOUND


def test_a_workspace_is_written_down_and_forgotten(
    client: Client, project: Path, tmp_path: Path
) -> None:
    kept = client.call("workspaces.add", workspace=str(project), here=str(tmp_path))
    assert kept["kept"] == str(project.resolve())
    assert kept["here"] == str(tmp_path.resolve())
    rows = {one["path"]: one for one in kept["workspaces"]}
    assert rows[str(project.resolve())]["there"] is True
    assert kept["workspaces"][0]["here"] is True

    client.call("workspaces.forget", workspace=str(project))
    listed = client.call("workspaces.list")
    assert str(project.resolve()) not in {one["path"] for one in listed["workspaces"]}

    gone = client.refused("workspaces.add", workspace=str(project / "nowhere"))
    assert gone.code == Code.NOT_FOUND

    verses = client.call("flowverses.list")
    assert set(verses) == {"verses", "installed", "updates"}
    unknown = client.refused("flowverses.get", name="nowhere")
    assert unknown.code == Code.NOT_FOUND
    assert unknown.message == "There is no flowverse nowhere."


class Host:
    """A host of this machine as the daemon lists it, saying whatever it is told to."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = str(workspace)
        self.slot = ""
        self.said: dict[str, Any] = {"pending": [], "ended": None, "state": "idle"}

    def status(self) -> dict[str, Any]:
        return {**self.said, "pid": 1, "started": "then"}

    def ends(self, epic: str, how: str) -> None:
        self.said = {
            **self.said,
            "ended": {"how": how, "epic": epic, "flow": "chat", "at": time.time()},
        }
        notices.watched().look()


def test_notices_are_followed_dropped_and_taken_up_after_the_last_heard(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = Host(project)
    monkeypatch.setattr(hmz.daemon, "daemons", lambda: [host])
    notices.watched().look()
    first = Client()
    try:
        opened = first.call("notices.subscribe")
        host.ends("e1", "done")
        host.ends("e2", "failed")
        told = first.notices(2)
    finally:
        first.close()

    assert [one["sub"] for one in told] == [opened["sub"]] * 2
    assert [(one["notice"]["epic"], one["notice"]["kind"]) for one in told] == [
        ("e1", "done"),
        ("e2", "failed"),
    ]
    assert opened["last"] < told[0]["notice"]["id"] < told[1]["notice"]["id"]

    # Said while nobody follows, and sent first to whoever takes it up after the last heard.
    host.ends("e3", "stopped")
    again = Client()
    try:
        heard = told[1]["notice"]["id"]
        resumed = again.call("notices.subscribe", after=heard)
        (third,) = again.notices(1)
        assert third["sub"] == resumed["sub"]
        assert third["notice"]["epic"] == "e3"
        assert resumed["last"] == third["notice"]["id"]
        kept = again.call("notices.list", after=told[0]["notice"]["id"])
        assert [one["epic"] for one in kept["notices"]] == ["e2", "e3"]

        assert again.call("notices.unsubscribe", sub=resumed["sub"]) == {}
        unknown = again.refused("notices.unsubscribe", sub=resumed["sub"])
        assert unknown.code == Code.UNKNOWN_SUBSCRIPTION
        assert unknown.message == f"There is no subscription {resumed['sub']}."
    finally:
        again.close()
