"""Command lines of the flow's own, put on a coding agent's PATH as programs it may run.

The other half of :mod:`hmz.coganchor.agents.tools`. A tool is something the model is told it
has; a command is something it finds out it has by running it, the way it finds out about every
other program on the machine -- `mycli --help`, then `mycli sub --help`, then the call. Which is
the one way of reaching the flow that needs nothing of the CLI driving the model: every one of
these that has a shell has a PATH, and a program on it is run by whatever the model runs.

So the program is a stand-in. What sits on PATH under the name the flow chose is a two-line
shell script that starts `hmz internal cli`, which carries the words it was run with to a socket
in this process and carries back what to print and what to exit with. The parsing happens here,
with :mod:`argparse` and a parser built from the pydantic models the flow declared, so that
`--help`, a misspelt flag and a missing argument are answered exactly as a real program's would
be -- usage on stderr and status 2 -- and the call itself is the flow's function, running in the
flow's process with the flow's variables, its answer printed as the program's output.

What is shelved is the agent's rather than one conversation's, for the reason its tools are: a
CLI is started with the environment it will hand its shell, and some of these are started once
per agent. Two conversations shelving a command line of one name are shelving one.
"""

from __future__ import annotations

import argparse
import contextlib
import enum
import functools
import io
import json
import os
import shlex
import socket
import sys
import tempfile
import threading
import types
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NoReturn, Union, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from pydantic import BaseModel, ValidationError

__all__ = ["Cli", "Command", "Shelf"]

#: How long a socket nothing has connected to is waited on before the thread serving it looks
#: again at whether it has been closed, as for a toolbox.
_LOOKING = 0.2

#: What a command line may be called: a file name on PATH, which a shell finds by that name.
_NAMED = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


@dataclass(frozen=True, slots=True)
class Command:
    """One subcommand of a command line of the flow's, and the function that answers it.

    Attributes:
      name: What the agent types after the program's name to reach it.
      about: What it is for, in a sentence: the line `--help` lists it under, and the
        description its own `--help` opens with.
      call: What to run when the agent runs it. It is given the arguments -- the model where
        one was declared, and nothing where none was -- and what it answers is printed: text
        as it is, None as nothing, and anything else as JSON. Raising `SystemExit` exits with
        that status, as a program's own `sys.exit` does; raising anything else exits with 1
        and the error on stderr. It runs on the thread serving that one run.
      takes: The options it takes, as a pydantic model, or None for a command that takes none.
        Each field is a `--flag` named for it: its description is the flag's help, a field with
        no default is a required flag, a `bool` is a `--flag/--no-flag` pair, a list takes
        several words, and a `Literal` or an `Enum` takes one of its values. What is typed is
        validated by the model, so a value it refuses is a usage error like any other.
    """

    name: str
    about: str
    call: Callable[..., Any]
    takes: type[BaseModel] | None = None


@dataclass(frozen=True, slots=True)
class Cli:
    """A command line of the flow's own, as the agent finds it on its PATH.

    Attributes:
      name: The program's name, which is what the agent runs: a file name, with no `/`.
      about: What it is for, which its `--help` opens with.
      commands: Its subcommands, at least one, each named once.
    """

    name: str
    about: str
    commands: tuple[Command, ...]

    def __post_init__(self) -> None:
        """Refuses a command line no shell could find, or one whose commands collide.

        Raises:
          ValueError: If the name is not a plain file name, there are no commands, or two
            commands share a name.
        """
        if not self.name or self.name[0] in ".-" or not set(self.name) <= _NAMED:
            raise ValueError(f"{self.name!r} is not a name a shell can run")
        names = [one.name for one in self.commands]
        if not names:
            raise ValueError(f"{self.name} has no commands")
        if len(set(names)) != len(names):
            raise ValueError(f"{self.name} names a command twice")

    def run(self, argv: Sequence[str]) -> tuple[int, str, str]:
        """Answers one run of this program, as a program would have.

        Args:
          argv: The words it was run with, after its own name.

        Returns:
          What it exits with, what it prints on stdout and what it prints on stderr: a help
          asked for is the help and 0, a line the parser refuses is the usage, the error and
          2, and a line it takes is whatever the command's function made of it.
        """
        from pydantic import ValidationError

        out, err = io.StringIO(), io.StringIO()
        said = (out, err)
        parser = _Parser(prog=self.name, description=self.about, said=said)
        chosen = parser.add_subparsers(
            dest="_command", metavar="COMMAND", title="commands", required=True
        )
        parsers: dict[str, _Parser] = {}
        for one in self.commands:
            parsers[one.name] = sub = chosen.add_parser(
                one.name, help=one.about, description=one.about, said=said
            )
            if one.takes is not None:
                _options(sub, one.takes)
        try:
            given = vars(parser.parse_args(list(argv)))
            named = given.pop("_command")
            command = next(one for one in self.commands if one.name == named)
            try:
                taken = (
                    None
                    if command.takes is None
                    else command.takes.model_validate(given, by_name=True)
                )
            except ValidationError as why:
                parsers[command.name].error(_refused(why))
        except _Exited as exited:
            return exited.code, out.getvalue(), err.getvalue()
        return _called(self.name, command, taken, out, err)


