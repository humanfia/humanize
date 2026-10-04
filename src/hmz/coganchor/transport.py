"""Getting a :class:`~hmz.coganchor.proto.Channel` to ``serve`` on the target.

Five ways in, and they are two kinds of thing.

Three of them *start* the serving half and take the pipe they started it down. ``local[:REAL]``
runs it as a child of this process, where ``REAL`` is the directory standing in for the
target's copy of the workspace; ``ssh://[user@]host[:port]`` and
``docker://container[@endpoint]`` ship a self-contained zipapp of coganchor to the far side and
run it there, needing nothing installed but a Python 3. Those three differ in one thing only --
how a command is run over there -- so they are one road with three prefixes, and :class:`Road`
is that road. A container's prefix names the daemon holding it, which :class:`Endpoint` is.

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

import contextlib
import hashlib
import logging
import os
import re
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
from hmz.coganchor import atomic
from hmz.coganchor.proto import Channel

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hmz.coganchor.rendezvous import Meeting

__all__ = [
    "Endpoint",
    "Road",
    "Target",
    "Transport",
    "build_bundle",
    "bundled",
    "connect",
    "python_command",
    "serve_line",
    "ssh_flags",
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

#: How many hex digits of an archive's SHA-256 name it, here and on every target.
_DIGEST = 16

#: How long an archive nothing has asked for is kept, here and on a target, before the next
#: one built or installed beside it sweeps it away. By age rather than by count, because the
#: only archive it is unsafe to remove is one a run is still using, and every run touches the
#: one it uses each time it asks for it: an archive left alone this long belongs to a checkout
#: or a version nobody is running.
_KEPT_FOR = 14 * 24 * 3600

#: Installing that copy, for a target reached by piping it there, in the target's own Python
#: because that is the one thing it is certain to have that can take a digest. What arrived is
#: checked against the digest it was sent as, and a copy already there against the same digest
#: before it is believed: a name is only a promise, and a copy a run cut short or a humanize of
#: another checkout left under it would otherwise be the code every later session on that
#: machine runs. A copy that answers is left where it is, touched so the sweep below counts it
#: as used -- rewriting it would be rewriting a file a live session may still be importing
#: from; one that does not is replaced.
#:
#: Written under a name of its own and moved into place, so a session finds the whole archive
#: or none of it. That name carries the writer's pid, because two sessions bootstrapping one
#: machine at the same moment is the ordinary case rather than the unlucky one -- a fleet
#: coming up does it by the hundred.
#:
#: The cache's own path is the far side's shell's to expand and make, which is what
#: :func:`_installing` has it do, since it has a `$HOME` in it that only that machine can say.
#: Then every other archive and half-written copy nobody has touched in `_KEPT_FOR` seconds
#: goes.
_INSTALL_SOURCE = f"""\
import hashlib, os, sys, time
cache = os.environ["HUMANIZE_BUNDLES"]
name, want, kept = sys.argv[1], sys.argv[2], float(sys.argv[3])
path = os.path.join(cache, name)
came = sys.stdin.buffer.read()
if hashlib.sha256(came).hexdigest()[:{_DIGEST}] != want:
    sys.exit(f"humanize: {{len(came)}} bytes arrived that are not {{name}}")
try:
    with open(path, "rb") as held:
        there = hashlib.file_digest(held, "sha256").hexdigest()[:{_DIGEST}]
except OSError:
    there = ""
if there == want:
    try:
        os.utime(path)
    except FileNotFoundError:
        there = ""
    except OSError:
        pass
if there != want:
    staged = f"{{path}}.{{os.getpid()}}"
    try:
        with open(staged, "wb") as writing:
            writing.write(came)
            writing.flush()
            os.fsync(writing.fileno())
        os.replace(staged, path)
    except BaseException:
        if os.path.exists(staged):
            os.unlink(staged)
        raise
now = time.time()
for one in os.scandir(cache):
    if one.name.startswith("humanize-") and ".pyz" in one.name and one.name != name:
        try:
            if now - one.stat(follow_symlinks=False).st_mtime > kept:
                os.unlink(one.path)
        except OSError:
            pass
