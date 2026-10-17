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
from dataclasses import dataclass, replace
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

def stall_if(key):
    if key in os.environ.get("FAKE_STALLED", "").split(","):
        import time
        # Unanswered for as long as whoever asked waits, and never past it.
        parent, until = os.getppid(), time.monotonic() + 120
        while os.getppid() == parent and time.monotonic() < until:
            time.sleep(0.2)
        sys.exit(255)
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

#: A swarm of one node, `n1`, that keeps its services as files in `$FAKE_SWARM`, one each,
#: under its name, which is its id too: `docker service create`, `ls` (by `label=` filters),
#: `inspect`, `ps` and `rm`, and `docker inspect --type task`. A service's task is preparing
#: for `$FAKE_SWARM_STARTING` seconds after it was created, then running in a container whose
#: `exec` runs here -- or failed, where the service's name holds `$FAKE_SWARM_FAILING`. A
#: stalled `service create` (`Fakes.stall`) creates the service, and then never answers.
_SWARM = """
import time

def kept(state, service):
    try:
        with open(os.path.join(state, service + ".json"), encoding="utf-8") as one:
            return json.load(one)
    except (OSError, ValueError):
        return None

def swarmed(state, sub, args):
    if sub == "inspect":
        service = args[-1].removeprefix("task-")
        made = kept(state, service)
        if made is None:
            sys.stderr.write("Error: No such object: " + args[-1] + "\\n")
            print("[]")
            return 1
        failing = os.environ.get("FAKE_SWARM_FAILING", "")
        if time.time() - made["made"] < float(os.environ.get("FAKE_SWARM_STARTING") or 0):
            status = {"State": "preparing"}
        elif failing and failing in service:
            status = {"State": "failed", "Err": "task: non-zero exit (1)"}
        else:
            status = {"State": "running", "ContainerStatus": {"ContainerID": "c-" + service}}
        print(json.dumps([{"NodeID": "n1", "Status": status}]))
        return 0
    verb, args = args[0], args[1:]
    valued = {"--name", "--label", "--user", "--workdir", "--env", "--mount", "--replicas",
              "--restart-condition", "--reserve-cpu", "--limit-cpu", "--reserve-memory",
              "--limit-memory", "--generic-resource", "--constraint", "--cap-add",
              "--filter"}
    flags, named = [], []
    while args:
        word = args.pop(0)
        if word.startswith("-"):
            flags.append((word, args.pop(0) if word in valued else ""))
        else:
            named.append(word)
            if verb == "create":
                break
    if verb == "create":
        labels = dict(value.partition("=")[::2] for flag, value in flags if flag == "--label")
        labels.update(json.loads(os.environ.get("FAKE_STALLED_LABELS") or "{}"))
        name = dict(flags)["--name"]
        spec = {"made": time.time(), "ID": name, "Spec": {"Name": name, "Labels": labels}}
        with open(os.path.join(state, "." + name), "w", encoding="utf-8") as one:
            json.dump(spec, one)
        os.replace(os.path.join(state, "." + name), os.path.join(state, name + ".json"))
        stall_if("service create")
        print(name)
    elif verb == "ls":
        wanted = [value.removeprefix("label=") for flag, value in flags if flag == "--filter"]
        for file in sorted(os.listdir(state)):
            made = kept(state, file[:-5]) if file.endswith(".json") else None
            labels = made["Spec"]["Labels"] if made else None
            if labels is not None and all(
                key in labels and (not eq or labels[key] == value)
                for key, eq, value in (one.partition("=") for one in wanted)
            ):
                print(file[:-5])
    elif verb == "inspect":
        print(json.dumps([made for made in map(lambda one: kept(state, one), named) if made]))
    elif verb == "ps":
        print("task-" + named[-1])
    elif verb == "rm":
        for service in named:
            try:
                os.remove(os.path.join(state, service + ".json"))
            except OSError:
                pass
    return 0
"""

#: `docker` and `container`. A subcommand a test stalled (`Fakes.stall`) never answers; one
#: it gave an answer for (`Fakes.answer`) says that; otherwise, on a swarm (`swarm`), its
#: services and tasks are what it keeps, `exec` and a one-shot `run` run their command here,
#: a detached `run` makes a container id and writes it where `--cidfile` says, `logs` says
#: `$FAKE_LOGS`, and anything else succeeds saying nothing. Where `$FAKE_CONTAINERS` names a
#: directory, a detached `run` also keeps its container there -- before it stalls, where it
#: is stalled, without writing the cidfile -- and `inspect --type container` and `rm` answer
#: from it.
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
if sub not in ("run", "service"):
    stall_if(sub)
