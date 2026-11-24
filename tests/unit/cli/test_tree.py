"""`hmz.cli.tree`: a command said once, and its line, its help and its answers read off that."""

from __future__ import annotations

import dataclasses
import json
import os
from typing import TYPE_CHECKING
from unittest import mock

import pytest

import hmz.sdk
from hmz.cli import main, tree
from hmz.cli.tree import Arg, Call, Command, Example, Exit, Field

if TYPE_CHECKING:
    from pathlib import Path


def _greets(call: Call) -> int | None:
    if call.name == "refused":
        raise hmz.sdk.Refused("There is no such thing.", code=404)
    if call.name == "unreached":
        raise OSError("no socket")
    call.answers(
        {"greeted": call.name, "loud": call.loud, "to": call.to}, [f"hello {call.name}"]
    )
    return 7 if call.name == "seven" else None


GREET = Command(
    "greet",
    "Open",
    says="Search",
    commands=(
        Command(
            "say",
            "Back",
            args=(
                Arg(("name",), "Close"),
                Arg(("--loud",), "Cancel"),
                Arg(("-t", "--to"), "Search", metavar="WHO", many=True),
                Arg(("--kind",), "Open", choices=("a", "b"), default="a"),
            ),
            examples=(Example("hmz greet say you", "Open"),),
            prints="Close",
            output=(Field("greeted", "string", "Back"),),
            exits=(Exit(7, "Cancel"),),
            methods=("devices.list",),
            see=("greet say",),
            run=_greets,
        ),
    ),
)


@pytest.fixture
def greeting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tree, "commands", lambda: {"greet": GREET})


def test_the_commands_are_found_by_walking_the_package() -> None:
    found = tree.commands()

    assert "devices" in found
    assert [one.name for one in found["devices"].commands] == ["list", "revoke", "pair"]
    assert found["help"].local


@pytest.mark.usefixtures("greeting")
def test_a_command_is_given_its_line_and_answers_in_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert tree.runs(["greet", "say", "you", "-t", "a", "--to", "b"]) == 0

    assert capsys.readouterr().out == "hello you\n"