"""

#: And the same as one line, which is what crosses: a word with newlines in it is one that
#: every log of a command line, and every stand-in for `ssh`, reads as several.
_INSTALLING = f"exec({_INSTALL_SOURCE!r})"


def _installing(cache: str, name: str, digest: str) -> list[str]:
    """The command that installs an archive arriving on its input, on the far side.

    Args:
      cache: The directory it goes in, as that machine's own shell spells it.
      name: What it is called there.
      digest: What its SHA-256 has to start with, there and on its way.

    Returns:
      The argv to run over there.
    """
    return python_command(
        ["-c", _INSTALLING, name, digest, str(_KEPT_FOR)],
        setting=(("HUMANIZE_BUNDLES", cache),),
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
#: second. It is on unless `HUMANIZE_SSH_REUSE` says `off`, `0`, `no` or `false` -- trimmed and in
#: any case -- or is set and empty, which is for a machine whose sshd refuses multiplexing.
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
    if bundle:
        # Touched by every line that runs it, so the sweep an install of another version makes
        # on that machine never counts an archive a run of this one is still starting from as
        # one nobody uses -- a process pushes it once, and may go on running it for weeks.
        script = f'touch -c "{bundle}" 2>/dev/null; ' + script
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


#: What a `docker` sent to any daemon but this machine's default is run without. Each of them
#: would take the command somewhere its endpoint does not say: `DOCKER_HOST` and
#: `DOCKER_CONTEXT` name another daemon, and the other three turn TLS on -- which no flag can
#: turn off again, docker reading even `--tlsverify=false` as a request for it.
_DOCKER_AMBIENT = (
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_TLS",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
)


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Which docker daemon a container is reached through.

    Written the way docker's own `--host` and `--context` write one, so that what a setting
    says is what `docker` is told: `local` for docker's default here, `unix:///PATH`,
    `tcp://HOST:PORT` with `?tls=DIR` for a verified one, `ssh://[USER@]HOST[:PORT]` with
    `?KEYWORD=VALUE&...` for what its `ssh` is told besides, or `context:NAME`. `ssh://` is
    docker's own transport, so it is the daemon's host that needs an sshd and a `docker`, and
    never the container.

    Attributes:
      host: docker's `--host` for it, or "" for a context or for the default.
      context: The docker context it is reached by, or "".
      certs: For a `tcp://` host, the directory holding its `ca.pem`, `cert.pem` and `key.pem`
        -- docker's own `DOCKER_CERT_PATH` layout -- or "" for plain TCP.
      options: For an `ssh://` host, what its `ssh` is told besides the login, the port and
        the host, as :attr:`Target.options` holds them. Docker dials with the `ssh` on `PATH`
        and tells it nothing else, so these reach it through an `ssh` of their own put in
        front of the real one: see :meth:`docker`.
    """

    host: str = ""
    context: str = ""
    certs: str = ""
    options: tuple[tuple[str, str], ...] = ()

    @classmethod
    def parse(cls, spec: str) -> Endpoint:
        """Reads an endpoint spelling.

        Args:
          spec: One of the five, or "" for `local`.

        Returns:
          The daemon it names.

        Raises:
          ValueError: If it is not one of them, or is one of them spelled wrongly.
        """
        if spec in ("", "local"):
            return cls()
        if spec.startswith("context:") and spec[len("context:") :]:
            return cls(context=spec[len("context:") :])
        if spec.startswith("unix:///"):
            return cls(host=spec)
        if spec.startswith("ssh://"):
            authority, _, query = spec[len("ssh://") :].partition("?")
            if authority.rpartition("@")[2] and not set("/#") & set(authority):
                try:
                    options = _ssh_options(query, spec)
                except ValueError:
                    options = None
                if options is not None:
                    return cls(host=f"ssh://{authority}", options=options)
        if spec.startswith("tcp://"):
            address, asks, certs = spec[len("tcp://") :].partition("?tls=")
            host, _, port = address.rpartition(":")
            if host and port.isdigit() and (not asks or certs.startswith("/")):
                return cls(host=f"tcp://{address}", certs=certs)
        raise ValueError(
            f"unsupported docker endpoint {spec!r}; expected local, unix:///PATH, "
            "tcp://HOST:PORT[?tls=DIR], ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...] or "
            "context:NAME"
        )

    def __str__(self) -> str:
        """Its own spelling back, which :meth:`parse` reads as this endpoint again."""
        if self.context:
            return f"context:{self.context}"
        if self.certs:
            return f"{self.host}?tls={self.certs}"
        if self.options:
            from urllib.parse import quote, urlencode

            return f"{self.host}?" + urlencode(
                self.options, quote_via=quote, safe="/~:@,"
            )
        return self.host or "local"

    @property
    def here(self) -> bool:
        """Whether the daemon is this machine's, and so sees the files this one does.

        A socket is, and so is docker's default unless this process's `DOCKER_HOST` sends it
        somewhere that is not one. A daemon reached over the network, over ssh, or through a
        context -- which may be either -- is answered for as one that is not.
        """
        if self.context:
            return False
        host = self.host or os.environ.get("DOCKER_HOST", "")
        return not host or host.startswith("unix://")

    def docker(self, *argv: str) -> list[str]:
        """The `docker` command that runs `argv` against this daemon and no other.

        Docker's default is left to find itself, the way `docker` run by hand finds it. Any
        other is said on the command line, with the variables that would redirect it taken
        off on the way: every command for one container has to reach the daemon holding it,
        whatever the environment of whichever process happens to be asking. An `ssh://` one
        with options is dialled through an `ssh` told them, first on the `PATH` it runs with.

        Args:
          argv: The docker subcommand and its arguments.

        Returns:
          The argv to run here.

        Raises:
          OSError: If the `ssh` an endpoint's options need cannot be written.
        """
        if not self.host and not self.context:
            return ["docker", *argv]
        said = ["--context", self.context] if self.context else ["--host", self.host]
        if self.certs:
            said += ["--tlsverify"]
            for flag, pem in (
                ("--tlscacert", "ca"),
                ("--tlscert", "cert"),
                ("--tlskey", "key"),
            ):
                said += [flag, os.path.join(self.certs, f"{pem}.pem")]
        unset = [word for name in _DOCKER_AMBIENT for word in ("-u", name)]
        if self.options:
            shim = _ssh_shim(self.options)
            unset.append(f"PATH={shim}{os.pathsep}{os.environ.get('PATH', os.defpath)}")
        return ["env", *unset, "docker", *said, *argv]


