"""Getting a :class:`~hmz.coganchor.proto.Channel` to the serving half on the target.

Seven ways in, and they are two kinds of thing.

Five of them *start* the serving half and take the pipe they started it down. ``local[:REAL]``
runs it as a child of this process, where ``REAL`` is the directory standing in for the
target's copy of the workspace; ``ssh://[user@]host[:port]``,
``docker://container[?options][@endpoint]``, ``apple-container://container`` and
``slurm://JOBID`` ship `coganchor`, built for the far side's OS and architecture, and run it
there, needing nothing installed but a `/bin/sh`. Those five differ in one thing only -- how a
command is run over there -- so they are one road with five prefixes, and :class:`Road` is that
road. A docker container's prefix names the daemon holding it, which :class:`Endpoint` is, and
whatever its options say of the user, the variables and the wrapper each command there is run
as, with and under; an Apple container's names none, Apple's `container` reaching the
containers of this Mac and no other; and a Slurm job's is an `srun` sharing that job's
allocation, on the node it was given.

Two of them *find* a serving half somebody else started. ``tcp://host:port`` dials one left
listening, and carries the session inside TLS (:mod:`hmz.coganchor.tls`), proving the token
rather than sending it. ``peer://TICKET@BROKER:PORT`` is met through a broker
(:mod:`hmz.coganchor.rendezvous`), which is the answer where the two halves are on two machines
that cannot dial each other and only Humanize can reach both -- and which `coganchor cog` dials
itself, a meeting being for one session.

What makes the far side cheap is that none of this is paid twice. The far side is asked its
`uname -sm` once, and the build for it lands in its cache as `coganchor-<digest>`, once per
machine per build; an `ssh` reaches a host once and every later command rides the connection
the first one opened; and a road already walked is not walked again to be told what it already
said.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import shlex
import socket
import stat
import subprocess
import tempfile
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.coganchor import binary, tls
from hmz.coganchor.proto import Channel
from hmz.coganchor.unix import sockets

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hmz.coganchor.rendezvous import Meeting

__all__ = [
    "Endpoint",
    "Road",
    "Target",
    "Transport",
    "awaiting",
    "coganchor_command",
    "connect",
    "idling",
    "serve_line",
    "ssh_flags",
]

log = logging.getLogger(__name__)

#: Where the shipped `coganchor` is cached on a target reached over ssh.  Written with `$HOME`
#: rather than `~`, because the shell that expands it is the one *inside* the line -- the
#: whole line is quoted on its way across, so a `~` would arrive as a directory of that name.
REMOTE_CACHE = "$HOME/.cache/humanize"

#: And in a container, which may have no home directory to speak of and is one user's anyway.
CONTAINER_CACHE = "/tmp/humanize"  # noqa: S108

#: What an Apple container's target is spelled with: `apple-container://NAME`, a container of
#: this Mac's, which Apple's `container` reaches and no daemon stands between.
APPLE = "apple-container"

#: What a Slurm job's target is spelled with: `slurm://JOBID`, a job of the cluster this
#: machine submits to, whose node `srun` reaches by sharing the job's allocation.
SLURM = "slurm"

#: Where a harness put on another machine keeps its mirror of the workspace. *Beside* the
#: program's cache rather than inside it, and that is not a matter of taste: `~/.cache/humanize`
#: is one of the directories a supervised turn deliberately answers from the machine the agent
#: runs on -- it is Humanize's own state, and the whole point of naming it is that it does not
#: cross. A mirror underneath it would be a mirror no path was ever translated through, so the
#: agent would find the workspace empty and every command it ran there would run in the wrong
#: directory. `path_within` is what keeps the two apart, a sibling name not being a prefix.
REMOTE_MIRRORS = "$HOME/.cache/humanize-mirrors"

#: And the same, in a container.
CONTAINER_MIRRORS = "/tmp/humanize-mirrors"  # noqa: S108

#: What a docker target may say after a `?` ahead of its endpoint, each `KEY=VALUE`: `user`
#: once, the `UID[:GID]` every command there is run as; `env`, a `NAME=VALUE` each is run
#: with; and `exec`, a word of the wrapper each is run under, in the order they are written.
_DOCKER_OPTIONS = ("user", "env", "exec")

#: How long a build nothing has run is kept on a target before the next one shipped beside it
#: sweeps it away. By age rather than by count, because the only build it is unsafe to remove
#: is one a run is still using, and every run touches the one it runs each time it runs it: a
#: build left alone this long belongs to a version nobody is running.
_KEPT_FOR = 14 * 24 * 3600

#: What every `ssh` this reaches for carries. `-T` because the far side is a pipe rather than a
#: terminal, and the keepalive so that a session held open across a long turn is not dropped by
#: something counting idle seconds.
_SSH_OPTIONS = ("-T", "-o", "BatchMode=no", "-o", "ServerAliveInterval=30")

#: And what makes the second command to a host cost nothing: the first one leaves a master
#: connection behind, and every later one rides it rather than paying for a TCP handshake, a
#: key exchange and an authentication of its own. A turn against a remote target opens several
#: -- ship the program, start the serving half, and whatever the harness itself needs -- so
#: this is most of the difference between an anchored turn starting now and starting in a
#: second. It is on unless `HUMANIZE_SSH_REUSE` says `off`, `0`, `no` or `false` -- trimmed and in
#: any case -- or is set and empty, which is for a machine whose sshd refuses multiplexing.
_SSH_REUSE = ("-o", "ControlMaster=auto", "-o", "ControlPersist=120")

#: What a control socket's path spends after its directory: `%C`, ssh's 40-digit digest, the
#: `-<8 digits>` of a target's own options, and the `.<16 digits>` ssh binds it under first
#: and then renames it from.
_CONTROL = 40 + 9 + 17


def coganchor_command(
    args: list[str],
    program: str,
    setting: Sequence[tuple[str, str]] = (),
    owned: Sequence[str] = (),
) -> list[str]:
    """The command that runs `coganchor` on the target, where :meth:`Road.shipped` put it.

    Argv, so that a path holding a space or a quote reaches the target as it is. The program
    is the whole of what that machine needs. Touched as it is run, so the sweep a ship of
    another build makes on that machine never counts one a run is still starting from as one
    nobody uses -- a process ships it once, and may go on running it for weeks.

    Args:
      args: What follows the program's name, its mode first.
      program: Where it is, as the *target's* shell will read it.
      setting: Variables to export first, whose values are read by the shell on the far side
        -- which is the only way to name that machine's home directory, since everything in
        `args` crosses as the word it already is.
      owned: Directories that have to be the far side's user's alone before anything else
        runs, as that machine's shell spells them: each is made, refused where it is a link
        or another user's, and made `0700`.

    Returns:
      The argv to run over there.
    """
    script = f'touch -c "{program}" 2>/dev/null; exec "{program}" "$@"'
    return ["/bin/sh", "-c", _prefaced(script, setting, owned), "coganchor", *args]


def _prefaced(
    script: str, setting: Sequence[tuple[str, str]], owned: Sequence[str]
) -> str:
    """A far-side script, with the directories it needs checked and its variables set first.

    Args:
      script: What runs once they are.
      setting: As :func:`coganchor_command` takes them.
      owned: As :func:`coganchor_command` takes them.

    Returns:
      The whole script.
    """
    # In front of what runs rather than inside it -- and `mkdir` with it, since a directory
    # named by one of these is one the far side has to have and nothing over there is going to
    # make it first.
    for name, value in setting:
        script = (
            f'{name}="{value}"; export {name}; mkdir -p "${name}" || exit 1; ' + script
        )
    # Before the settings, whose directories may be inside these. Once one is checked nobody
    # else can move or remove it from under this user, a shared `/tmp` being sticky.
    for path in reversed(owned):
        script = (
            f'mkdir -p "{path}" && [ -d "{path}" ] && [ ! -L "{path}" ] && '
            f'[ -O "{path}" ] && chmod 700 "{path}" || '
            f'{{ echo "Humanize: {path} is not a directory this user owns" >&2; '
            "exit 1; }; " + script
        )
    return script


#: Putting `coganchor` on a target, in its `/bin/sh`, which is all a machine with nothing of
#: Humanize on it is sure to have. A build already there under its name is touched and left:
#: it is named by its digest, and rewriting it would be rewriting a program a live session may
#: be running. Touched with `-c`, which sets its time by its name: a plain `touch` opens it
#: for writing to do that, and for as long as it is open Linux refuses to run it (`Text file
#: busy`) -- to a session which found it there a moment earlier. One that is not is read off
#: the input into `<path>.<pid>` -- two sessions shipping to one machine at once being the
#: ordinary case -- checked to be as long as what
#: was sent, so that a link cut half-way leaves nothing under the name, made `0700` and moved
#: into place. Then every other build and half-written copy nobody has touched in `{days}`
#: whole days and more goes, and so does any `humanize-*.pyz` archive an earlier Humanize,
#: which shipped itself as Python, left there. `{cache}`, `{name}` and `{size}` are the far
#: side's directory, the build's name there and its length in bytes.
_SHIPPING = (
    'c="{cache}"; mkdir -p "$c" || exit 1; p="$c/{name}"; '
    'if [ -f "$p" ]; then touch -c "$p"; else '
    't="$p.$$"; '
    'if cat > "$t" && n=$(wc -c < "$t") && [ $n -eq {size} ] && chmod 700 "$t" '
    '&& mv -f "$t" "$p"; then :; else rm -f "$t"; '
    'echo "Humanize: coganchor did not arrive whole at $p" >&2; exit 1; fi; fi; '
    'find "$c" -maxdepth 1 -type f \\( -name "coganchor-*" -o -name "humanize-*.pyz*" \\) '
    '! -name "{name}" -mtime +{days} '
    "-exec rm -f {{}} + 2>/dev/null; exit 0"
)


def _shipping(cache: str, name: str, size: int, *, owned: bool = False) -> list[str]:
    """The command that puts a build arriving on its input on the far side.

    Args:
      cache: The directory it goes in, as that machine's own shell spells it.
      name: What it is called there.
      size: How many bytes it is.
      owned: Whether `cache` has to be the far side's user's alone first, as
        :func:`coganchor_command` says.

    Returns:
      The argv to run over there.
    """
    # Whole days, as `find` counts them: `+13` is fourteen days or more.
    days = _KEPT_FOR // (24 * 3600) - 1
    script = _SHIPPING.format(cache=cache, name=name, size=size, days=days)
    return ["/bin/sh", "-c", _prefaced(script, (), (cache,) if owned else ())]


def awaiting(cache: str) -> str:
    """A far-side script that waits for the right `coganchor` to land in `cache`.

    For a machine that starts the anchor itself -- a Slurm job's batch step -- before anybody
    has asked it what it is: every build there is to ship is named, by the `uname -sm` it is
    for, and the one for the machine the script runs on is waited for, as `$p`.

    Args:
      cache: Where :meth:`Road.shipped` puts it, as that machine's shell spells it.

    Returns:
      The script, which leaves `$p` naming the program, or fails saying no build fits.
    """
    builds: dict[Path, list[str]] = {}
    for system in ("Linux", "Darwin"):
        for machine in ("x86_64", "amd64", "aarch64", "arm64"):
            build = binary.shipped(system, machine)
            if build is not None:
                builds.setdefault(build, []).append(f'"{system} {machine}"')
    cases = "".join(
        f'{"|".join(spellings)}) p="{cache}/coganchor-{binary.digest(build)}";; '
        for build, spellings in builds.items()
    )
    return (
        f'case "$(uname -sm)" in {cases}'
        '*) echo "Humanize: no coganchor is built for $(uname -sm)" >&2; exit 1;; esac; '
        'while [ ! -f "$p" ]; do sleep 1; done'
    )


def idling() -> list[str]:
    """What a container does while the turns come and go: nothing, for as long as it is let.

    The image needs no interpreter, `coganchor` being all that is shipped to it, so a `sleep`
    is all it does.

    Returns:
      The container's command.
    """
    return ["/bin/sh", "-c", "exec sleep 2147483647"]


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
    their digest under Humanize's directory for this machine and this user's alone, written
    once and whole; it takes its own directory off `PATH` again before running the real one.
    That directory is a temporary one a cleaner may empty under a long-lived process, so one
    already written is touched each time it is used, and written again if it has gone.

    Args:
      options: `(KEYWORD, VALUE)` pairs, as :attr:`Target.options` holds them.

    Returns:
      The directory, for the front of `PATH`.

    Raises:
      OSError: If it cannot be written.
    """
    from hmz import machine

    flags = " ".join(shlex.quote(flag) for flag in ssh_flags(options))
    at = machine() / "docker-ssh" / hashlib.sha256(flags.encode()).hexdigest()[:16]
    if str(at) in _SHIMS and _touched(at / "ssh"):
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


