"""The commands of `hmz`, each said once: what it takes, what it does, what it answers.

A command is a :class:`Command` in a module of `hmz.cli.commands`, found there by name. What
is written in it is everything anybody is told about it: the line it parses, its `--help`, the
fields of its `--json`, the entry `hmz help --json` gives an agent, and the skill `hmz skills
add` installs are all read off the one declaration, so that none of them can say something the
others do not (Section 3 of cli.md).

Every command here is a client of a daemon (:class:`hmz.sdk.Client`) and takes the same three
options: `--json` for one JSON document instead of text, `--daemon` for a daemon other than
this machine's, and `--no-color`. It answers with the same exit statuses: 0 done, 1 refused by
the daemon, 2 a line that cannot be read, 3 a daemon that cannot be reached, 130 interrupted.

What more than one command does the same way is here too, so that it is done one way: a line
that parsed and still cannot be read (:class:`Unread`), the workspace a line names
(:data:`WORKSPACE`, :func:`workspace`), and asking before something is removed (:data:`YES`,
:func:`sure`).

But for a command that is `local`, which asks no daemon: what it does is done on this machine,
to this user's own files, so it takes no `--daemon`, and it is refused here or not at all.
"""

from __future__ import annotations

import argparse
import json
import os
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
    "INTERRUPTED",
    "LOCALLY",
    "REFUSED",
    "UNREACHED",
    "UNREAD",
    "WORKSPACE",
    "YES",
    "Arg",
    "Call",
    "Command",
    "Example",
    "Exit",
    "Field",
    "Page",
    "Unread",
    "asks",
    "commands",
    "described",
    "helps",
    "named",
    "parser",
    "runs",
    "sure",
    "table",
    "taken",
    "whole",
    "workspace",
]

DONE: Final = 0
REFUSED: Final = 1
UNREAD: Final = 2
UNREACHED: Final = 3
INTERRUPTED: Final = 130

#: The code a line that cannot be read is answered with under `--json`: a bad request.
_BAD: Final = 400

#: The code a daemon that cannot be reached is answered with, and a call whose session ended.
_WENT: Final = 503


class Unread(Exception):  # noqa: N818 -- named for what happened
    """A line that parsed and still cannot be read, with what is wrong with it.

    Raised by a command for what only it can tell of its line -- a value that is not JSON, two
    options that cannot both be given -- and said as the parser says a usage error.
    """


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
    """One exit status a command ends with beyond those every command has.

    One whose `code` is a common one says what that status means of this command instead.
    """

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
            yield LOCALLY.says
        elif YES in self.args:
            yield _ASKED.says
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
    Exit(INTERRUPTED, "interrupted with ctrl+c"),
)

#: The workspace a command is about, where it is about one: the folder it is typed in, unnamed.
WORKSPACE: Final = Arg(
    ("-w", "--workspace"),
    "the workspace, a folder on the daemon's machine; the "
    "current directory when not given",
    metavar="DIR",
)

#: What a command that asks before it removes something takes to be told not to ask.
YES: Final = Arg(("-y", "--yes"), "do it without asking first")

#: What a command that asks ends with where it was refused: by the daemon, or by the answer.
_ASKED: Final = Exit(
    REFUSED,
    "the daemon refused it, or you did not answer yes",
)

#: What a command that asks no daemon ends with where it will not do what was asked.
LOCALLY: Final = Exit(REFUSED, "the request was refused and the reason was printed")


def _common(command: Command) -> tuple[Arg, ...]:
    """What a command takes after its own: every common option a daemon is not asked by."""
    if not command.local:
        return COMMON
    return tuple(arg for arg in COMMON if arg.name != "daemon")


def _statuses(command: Command) -> list[Exit]:
    """The statuses a command ends with, in order: the common ones, and its own.

    A common one is said as the command says it, where the command has more to say of it.
    """
    common = {one.code: one for one in EXITS}
    if command.local:
        # Nobody is asked, so nobody is unreached, and whatever refuses is this machine.
        del common[UNREACHED]
        common[REFUSED] = LOCALLY
    elif YES in command.args:
        common[REFUSED] = _ASKED
    own = {one.code: one for one in command.exits}
    return sorted((common | own).values(), key=lambda one: one.code)


