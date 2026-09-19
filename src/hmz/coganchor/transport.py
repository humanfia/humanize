"""Getting a :class:`~hmz.coganchor.proto.Channel` to ``serve`` on the target.

Five ways in, and they are two kinds of thing.

Three of them *start* the serving half and take the pipe they started it down. ``local[:REAL]``
runs it as a child of this process, where ``REAL`` is the directory standing in for the
target's copy of the workspace; ``ssh://[user@]host[:port]`` and ``docker://container`` ship a
self-contained zipapp of coganchor to the far side and run it there, needing nothing installed
but a Python 3. Those three differ in one thing only -- how a command is run over there -- so
they are one road with three prefixes, and :class:`Road` is that road.

Two of them *find* a serving half somebody else started. ``tcp://host:port`` dials one left
listening. ``peer://TICKET@BROKER:PORT`` meets one through
:mod:`hmz.coganchor.rendezvous`, which is the answer where the two halves are on two machines
that cannot dial each other and only humanize can reach both.

What makes the far side cheap is that none of this is paid twice. The zipapp is built once per
source tree and cached by its digest on both sides of the link; an `ssh` reaches a host once
and every later command rides the connection the first one opened; and a road already walked
is not walked again to be told what it already said.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipapp
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hmz import coganchor
from hmz.coganchor.proto import Channel

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hmz.coganchor.rendezvous import Meeting

__all__ = [
    "Road",
    "Target",
    "Transport",
    "build_bundle",
    "bundled",
    "connect",
    "python_command",
    "serve_line",
]

log = logging.getLogger(__name__)

#: Where the bootstrapped copy is cached on a target reached over ssh.  Written with `$HOME`
#: rather than `~`, because the shell that expands it is the one *inside* the line -- the
#: whole line is quoted on its way across, so a `~` would arrive as a directory of that name.
REMOTE_CACHE = "$HOME/.cache/humanize"

#: And in a container, which may have no home directory to speak of and is one user's anyway.
CONTAINER_CACHE = "/tmp/humanize"  # noqa: S108

#: Where a harness put on another machine keeps its mirror of the workspace. *Beside* the
#: archive's cache rather than inside it, and that is not a matter of taste: `~/.cache/humanize`
#: is one of the directories a supervised turn deliberately answers from the machine the agent
#: runs on -- it is humanize's own state, and the whole point of naming it is that it does not
#: cross. A mirror underneath it would be a mirror no path was ever translated through, so the
#: agent would find the workspace empty and every command it ran there would run in the wrong
#: directory. `path_within` is what keeps the two apart, a sibling name not being a prefix.
REMOTE_MIRRORS = "$HOME/.cache/humanize-mirrors"

#: And the same, in a container.
CONTAINER_MIRRORS = "/tmp/humanize-mirrors"  # noqa: S108

#: Where a target may keep a Python, in the order they are tried.  ``python3`` first, which
#: answers on every Linux and on a Mac somebody has set up; then the versioned names, which is
#: what a Homebrew or a python.org install answers to when the bare one was never linked; then
#: the paths those two install at, for a target whose ``PATH`` is the short one a non-login
#: shell gets.  ``/usr/bin/python3`` last: on macOS it is the Command Line Tools shim, which is
#: either an interpreter too old for this or a prompt to install Xcode, and on Linux it is the
#: one ``PATH`` has already found.
PYTHON_CANDIDATES = (
    "python3",
    "python3.14",
    "python3.13",
    "python3.12",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
    "/usr/bin/python3",
)

#: The oldest Python the bundle runs on, which is this project's own floor.
MINIMUM_PYTHON = (3, 12)

#: Installing that copy, for a target reached by piping it there. Written under a name of its
#: own and moved into place, so a session finds the whole archive or none of it, and a copy
#: already there is left where it is: it is named by its digest, so it is the same archive, and
#: rewriting it would be rewriting a file a live session may still be importing from.
#:
#: Quoted at every mention, because the path has a `$HOME` in it and that is the far side's to
#: expand: a home directory with a space in its name would otherwise arrive as two words and
#: the archive would be written somewhere nothing looks for it.
_INSTALL = (
    'mkdir -p "$(dirname -- "{file}")" || exit 1; '
    'if [ ! -s "{file}" ]; then cat > "{file}.part" && mv "{file}.part" "{file}"; '
    "else cat > /dev/null; fi"
)

#: What every `ssh` this reaches for carries. `-T` because the far side is a pipe rather than a
#: terminal, and the keepalive so that a session held open across a long turn is not dropped by
#: something counting idle seconds.
_SSH_OPTIONS = ("-T", "-o", "BatchMode=no", "-o", "ServerAliveInterval=30")

#: And what makes the second command to a host cost nothing: the first one leaves a master
#: connection behind, and every later one rides it rather than paying for a TCP handshake, a
#: key exchange and an authentication of its own. A turn against a remote target opens several
#: -- install the bundle, start the serving half, and whatever the harness itself needs -- so
#: this is most of the difference between an anchored turn starting now and starting in a
#: second. Unset `HUMANIZE_SSH_REUSE` to a falsy value on a host whose sshd refuses multiplexing.
_SSH_REUSE = ("-o", "ControlMaster=auto", "-o", "ControlPersist=120")

#: Finding an interpreter, in POSIX sh, because this runs on the target before anything of
#: humanize exists there.  Each candidate is *run* rather than merely looked for: macOS's
#: ``/usr/bin/python3`` is a shim that is there whether or not an interpreter is behind it,
#: and answers with a prompt to install Xcode when none is.  What it is asked is its version,
#: so a target whose only Python is older than the bundle needs is passed over here rather
#: than failing on a syntax error a frame later.  A target with none at all is told what was
#: looked for, since what to do about it is to install one of them.
_FIND_PYTHON = (
    "for py in {candidates}; do "
    'command -v "$py" >/dev/null 2>&1 || continue; '
    '"$py" -c "import sys; sys.exit(sys.version_info < {minimum})" >/dev/null 2>&1 '
    "|| continue; "
    "{run}; "
    "done; "
    'echo "humanize: no python {version} or newer on this machine; '
    'looked for: {candidates}" >&2; '
    "exit 127"
)


def python_command(
    args: list[str], bundle: str = "", setting: Sequence[tuple[str, str]] = ()
) -> list[str]:
    """The command that runs ``args`` under the target's Python, wherever it keeps one.

    Argv, so that a path holding a space or a quote reaches the target as it is.  Called with
    nothing it is the part that does the finding, which is what whoever has to hand a target
    one string instead -- ``ssh`` does -- quotes before writing its own arguments after it.

    Args:
      args: What to run, after the interpreter or after the archive.
      bundle: The archive to run, as the *target's* shell will read it, so that a `$HOME` in
        it is expanded on the machine it names a directory on. Empty runs the interpreter
        itself, which is what looking for one is.
      setting: Variables to export first, whose values are read by the shell on the far side
        -- which is the only way to name that machine's home directory, since everything in
        `args` crosses as the word it already is.

    Returns:
      The argv to run over there.
    """
    script = _FIND_PYTHON.format(
        candidates=" ".join(PYTHON_CANDIDATES),
        minimum=f"({MINIMUM_PYTHON[0]}, {MINIMUM_PYTHON[1]})",
        version=".".join(str(part) for part in MINIMUM_PYTHON),
        run=f'exec "$py" "{bundle}" "$@"' if bundle else 'exec "$py" "$@"',
    )
    # In front of the search rather than inside it, so a variable is set whichever
    # interpreter answers -- and `mkdir` with it, since a directory named by one of these is
    # one the far side has to have and nothing over there is going to make it first.
    for name, value in setting:
        script = (
            f'{name}="{value}"; export {name}; mkdir -p "${name}" || exit 1; ' + script
        )
    # ``/bin/sh`` by its path rather than its name, since the ``PATH`` this is reaching past
    # is the same one that would have to hold a shell.  ``$0`` is what sh prefixes its own
    # complaints with, so it is named for whose command this is.
    return ["/bin/sh", "-c", script, "humanize", *args]


@dataclass(frozen=True, slots=True)
class Target:
    """Where the target is."""

    scheme: str
    host: str = ""
    port: int = 0
    path: str = ""

    @classmethod
    def parse(cls, spec: str) -> Target:
        """Reads a target spelling.

        Args:
          spec: One of the five, as the command line and the settings both write them.

        Returns:
          The target it names.

        Raises:
          ValueError: If it is not one of them, or is one of them spelled wrongly.
        """
        if spec == "local" or spec.startswith("local:"):
            _, _, path = spec.partition(":")
            return cls("local", path=path)
        if spec.startswith("ssh://"):
            authority = spec[len("ssh://") :]
            host, _, port = authority.rpartition(":")
            if host and port.isdigit():
                return cls("ssh", host=host, port=int(port))
            return cls("ssh", host=authority)
        if spec.startswith("docker://") and (container := spec[len("docker://") :]):
            return cls("docker", host=container)
        if spec.startswith("tcp://"):
            host, _, port = spec[len("tcp://") :].rpartition(":")
            if not host or not port.isdigit():
                raise ValueError(f"malformed target {spec!r}; expected tcp://HOST:PORT")
            return cls("tcp", host=host, port=int(port))
        if spec.startswith("peer://"):
            from hmz.coganchor.rendezvous import Meeting

            met = Meeting.parse(spec[len("peer://") :])
            return cls("peer", host=met.host, port=met.port, path=met.ticket)
        raise ValueError(
            f"unsupported target {spec!r}; expected ssh://HOST, docker://CONTAINER, "
            "tcp://HOST:PORT, peer://TICKET@HOST:PORT or local[:PATH]"
        )

    def describe(self) -> str:
        """Its own spelling back, so that what is logged is what could be typed."""
        if self.scheme == "ssh":
            return f"ssh://{self.host}" + (f":{self.port}" if self.port else "")
        if self.scheme == "docker":
            return f"docker://{self.host}"
        if self.scheme == "tcp":
            return f"tcp://{self.host}:{self.port}"
        if self.scheme == "peer":
            return f"peer://{self.path}@{self.host}:{self.port}"
        return f"local{':' + self.path if self.path else ''}"

    @property
    def meeting(self) -> Meeting:
        """The meeting a `peer://` target names.

        Raises:
          ValueError: If this is not one, there being no meeting to answer with.
        """
        if self.scheme != "peer":
            raise ValueError(f"{self.describe()} is not a meeting")
        from hmz.coganchor.rendezvous import Meeting

        return Meeting(self.path, self.host, self.port)


@dataclass(frozen=True, slots=True)
class Road:
    """How a command is run on the machine a target names.

    The one thing the three bootstrapping targets differ in, and so the one thing written
    down per target rather than per caller. Given an argv it answers with the argv *this*
    machine runs to have it happen over there: nothing at all for a local target, an `ssh`
    carrying one quoted string for a host, a `docker exec` carrying argv straight through for
    a container.

    Attributes:
      target: The machine.
      prefix: What goes in front of a command to send it there.
      quotes: Whether the far side reads the line through a shell before running it, and so
        whether every word has to survive that reading.
      cache: Where the bundle is kept over there, as that machine's own shell reads it.
      mirrors: And where a harness running there keeps its mirrors, which is somewhere else
        again -- see :data:`REMOTE_MIRRORS` for why it may not be under `cache`.
    """

    target: Target
    prefix: tuple[str, ...]
    quotes: bool
    cache: str
    mirrors: str

    @classmethod
    def to(cls, target: Target) -> Road:
        """The road to one target.

        Args:
          target: Where the work lands.

        Returns:
          The road, for a target that is reached by starting something on it.

        Raises:
          ValueError: For a target that is not -- `tcp://` and `peer://` name a serving half
            somebody else started, and there is no command to run on the far side of either.
        """
        if target.scheme == "local":
            return cls(target, (), quotes=False, cache="", mirrors="")
        if target.scheme == "ssh":
            port = ("-p", str(target.port)) if target.port else ()
            return cls(
                target,
                ("ssh", *_SSH_OPTIONS, *_reuse(), *port, target.host),
                quotes=True,
                cache=REMOTE_CACHE,
                mirrors=REMOTE_MIRRORS,
            )
        if target.scheme == "docker":
            return cls(
                target,
                ("docker", "exec", "-i", target.host),
                quotes=False,
                cache=CONTAINER_CACHE,
                mirrors=CONTAINER_MIRRORS,
            )
        raise ValueError(f"nothing is started on the far side of {target.describe()}")

    def line(self, argv: Sequence[str]) -> list[str]:
        """The argv this machine runs to have `argv` run over there.

        Args:
          argv: What to run on the target, as the target's own `execve` would take it.

        Returns:
          The local command. Every word of `argv` survives whatever reads it on the way,
          which is what makes a workspace path holding a space no different from one that
          does not.
        """
        if not self.quotes:
            return [*self.prefix, *argv]
        # One string for ssh, which hands it to the login shell there before anything runs.
        # Quoted whole, so that shell passes the words on rather than acting on them -- and
        # `exec` in front, so the shell becomes the command instead of waiting on it.
        return [*self.prefix, " ".join(["exec", *(shlex.quote(word) for word in argv)])]

    def run(
        self, argv: Sequence[str], feeding: bytes = b""
    ) -> subprocess.CompletedProcess[bytes]:
        """Runs one short command over there and waits for it.

        Args:
          argv: What to run.
          feeding: What to put on its input.

        Returns:
          What it did, with both its streams captured.
        """
        return subprocess.run(
            self.line(argv), input=feeding, capture_output=True, check=False
        )

    def mirror(self, named: str) -> str:
        """Where a harness on this machine keeps its mirror of the workspace.

        Named for what it mirrors rather than for the turn using it: a mirror kept between
        turns is a workspace whose files are already there the second time, which is the one
        saving worth more than every other here put together. And beside the archive's cache
        rather than inside it -- :data:`REMOTE_MIRRORS` is where that is argued.

        Args:
          named: What tells this mirror from the others, being a digest of what it mirrors.

        Returns:
          The path, as that machine's own shell reads it.
        """
        return f"{self.mirrors}/{named}"

    def hmz(
        self, argv: Sequence[str], *, setting: Sequence[tuple[str, str]] = ()
    ) -> list[str]:
        """The argv this machine runs to have `hmz internal ...` run over there.

        The bundle is installed on the way, and installed once: it is named by its digest, so
        a machine that already has this one is left with it and this process does not ask a
        second time.

        Args:
          argv: What follows `hmz`, e.g. `["internal", "anchor", "serve", "--stdio"]`.
          setting: Variables the far side exports before running it, and makes a directory
            of each -- which is how a mirror lands under that machine's own home rather than
            under a path this machine guessed for it.

        Returns:
          The local command to spawn.

        Raises:
          ConnectionError: If the bundle cannot be put on the target.
        """
        if self.target.scheme == "local":
            return [*_myself(), *argv]
        return self.line(
            python_command(list(argv), bundle=self.installed(), setting=setting)
        )

    def installed(self) -> str:
        """Puts the bundle on the target if it is not already there, and says where.

        Returns:
          The archive's path over there, as that machine's shell reads it.

        Raises:
          ConnectionError: If it cannot be written.
        """
        archive, digest = bundled()
        where = f"{self.cache}/humanize-{digest}.pyz"
        # One push per machine per bundle for the life of this process. The archive is named
        # by what is in it, so a second push would write the same bytes over the same path --
        # a round trip, and a file a live session may be importing from, for no news. Asked
        # before the archive is read, so a machine that already has it costs no megabyte of
        # this one's memory either.
        already = (self.target.describe(), digest)
        with _PUSHED_LOCK:
            if already in _PUSHED:
                return where
        result = self.run(
            ["/bin/sh", "-c", _INSTALL.format(file=where)], archive.read_bytes()
        )
        if result.returncode != 0:
            raise ConnectionError(
                f"could not install humanize on {self.target.describe()}: "
                f"{result.stderr.decode(errors='replace').strip()}"
                f"{self._said()}"
            )
        with _PUSHED_LOCK:
            _PUSHED.add(already)
        return where

    def _said(self) -> str:
        """The tail of what a container printed, for an error that does not say enough.

        A container whose own process could not start is one docker then reports as merely
        not running; why it could not -- that there is no Python it can use, and where it was
        looked for -- was said on the way out and is in the log and nowhere else.
        """
        if self.target.scheme != "docker":
            return ""
        said = subprocess.run(
            ["docker", "logs", "--tail", "3", self.target.host],
            capture_output=True,
            check=False,
        )
        if said.returncode != 0:
            # There is no container to have said anything, or no daemon to ask -- which is
            # what the error being written already says, and saying it twice says less.
            return ""
        # Both streams: what a container printed on its way out is on the one it chose.
        tail = (said.stdout + said.stderr).decode(errors="replace").strip()
        return f"; the container said: {tail}" if tail else ""


#: Which machines already hold which bundle, so that a road walked twice is not paid for
#: twice. The target *whole* rather than its host, because two machines can answer to one
#: name -- `ssh://box:2201` and `ssh://box:2202` are two of them -- and a memo that could not
#: tell them apart is a second machine left without the archive it is about to be asked to
#: run. And the digest, because a rebuilt bundle is a different file.
_PUSHED: set[tuple[str, str]] = set()
_PUSHED_LOCK = threading.Lock()


def _myself() -> list[str]:
    """How this process starts another humanize on the machine it is already running on.

    Two answers, because there are two ways this code is ever running. Installed, it is a
    module and `-m` reaches it. Inside the archive a target was bootstrapped with, there is no
    installed `hmz` to import and `-m hmz` would find nothing -- which is exactly the case a
    harness put on another machine is in when it starts a serving half beside itself, that
    being how the work and the harness land on one machine. The archive knows its own path,
    so it is asked for it.
    """
    archive = getattr(getattr(coganchor, "__loader__", None), "archive", "")
    return [sys.executable, str(archive)] if archive else [sys.executable, "-m", "hmz"]


#: The archive this process last built, as `(stamp, path, digest)`. The digest is what a
#: target caches the archive under, and reading a megabyte off disk to work it out again is
#: what asking for it a second time would otherwise cost.
_bundle_held: tuple[str, Path, str] | None = None
_BUNDLING = threading.Lock()


def bundled() -> tuple[Path, str]:
    """The archive for the current source tree, and the name a target caches it under.

    Returns:
      Where it is, and the digest of what is in it.
    """
    global _bundle_held  # noqa: PLW0603 -- one archive per process, per source tree
    stamp = _stamped(Path(coganchor.__file__).parent)
    with _BUNDLING:
        if _bundle_held is not None and _bundle_held[0] == stamp:
            return _bundle_held[1], _bundle_held[2]
        archive = build_bundle()
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
        _bundle_held = (stamp, archive, digest)
        return archive, digest


#: The ssh options that make one connection serve every command, worked out once. Making the
#: directory they name is a syscall per command otherwise, for an answer that cannot change.
_reusing_held: tuple[str, ...] | None = None


def _reuse() -> tuple[str, ...]:
    """The options that let the second `ssh` to a host ride the first one's connection.

    The socket lives under this user's runtime directory where there is one and in the
    temporary directory otherwise, named by `%C` -- ssh's own digest of host, port and user,
    which is short, which matters: a unix socket path has about a hundred bytes to live in and
    a home directory can spend most of them.
    """
    global _reusing_held  # noqa: PLW0603 -- one answer per process, for a question with one
    if _reusing_held is not None:
        return _reusing_held
    if os.environ.get("HUMANIZE_SSH_REUSE", "1") in ("0", "no", "false", ""):
        _reusing_held = ()
        return _reusing_held
    under = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    control = os.path.join(under, f"humanize-ssh-{os.getuid()}")
    try:
        os.makedirs(control, mode=0o700, exist_ok=True)
    except OSError:
        _reusing_held = ()
    else:
        _reusing_held = (*_SSH_REUSE, "-o", f"ControlPath={control}/%C")
    return _reusing_held


@dataclass(slots=True)
class Transport:
    """An open channel plus whatever process is keeping it alive."""

    channel: Channel
    process: subprocess.Popen[bytes] | None = None

    def close(self) -> None:
        self.channel.close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                # Reaped rather than left: a run that opens an anchor per agent would
                # otherwise gather a zombie for each one that would not go quietly.
                self.process.wait()


def serve_line(
    target: Target, exports: list[str], *, meeting: Meeting | None = None
) -> list[str]:
    """The command that leaves a serving half answering on the target.

    Args:
      target: The machine it runs on.
      exports: The directories it may name, as `VIRTUAL[:REAL]`.
      meeting: Where to go and be met, for a serving half whose other half is on a third
        machine. None serves the one session over its own stdin and stdout, which is what a
        half this process started down a pipe answers on.

    Returns:
      The local argv to spawn.

    Raises:
      ValueError: If nothing is started on the far side of this target.
      ConnectionError: If the bundle cannot be put there.
    """
    how = ["--peer", str(meeting)] if meeting is not None else ["--stdio"]
    asked: list[str] = []
    for export in exports:
        asked += ["--export", export]
    return Road.to(target).hmz(["internal", "anchor", "serve", *how, *asked])


def connect(target: Target, exports: list[str], token: str | None = None) -> Transport:
    """Open a channel to the ``serve`` side described by ``target``.

    Args:
      target: Where it is, or how to be introduced to it.
      exports: The directories a session may name, for a serving half this starts.
      token: The secret a listening target asks for.

    Returns:
      The channel, and the process holding it open where this started one.

    Raises:
      OSError: If the target cannot be reached.
      ValueError: If the target cannot be read.
    """
    if target.scheme == "tcp":
        sock = socket.create_connection((target.host, target.port), timeout=30.0)
        sock.settimeout(None)
        # Nagle off, the way a punched socket has it off: this protocol is a small request
        # and a small reply, over and over, and a delay waiting for a second frame that is
        # not coming is a delay per syscall the agent makes.
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return Transport(Channel.from_socket(sock))
    if target.scheme == "peer":
        from hmz.coganchor import rendezvous

        met = rendezvous.dial(target.meeting, rendezvous.ANCHOR)
        return Transport(Channel.from_socket(met))
    return _spawn(serve_line(target, exports), token)


def _spawn(command: list[str], token: str | None) -> Transport:
    """Start a child that serves over its own stdin and stdout.

    The token travels in the environment the child inherits, which works for
    ``local``.  For ``ssh`` and ``docker`` the child is the client rather than
    the target and neither forwards the environment, so those sessions are
    authenticated by ssh and by the docker socket themselves and the token goes
    unused.
    """
    log.debug("starting the target: %s", " ".join(command))
    env = dict(os.environ)
    if token:
        env["HUMANIZE_TOKEN"] = token
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        env=env,
        close_fds=True,
    )
    assert process.stdin is not None  # noqa: S101
    assert process.stdout is not None  # noqa: S101
    return Transport(Channel(process.stdout, process.stdin), process)


#: What the target has no use for, left out of the bundle by name. This package is two
#: things: the anchor -- the wire, the supervisor and the serving half, which is what a
#: target runs -- and everything humanize knows about driving a coding agent CLI, which a
#: target never does. The anchor half ships whole, ptrace layer and register maps included,
#: because pruning *that* would be a list to keep in step and nothing is lost by carrying
#: it: the target only ever runs ``anchor serve``, which reaches none of it. The driving
#: half is a different answer -- it is megabytes of drivers, it reaches the network to read
#: prices and catalogues, and no line the target runs can arrive at it. It is named here
#: rather than inferred, and ``test_the_bundle_carries_nothing_that_drives_an_agent`` is
#: what notices a new one.
DRIVING = ("agents", "providers", "machines", "backends.py", "models.py", "fallbacks.py",
           "prices.py")  # fmt: skip


def build_bundle(destination: Path | None = None) -> Path:
    """Package the anchor, and the command line reaching it, as a zipapp for the target.

    The anchor half of this package ships whole -- see :data:`DRIVING` for what does not and
    why.  Nothing is lost by carrying the tracer with it: the target only ever runs ``anchor
    serve``, which :func:`hmz.cli.main` reaches without importing the modules that need
    ptrace or an x86-64 register map -- nor any other subpackage, none of which is here -- so
    the bundle runs on a target of any architecture.  It is pure stdlib, so a host needs
    nothing but ``python3``.

    Built once per source tree rather than once per session. The archive is a function of the
    source alone, so an unchanged tree is an unchanged archive, and a stamp beside it says
    which tree the one already there was made from -- which is a few hundred `stat` calls
    against copying the package, zipping it and rewriting every mode and timestamp in it,
    every time an agent is anchored.

    Args:
      destination: Where to write it, defaulting to one shared path per user.

    Returns:
      Where it is.
    """
    if destination is None:
        destination = Path(tempfile.gettempdir()) / f"humanize-{os.getuid()}.pyz"
    source = Path(coganchor.__file__).parent
    stamp = destination.with_suffix(".stamp")
    made = _stamped(source)
    if destination.exists() and _read(stamp) == made:
        return destination

    def stamping(staged: Path) -> None:
        staged.write_text(f"{made}\n")

    _publish(destination, lambda staged: _write_bundle(source, staged))
    # The stamp after the archive, and only if it was written: a stamp that got there first
    # would let a run that died mid-build be read as a build that finished.
    _publish(stamp, stamping)
    return destination


def _stamped(source: Path) -> str:
    """What the source tree is now, cheaply enough to ask before every session.

    Sizes and modification times rather than contents: reading the package to decide whether
    to rebuild it costs as much as rebuilding it, while the questions a filesystem answers
    from the directory entry it already has cost nothing worth measuring. An edit that keeps
    a file's size and its timestamp to the nanosecond is the one this would miss, and there
    is no way to make one by accident.
    """
    seen = hashlib.sha256()
    for path in sorted(source.rglob("*")):
        if "__pycache__" in path.parts or path.is_dir():
            continue
        found = path.stat()
        seen.update(
            f"{path.relative_to(source)}\0{found.st_size}\0{found.st_mtime_ns}\n".encode()
        )
    return seen.hexdigest()


def _read(path: Path) -> str:
    """What a stamp says, or nothing at all where there is none to read."""
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _publish(destination: Path, writing: Callable[[Path], None]) -> None:
    """Puts a file in place whole or not at all, by writing it elsewhere and moving it there.

    Two sessions starting at once build the same bytes to the same path, and a reader must
    find the whole file or the last one, never a half-written archive it would then ship to a
    target.

    Args:
      destination: Where it goes.
      writing: What fills it, given the name to write under.

    Raises:
      OSError: Whatever `writing` raises, with nothing of the attempt left behind.
    """
    handle, staged = tempfile.mkstemp(
        dir=destination.parent, prefix=f"{destination.name}."
    )
    os.close(handle)
    try:
        writing(Path(staged))
        os.replace(staged, destination)
    except BaseException:
        os.unlink(staged)  # a write that failed leaves nothing of itself behind
        raise


def _write_bundle(source: Path, destination: Path) -> None:
    """Builds the archive itself, which is what a changed source tree costs.

    Args:
      source: The package to put in it.
      destination: Where to write it, which :func:`_publish` is what moves into place.
    """
    with tempfile.TemporaryDirectory(prefix="humanize-bundle-") as staging:
        root = Path(staging)
        # Laid out under the package's own dotted name, so that moving the package moves the
        # bundle with it rather than breaking on the target, which is where it would surface.
        parts = coganchor.__name__.split(".")
        shutil.copytree(
            source,
            root.joinpath(*parts),
            ignore=shutil.ignore_patterns("__pycache__", "*.md", *DRIVING),
        )
        for depth in range(1, len(parts)):
            # A namespace of its own rather than the installed ``hmz/__init__.py``: the
            # bundle stays pure stdlib however the rest of humanize grows, and a regular package
            # cannot be shadowed by an unrelated ``hmz`` already on the target's path.
            init = root.joinpath(*parts[:depth]) / "__init__.py"
            init.write_text(
                f'"""{".".join(parts[:depth])}, cut down to {parts[depth]}."""\n'
            )
        # The command line comes too, because it is the only one: what the target runs is the
        # same ``hmz internal anchor`` a user would run there, and each of its commands names
        # the layers it needs only from inside itself, none of which is this one.
        # Taken off disk rather than imported, so that the serving half still names nothing
        # above itself.
        shutil.copytree(
            source.parent / "cli",
            root.joinpath(*parts[:-1]) / "cli",
            ignore=shutil.ignore_patterns("__pycache__", "*.md"),
        )
        # Written by hand rather than via zipapp's ``main=`` shim, which calls
        # the entry point but throws its return value away -- a target that
        # failed to start would then look like a clean exit.
        (root / "__main__.py").write_text(
            "from hmz.cli import main\n\nraise SystemExit(main())\n"
        )
        # One timestamp for everything, so the archive is a function of the source alone: the
        # bundle is addressed on the target by its digest, and a build stamp would miss that
        # cache on every connect and leave another copy behind. A zip entry holds local
        # wall-clock time and cannot predate 1980, so the instant is the one reading as
        # 1980-01-02 here: a fixed instant would fall out of that range west of UTC, and would
        # still leave the digest following the machine's timezone.
        when = time.mktime((1980, 1, 2, 0, 0, 0, 0, 2, -1))
        for path in root.rglob("*"):
            # Modes for the same reason: the files written just above carry the builder's
            # umask, and a checkout's own bits vary with it too. Nothing on the target reads
            # them -- it runs the archive, and zipimport ignores the entries' modes.
            path.chmod(0o755 if path.is_dir() else 0o644)
            os.utime(path, (when, when))
        zipapp.create_archive(root, destination, interpreter="/usr/bin/env python3")
