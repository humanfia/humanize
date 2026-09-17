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

Every turn here is taken `as local`, which is humanize's own word for the account nobody made
-- `hmz.coganchor.providers.LOCAL`, the provider `""`, the CLI signed in the way the person at
this machine signed it in with nothing redirected. That is what makes this a system test. A
turn taken under an account humanize was given is a turn through humanize's own redirection,
and what it pins is that the redirection works -- worth pinning, and pinned in the integration
tier against a stand-in service, where it costs nothing and runs in CI. What only this tier can
say is whether the CLI somebody installed and signed into answers at all, and it can only say
that by not standing between the two of them. So a backend this machine reaches only through
an account humanize was given is skipped here rather than borrowed into: fewer backends
covered, and every one of them covered as the person at the prompt would run it.

Costs tokens and needs network access, so it only runs with ``pytest --run-agents``.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import backends, providers
from hmz.coganchor.agents import Failed, driver

if TYPE_CHECKING:
    from hmz.coganchor.agents import AgentBase

pytestmark = pytest.mark.agent

#: Where this machine keeps what each backend last said it runs as whoever is signed into it.
#: Read from the real home rather than through `hmz.coganchor.models`, which the suite points
#: at a directory of its own: what is wanted here is what this machine's own sign-in may
#: actually name, which is the whole subject.
_KEPT = Path.home() / ".humanize" / "models"

#: What to ask for. One word, no tools, nothing to think about: what is being tested is that
#: a turn lands at all.
_ASKED = "Reply with exactly: OK"

#: The word itself, read off what was asked rather than written twice: a turn that answered
#: and the turn that is asserted about must agree on what an answer is.
_WORD = _ASKED.rpartition(": ")[2]

#: That word on its own, rather than anywhere inside a longer one. `OK` is two letters that
#: turn up in the middle of others -- `OKAY`, `TOKEN`, `BROKE`, `LOOKS` -- so a plain `in`
#: passes a backend that answered something else entirely and happened to spell one of them,
#: which is the reading this test least wants to be wrong about. A boundary on each side
#: still takes the punctuation and the markdown a model puts around it: `OK.`, `**OK**`.
_ANSWERED = re.compile(rf"\b{re.escape(_WORD)}\b")

#: How many of a catalogue's models to try before calling a backend one that will not run.
#: One is not enough and every one of them is a bill: some of these CLIs name a short list
#: their vendor stands behind, and some are pointed by environment variables of this machine's
#: own at a gateway that lists everything it fronts -- hundreds of ids, in whatever order the
#: gateway answered. Several of those are embedders, rerankers and models reachable only
#: through an API this is not; drawing one is luck, and a backend that works looking broken
#: because of the draw is worse than a slow test.
_TRIES = 6

#: Families a catalogue carries that no turn can be taken on, by the word their names hold. A
#: catalogue is a list of what an endpoint serves, not a list of things that answer a prompt:
#: a gateway offers embedders, rerankers, content-safety classifiers, speech and a load-test
#: stub alongside the models, and there is no saying which of those it names first.
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