def _called(
    name: str,
    command: Command,
    taken: BaseModel | None,
    out: io.StringIO,
    err: io.StringIO,
) -> tuple[int, str, str]:
    """Runs a command's function and says what the program printed and exits with.

    Args:
      name: The program's name, which an error is printed under.
      command: The command run.
      taken: Its arguments, or None for a command that takes none.
      out: Where its output goes.
      err: Where its errors go.

    Returns:
      The status, stdout and stderr.
    """
    from pydantic import BaseModel

    code = 0
    try:
        said = command.call() if taken is None else command.call(taken)
    except SystemExit as leaving:
        # The function leaving the way a program does, with the status it chose.
        said = None
        if isinstance(leaving.code, int) or leaving.code is None:
            code = leaving.code or 0
        else:
            err.write(f"{leaving.code}\n")
            code = 1
    except Exception as why:  # noqa: BLE001 -- the program failing, not the flow
        said = None
        err.write(f"{name}: {type(why).__name__}: {why}\n")
        code = 1
    if isinstance(said, BaseModel):
        said = said.model_dump(mode="json")
    if isinstance(said, str):
        out.write(said if not said or said.endswith("\n") else said + "\n")
    elif said is not None:
        out.write(json.dumps(said, indent=2, default=str) + "\n")
    return code, out.getvalue(), err.getvalue()


def _refused(why: ValidationError) -> str:
    """What the model refused, said the way a parser says a flag was wrong.

    Returns:
      Each error on the flag it is about, one after another.
    """
    return "; ".join(
        f"--{str(error['loc'][0]).replace('_', '-')}: {error['msg']}"
        if error["loc"]
        else error["msg"]
        for error in why.errors()
    )


class _Exited(Exception):  # noqa: N818 -- what it is, not what went wrong
    """The parser finishing the run, with the status it finished it with."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class _Parser(argparse.ArgumentParser):
    """A parser that prints into the run it is answering and exits by returning to it.

    Every parser of one run writes into the same two buffers, which is what a subcommand's
    parser -- made by `add_parser` with the arguments its parent was made with -- needs to be
    told: the process it is printing for is not this one.
    """

    def __init__(
        self, *args: Any, said: tuple[io.StringIO, io.StringIO], **kwargs: Any
    ) -> None:
        if sys.version_info >= (3, 14):
            # Never coloured: what is printed goes to a program's stdout, not this terminal.
            kwargs["color"] = False
        super().__init__(*args, **kwargs)
        self._said = said

    def print_help(self, file: Any = None) -> None:
        del file
        self._said[0].write(self.format_help())

    def print_usage(self, file: Any = None) -> None:
        self._said[1 if file is sys.stderr else 0].write(self.format_usage())

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._said[1].write(message)
        raise _Exited(status)


def _options(parser: argparse.ArgumentParser, model: type[BaseModel]) -> None:
    """Gives a parser a `--flag` for each field of a model.

    Every value is taken as the words typed and handed to the model as they are, which is what
    turns them into the field's type -- so a flag converts exactly as the model validates, and
    nothing about a type is said twice.

    Args:
      parser: The command's parser.
      model: What the command takes.
    """
    for name, field in model.model_fields.items():
        kind, many = _shape(field.annotation)
        said = field.description or ""
        options: dict[str, Any] = {"dest": name}
        if field.is_required():
            options["required"] = True
        else:
            # Left out of what is parsed rather than defaulted here: the model's default is
            # the one, factory and all.
            options["default"] = argparse.SUPPRESS
            if field.default_factory is None:
                default = (
                    field.default.value
                    if isinstance(field.default, enum.Enum)
                    else field.default
                )
                said = f"{said} (default: {default})".strip()
        if kind is bool and not many:
            options["action"] = argparse.BooleanOptionalAction
        elif choices := _choices(kind):
            options["choices"] = list(choices.values())
            options["type"] = functools.partial(_chosen, choices)
        else:
            options["metavar"] = name.upper()
        if many:
            options["nargs"] = "*"
        parser.add_argument(
            f"--{name.replace('_', '-')}",
            help=said.replace("%", "%%") or None,
            **options,
        )


def _shape(annotation: Any) -> tuple[Any, bool]:
    """What one field holds, and whether it holds several of them.

    Args:
      annotation: The field's type.

    Returns:
      The type of one value, with an optional's None taken off, and whether the field is a
      list, tuple or set of them.
    """
    if get_origin(annotation) in (Union, types.UnionType):
        held = [one for one in get_args(annotation) if one is not type(None)]
        if len(held) == 1:
            annotation = held[0]
    if get_origin(annotation) in (list, tuple, set, frozenset):
        held = [one for one in get_args(annotation) if one is not Ellipsis]
        return (held[0] if held else str), True
    return annotation, False


def _choices(kind: Any) -> dict[str, Any] | None:
    """The values a field may take, by how each is typed, where it may take only some.

    Returns:
      Each value of a `Literal` or an `Enum`, or None for any other type. By the words
      rather than as the words, since `Literal[1, 2]` is a field that refuses `"1"`.
    """
    if get_origin(kind) is Literal:
        return {str(one): one for one in get_args(kind)}
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return {str(one.value): one.value for one in kind}
    return None


def _chosen(choices: Mapping[str, Any], typed: str) -> Any:
    """The choice a word is, or the word itself where it is none, for the parser to refuse."""
    return choices.get(typed, typed)


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
        self._held: dict[int, tuple[Cli, ...]] = {}
        self._lock = threading.RLock()
        self._sock: socket.socket | None = None
        self._closed = threading.Event()
        self._where: tempfile.TemporaryDirectory[str] | None = None

    def shelves(self, whose: int, clis: Iterable[Cli]) -> None:
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

    def shelved(self) -> tuple[Cli, ...]:
        """Every command line on the agent's PATH now, one per name, in the order shelved."""
        with self._lock:
            found: dict[str, Cli] = {}
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
