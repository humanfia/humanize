"""The commands of `hmz`, each said once: what it takes, what it does, what it answers.

A command is a :class:`Command` in a module of `hmz.cli.commands`, found there by name. What
is written in it is everything anybody is told about it: the line it parses, its `--help`, the
fields of its `--json`, the entry `hmz help --json` gives an agent, and the skill `hmz skills
add` installs are all read off the one declaration, so that none of them can say something the
others do not (Section 3 of cli.md).

Every command here is a client of a daemon (:class:`hmz.sdk.Client`) and takes the same three
options: `--json` for one JSON document instead of text, `--daemon` for a daemon other than
this machine's, and `--no-color`. It answers with the same exit statuses: 0 done, 1 refused by
the daemon, 2 a line that cannot be read, 3 a daemon that cannot be reached.

But for a command that is `local`, which asks no daemon: what it does is done on this machine,
to this user's own files, so it takes no `--daemon`, and it is refused here or not at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Any, Final, NoReturn

from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from hmz.sdk import Client

__all__ = [
    "DONE",
    "REFUSED",
    "UNREACHED",
    "UNREAD",
    "Arg",
    "Call",
    "Command",
    "Example",
    "Exit",
    "Field",
    "commands",
    "described",
    "helps",
    "runs",
    "table",
]

DONE: Final = 0
REFUSED: Final = 1
UNREAD: Final = 2
UNREACHED: Final = 3


@dataclass(frozen=True)
class Arg:
    """One thing a command takes: a positional where `flags` is one bare name, else an option."""

    flags: tuple[str, ...]
    """`("name",)` for a positional; `("-a", "--agent")` for an option."""
    says: str
    """What it is, in one text of :mod:`hmz.words`."""
    metavar: str | None = None
    """What its value is shown as; None for a switch, and for a positional its own name."""
    many: bool = False
    """Whether an option may be given more than once, or a positional takes every word left."""
    required: bool = False
    """Whether an option must be given; a positional must unless it has a default."""
    default: Any = None
    """What it is where it is not given."""
    choices: tuple[str, ...] = ()
    """The only values it takes, where there are only some."""
    kind: Callable[[str], Any] = str
    """What reads its value."""

    @property
    def positional(self) -> bool:
        """Whether it is given by place rather than by name."""
        return not self.flags[0].startswith("-")

    @property
    def name(self) -> str:
        """What it is read back as: the long flag, or the positional, with `_` for `-`."""
        return self.flags[-1].lstrip("-").replace("-", "_")

    @property
    def switch(self) -> bool:
        """Whether it is an option that takes no value."""
        return not self.positional and self.metavar is None and not self.choices


@dataclass(frozen=True)
class Example:
    """One line somebody might type, and what it does."""

    line: str
    """The line, beginning `hmz`."""
    says: str
    """What it does, in one text of :mod:`hmz.words`."""


@dataclass(frozen=True)
class Field:
    """One field of what a command answers under `--json`."""

    name: str
    """Where it is, dotted from the top of the document; `[]` after a list (`chats[].id`)."""
    kind: str
    """What it is: `string`, `integer`, `number`, `boolean`, `object`, `list`."""
    says: str
    """What it holds, in one text of :mod:`hmz.words`."""


@dataclass(frozen=True)
class Exit:
    """One exit status a command ends with beyond the four every command has."""

    code: int
    says: str


@dataclass(frozen=True)
class Command:
    """One command, or a group of them.

    A group has `commands` and no `run`; a command has `run` and no `commands`. A command of
    the older kind, which reads its own line, has `passes` instead: it is given every word
    after its name, `--help` among them, and is in the tree to be listed.
    """

    name: str
    summary: str
    """What it does, in a line: one text of :mod:`hmz.words`, lower case, no full stop."""
    says: str = ""
    """What it does, in a paragraph; the summary where there is no more to say."""
    args: tuple[Arg, ...] = ()
    examples: tuple[Example, ...] = ()
    output: tuple[Field, ...] = ()
    """The fields of its `--json` document."""
    prints: str = ""
    """What it prints without `--json`, in one text of :mod:`hmz.words`."""
    exits: tuple[Exit, ...] = ()
    methods: tuple[str, ...] = ()
    """The methods of `protocol/openrpc.json` it calls."""
    see: tuple[str, ...] = ()
    """Other commands worth reading beside it, each as its path (`chat list`)."""
    run: Callable[[Call], int | None] | None = None
    passes: Callable[[list[str]], int] | None = None
    commands: tuple[Command, ...] = ()
    local: bool = False
    """Whether it asks no daemon: it then takes no `--daemon` and never ends unreached."""

    def texts(self) -> Iterable[str]:
        """Every text this command and the ones under it say."""
        yield self.summary
        if self.says:
            yield self.says
        if self.prints:
            yield self.prints
        for arg in self.args:
            yield arg.says
        for example in self.examples:
            yield example.says
        for one in self.output:
            yield one.says
        for status in self.exits:
            yield status.says
        if self.local:
            yield _LOCALLY.says
        for under in self.commands:
            yield from under.texts()


#: What every command of the tree takes, after its own.
COMMON: Final = (
    Arg(("--json",), "print one JSON document instead of text"),
    Arg(
        ("--daemon",),
        "ask the daemon named in the daemon list, or this machine's daemon",
        metavar="NAME",
    ),
    Arg(("--no-color",), "print without terminal colours"),
)

#: The statuses every command of the tree ends with.
EXITS: Final = (
    Exit(DONE, "did what was asked"),
    Exit(REFUSED, "the daemon refused the request and its reason was printed"),
    Exit(UNREAD, "the command line could not be read"),
    Exit(UNREACHED, "the daemon could not be reached"),
)

#: What a command that asks no daemon ends with where it will not do what was asked.
_LOCALLY: Final = Exit(REFUSED, "the request was refused and the reason was printed")


def _common(command: Command) -> tuple[Arg, ...]:
    """What a command takes after its own: every common option a daemon is not asked by."""
    if not command.local:
        return COMMON
    return tuple(arg for arg in COMMON if arg.name != "daemon")


def _statuses(command: Command) -> list[Exit]:
    """The statuses a command ends with, in order: the common ones, then its own."""
    common = (EXITS[0], _LOCALLY, EXITS[2]) if command.local else EXITS
    return sorted((*common, *command.exits), key=lambda one: one.code)


@dataclass
class Call:
    """One command being run: what it was given, and how it asks and answers."""

    path: tuple[str, ...]
    """The command, as the words after `hmz`."""
    given: argparse.Namespace
    """What the line gave it, each :class:`Arg` under its `name`."""
    json: bool = False
    daemon: str = ""
    _client: Client | None = field(default=None, repr=False)

    def __getattr__(self, name: str) -> Any:
        """What the line gave for one of the command's own arguments."""
        return getattr(self.given, name)

    @property
    def client(self) -> Client:
        """A session with the daemon asked for, opened when first wanted and closed after.

        Raises:
          OSError: If it cannot be reached.
        """
        if self._client is None:
            self._client = reach(self.daemon)
        return self._client

    def answers(self, document: Mapping[str, Any], lines: Iterable[str] = ()) -> None:
        """Says what the command found: the document under `--json`, the lines without.

        Args:
          document: What `--json` prints, whose fields the command's `output` names.
          lines: What is printed otherwise, a line apiece.
        """
        if self.json:
            print(json.dumps(document, ensure_ascii=False))
        else:
            for line in lines:
                print(line)

    def close(self) -> None:
        """Lets go of the session, where one was opened."""
        if self._client is not None:
            self._client.close()
            self._client = None


