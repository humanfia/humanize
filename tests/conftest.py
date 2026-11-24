"""What every test shares: a run that stays on the machine it was started on.

Three trees, one rule each:

- `tests/unit/<package>/` -- one directory per `hmz` top-level package. Only the public names
  of what is tested; every other `hmz` package mocked. No subprocess, socket or network.
- `tests/integration/test_<topic>_*.py` -- packages wired together against fakes this repo
  writes. CI runs each topic alone.
- `tests/system/` -- real agents on real tasks, and the web page in real browsers. Never in
  CI; see `AGENTS.md`.

The autouse fixtures below keep a test out of the home, the daemon, the network and the
sign-ins of whoever runs it. They reach into a few private names because resetting process
state is what they are for; tests themselves may not.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shutil
import signal
import stat
import sys
import tempfile
import unittest.mock
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

import hmz.coganchor.backends
import hmz.coganchor.models
import hmz.runtime.flowing.verses
from hmz.runtime import telemetry

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.coganchor.backends import Model
    from hmz.daemon.private import Private

#: Asking a backend what it runs, kept so that `asking` can give it back.
_ASKS = hmz.coganchor.models.ask

#: The home of whoever runs the suite, read before any fixture names another: what no test
#: may write into.
_THEIR_HOME = Path(os.environ.get("HUMANIZE_HOME") or Path.home() / ".hmz")

#: Their `HOME` and `PATH`, read as early: what `tests/system`, which signs in as them and runs
#: what they installed, is given back for a test (`as_them`), the suite's own being neither.
THEIRS = {"HOME": str(Path.home()), "PATH": os.environ.get("PATH", os.defpath)}


def pytest_report_header() -> str | None:
    """Says, over the run, that no `coganchor` is built for this checkout, where none is.

    A new worktree has none: `crates/coganchor/target` is not in the repository. Every test
    that runs a turn then fails, each after waiting its patience out, and none of them says
    why as plainly as this does.
    """
    from hmz.coganchor import binary

    if binary.found() is not None:
        return None
    return (
        "hmz: NO coganchor IS BUILT FOR THIS CHECKOUT, and every test that runs a turn will "
        "fail: run `cargo build --manifest-path crates/coganchor/Cargo.toml`, or name a "
        f"build with {binary.VARIABLE}"
    )


@pytest.fixture(autouse=True)
def _humanize_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home of the test's own; no crash reports, no price, release or flowverse fetch.

    A daemon a test starts fetches every flowverse's index as it starts, in a process this
    one cannot patch: `git` there is told that GitHub is a directory that is not there, so
    that its clone fails at once, as `_clones_nothing_elsewhere` fails one here.
    """
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "humanize-home"))
    monkeypatch.setenv("HUMANIZE_SENTRY", "off")
    monkeypatch.setenv("HUMANIZE_SHADOWS", str(tmp_path / "shadows"))
    monkeypatch.setenv("HUMANIZE_PRICES", "off")
    monkeypatch.setenv("HUMANIZE_RELEASES", "off")
    monkeypatch.setenv("HUMANIZE_SCAN", "off")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{tmp_path / 'no-github'}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")
    telemetry.again()


