"""`hosts.env.*` over the machine's daemon, on the envs of an epic a host of its own is going with.

A flow that waits is started; a client that never attaches then lists its envs, writes, reads,
runs a command in and searches the workspace it holds, and is refused as Section 4.23 of
daemon.md says where it asks for what it may not.
"""

from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.rpc import PROTOCOL, Frames, encode
from tests.integration.doubles_daemon import WAITS, hosting, project, until, written

if TYPE_CHECKING:
    import socket
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(90),
]

#: Writes through two `LocalEnv` roles nobody passed, both the run's workspace, then waits.
TWO = """
import asyncio

from hmz.flows import AgentCollection, EnvCollection, FilesEnvMixin, FlowParams, LocalEnv, flow


class Files(LocalEnv, FilesEnvMixin): ...


class Envs(EnvCollection):
    code: Files
    docs: Files


@flow(agents=AgentCollection, envs=Envs, params=FlowParams, name="two")
async def two(task, *, agents, envs, params, ctx):
    await envs["code"].write("a.txt", b"x")
    await envs["docs"].write("b.txt", b"y")
    while True:
        await asyncio.sleep(0.05)
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    written(at, "waits", WAITS)
    with hosting():
        yield at


def _client(one: socket.socket) -> Callable[..., dict[str, Any]]:
    """Calls one method at a time over a bare session, answering its response whole."""
    frames, ids = Frames(), itertools.count()

    def call(method: str, **params: Any) -> dict[str, Any]:
        asked = next(ids)
        one.sendall(
            encode({"jsonrpc": "2.0", "id": asked, "method": method, "params": params})
        )
        while True:
            chunk = one.recv(1 << 16)
            assert chunk, "the daemon closed without answering"
            for payload in frames.feed(chunk):
                said = json.loads(payload)
                if said.get("id") == asked:
                    return said

    call("session.hello", protocol=PROTOCOL, client={"name": "", "kind": "cli"})
    return call


def test_the_envs_of_an_epic_are_listed_written_read_run_in_and_searched(
    workspace: Path,
) -> None:
    held = daemon.host()
    named = where.workspace(workspace)
    with (
        held.link(name="starter") as link,
        where.connects(where.at()) as one,
    ):
        one.settimeout(60)
        call = _client(one)
        assert call("hosts.env.list", workspace=named)["error"] == {
            "code": 409,
            "message": "no flow is running, so no env is open",
        }
        link.start("./waits", "forever", budget={"cost": 1})

        assert until(
            lambda: (
                call("hosts.env.list", workspace=named).get("result", {}).get("envs")
            )
        )
        assert call("hosts.env.list", workspace=named)["result"]["envs"] == [
            {
                "name": "workspace",
                "kind": "local",
                "workdir": str(workspace.resolve()),
                "can": ["read", "write", "exec", "grep"],
            }
        ]
        at = {"workspace": named, "env": "workspace"}
        assert call("hosts.env.write", **at, path="notes/a.txt", text="héllo\nworld\n")[
            "result"
        ] == {"size": 13}
        assert (workspace / "notes" / "a.txt").read_text() == "héllo\nworld\n"
        assert call("hosts.env.read", **at, path="notes/a.txt", offset=7)["result"] == {
            "text": "world\n",
            "size": 13,
            "eof": True,
        }
        assert call("hosts.env.read", **at, path="notes/a.txt", length=2)["result"] == {
            "text": "h\N{REPLACEMENT CHARACTER}",
            "size": 13,
            "eof": False,
        }
        ran = call(
            "hosts.env.exec",
            **at,
            argv=["sh", "-c", "cat notes/a.txt; echo oops >&2; exit 3"],
        )["result"]
        assert ran == {"code": 3, "stdout": "héllo\nworld\n", "stderr": "oops\n"}
        assert call("hosts.env.exec", **at, argv=["sleep", "30"], seconds=1)[
            "result"
        ] == {"code": None, "stdout": "", "stderr": ""}
        assert call("hosts.env.grep", **at, pattern="w.r+ld")["result"] == {
            "matches": [{"path": "notes/a.txt", "line": 2, "text": "world"}],
            "more": False,
        }

        assert call("hosts.env.write", **at, path="~/b.txt", text="in")["result"] == {
            "size": 2
        }
        assert (workspace / "~" / "b.txt").read_text() == "in"
        assert call("hosts.env.read", **at, path="~/b.txt")["result"]["text"] == "in"
        assert call("hosts.env.read", **at, path="../outside")["error"] == {
            "code": 400,
            "message": "../outside is outside the env workspace.",
        }
        assert call("hosts.env.read", **at, path="missing")["error"] == {
            "code": 404,
            "message": "There is no file missing in workspace.",
        }
        assert call("hosts.env.exec", **at, argv=[])["error"] == {
            "code": 400,
            "message": "hosts.env.exec runs a command: give argv.",
        }
        assert call("hosts.env.read", workspace=named, env="nope", path="a")[
            "error"
        ] == {
            "code": 404,
            "message": "The epic has no env nope.",
        }
        assert held.status()["attached"] == 1
        link.stop()


def test_two_env_roles_sharing_the_workspace_are_each_listed_and_reached(
    workspace: Path,
) -> None:
    written(workspace, "two", TWO)
    held = daemon.host()
    named = where.workspace(workspace)
    with (
        held.link(name="starter") as link,
        where.connects(where.at()) as one,
    ):
        one.settimeout(60)
        call = _client(one)
        link.start("./two", "forever", budget={"cost": 1})
        assert until((workspace / "b.txt").exists)

        local = {
            "kind": "local",
            "workdir": str(workspace.resolve()),
            "can": ["read", "write", "exec", "grep"],
        }
        assert call("hosts.env.list", workspace=named)["result"]["envs"] == [
            {"name": "code", **local},
            {"name": "docs", **local},
        ]
        assert call("hosts.env.read", workspace=named, env="docs", path="b.txt")[
            "result"
        ] == {"text": "y", "size": 1, "eof": True}
        assert call("hosts.env.read", workspace=named, env="workspace", path="b.txt")[
            "error"
        ] == {"code": 404, "message": "The epic has no env workspace."}
        link.stop()