def reach(daemon: str) -> Client:
    """A session with a daemon: this machine's for `""`, else the one kept under a name.

    Raises:
      OSError: If it cannot be reached.
      hmz.sdk.Refused: If nothing is kept under that name.
    """
    from hmz.sdk import Client, Refused

    if daemon:
        raise Refused(t("No daemon is kept under the name {name}.", name=daemon))
    return Client.local(kind="cli")


def table(rows: Sequence[Sequence[str]]) -> list[str]:
    """Rows as lines, each column as wide as its widest cell, two spaces between."""
    if not rows:
        return []
    widths = [max(len(row[at]) for row in rows) for at in range(len(rows[0]))]
    return [
        "  ".join(
            cell.ljust(width) for cell, width in zip(row, widths, strict=True)
        ).rstrip()
        for row in rows
    ]


@cache
def commands() -> dict[str, Command]:
    """Every command of `hmz.cli.commands`, by name, in the order of their modules' names."""
    import pkgutil
    from importlib import import_module

    from . import commands as package

    found: dict[str, Command] = {}
    for module in sorted(
        pkgutil.iter_modules(package.__path__), key=lambda one: one.name
    ):
        if module.name.startswith("_"):
            continue
        held: tuple[Command, ...] = import_module(
            f"{package.__name__}.{module.name}"
        ).COMMANDS
        for command in held:
            if command.name in found:
                raise RuntimeError(f"two commands are called {command.name!r}")
            found[command.name] = command
    return found


