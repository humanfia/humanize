"""`hmz help`: what `hmz` is and every command it has, for a person or for an agent.

The top of the command line is written here: `hmz --help` and `hmz help` are the same page,
which says what `hmz` is, lists every command there is under what it is about, states what
commands share, and names what to run next. It is read off the commands that exist when it is
asked for, so a command added tomorrow is on it without anybody editing it.

The same declarations are given whole to whoever would rather not read a page a command at a
time: `hmz help --all` is every help in one stream, `hmz help --json` is every command as one
JSON document, and `hmz help completions SHELL` is a completion script for a shell. None of it
asks a daemon anything.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any, Final

from hmz.cli import tree
from hmz.cli.tree import Arg, Command, Example, Field
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from hmz.cli.tree import Call

__all__ = ["COMMANDS", "GROUPS", "REST", "USAGE", "grouped", "top"]

#: The line `hmz` itself takes.
USAGE: Final = ("hmz [COMMAND] [ARGS...]", "hmz --version")

#: What the commands are about, and which are about it, in the order they are listed. This is
#: the one place a command is put in a group; one named in none is listed under `REST`, so
#: that a command nobody has placed is still a command anybody can find.
GROUPS: Final = (
    ("Chats and epics", ("chat", "exec", "epic", "hosts")),
    ("Past work and backups", ("runs", "backup")),
    ("Environments", ("env",)),
    (
        "Setting things up",
        (
            "flows",
            "flowverses",
            "workspaces",
            "settings",
            "accounts",
            "nous",
            "runtimes",
            "easytier",
        ),
    ),
    ("Daemons and devices", ("daemon", "daemons", "devices", "relay", "web")),
    ("Notices and questions", ("notices", "ai", "btw")),
    ("This program", ("skills", "help", "update", "internal")),
)

#: The heading over every command no group of `GROUPS` names.
REST: Final = "Other commands"

#: The word after `hmz help` that asks for a completion script rather than a command's help.
_COMPLETIONS: Final = "completions"


def grouped() -> list[tuple[str, list[tuple[str, str]]]]:
    """Every command there is with its summary, under the heading of what it is about.

    Returns:
      Each heading that has a command, in the order of `GROUPS` with `REST` last, and the
      commands under it.
    """
    from hmz.cli import summaries

    left = summaries()
    found: list[tuple[str, list[tuple[str, str]]]] = []
    for title, names in GROUPS:
        held = [(name, left.pop(name)) for name in names if name in left]
        if held:
            found.append((t(title), held))
    if left:
        found.append((t(REST), list(left.items())))
    return found


def _about() -> list[str]:
    return [
        t(
            "Runs AI coding agents on your own machines, as chats, and as epics that "
            "run flows."
        ),
        t("With no command, `hmz` opens the terminal interface in this folder."),
    ]


def _shared() -> list[str]:
    """What is said of `--json` wherever what commands share is said."""
    return [
        t("With `--json`, a command prints one JSON document on standard output."),
        t(
            "With `--json`, a command that fails prints one object whose `error` field "
            "holds a `code` and a `message`."
        ),
    ]


def _shares() -> dict[str, Any]:
    """What every command takes and ends with, as any command's own are described.

    They are those of a command that takes nothing of its own and ends no other way.
    """
    return tree.described(["help"], Command("help", "Options", run=lambda _: None))


def top(*, width: int | None = None, colour: bool | None = None) -> str:
    """The help of `hmz` itself: one page to find any command from.

    Args:
      width: How many columns to write to; None for the terminal's, or eighty.
      colour: Whether to mark headings with escapes; None for what standard output allows.
    """
    page = tree.Page(width=width, colour=colour)
    first, *others = USAGE
    page.line(f"{t('Usage')}: {first}")
    for other in others:
        page.line(" " * (len(t("Usage")) + 2) + other)
    page.line()
    for said in _about():
        page.says(said)
    groups = grouped()
    column = max((len(name) for _, held in groups for name, _ in held), default=0)
    for title, held in groups:
        page.section(
            title, page.listed([(name.ljust(column), said) for name, said in held])
        )
    page.heading(t("Shared conventions"))
    for said in (
        t(
            "Commands share these options and exit codes unless their own help says "
            "otherwise."
        ),
        *_shared(),
    ):
        page.says(said, 2)
    shares = _shares()
    page.section(
        t("Options"),
        page.listed(
            [
                *((one["name"], one["description"]) for one in shares["arguments"]),
                ("-h, --help", t("show this help and exit")),
            ]
        ),
    )
    page.section(t("Exit codes"), page.listed(list(shares["exit_status"].items())))
    page.heading(t("Next steps"))
    for said in (
        t(
            "Run `{line}` to read everything about one command.",
            line="hmz COMMAND --help",
        ),
        t(
            "Run `{line}` to read every command as one JSON document.",
            line="hmz help --json",
        ),
        t(
            "Run `{line}` to read the full help of every command at once.",
            line="hmz help --all",
        ),
        t(
            "Run `{line}` to print a shell completion script.",
            line="hmz help completions SHELL",
        ),
    ):
        page.says(said, 2)
    return page.text()


def _legacy(name: str) -> dict[str, Any]:
    """A command that reads its own line, as much as can be said of it from here."""
    from hmz.cli import summaries

    return {
        "command": f"hmz {name}",
        "summary": summaries()[name],
        "help": f"hmz {name} --help",
    }


def _document(commands: list[dict[str, Any]]) -> dict[str, Any]:
    """What `--json` answers: `hmz` itself, what commands share, and the commands given."""
    from importlib.metadata import version

    shares = _shares()
    return {
        "version": version("hmz"),
        "usage": USAGE[0],
        "description": " ".join(_about()),
        "conventions": {
            "options": shares["arguments"],
            "exit_status": shares["exit_status"],
            "json": " ".join(_shared()),
        },
        "groups": [
            {"title": title, "commands": [name for name, _ in held]}
            for title, held in grouped()
        ],
        "commands": commands,
    }


def _under(
    path: tuple[str, ...], command: Command
) -> Iterator[tuple[tuple[str, ...], Command]]:
    """A command and every command under it, each after the group it is in."""
    yield path, command
    for one in command.commands:
        yield from _under((*path, one.name), one)


def _refuses(call: Call, message: str) -> None:
    """Ends on a line that named nothing there is, as a line that cannot be read does."""
    tree.parser(call.path, COMMANDS[0]).error(message)


def _reads(name: str) -> Callable[[list[str]], int] | None:
    """What reads the line of a command that reads its own; None for a declared one."""
    from hmz import cli

    if name in cli.COMMANDS:
        return cli.COMMANDS[name][0]
    return tree.commands()[name].passes


def _own(name: str) -> int:
    """Has a command that reads its own line print its help; zero once it has.

    Its name alone is given it, and `--help`: what its words are under that is known only to
    its own parser, and a word it took for something to run would be run.
    """
    reads = _reads(name)
    if reads is None:
        raise RuntimeError(f"{name} does not read its own line")
    try:
        return reads(["--help"])
    except SystemExit as done:
        # How a parser leaves once it has printed its help, which here is not the end.
        code = done.code
        return code if isinstance(code, int) else int(code is not None)


def _completes(call: Call, rest: list[str]) -> None:
    from hmz.cli import completions

    if len(rest) != 1 or rest[0] not in completions.SHELLS:
        _refuses(
            call,
            t(
                "`completions` needs the name of a shell, one of {shells}",
                shells=", ".join(completions.SHELLS),
            ),
        )
    script = completions.script(rest[0])
    call.answers({"shell": rest[0], "script": script}, [script.rstrip("\n")])


def _help(call: Call) -> int | None:
    words: list[str] = list(call.command)
    if words[:1] == [_COMPLETIONS]:
        _completes(call, words[1:])
        return None
    colour = False if call.no_color else None
    names = [name for _, held in grouped() for name, _ in held]
    declared = tree.commands()
    found: tuple[tuple[str, ...], Command] | None = None
    if words:
        if words[0] not in names:
            _refuses(call, t("no command named {name}", name=words[0]))
        rest = words[1:]
        if _reads(words[0]) is None:
            path, command, rest = tree.named(words)
            found = path, command
        if rest:
            _refuses(call, t("no command named {name}", name=rest[0]))
    if call.json:
        if found is not None:
            described = [tree.described(*found)]
        else:
            described = [
                _legacy(name)
                if _reads(name) is not None
                else tree.described([name], declared[name])
                for name in (words[:1] or names)
            ]
        print(json.dumps(_document(described), ensure_ascii=False))
        return None
    if words and found is None:
        # One that reads its own line says its own help.
        return _own(words[0])
    first = top(colour=colour) if found is None else tree.helps(*found, colour=colour)
    print(first, end="")
    if not call.all:
        return None
    # Every help there is, or every one under the command named, each after a rule.
    every: list[tuple[tuple[str, ...], Command | None]] = []
    if found is not None:
        every.extend(list(_under(*found))[1:])
    for name in names if found is None else ():
        if _reads(name) is not None:
            every.append(((name,), None))
        else:
            every.extend(_under((name,), declared[name]))
    rule = "-" * tree.Page(colour=False).width
    for path, command in every:
        print(f"\n{rule}\n")
        if command is None:
            # Its own parser writes to the stream itself, after what is already written.
            sys.stdout.flush()
            _own(path[0])
        else:
            print(tree.helps(path, command, colour=colour), end="")
    return None


COMMANDS = (
    Command(
        "help",
        "show the help of hmz or of one command",
        says="Prints the help of hmz, or of the command named. Prints every command at once "
        "as text or JSON, and shell completion scripts.",
        args=(
            Arg(
                ("command",),
                "the command to read about, as its words after `hmz`; or `completions` "
                "and a shell",
                many=True,
            ),
            Arg(("--all",), "print the full help of every command, one after another"),
        ),
        examples=(
            Example(
                "hmz help", "show the commands of hmz, grouped by what they are about"
            ),
            Example(
                "hmz help devices revoke", "show everything about `hmz devices revoke`"
            ),
            Example("hmz help --all", "print the full help of every command"),
            Example(
                "hmz help --json",
                "print every command as one JSON document, for an agent to load",
            ),
            Example(
                "hmz help --json devices",
                "print `hmz devices` and the commands under it as one JSON document",
            ),
            Example(
                "hmz help completions bash > ~/.local/share/bash-completion/completions/hmz",
                "write the bash completion script to where bash loads completions from",
            ),
            Example(
                "hmz help completions zsh > ~/.zfunc/_hmz",
                "write the zsh completion script to a directory of zsh's `fpath`",
            ),
            Example(
                "hmz help completions fish > ~/.config/fish/completions/hmz.fish",
                "write the fish completion script to where fish loads completions from",
            ),
        ),
        prints="Prints the help text, or the completion script.",
        output=(
            Field("version", "string", "the version of hmz"),
            Field("usage", "string", "the line hmz itself takes"),
            Field("description", "string", "what hmz is, in a sentence or two"),
            Field(
                "conventions",
                "object",
                "what commands share unless their own help says otherwise",
            ),
            Field(
                "conventions.options",
                "list",
                "the options commands share, each as an entry of `commands[].arguments`",
            ),
            Field(
                "conventions.exit_status",
                "object",
                "what each shared exit code means, by code",
            ),
            Field(
                "conventions.json",
                "string",
                "what a command prints with `--json`, when it does what was asked and "
                "when it fails",
            ),
            Field(
                "groups",
                "list",
                "the commands grouped by what they are about, in the order `hmz --help` "
                "lists them",
            ),
            Field("groups[].title", "string", "the heading of the group"),
            Field(
                "groups[].commands", "list", "the names of the commands in the group"
            ),
            Field(
                "commands",
                "list",
                "every command, or only the one named, each holding the commands under it",
            ),
            Field(
                "commands[].command",
                "string",
                "the command as it is typed, starting with `hmz`",
            ),
            Field("commands[].summary", "string", "what the command does, in a line"),
            Field(
                "commands[].description",
                "string",
                "what the command does, in a paragraph",
            ),
            Field("commands[].usage", "string", "the line the command takes"),
            Field(
                "commands[].help",
                "string",
                "the line that prints the command's own help, for a command not "
                "described further here",
            ),
            Field(
                "commands[].commands",
                "list",
                "the commands under a group, each shaped like this one",
            ),
            Field(
                "commands[].arguments",
                "list",
                "what the command takes, positional arguments and options",
            ),
            Field(
                "commands[].arguments[].name",
                "string",
                "the argument or option as its help shows it",
            ),
            Field(
                "commands[].arguments[].flags",
                "list",
                "the spellings of an option, or the name of a positional argument",
            ),
            Field(
                "commands[].arguments[].description",
                "string",
                "what the argument or option is",
            ),
            Field(
                "commands[].arguments[].positional",
                "boolean",
                "whether it is given by position rather than by name",
            ),
            Field(
                "commands[].arguments[].required", "boolean", "whether it must be given"
            ),
            Field(
                "commands[].arguments[].repeatable",
                "boolean",
                "whether it may be given more than once",
            ),
            Field(
                "commands[].arguments[].takes_value",
                "boolean",
                "whether an option is followed by a value",
            ),
            Field(
                "commands[].arguments[].choices",
                "list",
                "the only values it takes, or an empty list for any",
            ),
            Field(
                "commands[].arguments[].default",
                "any",
                "its value when it is not given, or null",
            ),
            Field(
                "commands[].examples",
                "list",
                "command lines to type, each with its `line` and what it `does`",
            ),
            Field(
                "commands[].prints",
                "string",
                "what the command prints without `--json`",
            ),
            Field(
                "commands[].json",
                "list",
                "the fields of the command's `--json` document, each with `field`, "
                "`type` and `description`",
            ),
            Field(
                "commands[].exit_status",
                "object",
                "what each exit code of the command means, by code",
            ),
            Field(
                "commands[].daemon_methods",
                "list",
                "the daemon methods the command calls",
            ),
            Field(
                "commands[].see_also", "list", "other commands worth reading beside it"
            ),
            Field("shell", "string", "with `completions`, the shell the script is for"),
            Field("script", "string", "with `completions`, the completion script"),
        ),
        run=_help,
        local=True,
    ),
)