@pytest.mark.usefixtures("greeting")
def test_a_command_answers_one_document_under_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert tree.runs(["greet", "say", "you", "--loud", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "greeted": "you",
        "loud": True,
        "to": None,
    }


@pytest.mark.usefixtures("greeting")
def test_a_command_ends_with_the_status_it_returns() -> None:
    assert tree.runs(["greet", "say", "seven"]) == 7


@pytest.mark.usefixtures("greeting")
@pytest.mark.parametrize(
    ("name", "status", "code", "message"),
    [
        ("refused", tree.REFUSED, 404, "There is no such thing."),
        ("unreached", tree.UNREACHED, 503, "the daemon cannot be reached: no socket"),
    ],
)
def test_a_refusal_is_a_line_on_stderr_or_a_document_under_json(
    name: str, status: int, code: int, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert tree.runs(["greet", "say", name]) == status
    said = capsys.readouterr()
    assert (said.out, said.err) == ("", f"hmz greet say: {message}\n")

    assert tree.runs(["greet", "say", name, "--json"]) == status
    said = capsys.readouterr()
    assert json.loads(said.out) == {"error": {"code": code, "message": message}}
    assert said.err == ""


@pytest.mark.usefixtures("greeting")
@pytest.mark.parametrize(
    "argv",
    [
        ["greet", "say"],
        ["greet", "say", "you", "--kind", "c"],
        ["greet", "say", "you", "--lou"],
        ["greet", "shout"],
        ["greet", "--loud"],
    ],
)
def test_a_line_that_cannot_be_read_is_refused_with_where_to_read(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        tree.runs(argv)

    assert raised.value.code == tree.UNREAD
    err = capsys.readouterr().err
    assert err.startswith("hmz greet")
    assert "--help` for help." in err


@pytest.mark.usefixtures("greeting")
def test_a_group_named_alone_says_what_is_under_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert tree.runs(["greet"]) == 0

    assert capsys.readouterr().out == (
        "Usage: hmz greet COMMAND ...\n"
        "\n"
        "Search\n"
        "\n"
        "Commands:\n"
        "  say  Back\n"
        "\n"
        "Run `hmz greet COMMAND --help` to read everything about one command.\n"
    )


@pytest.mark.usefixtures("greeting")
def test_help_says_everything_a_command_declares(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        tree.runs(["greet", "say", "--help"])

    assert raised.value.code == 0
    assert capsys.readouterr().out == (
        "Usage: hmz greet say NAME [options]\n"
        "\n"
        "Back\n"
        "\n"
        "Arguments:\n"
        "  NAME  Close\n"
        "\n"
        "Options:\n"
        "  --loud         Cancel\n"
        "  -t, --to WHO   Search [may be given more than once]\n"
        "  --kind {a,b}   Open [default: a]\n"
        "  --json         print one JSON document instead of text\n"
        "  --daemon NAME  ask the daemon named in the daemon list, or this machine's\n"
        "                 daemon\n"
        "  --no-color     print without terminal colours\n"
        "  -h, --help     show this help and exit\n"
        "\n"
        "Examples:\n"
        "  hmz greet say you\n"
        "      Open\n"
        "\n"
        "Output:\n"
        "  Close\n"
        "  With `--json`, prints one object with these fields:\n"
        "    greeted  string  Back\n"
        "\n"
        "Exit codes:\n"
        "  0    did what was asked\n"
        "  1    the daemon refused the request and its reason was printed\n"
        "  2    the command line could not be read\n"
        "  3    the daemon could not be reached\n"
        "  7    Cancel\n"
        "  130  interrupted with ctrl+c\n"
        "\n"
        "Daemon calls:\n"
        "  devices.list\n"
        "\n"
        "See also:\n"
        "  hmz greet say --help\n"
    )


def test_help_is_wrapped_to_the_width_it_is_written_to() -> None:
    say = GREET.commands[0]

    wide = tree.helps(["greet", "say"], say, width=100, colour=False)
    assert (
        "  --daemon NAME  ask the daemon named in the daemon list, or this machine's "
        "daemon\n"
    ) in wide

    narrow = tree.helps(["greet", "say"], say, width=44, colour=False)
    assert max(len(line) for line in narrow.splitlines()) <= 44
    assert (
        "  --daemon NAME\n"
        "              ask the daemon named in the\n"
        "              daemon list, or this machine's\n"
        "              daemon\n"
    ) in narrow
    # A line to type is one line however narrow the page.
    assert "  hmz greet say you\n" in narrow


def test_headings_are_marked_only_where_colour_is_asked_for() -> None:
    say = GREET.commands[0]

    coloured = tree.helps(["greet", "say"], say, width=80, colour=True)
    assert "\x1b[1mOptions\x1b[0m:\n" in coloured
    plain = tree.helps(["greet", "say"], say, width=80, colour=False)
    assert "\x1b[" not in plain
    assert coloured.replace("\x1b[1m", "").replace("\x1b[0m", "") == plain


def test_a_page_is_eighty_columns_where_no_terminal_reads_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COLUMNS", "132")
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    page = tree.Page()

    assert (page.width, page.colour) == (80, False)
    assert tree.Page(width=10).width == 40


def test_two_columns_wrap_the_right_under_itself_and_a_long_name_stands_alone() -> None:
    page = tree.Page(width=40, colour=False)

    assert page.listed(
        [
            ("a", "one two three four five six seven eight nine ten"),
            ("a-name-too-long-to-sit-beside", "what it is"),
            ("bb", ""),
        ]
    ) == [
        "  a   one two three four five six seven",
        "      eight nine ten",
        "  a-name-too-long-to-sit-beside",
        "      what it is",
        "  bb",
    ]
    assert page.listed([("a-name-too-long-to-sit-beside", ""), ("b", "what")]) == [
        "  a-name-too-long-to-sit-beside",
        "  b  what",
    ]
    assert page.listed([]) == []


def test_a_page_is_its_lines_under_their_headings() -> None:
    page = tree.Page(width=40, colour=False)
    page.line("first")
    page.says("one two three four five six seven eight nine ten", 2)
    page.section("Empty", [])
    page.section("Held", ["  a"])

    assert page.text() == (
        "first\n  one two three four five six seven\n  eight nine ten\n\nHeld:\n  a\n"
    )


LOCAL = Command(
    "here", "Open", args=(Arg(("--loud",), "Cancel"),), run=_greets, local=True
)


def test_a_command_that_asks_no_daemon_takes_no_daemon(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran: list[Call] = []
    monkeypatch.setattr(
        tree, "commands", lambda: {"here": dataclasses.replace(LOCAL, run=ran.append)}
    )

    assert [arg.name for arg in tree.taken(LOCAL)] == ["loud", "json", "no_color"]
    assert [arg.name for arg in tree.taken(GREET.commands[0])][-3:] == [
        "json",
        "daemon",
        "no_color",
    ]
    said = tree.helps(["here"], LOCAL)
    assert "--daemon" not in said
    assert said.endswith(
        "Exit codes:\n"
        "  0    did what was asked\n"
        "  1    the request was refused and the reason was printed\n"
        "  2    the command line could not be read\n"
        "  130  interrupted with ctrl+c\n"
    )
    described = tree.described(["here"], LOCAL)
    assert list(described["exit_status"]) == ["0", "1", "2", "130"]
    assert "the request was refused and the reason was printed" in LOCAL.texts()
    assert [one["name"] for one in described["arguments"]] == [
        "--loud",
        "--json",
        "--no-color",
    ]

    assert tree.runs(["here", "--json"]) == 0
    assert (ran[0].json, ran[0].daemon) == (True, "")
    capsys.readouterr()

    # A file of this machine's that would not be read: refused here, nobody unreached.
    def fails(_: Call) -> None:
        raise OSError("no such file")

    monkeypatch.setattr(
        tree, "commands", lambda: {"here": dataclasses.replace(LOCAL, run=fails)}
    )
    assert tree.runs(["here"]) == tree.REFUSED
    assert capsys.readouterr().err == "hmz here: no such file\n"
    with pytest.raises(SystemExit) as raised:
        tree.runs(["here", "--daemon", "far"])
    assert raised.value.code == tree.UNREAD
    assert "--daemon" in capsys.readouterr().err


@pytest.mark.usefixtures("greeting")
def test_a_line_names_a_command_and_leaves_the_rest() -> None:
    say = GREET.commands[0]

    assert tree.named(["greet"]) == (("greet",), GREET, [])
    assert tree.named(["greet", "say", "you", "--loud"]) == (
        ("greet", "say"),
        say,
        ["you", "--loud"],
    )
    assert tree.named(["greet", "shout", "you"]) == (
        ("greet",),
        GREET,
        ["shout", "you"],
    )
    assert tree.named(["greet", "--help", "say"]) == (
        ("greet",),
        GREET,
        ["--help", "say"],
    )
    with pytest.raises(KeyError):
        tree.named(["nope"])


def test_a_commands_parser_reads_its_line() -> None:
    say = GREET.commands[0]

    given = tree.parser(["greet", "say"], say).parse_args(["you", "-t", "a", "--json"])

    assert (given.name, given.to, given.json, given.kind) == ("you", ["a"], True, "a")
    with pytest.raises(SystemExit) as raised:
        tree.parser(["greet", "say"], say).parse_args([])
    assert raised.value.code == tree.UNREAD


@pytest.mark.usefixtures("greeting")
def test_no_color_is_help_without_escapes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")

    assert tree.runs(["greet"]) == 0
    assert "\x1b[1mCommands\x1b[0m:" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        tree.runs(["greet", "say", "--help"])
    assert "\x1b[1mOptions\x1b[0m:" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        tree.runs(["greet", "say", "--no-color", "--help"])
    assert "\x1b[" not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        tree.runs(["greet", "--no-color", "--help"])
    assert "\x1b[" not in capsys.readouterr().out


def test_a_command_is_described_as_one_object() -> None:
    said = tree.described(["greet"], GREET)

    assert said["command"] == "hmz greet"
    (say,) = said["commands"]
    assert say["usage"] == "hmz greet say NAME [options]"
    assert say["arguments"][0] == {
        "name": "NAME",
        "flags": ["name"],
        "description": "Close",
        "positional": True,
        "required": True,
        "repeatable": False,
        "takes_value": True,
        "choices": [],
        "default": None,
    }
    assert [one["name"] for one in say["arguments"]][-3:] == [
        "--json",
        "--daemon NAME",
        "--no-color",
    ]
    assert say["json"] == [
        {"field": "greeted", "type": "string", "description": "Back"}
    ]
    assert say["exit_status"]["7"] == "Cancel"
    assert say["daemon_methods"] == ["devices.list"]
    json.dumps(said)


def test_every_text_a_command_says_is_listed() -> None:
    assert set(GREET.texts()) == {"Open", "Search", "Back", "Close", "Cancel"}


def test_this_machines_daemon_is_asked_as_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = mock.Mock()
    monkeypatch.setattr(hmz.sdk.Client, "local", local)

    assert tree.reach("") is local.return_value
    assert tree.reach("local") is local.return_value
    assert local.mock_calls == [mock.call(kind="cli"), mock.call(kind="cli")]


def test_another_machines_daemon_is_asked_by_the_name_it_is_kept_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    named = mock.Mock()
    monkeypatch.setattr(hmz.sdk.Client, "named", named)

    assert tree.reach("gpu") is named.return_value
    named.assert_called_once_with("gpu", kind="cli")


def test_a_name_no_daemon_is_kept_under_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        hmz.sdk.Client, "named", mock.Mock(side_effect=LookupError("none"))
    )

    with pytest.raises(
        hmz.sdk.Refused, match=r"No daemon is kept under the name far\."
    ) as refused:
        tree.reach("far")
    assert refused.value.code == 404

    assert main(["devices", "list", "--daemon", "far"]) == tree.REFUSED
    assert capsys.readouterr().err == (
        "hmz devices list: No daemon is kept under the name far.\n"
    )


def test_a_daemon_kept_that_cannot_be_reached_ends_as_one_that_cannot(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        hmz.sdk.Client, "named", mock.Mock(side_effect=ConnectionError("no route"))
    )

    assert main(["devices", "list", "--daemon", "gpu", "--json"]) == tree.UNREACHED
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 503, "message": "the daemon cannot be reached: no route"}
    }


def test_a_session_is_opened_when_first_wanted_and_closed_after(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = mock.Mock()
    client.devices.list.return_value = []
    reach = mock.Mock(return_value=client)
    monkeypatch.setattr(tree, "reach", reach)

    assert main(["devices", "list", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {"devices": []}
    reach.assert_called_once_with("")
    client.close.assert_called_once_with()


def _here(call: Call) -> None:
    if call.loud:
        raise PermissionError("no file")
    call.answers({"daemon": call.daemon}, ["here"])


HERE = Command(
    "here", "Open", args=(Arg(("--loud",), "Cancel"),), run=_here, local=True
)


def test_a_local_command_takes_no_daemon_and_reaches_none(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tree, "commands", lambda: {"here": HERE})
    reach = mock.Mock()
    monkeypatch.setattr(tree, "reach", reach)

    assert tree.runs(["here", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"daemon": ""}
    reach.assert_not_called()

    with pytest.raises(SystemExit) as raised:
        tree.runs(["here", "--daemon", "far"])
    assert raised.value.code == tree.UNREAD
    assert "--daemon" in capsys.readouterr().err

    # A file that would not be written is a refusal: there is no daemon to be unreached.
    assert tree.runs(["here", "--loud"]) == tree.REFUSED
    assert capsys.readouterr().err == "hmz here: no file\n"
    assert tree.runs(["here", "--loud", "--json"]) == tree.REFUSED
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 0, "message": "no file"}
    }


def test_a_local_command_says_so_in_its_help_and_its_description() -> None:
    assert tree.helps(["here"], HERE) == (
        "Usage: hmz here [options]\n"
        "\n"
        "Open\n"
        "\n"
        "Options:\n"
        "  --loud      Cancel\n"
        "  --json      print one JSON document instead of text\n"
        "  --no-color  print without terminal colours\n"
        "  -h, --help  show this help and exit\n"
        "\n"
        "Exit codes:\n"
        "  0    did what was asked\n"
        "  1    the request was refused and the reason was printed\n"
        "  2    the command line could not be read\n"
        "  130  interrupted with ctrl+c\n"
    )

    said = tree.described(["here"], HERE)

    assert [one["name"] for one in said["arguments"]] == [
        "--loud",
        "--json",
        "--no-color",
    ]
    assert said["exit_status"] == {
        "0": "did what was asked",
        "1": "the request was refused and the reason was printed",
        "2": "the command line could not be read",
        "130": "interrupted with ctrl+c",
    }
    assert "the request was refused and the reason was printed" in set(HERE.texts())


def test_rows_are_set_in_columns() -> None:
    assert tree.table([["a", "bbb", "c"], ["aaaa", "b", ""]]) == [
        "a     bbb  c",
        "aaaa  b",
    ]
    assert tree.table([]) == []


def _removes(call: Call) -> None:
    if call.what == "unread":
        raise tree.Unread("this is not JSON")
    if call.what == "interrupted":
        raise KeyboardInterrupt
    if call.what == "went":
        call.client.call("devices.list")
    tree.sure(call, f"Remove {tree.workspace(call)}?")
    call.answers({"removed": call.what}, ["gone"])


REMOVE = Command(
    "remove",
    "Open",
    args=(Arg(("what",), "Close"), tree.WORKSPACE, tree.YES),
    run=_removes,
)


@pytest.fixture
def removing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tree, "commands", lambda: {"remove": REMOVE})


def _stdin(monkeypatch: pytest.MonkeyPatch, typed: str, *, terminal: bool) -> None:
    asked = mock.Mock(isatty=lambda: terminal, readline=mock.Mock(return_value=typed))
    monkeypatch.setattr("sys.stdin", asked)


@pytest.mark.usefixtures("removing")
def test_a_line_a_command_cannot_read_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert tree.runs(["remove", "unread"]) == tree.UNREAD
    said = capsys.readouterr()
    assert (said.out, said.err) == (
        "",
        "hmz remove: this is not JSON\nRun `hmz remove --help` for help.\n",
    )

    assert tree.runs(["remove", "unread", "--json"]) == tree.UNREAD
    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "error": {"code": 400, "message": "this is not JSON"}
    }
    assert said.err == ""


@pytest.mark.usefixtures("removing")
def test_an_interrupt_ends_any_command_with_130_and_no_more_said(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert tree.runs(["remove", "interrupted", "--json"]) == tree.INTERRUPTED == 130

    said = capsys.readouterr()
    assert (said.out, said.err) == ("", "")


@pytest.mark.usefixtures("removing")
@pytest.mark.parametrize(
    ("ended", "status", "message"),
    [
        (True, tree.UNREACHED, "the daemon cannot be reached: the daemon went away"),
        # Refused 503 by a daemon that is still there: what the call needs is not reached.
        (False, tree.REFUSED, "the daemon went away"),
    ],
)
def test_a_session_that_ended_under_a_call_is_a_daemon_not_reached(
    ended: bool,
    status: int,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = mock.Mock()
    client.call.side_effect = hmz.sdk.Refused("the daemon went away", code=503)
    client.wait.return_value = ended
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))

    assert tree.runs(["remove", "went", "--json"]) == status

    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 503, "message": message}
    }
    client.wait.assert_called_once_with(0)
    client.close.assert_called_once_with()


