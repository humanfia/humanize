"""`hmz.cli.tree`: a command said once, and its line, its help and its answers read off that."""

from __future__ import annotations

import json
from unittest import mock

import pytest

import hmz.sdk
from hmz.cli import main, tree
from hmz.cli.tree import Arg, Call, Command, Example, Exit, Field


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
        "  --daemon NAME  ask the daemon named in the daemon list, or this machine's daemon\n"
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
        "  0  did what was asked\n"
        "  1  the daemon refused the request and its reason was printed\n"
        "  2  the command line could not be read\n"
        "  3  the daemon could not be reached\n"
        "  7  Cancel\n"
        "\n"
        "Daemon calls:\n"
        "  devices.list\n"
        "\n"
        "See also:\n"
        "  hmz greet say --help\n"
    )


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
    local.assert_called_once_with(kind="cli")
    with pytest.raises(
        hmz.sdk.Refused, match=r"No daemon is kept under the name far\."
    ):
        tree.reach("far")


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


def test_rows_are_set_in_columns() -> None:
    assert tree.table([["a", "bbb", "c"], ["aaaa", "b", ""]]) == [
        "a     bbb  c",
        "aaaa  b",
    ]
    assert tree.table([]) == []
