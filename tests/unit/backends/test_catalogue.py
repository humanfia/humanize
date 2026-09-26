"""The facts about each backend, held to what its driver actually does.

Honesty tests: every backend set here is exactly what the live driver classes declare or what
the facts in `hmz.coganchor.backends` say -- which backends steer a turn already running, what
each counts and which rungs each takes. A fact that
drifted from the driver is a capability humanize would offer and nothing serves. What a
capability does once it has been asked for is covered where it is driven -- steering a real CLI
in `tests/system/agents` -- and not here.
"""

from __future__ import annotations

import inspect
import sys
from typing import TYPE_CHECKING

from hmz.coganchor.agents import DRIVEN, KINDS, PERMISSIONS
from hmz.coganchor.backends import PROFILES

if TYPE_CHECKING:
    from hmz.coganchor.agents.base import SessionBase

#: The backends whose turns can be talked to while they are running, which is the whole of
#: what `steers` claims: each holds its turn open somewhere a later word can reach -- a
#: process reading its stdin, a thread on an app server -- and answers to say the agent has
#: it. Written out rather than read off the classes, since what the classes say is what is
#: on trial.
_STEERING = {"claude", "codex", "kimi", "pi"}


def _sessions() -> dict[str, type[SessionBase]]:
    """The session class each driven backend answers with, as the catalogue reads them.

    Returns:
      The classes, by backend name, read off what each driver's `new` says it answers with.
    """
    held: dict[str, type[SessionBase]] = {}
    for name, (cls, _) in DRIVEN.items():
        told = inspect.signature(cls.new).return_annotation
        if isinstance(told, str):
            told = vars(sys.modules[cls.__module__])[told]
        held[name] = told
    return held


def test_a_backend_that_steers_a_running_turn_says_so_and_one_that_cannot_says_so() -> (
    None
):
    """The four that hold a turn open somewhere a later word reaches, and the rest."""
    sessions = _sessions()
    assert {name for name, one in sessions.items() if one.steers} == _STEERING
    # Each of the others refuses rather than queueing the word behind as another turn, which
    # is what `steers` being False is a promise about.
    for name, one in sessions.items():
        assert one.steers is (name in _STEERING), name


def test_each_layer_names_exactly_the_backends_it_reaches() -> None:
    """All three layers are built now, and each says which CLIs it reaches and no more.

    The hooked layer names the CLIs that take a hook table meant for a single run rather than
    every CLI that happens to have hooks at all; the preload layer, the four whose CLI is a
    plain Node script; the patched layer, the two shipped as one Bun file. A layer half filled
    in would read as a backend that had quietly gained one, which is what this refuses.
    """
    assert {one.name for one in PROFILES if one.hooks is not None} == {"claude", "qwen"}
    assert {one.name for one in PROFILES if one.preloads} == {
        "kimi",
        "mimo",
        "pi",
        "qwen",
    }
    assert {one.name for one in PROFILES if one.bundles} == {"claude", "opencode"}
    for one in PROFILES:
        if one.bundles:
            # Every bundle written down fingerprints on a line rather than a path alone.
            assert all(bundle.says for bundle in one.bundles), one.name


#: What each backend's driver reports of what a turn cost, written out rather than read off
#: the drivers -- what the drivers say is what is on trial. `reasoning` is there only for the
#: three that count it beside the output rather than inside it; and two say the input and the
#: output alone, each of them counting its cached reads inside the input.
_COUNTING: dict[str, set[str]] = {
    "agy": {"input", "output", "cache_read", "reasoning"},
    "claude": {"input", "output", "cache_read", "cache_write"},
    "codex": {"input", "output"},
    "cursor-agent": {"input", "output", "cache_read", "cache_write"},
    "dsh": {"input", "output", "cache_read", "cache_write"},
    "grok": {"input", "output", "cache_read", "cache_write"},
    "kimi": {"input", "output", "cache_read", "cache_write"},
    "mimo": {"input", "output", "cache_read", "cache_write", "reasoning"},
    "opencode": {"input", "output", "cache_read", "cache_write", "reasoning"},
    "pi": {"input", "output", "cache_read", "cache_write"},
    "qwen": {"input", "output", "cache_read", "cache_write"},
    "zcode": {"input", "output"},
}


def test_what_each_backend_counts_is_what_its_driver_says_it_counts() -> None:
    """And every word of it is a kind humanize has, rather than one CLI's own spelling."""
    assert {name: set(cls.counts) for name, (cls, _) in DRIVEN.items()} == _COUNTING
    for name, (cls, _) in DRIVEN.items():
        assert cls.counts <= set(KINDS), name


def test_what_a_driver_says_it_takes_is_what_it_actually_takes() -> None:
    """`rungs` is a word for a refusal, and a word that drifted from one would be a lie.

    The refusal lives in each driver's own `_serves`, which is where it has to be: a config
    arrives at an agent that is being made and at one being set up as something else, and both
    are refused there. `rungs` is the same fact said early enough for somebody choosing a
    backend to read, and nothing in `AgentBase._serves` holds the two together yet -- so this
    does, by making every driven backend at every rung and asking whether it was refused.

    A backend that learns to refuse a rung and forgets to narrow `rungs` would advertise it,
    pass the picker, pass `serves`, and raise where the agent is made: exactly the late
    failure the capability exists to move earlier.
    """
    for backend, (cls, config) in DRIVEN.items():
        for permission in PERMISSIONS:
            settings = config(model="m", effort="", permission=permission)
            try:
                cls(settings)
            except ValueError:
                taken = False
            else:
                taken = True

            assert taken is (permission in cls.rungs), (backend, permission)
