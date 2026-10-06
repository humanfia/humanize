"""Stand-in coding agent CLIs for the `agents` integration tests.

A stand-in is a small Python script written into a test's own `bin/` and put first on PATH
under the name the driver calls, so a driver is run for real -- its command line built, its
process spawned, its output parsed -- against a CLI this repo wrote. Each stand-in prints the
wire format its real CLI prints and records, one JSON line per call, the argv it was started
with, what it was fed and the environment variables a test asks about.

Every stand-in body is run after a shared prelude that gives it:

- `argv`, the arguments it was started with, and `flags`, each `--flag` mapped to the word after.
- `note(said)`, which records one call: the argv, `said`, the pid and the watched variables.
- `out(obj)`, which writes `obj` as one JSON line on stdout, flushed.

The drivers that call a model from an SDK rather than a CLI are driven against `Endpoint`
instead: an OpenAI-compatible chat completions endpoint on the loopback, in the test's own
process.
"""

from __future__ import annotations

import json
import os
import socketserver
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import pytest

#: Environment variables every call records, beside whatever a test adds.
WATCHED = ("HMZ_TEST_INHERITED",)

_PRELUDE = """
import json, os, pathlib, sys

LOG = pathlib.Path({log!r})
WATCHED = {watched!r}
argv = sys.argv[1:]
flags = dict(zip(argv, argv[1:]))


def note(said=""):
    with LOG.open("a") as stream:
        json.dump({{"name": {name!r}, "argv": argv, "stdin": said, "pid": os.getpid(),
                   "cwd": os.getcwd(),
                   "env": {{key: os.environ.get(key) for key in WATCHED}}}}, stream)
        stream.write("\\n")


def out(obj):
    print(json.dumps(obj), flush=True)

"""


@dataclass(frozen=True)
class Call:
    """One thing a stand-in was asked: by which name, with what, and in what environment."""

    name: str
    argv: list[str]
    stdin: str
    pid: int
    cwd: str
    env: dict[str, str | None]

    def flag(self, name: str) -> str | None:
        """The word after `name` on the command line, or None where it is not there."""
        if name not in self.argv:
            return None
        at = self.argv.index(name)
        return self.argv[at + 1] if at + 1 < len(self.argv) else ""


@dataclass
class Standins:
    """A test's own `bin/` on PATH, and what the stand-ins installed there were asked."""

    bin: Path
    log: Path
    watched: tuple[str, ...] = WATCHED

    def install(self, name: str, body: str) -> Path:
        """Writes one stand-in CLI called `name`, running `body` after the shared prelude."""
        at = self.bin / name
        prelude = _PRELUDE.format(log=str(self.log), watched=self.watched, name=name)
        at.write_text(f"#!{sys.executable}\n{prelude}\n{body}\n", encoding="utf-8")
        at.chmod(0o755)
        return at

    def calls(self, name: str | None = None) -> list[Call]:
        """Every call recorded so far, in order, or only those of the stand-in `name`."""
        if not self.log.exists():
            return []
        held = [
            Call(**json.loads(line))
            for line in self.log.read_text(encoding="utf-8").splitlines()
        ]
        return [one for one in held if name is None or one.name == name]

    def said(self, name: str | None = None) -> list[str]:
        """What each recorded call was fed, leaving out the launches that were fed nothing."""
        return [one.stdin for one in self.calls(name) if one.stdin]


def standins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *watched: str
) -> Standins:
    """A `bin/` of the test's own, first on PATH, and a HOME of its own beside it.

    The HOME is so that a driver reading a CLI's own config or log reads the test's, never the
    one of whoever runs the suite.
    """
    binaries = tmp_path / "bin"
    binaries.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    # Only the system's own directories after it, so a real agent CLI installed on the machine
    # running the suite is never the one found.
    monkeypatch.setenv("PATH", os.pathsep.join((str(binaries), "/usr/bin", "/bin")))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HMZ_TEST_INHERITED", "from-the-flow")
    return Standins(binaries, tmp_path / "calls.jsonl", (*WATCHED, *watched))


