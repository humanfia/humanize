"""The suite's own places: what a test's home and temporary directory are undone to.

A thread that outlives its test reads the environment after the test's own home and `TMPDIR`
were given back. What is under them is the suite's, never the home or the daemon of whoever
runs it (`_suite_places` in `tests/conftest.py`).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import hmz

if TYPE_CHECKING:
    import pytest


def test_a_tests_home_and_temporary_directory_are_undone_to_the_suites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    homes = (hmz.config, hmz.data, hmz.state, hmz.cache)
    assert [one() for one in homes] == [
        tmp_path / "xdg" / kind / "humanize"
        for kind in ("config", "data", "state", "cache")
    ]
    mine = hmz.machine()

    # As the end of the test does it, for whatever of it is still going.
    monkeypatch.undo()

    suite = hmz.data()
    assert suite.parent.parent.name == "home"
    assert not suite.is_relative_to(tmp_path)
    between = Path(os.environ["TMPDIR"])
    assert (between.name, between.parent) == ("between", suite.parent.parent.parent)
    assert tempfile.gettempdir() == str(between)
    assert hmz.machine() == between / mine.name
    assert {
        os.environ[f"HUMANIZE_{one}"] for one in ("SENTRY", "PRICES", "RELEASES")
    } == {"off"}


def test_a_tests_home_directory_and_path_are_undone_to_the_suites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.conftest import THEIRS

    mine = Path.home()

    monkeypatch.undo()

    # `~` is never the home of whoever runs the suite, nor is what they installed found.
    nobody = Path.home()
    assert nobody not in (mine, Path(THEIRS["HOME"]))
    assert (nobody.name, nobody.parent) == ("nobody", hmz.data().parents[2])
    assert Path(THEIRS["HOME"]) not in Path("~/.hmz").expanduser().parents
    searched = os.environ["PATH"].split(os.pathsep)
    assert set(searched) <= {
        str(Path(sys.executable).parent),
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    }


def test_what_names_a_test_directory_in_their_home_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests import conftest

    theirs = tmp_path / "theirs"
    (theirs / "flowverses").mkdir(parents=True)
    history = theirs / "history.jsonl"
    history.write_text('{"workspace": "/their/own/project"}\n')
    (theirs / "settings.toml").write_text("listen = []\n")
    monkeypatch.setattr(conftest, "_THEIR_HOMES", (theirs,))
    marks = frozenset({str(tmp_path / "mine")})
    before = conftest.kept_there()

    # Whoever runs the suite goes on using it: nothing of that is a test's.
    with history.open("a") as held:
        held.write('{"workspace": "/their/own/other"}\n')
    (theirs / "identity").write_text("theirs")
    assert conftest.written_there(before, marks) == []

    with history.open("a") as held:
        held.write(f'{{"workspace": "{tmp_path / "mine"}"}}\n')
    kept = theirs / "flowverses" / "scratch"
    kept.mkdir()
    (kept / "index.yaml").write_text(f"url: {tmp_path / 'mine'}\n")
    (theirs / "web-port").write_text(f"{tmp_path / 'mine'}")
    assert conftest.written_there(before, marks) == [
        str(kept),
        str(history),
        str(theirs / "web-port"),
    ]
    # Looked at again, what has not changed since is not found twice.
    assert conftest.written_there(conftest.kept_there(), marks) == []
    # Before the suite's own look at their home, which is the real one again.
    monkeypatch.undo()
