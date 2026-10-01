"""Where each CLI's column of the regression matrix is run: the account, the model, the effort.

A cell of the matrix is one feature driven through one CLI, and every cell of a column has to
be run somewhere that CLI will take a turn at all -- otherwise the column is a column of the
same refusal twenty times over, reported against twenty features that were never reached. So a
column's *place* is settled once, by asking: the candidates below are tried in order with one
word asked of each, and the first that answers is where every cell of that column runs.

**As local first.** A place with no account is the CLI as the person at this machine signed it
in, with nothing of humanize's standing between the two -- which is what the system tier is for.
Where that does not answer (a CLI installed but signed out, one that only ever runs through a
gateway), the column is run under one of the accounts this machine keeps in its own
`~/.humanize/providers`, *borrowed*: made again in the test's own `HUMANIZE_HOME` through the
SDK's accounts facade, out of the variables and files the machine's account holds, and taken
back off disk when the cell ends. Nothing of the machine's own store is written; it is read, and
only for the account a candidate names. And never an account signed in with a login whose token
refreshes itself: a copy of one is a second holder of the same sign-in, and the first of the two
to refresh has the vendor revoke the other -- the machine's own account. Such a candidate is
passed over, saying so.

A place that no candidate answers is a column that says why and skips, cell by cell: that is the
machine's account, not humanize, and a red matrix for somebody's expired subscription is a
matrix nobody reads.

The table is small on purpose and cheap on purpose: every model here is one of the cheapest its
CLI takes, at the least effort it takes, because every cell costs a turn or three.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor._lending import refreshing

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = [
    "CANDIDATES",
    "MACHINE",
    "Place",
    "borrowed",
    "installed",
    "settled",
]

#: Where this machine keeps the accounts humanize was given, read -- never written -- to
#: borrow one. The real home rather than `hmz.home()`, which the suite points at a directory
#: of its own for every test.
MACHINE = Path.home() / ".humanize" / "providers"

#: What this machine's CLIs last said they run as local, for a candidate list to fall back on.
_KEPT = Path.home() / ".humanize" / "models"

#: What a place is asked, and what it has to answer to be one.
_ASKED = "Reply with exactly: OK"
_ANSWERED = re.compile(r"\bOK\b")


@dataclass(frozen=True, slots=True)
class Place:
    """One place a turn of a CLI can be taken: the CLI, the account, the model, the effort.

    Attributes:
      cli: The backend, by the name `-a` gives it.
      provider: The account, or "" for the one this machine is already signed into.
      model: The model, in the CLI's (or the account's gateway's) own spelling.
      effort: The effort, or "" for the CLI's own default.
    """

    cli: str
    provider: str
    model: str
    effort: str = ""

    def spec(self, *, provider: str | None = None, model: str | None = None) -> str:
        """The place as `-a` and the SDK spell an agent: `cli[@provider]/model:effort`.

        Args:
          provider: Another account to spell it under, or None for this one's.
          model: Another model to spell it at, or None for this one's.
        """
        from hmz.coganchor import backends

        account = self.provider if provider is None else provider
        at = f"@{account}" if account else ""
        return (
            f"{self.cli}{at}/{self.model if model is None else model}"
            f":{backends.written(self.effort)}"
        )

    def __str__(self) -> str:
        return self.spec() + ("" if self.provider else " (as local)")


def _at(cli: str, provider: str, model: str, effort: str = "low") -> Place:
    return Place(cli, provider, model, effort)


#: Each CLI's places, best first. As local ahead of any account, and the cheapest model the
#: CLI or the account's gateway serves ahead of anything better. An account named here is one
#: this machine keeps under `MACHINE`; one it does not keep is passed over, saying so.
#:
#: Where a CLI's own catalogue is on this machine, its first few chat models are tried after
#: these as local, which is `tests/system/agents/test_every_backend.py`'s own fallback: a
#: model id written down here goes stale on the vendor's schedule, and a column should not go
#: dark because of it.
CANDIDATES: dict[str, tuple[Place, ...]] = {
    "claude": (
        _at("claude", "", "claude-haiku-4-5-20251001"),
        _at("claude", "nvidia", "azure/anthropic/claude-haiku-4-5"),
    ),
    "agy": (
        _at("agy", "", "gemini-3.8-flash-low"),
        _at("agy", "nvidia", "gemini-3.8-flash-low"),
    ),
    "codex": (
        _at("codex", "", "gpt-5.5"),
        _at("codex", "", "gpt-5.6-luna"),
        _at("codex", "nvidia", "azure/openai/gpt-5.4-mini"),
    ),
    "dsh": (
        _at("dsh", "", "deepseek-v4-flash", "off"),
        _at("dsh", "nvidia", "nvidia/deepseek-ai/deepseek-v4-flash", "off"),
    ),
    "grok": (
        _at("grok", "", "grok-4.7"),
        _at("grok", "nvidia", "azure/openai/gpt-5.4-mini"),
    ),
    "kimi": (
        _at("kimi", "", "kimi-code/k3"),
        _at("kimi", "nvidia", "__kimi_env_model__"),
    ),
    "pi": (
        _at("pi", "", "openai-codex/gpt-5.4-mini"),
        _at("pi", "nvidia", "nvgw/nvidia/minimaxai/minimax-m3"),
    ),
    "qwen": (
        _at("qwen", "", "qwen3-coder-flash"),
        _at("qwen", "nvidia", "azure/openai/gpt-5.4-mini"),
    ),
    "opencode": (
        _at("opencode", "", "opencode/nemotron-3.5-lightning-free"),
        _at("opencode", "", "opencode/big-pickle"),
        _at("opencode", "nvidia", "nvgw/nvidia/minimaxai/minimax-m3"),
        _at("opencode", "nvidia", "anthropic/claude-haiku-4-5"),
    ),
    "mimo": (
        _at("mimo", "", "xiaomi/mimo-v2.5"),
        _at("mimo", "nvidia", "nvgw/nvidia/minimaxai/minimax-m3"),
        _at("mimo", "nvidia", "anthropic/claude-haiku-4-5"),
    ),
    "cursor-agent": (
        _at("cursor-agent", "", "auto", ""),
        _at("cursor-agent", "nvidia", "auto", ""),
    ),
    # Its own fast model as local, which takes no rung; then a gateway added to it, whose
    # models are named under the provider it was added as.
    "mcode": (
        _at("mcode", "", "minimax/MiniMax-M2.7-highspeed", ""),
        _at(
            "mcode", "nvidia", "custom_provider:gateway/nvidia/minimaxai/minimax-m3", ""
        ),
    ),
}

#: Families a catalogue carries that no turn can be taken on, by a word their names hold.
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

#: How many of a CLI's own catalogue to try after the table, as local.
_TRIES = 3


def installed(cli: str) -> bool:
    """Whether this backend is on this machine at all, looked for where humanize looks."""
    if cli == "dsh":
        import importlib.util

        return importlib.util.find_spec("deepseek_harness") is not None
    from hmz.coganchor import backends

    return backends.program(cli) is not None


def _catalogued(cli: str) -> list[Place]:
    """The first few chat models this machine's own catalogue of a CLI names, as local."""
    try:
        said = json.loads((_KEPT / f"{cli}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    held = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    found: list[Place] = []
    for one in cast("list[dict[str, Any]]", held.get("models") or []):
        name = str(one.get("name") or "").strip()
        if not name or any(word in name.lower() for word in _NOT_A_CHAT):
            continue
        efforts = cast("list[str]", one.get("efforts") or [])
        found.append(Place(cli, "", name, str(efforts[-1]) if efforts else ""))
        if len(found) == _TRIES:
            break
    return found


@contextlib.contextmanager
def borrowed(cli: str, theirs: str, ours: str = "") -> Generator[str]:
    """Makes one of this machine's accounts again in the test's own home, for as long as held.

    Made through the SDK's accounts facade out of what the machine's account says it is --
    the way it was made by, its variables, its arguments -- and the files its login left,
    copied beside it. Taken back off disk however the block ends, and checked to be gone: a
    borrowed account is somebody's live credential, and the directory it was borrowed into is
    kept by pytest for the next three runs to read.

    Args:
      cli: The backend.
      theirs: The account's name on this machine.
      ours: What to call it in the test's home, or "" for the same name.

    Yields:
      The name it is under in the test's home.

    Raises:
      LookupError: If this machine keeps no account of that name for that backend, or keeps
        one whose sign-in refreshes itself, which is never copied.
    """
    from hmz import home
    from hmz.sdk import Hmz

    source = MACHINE / cli / theirs
    try:
        held = cast(
            "dict[str, Any]",
            json.loads((source / "provider.json").read_text(encoding="utf-8")),
        )
    except (OSError, ValueError) as missing:
        raise LookupError(
            f"this machine keeps no {cli} account {theirs!r}"
        ) from missing
    # Its credential roots, which is where a login leaves a sign-in -- not `provider.json`,
    # whose variables are copied as variables and never refresh themselves.
    if lent := refreshing(str(source / root) for root in ("home", "config", "user")):
        raise LookupError(
            f"this machine's {cli} account {theirs!r} signs in with a token that refreshes "
            f"itself ({', '.join(sorted(Path(one).name for one in lent))}), and a borrowed "
            "copy refreshing apart from it would get it revoked"
        )
    name = ours or theirs
    # Checked before anything is written or registered to be deleted: what is removed below
    # is a recursive remove, and a run whose home had become the real one would remove the
    # very account it set out to borrow.
    assert home().resolve() != MACHINE.parent.resolve(), (
        "HUMANIZE_HOME is this machine's own; a borrowed account would be the original"
    )
    made = Hmz().accounts.write(
        cli,
        name,
        way=str(held.get("way") or ""),
        env=cast("dict[str, str]", held.get("env") or {}),
        args=tuple(cast("list[str]", held.get("args") or [])),
    )
    try:
        for one in source.iterdir():
            if one.name == "provider.json":
                continue
            if one.is_dir():
                shutil.copytree(one, made.at / one.name, dirs_exist_ok=True)
            else:
                shutil.copy2(one, made.at / one.name)
        yield name
    finally:
        shutil.rmtree(made.at, ignore_errors=True)
        assert not made.at.exists(), f"a borrowed account is still on disk at {made.at}"


def _answers(place: Place) -> str:
    """Asks one place for a word, and says why it is not a place -- or "" when it is.

    Asked of the driver itself rather than through a flow, as
    `tests/system/agents/test_every_backend.py` asks: this is the cheapest turn there is, and
    what it decides is only where the cells go.
    """
    from hmz.coganchor.agents import driver

    agent, config = driver(place.cli)
    try:
        one = agent(
            config(model=place.model, effort=place.effort, provider=place.provider)
        )
    except (ValueError, KeyError) as refused:
        return f"{place} cannot be configured: {refused}"
    session = None
    try:
        session = one.new()
        said = session(_ASKED)
    except OSError as refused:
        return f"{place} would not start: {refused}"
    except subprocess.CalledProcessError as refused:
        # What the CLI said, which is after the command line and its exit status.
        told = str(refused).partition(" exit status ")[2] or str(refused)
        return f"{place} would not take a turn: {told.strip()[:400]}"
    finally:
        if session is not None:
            with contextlib.suppress(Exception):
                session.close()
        with contextlib.suppress(Exception):
            one.stop()
    if not _ANSWERED.search(said):
        return f"{place} answered {said[:60]!r} to {_ASKED!r}"
    return ""


#: What has been settled this run, by CLI and by whether an account was asked for: the
#: place, or why there is none. Per process: a run grouped by CLI -- which is how
#: `tests/conftest.py` has xdist hand these out -- asks each CLI once.
_SETTLED: dict[tuple[str, bool], Place | str] = {}


def settled(cli: str, *, account: bool = False) -> Place | str:
    """Where one CLI's cells run, asked once a run: the place, or why there is none.

    Args:
      cli: The backend.
      account: Whether the place has to be one of this machine's accounts -- which is what the
        cell about named accounts runs at -- rather than the column's own, which is as local
        wherever that answers.

    Returns:
      The first candidate that answered, or every reason each of them gave for not.
    """
    key = (cli, account)
    if key in _SETTLED:
        return _SETTLED[key]
    tried: list[str] = []
    candidates = [one for one in CANDIDATES.get(cli, ()) if one.provider or not account]
    if not account:
        # As local ahead of any account, the catalogue's own models among them.
        ahead = [one for one in candidates if not one.provider]
        behind = [one for one in candidates if one.provider]
        candidates = [*ahead, *(o for o in _catalogued(cli) if o not in ahead), *behind]
    found: Place | str = ""
    for place in candidates:
        if place.provider:
            try:
                with borrowed(cli, place.provider):
                    why = _answers(place)
            except LookupError as missing:
                why = str(missing)
        else:
            why = _answers(place)
        if not why:
            found = place
            break
        tried.append(why)
    if not found:
        found = "; ".join(tried) or f"no place is written down for {cli}"
    _SETTLED[key] = found
    return found
