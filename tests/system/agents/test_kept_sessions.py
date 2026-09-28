"""One real session on every backend installed here, kept where humanize keeps it and nowhere else.

What `hmz.coganchor.backends` writes down as each CLI's sessions was read off a tracer watching
one turn, one more, and a fork of each CLI -- which is the most it can be: a release that starts
keeping something new somewhere new is a release that writes it into the person's own home
again, with nothing looking wrong. So this takes that turn again, on the real thing and `as
local`, with the session kept in a directory of the test's own, and holds three things to it:
the session is there, the conversation carries on from there -- a second turn, and a fork into a
second agent wherever the CLI forks, which is a second process reading it back -- and nothing of
it is anywhere under the CLI's own session paths at home.

That last is asked of the session rather than of the directories. A person's own sessions go on
being written under those paths while this runs -- this suite is often run from inside one -- so
a directory that changed says nothing; one naming this session, or holding its id, says all of
it.

Costs tokens and needs network access, so it only runs with ``pytest --run-agents``. A backend
this machine is not signed into, or whose catalogue names nothing it will run, is skipped as
`tests/system/agents/test_every_backend.py` skips one: an account is not humanize's to have.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import backends, providers
from hmz.coganchor.agents import Failed, driver

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.coganchor.agents import AgentBase, SessionBase

pytestmark = pytest.mark.agent

#: Where this machine keeps what each backend last said it runs as whoever is signed into it.
_KEPT = Path.home() / ".humanize" / "models"

#: One word, no tools: what is being tested is where a turn keeps itself, not what it says.
_ASKED = "Reply with exactly: OK"

#: Families a catalogue carries that no turn can be taken on, by the word their names hold.
_NOT_A_CHAT = (
    "embed",
    "rerank",
    "retriev",
    "guard",
    "safety",
    "load-test",
    "tts",
    "ocr",
)

#: What a turn fails for that is the account's to answer rather than anything humanize kept:
#: as :data:`hmz.coganchor.backends.FAULTS` names them.
_ACCOUNTS = frozenset({"throttled", "refused", "unlisted", "retired"})

#: How much of a file is read at a time, looking for a session id in it.
_CHUNK = 1 << 20


def _models(cli: str) -> list[tuple[str, str]]:
    """What to try running one backend at, best first, each at the least effort it takes."""
    try:
        said = json.loads((_KEPT / f"{cli}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip(f"nothing has asked {cli} what it runs on this machine")
    held = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    models = [
        one
        for one in cast("list[dict[str, Any]]", held.get("models") or [])
        if str(one.get("name") or "").strip()
        and not any(word in str(one["name"]).lower() for word in _NOT_A_CHAT)
    ]
    if not models:
        pytest.skip(f"{cli} has said nothing it runs on this machine")
    picked: list[tuple[str, str]] = []
    for one in models[:4]:
        efforts = cast("list[str]", one.get("efforts") or [])
        picked.append((str(one["name"]), str(efforts[-1]) if efforts else ""))
    return picked


def _installed(cli: str) -> bool:
    """Whether this backend is on this machine at all."""
    if cli == "dsh":
        import importlib.util

        return importlib.util.find_spec("deepseek_harness") is not None
    return shutil.which(cli) is not None


def _at_home(profile: backends.Profile) -> Iterator[Path]:
    """Every file under the CLI's own session paths, as its own home has them."""
    home = profile.directory()
    for said in profile.sessions:
        patterned = any(mark in said for mark in "*?[")
        for one in home.glob(said) if patterned else [home / said]:
            if one.is_file():
                yield one
            elif one.is_dir():
                yield from (inside for inside in one.rglob("*") if inside.is_file())


def _mentions(path: Path, said: bytes) -> bool:
    """Whether a file holds some bytes, read a piece at a time."""
    with contextlib.suppress(OSError), path.open("rb") as stream:
        carried = b""
        while chunk := stream.read(_CHUNK):
            if said in carried + chunk:
                return True
            carried = chunk[-len(said) :]
    return False


