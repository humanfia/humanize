"""Seatbelt: macOS's sandbox, holding a process tree to the paths and connections it names.

A :class:`Profile` names what may be read, what may be written and, where the network is cut,
the one TCP port on loopback that may still be connected to; :meth:`Profile.command` is the
command line that runs a program inside it. That is ``sandbox-exec``, which applies the
profile to itself and then becomes the program: Seatbelt restricts a process and everything
it later starts, and nothing already running can be restricted from outside -- the same
reason Landlock is put up in a forked child just before ``execve``.

``sandbox-exec`` rather than ``sandbox_init`` called in a forked child: the process doing the
forking serves a proxy from a thread of its own, and a child of a process with threads may
take no lock one of them held, which compiling a profile takes. What runs between the fork and
the program here is ``execve`` and nothing else. It is the same command Codex and Claude
Code's own sandboxes run their commands under, and has been on every Mac since 10.5.

Paths are named in a profile as the kernel resolves them, a link followed: `/tmp` is
`/private/tmp` to Seatbelt, as `/var` and `/etc` are, and a grant written `/tmp/x` would grant
nothing. Each path is granted as given and as it resolves, which is what Landlock does with a
path whose rule it opens. Metadata is left readable everywhere, as Landlock leaves it: a
program that cannot `stat` the directories above its own cannot find its way to them. So is
the root directory itself, though nothing beneath it: a Mac starts no program, `/bin/sh`
included, that cannot open `/`.

Two things the network part cannot say, and so says only as near as it can. A host is
`localhost` or `*` and nothing between, so a socket may be bound to every address wherever it
may be bound to loopback, and nothing asks which; and a Mach service that reaches the network
for whoever asks -- the system's URL session daemon -- is a way out that no rule on this
process's own sockets closes.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = ["SANDBOX_EXEC", "Profile", "available"]

#: The command a profile is applied with.
SANDBOX_EXEC: Final = "/usr/bin/sandbox-exec"

#: The pseudo-terminals a program may write to, however little else: the slave side of a
#: terminal it was started on, which Linux keeps under `/dev/pts` and a Mac numbers in `/dev`.
_TERMINALS: Final = r"^/dev/ttys[0-9]+$"

#: Where the system's resolver is asked for a name: a Unix socket, which is otherwise left
#: open while the network is cut, as Landlock leaves Unix sockets open. Shut, because a name
#: asked for is a name the resolver sends out -- a way out of a cut network one word at a time.
_RESOLVER: Final = "/private/var/run/mDNSResponder"


@functools.cache
def available() -> bool:
    """Whether a profile can be applied here at all.

    Asked of the machine rather than assumed of a Mac: a process already inside a sandbox --
    an agent's own, or an app's -- cannot apply another, and ``sandbox-exec`` there fails
    before it runs anything. So it is run once, with a profile that allows everything, and
    the answer kept for the life of this process.

    Returns:
      Whether this is a Mac whose ``sandbox-exec`` ran a program inside a profile.
    """
    if sys.platform != "darwin" or not os.access(SANDBOX_EXEC, os.X_OK):
        return False
    try:
        done = subprocess.run(
            [SANDBOX_EXEC, "-p", "(version 1)(allow default)", "/usr/bin/true"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _held(paths: Iterable[str]) -> list[str]:
    """Each path as given and as the kernel resolves it, each once."""
    return list(
        dict.fromkeys(
            one
            for path in paths
            for one in (os.path.normpath(path), os.path.realpath(path))
        )
    )


@dataclass(frozen=True, slots=True)
class Profile:
    """What a program run under :data:`SANDBOX_EXEC` may reach.

    Attributes:
      read: Absolute paths that may be read, listed and executed, with everything beneath.
      write: Absolute paths that may be read, executed and changed, with everything beneath.
      port: The one TCP port on loopback that may be connected to, where the network is cut;
        None leaves the network as it is.
    """

    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    port: int | None = None

    def rules(self) -> tuple[str, dict[str, str]]:
        """The profile, and the parameters the paths in it are named by.

        Named by parameter rather than written into the profile, so that a path holding a
        quote or a backslash is a path rather than the end of a string.

        Returns:
          The profile's text, and each parameter it reads with its value.
        """
        params: dict[str, str] = {}

        def named(paths: Sequence[str], prefix: str) -> str:
            held = _held(paths)
            for index, path in enumerate(held):
                params[f"{prefix}{index}"] = path
            return " ".join(
                f'(subpath (param "{prefix}{index}"))' for index in range(len(held))
            )

        lines = [
            "(version 1)",
            "(allow default)",
            "(deny file-read* file-write* process-exec)",
            "(allow file-read-metadata)",
            '(allow file-read-data (literal "/"))',
        ]
        if reading := named(self.read, "R"):
            lines.append(f"(allow file-read* process-exec {reading})")
        if writing := named(self.write, "W"):
            lines.append(f"(allow file-read* file-write* process-exec {writing})")
        lines.append(f'(allow file-read* file-write* (regex #"{_TERMINALS}"))')
        if self.port is not None:
            lines += [
                "(deny network*)",
                f'(allow network-outbound (remote tcp "localhost:{int(self.port)}"))',
                '(allow network-inbound (local tcp "localhost:*"))',
                "(allow network* (local unix-socket) (remote unix-socket))",
                f'(deny network-outbound (remote unix-socket (path-literal "{_RESOLVER}")))',
            ]
        return "\n".join(lines), params

    def command(self, argv: Sequence[str]) -> list[str]:
        """The command line that runs a program inside this profile.

        Args:
          argv: The program and its arguments; a name is looked up on the `PATH` of the
            environment the command is run with.

        Returns:
          ``sandbox-exec -D NAME=PATH ... -p PROFILE -- PROGRAM ARGS...``.
        """
        profile, params = self.rules()
        return [
            SANDBOX_EXEC,
            *(f"-D{name}={value}" for name, value in params.items()),
            "-p",
            profile,
            "--",
            *argv,
        ]