def _ssh_shim(options: Sequence[tuple[str, str]]) -> str:
    """The directory holding an `ssh` that tells the real one these options first.

    Docker's own ssh transport runs whichever `ssh` is first on `PATH` and hands it the login,
    the port and the host alone, so what else a daemon's host needs -- a key, a jump host, a
    config of its own -- is said by one of these instead. One per set of options, named by
    their digest under humanize's home and this user's alone, written once and whole; it takes
    its own directory off `PATH` again before running the real one.

    Args:
      options: `(KEYWORD, VALUE)` pairs, as :attr:`Target.options` holds them.

    Returns:
      The directory, for the front of `PATH`.

    Raises:
      OSError: If it cannot be written.
    """
    from hmz import home

    flags = " ".join(shlex.quote(flag) for flag in ssh_flags(options))
    at = home() / "docker-ssh" / hashlib.sha256(flags.encode()).hexdigest()[:16]
    if str(at) in _SHIMS:
        return str(at)
    script = (
        "#!/bin/sh\n"
        "# The ssh docker dials its daemon's host through, told what the endpoint says.\n"
        f"PATH=${{PATH#{shlex.quote(str(at) + os.pathsep)}}}\n"
        f'exec ssh {flags} "$@"\n'
    )
    ssh = at / "ssh"
    if _read(ssh) == script.strip():
        _SHIMS.add(str(at))
        return str(at)
    at.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, staged = tempfile.mkstemp(dir=at, prefix=".ssh.", suffix=".new")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(script)
        os.chmod(staged, 0o700)
        os.replace(staged, ssh)
    except OSError:
        Path(staged).unlink(missing_ok=True)
        raise
    _SHIMS.add(str(at))
    return str(at)


#: The `ssh` shims this process has written or found whole, so each is looked at once.
_SHIMS: set[str] = set()