def _left_at_home(profile: backends.Profile, since: float, *said: str) -> list[str]:
    """What of one session is under the CLI's own session paths: named for it, or holding it."""
    found: list[str] = []
    for one in _at_home(profile):
        if any(word in str(one) for word in said):
            found.append(str(one))
            continue
        with contextlib.suppress(OSError):
            if one.stat().st_mtime >= since and any(
                _mentions(one, word.encode()) for word in said
            ):
                found.append(str(one))
    return found


def _kept(at: Path) -> list[str]:
    """Every file kept under a directory, relative to it."""
    return sorted(
        one.relative_to(at).as_posix() for one in at.rglob("*") if one.is_file()
    )


def _logged(profile: backends.Profile, at: Path, ident: str) -> list[Path]:
    """The session's own log under where it was kept, as the backend's `logs` name it."""
    return [
        one
        for glob in profile.logs
        for one in at.glob(glob.format(ident=ident))
        if one.is_file()
    ]


@pytest.mark.timeout(1500)
@pytest.mark.parametrize(
    "cli", [one.name for one in backends.PROFILES if one.sessions], ids=lambda one: one
)
def test_a_real_session_is_kept_where_humanize_keeps_it_and_nothing_of_it_at_home(
    cli: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not _installed(cli):
        pytest.skip(f"{cli} is not installed here")
    profile = backends.named(cli)
    assert profile is not None
    # A workspace no other run has ever had, so that anything named for it at home is this.
    workspace = tmp_path / f"kept-{uuid.uuid4().hex[:12]}"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    kept = tmp_path / "kept"
    since = time.time()
    agent, config = driver(cli)
    held: list[AgentBase] = []
    session: SessionBase | None = None
    refused: subprocess.CalledProcessError | None = None
    try:
        for model, effort in _models(cli):
            one = agent(config(model=model, effort=effort, provider=providers.LOCAL))
            one.keeps = kept
            held.append(one)
            session = one.new()
            try:
                session(_ASKED)
            except subprocess.CalledProcessError as why:
                refused = why
                continue
            refused = None
            break
        if refused is not None or session is None:
            pytest.skip(f"{cli} would not take a turn on this machine: {refused}")
        ident = session.id
        at = kept / cli
        assert held[-1].kept() == at
        assert _kept(at), f"{cli}: nothing was kept in {at}"
        if profile.logs:
            assert _logged(profile, at, ident), f"{cli}: no log of {ident} in {at}"

        # The conversation carries on from where it was kept: another turn in it, and -- where
        # the CLI forks -- a second agent's process reading it back.
        try:
            session(_ASKED)
        except Failed as why:
            # The account's -- a rate limit reached between two turns -- rather than where
            # the session was kept, which a refusal would be no answer about either way.
            if why.fault not in _ACCOUNTS:
                raise
            pytest.skip(f"{cli}'s account stopped taking turns after the first: {why}")
        forked, unforked = "", ""
        if session.forks:
            side = held[-1].clone()
            held.append(side)
            child = session.fork(into=side)
            try:
                child(_ASKED)
            except Failed as why:
                # The account's rather than the session's -- a quota spent, a model the fork
                # is refused -- which is the same answer the CLI gives a fork it was never
                # kept anywhere for. Anything else is where the fork looked, and is raised.
                if why.fault not in _ACCOUNTS:
                    raise
                unforked = str(why)
            else:
                forked = child.id
                assert side.keeps == kept
                if profile.logs:
                    assert _logged(profile, at, forked), (
                        f"{cli}: the fork was kept elsewhere"
                    )

        said = [one for one in (ident, forked, workspace.name) if one]
        assert not _left_at_home(profile, since, *said), (
            f"{cli}: this session reached the CLI's own home"
        )
        if unforked:
            pytest.skip(
                f"{cli} kept its session, and its account refused the fork: {unforked}"
            )
    finally:
        for one in held:
            with contextlib.suppress(Exception):
                one.stop()


def test_what_is_looked_for_at_home_is_every_session_path_there_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path the search above never reaches is a path it can never catch a session at."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    profile = backends.named("codex")
    assert profile is not None
    for name in ("sessions/2026/a.jsonl", "state_5.sqlite-wal", "config.toml"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")

    assert sorted(one.name for one in _at_home(profile)) == [
        "a.jsonl",
        "state_5.sqlite-wal",
    ]
