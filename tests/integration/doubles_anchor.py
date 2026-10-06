"""Stand-ins the anchor tests write: `ssh`, `docker` and `container` on `PATH`, and a fence.

Each fake is a small Python program that appends its argv (and the few variables it was
asked about) to a JSON-lines log, then does what the code under test reads from the real
tool. A command sent "over there" -- `ssh HOST CMD`, `docker exec -i NAME ARGV...`,
`container exec -i NAME ARGV...` -- runs on this machine, in a home or a root of the test's
own, so the anchor's whole road (bundle install, serve, protocol) is exercised for real.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hmz.coganchor.proto import Channel
from hmz.coganchor.remote import RemoteClient
from hmz.coganchor.serve.exports import ExportTable
from hmz.coganchor.serve.server import Server

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

    import pytest

#: Variables each fake writes down beside its argv, for tests about what reached it.
NOTED = ("DOCKER_HOST", "DOCKER_CONTEXT", "HOME")

_COMMON = """\
import json, os, sys

def note(tool):
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({
            "tool": tool,
            "argv": sys.argv[1:],
            "env": {k: os.environ[k] for k in NOTED_HERE if k in os.environ},
        }) + "\\n")

def fail_if_asked(tool):
    said = os.environ.get("FAKE_FAIL_" + tool.upper().replace("-", "_"))
    if said:
        sys.stderr.write(said + "\\n")
        sys.exit(255)

def rooted(words):
    root = os.environ.get("FAKE_ROOT", "")
    if not root:
        return list(words)
    return [w.replace("/tmp/humanize", root + "/tmp/humanize") for w in words]
""".replace("NOTED_HERE", repr(NOTED))

#: ssh's options that take a value; every other `-x` is a switch.
_SSH = """
note("ssh")
args = sys.argv[1:]
valued = set("BbcDEeFIiJLlmOoPpQRSWw")
while args and args[0].startswith("-") and len(args[0]) > 1:
    flag = args.pop(0)
    if flag[1] in valued and len(flag) == 2:
        args.pop(0)
fail_if_asked("ssh")
if not args:
    sys.exit(255)
host, rest = args[0], args[1:]
env = dict(os.environ, HOME=os.environ["FAKE_HOME"])
os.execve("/bin/sh", ["/bin/sh", "-c", " ".join(rest)], env)
"""

#: `docker` and `container`. A subcommand a test gave an answer for (`Fakes.answer`) says
#: that; otherwise `exec` and a one-shot `run` run their command here, a detached `run`
#: makes a container id and writes it where `--cidfile` says, `logs` says `$FAKE_LOGS`, and
#: anything else succeeds saying nothing.
_EXEC = """
tool = os.path.basename(sys.argv[0])
note(tool)
args = sys.argv[1:]
globals_valued = {"--host", "-H", "--context", "--tlscacert", "--tlscert", "--tlskey",
                  "--config", "--log-level"}
while args and args[0].startswith("-"):
    if args.pop(0) in globals_valued:
        args.pop(0)
if not args:
    sys.exit(0)
sub, args = args[0], args[1:]
answers = {}
if os.path.exists(os.environ["FAKE_ANSWERS"]):
    with open(os.environ["FAKE_ANSWERS"], encoding="utf-8") as held:
        answers = json.load(held)
for key in ((sub + " " + args[0]) if args else None, sub):
    if key in answers:
        said = answers[key]
        sys.stdout.write(said.get("stdout", ""))
        sys.stderr.write(said.get("stderr", ""))
        sys.exit(said.get("status", 0))
if sub == "logs":
    sys.stdout.write(os.environ.get("FAKE_LOGS", ""))
    sys.exit(0)
env = dict(os.environ)
if sub == "exec":
    fail_if_asked(tool)
    while args and args[0].startswith("-"):
        flag = args.pop(0)
        if flag in ("-e", "--env"):
            name, _, value = args.pop(0).partition("=")
            env[name] = value
        elif flag in ("-w", "--workdir", "-u", "--user"):
            args.pop(0)
    argv = rooted(args[1:])
elif sub == "run":
    valued = {"--cidfile", "--name", "--label", "-l", "--user", "-u", "--workdir", "-w",
              "--env", "-e", "--mount", "--cpus", "--memory", "-m", "--shm-size",
              "--runtime", "--network", "--device", "--gpus", "--entrypoint", "--platform",
              "--progress", "-v", "--volume", "--cap-add", "--arch", "--os", "-c"}
    flags = {}
    while args and args[0].startswith("-"):
        flag = args.pop(0)
        flags[flag] = args.pop(0) if flag in valued else ""
    if "--detach" in flags or "-d" in flags:
        made = "cid-" + flags.get("--name", "anonymous")
        if "--cidfile" in flags:
            with open(flags["--cidfile"], "w", encoding="utf-8") as cid:
                cid.write(made)
        print(made)
        sys.exit(0)
    argv = rooted(args[1:])
    if not argv:
        sys.exit(0)
else:
    sys.exit(0)
os.execve(argv[0] if argv[0].startswith("/") else "/usr/bin/env",
          argv if argv[0].startswith("/") else ["env", *argv], env)