#: The `ssh` shims this process has written or found whole, so each is read once and touched after.
_SHIMS: set[str] = set()


def _touched(path: Path) -> bool:
    """Marks a file as just used, and says whether it was there to mark."""
    try:
        os.utime(path)
    except FileNotFoundError:
        return False
    return True


def _read(path: Path) -> str:
    """What a file says, stripped, or nothing at all where there is none to read."""
    try:
        return path.read_text().strip()
    except OSError:
        return ""


@dataclass(frozen=True, slots=True)
class Target:
    """Where the target is.

    Attributes:
      host: The host, the container, or for a `slurm://` target the job's id.
      path: For a `local` target, the directory standing in for the workspace; for a
        `docker://` one, its daemon; for a `slurm://` one, the Python it names, `?python=PATH`,
        which is read and kept for the spelling and not used: `coganchor` needs none.
      options: For an ssh target, what its `ssh` is told besides the destination, as
        `(KEYWORD, VALUE)` pairs: each an ssh_config keyword, passed as `-o KEYWORD=VALUE`,
        but for `F`, the config file ssh reads instead of the user's own (`-F VALUE`).
        Spelled after a `?` in the target, `&` between them, each value URL-quoted. For a
        docker one, what each `docker exec` is told besides the container, as
        :data:`_DOCKER_OPTIONS` says, in the same pairs and spelled the same way, after a `?`
        ahead of the `@` of its endpoint.
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
          spec: One of the seven, as the command line and the settings both write them.

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
            # At the first `@`: a container's name cannot hold one, its options are quoted
            # so as not to, and an endpoint's can.
            container, at, where = spec[len("docker://") :].partition("@")
            container, _, query = container.partition("?")
            if container and (where or not at):
                options = _docker_options(query, spec)
                # Kept as its own spelling, and none for the default -- so a target
                # naming its daemon `local` is the same target as one naming none.
                endpoint = Endpoint.parse(where)
                spelled = "" if endpoint == Endpoint() else str(endpoint)
                return cls("docker", host=container, path=spelled, options=options)
        if spec.startswith(f"{APPLE}://"):
            container = spec[len(f"{APPLE}://") :]
            if container and not set("@/?#") & set(container):
                return cls(APPLE, host=container)
        if spec.startswith(f"{SLURM}://"):
            job, _, query = spec[len(f"{SLURM}://") :].partition("?")
            python = _python_option(query, spec)
            if job.isdigit():
                return cls(SLURM, host=job, path=python)
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
            f"docker://CONTAINER[@ENDPOINT], {APPLE}://CONTAINER, "
            f"{SLURM}://JOBID[?python=PATH], tcp://HOST:PORT, peer://TICKET@HOST:PORT or "
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
            from urllib.parse import quote, urlencode

            said = f"docker://{self.host}"
            if self.options:
                # An `@` quoted, so that the container's part still ends at the first one.
                said += "?" + urlencode(self.options, quote_via=quote, safe="/~:,=")
            return said + (f"@{self.path}" if self.path else "")
        if self.scheme == APPLE:
            return f"{APPLE}://{self.host}"
        if self.scheme == SLURM:
            from urllib.parse import quote

            python = f"?python={quote(self.path, safe='/~:@,')}" if self.path else ""
            return f"{SLURM}://{self.host}{python}"
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


#: What a docker target's `user` may be: the numeric `UID[:GID]` docker's `-u` takes, numeric
#: so that the directories Humanize keeps there are named for whom they are without asking.
_DOCKER_USER = re.compile(r"[0-9]+(?::[0-9]+)?\Z")

#: What a variable a docker target's `env` sets may be called.
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _docker_options(query: str, spec: str) -> tuple[tuple[str, str], ...]:
    """The options after the `?` of a docker target, read.

    Raises:
      ValueError: For one that is not one of :data:`_DOCKER_OPTIONS`, a `user` that is not
        `UID[:GID]` or is said twice, an `env` that is not `NAME=VALUE`, an empty `exec`, or
        any value that would be two lines or holds a NUL.
    """
    from urllib.parse import parse_qsl

    if not query:
        return ()
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise ValueError(
            f"malformed target {spec!r}; expected "
            "docker://CONTAINER?user=UID[:GID]&env=NAME=VALUE&exec=WORD&..."
        ) from error
    users = 0
    for key, value in pairs:
        name, equals, _ = value.partition("=")
        users += key == "user"
        if (
            set(value) & set("\n\r\0")
            or (key == "user" and (users > 1 or not _DOCKER_USER.match(value)))
            or (key == "env" and not (equals and _VARIABLE.match(name)))
            or (key == "exec" and not value)
            or key not in _DOCKER_OPTIONS
        ):
            raise ValueError(
                f"malformed target {spec!r}; {key}={value!r} is not a docker exec option"
            )
    return tuple(pairs)


def _python_option(query: str, spec: str) -> str:
    """The Python a `slurm://` target names after its `?`, or "" for none.

    Raises:
      ValueError: For anything but one `python=PATH`, the path absolute or under `~/`.
    """
    from urllib.parse import parse_qsl

    if not query:
        return ""
    try:
        pairs = parse_qsl(query, strict_parsing=True)
    except ValueError:
        pairs = []
    if (
        len(pairs) != 1
        or pairs[0][0] != "python"
        or not pairs[0][1].startswith(("/", "~/"))
        or set(pairs[0][1]) & set('\n\r\0"')
    ):
        raise ValueError(
            f"malformed target {spec!r}; expected {SLURM}://JOBID[?python=PATH]"
        )
    return pairs[0][1]


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

    The one thing the four bootstrapping targets differ in, and so the one thing written
    down per target rather than per caller. Given an argv it answers with the argv *this*
    machine runs to have it happen over there: nothing at all for a local target, an `ssh`
    carrying one quoted string for a host, a `docker exec` or a `container exec` carrying argv
    straight through for a container.

    Attributes:
      target: The machine.
      prefix: What goes in front of a command to send it there.
      quotes: Whether the far side reads the line through a shell before running it, and so
        whether every word has to survive that reading.
      cache: Where `coganchor` is kept over there, as that machine's own shell reads it.
      mirrors: And where a harness running there keeps its mirrors, which is somewhere else
        again -- see :data:`REMOTE_MIRRORS` for why it may not be under `cache`.
      owned: Whether `cache` and `mirrors` are the far side's user's own, and so are checked
        to be before anything goes in them or runs out of them: a container's commands run as
        a user its target names, among others of that container's that could have made a
        directory of that name first.
    """

    target: Target
    prefix: tuple[str, ...]
    quotes: bool
    cache: str
    mirrors: str
    owned: bool = False

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
            # setting, so what somebody wrote for this host wins over what Humanize assumes.
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
            # As the user the target names, with its variables, under its wrapper: every
            # command over there, the serving half and a native CLI among them. Its own
            # directories there then, named for that user, a container's `/tmp` being every
            # one of its users'.
            flags: list[str] = []
            wrapper: list[str] = []
            user = ""
            for key, value in target.options:
                if key == "user":
                    flags += ["-u", value]
                    user = value.partition(":")[0]
                elif key == "env":
                    flags += ["-e", value]
                else:
                    wrapper.append(value)
            own = f"-{user}" if user else ""
            return cls(
                target,
                (*target.endpoint.docker("exec", "-i", *flags, target.host), *wrapper),
                quotes=False,
                cache=CONTAINER_CACHE + own,
                mirrors=CONTAINER_MIRRORS + own,
                owned=bool(user),
            )
        if target.scheme == APPLE:
            return cls(
                target,
                ("container", "exec", "-i", target.host),
                quotes=False,
                cache=CONTAINER_CACHE,
                mirrors=CONTAINER_MIRRORS,
            )
        if target.scheme == SLURM:
            # A step of the job's own, sharing its allocation rather than waiting for a share
            # of it, on its one node: argv straight through, the bytes as they come, nothing of
            # this process's environment but whose it is, and none of its directory either --
            # which the node may not have.
            return cls(
                target,
                (
                    "srun",
                    f"--jobid={target.host}",
                    "--overlap",
                    "--nodes=1",
                    "--ntasks=1",
                    "--unbuffered",
                    "--quiet",
                    "--export=HOME,USER",
                    "--chdir=/",
                ),
                quotes=False,
                cache=REMOTE_CACHE,
                mirrors=REMOTE_MIRRORS,
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
        self, argv: Sequence[str], feeding: bytes = b"", timeout: float | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        """Runs one short command over there and waits for it.

        Args:
          argv: What to run.
          feeding: What to put on its input.
          timeout: How long to wait for it, in seconds, or None for as long as it takes.

        Returns:
          What it did, with both its streams captured.

        Raises:
          subprocess.TimeoutExpired: If it took longer than `timeout`.
        """
        return subprocess.run(
            self.line(argv),
            input=feeding,
            capture_output=True,
            check=False,
            timeout=timeout,
        )

    def mirror(self, named: str) -> str:
        """Where a harness on this machine keeps its mirror of the workspace.

        Named for what it mirrors rather than for the turn using it: a mirror kept between
        turns is a workspace whose files are already there the second time, which is the one
        saving worth more than every other here put together. And beside the program's cache
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
        """The argv this machine runs to have `hmz internal ...` run over there, as `coganchor`.

        The line is `coganchor`'s own spelling of the same command: `internal anchor serve
        ...` is `coganchor anchor ...`, `internal anchor ...` is `coganchor cog ...`. The program
        is shipped on the way, and shipped once: it is named by its digest, so a machine that
        already has this build is left with it and this process does not ask a second time.

        Args:
          argv: What follows `hmz`, e.g. `["internal", "anchor", "serve", "--stdio"]`.
          setting: Variables the far side exports before running it, and makes a directory
            of each -- which is how a mirror lands under that machine's own home rather than
            under a path this machine guessed for it.

        Returns:
          The local command to spawn.

        Raises:
          ValueError: For a line `coganchor` does not carry out.
          ConnectionError: If there is no `coganchor` for this machine, or it cannot be put
            on the target.
        """
        if list(argv[:1]) != ["internal"] or len(argv) < 2:  # noqa: PLR2004 -- `internal` and a command
            raise ValueError(f"coganchor does not run `hmz {shlex.join(argv)}`")
        translated = binary.translated(argv[1], list(argv[2:]))
        if self.target.scheme == "local":
            try:
                return [str(binary.here()), *translated]
            except FileNotFoundError as missing:
                raise ConnectionError(str(missing)) from missing
        return self.line(
            coganchor_command(
                translated, self.shipped(), setting=setting, owned=self._owning(setting)
            )
        )

    def _owning(self, setting: Sequence[tuple[str, str]]) -> list[str]:
        """The directories a line has to find the far side's user's own, as `owned` says.

        The program's directory, and the mirrors' where a setting puts something in it.
        """
        owned = [self.cache] if self.owned else []
        if self.owned and any(
            value.startswith(f"{self.mirrors}/") for _, value in setting
        ):
            owned.append(self.mirrors)
        return owned

    def shipped(self) -> str:
        """Puts `coganchor` on the target if it is not already there, and says where.

        The build for the target's own OS and architecture, which it is asked once, named
        `coganchor-<digest>` in :attr:`cache` and installed by :data:`_SHIPPING`. Once per
        machine per build for the life of this process: it is named by what is in it, so a
        second push would write the same bytes over the same path.

        Returns:
          The program's path over there, as that machine's shell reads it.

        Raises:
          ConnectionError: If the target cannot say what it is, there is no build for it, or
            the build cannot be written there.
        """
        system, machine = self._platform()
        program = binary.shipped(system, machine)
        if program is None:
            raise ConnectionError(
                f"could not install Humanize on {self.target.describe()}: no coganchor "
                f"is built for {system} {machine}; a target must be Linux or macOS on "
                "x86-64 or aarch64"
            )
        try:
            digest = binary.digest(program)
        except OSError as failed:
            raise ConnectionError(
                f"could not install Humanize on {self.target.describe()}: {failed}"
            ) from failed
        name = f"coganchor-{digest}"
        where = f"{self.cache}/{name}"
        already = (self.target.describe(), digest)
        with _PUSHED_LOCK:
            if already in _PUSHED:
                return where
        try:
            carried = program.read_bytes()
        except OSError as failed:
            raise ConnectionError(
                f"could not install Humanize on {self.target.describe()}: {failed}"
            ) from failed
        result = self.run(
            _shipping(self.cache, name, len(carried), owned=self.owned), carried
        )
        if result.returncode != 0:
            raise ConnectionError(
                f"could not install Humanize on {self.target.describe()}: "
                f"{result.stderr.decode(errors='replace').strip()}"
                f"{self._said()}"
            )
        with _PUSHED_LOCK:
            _PUSHED.add(already)
        return where

    def _platform(self) -> tuple[str, str]:
        """The target's `uname -sm`, asked once per machine for the life of this process.

        Raises:
          ConnectionError: If it could not be asked, or did not answer as `uname` does.
        """
        described = self.target.describe()
        with _PUSHED_LOCK:
            known = _UNAMES.get(described)
        if known is not None:
            return known
        # Through the shell, which finds `uname` on its PATH: a road such as `srun` may run
        # the program it is handed without looking it up.
        said = self.run(["/bin/sh", "-c", "exec uname -sm"])
        words = said.stdout.decode(errors="replace").split()
        if said.returncode != 0 or len(words) != 2:  # noqa: PLR2004 -- the OS, and the machine
            raise ConnectionError(
                f"could not ask {described} what it is: "
                f"{said.stderr.decode(errors='replace').strip() or ' '.join(words)}"
                f"{self._said()}"
            )
        known = (words[0], words[1])
        with _PUSHED_LOCK:
            _UNAMES[described] = known
        return known

    def forget(self) -> None:
        """Forgets that this machine was given `coganchor`, for one that has been replaced.

        A container made again under a name one had before is a new machine holding nothing,
        and the memo would otherwise answer for it with what the old one was given -- as
        every user a target of it named, each of whom was given one of their own. What it said
        it was goes too, a machine made again being free to be another kind.
        """
        named = _machine(self.target.describe())
        with _PUSHED_LOCK:
            _PUSHED.difference_update(
                [one for one in _PUSHED if _machine(one[0]) == named]
            )
            for one in [one for one in _UNAMES if _machine(one) == named]:
                del _UNAMES[one]

    def _said(self) -> str:
        """The tail of what a container printed, for an error that does not say enough.

        A container whose own process could not start is one docker then reports as merely
        not running; why it could not was said on the way out and is in the log and nowhere
        else.
        """
        if self.target.scheme == "docker":
            asking = self.target.endpoint.docker(
                "logs", "--tail", "3", self.target.host
            )
        elif self.target.scheme == APPLE:
            asking = ["container", "logs", "-n", "3", self.target.host]
        else:
            return ""
        said = subprocess.run(asking, capture_output=True, check=False)
        if said.returncode != 0:
            # There is no container to have said anything, or no daemon to ask -- which is
            # what the error being written already says, and saying it twice says less.
            return ""
        # Both streams: what a container printed on its way out is on the one it chose.
        tail = (said.stdout + said.stderr).decode(errors="replace").strip()
        return f"; the container said: {tail}" if tail else ""


#: Which machines already hold which build, so that a road walked twice is not paid for
#: twice. The target *whole* rather than its host, because two machines can answer to one
#: name -- `ssh://box:2201` and `ssh://box:2202` are two of them, and so are two containers
#: of one name on two daemons, which is why a container's spelling carries its endpoint -- and
#: a memo that could not tell them apart is a second machine left without the program it is
#: about to be asked to run. And the digest, because a rebuilt program is a different file.
_PUSHED: set[tuple[str, str]] = set()
_PUSHED_LOCK = threading.Lock()

#: What each machine said its `uname -sm` was, as `(OS, machine)`, by its target's spelling.
_UNAMES: dict[str, tuple[str, str]] = {}


def _machine(spelled: str) -> str:
    """The machine a target spelling names, whoever it names as using it.

    A docker target's options say who uses a container and how, not which container it is:
    every spelling of one container is forgotten with it when it is replaced.
    """
    target = Target.parse(spelled)
    if target.scheme == "docker":
        return replace(target, options=()).describe()
    return spelled


#: The ssh options that make one connection serve every command, worked out once. Making the
#: directory they name is a syscall per command otherwise, for an answer that cannot change.
_reusing_held: tuple[str, ...] | None = None


def _reuse(options: Sequence[tuple[str, str]] = ()) -> tuple[str, ...]:
    """The options that let the second `ssh` to a host ride the first one's connection.

    The socket lives under this user's runtime directory where there is one and in the
    temporary directory otherwise, named by `%C` -- ssh's own digest of host, port and user,
    which is short, which matters: a unix socket path has about a hundred bytes to live in,
    and a Mac's temporary directory spends half of them. Where what is left is too few, it
    lives under `/tmp` instead, and is shared there only where the directory is this user's
    alone.

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
            name = f"humanize-ssh-{os.getuid()}"
            under = sockets(
                len(f"/{name}/") + _CONTROL, os.environ.get("XDG_RUNTIME_DIR", "")
            )
            control = os.path.join(under, name)
            with contextlib.suppress(OSError):
                os.mkdir(control, mode=0o700)
            try:
                found = os.lstat(control)
            except OSError:
                pass
            else:
                # Under `/tmp` a directory of this name may be anybody's, made first, and a
                # socket in it one they could take this user's connections over.
                if (
                    stat.S_ISDIR(found.st_mode)
                    and found.st_uid == os.getuid()
                    and not found.st_mode & 0o077
                ):
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
      ConnectionError: If `coganchor` cannot be put there.
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
      OSError: If the target cannot be reached, or is a meeting: a `peer://` target is met
        by `coganchor cog` itself, a ticket being good for one session.
      ValueError: If the target cannot be read.
    """
    if target.scheme == "tcp":
        # An IPv6 literal is spelled in brackets and dialled without them, as the cog does.
        sock = socket.create_connection(
            (target.host.strip("[]"), target.port), timeout=30.0
        )
        # Nagle off, the way a punched socket has it off: this protocol is a small request
        # and a small reply, over and over, and a delay waiting for a second frame that is
        # not coming is a delay per syscall the agent makes.
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # The handshake within the same 30 seconds a step; the session as long as it lasts.
        # An empty token is none, as an empty `$HUMANIZE_TOKEN` is to the serving half.
        sealed = tls.dial(sock, token.encode() if token else None, target.describe())
        sock.settimeout(None)
        return Transport(Channel.from_pipe(sealed, sealed.bound))
    if target.scheme == "peer":
        raise ConnectionError(
            f"{target.describe()} is a meeting for one session, which coganchor keeps"
        )
    return _spawn(serve_line(target, exports), token)


def _spawn(command: list[str], token: str | None) -> Transport:
    """Start a child that serves over its own stdin and stdout.

    The token travels in the environment the child inherits, which works for
    ``local``; with none, the child is kept from one this process happens to have
    exported, which it would require and never be shown.  For ``ssh`` and
    ``docker`` the child is the client rather than
    the target and neither forwards the environment, so those sessions are
    authenticated by ssh and by the docker socket themselves and the token goes
    unused.
    """
    log.debug("starting the target: %s", " ".join(command))
    env = dict(os.environ)
    if token:
        env["HUMANIZE_TOKEN"] = token
    else:
        env.pop("HUMANIZE_TOKEN", None)
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
