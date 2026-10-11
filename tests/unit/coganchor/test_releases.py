"""`hmz.coganchor.releases`: the newest release, read from a local file and kept a day.

Never the network: `releases.WHENCE` points every fetch at a file under `tmp_path`.
"""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING

import pytest

import hmz.coganchor
from hmz.coganchor import releases

if TYPE_CHECKING:
    from pathlib import Path


def _pypi(at: Path, version: str) -> Path:
    at.write_text(json.dumps({"info": {"version": version}, "releases": {}}))
    return at


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    at = _pypi(tmp_path / "pypi.json", "0.3.0")
    monkeypatch.setenv(releases.WHENCE, str(at))
    return at


@pytest.fixture
def running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hmz.coganchor, "__version__", "0.2.0", raising=False)


def test_nothing_is_kept_before_anything_was_asked() -> None:
    assert releases.latest() is None
    assert releases.newer() is None


def test_fetch_keeps_the_newest_release(source: Path) -> None:
    assert releases.fetch() == "0.3.0"
    assert releases.latest() == "0.3.0"
    assert json.loads(releases.where().read_text()) == {"latest": "0.3.0"}


@pytest.mark.usefixtures("running")
@pytest.mark.parametrize(
    ("newest", "newer"), [("0.3.0", "0.3.0"), ("0.2.0", None), ("0.1.9", None)]
)
def test_newer_is_only_a_release_past_the_running_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, newest: str, newer: str | None
) -> None:
    monkeypatch.setenv(releases.WHENCE, str(_pypi(tmp_path / "pypi.json", newest)))
    releases.fetch()
    assert releases.newer() == newer


@pytest.mark.usefixtures("source")
@pytest.mark.parametrize("version", ["0.0.0", "unknown"])
def test_a_source_tree_is_behind_no_release(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    monkeypatch.setattr(hmz.coganchor, "__version__", version, raising=False)
    releases.fetch()
    assert releases.newer() is None


def test_turned_off_it_asks_nothing() -> None:
    assert os.environ[releases.WHENCE] == "off"
    assert releases.fetch() is None
    releases.refresh(wait=True)
    assert releases.latest() is None


@pytest.mark.parametrize("body", ["not json", "{}", '{"info": {"version": "x.y"}}'])
def test_an_answer_with_no_release_keeps_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    at = tmp_path / "pypi.json"
    at.write_text(body)
    monkeypatch.setenv(releases.WHENCE, str(at))
    assert releases.fetch() is None
    assert releases.latest() is None


def test_refresh_asks_again_only_once_what_is_kept_is_stale(source: Path) -> None:
    releases.refresh(wait=True)
    assert releases.latest() == "0.3.0"
    _pypi(source, "0.4.0")
    releases.refresh(wait=True)
    assert releases.latest() == "0.3.0"
    old = time.time() - releases.STALE - 1
    os.utime(releases.where(), (old, old))
    releases.refresh(wait=True)
    assert releases.latest() == "0.4.0"


def test_refresh_asks_on_a_thread_of_its_own(source: Path) -> None:
    releases.refresh()
    until = time.monotonic() + 10
    while releases.latest() is None and time.monotonic() < until:
        time.sleep(0.01)
    assert releases.latest() == "0.3.0"
