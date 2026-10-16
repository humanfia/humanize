"""Command lines of the flow's own, put on a coding agent's PATH as programs it may run.

The other half of :mod:`hmz.coganchor.agents.tools`. A tool is something the model is told it
has; a command is something it finds out it has by running it, the way it finds out about every
other program on the machine -- `mycli --help`, then `mycli sub --help`, then the call. Which is
the one way of reaching the flow that needs nothing of the CLI driving the model: every one of
these that has a shell has a PATH, and a program on it is run by whatever the model runs.

So the program is a stand-in. What sits on PATH under the name the flow chose is a two-line
shell script that starts `hmz internal cli`, which carries the words it was run with to a socket
in this process and carries back what to print and what to exit with. The parsing happens in
this process too, in :meth:`~hmz.coganchor.faking.FakeCli.run`, with :mod:`argparse` and a
parser built from the pydantic models the flow declared, so that `--help`, a misspelt flag and
a missing argument are answered exactly as a real program's would be -- usage on stderr and
status 2 -- and the call itself is the flow's function, running in the flow's process with the
flow's variables, its answer printed as the program's output.

What is shelved is the agent's rather than one conversation's, for the reason its tools are: a
CLI is started with the environment it will hand its shell, and some of these are started once
per agent. Two conversations shelving a command line of one name are shelving one.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import socket
import sys
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from hmz.coganchor.faking import FakeCli

__all__ = ["Shelf"]

#: How long a socket nothing has connected to is waited on before the thread serving it looks
#: again at whether it has been closed, as for a toolbox.
_LOOKING = 0.2


class Shelf:
    """The command lines one agent's conversations are shelving, served over a socket.

    Held by the agent rather than by a session, as its toolbox is. Nothing is started until
    something is shelved; from then on it is a directory of this user's alone holding a `bin`
    of one script per command line and the socket those scripts reach this process on, which
    stays for as long as the agent does -- so that a process started with it on its PATH goes
    on finding whatever is shelved there next, and a process that was not is one to start
    again (:meth:`where`).
    """

    def __init__(self) -> None:
        """Initializes a shelf nothing has been put on and nothing is serving."""
        #: What each conversation is shelving, by the id of the conversation.
        self._held: dict[int, tuple[FakeCli, ...]] = {}
        self._lock = threading.RLock()
        self._sock: socket.socket | None = None
        self._closed = threading.Event()
        self._where: tempfile.TemporaryDirectory[str] | None = None

    def shelves(self, whose: int, clis: Iterable[FakeCli]) -> None:
        """Says which command lines one conversation is putting on the agent's PATH.

        Args:
          whose: Which conversation, by a number nothing else answers to.
          clis: The command lines, or nothing at all to take back whatever it was shelving.
        """
        held = tuple(clis)
        with self._lock:
            if held:
                self._held[whose] = held
            else:
                self._held.pop(whose, None)
            if held and self._where is None:
                self._start()
            if self._where is not None:
                self._stock(Path(self._where.name))

    def shelved(self) -> tuple[FakeCli, ...]:
        """Every command line on the agent's PATH now, one per name, in the order shelved."""
        with self._lock:
            found: dict[str, FakeCli] = {}
            for clis in self._held.values():
                for one in clis:
                    found.setdefault(one.name, one)
            return tuple(found.values())

    def empty(self) -> bool:
        """Whether nothing is being shelved: an agent with no command lines of the flow's."""
        with self._lock:
            return not self._held

    def where(self) -> str:
        """The directory holding the scripts and the socket, or "" while nothing ever was shelved.

        Which never changes once it is anything: a process started while it was "" is one with
        nothing of this on its PATH, and one started since has it there for good.
        """
        with self._lock:
            return "" if self._where is None else self._where.name

    def environ(self, environ: Mapping[str, str] | None = None) -> dict[str, str]:
        """What a process of the agent's has to be started with to find these on its PATH.

        Args:
          environ: The variables the process is otherwise being given, whose `PATH` is the one
            put after the scripts; this process's own where they say nothing of one.

        Returns:
          `PATH` with the scripts first, or nothing at all while nothing ever was shelved.
        """
        where = self.where()
        if not where:
            return {}
        rest = (environ or {}).get("PATH") or os.environ.get("PATH", os.defpath)
        return {"PATH": os.pathsep.join((str(Path(where) / "bin"), rest))}

    def close(self) -> None:
        """Stops serving, and takes the directory away. Doing it twice does it once."""
        self._closed.set()
        with self._lock:
            self._held.clear()
            sock, self._sock = self._sock, None
            where, self._where = self._where, None
        if sock is not None:
            sock.close()
        if where is not None:
            where.cleanup()

    def _start(self) -> None:
        """Makes the directory and starts serving on the socket inside it."""
        self._closed.clear()
        self._where = tempfile.TemporaryDirectory(
            prefix="humanize-clis-", ignore_cleanup_errors=True
        )
        # Inside a directory this user alone may enter, as a toolbox's is: the socket is a way
        # into this process.
        where = Path(self._where.name)
        where.chmod(0o700)
        (where / "bin").mkdir(mode=0o700)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(where / "cli.sock"))
        self._sock.listen(8)
        self._sock.settimeout(_LOOKING)
        threading.Thread(
            target=self._accepts, name="humanize-clis", daemon=True
        ).start()

    def _stock(self, where: Path) -> None:
        """Writes a script for every command line shelved, and takes away every other.

        Each is written whole and then moved into place, so that a shell running one while
        another is shelved runs the old one or the new one and never half of either.

        Args:
          where: The shelf's directory.
        """
        names = {one.name for one in self.shelved()}
        holder = where / "bin"
        if not holder.is_dir():
            return  # taken away under it -- at exit, a temporary directory cleaned first
        for old in holder.iterdir():
            if old.name not in names:
                with contextlib.suppress(OSError):
                    old.unlink()
        relay = shlex.join(
            [
                sys.executable,
                "-Pm",
                "hmz",
                "internal",
                "cli",
                "--at",
                str(where / "cli.sock"),
            ]
        )
        for name in names:
            script = f'#!/bin/sh\nexec {relay} --name {shlex.quote(name)} -- "$@"\n'
            if (holder / name).is_file() and (holder / name).read_text() == script:
                continue
            fd, made = tempfile.mkstemp(dir=holder, prefix=".", suffix=".tmp")
            with os.fdopen(fd, "w") as stream:
                stream.write(script)
            Path(made).chmod(0o700)
            Path(made).replace(holder / name)

    def _accepts(self) -> None:
        """Takes each connection and serves it on a thread of its own, until this is closed."""
        while not self._closed.is_set():
            sock = self._sock
            if sock is None:
                return
            try:
                held, _from = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return  # closed under us, which is what closing does
            threading.Thread(
                target=self._serves, args=(held,), name="humanize-cli", daemon=True
            ).start()

    def _serves(self, held: socket.socket) -> None:
        """Answers one run: one line asking, one line answering.

        Args:
          held: The connection.
        """
        with held, held.makefile("rwb") as stream:
            try:
                asked = json.loads(stream.readline())
                name, argv = str(asked["name"]), [str(one) for one in asked["argv"]]
            except (ValueError, KeyError, TypeError):
                return
            cli = next((one for one in self.shelved() if one.name == name), None)
            if cli is None:
                # Taken off the shelf while the shell still had it: the status a shell gives a
                # command it cannot find.
                code, out, err = 127, "", f"{name}: command not found\n"
            else:
                try:
                    code, out, err = cli.run(argv)
                except Exception as why:  # noqa: BLE001 -- a program that failed, not the flow
                    # A model no parser can be built from -- a field called `help` -- among
                    # whatever else: the run fails rather than the thread answering it.
                    code, out, err = 1, "", f"{name}: {type(why).__name__}: {why}\n"
            with contextlib.suppress(OSError):
                stream.write(
                    (json.dumps({"code": code, "out": out, "err": err}) + "\n").encode()
                )
                stream.flush()
