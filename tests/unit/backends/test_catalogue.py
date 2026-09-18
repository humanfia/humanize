"""The capability catalogue, held to saying only what this installation actually serves.

Honesty tests: every name the catalogue uses is a real moment, a real backend or a real
member of the interfaces a flow is written against, and every backend set is exactly what
the live driver classes declare or what the facts in `hmz.coganchor.backends` say. The catalogue is
what a compiler steers by, and a capability it invented -- or one that drifted from the
drivers -- is a generated flow that asks for what nothing serves.

The vocabulary those names are drawn from is covered here too: which backends steer a turn
already running, and which capability names a backend's own facts come to. What a capability
does once it has been asked for is covered where it is driven -- steering a real CLI in
`tests/system/agents` -- and not here.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import sys
from typing import TYPE_CHECKING

from hmz.coganchor import places
from hmz.coganchor.agents import DRIVEN, EVERYWHERE, KINDS, PERMISSIONS, Moment, rung
from hmz.coganchor.agents.config import UNSAID, AgentConfig
from hmz.coganchor.backends import PROFILES, Bundled, Hooked, Profile, named
from hmz.flows import Agent, Person, Session
from hmz.flows.checking import OF_AGENT, WHERE, briefed, catalogue, offered, surface

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


def test_every_conditional_moment_is_real_and_exactly_whose_drivers_say() -> None:
    told = {one.name: one for one in catalogue() if one.name.startswith("moment:")}
    outside = {one for one in Moment if one not in EVERYWHERE}
    assert set(told) == {f"moment:{one.value}" for one in outside}
    for moment in outside:
        assert told[f"moment:{moment.value}"].backends == frozenset(
            name for name, (cls, _) in DRIVEN.items() if moment in cls.moments
        )


def test_the_backend_facts_are_the_drivers_own() -> None:
    told = {one.name: one.backends for one in catalogue()}
    assert told["pursue"] == frozenset(
        name for name, (cls, _) in DRIVEN.items() if cls.pursues
    )
    assert told["goal"] == told["pursue"]
    # The two facts a session carries, checked against the backends known to carry them:
    # the sets themselves are read off the session classes, so what is pinned here is that
    # the reading reaches them at all.
    assert {"claude", "codex"} <= told["shape"]
    assert "claude" in told["tools"]
    for one in catalogue():
        assert one.backends <= set(DRIVEN), one.name


def test_every_ask_the_catalogue_spells_is_on_the_interfaces() -> None:
    """The primitives are described in code, and the code has to be the real interface."""
    asks = surface(Agent) | surface(Session) | surface(Person)
    anchored = {
        "turns": "batch",
        "sessions": "new",
        "budgets": "spent",
        "hooks": "hooks",
        "board": "board",
        "clone": "clone",
        "skills": "loads",
        "pursue": "pursue",
        "tools": "offers",
        "steer": "interject",
        "fork": "fork",
    }
    said = {one.name: one.said for one in catalogue()}
    for name, member in anchored.items():
        assert member in asks
        assert member in said[name], name
    # And the ones whose anchor is the vocabulary hmz.flows hands through.
    offers = offered()
    for name, word in {
        "subflows": "load",
        "person": "Person",
        "state": "flow",
        "hooks": "Moment",
        "goal": "Goal",
    }.items():
        assert word in offers
        assert word in said[name], name


def test_the_moments_every_backend_reaches_are_everywhere() -> None:
    (moments,) = (one for one in catalogue() if one.name == "moments")
    assert moments.backends == frozenset()
    for one in EVERYWHERE:
        assert f"Moment.{one.name}" in moments.said


def test_the_briefing_mentions_every_capability_and_its_backends() -> None:
    page = briefed()
    for one in catalogue():
        assert f"- {one.name}" in page
        for backend in one.backends:
            assert backend in page
    # The split the compiler steers by: what needs declaring is under the second heading,
    # and what a *machine* has to come to is under a third of its own. Three rather than two
    # because a flow writes the vocabulary in two places -- `Needs(...)` and `Needs(where=...)`
    # -- and a page that ran them together was teaching the one mistake nothing used to catch.
    assert "Every backend -- Needs(...) beside the place:" in page
    assert "Only some backends" in page
    assert "Where an agent's turns land -- Needs(where=(...))" in page
    assert page.index("- turns:") < page.index("Only some backends")
    assert page.index("Only some backends") < page.index("- pursue")
    assert page.index("- pursue") < page.index("Where an agent's turns land")
    assert page.index("Where an agent's turns land") < page.index("- isolated:")


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


def test_the_catalogue_says_which_backends_narrate_a_reach_as_it_happens() -> None:
    """One, and it is the one whose driver asks its CLI for the fragments."""
    sessions = _sessions()
    told = {one.name: one.backends for one in catalogue()}

    assert told["narrate"] == frozenset(
        name for name, one in sessions.items() if one.narrates
    )
    assert told["narrate"] == {"claude"}


def test_one_setting_is_one_capability_name_and_no_second_one() -> None:
    """A field only some of these configs carry is asked for as `settings:<field>` alone.

    The catalogue used to mint a word of its own for some of them -- `trust`, `title`,
    `features` -- beside the name the derived block gives every such field, so Cursor's trust
    flag answered to `trust` and to `settings:trust` both. That is one fact written in two
    places: the hand-written word goes on promising what a renamed field no longer serves,
    and a generated flow asks under whichever of the two it happened to read.

    What makes a hand-written name a duplicate rather than a capability of its own is that it
    says nothing the field's own presence does not. `narrate` is the counter-case and is why
    this is not simply a ban on naming a field: it asks whether a session can be told at all,
    which is a question with a different answer -- two backends carry `partial_messages` and
    one of them narrates. So a name is a duplicate here when it serves exactly the backends
    whose config carries the field *and* names that field, and only the derived one may.
    """
    common = {one.name for one in dataclasses.fields(AgentConfig)}
    carriers: dict[str, set[str]] = {}
    for backend, (_, config) in DRIVEN.items():
        for one in dataclasses.fields(config):
            if one.name not in common:
                carriers.setdefault(one.name, set()).add(backend)
    held = catalogue()

    assert carriers
    for field, backends in carriers.items():
        naming = [
            one.name
            for one in held
            if one.backends == frozenset(backends)
            and re.search(rf"\b{field}\b", one.said)
        ]
        assert naming == [f"settings:{field}"], field
    # `tier:fast` is not one of these and must not be read as one: `service_tier` is a field
    # of the common config, which every backend carries and the derived block therefore
    # leaves out, so the hand-written name is the only word there has ever been for it.
    assert "service_tier" in common
    assert "tier:fast" in {one.name for one in held}


def test_the_catalogue_says_which_backends_steer_and_which_fork() -> None:
    told = {one.name: one.backends for one in catalogue()}
    assert told["steer"] == frozenset(_STEERING)
    # Read off `hmz.coganchor.backends` rather than off the drivers: a fork is the CLI's own, so the
    # one place a fact about a CLI is written is where the catalogue asks.
    assert told["fork"] == frozenset(
        name for name in DRIVEN if (one := named(name)) is not None and one.forks
    )


def test_the_names_a_backend_serves_are_derived_from_its_own_facts() -> None:
    """`tags` says the vocabulary's word for a fact rather than storing the word too."""
    bare = Profile(
        name="bare", aliases=("bare",), home_var="", home_dir="", logs=(), efforts=()
    )
    assert bare.tags() == {"resume"}  # every CLI here resumes unless it says otherwise
    full = Profile(
        name="full",
        aliases=("full",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        swarms=True,
        searches=True,
        forks=True,
        resumes=False,
        hooks=Hooked(seam="flag", name="--settings"),
        preloads="NODE_OPTIONS",
        bundles=(Bundled(path="dist/*/cli.js", says=r"spawnSync\("),),
    )
    # `bundles` is set on this profile and names nothing: what a fingerprint says is that a
    # patch could be found in what the CLI shipped, which the bytes on this machine decide
    # rather than the table -- so it is read back where a turn takes that road, not promised
    # here where a flow could ask for it and be given nothing.
    assert full.tags() == {
        "swarm",
        "search",
        "fork",
        "anchor:hooked",
        "anchor:preloaded",
    }


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


def test_the_catalogue_names_where_an_agents_turns_may_land() -> None:
    told = {one.name: one for one in catalogue()}
    for name in ("remote", "isolated", "managed", "linux", "darwin"):
        # Every backend, since what a machine is is the same question whichever CLI is
        # driven on it -- and what needs saying is said where the place is declared.
        assert told[name].backends == frozenset(), name
        assert told[name].said


def test_an_anchor_nothing_serves_is_left_out_rather_than_read_as_everybodys() -> None:
    told = {one.name: one for one in catalogue() if one.name.startswith("anchor:")}
    # An empty backend set means every backend here, so a way in that has not been built
    # must not be listed at all, and one only some of them serve must be listed with exactly
    # those. The two universal ones always are: every backend is a command line spawned here,
    # and what a spawned turn runs is what an anchor traces. The other two are served by the
    # CLIs whose profile says so, and are listed against exactly those. There is no
    # `anchor:patched`: nothing takes a turn down that road yet, and a name here would be one
    # a flow could ask for and pass.
    assert set(told) == {
        "anchor:native-cli",
        "anchor:supervised",
        "anchor:hooked",
        "anchor:preloaded",
    }
    assert told["anchor:native-cli"].backends == frozenset()
    assert told["anchor:supervised"].backends == frozenset()
    assert told["anchor:hooked"].backends == frozenset({"claude", "qwen"})
    assert told["anchor:preloaded"].backends == frozenset(
        {"kimi", "mimo", "pi", "qwen"}
    )


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


def test_each_kind_of_token_is_a_capability_and_whose_is_the_drivers_own() -> None:
    """A flow steering by what a turn cost has to be able to ask before it starts.

    A backend that never counts a kind answers nought for it exactly as one that spent
    nothing does, and a loop bounded by an output count on a backend that reports none is a
    loop that never ends.
    """
    told = {one.name: one for one in catalogue() if one.name.startswith("counts:")}
    assert set(told) == {f"counts:{kind}" for kind in KINDS}
    for kind in KINDS:
        assert told[f"counts:{kind}"].backends == frozenset(
            name for name, (cls, _) in DRIVEN.items() if kind in cls.counts
        )
    # A kind only some of them count leaves the rest out rather than quietly reading as
    # nought for everybody: `reasoning` is the three that count it beside the output.
    assert told["counts:reasoning"].backends == frozenset({"agy", "mimo", "opencode"})


def test_every_name_a_backends_own_facts_come_to_is_in_the_catalogue() -> None:
    """A name a flow may ask under and a compiler cannot read is one nothing generated asks.

    `search`, `swarm` and `resume` were exactly that. `comes_to` unions a backend's tags in,
    so they have always worked in `Needs`; the catalogue and the briefing -- the one page a
    compiler steers by -- said nothing about any of them.
    """
    named_here = {one.name for one in catalogue()}

    assert {name for one in PROFILES for name in one.tags()} <= named_here
    for name in ("search", "swarm", "resume"):
        (one,) = (held for held in catalogue() if held.name == name)

        assert one.backends == frozenset(
            backend
            for backend in DRIVEN
            if (profile := named(backend)) is not None and name in profile.tags()
        )


def test_every_capability_says_which_half_of_needs_asks_for_it() -> None:
    """The two halves are answered by different code against different facts.

    A machine capability carries no backends because no backend answers for it, and an empty
    backend set is how this catalogue says "every backend here". Without the half written
    down, the one is read as the other: `Needs("isolated")` was satisfied by everything.
    """
    held = catalogue()

    assert {one.asked for one in held} == {OF_AGENT, WHERE}
    asked = {one.name: one.asked for one in held}
    for name in ("remote", "isolated", "managed", "linux", "darwin"):
        assert asked[name] == WHERE, name
    # The roads split between the halves, which is the one thing here that is not obvious.
    # An anchor declares the two it reaches a machine by; the two humanize takes from inside
    # a process it started are the CLI's own, and no machine has ever carried either.
    assert asked["anchor:native-cli"] == WHERE
    assert asked["anchor:supervised"] == WHERE
    assert asked["anchor:hooked"] == OF_AGENT
    assert asked["anchor:preloaded"] == OF_AGENT
    for one in held:
        # Backends are meaningless on the machine half and must stay empty there, or the
        # emptiness that means "all of them" would read off the wrong side of the line.
        if one.asked == WHERE:
            assert one.backends == frozenset(), one.name


def test_the_places_described_here_are_the_places_coganchor_knows() -> None:
    """The words are declared beside the machines and only described by the catalogue."""
    assert {one.name for one in catalogue() if one.asked == WHERE} == (
        places.PLACES | set(places.ROADS)
    )
    assert frozenset({"anchor:hooked", "anchor:preloaded"}) == places.INSIDE


def test_a_rung_is_named_against_exactly_the_backends_that_take_it() -> None:
    """Read off the drivers' own `rungs`, which is what each of them refuses a config for."""
    told = {one.name: one.backends for one in catalogue()}
    for permission in PERMISSIONS:
        taking = frozenset(
            backend for backend, (cls, _) in DRIVEN.items() if permission in cls.rungs
        )

        assert told[rung(permission)] == (
            frozenset() if taking == frozenset(DRIVEN) else taking
        ), permission
    # dsh is the one driven backend that cannot be held below `bypass`, and it is the only
    # one missing from the three narrower rungs.
    assert frozenset(DRIVEN) - told[rung("read-only")] == {"dsh"}
    # And `bypass` is every backend there is, which the catalogue says by naming none: a CLI
    # somebody added by hand is in no `DRIVEN` table, and it takes that rung too.
    assert told[rung("bypass")] == frozenset()


def test_no_rung_is_named_for_the_silence_above_the_ladder() -> None:
    """`UNSAID` is not a rung, and every backend can be told nothing at all."""
    assert rung(UNSAID) not in {one.name for one in catalogue()}
