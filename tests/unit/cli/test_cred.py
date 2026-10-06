"""`hmz internal cred`: a program run with some of its paths answered by others."""

from __future__ import annotations

from unittest import mock

import pytest

import hmz.coganchor.providers.redirect
from hmz.cli.cred import cred


@pytest.fixture
def redirect(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.coganchor.providers.redirect`, mocked to read one swap and exit 0."""
    held = mock.Mock()
    held.read.return_value = ["swap"]
    held.run.return_value = 0
    monkeypatch.setattr(hmz.coganchor.providers.redirect, "read", held.read)
    monkeypatch.setattr(hmz.coganchor.providers.redirect, "run", held.run)
    return held


@pytest.mark.parametrize(
    ("argv", "maps", "keeps", "command"),
    [
        (["--map", "/a=/b", "--", "claude"], ["/a=/b"], [], ["claude"]),
        (
            ["--map", "/a=/b", "claude", "-p", "hi"],
            ["/a=/b"],
            [],
            ["claude", "-p", "hi"],
        ),
        (
            ["--map", "/a=/b", "--map", "/c=/d", "--keep", "/s/*=/t", "--", "codex"],
            ["/a=/b", "/c=/d"],
            ["/s/*=/t"],
            ["codex"],
        ),
        (["--keep", "/s=/t", "--", "x", "--", "y"], [], ["/s=/t"], ["x", "--", "y"]),
    ],
)
def test_cred_runs_the_program_with_the_swaps(
    redirect: mock.Mock,
    argv: list[str],
    maps: list[str],
    keeps: list[str],
    command: list[str],
) -> None:
    redirect.run.return_value = 9
    assert cred(argv) == 9
    redirect.read.assert_called_once_with(maps, keeps)
    redirect.run.assert_called_once_with(["swap"], command)


@pytest.mark.parametrize("argv", [["--map", "/a=/b"], ["--map", "/a=/b", "--"]])
def test_cred_without_a_program_is_refused(
    redirect: mock.Mock, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cred(argv)
    assert raised.value.code == 2
    assert "no program given" in capsys.readouterr().err
    redirect.run.assert_not_called()


def test_cred_with_nothing_to_swap_is_refused(
    redirect: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    redirect.read.return_value = []
    with pytest.raises(SystemExit) as raised:
        cred(["--", "claude"])
    assert raised.value.code == 2
    assert "give at least one --map or --keep" in capsys.readouterr().err
    redirect.run.assert_not_called()


def test_cred_refuses_a_swap_it_cannot_read(
    redirect: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    redirect.read.side_effect = ValueError("FROM must be absolute")
    with pytest.raises(SystemExit) as raised:
        cred(["--map", "a=b", "--", "claude"])
    assert raised.value.code == 2
    assert "FROM must be absolute" in capsys.readouterr().err


@pytest.mark.parametrize(
    "failure", [OSError("no ptrace"), RuntimeError("x"), ValueError("y")]
)
def test_cred_never_runs_a_program_unsupervised(
    redirect: mock.Mock, failure: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    redirect.run.side_effect = failure
    assert cred(["--map", "/a=/b", "--", "claude"]) == 1
    assert capsys.readouterr().err == f"hmz internal cred: {failure}\n"
    assert redirect.run.call_count == 1