@pytest.mark.usefixtures("removing")
def test_removing_asks_at_a_terminal_and_takes_only_a_yes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, "n\n", terminal=True)
    assert tree.runs(["remove", "it", "-w", "/w"]) == tree.REFUSED
    said = capsys.readouterr()
    assert (said.out, said.err) == (
        "",
        "Remove /w? [y/N] hmz remove: Nothing was changed.\n",
    )

    _stdin(monkeypatch, "YES\n", terminal=True)
    assert tree.runs(["remove", "it", "-w", "/w"]) == tree.DONE
    said = capsys.readouterr()
    assert (said.out, said.err) == ("gone\n", "Remove /w? [y/N] ")


@pytest.mark.usefixtures("removing")
def test_nobody_is_asked_without_a_terminal_or_under_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    nobody = "Nobody is at a terminal to ask; run it again with `-y`."
    _stdin(monkeypatch, "y\n", terminal=False)
    assert tree.runs(["remove", "it"]) == tree.REFUSED
    assert capsys.readouterr().err == f"hmz remove: {nobody}\n"

    _stdin(monkeypatch, "y\n", terminal=True)
    assert tree.runs(["remove", "it", "--json"]) == tree.REFUSED
    said = capsys.readouterr()
    assert json.loads(said.out) == {"error": {"code": 0, "message": nobody}}
    assert said.err == ""

    _stdin(monkeypatch, "", terminal=False)
    assert tree.runs(["remove", "it", "--yes", "--json"]) == tree.DONE
    assert json.loads(capsys.readouterr().out) == {"removed": "it"}


