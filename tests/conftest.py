"""What every test shares: a run that stays on the machine it was started on.

Three trees, one rule each:

- `tests/unit/<package>/` -- one directory per `hmz` top-level package. Only the public names
  of what is tested; every other `hmz` package mocked. No subprocess, socket or network.
- `tests/integration/test_<topic>_*.py` -- packages wired together against fakes this repo
  writes. CI runs one job per topic.
- `tests/system/` -- real agents on real tasks. Never in CI; see `AGENTS.md`.

The autouse fixtures below keep a test out of the home, the daemon, the network and the
sign-ins of whoever runs it. They reach into a few private names because resetting process
state is what they are for; tests themselves may not.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import signal
import stat
import tempfile
import unittest.mock
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

import hmz.coganchor.models
import hmz.coganchor.transport
import hmz.runtime.flowing.verses
from hmz.runtime import telemetry

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.coganchor.backends import Model

#: Asking a backend what it runs, kept so that `asking` can give it back.
_ASKS = hmz.coganchor.models.ask


@pytest.fixture(autouse=True)
def _humanize_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home of the test's own; no crash reports, no daemon, no price fetch."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "humanize-home"))
    monkeypatch.setenv("HUMANIZE_SENTRY", "off")
    monkeypatch.setenv("HUMANIZE_SHADOWS", str(tmp_path / "shadows"))
    monkeypatch.setenv("HUMANIZE_DAEMON", "off")
    monkeypatch.setenv("HUMANIZE_PRICES", "off")
    telemetry.again()


@pytest.fixture(scope="session")
def _temporary() -> Iterator[Path]:
    """A short temporary directory for the session: socket paths must stay under ~100 bytes."""
    held = Path(tempfile.mkdtemp(prefix="hmz-"))
    try:
        yield held
    finally:
        shutil.rmtree(held, ignore_errors=True)


_tests = itertools.count(1)


@pytest.fixture(autouse=True)
def _machine_temp(_temporary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `TMPDIR` per test, so each finds only the daemon it started itself."""
    held = _temporary / f"{next(_tests)}"
    held.mkdir()
    monkeypatch.setenv("TMPDIR", str(held))
    monkeypatch.setattr(tempfile, "tempdir", str(held))
    monkeypatch.setattr(hmz.coganchor.transport, "_bundle_held", None)


def _handlers() -> dict[int, Any]:
    """Every signal's handler but `SIGALRM`, which pytest-timeout owns."""
    held: dict[int, Any] = {}
    for one in signal.valid_signals():
        if one == signal.SIGALRM:
            continue
        try:
            held[int(one)] = signal.getsignal(one)
        except (OSError, ValueError):
            continue
    return held


@pytest.fixture(autouse=True, scope="session")
def _hears_interrupts() -> Iterator[None]:
    """Hears `SIGINT` even in a suite started with it ignored, which children would inherit."""
    if signal.getsignal(signal.SIGINT) != signal.SIG_IGN:
        yield
        return
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)


@pytest.fixture(autouse=True)
def _leaves_the_signals_as_it_found_them() -> Iterator[None]:
    """Fails a test that changed a signal handler, and puts it back for the next one."""
    before = _handlers()
    yield
    after = _handlers()
    changed = [one for one in before if after.get(one) != before[one]]
    for one in changed:
        was = before[one]
        signal.signal(one, signal.SIG_DFL if was is None else was)
    if changed:
        names = sorted(signal.strsignal(one) or str(one) for one in changed)
        pytest.fail(f"left these signals handled otherwise than it found them: {names}")


@pytest.fixture(autouse=True)
def _nothing_running_yet() -> Iterator[None]:
    """No flow running and no flow module held, before and after each test."""
    from hmz.runtime.flowing import engine, loading

    engine._RUNS.clear()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    loading.forget()
    yield
    engine._RUNS.clear()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    loading.forget()


#: Sign-ins that refresh themselves: the variable moving the CLI's home, its default, the file.
#: A copy that refreshes apart from the original gets the original revoked.
_SIGN_INS = (
    ("CODEX_HOME", ".codex", "auth.json"),
    ("CLAUDE_CONFIG_DIR", ".claude", ".credentials.json"),
)
_REFRESH_KEYS = frozenset({"refresh_token", "refreshtoken", "refresh"})


def _refresh_tokens() -> frozenset[bytes]:
    found: set[bytes] = set()

    def walk(said: object) -> None:
        if isinstance(said, dict):
            for key, value in cast("dict[str, object]", said).items():
                if (
                    key.lower() in _REFRESH_KEYS
                    and isinstance(value, str)
                    and len(value) > 15
                ):
                    found.add(value.encode())
                walk(value)
        elif isinstance(said, list):
            for value in cast("list[object]", said):
                walk(value)

    for variable, default, name in _SIGN_INS:
        home = Path(os.environ.get(variable) or Path.home() / default)
        try:
            walk(json.loads((home / name).read_bytes()))
        except (OSError, ValueError):
            continue
    return frozenset(found)


def _holding(root: Path, tokens: frozenset[bytes]) -> list[str]:
    held: list[str] = []
    for path in root.rglob("*"):
        try:
            found = path.lstat()
            if not stat.S_ISREG(found.st_mode) or found.st_size > 1 << 20:
                continue
            said = path.read_bytes()
        except OSError:
            continue
        if any(token in said for token in tokens):
            held.append(str(path))
    return held


@pytest.fixture(autouse=True, scope="session")
def _copies_no_sign_in(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Fails the run if any test left a copy of this machine's own sign-in in its temp dirs."""
    before = _refresh_tokens()
    yield
    tokens = before | _refresh_tokens()
    if tokens and (copied := _holding(tmp_path_factory.getbasetemp(), tokens)):
        pytest.fail(
            "a test copied this machine's own sign-in to "
            + ", ".join(copied)
            + " -- use the CLI's own home in place instead",
            pytrace=False,
        )


def _elsewhere(url: str) -> bool:
    """Whether git cloning `url` would leave this machine (`file://` does not)."""
    scheme, found, _ = url.partition("://")
    if found:
        return scheme.lower() != "file"
    before, found, _ = url.partition(":")
    return bool(found) and "/" not in before


@pytest.fixture(autouse=True, scope="session")
def _clones_nothing_elsewhere() -> Iterator[None]:
    """Refuses, as a failed clone would, any clone of a repository not on this machine.

    Patched for the whole session, not per test: a flowverse fetch runs on a thread that can
    outlive the test that started it.
    """
    verses = hmz.runtime.flowing.verses
    clones = verses.clone

    def only_from_here(url: str, at: Path) -> None:
        whence = verses._url_of(url)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        if _elsewhere(whence):
            raise OSError(f"the suite does not clone {whence}")
        clones(whence, at)

    with unittest.mock.patch.object(verses, "clone", only_from_here):
        yield


@pytest.fixture(autouse=True)
def _asks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never starts a real coding agent to ask what models it runs."""

    def refuse(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        raise AssertionError(f"the suite does not start {cli} to ask what it runs")

    monkeypatch.setattr(hmz.coganchor.models, "ask", refuse)


@pytest.fixture
def asking(_asks_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives a test about the asking the real `hmz.coganchor.models.ask` back."""
    monkeypatch.setattr(hmz.coganchor.models, "ask", _ASKS)