def taken(command: Command) -> tuple[Arg, ...]:
    """Everything a command takes: its own, then what every command does."""
    return (*command.args, *_common(command))


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

    def went(self) -> bool:
        """Whether a session was opened and has ended: the daemon went away under the command."""
        return self._client is not None and self._client.wait(0) is True

    def close(self) -> None:
        """Lets go of the session, where one was opened."""
        if self._client is not None:
            self._client.close()
            self._client = None


def reach(daemon: str) -> Client:
    """A session with a daemon: this machine's for `""` or `local`, else the one of that name.

    A name is one of the registry of other machines' daemons (`hmz daemons list`), and its
    daemon is reached over the routes written there.

    Raises:
      OSError: If it cannot be reached.
      hmz.sdk.Refused: If nothing is kept under that name.
    """
    from hmz.sdk import Client, Refused

    if daemon in ("", "local"):
        return Client.local(kind="cli")
    try:
        return Client.named(daemon, kind="cli")
    except LookupError:
        raise Refused(
            t("No daemon is kept under the name {name}.", name=daemon), code=404
        ) from None


def whole(path: str) -> str:
    """A path of the daemon's machine as a daemon is told it: whole.

    One written from here is taken from the directory the line was typed in, with no link
    followed: which directory that names is the daemon's to say. One beginning `~` is left as
    it is, for the daemon to expand on its own machine.
    """
    return path if path.startswith("~") else os.path.abspath(path)  # noqa: PTH100


def workspace(call: Call) -> str:
    """The workspace a line names with `--workspace`: where it was typed, where it names none."""
    given: str | None = call.given.workspace
    return os.getcwd() if given is None else whole(given)  # noqa: PTH109 -- as the shell names it


