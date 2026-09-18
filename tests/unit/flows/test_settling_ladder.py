"""The rule a place is settled onto an agent by, read on its own, apart from any flow.

Settling is one line of :func:`hmz.flows.driving.runs_at` and the whole of what a flow's
declaration comes to: two answers go in -- what the agent already carries and what the place
declares -- and the narrower of them comes out, so that a flow calling one somebody else wrote
cannot have its `read-only` undone by a callee that declared nothing.

What is new here is that a config may carry no answer at all. `UNSAID` is not a rung on the
ladder but the absence of one: humanize saying nothing to the CLI about what its agent may do,
which leaves the agent wherever that CLI's own headless run leaves it. It has to sit looser
than every rung, or the tighten-only rule would read silence as a tightening and a place
declaring nothing would start settling something.

Tested here rather than through a flow because there is no agent, no process and no CLI in any
of it: the ladder is a tuple and the rule is a `min` over it, and what a reader wants to know
is which answer wins.
"""

from __future__ import annotations

import pytest

from hmz.coganchor.agents import (
    PERMISSIONS,
    UNSAID,
    AgentConfig,
    AgentDefaults,
    searching,
    tightest,
)


def test_silence_on_both_sides_stays_silence() -> None:
    """Two configs that say nothing settle to saying nothing, which is the whole point.

    This is the case the work is for: a run given no special parameters, filling a place that
    declared no rung, has to reach the CLI as bare as a person launching it headless by hand.
    """
    assert tightest(UNSAID, UNSAID) == UNSAID


@pytest.mark.parametrize("rung", PERMISSIONS)
def test_any_rung_beats_the_silence_above_it(rung: str) -> None:
    """A declared rung settles onto silence, and silence never settles onto a rung.

    Both directions, because a place and an agent are the two sides of the same call: a flow
    declaring `read-only` over an agent that said nothing gets `read-only`, and an agent
    carrying `read-only` under a place that said nothing keeps it.
    """
    assert tightest(UNSAID, rung) == rung
    assert tightest(rung, UNSAID) == rung


def test_the_tighter_of_two_rungs_wins() -> None:
    """The rule the ladder was written for, unchanged by the silence sitting above it."""
    assert tightest("read-only", "bypass") == "read-only"
    assert tightest("bypass", "read-only") == "read-only"
    assert tightest("workspace-write", "auto") == "workspace-write"


@pytest.mark.parametrize("was", [*PERMISSIONS, UNSAID])
@pytest.mark.parametrize("said", [*PERMISSIONS, UNSAID])
def test_which_side_an_answer_was_written_on_makes_no_difference(
    was: str, said: str
) -> None:
    """Symmetric in its arguments, over every pair there is.

    Nothing reads the argument names to decide: settling is the narrower of two answers, and a
    rule that came out differently depending on which of them was the agent's would make a
    flow's behaviour depend on how its caller happened to be configured.
    """
    assert tightest(was, said) == tightest(said, was)


@pytest.mark.parametrize(
    ("was", "said", "settled"),
    [
        (None, None, None),
        (None, True, True),
        (True, None, True),
        (True, True, True),
        (True, False, False),
        (False, None, False),
        (False, True, False),
        (None, False, False),
    ],
)
def test_the_web_is_read_only_where_nobody_withheld_it(
    was: bool | None, said: bool | None, settled: bool | None
) -> None:
    """Off beats on, and on beats unsaid: the same ladder, two rungs and a silence.

    `None` is the run that never mentions searching, so the CLI is never told either way and
    goes on doing whatever it does unasked. An explicit `True` is humanize saying so, which is
    a narrowing of that silence rather than a loosening: a backend that cannot be told refuses
    it, and refusing is what a setting that would otherwise lie is owed.
    """
    assert searching(was, said) is settled


def test_a_config_may_be_written_with_no_rung_at_all() -> None:
    """Both places a permission is written accept the silence, because it is an answer."""
    assert AgentConfig(model="m", effort="", permission=UNSAID).permission == UNSAID
    assert AgentDefaults(permission=UNSAID).permission == UNSAID


def test_a_rung_no_backend_has_a_word_for_is_still_refused() -> None:
    """Widening the answers is not opening them: a typo is refused where it is written.

    Both places, and with the sentence it always had: what a reader of the refusal needs is
    the rungs there are rather than the silence, which is what they get by writing nothing.
    """
    with pytest.raises(ValueError, match="permission must be one of"):
        AgentConfig(model="m", effort="", permission="whatever")
    with pytest.raises(ValueError, match="permission must be one of"):
        AgentDefaults(permission="whatever")