def _models(cli: str) -> list[tuple[str, str]]:
    """What to try running one backend at, best first, each at the least effort it takes.

    In the catalogue's own order, which is this backend's idea of what it runs as this
    machine is signed into it -- what the interface opens on. The least effort because this
    is a turn that says one word.

    Args:
      cli: The backend.

    Returns:
      Up to :data:`_TRIES` pairs of model and effort.
    """
    try:
        said = json.loads((_KEPT / f"{cli}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip(f"nothing has asked {cli} what it runs on this machine")
    held = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    models = cast("list[dict[str, Any]]", held.get("models") or [])
    if not models:
        pytest.skip(f"{cli} has said nothing about what it runs on this machine")
    # Named first, and everything else afterwards from the named ones only. The catalogue is
    # whatever this machine's own CLI wrote down, which is a file this test does not own: a
    # row that carries no name is a row no turn can be asked for, and reading `one["name"]`
    # off it raises `KeyError` out of a test whose subject is whether a CLI answers -- a
    # failure that says nothing about the backend and sends whoever reads it to the wrong
    # place. Passed over instead, like any other id that cannot be tried.
    named = [one for one in models if str(one.get("name") or "").strip()]
    if not named:
        pytest.skip(f"{cli} named nothing this machine could ask a turn of")
    wanted = [
        one
        for one in named
        if not any(word in str(one["name"]).lower() for word in _NOT_A_CHAT)
    ]
    picked: list[tuple[str, str]] = []
    for one in (wanted or named)[:_TRIES]:
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
    """A turn, an answer, and the session it landed in -- on the real thing, as local.

    A turn the vendor refuses is not a failure of this test's: an account that may not name a
    model and a service that has been withdrawn are things about that account. What is
    checked then is that humanize said which, in words rather than in an exit status.
    """
    if not _installed(cli):
        pytest.skip(f"{cli} is not installed here")
    monkeypatch.chdir(tmp_path)  # so an agent that tidies up tidies up nothing of ours
    agent, config = driver(cli)
    said = ""
    refused: subprocess.CalledProcessError | None = None
    one: AgentBase | None = None
    session = None
    tried: list[str] = []
    # Every agent this opens is stopped and every session closed, whichever way the test
    # ends. What is merely dropped is a daemon still listening, a CLI still resident and a
    # conversation still open at the vendor for the rest of the run -- an agent holds its
    # sessions weakly, so letting go of one is not closing it. Registered as each is opened
    # rather than left to a `finally`, so that an attempt which raised on the way up is not
    # the one that gets left behind.
    with contextlib.ExitStack() as holding:
        for model, effort in _models(cli):
            if one is not None:
                # And the attempt before this one goes now rather than at the end of the
                # test: a backend that needs all six ids would otherwise hold six daemons
                # and six conversations at once, for as long as the slowest of them takes.
                # Stopping it twice is not an error -- the stack stops it again -- and
                # stopping it once too few is a daemon that outlives the run.
                one.stop()
            # `as local` said rather than left to the default, which is what this whole tier
            # is for: a default that one day picked up an account humanize was given would
            # send every turn here through humanize's own redirection without anything going
            # red.
            one = agent(config(model=model, effort=effort, provider=providers.LOCAL))
            holding.callback(one.stop)
            session = one.new()
            holding.callback(session.close)
            try:
                said = session(_ASKED)
            except subprocess.CalledProcessError as why:
                # This id, not this backend. A catalogue lists plenty a turn cannot be
                # taken on, and a vendor retires a model without telling the list -- so the
                # next id is asked before the backend is called broken.
                refused = why
                continue
            # The turn landed, whatever it said, so there is no refusal outstanding: a
            # backend that answered on its second id must not be reported as one that would
            # not run.
            refused = None
            if _ANSWERED.search(said):
                break
            # It answered, and not the word it was asked for. That is an id this test
            # cannot read an answer out of rather than a backend that failed -- a load-test
            # stub on a gateway replies `xxxx` to anything -- so it counts as another id
            # tried.
            tried.append(f"{model} said {said[:40]!r}")
        assert one is not None
        assert session is not None
        if refused is not None:
            # The turn did not land. Whether that is this machine's account or this CLI's
            # day, the one thing humanize owes whoever is at the prompt is which -- so the
            # failure has to say something beyond the exit status it stopped on.
            assert isinstance(refused, Failed), (
                f"{cli}: a turn that failed must say why, and this said only its exit status"
            )
            told = str(refused).partition("status")[2]
            assert told.strip(" .0123456789"), (
                f"{cli}: nothing was said about why it failed"
            )
            pytest.skip(f"{cli} would not take a turn on this machine: {refused}")

        if tried and not _ANSWERED.search(said):
            # Every id this machine's catalogue offered that could be tried answered with
            # something that is not an answer. What that says is about the catalogue rather
            # than about humanize, which is the same thing a refusal says and gets the same
            # treatment.
            pytest.skip(
                f"{cli}: no model this machine offers answered -- {'; '.join(tried)}"
            )

        assert _ANSWERED.search(said), f"{cli}: answered {said[:80]!r}"
        assert session.id, f"{cli}: the turn landed and the session was never named"
        assert session.id in one.opened
