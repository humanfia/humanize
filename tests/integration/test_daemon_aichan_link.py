"""The scoped link of an Ai-chan conversation under a machine directory too long for an address.

The daemon listens on `<mdir>/ai-<hex>.sock` (Section 7.6.9 of files.md) and her host connects
to the path `HUMANIZE_AICHAN_LINK` names, wherever the temporary directory is: one nested deep
enough that the socket's whole path is longer than a Unix socket address holds is still one the
link is made and reached under.
"""

from __future__ import annotations

import tempfile
import threading
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from hmz.daemon.reach import Links
from hmz.runtime.doing import aichan
from tests.conftest import rehome

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(60),
]


def test_a_scoped_link_is_made_and_reached_under_a_long_machine_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rehome(monkeypatch, tmp_path / "home")
    deep = tmp_path / ("x" * 60) / ("y" * 60)
    deep.mkdir(parents=True)
    monkeypatch.setenv("TMPDIR", str(deep))
    monkeypatch.setattr(tempfile, "tempdir", str(deep))
    admitted = threading.Event()

    def admit(*_: object) -> None:
        admitted.set()

    links = Links(admit, mock.Mock())
    links.kept.made(
        {
            "slot": "ai:0ba5471f4630",
            "title": "hi",
            "scope": "daemon",
            "workspace": "/w",
            "epic": "",
            "nous": "claude/opus",
            "preset": "read-only",
        }
    )
    try:
        told = links.before("/w", "ai:0ba5471f4630")

        # The variable names the socket where the protocol puts it, whole.
        path = Links.path("ai:0ba5471f4630")
        assert told == {aichan.LINK: str(path)}
        assert len(str(path).encode()) > 108
        assert path.is_socket()
        assert path.stat().st_mode & 0o777 == 0o600

        monkeypatch.setenv(aichan.LINK, told[aichan.LINK])
        aichan.linked().close()
        assert admitted.wait(10)
    finally:
        links.close()
