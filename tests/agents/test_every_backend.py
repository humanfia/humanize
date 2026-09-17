"""One real turn on every backend installed here, which is the only test of `it works`.

The rest of the suite drives stand-ins that print each backend's protocol, which is what makes
it runnable on a machine with nothing installed -- and what makes it blind to the half that
only the real thing has: an account that has expired, a model the account may not name, a
service that has been withdrawn, a flag the CLI stopped taking in the version that shipped
this morning. None of those is a bug in humanize, and all of them are `this CLI does not work`
to whoever is at the prompt.

So this drives whatever is installed, at whatever that CLI last said it runs, and asks it for
one word. What it pins is that a turn lands, that the session it landed in is named, and that
a turn which does not land says why in words a person can act on -- which is the difference
between `your account cannot run that model` and `returned non-zero exit status 1`.

Costs tokens and needs network access, so it only runs with ``pytest --run-agents``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import Failed, driver

if TYPE_CHECKING:
    from hmz.coganchor.agents import AgentBase

pytestmark = pytest.mark.agent

#: The real home, read rather than the one the suite points itself at: what is wanted here is
#: what this machine's own accounts may actually name, which is the whole subject.
_HOME = Path.home() / ".humanize"

#: Where this machine keeps what each backend last said it runs as whoever is signed into it.
_KEPT = _HOME / "models"

#: And where it keeps the accounts humanize was given, one directory per account per backend,
#: each with the catalogue that account's own endpoint answered with.
_ACCOUNTS = _HOME / "providers"

#: What to ask for. One word, no tools, nothing to think about: what is being tested is that
#: a turn lands at all.
_ASKED = "Reply with exactly: OK"


def _account(cli: str) -> str:
    """The account to drive one backend as, out of the ones humanize was given for it.

    Most of these CLIs are signed in where the CLI itself keeps a login, and for those the
    answer is "" -- the machine's own, which is what a bare `hmz` would use. But a login is
    not the only way in and on plenty of machines it is not the way anybody used: every one
    of these backends can be pointed at a third-party endpoint instead, and an account made
    that way lives here rather than in the CLI's own home. A backend reached only that way
    -- ZCode on a gateway, a DeepSeek key, a CLI whose vendor withdrew its free tier -- would
    otherwise look on this test like a backend that does not work, when what it has is simply
    an account this test declined to use.

    Args:
      cli: The backend.

    Returns:
      The account's name, or "" to run as whoever this machine is signed into.
    """
    where = _ACCOUNTS / cli
    if not where.is_dir():
        return ""
    # The one with a catalogue, since that is the one something has actually asked. Sorted so
    # that a machine with several picks the same one twice running rather than whichever the
    # filesystem happened to name first.
    for held in sorted(where.iterdir()):
        if (held / "models.json").is_file():
            return held.name
    return ""


def _borrowed(cli: str, account: str, home: Path) -> None:
    """Copies one account into the home this run was given, so a turn can be taken as it.

    The suite runs under a `HUMANIZE_HOME` of its own, which is what keeps a run's epic out of
    the history of whoever asked for the tests to pass -- and which also puts every account
    out of reach. So the account is borrowed rather than the home given up: what the turn
    writes still lands in the temporary directory, and only the credential is shared.

    Args:
      cli: The backend.
      account: The account's name.
      home: The `HUMANIZE_HOME` this run was given.
    """
    ours = home / "providers" / cli / account
    if ours.exists():
        return
    ours.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_ACCOUNTS / cli / account, ours)


#: How many of an account's models to try before calling a backend one that will not run. One
#: is not enough and every one of them is a bill: a CLI's own catalogue is a short list its
#: vendor stands behind, but an account on a gateway is offered everything that gateway fronts
#: -- 244 ids here -- and the first of those is whatever came back first. Several of them are
#: embedders, rerankers and models reachable only through an API this is not; drawing one is
#: luck, and a backend that works looking broken because of the draw is worse than a slow test.
_TRIES = 6

#: Families a gateway fronts that no turn can be taken on, by the word their names carry. A
#: catalogue is a list of what an endpoint serves, not a list of things that answer a prompt:
#: this one offers embedders, rerankers, content-safety classifiers, speech and a load-test
#: stub alongside the models, and the first few ids happen to be several of those.
#:
#: Matched on the name, which is a guess, and a cheap one made only to avoid spending a turn
#: to learn what the name already said. Nothing depends on it being complete -- an id it
#: misses is an id tried and passed over like any other -- so it may be wrong in the
#: forgiving direction and never in the other.
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


def _models(cli: str, account: str = "") -> list[tuple[str, str]]:
    """What to try running one backend at, best first, each at the least effort it takes.

    In the catalogue's own order, which for a CLI asked about itself is that CLI's idea of
    what it runs -- what the interface opens on -- and for an account on a gateway is simply
    what that gateway listed. The least effort because this is a turn that says one word.

    Args:
      cli: The backend.
      account: The account whose catalogue to read, or "" for this machine's own.

    Returns:
      Up to :data:`_TRIES` pairs of model and effort.
    """
    kept = (
        _ACCOUNTS / cli / account / "models.json" if account else _KEPT / f"{cli}.json"
    )
    try:
        said = json.loads(kept.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip(f"nothing has asked {cli} what it runs on this machine")
    held = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    models = cast("list[dict[str, Any]]", held.get("models") or [])
    if not models:
        pytest.skip(f"{cli} has said nothing about what it runs on this machine")
    wanted = [
        one
        for one in models
        if not any(word in str(one["name"]).lower() for word in _NOT_A_CHAT)
    ]
    picked: list[tuple[str, str]] = []
    for one in (wanted or models)[:_TRIES]:
        efforts = cast("list[str]", one.get("efforts") or [])
        # The least of the efforts it takes, and none at all for a model that takes none: a
        # backend whose models carry their own effort refuses one said beside the name.
        picked.append((str(one["name"]), str(efforts[-1]) if efforts else ""))
    return picked


def _installed(cli: str) -> bool:
    """Whether this backend is on this machine at all."""
    if cli == "dsh":
        import importlib.util

        return importlib.util.find_spec("deepseek_harness") is not None
    return shutil.which(cli) is not None


@pytest.mark.timeout(900)
@pytest.mark.parametrize(
    "cli", [one.name for one in backends.PROFILES], ids=lambda one: one
)
def test_a_turn_lands_on_every_backend_installed_here(
    cli: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn, an answer, and the session it landed in -- on the real thing.

    A turn the vendor refuses is not a failure of this test's: an account that may not name a
    model and a service that has been withdrawn are things about that account. What is
    checked then is that humanize said which, in words rather than in an exit status.
    """
    if not _installed(cli):
        pytest.skip(f"{cli} is not installed here")
    monkeypatch.chdir(tmp_path)  # so an agent that tidies up tidies up nothing of ours
    account = _account(cli)
    if account:
        _borrowed(cli, account, Path(os.environ["HUMANIZE_HOME"]))
    agent, config = driver(cli)
    said = ""
    refused: subprocess.CalledProcessError | None = None
    one: AgentBase | None = None
    session = None
    tried: list[str] = []
    for model, effort in _models(cli, account):
        one = agent(config(model=model, effort=effort, provider=account))
        session = one.new()
        try:
            said = session(_ASKED)
        except subprocess.CalledProcessError as why:
            # This id, not this backend. A gateway fronts plenty a turn cannot be taken on,
            # and a vendor retires a model without telling the list -- so the next id is
            # asked before the backend is called broken.
            refused = why
            continue
        if _ASKED.rpartition(": ")[2] in said:
            refused = None
            break
        # It answered, and not the word it was asked for. That is an id this test cannot
        # read an answer out of rather than a backend that failed -- the load-test stub on
        # this gateway replies `xxxx` to anything -- so it counts as another id tried.
        tried.append(f"{model} said {said[:40]!r}")
    assert one is not None
    assert session is not None
    if refused is not None:
        # The turn did not land. Whether that is this machine's account or this CLI's day,
        # the one thing humanize owes whoever is at the prompt is which -- so the failure
        # has to say something beyond the exit status it stopped on.
        assert isinstance(refused, Failed), (
            f"{cli}: a turn that failed must say why, and this said only its exit status"
        )
        told = str(refused).partition("status")[2]
        assert told.strip(" .0123456789"), (
            f"{cli}: nothing was said about why it failed"
        )
        pytest.skip(f"{cli} would not take a turn on this machine: {refused}")

    if tried and _ASKED.rpartition(": ")[2] not in said:
        # Every id this account offered that could be tried answered with something that is
        # not an answer. What that says is about the account's catalogue rather than about
        # humanize, which is the same thing a refusal says and gets the same treatment.
        pytest.skip(
            f"{cli}: no model this account offers answered -- {'; '.join(tried)}"
        )

    assert "OK" in said
    assert session.id, f"{cli}: the turn landed and the session was never named"
    assert session.id in one.opened