"""


@dataclass(frozen=True)
class Fakes:
    """Fake tools on `PATH`, the log they write, and the "far side" they run things in.

    Attributes:
      bin: The directory on the front of `PATH`.
      log: The JSON-lines log every fake appends to.
      home: The `HOME` a command sent over `ssh` runs with.
      root: Where a container's `/tmp/humanize...` really is.
      answers: What `docker` and `container` answer each subcommand with, as JSON.
    """

    bin: Path
    log: Path
    home: Path
    root: Path
    answers: Path

    def answer(
        self, subcommand: str, stdout: str = "", *, stderr: str = "", status: int = 0
    ) -> None:
        """Has `docker` and `container` answer `subcommand` (one word or two) like this."""
        held: dict[str, Any] = (
            json.loads(self.answers.read_text()) if self.answers.exists() else {}
        )
        held[subcommand] = {"stdout": stdout, "stderr": stderr, "status": status}
        self.answers.write_text(json.dumps(held))

    def calls(self, tool: str) -> list[list[str]]:
        """Every argv `tool` was run with, oldest first."""
        return [one["argv"] for one in self.records() if one["tool"] == tool]

    def records(self) -> list[dict[str, Any]]:
        """Everything every fake wrote down, oldest first."""
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def fail(self, monkeypatch: pytest.MonkeyPatch, tool: str, said: str) -> None:
        """Has `tool` refuse what it is asked to run over there, saying `said`."""
        monkeypatch.setenv(f"FAKE_FAIL_{tool.upper().replace('-', '_')}", said)


def fakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """Writes `ssh`, `docker` and `container` into a directory on the front of `PATH`."""
    made = Fakes(
        bin=tmp_path / "fake-bin",
        log=tmp_path / "fake-calls.jsonl",
        home=tmp_path / "far-home",
        root=tmp_path / "far-root",
        answers=tmp_path / "fake-answers.json",
    )
    for one in (made.bin, made.home, made.root / "tmp"):
        one.mkdir(parents=True)
    for name, body in (("ssh", _SSH), ("docker", _EXEC), ("container", _EXEC)):
        path = made.bin / name
        path.write_text(f"#!{sys.executable}\n{_COMMON}{body}")
        path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{made.bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(made.log))
    monkeypatch.setenv("FAKE_HOME", str(made.home))
    monkeypatch.setenv("FAKE_ROOT", str(made.root))
    monkeypatch.setenv("FAKE_ANSWERS", str(made.answers))
    return made


#: The fence stand-in: writes the policy it was given down, then becomes the program.
_FENCE = """\
import os, sys
policy = sys.argv[1].removeprefix("--policy=")
rest = sys.argv[3:] if sys.argv[2:3] == ["--"] else sys.argv[2:]
with open(os.environ["FAKE_FENCE_LOG"], "a", encoding="utf-8") as log:
    log.write(policy + "\\n")
os.execvp(rest[0], rest)
"""


def fence_stand_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Has every fenced command of this process spawned under a stand-in that logs its policy.

    A real fence is Landlock or Seatbelt, which is the kernel's to enforce and a system
    test's to check; what is left here is which policy a command would be held to.

    Returns:
      The JSON-lines log of policies, one per fenced command.
    """
    program = tmp_path / "fence-stand-in"
    program.write_text(f"#!{sys.executable}\n{_FENCE}")
    program.chmod(0o755)
    log = tmp_path / "fences.jsonl"
    monkeypatch.setenv("FAKE_FENCE_LOG", str(log))

    def wrapper(fence: Any) -> list[str]:
        return [str(program), f"--policy={fence.dumps()}", "--"]

    def able(*, net: bool) -> bool:
        del net
        return True

    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", able)
    monkeypatch.setattr("hmz.coganchor.fence.landlocked", able)
    return log


def policies(log: Path) -> list[dict[str, Any]]:
    """Every policy a fenced command was spawned with, oldest first."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def announced(
    command: list[str], *, env: dict[str, str] | None = None
) -> tuple[subprocess.Popen[bytes], str, int]:
    """Starts a command that says `... listening HOST PORT` on stderr, and reads that line.

    Returns:
      The process, and the host and port it said it landed on.

    Raises:
      AssertionError: If it ended before saying so.
    """
    process = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env
    )
    assert process.stderr is not None
    for raw in process.stderr:
        line = raw.decode(errors="replace").split()
        if "listening" in line:
            host, port = line[-2], int(line[-1])
            # Keep draining, so a chatty child never blocks on a full pipe.
            threading.Thread(target=process.stderr.read, daemon=True).start()
            return process, host, port
    process.wait()
    raise AssertionError(f"{command} never said where it listened")


def stopped(process: subprocess.Popen[bytes]) -> None:
    """Ends a process this suite started, and reaps it."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def routable_address() -> str | None:
    """An address of this host that is not loopback, or None where it has only loopback."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1: nothing is sent
        address = str(probe.getsockname()[0])
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith("127.") else address


def echoing(host: str) -> Iterator[tuple[str, int]]:
    """A TCP server on `host` that answers everything it is sent with `echo:` before it."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, 0))
    listener.listen(8)

    def serve() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                while data := connection.recv(4096):
                    connection.sendall(b"echo:" + data)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[:2]
    finally:
        listener.close()
        thread.join(timeout=2)


#: The directory a linked client names, which the server answers from a real one.
VIRTUAL = "/project"


@dataclass(frozen=True)
class Link:
    """A client talking to an in-process server, and the target directory it serves."""

    client: RemoteClient
    real: Path


@contextlib.contextmanager
def linked(real: Path, *, timeout: float = 30.0) -> Generator[Link]:
    """Both halves over a socketpair in this process, handshake done, serving `real`."""
    real.mkdir(exist_ok=True)
    left, right = socket.socketpair()
    server = Server(
        Channel.from_socket(right), ExportTable.parse([f"{VIRTUAL}:{real}"])
    )
    serving = threading.Thread(target=server.serve, daemon=True)
    serving.start()
    client = RemoteClient(Channel.from_socket(left), timeout=timeout)
    try:
        client.start()
        yield Link(client, real)
    finally:
        client.close()
        serving.join(timeout=5)
