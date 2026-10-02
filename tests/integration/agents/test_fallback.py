"""How many times over a failed turn is taken again at the place it is running at.

A provider goes down -- a key revoked, a gateway refusing, a subscription out of quota -- and
what a flow sees is a turn that failed. How many times over the turn is taken again before it
leaves is a thing about the place it is running at rather than about the credentials, written in
`hmz.coganchor.fallbacks` beside the chain of places it goes to afterwards. What is checked here
is the trying again: that it is taken in the conversation that was running, as many times as the
place asked and the failure is worth, and that an agent with nowhere to go still fails the way
it always did. Where it goes afterwards is `test_agent_fallback.py`'s. An account no longer
names an account to carry on under: what goes down is a place, and a place is what answers it.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, fallbacks, providers
from hmz.coganchor.agents import AgentConfig
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two accounts for one backend: one that is down, and one that answers."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    # The stand-in agent's class names the backend `shell`, so that is the backend these are
    # accounts of: added as a CLI of your own, which is a backend like any other -- and added
    # as what it runs, since that is the only name an added CLI may answer to.
    backends.remember("shell", ["shell"])
    providers.add("shell", "main", env={"DOWN": "1", "WHOSE": "main"})
    providers.add("shell", "spare", env={"WHOSE": "spare"})


def _agent(provider: str) -> ShellAgent:
    """An agent whose turns run a shell script, as whichever account it was given."""
    return ShellAgent(AgentConfig(model="m", effort="high", provider=provider))


def test_a_turn_with_nowhere_to_fall_back_to_fails_as_it_always_did(
    accounts: None,
) -> None:
    """No tries, no chain: a failed turn is a failed turn."""
    with pytest.raises(subprocess.CalledProcessError):
        _agent("main").new()(_FLAKY_AS_SCRIPT)


def test_a_place_is_tried_again_before_the_turn_leaves_it(
    accounts: None, tmp_path: Path
) -> None:
    """A gateway that answered 503 is the same call away from working, so it gets one."""
    fallbacks.retrying("shell@main/m", 2, "none", 0.0)
    tally = tmp_path / "tries.txt"
    agent = _agent("main")

    with pytest.raises(subprocess.CalledProcessError):
        agent.new()(_COUNTING.format(at=tally))

    # Three tries under the account that was down -- the first and the two it was given --
    # and never one under another account of it: an account names nowhere to carry on to.
    assert tally.read_text().split() == ["main", "main", "main"]


def test_the_tries_stop_when_the_time_they_were_given_is_spent(
    accounts: None, tmp_path: Path
) -> None:
    """Checked before the wait, so a turn is never started knowing it is already past."""
    fallbacks.retrying("shell@main/m", 5, "constant", 0.5)
    tally = tmp_path / "tries.txt"

    with pytest.raises(subprocess.CalledProcessError):
        _agent("main").new()(_COUNTING.format(at=tally))

    # One wait of a second is already more than the half-second it was given, so the first
    # try is the only one taken.
    assert tally.read_text().count("main") == 1


def test_an_agent_as_this_machine_is_signed_in_is_on_an_account_too(
    accounts: None,
) -> None:
    """One nobody made: the CLI as it is already run."""
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    assert agent.node().name == ""  # the account this machine is signed into
    assert not fallbacks.tried(agent.spec).tries  # nothing written down, so tried once
    # Which is not an account anything is run *under*: nothing is added to the environment,
    # nothing is taken out of it, and no path is answered by another.
    assert agent.provider is None
    assert agent.node().swaps() == ()
    assert agent.new()("echo here") == "here"


def test_the_place_an_unaccounted_agent_runs_at_is_tried_again_too(
    accounts: None, tmp_path: Path
) -> None:
    """The tries are written against the place, and a place with no account is a place."""
    fallbacks.retrying("shell/m", 2, "none", 0.0)
    tally = tmp_path / "tries.txt"

    with pytest.raises(subprocess.CalledProcessError):
        ShellAgent(AgentConfig(model="m", effort="high")).new()(
            _COUNTING.format(at=tally)
        )

    assert tally.read_text().split() == ["nobody"] * 3  # the first and the two given


def test_an_account_says_nothing_about_where_a_turn_goes_when_it_fails(
    accounts: None, tmp_path: Path
) -> None:
    """A `fallback` an older humanize wrote on an account is read past, and walks nowhere."""
    import json

    main = providers.find("shell", "main")
    assert main is not None
    held = json.loads((main.at / "provider.json").read_text())
    (main.at / "provider.json").write_text(json.dumps(held | {"fallback": "spare"}))
    tally = tmp_path / "tries.txt"

    with pytest.raises(subprocess.CalledProcessError):
        _agent("main").new()(_COUNTING.format(at=tally))

    assert tally.read_text().split() == ["main"]
    assert not hasattr(providers, "chain")
    assert not hasattr(providers, "points")


def test_the_waits_are_the_ones_everybody_uses() -> None:
    """Each under the name it is known by, and none of them invented here."""
    waits = fallbacks.waits
    assert [waits("constant", at) for at in (1, 2, 3, 4)] == [0.0, 1.0, 1.0, 1.0]
    assert [waits("linear", at) for at in (1, 2, 3, 4)] == [0.0, 1.0, 2.0, 3.0]
    assert [waits("exponential", at) for at in (1, 2, 3, 4)] == [0.0, 1.0, 2.0, 4.0]
    assert [waits("fibonacci", at) for at in (1, 2, 3, 4, 5)] == [
        0.0,
        1.0,
        1.0,
        2.0,
        3.0,
    ]
    assert [waits("none", at) for at in (1, 2, 3)] == [0.0, 0.0, 0.0]
    # Full jitter is anywhere up to the exponential wait, which is what keeps a flow's agents
    # from all coming back on the same second.
    assert all(0.0 <= waits("exponential-jitter", 4) <= 4.0 for _ in range(20))
    # However far it climbs, no single wait is longer than a turn.
    assert waits("exponential", 40) == fallbacks.CEILING
    # A policy nobody recognises waits the way the default does rather than not at all.
    assert 0.0 <= waits("nonesuch", 3) <= 2.0


def test_every_kind_of_failure_has_an_answer_and_nothing_else_does() -> None:
    """One row per kind, and the kind nobody recognised is not among them: it is the default."""
    assert {one.fault for one in fallbacks.ANSWERS} == set(backends.FAULTS)

    owed = fallbacks.answers("nothing-is-called-this")
    assert owed.about == "failed"  # which is how a failed turn has always been narrated
    assert (owed.tries, owed.held, owed.policy, owed.least) == (0, False, "", 0.0)


def test_a_kind_may_floor_the_goes_a_place_asked_for_and_may_take_them_away() -> None:
    """A floor is what a failure worth another go needs; a ceiling would overrule a person."""
    # Three goes at a store another turn had open, whether or not anybody asked for any.
    assert fallbacks.answers("contended").tries == fallbacks._BUSY
    assert not fallbacks.answers("contended").held
    # And none at all for a credential that was refused, however many the place asked for.
    assert fallbacks.answers("refused").held


def test_the_least_a_rate_limit_waits_is_longer_than_a_backoff_starts_at() -> None:
    """The first second of an exponential backoff is a second the service already refused."""
    assert fallbacks.answers("throttled").least == fallbacks.THROTTLED
    assert fallbacks.waits("exponential", 2) < fallbacks.THROTTLED
    # And never longer than a wait may be, however the shape of it is arrived at.
    assert fallbacks.THROTTLED <= fallbacks.CEILING


def test_a_policy_that_is_not_one_is_refused_where_it_is_written(
    accounts: None,
) -> None:
    """A setting to correct, rather than a turn that finds out about it hours in."""
    with pytest.raises(ValueError, match="is not a retry policy"):
        fallbacks.retrying("shell/m", 1, "nonesuch", 0.0)
    with pytest.raises(ValueError, match="not debts"):
        fallbacks.retrying("shell/m", -1, "constant", 0.0)


#: The stand-in as one line a shell session runs, since that agent takes its prompt as a
#: script: the same two-branch behaviour, written where the prompt goes.
_FLAKY_AS_SCRIPT = (
    'if [ -n "$DOWN" ]; then echo "the account is down" >&2; exit 1; fi; '
    'echo "${WHOSE:-nobody}"'
)

#: The same, writing down which account each try was taken under. A turn under the account
#: this machine is signed into has no `WHOSE`, and fails for having none.
_COUNTING = (
    'echo "${{WHOSE:-nobody}}" >> {at}; '
    'if [ -n "$DOWN" ] || [ -z "$WHOSE" ]; then echo "down" >&2; exit 1; fi; '
    'echo "${{WHOSE}}"'
)


def test_a_turn_stopped_between_tries_is_stopped(accounts: None) -> None:
    """A run ended by hand is ended, not carried on at the next place along.

    Esc reaches an agent whose turn is in the wait between two tries, and that is not a
    moment to go on from.
    """
    import threading

    from hmz.coganchor.agents import Stopped

    fallbacks.retrying("shell@main/m", 3, "constant", 0.0)
    fallbacks.points("shell@main/m", ["shell@spare/m"])
    agent = _agent("main")
    session = agent.new()
    threading.Timer(0.3, agent.stop).start()

    # The first try takes a second and fails; the stop lands while it is running, and the
    # try after it is where the loop finds out.
    with pytest.raises(Stopped):
        session('sleep 1; echo "the account is down" >&2; exit 1')

    assert agent.stands_in() is not None  # somewhere to go, and it never went there
    assert agent.provider is not None
    assert agent.provider.name == "main"