def kinds(events: list[Any]) -> list[str]:
    """The kind of each event, in order."""
    return [event.kind for event in events]


#: How DeepSeek Harness opens the snapshot of its own runtime it puts after a user's prompt.
RUNTIME_CONTEXT = "Current runtime context."


def harnessed(message: dict[str, Any]) -> bool:
    """Whether a user message is one a harness wrote itself, not one it was prompted with."""
    return str(message.get("content") or "").startswith(RUNTIME_CONTEXT)


@dataclass
class Endpoint:
    """An OpenAI-compatible `/v1/chat/completions` on the loopback, and what it was asked.

    What it answers is chosen by the last user message a harness did not write itself, so a
    test says the turn it wants by what it asks: `unfinished` is refused with a 400, `hang`
    sends one piece and then nothing until the endpoint is shut, and anything else streams
    back some thinking and the prompt itself -- or `{"value": <prompt>}` where a shape was
    asked for -- with usage.
    """

    url: str
    asked: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    shut: threading.Event = field(default_factory=threading.Event)


class _Answers(BaseHTTPRequestHandler):
    endpoint: ClassVar[Endpoint]
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args

    def _send(self, status: int, body: dict[str, Any]) -> None:
        said = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(said)))
        self.end_headers()
        self.wfile.write(said)

    def _chunk(
        self, delta: dict[str, Any], usage: dict[str, int] | None = None
    ) -> None:
        said: dict[str, Any] = {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "stand-in",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}]
            if delta
            else [],
        }
        if usage is not None:
            said["usage"] = usage
        self.wfile.write(f"data: {json.dumps(said)}\n\n".encode())
        self.wfile.flush()

    def do_GET(self) -> None:
        self._send(200, {"object": "list", "data": [{"id": "stand-in"}]})

    def do_POST(self) -> None:
        asked: dict[str, Any] = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}"
        )
        self.endpoint.asked.append(asked)
        # The first line only: a prompt asked for a shape in words carries the schema below.
        said = next(
            (
                str(one.get("content") or "").partition("\n")[0]
                for one in reversed(asked.get("messages") or [])
                if one.get("role") == "user" and not harnessed(one)
            ),
            "",
        )
        if said == "unfinished":
            self._send(400, {"error": {"message": "it could not finish"}})
            return
        shaped = asked.get("response_format") or "schema" in json.dumps(
            asked["messages"]
        )
        answer = json.dumps({"value": said}) if shaped else said
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self._chunk(
            {"role": "assistant", "reasoning_content": "thinking about " + said}
        )
        if said == "hang":
            self.endpoint.shut.wait(600)
            return
        for piece in (answer[: len(answer) // 2], answer[len(answer) // 2 :]):
            self._chunk({"content": piece})
        self._chunk(
            {}, {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


class _Loopback(ThreadingHTTPServer):
    """A server that does not ask DNS what the loopback is called.

    `HTTPServer.server_bind` looks its own address up with `getfqdn`, which on a CI runner
    can be a reverse lookup that takes seconds -- a test's whole time budget, gone before it
    has asked anything.
    """

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, self.server_port = self.server_address[:2]
        self.server_name = str(host)


def serving() -> Iterator[Endpoint]:
    """Serves an `Endpoint` on a port of its own until the generator is closed."""
    server = _Loopback(("127.0.0.1", 0), _Answers)
    server.daemon_threads = True
    endpoint = Endpoint(f"http://127.0.0.1:{server.server_address[1]}/v1")
    server.RequestHandlerClass = type("_Serving", (_Answers,), {"endpoint": endpoint})
    held = threading.Thread(target=server.serve_forever, daemon=True)
    held.start()
    try:
        yield endpoint
    finally:
        endpoint.shut.set()
        server.shutdown()
        server.server_close()
