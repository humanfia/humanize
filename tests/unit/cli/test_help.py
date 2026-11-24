"""`hmz help`: the top of the command line, a command's help, all of them, and as JSON."""

from __future__ import annotations

import json
import sys
from importlib.metadata import version
from typing import Any, cast

import pytest

import hmz.cli
from hmz.cli import main, tree
from hmz.cli.commands import help as helping
from hmz.cli.tree import Arg, Call, Command, Example, Field


def _greets(call: Call) -> None:
    call.answers({"greeted": call.name}, [f"hello {call.name}"])


GREET = Command(
    "greet",
    "Open",
    says="Search",
    commands=(
        Command(
            "say",
            "Back",
            args=(Arg(("name",), "Close"),),
            examples=(Example("hmz greet say you", "Open"),),
            prints="Close",
            output=(Field("greeted", "string", "Back"),),
            run=_greets,
        ),
    ),
)

#: A command placed in a group, to be listed under its heading.
ENV = Command("env", "Environment", run=_greets)


def _old(argv: list[str]) -> int:
    """A command that reads its own line, as argparse leaves once it has printed a help."""
    sys.stdout.write("usage: hmz old " + " ".join(argv) + "\n")
    raise SystemExit(0)


@pytest.fixture(autouse=True)
def commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three declared commands and one that reads its own line."""
    (asked,) = helping.COMMANDS
    declared = {"env": ENV, "greet": GREET, "help": asked}
    monkeypatch.setattr(tree, "commands", lambda: declared)
    monkeypatch.setattr(hmz.cli, "COMMANDS", {"old": (_old, "an old command")})


TOP = """\
Usage: hmz [COMMAND] [ARGS...]
       hmz --version

Runs AI coding agents on your own machines, as chats, and as epics that run
flows.
With no command, `hmz` opens the terminal interface in this folder.

Environments:
  env    Environment

This program:
  help   show the help of hmz or of one command

Other commands:
  old    an old command
  greet  Open

Shared conventions:
  Commands share these options and exit codes unless their own help says
  otherwise.
  With `--json`, a command prints one JSON document on standard output.
  With `--json`, a command that fails prints one object whose `error` field
  holds a `code` and a `message`.

Options:
  --json         print one JSON document instead of text
  --daemon NAME  ask the daemon named in the daemon list, or this machine's
                 daemon
  --no-color     print without terminal colours
  -h, --help     show this help and exit

Exit codes:
  0    did what was asked
  1    the daemon refused the request and its reason was printed
  2    the command line could not be read
  3    the daemon could not be reached
  130  interrupted with ctrl+c

Next steps:
  Run `hmz COMMAND --help` to read everything about one command.
  Run `hmz help --json` to read every command as one JSON document.
  Run `hmz help --all` to read the full help of every command at once.
  Run `hmz help completions SHELL` to print a shell completion script.
