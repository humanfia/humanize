"""`hmz.cli.main`: which command a line names, and opening the interface when it names none."""

from __future__ import annotations

import os
import sys
import types
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn
from unittest import mock

import pytest

import hmz.coganchor.binary
import hmz.daemon
from hmz.cli import COMMANDS, INTERNAL, main, many, opens, output

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("count", "thing", "said"),
    [
        (0, "session", "0 sessions"),
        (1, "session", "1 session"),
        ("1", "turn", "1 turn"),
        (2, "turn", "2 turns"),
        ("many", "run", "many runs"),
    ],
)
def test_many_says_a_count_as_english_does(
    count: int | str, thing: str, said: str
) -> None:
    assert many(count, thing) == said


def test_the_commands_are_these_and_the_internal_door() -> None:
    commands = [
        "exec",
        "web",
        "daemon",
        "relay",
        "update",
        "backup",
        "internal",
    ]
    assert list(COMMANDS) == commands
    assert set(INTERNAL) == {"anchor", "cli", "cred", "fence", "hook", "tools"}
    for run, summary in (*COMMANDS.values(), *INTERNAL.values()):
        assert callable(run)
        assert summary


def test_version_is_the_installed_one(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out == f"hmz {version('hmz')}\n"


def test_help_names_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: hmz")
    for name, (_, summary) in COMMANDS.items():
        assert name in out
        assert summary in out


@pytest.mark.parametrize("argv", [["bogus"], ["--version", "extra"], ["-x"], ["Exec"]])
def test_a_line_naming_no_command_is_refused(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code == 2
    assert "usage: hmz" in capsys.readouterr().err


def test_main_reads_this_processs_own_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["hmz", "--version"])
    assert main() == 0
    assert capsys.readouterr().out.startswith("hmz ")


@pytest.mark.parametrize("argv", [[], ["bogus"], ["--nope"]])
def test_internal_naming_none_of_them_is_refused(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["internal", *argv])
    assert raised.value.code == 2
    assert "usage: hmz internal" in capsys.readouterr().err


def test_internal_help_lists_all_six(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["internal", "--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert "Not intended to be run directly" in " ".join(out.split())
    for name, (_, summary) in INTERNAL.items():
        assert name in out
        assert summary in out


#: The three of them `coganchor` carries out, which this process becomes.
COGANCHOR = ("anchor", "cred", "fence")


@pytest.mark.parametrize("name", sorted(set(INTERNAL) - set(COGANCHOR)))
def test_each_internal_command_answers_its_own_help(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["internal", name, "--help"])
    assert raised.value.code == 0
    assert f"hmz internal {name}" in capsys.readouterr().out


class _Became(Exception):  # noqa: N818 -- what happened, not what went wrong
    """What a stand-in for `os.execv` raises in place of becoming the program."""


@pytest.mark.parametrize(
    ("argv", "line"),
    [
        (["anchor", "--target=local", "claude"], ["cog", "--target=local", "claude"]),
        (["anchor", "serve", "--stdio"], ["anchor", "--stdio"]),
        (["anchor", "rendezvous", "--listen", "0"], ["broker", "--listen", "0"]),
        (["cred", "--map", "/a=/b", "--", "claude"],
         ["internal", "cred", "--map", "/a=/b", "--", "claude"]),
        (["fence", "--policy", "{}", "--", "claude"],
         ["internal", "fence", "--policy", "{}", "--", "claude"]),
    ],
)  # fmt: skip
def test_the_anchors_internal_commands_become_coganchor(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], line: list[str]
) -> None:
    became: list[tuple[Path, list[str]]] = []

    def execv(program: Path, args: list[str]) -> NoReturn:
        became.append((program, args))
        raise _Became

    monkeypatch.setattr(hmz.coganchor.binary, "found", lambda: Path("/opt/coganchor"))
    monkeypatch.setattr(os, "execv", execv)
    # Set, so that what is set is taken off again after.
    monkeypatch.setenv(hmz.coganchor.binary.BINARIES, "")
    monkeypatch.delenv(hmz.coganchor.binary.BINARIES)

    with pytest.raises(_Became):
        main(["internal", *argv])

    assert became == [(Path("/opt/coganchor"), ["/opt/coganchor", *line])]
    # Told where the builds for other machines are, to ship the one a target needs.
    assert os.environ[hmz.coganchor.binary.BINARIES] == str(
        hmz.coganchor.binary.shelf()
    )


@pytest.mark.parametrize("name", COGANCHOR)
def test_with_no_coganchor_built_here_an_anchor_command_is_not_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    monkeypatch.setattr(hmz.coganchor.binary, "found", lambda: None)

    assert main(["internal", name, "--help"]) == 127
    assert "hmz: no coganchor is built for this machine (" in capsys.readouterr().err


class _App:
    """The terminal interface, as `opens` sees it."""

    made: list[dict[str, Any]]
    return_code: int | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).made.append(kwargs)

    def run(self) -> None:
        pass


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> type[_App]:
    """The interface, mocked, keeping what each one was opened with.

    Opened from no terminal in particular: what opening it writes into the environment for
    one terminal is put back after the test, whichever terminal the suite was started from.
    """
    for name in ("TMUX", "TERM_PROGRAM", "LC_TERMINAL", "TEXTUAL_DISABLE_KITTY_KEY"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)

    class App(_App):
        made: list[dict[str, Any]] = []  # noqa: RUF012 -- one list per test

    tui = types.ModuleType("hmz.tui")
    tui.Humanize = App  # pyright: ignore[reportAttributeAccessIssue]
    monkeypatch.setitem(sys.modules, "hmz.tui", tui)
    return App


@pytest.fixture
def attach(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Attaching to the runs this machine's daemon holds, mocked."""
    held = mock.Mock()
    monkeypatch.setattr(hmz.daemon, "attach", held)
    return held


@pytest.mark.parametrize(("code", "status"), [(None, 0), (0, 0), (3, 3)])
def test_no_command_opens_the_interface_on_the_runs_held_here(
    app: type[_App], attach: mock.Mock, code: int | None, status: int
) -> None:
    app.return_code = code
    assert main([]) == status
    attach.assert_called_once_with("tui")
    assert app.made == [{"link": attach.return_value}]


@pytest.mark.parametrize(
    ("environ", "set_"),
    [
        ({"TERM_PROGRAM": "iTerm.app"}, True),
        ({"LC_TERMINAL": "iTerm2"}, True),
        ({"TERM_PROGRAM": "iTerm.app", "TMUX": "/tmp/tmux"}, False),
        ({"TERM_PROGRAM": "Apple_Terminal"}, False),
    ],
)
def test_opening_keeps_extended_keys_off_a_direct_iterm(
    app: type[_App],
    attach: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    environ: dict[str, str],
    set_: bool,
) -> None:
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    main([])
    assert (os.environ.get("TEXTUAL_DISABLE_KITTY_KEY") == "1") is set_
    assert app.made == [{"link": attach.return_value}]


def test_opening_leaves_an_explicit_extended_keys_setting_alone(
    app: type[_App], attach: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.setenv("TEXTUAL_DISABLE_KITTY_KEY", "0")
    main([])
    assert os.environ["TEXTUAL_DISABLE_KITTY_KEY"] == "0"
    del app, attach


def test_a_daemon_of_an_older_humanize_is_said_and_not_opened(
    app: type[_App], attach: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    attach.side_effect = hmz.daemon.Older("held by an older Humanize")
    assert opens() == 1
    assert capsys.readouterr().err == "hmz: held by an older Humanize\n"
    assert app.made == []


def test_a_daemon_that_cannot_be_reached_is_said_and_not_opened(
    app: type[_App], attach: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    attach.side_effect = OSError("no fork")
    assert opens() == 1
    assert capsys.readouterr().err == "hmz: the daemon cannot be reached: no fork\n"
    assert app.made == []


def test_a_clock_is_up_while_the_runs_are_reached_and_down_before_the_interface(
    app: type[_App], attach: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    said: list[str | None] = []

    def spins(_: output.Out, says: Callable[[], str] | None) -> None:
        said.append(says and says())

    monkeypatch.setattr(output.Out, "spins", spins)
    attach.side_effect = lambda _: said.append("attached")  # pyright: ignore[reportUnknownLambdaType]
    assert opens() == 0
    assert said == ["connecting to the runs held here", "attached", None]
    assert len(app.made) == 1