@dataclass(frozen=True, slots=True)
class Target:
    """Where the target is.

    Attributes:
      options: For an ssh target, what its `ssh` is told besides the destination, as
        `(KEYWORD, VALUE)` pairs: each an ssh_config keyword, passed as `-o KEYWORD=VALUE`,
        but for `F`, the config file ssh reads instead of the user's own (`-F VALUE`).
        Spelled after a `?` in the target, `&` between them, each value URL-quoted.
    """

    scheme: str
    host: str = ""
    port: int = 0
    path: str = ""
    options: tuple[tuple[str, str], ...] = ()

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
            authority, _, query = spec[len("ssh://") :].partition("?")
            options = _ssh_options(query, spec)
            host, _, port = authority.rpartition(":")
            if host and port.isdigit():
                return cls("ssh", host=host, port=int(port), options=options)
            return cls("ssh", host=authority, options=options)
        if spec.startswith("docker://"):
            # At the first `@`: a container's name cannot hold one, and an endpoint's can.
            container, at, where = spec[len("docker://") :].partition("@")
            if container and (where or not at):
                # Kept as its own spelling, and none for the default -- so a target
                # naming its daemon `local` is the same target as one naming none.
                endpoint = Endpoint.parse(where)
                spelled = "" if endpoint == Endpoint() else str(endpoint)
                return cls("docker", host=container, path=spelled)
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
            f"unsupported target {spec!r}; expected ssh://HOST, "
            "docker://CONTAINER[@ENDPOINT], tcp://HOST:PORT, peer://TICKET@HOST:PORT or "
            "local[:PATH]"
        )

    def describe(self) -> str:
        """Its own spelling back, so that what is logged is what could be typed."""
        if self.scheme == "ssh":
            from urllib.parse import quote, urlencode

            said = f"ssh://{self.host}" + (f":{self.port}" if self.port else "")
            if self.options:
                said += "?" + urlencode(self.options, quote_via=quote, safe="/~:@,")
            return said
        if self.scheme == "docker":
            return f"docker://{self.host}" + (f"@{self.path}" if self.path else "")
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

    @property
    def endpoint(self) -> Endpoint:
        """The daemon a `docker://` target's container is held by.

        Raises:
          ValueError: If this is not one, there being no daemon to answer with.
        """
        if self.scheme != "docker":
            raise ValueError(f"{self.describe()} is not a container")
        return Endpoint.parse(self.path)


#: What an ssh option may be called: an ssh_config keyword, or `F` for the config file.
_KEYWORD = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")


def _ssh_options(query: str, spec: str) -> tuple[tuple[str, str], ...]:
    """The options after the `?` of an ssh target, read.

    Raises:
      ValueError: For one that is not `KEYWORD=VALUE`, or whose value is empty, would be
        two lines, or holds a double quote, which ssh reads a value's quoting with.
    """
    from urllib.parse import parse_qsl

    if not query:
        return ()
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise ValueError(
            f"malformed target {spec!r}; expected ssh://HOST?KEYWORD=VALUE&..."
        ) from error
    for key, value in pairs:
        if not _KEYWORD.match(key) or not value or set(value) & set('\n\r\0"'):
            raise ValueError(
                f"malformed target {spec!r}; {key}={value!r} is not an ssh option"
            )
    return tuple(pairs)


