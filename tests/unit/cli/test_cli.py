"""`hmz.cli.main`: which command a line names, and opening the interface when it names none."""

from __future__ import annotations

import io
import os
import sys
import types
from importlib.metadata import version
from typing import Any
from unittest import mock

import pytest

import hmz.coganchor.fence.wrap
import hmz.coganchor.providers.redirect
import hmz.daemon
from hmz.cli import APART, COMMANDS, INTERNAL, main, many, opens


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


def test_the_commands_are_exec_and_the_internal_door() -> None:
    assert set(COMMANDS) == {"exec", "internal"}
    assert set(INTERNAL) == {"anchor", "cred", "fence", "hook", "tools"}
    for run, summary in (*COMMANDS.values(), *INTERNAL.values()):
        assert callable(run)
        assert summary
    assert APART == "HUMANIZE_DAEMON"


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


def test_internal_help_lists_all_five(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["internal", "--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert "Not intended to be run directly" in " ".join(out.split())
    for name, (_, summary) in INTERNAL.items():
        assert name in out
        assert summary in out


@pytest.mark.parametrize("name", sorted(INTERNAL))
def test_each_internal_command_answers_its_own_help(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["internal", name, "--help"])
    assert raised.value.code == 0
    assert f"hmz internal {name}" in capsys.readouterr().out


def test_internal_hands_the_rest_of_the_line_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redirect = mock.Mock()
    redirect.read.return_value = ["swap"]
    redirect.run.return_value = 7
    monkeypatch.setattr(hmz.coganchor.providers.redirect, "read", redirect.read)
    monkeypatch.setattr(hmz.coganchor.providers.redirect, "run", redirect.run)
    assert main(["internal", "cred", "--map", "/a=/b", "--", "claude", "-p"]) == 7
    redirect.read.assert_called_once_with(["/a=/b"], [])
    redirect.run.assert_called_once_with(["swap"], ["claude", "-p"])


def test_internal_fence_reaches_the_fence(monkeypatch: pytest.MonkeyPatch) -> None:
    wrapping = mock.Mock(return_value=3)
    monkeypatch.setattr(hmz.coganchor.fence.wrap, "main", wrapping)
    assert main(["internal", "fence", "--policy", "{}", "--", "claude"]) == 3
    wrapping.assert_called_once_with("{}", ["claude"])


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


@pytest.mark.parametrize(("code", "status"), [(None, 0), (0, 0), (3, 3)])
def test_no_command_opens_the_interface_here(
    app: type[_App], code: int | None, status: int
) -> None:
    app.return_code = code
    assert main([]) == status
    assert app.made == [{}]


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
    monkeypatch: pytest.MonkeyPatch,
    environ: dict[str, str],
    set_: bool,
) -> None:
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    main([])
    assert (os.environ.get("TEXTUAL_DISABLE_KITTY_KEY") == "1") is set_
    assert app.made == [{}]


def test_opening_leaves_an_explicit_extended_keys_setting_alone(
    app: type[_App], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.setenv("TEXTUAL_DISABLE_KITTY_KEY", "0")
    main([])
    assert os.environ["TEXTUAL_DISABLE_KITTY_KEY"] == "0"
    del app


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _opened(
    monkeypatch: pytest.MonkeyPatch, *, stdout: io.StringIO | None = None
) -> int:
    """Opens the interface with a terminal on both ends, or on stdin and `stdout`.

    Set here rather than in a fixture: pytest puts its own capture back before each test runs.
    """
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(sys, "stdout", _Tty() if stdout is None else stdout)
    return opens()


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """A terminal on both ends, runs wanted apart, and attaching to them mocked."""
    monkeypatch.setenv(APART, "on")
    attach = mock.Mock()
    monkeypatch.setattr(hmz.daemon, "attach", attach)
    return attach


@pytest.mark.parametrize("value", ["off", "0", "no", " OFF "])
def test_runs_are_held_here_where_the_machine_says_so(
    app: type[_App], terminal: mock.Mock, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(APART, value)
    assert _opened(monkeypatch) == 0
    assert app.made == [{}]
    terminal.assert_not_called()


def test_runs_are_held_here_where_there_is_no_terminal(
    app: type[_App], terminal: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _opened(monkeypatch, stdout=io.StringIO()) == 0
    assert app.made == [{}]
    terminal.assert_not_called()


def test_the_interface_opens_on_the_runs_held_here(
    app: type[_App], terminal: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _opened(monkeypatch) == 0
    terminal.assert_called_once_with("tui")
    assert app.made == [{"link": terminal.return_value}]


def test_a_daemon_of_an_older_humanize_is_said_and_not_opened(
    app: type[_App],
    terminal: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    terminal.side_effect = hmz.daemon.Older("held by an older humanize")
    assert _opened(monkeypatch) == 1
    assert capsys.readouterr().err == "hmz: held by an older humanize\n"
    assert app.made == []


def test_runs_that_cannot_be_held_apart_are_held_here(
    app: type[_App],
    terminal: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    terminal.side_effect = OSError("no fork")
    assert _opened(monkeypatch) == 0
    assert "runs cannot be detached from the terminal (no fork)" in (
        capsys.readouterr().err
    )
    assert app.made == [{}]