def _usage(path: Sequence[str], command: Command) -> str:
    """The line a command takes, as its help opens with it."""
    words = ["hmz", *path]
    if command.commands:
        return " ".join([*words, "COMMAND", "..."])
    for arg in command.args:
        if arg.positional:
            shown = (arg.metavar or arg.name).upper()
            shown = f"{shown}..." if arg.many else shown
            words.append(
                shown if arg.default is None and not arg.many else f"[{shown}]"
            )
        elif arg.required:
            words.append(f"{arg.flags[-1]} {arg.metavar}")
    if any(not arg.positional and not arg.required for arg in command.args):
        words.append(f"[{t('options')}]")
    return " ".join(words)


def _flags(arg: Arg) -> str:
    if arg.positional:
        return (arg.metavar or arg.name).upper()
    value = arg.metavar or ("{" + ",".join(arg.choices) + "}" if arg.choices else "")
    return ", ".join(arg.flags) + (f" {value}" if value else "")


def _said(arg: Arg) -> str:
    """What an argument is, with what it takes and what it is left as put after."""
    said = t(arg.says)
    if arg.choices and arg.metavar:
        said += " (" + ", ".join(arg.choices) + ")"
    if arg.default not in (None, False, "", ()):
        said += " [" + t("default: {value}", value=arg.default) + "]"
    if arg.many and not arg.positional:
        said += " [" + t("may be given more than once") + "]"
    return said


def _listed(pairs: Sequence[tuple[str, str]]) -> list[str]:
    width = max((len(left) for left, _ in pairs), default=0)
    return [f"  {left.ljust(width)}  {right}".rstrip() for left, right in pairs]


def helps(path: Sequence[str], command: Command) -> str:
    """Everything `--help` says of a command: enough to use it without reading anything else.

    The same sections in the same order for every command, the empty ones left out: the line
    it takes, what it does, the commands under it, what it takes by place and by name, lines
    to type, what it prints and the fields of its `--json`, the statuses it ends with, and
    what to read beside it.
    """
    out = [
        f"{t('Usage')}: {_usage(path, command)}",
        "",
        t(command.says or command.summary),
    ]

    def section(title: str, lines: Sequence[str]) -> None:
        if lines:
            out.extend(["", f"{t(title)}:", *lines])

    section(
        "Commands", _listed([(one.name, t(one.summary)) for one in command.commands])
    )
    if command.commands:
        run = " ".join(["hmz", *path, "COMMAND", "--help"])
        out.extend(
            ["", t("Run `{line}` to read everything about one command.", line=run)]
        )
        return "\n".join(out) + "\n"
    if command.passes is not None:
        return "\n".join(out) + "\n"
    placed = [arg for arg in command.args if arg.positional]
    named = [arg for arg in (*command.args, *_common(command)) if not arg.positional]
    section("Arguments", _listed([(_flags(arg), _said(arg)) for arg in placed]))
    section(
        "Options",
        _listed(
            [
                *((_flags(arg), _said(arg)) for arg in named),
                ("-h, --help", t("show this help and exit")),
            ]
        ),
    )
    examples: list[str] = []
    for example in command.examples:
        examples.extend([f"  {example.line}", f"      {t(example.says)}"])
    section("Examples", examples)
    output = [f"  {t(command.prints)}"] if command.prints else []
    if command.output:
        output.append(f"  {t('With `--json`, prints one object with these fields:')}")
        fields = [[one.name, one.kind, t(one.says)] for one in command.output]
        output.extend(f"    {line}" for line in table(fields))
    section("Output", output)
    section(
        "Exit codes",
        _listed([(str(one.code), t(one.says)) for one in _statuses(command)]),
    )
    if command.methods:
        section("Daemon calls", [f"  {', '.join(command.methods)}"])
    section("See also", [f"  hmz {one} --help" for one in command.see])
    return "\n".join(out) + "\n"


def described(path: Sequence[str], command: Command) -> dict[str, Any]:
    """A command as one JSON object: what `hmz help --json` and the skill are written from."""
    said: dict[str, Any] = {
        "command": " ".join(["hmz", *path]),
        "summary": t(command.summary),
        "description": t(command.says or command.summary),
        "usage": _usage(path, command),
    }
    if command.commands:
        said["commands"] = [
            described([*path, one.name], one) for one in command.commands
        ]
        return said
    if command.passes is not None:
        return said
    said["arguments"] = [
        {
            "name": _flags(arg),
            "flags": list(arg.flags),
            "description": t(arg.says),
            "positional": arg.positional,
            "required": arg.required
            or (arg.positional and arg.default is None and not arg.many),
            "repeatable": arg.many,
            "takes_value": not arg.switch,
            "choices": list(arg.choices),
            "default": arg.default,
        }
        for arg in (*command.args, *_common(command))
    ]
    said["examples"] = [
        {"line": one.line, "does": t(one.says)} for one in command.examples
    ]
    said["prints"] = t(command.prints) if command.prints else ""
    said["json"] = [
        {"field": one.name, "type": one.kind, "description": t(one.says)}
        for one in command.output
    ]
    said["exit_status"] = {str(one.code): t(one.says) for one in _statuses(command)}
    said["daemon_methods"] = list(command.methods)
    said["see_also"] = [f"hmz {one}" for one in command.see]
    return said


