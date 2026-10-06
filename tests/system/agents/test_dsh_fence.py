"""That a dsh agent held to a flow's permission is held to it by the fence, shell and all.

dsh enforces none of a fence itself -- the bundle ships no confining shell executor, and the
Landlock launcher `dsh-sandbox-local` it does carry lets a command read all of `/` and write all
of `/tmp` -- so the whole of it is `hmz internal fence` around the runtime the SDK launches. This
drives that: the real bundled runtime, launched by the real SDK through the driver, inside the
real wall, taking one turn whose model is a server of this test's own that asks for one `bash`
call after another and writes down what each came back with.

That server listens on this machine's own address rather than on loopback, because the runtime
connects to loopback directly and to nothing else through a proxy -- so a model on loopback is
one a fenced runtime cannot reach at all, and one anywhere else is reached the way DeepSeek's
own endpoint is, through the proxy the fence leaves open.

A system test because the other side is the runtime and the kernel. It spends no tokens and
talks to no model of anybody's, so it is not behind `--run-agents`.
"""

from __future__ import annotations

import json
import shutil
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import DshAgent, DshAgentConfig
from hmz.coganchor.fence import enforceable
from hmz.coganchor.linux import landlock
from hmz.flows import HarnessKind, Permission, PermissionKind
from hmz.runtime.flowing import harnessing

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.skipif(
    not enforceable(net=True),
    reason=f"this kernel speaks Landlock ABI {landlock.abi()}; cutting TCP needs 4",
)


class _Model(ThreadingHTTPServer):
    """Chat completions that ask for each of `commands` in turn, then say `done`."""

    def __init__(self, commands: list[str], address: str) -> None:
        self.commands = commands
        self.results: list[str] = []
        self.tools: list[str] = []
        self.url = ""
        super().__init__((address, 0), _Asks)


def _outward() -> str | None:
    """This machine's address on the interface it would reach the internet through.

    Read off a datagram socket pointed at a routable address, which picks the interface and
    sends nothing.

    Returns:
      The address, or None for a machine with no route but loopback.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
        except OSError:
            return None
        address = str(probe.getsockname()[0])
    return None if address.startswith("127.") else address


class _Asks(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        served = cast("_Model", self.server)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        said = [one for one in body.get("messages", []) if one.get("role") == "tool"]
        if said:
            served.results.append(str(said[-1].get("content")))
        served.tools = [one["function"]["name"] for one in body.get("tools", [])]
        if len(said) < len(served.commands):
            call = {"command": served.commands[len(said)], "description": "probe"}
            delta: dict[str, Any] = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": f"call-{len(said)}",
                        "type": "function",
                        "function": {"name": "bash", "arguments": json.dumps(call)},
                    }
                ],
            }
            finish = "tool_calls"
        else:
            delta, finish = {"role": "assistant", "content": "done"}, "stop"
        chunk = {"id": "c", "object": "chat.completion.chunk", "created": 1}
        frames: list[dict[str, Any]] = [
            {**chunk, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {
                **chunk,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in frames:
            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[_Model]:
    pytest.importorskip(
        "deepseek_harness_runtime",
        reason="the [dsh] extra is not installed in this Python environment",
    )
    address = _outward()
    if address is None:
        pytest.skip("this machine has no address but loopback")
    probe = Path.home() / f"fence-probe-dsh-{uuid.uuid4().hex[:8]}"
    served = _Model(
        [
            f"echo no > {probe}",
            "cat /etc/machine-id",
            "curl -sS -m 10 https://example.com",
            "echo ok > ./ok.txt && echo WROTE",
        ],
        address,
    )
    served.url = f"http://{address}:{served.server_port}"
    threading.Thread(target=served.serve_forever, daemon=True).start()
    monkeypatch.setenv("DEEPSEEK_BASE_URL", served.url)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-a-real-key")
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh-home"))
    try:
        yield served
    finally:
        served.shutdown()
        served.server_close()
        assert not probe.exists(), f"the fence let the agent write {probe}"
        probe.unlink(missing_ok=True)


def test_a_fenced_dsh_turn_reaches_its_workdir_and_its_model_and_nothing_else(
    model: _Model, tmp_path: Path
) -> None:
    """local=all, user=read, system=none, online=none: the recipe every CLI is put to."""
    work = tmp_path / "work"
    work.mkdir()
    permission = Permission(
        local=PermissionKind.ALL,
        user=PermissionKind.READ,
        system=PermissionKind.NONE,
        online=PermissionKind.NONE,
    )
    fence = harnessing.fenced(
        permission,
        workdir=str(work),
        home=str(Path.home()),
        profile=backends.named("dsh"),
        environ={"DEEPSEEK_BASE_URL": model.url},
    )
    agent = DshAgent(
        DshAgentConfig(
            model="deepseek-v4-flash",
            effort="high",
            permission=harnessing.rung(
                HarnessKind.DSH, permission, rungs=DshAgent.rungs
            ),
            fence=fence,
            web_search=harnessing.searching(permission, tellable=True),
        )
    )

    # The turn completes, which is the model reached through the proxy the fence left open.
    assert agent.new(work)("go") == "done"

    home, machine, web, workdir = model.results
    assert "Permission denied" in home
    assert "Permission denied" in machine
    assert "403" in web or shutil.which("curl") is None
    assert "WROTE" in workdir
    assert (work / "ok.txt").read_text() == "ok\n"
    assert not {"web_search", "web_fetch"} & set(model.tools)