kept_in = os.environ.get("FAKE_CONTAINERS", "")
if kept_in and sub == "inspect" and args[:2] == ["--type", "container"]:
    found = []
    for name in args[2:]:
        try:
            with open(os.path.join(kept_in, name + ".json"), encoding="utf-8") as one:
                found.append(json.load(one))
        except OSError:
            sys.stderr.write("Error: No such container: " + name + "\\n")
    print(json.dumps(found))
    sys.exit(0 if found else 1)
if kept_in and sub == "rm":
    for name in os.listdir(kept_in):
        with open(os.path.join(kept_in, name), encoding="utf-8") as one:
            made = json.load(one)
        if made["Id"] in args or made["Name"][1:] in args:
            os.remove(os.path.join(kept_in, name))
    sys.exit(0)
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
tasked = sub == "inspect" and args[:2] == ["--type", "task"]
if os.environ.get("FAKE_SWARM") and (sub == "service" or tasked):
    sys.exit(swarmed(os.environ["FAKE_SWARM"], sub, args))
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
        if kept_in:
            labels = {}
            for flag, value in zip(sys.argv[1:], sys.argv[2:]):
                if flag in ("--label", "-l"):
                    labels.update([value.partition("=")[::2]])
            labels.update(json.loads(os.environ.get("FAKE_STALLED_LABELS") or "{}"))
            kept = {"Id": made, "Name": "/" + flags.get("--name", "anonymous"),
                    "Config": {"Labels": labels}, "State": {"Status": "created"}}
            with open(os.path.join(kept_in, flags.get("--name", made) + ".json"), "w",
                      encoding="utf-8") as one:
                json.dump(kept, one)
        stall_if("run")
        if "--cidfile" in flags:
            with open(flags["--cidfile"], "w", encoding="utf-8") as cid:
                cid.write(made)
        print(made)
        sys.exit(0)
    stall_if("run")
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
      kept: Where a detached `run` keeps its container, once a test stalls the daemon.
      swarm: Where a swarm (`swarm`) keeps its services, or None for no swarm.
    """

    bin: Path
    log: Path
    home: Path
    root: Path
    answers: Path
    kept: Path
    swarm: Path | None = None

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

    def services(self) -> list[str]:
        """The services the swarm has now, by name."""
        assert self.swarm is not None
        return sorted(one.stem for one in self.swarm.glob("*.json"))

    def stall(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *subcommands: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Has `docker` never answer `subcommands`, as a daemon that has stopped answering.

        A stalled detached `run` makes its container first, kept where :meth:`containers`
        reads it and with no cidfile written, and a stalled `service create` its service, as
        a slow daemon goes on to: each labelled with `labels` over what it was told.
        """
        monkeypatch.setenv("FAKE_STALLED", ",".join(subcommands))
        monkeypatch.setenv("FAKE_STALLED_LABELS", json.dumps(labels or {}))
        monkeypatch.setenv("FAKE_CONTAINERS", str(self.kept))

    def containers(self) -> list[str]:
        """The containers a detached `run` made, by name, while the daemon was stalled."""
        return sorted(one.stem for one in self.kept.glob("*.json"))


def fakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """Writes `ssh`, `docker` and `container` into a directory on the front of `PATH`."""
    made = Fakes(
        bin=tmp_path / "fake-bin",
        log=tmp_path / "fake-calls.jsonl",
        home=tmp_path / "far-home",
        root=tmp_path / "far-root",
        answers=tmp_path / "fake-answers.json",
        kept=tmp_path / "fake-containers",
    )
    for one in (made.bin, made.home, made.root / "tmp", made.kept):
        one.mkdir(parents=True)
    for name, body in (
        ("ssh", _SSH),
        ("docker", _SWARM + _EXEC),
        ("container", _SWARM + _EXEC),
    ):
        path = made.bin / name
        path.write_text(f"#!{sys.executable}\n{_COMMON}{body}")
        path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{made.bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(made.log))
    monkeypatch.setenv("FAKE_HOME", str(made.home))
    monkeypatch.setenv("FAKE_ROOT", str(made.root))
    monkeypatch.setenv("FAKE_ANSWERS", str(made.answers))
    return made


