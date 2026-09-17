"""Which path is answered by which: the table a redirected run is decided by, read directly.

A dictionary and a command line. Longest match wins, everything inside a redirected directory
moves with it, a path is kept the way the kernel would read it, a path that is the program's
own is left alone, and a line that could not be run is a line to correct rather than a program
run unsupervised. All of it happens in this process: nothing here spawns anything, and the one
test about a supervisor that will not start refuses to start one on purpose. Which is what
makes it the unit tier -- there is no machine this cannot be checked on.

The other half is the supervisor itself -- a real `hmz internal cred` with a real program
under it -- and that is `tests/system/providers/test_redirect.py`, the tier meant to be left
out where a tracer cannot be counted on. Apart from it because a tier is a directory: kept in
that file, the arithmetic every redirect is built on would be left out along with it, and the
half that can be checked anywhere would be checked only where the kernel allows the other.
"""

from __future__ import annotations

import errno
import signal
import sys

import pytest

from hmz import cli
from hmz.coganchor.providers import redirect

# ------------------------------------------------------------------ the table


def test_the_path_that_was_named_is_answered_exactly() -> None:
    swaps = redirect.Swaps.of(
        [("/house/.claude/.credentials.json", "/store/mine/creds")]
    )

    assert swaps.swap("/house/.claude/.credentials.json") == "/store/mine/creds"


def test_everything_inside_a_redirected_directory_moves_with_it() -> None:
    """Kimi keeps one file per endpoint it has signed into, so a credential is a directory."""
    swaps = redirect.Swaps.of([("/house/.kimi-code/oauth", "/store/mine/home/oauth")])

    assert swaps.swap("/house/.kimi-code/oauth/api.json") == (
        "/store/mine/home/oauth/api.json"
    )
    assert swaps.swap("/house/.kimi-code/oauth/deeper/still.lock") == (
        "/store/mine/home/oauth/deeper/still.lock"
    )


def test_the_longest_of_the_paths_that_name_one_file_is_the_one_that_answers() -> None:
    swaps = redirect.Swaps.of(
        [
            ("/house/.claude", "/store/all"),
            ("/house/.claude/.credentials.json", "/store/one/creds"),
        ]
    )

    assert swaps.swap("/house/.claude/.credentials.json") == "/store/one/creds"
    assert swaps.swap("/house/.claude/settings.json") == "/store/all/settings.json"


@pytest.mark.parametrize(
    "path",
    [
        "/house/.claudely",  # the same text, a different directory
        "/house/.claude-code/.credentials.json",
        "/etc/hosts",
        "",
        ".claude/.credentials.json",
        "relative/path",
    ],
)
def test_a_path_that_is_the_programs_own_is_left_alone(path: str) -> None:
    swaps = redirect.Swaps.of([("/house/.claude", "/store/all")])

    assert swaps.swap(path) is None


def test_a_table_that_points_nothing_anywhere_is_nothing() -> None:
    assert not redirect.Swaps.of([])
    assert not redirect.Swaps.of([("", "/store/one"), ("/house/.claude", "")])
    assert redirect.Swaps.of([("/house/.claude", "/store/one")])


def test_a_path_is_kept_the_way_the_kernel_would_read_it() -> None:
    """A trailing slash and a dot name the same file, so they must name the same swap."""
    swaps = redirect.Swaps.of([("/house/.claude/", "/store/mine/./home")])

    assert swaps.pairs == (("/house/.claude", "/store/mine/home"),)


def test_the_swaps_are_read_off_the_command_line_that_named_them() -> None:
    swaps = redirect.read(["/house/.claude=/store/mine/home", "/house/x=/store/mine/y"])

    assert swaps.swap("/house/.claude/.credentials.json") == (
        "/store/mine/home/.credentials.json"
    )
    assert swaps.swap("/house/x") == "/store/mine/y"


@pytest.mark.parametrize(
    "said", ["nonsense", "relative=/store/one", "/house/x=relative", "=/store/one"]
)
def test_a_swap_that_is_not_two_absolute_paths_is_a_line_to_correct(said: str) -> None:
    with pytest.raises(ValueError, match="is not FROM=TO"):
        redirect.read([said])


def test_the_command_names_every_swap_and_then_the_program() -> None:
    rendered = redirect.command(
        [("/house/x", "/store/y"), ("/house/.claude", "/store/mine/home")],
        ["claude", "--print"],
    )

    assert rendered == [
        sys.executable,
        "-m",
        "hmz",
        "internal",
        "cred",
        "--map=/house/.claude=/store/mine/home",  # longest first, as the table is
        "--map=/house/x=/store/y",
        "--",
        "claude",
        "--print",
    ]


def test_a_program_with_nothing_to_answer_is_spawned_as_itself() -> None:
    """A provider that is only variables costs no supervisor and no ptrace at all."""
    assert redirect.command([], ["claude", "--print"]) == ["claude", "--print"]
    assert redirect.command([("", "")], ("claude",)) == ["claude"]


@pytest.mark.parametrize(
    ("status", "exits"),
    [(0, 0), (7 << 8, 7), (int(signal.SIGKILL), 128 + int(signal.SIGKILL))],
)
def test_what_a_program_came_to_is_what_the_run_comes_to(
    status: int, exits: int
) -> None:
    assert redirect.failed(status) == exits


def test_a_call_that_could_not_be_answered_is_failed_rather_than_let_through() -> None:
    """A turn that read the credentials of whoever is at this machine is the wrong account."""
    assert redirect.UNSWAPPABLE == errno.EIO


# --------------------------------------------------------- the line that runs one


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (["--map=/house/x=/store/y"], "no program given"),
        (["--map=relative=/store/y", "--", "true"], "is not FROM=TO"),
        (["--", "true"], "nothing to answer with anything"),
    ],
)
def test_a_line_that_could_not_be_run_is_a_line_to_correct(
    argv: list[str], says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["internal", "cred", *argv])

    assert stopped.value.code == 2
    assert says in capsys.readouterr().err


def test_a_run_that_cannot_be_supervised_does_not_run_unsupervised(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The program would read the credentials of whoever is at this machine, so it does not."""

    def refuse(*_: object) -> int:
        raise OSError("no supervisor here")

    monkeypatch.setattr("hmz.coganchor.providers.redirect.run", refuse)

    assert cli.main(["internal", "cred", "--map=/house/x=/store/y", "--", "true"]) == 1
    assert "no supervisor here" in capsys.readouterr().err