@pytest.fixture(autouse=True)
def _no_real_agents(_temporary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hides every coding agent installed here. `tests/system` overrides this."""
    hide_agents(_temporary, monkeypatch)


#: The system's own directories and this Python's: a `PATH` no coding agent is found on.
_SEARCHED = os.pathsep.join(
    (str(Path(sys.executable).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin")
)


def as_them(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives one test the `HOME` and `PATH` of whoever runs the suite: `tests/system` alone."""
    for name, value in THEIRS.items():
        monkeypatch.setenv(name, value)


def hide_agents(temporary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hides every coding agent installed here, so a test that forgot its stand-in fails.

    Humanize looks for a CLI on `PATH`, then where an installer puts one: `PATH` is narrowed
    to the system's own directories and this Python's, and where an installer puts one to
    those under the home, which is the test's own.
    """
    monkeypatch.setenv("HOME", tempfile.mkdtemp(prefix="home-", dir=temporary))
    monkeypatch.setenv("PATH", _SEARCHED)
    installed = hmz.coganchor.backends._INSTALLED_AT  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(
        hmz.coganchor.backends,
        "_INSTALLED_AT",
        tuple(one for one in installed if one.startswith("~")),
    )


@pytest.fixture(scope="session")
def _temporary() -> Iterator[Path]:
    """A short temporary directory for the session: socket paths must stay under ~100 bytes."""
    held = Path(tempfile.mkdtemp(prefix="hmz-"))
    try:
        yield held
    finally:
        shutil.rmtree(held, ignore_errors=True)


@pytest.fixture(autouse=True, scope="session")
def _suite_places(_temporary: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """A home and a `TMPDIR` of the suite's own under every test's, never given back.

    `hmz.home()` and `hmz.machine()` read the environment at each call, and a test's own
    (`_humanize_home`, `_machine_temp`) are undone as it ends: a thread that outlives its test
    -- a host letting go of a chat, a flowverse fetch -- would write into the home, and reach
    the daemon, of whoever runs the suite. What a test's are undone to is the suite's, which
    stay named after the last test for the same reason. So are `HOME` and `PATH`, which
    `_no_real_agents` sets for a test and undoes as well: `~` there would be their home --
    `~/.hmz/flows`, a workspace `~` -- and their `PATH` holds the agents they installed.
    `tests/system`, which signs in as them, takes theirs back for each test (`as_them`).
    """
    # Pytest's own base is worked out of the temporary directory once: before that moves.
    tmp_path_factory.getbasetemp()
    between = _temporary / "between"
    between.mkdir()
    nobody = _temporary / "nobody"
    nobody.mkdir()
    os.environ |= {
        "HOME": str(nobody),
        "PATH": _SEARCHED,
        "HUMANIZE_HOME": str(_temporary / "home"),
        "HUMANIZE_SHADOWS": str(_temporary / "shadows"),
        "HUMANIZE_SENTRY": "off",
        "HUMANIZE_PRICES": "off",
        "HUMANIZE_RELEASES": "off",
        "HUMANIZE_SCAN": "off",
        "TMPDIR": str(between),
    }
    tempfile.tempdir = str(between)


#: A file of that home is read for a test directory's name only this far back from its end.
_TAIL = 1 << 20


def kept_there() -> dict[str, tuple[int, int]]:
    """What the home of whoever runs the suite holds, each as it was last written.

    A directory's entries by name alone (an epic, a chat, a flowverse, a provider), a file by
    when it was written and how long it is (`settings.toml`, `history.jsonl`).
    """
    held: dict[str, tuple[int, int]] = {}
    try:
        top = list(os.scandir(_THEIR_HOME))
    except OSError:
        return held
    for one in top:
        try:
            if one.is_dir(follow_symlinks=False):
                held.update(
                    {f"{one.name}/{under.name}": (0, 0) for under in os.scandir(one)}
                )
            else:
                found = one.stat(follow_symlinks=False)
                held[one.name] = (found.st_mtime_ns, found.st_size)
        except OSError:
            continue
    return held


def _slug(path: str) -> str:
    """A path as a directory kept for it is named: every other character a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _names(path: Path, since: int, marks: frozenset[bytes]) -> bool:
    """Whether a file names one of the suite's directories in what was added past `since`."""
    try:
        with path.open("rb") as held:
            held.seek(0, os.SEEK_END)
            # A little before, so that a name written across the old end is still whole.
            held.seek(max(0, since - 4096, held.tell() - _TAIL))
            said = held.read()
    except OSError:
        return False
    return any(mark in said for mark in marks)


def written_there(
    before: dict[str, tuple[int, int]], marks: frozenset[str]
) -> list[str]:
    """What changed in that home since `before` that names one of the suite's directories.

    Whoever runs the suite may be using Humanize meanwhile: only what names a directory of
    the suite's (`marks`) is a test's doing. Read, never written.
    """
    encoded = frozenset(mark.encode() for mark in marks)
    found: list[str] = []
    for name, (written, size) in sorted(kept_there().items()):
        was = before.get(name)
        if was == (written, size):
            continue
        at = _THEIR_HOME / name
        if "/" not in name:
            # Read from where it ended if it only grew, as a history does; whole otherwise.
            grown = was is not None and size >= was[1]
            named = _names(at, was[1] if was and grown else 0, encoded)
        else:
            named = any(_slug(mark) in name for mark in marks) or bool(
                _holding(at, encoded)
            )
        if named:
            found.append(str(at))
    return found


class _TheirHome:
    """That home as it was last looked at, and what names one of the suite's directories."""

    def __init__(self, marks: frozenset[str]) -> None:
        self._marks = marks
        self._before = kept_there()

    def check(self) -> None:
        """Fails whatever is running if a test's directory was written there since last asked."""
        before, self._before = self._before, kept_there()
        if written := written_there(before, self._marks):
            pytest.fail(
                f"wrote into the home of whoever runs the suite: {', '.join(written)} -- "
                "a test writes only under the home `_humanize_home` gives it",
                pytrace=False,
            )


@pytest.fixture(scope="session")
def _their_home(
    _suite_places: None, _temporary: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[_TheirHome]:
    """The home of whoever runs the suite, looked at once more after the last test."""
    places = (_temporary, tmp_path_factory.getbasetemp())
    held = _TheirHome(
        frozenset(str(one) for place in places for one in (place, place.resolve()))
    )
    yield held
    held.check()


@pytest.fixture(autouse=True)
def _writes_no_real_home(_their_home: _TheirHome) -> Iterator[None]:
    """Fails the test after which the home of whoever runs the suite names a test directory."""
    yield
    _their_home.check()


_tests = itertools.count(1)


@pytest.fixture(autouse=True)
def _machine_temp(_temporary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `TMPDIR` per test, so each finds only the daemon it started itself."""
    held = _temporary / f"{next(_tests)}"
    held.mkdir()
    monkeypatch.setenv("TMPDIR", str(held))
    monkeypatch.setattr(tempfile, "tempdir", str(held))


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
        home = Path(os.environ.get(variable) or Path(THEIRS["HOME"]) / default)
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


@pytest.fixture
def daemon(_machine_temp: None, _humanize_home: None) -> Iterator[Private]:
    """This machine's daemon, stood in for one test by a daemon of this process.

    It listens on the test's own socket (`_machine_temp`) as this machine's daemon would, so
    every frontend and `hmz exec` the test starts finds it there; its hosts are held on
    threads of this process, with the test's own home, so nothing forks and nothing outlives
    the test.
    """
    import socket

    from hmz.daemon import where
    from hmz.daemon.private import Private
    from hmz.rpc import PROTOCOL
    from hmz.runtime import Holding

    at = where.at()
    holding = where.holds(at)
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with where.reached(at) as reaching:
        listening.bind(reaching)
    listening.listen(64)
    where.wrote(
        at,
        {
            "pid": os.getpid(),
            "started": where.now(),
            "kind": "daemon",
            "protocol": PROTOCOL,
        },
    )
    held = Private(at, listening, Holding)
    held.start()
    try:
        yield held
    finally:
        held.close()
        os.close(holding)