class _Parser(argparse.ArgumentParser):
    """A parser that says a command's whole declaration for `--help`, and refuses in one voice."""

    said: Callable[[], str] | None = None

    def format_help(self) -> str:
        return self.said() if self.said is not None else super().format_help()

    def error(self, message: str) -> NoReturn:
        self.exit(
            UNREAD,
            f"{self.prog}: {message}\n{t('Run `{line}` for help.', line=self.prog + ' --help')}\n",
        )


def _adds(parser: argparse.ArgumentParser, arg: Arg) -> None:
    if arg.switch:
        parser.add_argument(*arg.flags, action="store_true", dest=arg.name)
        return
    taken: dict[str, Any] = {"type": arg.kind, "default": arg.default}
    if arg.choices:
        taken["choices"] = arg.choices
    if arg.positional:
        if arg.many:
            taken["nargs"] = "*"
        elif arg.default is not None:
            taken["nargs"] = "?"
        parser.add_argument(
            arg.name, metavar=(arg.metavar or arg.name).upper(), **taken
        )
        return
    if arg.many:
        taken.update(action="append", default=None)
    parser.add_argument(
        *arg.flags, dest=arg.name, metavar=arg.metavar, required=arg.required, **taken
    )


def _parser(path: tuple[str, ...], command: Command) -> _Parser:
    parser = _Parser(prog=" ".join(["hmz", *path]), add_help=False, allow_abbrev=False)
    parser.said = lambda: helps(path, command)
    parser.add_argument("-h", "--help", action="help")
    if command.commands:
        # Nothing but `--help`: `runs` walks the groups itself.
        parser.add_argument("_rest", nargs="*")
        return parser
    for arg in (*command.args, *_common(command)):
        _adds(parser, arg)
    return parser


def _failed(call: Call | None, path: Sequence[str], code: int, message: str) -> None:
    """Says why a command was not done: a document under `--json`, a line without."""
    if call is not None and call.json:
        print(
            json.dumps(
                {"error": {"code": code, "message": message}}, ensure_ascii=False
            )
        )
    else:
        print(f"{' '.join(['hmz', *path])}: {message}", file=sys.stderr)


def runs(argv: Sequence[str]) -> int:
    """Runs the command a line names, which begins with the name of one of :func:`commands`.

    Args:
      argv: The words after `hmz`.

    Returns:
      Its exit status.
    """
    from hmz.sdk import Refused

    command = commands()[argv[0]]
    path: tuple[str, ...] = (argv[0],)
    rest = list(argv[1:])
    if command.passes is not None:
        return command.passes(rest)
    # Down the groups by name, so that a group's help is its own and a command's is its own.
    while command.commands and rest and not rest[0].startswith("-"):
        under = {one.name: one for one in command.commands}
        if rest[0] not in under:
            _parser(path, command).error(t("no command named {name}", name=rest[0]))
        command, path, rest = under[rest[0]], (*path, rest[0]), rest[1:]
    parser = _parser(path, command)
    if command.commands:
        # A group named with nothing under it is asking what there is.
        if not rest:
            print(helps(path, command), end="")
            return DONE
        parser.parse_args(rest)
        parser.error(t("needs a command name"))
    given = parser.parse_args(rest)
    call = Call(
        path, given, json=given.json, daemon=getattr(given, "daemon", None) or ""
    )
    if command.run is None:
        raise RuntimeError(f"{' '.join(path)} does nothing")
    try:
        return command.run(call) or DONE
    except Refused as why:
        _failed(call, path, getattr(why, "code", 0) or 0, str(why))
        return REFUSED
    except TimeoutError as why:
        _failed(call, path, 504, str(why))
    except OSError as why:
        if command.local:
            # A file of this machine's that would not be read or written: nobody was asked.
            _failed(call, path, 0, str(why))
            return REFUSED
        from .output import unreached

        _failed(call, path, 503, unreached(why).removeprefix("hmz: "))
    finally:
        call.close()
    return UNREACHED
