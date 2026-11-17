"""What every unit test starts from, beyond what every test does (`tests/conftest.py`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import binary, fence

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="session")
def _coganchor_stand_in(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An empty file standing in for a build of `coganchor`, made once for the session."""
    stand_in = tmp_path_factory.mktemp("coganchor") / "coganchor"
    stand_in.write_text("")
    return stand_in


@pytest.fixture(autouse=True)
def _coganchor(_coganchor_stand_in: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`HUMANIZE_COGANCHOR` naming the stand-in, whatever is built or not.

    The command lines a unit test reads name `coganchor` by its path, and a unit test runs
    nothing: it must not depend on whether this checkout has a build of the crate, or where
    one is. A test about finding the build says for itself what the variable names.
    """
    monkeypatch.setenv(binary.VARIABLE, str(_coganchor_stand_in))


@pytest.fixture(autouse=True)
def _fences_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    """This machine able to fence the filesystem and the network, carve-outs and all.

    Asking is running `coganchor internal able`, which a unit test does not do; a test about a
    machine that cannot fence says so itself.
    """

    def able(sandbox: str = "auto") -> tuple[bool, bool]:
        del sandbox
        return True, True

    monkeypatch.setattr(fence, "able", able)

    def held(_: fence.Fence) -> str | None:
        return None

    monkeypatch.setattr(fence, "unheld", held)
