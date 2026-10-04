"""Where humanize keeps things, and the move from the name those places had before.

`~/.hmz` and a project's `.hmz` were `~/.humanize` and `.humanize`. What was kept under the old
name is moved, in one rename, the first time the new one is asked for -- and only then: a
directory already at the new name is the one in use, and the old one is left as it was rather
than merged into it or taken for an error.

The move is made once per place and process, and the environment, the working directory and
what was moved are the process's, not the test's: a thread an earlier test left running may ask
for humanize's home at any moment. So each test lays out its directories first and only then
asks, as a new process would, inside :func:`_anew` -- a window as short as the asking, out of
which the home and the working directory are the suite's own again.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import hmz
from hmz import here, home
from hmz.runtime.flowing.finding import find, fork

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def me(tmp_path: Path) -> Path:
    """A home directory of the test's own."""
    at = tmp_path / "me"
    at.mkdir()
    return at


@contextlib.contextmanager
def _anew(
    me: Path, *, named: Path | None = None, cwd: Path | None = None
) -> Generator[None]:
    """Asks as a process just started would, from `cwd`, with `me` as the home directory.

    Args:
      me: The home directory.
      named: What `HUMANIZE_HOME` says, or None for it to say nothing.
      cwd: Where humanize is being run, or None for where the test already is.
    """
    with pytest.MonkeyPatch.context() as patched:
        patched.setenv("HOME", str(me))
        if named is None:
            patched.delenv("HUMANIZE_HOME", raising=False)
        else:
            patched.setenv("HUMANIZE_HOME", str(named))
        if cwd is not None:
            patched.chdir(cwd)
        hmz._moved.cache_clear()
        hmz._project.cache_clear()
        yield


def _kept(at: Path, said: str) -> None:
    """Something written under a directory, which is what tells one directory from another."""
    at.mkdir(parents=True, exist_ok=True)
    (at / "settings.yaml").write_text(said)


# ---------------------------------------------------------------------------- the home


def test_the_home_is_hmz_under_yours(me: Path) -> None:
    with _anew(me):
        assert home() == me / ".hmz"
    assert not (me / ".hmz").exists(), "asking is not making"


def test_a_home_under_the_old_name_is_moved_whole(me: Path) -> None:
    _kept(me / ".humanize", "old")

    with _anew(me):
        assert home() == me / ".hmz"

    assert not (me / ".humanize").exists()
    assert (me / ".hmz" / "settings.yaml").read_text() == "old"


def test_a_home_under_the_new_name_is_left_as_it_is(me: Path) -> None:
    _kept(me / ".hmz", "new")

    with _anew(me):
        assert home() == me / ".hmz"

    assert (me / ".hmz" / "settings.yaml").read_text() == "new"
    assert not (me / ".humanize").exists()


def test_where_both_are_the_new_one_is_used_and_neither_is_touched(me: Path) -> None:
    _kept(me / ".humanize", "old")
    _kept(me / ".hmz", "new")

    with _anew(me):
        assert home() == me / ".hmz"

    assert (me / ".humanize" / "settings.yaml").read_text() == "old"
    assert (me / ".hmz" / "settings.yaml").read_text() == "new"
    assert sorted(one.name for one in (me / ".hmz").iterdir()) == ["settings.yaml"]


def test_a_home_somebody_named_moves_nothing(me: Path, tmp_path: Path) -> None:
    _kept(me / ".humanize", "old")

    with _anew(me, named=tmp_path / "elsewhere"):
        assert home() == tmp_path / "elsewhere"

    assert (me / ".humanize" / "settings.yaml").read_text() == "old"
    assert not (me / ".hmz").exists()


def test_a_move_that_fails_is_no_reason_not_to_start(me: Path) -> None:
    _kept(me / ".humanize", "old")

    def refused(self: Path, target: Path) -> Path:
        raise OSError(18, "Invalid cross-device link", str(self))

    with _anew(me), pytest.MonkeyPatch.context() as patched:
        patched.setattr(Path, "rename", refused)
        assert home() == me / ".hmz"

    assert (me / ".humanize" / "settings.yaml").read_text() == "old"
    assert not (me / ".hmz").exists()