def ssh_flags(options: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """What `ssh` is told for a target's options, in the order they were written.

    Args:
      options: `(KEYWORD, VALUE)` pairs, as :attr:`Target.options` holds them.

    Returns:
      `-F FILE` for the config file, and `-o KEYWORD=VALUE` for each of the rest -- the value
      in double quotes where it has a space in it, which ssh would otherwise read as two.
    """
    flags: list[str] = []
    for key, value in options:
        if key == "F":
            flags += ["-F", value]
        else:
            said = f'"{value}"' if any(one.isspace() for one in value) else value
            flags += ["-o", f"{key}={said}"]
    return tuple(flags)


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
            # The target's own options first: ssh keeps the first value it is given for a
            # setting, so what somebody wrote for this host wins over what humanize assumes.
            return cls(
                target,
                (
                    "ssh",
                    *ssh_flags(target.options),
                    *_SSH_OPTIONS,
                    *_reuse(target.options),
                    *port,
                    target.host,
                ),
                quotes=True,
                cache=REMOTE_CACHE,
                mirrors=REMOTE_MIRRORS,
            )
        if target.scheme == "docker":
            return cls(
                target,
                tuple(target.endpoint.docker("exec", "-i", target.host)),
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
          ConnectionError: If it cannot be written, or what arrived is not what was sent.
        """
        try:
            archive, digest = bundled()
        except OSError as failed:
            raise ConnectionError(
                f"could not install humanize on {self.target.describe()}: {failed}"
            ) from failed
        name = f"humanize-{digest}.pyz"
        where = f"{self.cache}/{name}"
        # One push per machine per bundle for the life of this process. The archive is named
        # by what is in it, so a second push would write the same bytes over the same path --
        # a round trip, and a file a live session may be importing from, for no news. Asked
        # before the archive is read, so a machine that already has it costs no megabyte of
        # this one's memory either.
        already = (self.target.describe(), digest)
        with _PUSHED_LOCK:
            if already in _PUSHED:
                return where
        try:
            carried = archive.read_bytes()
        except FileNotFoundError:
            # Swept between being asked for and being read, which only an archive nothing had
            # used for weeks can be: built again, under the same name.
            carried = _rebundled().read_bytes()
        result = self.run(_installing(self.cache, name, digest), carried)
        if result.returncode != 0:
            raise ConnectionError(
                f"could not install humanize on {self.target.describe()}: "
                f"{result.stderr.decode(errors='replace').strip()}"
                f"{self._said()}"
            )
        with _PUSHED_LOCK:
            _PUSHED.add(already)
        return where

    def forget(self) -> None:
        """Forgets that this machine was given the bundle, for one that has been replaced.

        A container made again under a name one had before is a new machine holding nothing,
        and the memo would otherwise answer for it with what the old one was given.
        """
        named = self.target.describe()
        with _PUSHED_LOCK:
            _PUSHED.difference_update([one for one in _PUSHED if one[0] == named])

    def _said(self) -> str:
        """The tail of what a container printed, for an error that does not say enough.

        A container whose own process could not start is one docker then reports as merely
        not running; why it could not -- that there is no Python it can use, and where it was
        looked for -- was said on the way out and is in the log and nowhere else.
        """
        if self.target.scheme != "docker":
            return ""
        said = subprocess.run(
            self.target.endpoint.docker("logs", "--tail", "3", self.target.host),
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
#: name -- `ssh://box:2201` and `ssh://box:2202` are two of them, and so are two containers
#: of one name on two daemons, which is why a container's spelling carries its endpoint -- and
#: a memo that could not tell them apart is a second machine left without the archive it is
#: about to be asked to run. And the digest, because a rebuilt bundle is a different file.
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


#: The archive this process last used, as `(stamp, path, digest, touched)`. The digest is
#: what a target caches the archive under, and reading a megabyte off disk to work it out again
#: is what asking for it a second time would otherwise cost. `touched` is when it was last
#: marked as used, on the monotonic clock.
_bundle_held: tuple[str, Path, str, float] | None = None
_BUNDLING = threading.Lock()

#: How often the archive held is marked as used. Far inside :data:`_KEPT_FOR`, so that no
#: sweep ever finds it old while a run holds it, and far outside the time between two turns,
#: so that marking it is not a write to the disk for every one of them.
_RETOUCH = 3600.0


def bundled() -> tuple[Path, str]:
    """The archive for the current source tree, and the name a target caches it under.

    The archive held is touched every so often while it is asked for, which is what keeps
    another run's sweep from taking it away while this one is still shipping it -- and what
    finds that it has gone anyway, after a run idle for longer than the sweep waits, so that
    it is built again rather than read from a path that is no longer there.

    Returns:
      Where it is, and the digest of what is in it.
    """
    global _bundle_held  # noqa: PLW0603 -- one archive per process, per source tree
    source = Path(coganchor.__file__).parent
    stamp = _lately(source)
    with _BUNDLING:
        now = time.monotonic()
        held = _bundle_held
        if held is not None and held[0] == stamp:
            if now - held[3] < _RETOUCH:
                return held[1], held[2]
            if _touched(held[1]):
                _bundle_held = (*held[:3], now)
                return held[1], held[2]
        archive, digest = _built(source, stamp)
        _bundle_held = (stamp, archive, digest, now)
        return archive, digest


def _rebundled() -> Path:
    """The archive again, for one that has gone from under this process since it was held.

    Returns:
      Where it is now.
    """
    global _bundle_held  # noqa: PLW0603 -- one archive per process, per source tree
    with _BUNDLING:
        _bundle_held = None
    return bundled()[0]


def _built(source: Path, stamp: str) -> tuple[Path, str]:
    """The archive for the tree a stamp was taken of, built unless it already has been.

    What a stamp built is written down under the stamp's own name, so that finding the
    archive again is one small read rather than a build. The archive itself is written under a
    name of its own, named by its digest once that is known, and moved into place: whoever
    reads `humanize-<digest>.pyz` reads exactly the bytes that digest was taken of, which is
    the whole of what a target caching it by that name relies on.

    Args:
      source: The package the archive is made of.
      stamp: What :func:`_stamped` said of it.

    Returns:
      Where the archive is, and its digest.
    """
    # Imported here rather than above: on a target, `hmz` is the namespace the bundle cut
    # down to this package, and only the machine that builds an archive keeps one.
    from hmz import machine

    # One per user rather than one shared, and the archives in it named by what is in them
    # rather than by whose they are: two checkouts, two installed versions or two users on
    # one machine each find their own archive there and never one another's.
    home = machine()
    index = home / f"{stamp}.digest"
    digest = _read(index)
    if digest:
        archive = home / f"humanize-{digest}.pyz"
        if _touched(archive):
            _touched(index)
            return archive, digest
    handle, staged = tempfile.mkstemp(dir=home, prefix="humanize-", suffix=".pyz.new")
    os.close(handle)
    made = Path(staged)
    try:
        _write_bundle(source, made)
        with made.open("rb") as reading:
            digest = hashlib.file_digest(reading, "sha256").hexdigest()[:_DIGEST]
        archive = home / f"humanize-{digest}.pyz"
        # Over one already there, if one is: the same name is the same bytes, and a run
        # already reading the old file goes on reading it.
        made.replace(archive)
    except BaseException:
        # A build that failed leaves nothing of itself behind.
        made.unlink(missing_ok=True)
        raise
    # The index after the archive, and only if it was written: an index that got there first
    # would name an archive a run that died mid-build never finished.
    atomic.writes(index, f"{digest}\n", mode=0o600)
    _swept(home, archive)
    return archive, digest


def _touched(path: Path) -> bool:
    """Marks a file as just used, and says whether it was there to mark."""
    try:
        os.utime(path)
    except FileNotFoundError:
        return False
    return True


def _swept(home: Path, keeping: Path) -> None:
    """Removes whatever in this user's directory of archives nothing has used in a while.

    Only after a build, which is the one moment a new archive has joined the rest, and only
    what has gone :data:`_KEPT_FOR` untouched: every run touches the archive it is using
    every :data:`_RETOUCH` seconds while it asks for it, so nothing old enough to go is
    anything a run still holds.

    Args:
      home: The directory.
      keeping: The archive just built, which goes nowhere whatever its age says.
    """
    now = time.time()
    # And what an earlier humanize kept beside it, one archive every checkout shared.
    legacy = home.with_name(f"{home.name}.pyz")
    for one in [*home.iterdir(), legacy, legacy.with_suffix(".stamp")]:
        # What a build made, and nothing else: this machine's daemon keeps its socket and the
        # lock it holds for as long as it runs beside the archives, and a lock swept from
        # under a daemon is a second daemon.
        if one == keeping or not (
            one.name.startswith("humanize-") or one.suffix == ".digest"
        ):
            continue
        with contextlib.suppress(OSError):
            if now - one.lstat().st_mtime > _KEPT_FOR:
                one.unlink()


#: The ssh options that make one connection serve every command, worked out once. Making the
#: directory they name is a syscall per command otherwise, for an answer that cannot change.
_reusing_held: tuple[str, ...] | None = None


def _reuse(options: Sequence[tuple[str, str]] = ()) -> tuple[str, ...]:
    """The options that let the second `ssh` to a host ride the first one's connection.

    The socket lives under this user's runtime directory where there is one and in the
    temporary directory otherwise, named by `%C` -- ssh's own digest of host, port and user,
    which is short, which matters: a unix socket path has about a hundred bytes to live in and
    a home directory can spend most of them.

    Args:
      options: The target's own options. A digest of them joins the name where there are
        any, so that two targets at one host and user told different things -- another key,
        another jump host, another config -- do not ride one connection.
    """
    global _reusing_held  # noqa: PLW0603 -- one answer per process, for a question with one
    if _reusing_held is None:
        _reusing_held = ()
        said = os.environ.get("HUMANIZE_SSH_REUSE", "on").strip().lower()
        if said not in ("off", "0", "no", "false", ""):
            under = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
            control = os.path.join(under, f"humanize-ssh-{os.getuid()}")
            try:
                os.makedirs(control, mode=0o700, exist_ok=True)
            except OSError:
                pass
            else:
                _reusing_held = (*_SSH_REUSE, "-o", f"ControlPath={control}/%C")
    if not options or not _reusing_held:
        return _reusing_held
    told = hashlib.sha256(repr(tuple(options)).encode()).hexdigest()[:8]
    return (*_reusing_held[:-1], f"{_reusing_held[-1]}-{told}")


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

    Built once per source tree rather than once per session, where no destination is given:
    the archive is a function of the source alone, so an unchanged tree is an unchanged
    archive, and the one already built for it is found by a few hundred `stat` calls rather
    than by copying the package, zipping it and rewriting every mode and timestamp in it,
    every time an agent is anchored. See :func:`bundled`.

    Args:
      destination: Where to write it. None keeps it in this user's own directory of
        archives, `$TMPDIR/humanize-<uid>/humanize-<digest>.pyz`.

    Returns:
      Where it is.
    """
    if destination is None:
        return bundled()[0]
    source = Path(coganchor.__file__).parent
    _publish(destination, lambda staged: _write_bundle(source, staged))
    return destination


#: How long a reading of the source tree is trusted for. Every rendered line asks whether the
#: archive is still the right one, and asking costs a `stat` per file in this package -- which
#: for a hub rendering a line per turn is the largest single thing it does per turn, and it is
#: asking a question whose answer cannot change while a run is going. Seconds rather than the
#: whole run: somebody editing this package with a hub up should not have to restart it, and a
#: few seconds of staleness is the most that can cost them.
_RESTAMP = 5.0
_stamp_held: tuple[float, str] | None = None
_STAMPING = threading.Lock()


def _lately(source: Path) -> str:
    """What the source tree was, as of a moment ago.

    Args:
      source: The package to read.

    Returns:
      Its stamp, taken afresh if the last one has gone stale.
    """
    global _stamp_held  # noqa: PLW0603 -- one reading per process at a time
    with _STAMPING:
        now = time.monotonic()
        if _stamp_held is not None and now - _stamp_held[0] < _RESTAMP:
            return _stamp_held[1]
        stamp = _stamped(source)
        _stamp_held = (now, stamp)
        return stamp


def _stamped(source: Path) -> str:
    """What the source tree is now, cheaply enough to ask before every session.

    Sizes and modification times rather than contents: reading the package to decide whether
    to rebuild it costs as much as rebuilding it, while the questions a filesystem answers
    from the directory entry it already has cost nothing worth measuring. An edit that keeps
    a file's size and its timestamp to the nanosecond is the one this would miss, and there
    is no way to make one by accident.
    """
    seen = hashlib.sha256()
    # Both trees the archive is made of -- the command line goes in too -- and each by where
    # it is, so that two checkouts never share a stamp however alike their files look.
    for tree in (source, source.parent / "cli"):
        seen.update(f"{tree.resolve()}\n".encode())
        for path in sorted(tree.rglob("*")):
            if "__pycache__" in path.parts or path.is_dir():
                continue
            found = path.stat()
            seen.update(
                f"{path.relative_to(tree)}\0{found.st_size}\0{found.st_mtime_ns}\n".encode()
            )
    return seen.hexdigest()


def _read(path: Path) -> str:
    """What an index says, or nothing at all where there is none to read."""
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
