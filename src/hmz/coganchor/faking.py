"""What a flow hands a coding agent of its own: fake tools and fake command lines.

A fake tool is a tool the agent is told it has, and a fake command line is a program it finds
on its PATH and runs like any other -- `--help` and all. Neither is what it looks like: each
call of either is a function of the flow's, running in the flow's process, and what it answers
is what the agent reads back.

These are the values a flow writes, and the whole of what both sides know of them: a flow
declares them on a role (`hmz.flows` hands them on from here), the runtime gives them to the
agent's sessions, and :mod:`hmz.coganchor.agents.tools` and :mod:`hmz.coganchor.agents.clis`
put them in front of the CLI. Kept apart from both of those so that a flow importing them
costs no driver: this is the standard library, with pydantic fetched when a tool is first
described or a command line first run.
"""

from __future__ import annotations

import argparse
import enum
import functools
import io
import json
import sys
import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, NoReturn, Union, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from pydantic import BaseModel, ValidationError

__all__ = ["FakeCli", "FakeCommand", "FakeTool"]

#: What a command line may be called: a file name on PATH, which a shell finds by that name.
_NAMED = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


@dataclass(frozen=True, slots=True)
class FakeTool:
    """A function of the flow's, offered to the agent as a tool of its own.

    The agent calling it is the function running, in the flow's process, as the flow::

        async def remember(said: Note) -> str:
            notes.append(said.text)
            return "noted"

        class Scribe(Agent, FakeToolAgentMixin):
            _tools = (FakeTool("remember", "Writes a note down for later.", remember, Note),)

    Attributes:
      name: What the agent calls it, which is what it must be told to use. A tool named for
        what it does is a tool a model reaches for at the right moment.
      about: What it is for, said to the model. This is the whole of what the model knows
        about when to use it, so it is a sentence rather than a label.
      takes: The shape of what it is called with, as a pydantic model, or None for a tool
        that takes nothing. The model is the whole of what the agent is told: its fields,
        their types, which are required and the description each was declared with are
        already in it, so nothing about the arguments is said twice.
      call: What to run when the agent reaches for it. It is given the arguments -- the model
        where one was declared, and nothing at all where none was -- and what it answers is
        put in front of the agent as text: a string as it is, None as `done`, anything else as
        JSON. What it raises is the tool failing, which the agent is told of; the turn goes on.
        Declared by a flow, it may be sync or async, and the runtime runs it on the flow's loop
        as the flow; handed to :mod:`hmz.coganchor.agents` directly, it is sync and runs on the
        thread serving the tool call.
    """

    name: str
    about: str
    call: Callable[..., Any]
    takes: type[BaseModel] | None = None

    def schema(self) -> dict[str, Any]:
        """What the agent is told this tool takes, as the JSON Schema the protocol wants.

        Returns:
          The model's own schema, or the schema of a tool that takes nothing.
        """
        if self.takes is None:
            return {"type": "object", "properties": {}}
        return self.takes.model_json_schema()

    def called(self, given: Mapping[str, Any]) -> str:
        """Runs the callback and says what it answered, in words the agent can read.

        Args:
          given: What the agent called it with.

        Returns:
          What the callback answered, as text. A callback that answers with nothing is a tool
          that did something rather than one that failed, and says so.

        Raises:
          Exception: Whatever the callback raised, which is answered to the agent as the tool
            having failed rather than as the turn having failed: a flow must not end because
            a model called one of its tools wrongly.
        """
        said = self.call() if self.takes is None else self.call(self.takes(**given))
        if said is None:
            return "done"
        return said if isinstance(said, str) else json.dumps(said, default=str)


@dataclass(frozen=True, slots=True)
class FakeCommand:
    """One subcommand of a command line of the flow's, and the function that answers it.

    Attributes:
      name: What the agent types after the program's name to reach it.
      about: What it is for, in a sentence: the line `--help` lists it under, and the
        description its own `--help` opens with.
      call: What to run when the agent runs it. It is given the arguments -- the model where
        one was declared, and nothing where none was -- and what it answers is printed: text
        as it is, None as nothing, and anything else as JSON. Raising `SystemExit` exits with
        that status, as a program's own `sys.exit` does; raising anything else exits with 1
        and the error on stderr. Declared by a flow, it may be sync or async and runs as the
        flow, as a tool's does; handed to :mod:`hmz.coganchor.agents` directly, it is sync and
        runs on the thread serving that one run.
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
class FakeCli:
    """A command line of the flow's own, which the agent finds on its PATH and runs.

    It answers `--help`, a misspelt flag and a missing one as any program does, and each run of
    a command is its function running in the flow::

        class Ticket(pydantic.BaseModel):
            title: str = pydantic.Field(description="What the ticket says.")

        async def file(ticket: Ticket) -> str:
            tickets.append(ticket.title)
            return f"filed #{len(tickets)}"

        class Triager(Agent):
            _clis = (
                FakeCli("tix", "Files tickets.", (FakeCommand("file", "Files one", file, Ticket),)),
            )

    Attributes:
      name: The program's name, which is what the agent runs: a file name, with no `/`.
      about: What it is for, which its `--help` opens with.
      commands: Its subcommands, at least one, each named once.
    """

    name: str
    about: str
    commands: tuple[FakeCommand, ...]

    def __post_init__(self) -> None:
        """Refuses a command line no shell could find, or one whose commands collide.

        Raises:
          ValueError: If the name is not a plain file name, there are no commands, or two
            commands share a name.
        """
        # A tuple whatever it was given as, so that a command line is a value like any other.
        object.__setattr__(self, "commands", tuple(self.commands))
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
    command: FakeCommand,
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