def swarm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    starting: float = 0.0,
    failing: str = "",
) -> Fakes:
    """The swarm this machine manages, of one node, `n1`, which is this machine.

    Args:
      tmp_path: Where the fakes and the services are kept.
      monkeypatch: What puts them on `PATH`.
      starting: How long, in seconds, each task prepares before it runs.
      failing: What the name of a service whose task fails holds; nothing fails where empty.
    """
    made = replace(fakes(tmp_path, monkeypatch), swarm=tmp_path / "fake-swarm")
    assert made.swarm is not None
    made.swarm.mkdir()
    monkeypatch.setenv("FAKE_SWARM", str(made.swarm))
    monkeypatch.setenv("FAKE_SWARM_STARTING", str(starting))
    monkeypatch.setenv("FAKE_SWARM_FAILING", failing)
    manager = {"LocalNodeState": "active", "ControlAvailable": True, "NodeID": "n1"}
    made.answer("info", json.dumps({"ServerVersion": "27.0", "Swarm": manager}))
    made.answer(
        "node inspect",
        json.dumps(
            [
                {
                    "ID": "n1",
                    "Spec": {"Availability": "active"},
                    "Description": {"Hostname": "alpha", "Resources": {}},
                    "Status": {"State": "ready", "Addr": "10.0.0.7"},
                }
            ]
        ),
    )
    return made


#: `sbatch`, `squeue`, `scancel` and `srun`, for a cluster whose one node is this machine. A
#: job is its `--wrap` run here in a session of its own, in the far home, writing where its
#: `--output` says under the far root; it runs until it is cancelled or ends, and `squeue`
#: says so. `srun --jobid=J ... ARGV` runs ARGV here, as `--export=HOME,USER` leaves it.
_SLURM = """
import signal, subprocess

tool = os.path.basename(sys.argv[0])
note(tool)
state = os.environ["FAKE_SLURM"]
args = sys.argv[1:]

def held(job):
    try:
        with open(os.path.join(state, job + ".json"), encoding="utf-8") as one:
            said = json.load(one)
    except OSError:
        return None
    try:
        os.kill(said["pid"], 0)
    except OSError:
        return None
    return said

if tool == "sbatch":
    fail_if_asked(tool)
    flags = {}
    while args:
        flag = args.pop(0)
        flags[flag] = "" if flag == "--parsable" else args.pop(0)
    jobs = sorted(int(one[:-5]) for one in os.listdir(state) if one.endswith(".json"))
    job = str((jobs[-1] if jobs else 100) + 1)
    output = rooted([flags.get("--output", os.devnull).replace("%j", job)])[0]
    with open(output, "ab") as out:
        made = subprocess.Popen(
            ["/bin/sh", "-c", flags["--wrap"]],
            cwd=flags["--chdir"] if os.path.isdir(flags.get("--chdir", "")) else None,
            env={"HOME": os.environ["FAKE_HOME"], "USER": "me", "PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True,
        )
    with open(os.path.join(state, job + ".json"), "w", encoding="utf-8") as one:
        json.dump({"pid": made.pid, "comment": flags.get("--comment", "")}, one)
    print(job)
elif tool == "squeue":
    asked = args[args.index("--jobs") + 1] if "--jobs" in args else ""
    for name in sorted(os.listdir(state)):
        job = name[:-5]
        said = held(job) if name.endswith(".json") else None
        if said is not None and asked in ("", job):
            print(f"{job}|RUNNING|None|{said['comment']}|localhost")
elif tool == "scancel":
    said = held(args[0])
    if said is not None:
        os.killpg(said["pid"], signal.SIGTERM)
elif tool == "srun":
    fail_if_asked(tool)
    while args and args[0].startswith("--"):
        args.pop(0)
    env = {"HOME": os.environ["FAKE_HOME"], "USER": "me"}
    argv = rooted(args)
    os.execve(argv[0], argv, env)
"""


def slurm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """`sbatch`, `squeue`, `scancel` and `srun` on `PATH`, beside the other fakes."""
    made = fakes(tmp_path, monkeypatch)
    jobs = tmp_path / "fake-slurm"
    jobs.mkdir()
    for name in ("sbatch", "squeue", "scancel", "srun"):
        path = made.bin / name
        path.write_text(f"#!{sys.executable}\n{_COMMON}{_SLURM}")
        path.chmod(0o755)
    monkeypatch.setenv("FAKE_SLURM", str(jobs))
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
