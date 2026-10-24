from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.coganchor.unix import LONGEST, sockets

if TYPE_CHECKING:
    import pytest


def test_a_socket_that_fits_goes_under_the_temporary_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", "/t")
    assert sockets(LONGEST - 2) == Path("/t")


def test_a_socket_that_does_not_fit_goes_under_tmp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A Mac's: 49 bytes, which leaves no room for ssh's 40-digit `%C` and what follows it.
    mac = "/var/folders/02/x1xchdkn75v3kwjq981zdghc0000gn/T/"
    monkeypatch.setattr(tempfile, "tempdir", mac)
    assert sockets(len("/humanize-ssh-501/") + 66) == Path("/tmp")


def test_a_directory_preferred_is_kept_where_it_fits() -> None:
    assert sockets(20, "/run/user/1000") == Path("/run/user/1000")
    assert sockets(LONGEST, "/run/user/1000") == Path("/tmp")