def test_the_move_is_made_once_a_process(me: Path) -> None:
    """Once moved, an old directory made again afterwards is one somebody else is writing."""
    _kept(me / ".humanize", "old")

    with _anew(me):
        assert home() == me / ".hmz"
        (me / ".hmz").rename(me / ".humanize")
        assert home() == me / ".hmz"

    assert (me / ".humanize" / "settings.yaml").read_text() == "old"
    assert not (me / ".hmz").exists()


# ------------------------------------------------------------------------- the project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A directory humanize is being run in."""
    at = tmp_path / "project"
    at.mkdir()
    return at


def test_a_project_keeps_its_own_in_hmz_here(me: Path, project: Path) -> None:
    with _anew(me, named=me / "home", cwd=project):
        assert here() == Path(".hmz")
    assert not (project / ".hmz").exists(), "asking is not making"


def test_a_project_directory_under_the_old_name_is_moved(
    me: Path, project: Path
) -> None:
    _kept(project / ".humanize", "old")

    with _anew(me, named=me / "home", cwd=project):
        assert here() == Path(".hmz")

    assert not (project / ".humanize").exists()
    assert (project / ".hmz" / "settings.yaml").read_text() == "old"


def test_where_a_project_has_both_neither_is_touched(me: Path, project: Path) -> None:
    _kept(project / ".humanize", "old")
    _kept(project / ".hmz", "new")

    with _anew(me, named=me / "home", cwd=project):
        assert here() == Path(".hmz")

    assert (project / ".humanize" / "settings.yaml").read_text() == "old"
    assert (project / ".hmz" / "settings.yaml").read_text() == "new"


def test_the_directory_humanize_home_names_is_not_a_project_s_to_move(
    me: Path, project: Path
) -> None:
    """Run from your home with `HUMANIZE_HOME=~/.humanize`, `.humanize` here is that home."""
    _kept(project / ".humanize", "home")

    with _anew(me, named=project / ".humanize", cwd=project):
        assert here() == Path(".hmz")

    assert (project / ".humanize" / "settings.yaml").read_text() == "home"
    assert not (project / ".hmz").exists()


def test_run_from_your_home_the_home_there_moves_by_the_rules_for_a_home(
    me: Path, tmp_path: Path
) -> None:
    """Moved where nothing names another home, and left where something does."""
    _kept(me / ".humanize", "old")

    with _anew(me, named=tmp_path / "elsewhere", cwd=me):
        assert here() == Path(".hmz")

    assert (me / ".humanize" / "settings.yaml").read_text() == "old"
    assert not (me / ".hmz").exists()

    with _anew(me, cwd=me):
        assert here() == Path(".hmz")

    assert not (me / ".humanize").exists()
    assert (me / ".hmz" / "settings.yaml").read_text() == "old"


def test_a_project_since_removed_holds_nothing_to_move(me: Path, project: Path) -> None:
    with _anew(me, named=me / "home", cwd=project):
        os.rmdir(project)  # noqa: PTH106 -- the directory being run in, gone from under it
        assert here() == Path(".hmz")


def test_a_project_s_own_flows_are_found_where_they_were_kept_before(
    me: Path, project: Path
) -> None:
    flow = project / ".humanize" / "flows" / "mine" / "__init__.py"
    flow.parent.mkdir(parents=True)
    flow.write_text('"""Mine."""\n')

    with _anew(me, named=me / "home", cwd=project):
        found = find("@local/mine")

    assert found == str((project / ".hmz" / "flows" / "mine" / "__init__.py").resolve())
    assert not (project / ".humanize").exists()


def test_a_flow_forked_lands_beside_the_project_s_own_kept_before(
    me: Path, project: Path
) -> None:
    flow = project / ".humanize" / "flows" / "mine" / "__init__.py"
    flow.parent.mkdir(parents=True)
    flow.write_text('"""Mine."""\n')

    with _anew(me, named=me / "home", cwd=project):
        fork("chat")

    assert (project / ".hmz" / "flows" / "chat" / "__init__.py").is_file()
    assert (project / ".hmz" / "flows" / "mine" / "__init__.py").is_file()
    assert not (project / ".humanize").exists()