"""


def test_the_top_says_what_hmz_is_and_every_command_under_what_it_is_about() -> None:
    assert helping.top(width=80, colour=False) == TOP


@pytest.mark.parametrize("argv", [["--help"], ["-h"]])
def test_the_help_of_hmz_is_that_page(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)

    assert raised.value.code == 0
    assert capsys.readouterr().out == TOP


def test_hmz_help_is_the_same_page(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["help"]) == 0

    assert capsys.readouterr().out == TOP


def test_a_command_in_no_group_is_listed_under_the_last() -> None:
    assert helping.grouped() == [
        ("Environments", [("env", "Environment")]),
        ("This program", [("help", "show the help of hmz or of one command")]),
        ("Other commands", [("old", "an old command"), ("greet", "Open")]),
    ]


def test_every_group_names_its_commands_once() -> None:
    placed = [name for _, names in helping.GROUPS for name in names]

    assert len(placed) == len(set(placed))


def test_a_page_narrower_wraps_and_one_coloured_marks_its_headings() -> None:
    narrow = helping.top(width=50, colour=False)
    assert max(len(line) for line in narrow.splitlines()) <= 50

    assert "\x1b[1mEnvironments\x1b[0m:" in helping.top(width=80, colour=True)
    assert "\x1b[" not in helping.top(width=80, colour=False)


def test_hmz_help_and_a_commands_words_is_that_commands_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["help", "greet", "say"]) == 0

    assert capsys.readouterr().out == tree.helps(["greet", "say"], GREET.commands[0])


def test_a_command_that_reads_its_own_line_says_its_own_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["help", "old"]) == 0

    assert capsys.readouterr().out == "usage: hmz old --help\n"


def test_a_declared_command_that_reads_its_own_line_is_asked_as_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    passing = Command("env", "Environment", passes=_old)
    declared = {"env": passing, "help": helping.COMMANDS[0]}
    monkeypatch.setattr(tree, "commands", lambda: declared)

    assert main(["help", "env"]) == 0
    assert capsys.readouterr().out == "usage: hmz old --help\n"

    assert main(["help", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["commands"][0] == {
        "command": "hmz env",
        "summary": "Environment",
        "help": "hmz env --help",
    }


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (["help", "nope"], "hmz help: no command named nope\n"),
        (["help", "greet", "shout"], "hmz help: no command named shout\n"),
        (["help", "--json", "nope"], "hmz help: no command named nope\n"),
        # A word after one that reads its own line is never handed to it: it might run it.
        (["help", "old", "deeper"], "hmz help: no command named deeper\n"),
        (["help", "--json", "old", "deeper"], "hmz help: no command named deeper\n"),
        (
            ["help", "completions"],
            "hmz help: `completions` needs the name of a shell, one of bash, zsh, fish\n",
        ),
        (
            ["help", "completions", "tcsh"],
            "hmz help: `completions` needs the name of a shell, one of bash, zsh, fish\n",
        ),
    ],
)
def test_a_command_there_is_not_is_a_line_that_cannot_be_read(
    argv: list[str], said: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)

    assert raised.value.code == tree.UNREAD
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == said + "Run `hmz help --help` for help.\n"


def test_all_is_the_top_and_every_help_in_one_stream(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["help", "--all"]) == 0

    (asked,) = helping.COMMANDS
    rule = "\n" + "-" * 80 + "\n\n"
    assert capsys.readouterr().out == rule.join(
        [
            TOP,
            tree.helps(["env"], ENV),
            tree.helps(["help"], asked),
            "usage: hmz old --help\n",
            tree.helps(["greet"], GREET),
            tree.helps(["greet", "say"], GREET.commands[0]),
        ]
    )


def test_all_of_one_command_is_it_and_every_command_under_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["help", "--all", "greet"]) == 0

    assert capsys.readouterr().out == (
        tree.helps(["greet"], GREET)
        + "\n"
        + "-" * 80
        + "\n\n"
        + tree.helps(["greet", "say"], GREET.commands[0])
    )


def test_json_is_the_whole_command_line_as_one_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["help", "--json"]) == 0

    said = json.loads(capsys.readouterr().out)
    (asked,) = helping.COMMANDS
    assert set(said) == {
        "version",
        "usage",
        "description",
        "conventions",
        "groups",
        "commands",
    }
    assert said["version"] == version("hmz")
    assert said["usage"] == "hmz [COMMAND] [ARGS...]"
    assert said["description"].startswith("Runs AI coding agents")
    assert [one["name"] for one in said["conventions"]["options"]] == [
        "--json",
        "--daemon NAME",
        "--no-color",
    ]
    assert list(said["conventions"]["exit_status"]) == ["0", "1", "2", "3", "130"]
    assert "`error`" in said["conventions"]["json"]
    assert said["groups"] == [
        {"title": "Environments", "commands": ["env"]},
        {"title": "This program", "commands": ["help"]},
        {"title": "Other commands", "commands": ["old", "greet"]},
    ]
    assert said["commands"] == [
        tree.described(["env"], ENV),
        tree.described(["help"], asked),
        {"command": "hmz old", "summary": "an old command", "help": "hmz old --help"},
        tree.described(["greet"], GREET),
    ]


def test_json_of_one_command_is_the_same_document_holding_only_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["help", "--json", "greet", "say"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["commands"] == [tree.described(["greet", "say"], GREET.commands[0])]
    assert said["conventions"]["exit_status"]["3"] == "the daemon could not be reached"

    assert main(["help", "old", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert [one["command"] for one in said["commands"]] == ["hmz old"]


def _fields(value: Any, at: str, stated: set[str]) -> set[str]:
    """Where each field of a document is, as a help states one: dotted, `[]` after a list.

    No further down than the help goes: an object stated whole, such as one keyed by exit
    code, is one field, and a command under a group is shaped as the one over it.
    """
    if isinstance(value, list):
        items = cast("list[Any]", value)
        return {name for one in items for name in _fields(one, f"{at}[]", stated)}
    if not isinstance(value, dict):
        return set()
    found: set[str] = set()
    for key, under in cast("dict[str, Any]", value).items():
        name = f"{at}.{key}" if at else key
        found.add(name)
        further = any(one.startswith((f"{name}.", f"{name}[")) for one in stated)
        if further and name != "commands[].commands":
            found |= _fields(under, name, stated)
    return found


def test_every_field_the_document_holds_is_one_its_help_states(
    capsys: pytest.CaptureFixture[str],
) -> None:
    (asked,) = helping.COMMANDS
    stated = {one.name for one in asked.output}

    assert main(["help", "--json"]) == 0
    found = _fields(json.loads(capsys.readouterr().out), "", stated)
    assert found <= stated
    # And each is there to be read: all but the two a completion script is answered with.
    assert stated - found == {"shell", "script"}

    assert main(["help", "completions", "bash", "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"shell", "script"}


def test_help_asks_no_daemon_and_takes_no_daemon(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def reach(_: str) -> None:
        raise AssertionError("asked a daemon")

    monkeypatch.setattr(tree, "reach", reach)
    assert main(["help", "greet"]) == 0
    assert "--daemon" not in tree.helps(["help"], helping.COMMANDS[0])
    capsys.readouterr()

    with pytest.raises(SystemExit) as raised:
        main(["help", "--daemon", "far"])
    assert raised.value.code == tree.UNREAD


def test_no_color_is_help_without_escapes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")

    assert main(["help"]) == 0
    assert "\x1b[1m" in capsys.readouterr().out
    assert main(["help", "greet", "say"]) == 0
    assert "\x1b[1m" in capsys.readouterr().out

    for argv in (["help", "--no-color"], ["help", "greet", "--no-color"]):
        assert main(argv) == 0
        assert "\x1b[" not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["greet", "say", "--no-color", "--help"])
    assert "\x1b[" not in capsys.readouterr().out


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_a_completion_script_is_printed_for_a_shell(
    shell: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["help", "completions", shell]) == 0
    script = capsys.readouterr().out
    assert f"{shell} completion for hmz" in script

    assert main(["help", "completions", shell, "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said == {"shell": shell, "script": script}