def asks(call: Call, question: str) -> bool:
    """Whether somebody said yes: on the line with `--yes`, or to the question at a terminal.

    Never asked of anything but somebody at a terminal, nor under `--json`, whose standard
    error stays empty: a line read off a pipe is not a yes, and a program reading one document
    is not somebody to ask.

    Args:
      call: The command being run, which takes :data:`YES`.
      question: What is asked, as the page asks it.

    Raises:
      hmz.sdk.Refused: If nobody can be asked.
    """
    from hmz.sdk import Refused

    if call.given.yes:
        return True
    if call.json or not sys.stdin.isatty():
        raise Refused(t("Nobody is at a terminal to ask; run it again with `-y`."))
    print(f"{question} [y/N] ", end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def sure(call: Call, question: str) -> None:
    """Asks before something is removed, and returns only where the answer is yes.

    Args:
      call: The command being run, which takes :data:`YES`.
      question: What is asked, as the page asks it.

    Raises:
      hmz.sdk.Refused: If the answer is not yes, or nobody can be asked: nothing was changed.
    """
    from hmz.sdk import Refused

    if not asks(call, question):
        raise Refused(t("Nothing was changed."))


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


#: The width a help is written to where nobody says: no terminal is reading it.
WIDTH: Final = 80

#: The widest a help is written however wide the terminal: a line longer is hard to read.
_WIDEST: Final = 100

#: The narrowest, under which wrapping leaves a word a line.
_NARROWEST: Final = 40

#: The narrowest the right of two columns is left; a name on the left that would leave it
#: less has what it is on the next line.
_RIGHT: Final = 30


class Page:
    """A help being written: paragraphs wrapped, columns aligned, headings marked.

    Every help of `hmz` is set by one of these, so that they read as one: text is wrapped to
    the terminal, or to eighty columns where none is reading; the right of two columns wraps
    under itself; and a heading is bold where escapes may be written (Section 4.2 of cli.md)
    and `--no-color` was not given. A line to type is never wrapped: it is there to be copied.
    """

    def __init__(self, *, width: int | None = None, colour: bool | None = None) -> None:
        """Starts one.

        Args:
          width: How many columns to write to; None for the terminal's, or eighty.
          colour: Whether to write escapes; None for what standard output allows.
        """
        from .output import colours, terminal

        if width is None:
            import shutil

            width = shutil.get_terminal_size().columns if terminal() else WIDTH
            width = min(width, _WIDEST)
        self.width = max(width, _NARROWEST)
        self.colour = colours() if colour is None else colour
        self._lines: list[str] = []

    def line(self, text: str = "") -> None:
        """Adds one line as it is."""
        self._lines.append(text)

    def says(self, text: str, indent: int = 0) -> None:
        """Adds a paragraph, wrapped, each line so far in."""
        self._lines.extend(self.wrapped(text, indent))

    def heading(self, title: str) -> None:
        """Adds an empty line and the heading of what follows."""
        marked = f"\x1b[1m{title}\x1b[0m" if self.colour else title
        self._lines.extend(["", f"{marked}:"])

    def section(self, title: str, lines: Sequence[str]) -> None:
        """Adds lines under a heading, or nothing where there are none."""
        if lines:
            self.heading(title)
            self._lines.extend(lines)

    def wrapped(self, text: str, indent: int = 0) -> list[str]:
        """A paragraph as lines no wider than the page, each so far in."""
        import textwrap

        pad = " " * indent
        return textwrap.wrap(
            text,
            self.width,
            initial_indent=pad,
            subsequent_indent=pad,
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]

    def listed(self, pairs: Sequence[tuple[str, str]], indent: int = 2) -> list[str]:
        """Two columns: names as wide as the widest, and what each is wrapped beside it."""
        pad = " " * indent
        widest = self.width - indent - 2 - _RIGHT
        column = max((len(left) for left, _ in pairs if len(left) <= widest), default=0)
        lines: list[str] = []
        for left, right in pairs:
            said = self.wrapped(right, indent + column + 2) if right else []
            if len(left) > column:
                lines.append(f"{pad}{left}".rstrip())
            elif said:
                said[0] = f"{pad}{left.ljust(column)}  {said[0].lstrip()}"
            else:
                lines.append(f"{pad}{left}".rstrip())
            lines.extend(said)
        return lines

    def text(self) -> str:
        """Everything added, as it is printed."""
        return "\n".join(self._lines) + "\n"


def helps(
    path: Sequence[str],
    command: Command,
    *,
    width: int | None = None,
    colour: bool | None = None,
) -> str:
    """Everything `--help` says of a command: enough to use it without reading anything else.

    The same sections in the same order for every command, the empty ones left out: the line
    it takes, what it does, the commands under it, what it takes by place and by name, lines
    to type, what it prints and the fields of its `--json`, the statuses it ends with, and
    what to read beside it.

    Args:
      path: The command, as the words after `hmz`.
      command: Its declaration.
      width: How many columns to write to; None for the terminal's, or eighty.
      colour: Whether to mark headings with escapes; None for what standard output allows.
    """
    page = Page(width=width, colour=colour)
    page.line(f"{t('Usage')}: {_usage(path, command)}")
    page.line()
    page.says(t(command.says or command.summary))
    page.section(
        t("Commands"),
        page.listed([(one.name, t(one.summary)) for one in command.commands]),
    )
    if command.commands:
        run = " ".join(["hmz", *path, "COMMAND", "--help"])
        page.line()
        page.says(t("Run `{line}` to read everything about one command.", line=run))
        return page.text()
    if command.passes is not None:
        return page.text()
    every = taken(command)
    placed = [arg for arg in every if arg.positional]
    by_name = [arg for arg in every if not arg.positional]
    page.section(
        t("Arguments"), page.listed([(_flags(arg), _said(arg)) for arg in placed])
    )
    page.section(
        t("Options"),
        page.listed(
            [
                *((_flags(arg), _said(arg)) for arg in by_name),
                ("-h, --help", t("show this help and exit")),
            ]
        ),
    )
    examples: list[str] = []
    for example in command.examples:
        examples.extend([f"  {example.line}", *page.wrapped(t(example.says), 6)])
    page.section(t("Examples"), examples)
    output = page.wrapped(t(command.prints), 2) if command.prints else []
    if command.output:
        output.extend(
            page.wrapped(t("With `--json`, prints one object with these fields:"), 2)
        )
        names = max(len(one.name) for one in command.output)
        kinds = max(len(one.kind) for one in command.output)
        output.extend(
            page.listed(
                [
                    (f"{one.name.ljust(names)}  {one.kind.ljust(kinds)}", t(one.says))
                    for one in command.output
                ],
                4,
            )
        )
    page.section(t("Output"), output)
    page.section(
        t("Exit codes"),
        page.listed([(str(one.code), t(one.says)) for one in _statuses(command)]),
    )
    if command.methods:
        page.section(t("Daemon calls"), page.wrapped(", ".join(command.methods), 2))
    page.section(t("See also"), [f"  hmz {one} --help" for one in command.see])
    return page.text()


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
        for arg in taken(command)
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


def parser(
    path: Sequence[str], command: Command, *, plain: bool = False
) -> argparse.ArgumentParser:
    """What reads the line of one command, and answers `--help` with :func:`helps`.

    Args:
      path: The command, as the words after `hmz`.
      command: Its declaration.
      plain: Whether its help is written without escapes whatever is reading it.
    """
    return _parser(tuple(path), command, plain=plain)


def _parser(path: tuple[str, ...], command: Command, *, plain: bool = False) -> _Parser:
    reads = _Parser(prog=" ".join(["hmz", *path]), add_help=False, allow_abbrev=False)
    reads.said = lambda: helps(path, command, colour=False if plain else None)
    reads.add_argument("-h", "--help", action="help")
    if command.commands:
        # Nothing but `--help`: `runs` walks the groups itself.
        reads.add_argument("_rest", nargs="*")
        return reads
    for arg in taken(command):
        _adds(reads, arg)
    return reads


def _unreached(why: OSError) -> str:
    """What is said of a daemon that could not be reached, as every command says it."""
    from .output import unreached

    return unreached(why).removeprefix("hmz: ")


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


def named(words: Sequence[str]) -> tuple[tuple[str, ...], Command, list[str]]:
    """The command a line names, and the words left for it.

    Down the groups by name, so that a group's help is its own and a command's is its own. It
    stops at a group where the next word names nothing under it, which is then the first of
    the words left.

    Args:
      words: The words after `hmz`, the first naming one of :func:`commands`.

    Returns:
      The words that named it, its declaration, and the rest of the line.

    Raises:
      KeyError: If the first word names none of :func:`commands`.
    """
    command = commands()[words[0]]
    path: tuple[str, ...] = (words[0],)
    rest = list(words[1:])
    while command.commands and rest and not rest[0].startswith("-"):
        under = {one.name: one for one in command.commands}
        if rest[0] not in under:
            break
        command, path, rest = under[rest[0]], (*path, rest[0]), rest[1:]
    return path, command, rest


def runs(argv: Sequence[str]) -> int:
    """Runs the command a line names, which begins with the name of one of :func:`commands`.

    Args:
      argv: The words after `hmz`.

    Returns:
      Its exit status.
    """
    from hmz.sdk import Refused

    passes = commands()[argv[0]].passes
    if passes is not None:
        return passes(list(argv[1:]))
    path, command, rest = named(argv)
    plain = "--no-color" in rest
    reads = _parser(path, command, plain=plain)
    if command.commands:
        # A group named with nothing under it is asking what there is.
        if not rest:
            print(helps(path, command, colour=False if plain else None), end="")
            return DONE
        if not rest[0].startswith("-"):
            reads.error(t("no command named {name}", name=rest[0]))
        reads.parse_args(rest)
        reads.error(t("needs a command name"))
    given = reads.parse_args(rest)
    daemon = getattr(given, "daemon", None) or ""
    call = Call(path, given, json=given.json, daemon=daemon)
    if command.run is None:
        raise RuntimeError(f"{' '.join(path)} does nothing")
    try:
        return command.run(call) or DONE
    except Unread as why:
        helped = t("Run `{line}` for help.", line=f"{reads.prog} --help")
        _failed(call, path, _BAD, str(why) if call.json else f"{why}\n{helped}")
        return UNREAD
    except KeyboardInterrupt:
        # Whatever it was waiting on: nothing more is said, and what a daemon holds goes on.
        return INTERRUPTED
    except Refused as why:
        code: int = getattr(why, "code", 0) or 0
        if code != _WENT or not call.went():
            _failed(call, path, code, str(why))
            return REFUSED
        # A session that ended under a call is a daemon not reached, whatever was asked.
        _failed(call, path, _WENT, _unreached(ConnectionError(str(why))))
    except TimeoutError as why:
        _failed(call, path, 504, str(why))
    except OSError as why:
        if command.local:
            # A file of this machine's that would not be read or written: nobody was asked.
            _failed(call, path, 0, str(why))
            return REFUSED
        _failed(call, path, _WENT, _unreached(why))
    finally:
        call.close()
    return UNREACHED