def test_a_command_that_asks_says_who_may_refuse_it() -> None:
    said = tree.described(["remove"], REMOVE)["exit_status"]

    assert said["1"] == "the daemon refused it, or you did not answer yes"
    assert said["1"] in set(REMOVE.texts())
    assert said["130"] == "interrupted with ctrl+c"


def test_a_status_a_command_declares_is_said_in_its_own_words() -> None:
    followed = dataclasses.replace(REMOVE, exits=(Exit(130, "Cancel"),))

    assert tree.described(["remove"], followed)["exit_status"]["130"] == "Cancel"
    assert "  130  Cancel\n" in tree.helps(["remove"], followed)
    assert "interrupted with ctrl+c" not in tree.helps(["remove"], followed)


def test_a_workspace_is_whole_and_read_from_where_the_line_was_typed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    here = os.getcwd()  # noqa: PTH109 -- as the helper names it

    assert tree.whole("sub/../app") == f"{here}/app"
    assert tree.whole("/abs/app") == "/abs/app"
    # The daemon's own home, which this machine cannot expand for it.
    assert tree.whole("~/app") == "~/app"

    given = mock.Mock(workspace=None)
    assert tree.workspace(Call(("x",), given)) == here
    given.workspace = "app"
    assert tree.workspace(Call(("x",), given)) == f"{here}/app"
