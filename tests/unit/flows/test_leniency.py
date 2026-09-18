"""What a place gets when it would rather run than be refused, and what it is still refused.

A declaration is meant to hold, so a backend that cannot carry one refuses the run -- that is
the doctrine, it is the default, and it stays the default. `insist=False` is the other honest
answer to one particular problem: a benchmark declaring `web_search=False` across every CLI
there is is declaring something about the comparison rather than about the roster, and the
three backends with no way of being told should cost it three noisier cells rather than three
cells that never ran.

What it must never be is "apply it anyway and say nothing". The setting that cannot be carried
is dropped -- the config comes out not carrying it -- the rest are settled, and a line says
which place, which setting and what the agent does instead. A config left holding
`web_search=False` on an agent that will go on searching is the whole of what this seam exists
to prevent, and asking politely does not make it true.

Here rather than through a flow because none of it needs one: a `Place` is a named tuple, an
agent is an object, and `runs_at` is the one call between them. Nothing is started, nothing is
installed and no CLI is run.
"""

from __future__ import annotations

import pytest

from hmz.coganchor.agents import (
    UNSAID,
    AgentConfig,
    AgentDefaults,
    ClaudeCodeAgent,
    DshAgent,
    KimiCodeCLIAgent,
    Unserved,
)
from hmz.flows.driving import NotAFlow, Place, _declared, runs_at

#: The two the acceptance case is about: `dsh` and `kimi` are backends whose profiles say they
#: cannot be told about the web at all, which is why a flow declaring `web_search=False` used
#: to kill every cell of theirs before the first turn.
UNTELLABLE = (DshAgent, KimiCodeCLIAgent)


def place(**said: object) -> Place:
    """A place called `reviewer` that declares what it is given and nothing else."""
    return Place(name="reviewer", person=False, moments=frozenset(), **said)  # type: ignore[arg-type]


def agent(kind: type, **said: object) -> object:
    """One of those agents, made with a model and an effort nothing here reads."""
    return kind(AgentConfig(model="a-model", effort="", **said))  # type: ignore[arg-type]


class TestTheFlowbenchCase:
    """A place declaring `web_search=False` onto a backend with no way of being told."""

    @pytest.mark.parametrize("kind", UNTELLABLE)
    def test_it_runs_rather_than_being_refused(self, kind: type) -> None:
        """Which is the point: the cell runs, where before it never started."""
        runs_at("bench.py", agent(kind), place(web_search=False, insist=False))  # type: ignore[arg-type]

    @pytest.mark.parametrize("kind", UNTELLABLE)
    def test_the_config_does_not_come_out_carrying_the_answer_it_cannot_keep(
        self, kind: type
    ) -> None:
        """The honest half. An agent that will search must not be holding `False`.

        This is the assertion the whole design is for. Leniency that left the declaration on
        the config would be leniency that made the config lie, which is worse than the
        refusal it replaced -- the refusal at least said so.
        """
        one = agent(kind)
        runs_at("bench.py", one, place(web_search=False, insist=False))  # type: ignore[arg-type]
        assert one.config.web_search is not False  # type: ignore[attr-defined]

    @pytest.mark.parametrize("kind", UNTELLABLE)
    def test_it_says_which_place_which_setting_and_what_happens_instead(
        self, kind: type
    ) -> None:
        """The other honest half: dropped is not the same as ignored unless nobody is told."""
        dropped: list[str] = []
        runs_at(  # type: ignore[arg-type]
            "bench.py", agent(kind), place(web_search=False, insist=False), dropped=dropped
        )
        assert len(dropped) == 1
        assert "reviewer" in dropped[0]
        assert "web_search" in dropped[0]
        assert "reading the web" in dropped[0]

    @pytest.mark.parametrize("kind", UNTELLABLE)
    def test_insisting_is_still_the_refusal_it_always_was(self, kind: type) -> None:
        """A place that says nothing about insisting insists, so nothing moved under anyone."""
        with pytest.raises(NotAFlow, match="no way of being told not to search the web"):
            runs_at("bench.py", agent(kind), place(web_search=False))  # type: ignore[arg-type]


class TestTheRestIsStillSettled:
    """Dropping one declaration is not dropping the declaration."""

    def test_the_servable_one_settles_and_the_other_is_dropped(self) -> None:
        """Two declared, one carried: kimi takes a rung and cannot be told about the web."""
        one = agent(KimiCodeCLIAgent)
        dropped: list[str] = []
        runs_at(  # type: ignore[arg-type]
            "bench.py",
            one,
            place(web_search=False, permission="read-only", insist=False),
            dropped=dropped,
        )
        assert one.config.permission == "read-only"  # type: ignore[attr-defined]
        assert one.config.web_search is not False  # type: ignore[attr-defined]
        assert "web_search" in dropped[0]
        assert "permission" not in dropped[0]

    def test_a_backend_that_carries_both_drops_neither(self) -> None:
        """Leniency is reached for only where something was actually refused."""
        one = agent(ClaudeCodeAgent)
        dropped: list[str] = []
        runs_at(  # type: ignore[arg-type]
            "bench.py",
            one,
            place(web_search=False, permission="read-only", insist=False),
            dropped=dropped,
        )
        assert one.config.web_search is False  # type: ignore[attr-defined]
        assert one.config.permission == "read-only"  # type: ignore[attr-defined]
        assert dropped == []

    def test_two_refusals_take_two_passes_and_both_are_given_up(self) -> None:
        """`_serves` raises at the first thing it finds, so settling asks again.

        dsh can be told neither, and refuses the web first because the base class checks it
        before the driver checks the rung. One pass would have dropped the web and been
        refused about the rung; the loop gives up both and says so in one line.
        """
        one = agent(DshAgent)
        dropped: list[str] = []
        runs_at(  # type: ignore[arg-type]
            "bench.py",
            one,
            place(web_search=False, permission="read-only", insist=False),
            dropped=dropped,
        )
        assert one.config.web_search is not False  # type: ignore[attr-defined]
        assert one.config.permission == UNSAID  # type: ignore[attr-defined]
        assert len(dropped) == 1
        assert "permission" in dropped[0]
        assert "web_search" in dropped[0]


class TestOnlyWhatThePlaceDeclared:
    """Leniency gives up the flow's own answers and nobody else's.

    A tier and an effort are refused where the agent is built, which is upstream of every
    flow, so neither of them can reach `runs_at` by way of a place at all -- and that is the
    point rather than a gap: they are the settings whoever chose the agent chose, and there
    is no path by which a flow gives one of them up. What does reach here is a refusal naming
    a field beside one the place declared, and that is refused whatever the place says.
    """

    def test_a_refusal_naming_a_setting_the_place_did_not_declare_is_still_a_refusal(
        self,
    ) -> None:
        """The guard itself, put to a backend that refuses something nobody here asked for.

        No backend in the package can be made to do this today -- a tier and an effort are
        refused at construction, upstream of every flow -- which is why it is asked of a
        stand-in rather than of one of them. The rule has to hold for the backend somebody
        adds next: a refusal about a field the flow never spoke about is not the flow's to
        wave away, however little it insisted about the field it did speak about.
        """

        class RefusesTheTier(DshAgent):
            """Made happily, and refuses the tier the moment it is set up as anything."""

            built = False

            def _serves(self, config: AgentConfig) -> None:
                if not self.built:
                    return
                raise Unserved("this one cannot be served fast", "service_tier")

        one = RefusesTheTier(AgentConfig(model="a-model", effort=""))
        one.built = True
        with pytest.raises(NotAFlow, match="cannot be served fast"):
            runs_at("bench.py", one, place(web_search=False, insist=False))  # type: ignore[arg-type]

    def test_a_tier_no_backend_can_send_is_refused_where_the_agent_is_built(self) -> None:
        """Upstream of every flow, which is why no place may give it up."""
        with pytest.raises(Unserved) as refused:
            DshAgent(AgentConfig(model="a-model", effort="", service_tier="fast"))
        assert refused.value.settings == frozenset({"service_tier"})

    def test_an_effort_off_the_ladder_is_refused_where_the_agent_is_built(self) -> None:
        """The same, for the rung it thinks at: a place never declares one."""
        with pytest.raises(Unserved) as refused:
            ClaudeCodeAgent(AgentConfig(model="a-model", effort="ultrathink"))
        assert refused.value.settings == frozenset({"effort"})

    def test_the_three_a_place_may_declare_are_the_three_it_may_give_up(self) -> None:
        """The rule underneath both, read on its own: silence declares nothing."""
        assert _declared(place()) == frozenset()
        assert _declared(place(web_search=False)) == frozenset({"web_search"})
        assert _declared(place(permission="read-only")) == frozenset({"permission"})
        assert _declared(place(goals=False)) == frozenset({"goals"})
        assert "service_tier" not in _declared(
            place(web_search=False, permission="read-only", goals=False)
        )


class TestTheRefusalNamesItself:
    """What makes any of this possible: a shortfall that says which setting it was."""

    def test_it_is_a_value_error_still(self) -> None:
        """Every `except ValueError` written before this catches it now."""
        assert issubclass(Unserved, ValueError)

    def test_the_sentence_is_the_sentence_and_the_name_travels_beside_it(self) -> None:
        """The message a person reads is unchanged; the field name is the new part."""
        one = Unserved("it cannot be told", "web_search")
        assert str(one) == "it cannot be told"
        assert one.settings == frozenset({"web_search"})

    def test_a_backend_that_cannot_be_told_names_the_field(self) -> None:
        """Raised where it always was, and now answerable about what it was about."""
        with pytest.raises(Unserved) as refused:
            DshAgent(AgentConfig(model="a-model", effort="", web_search=False))
        assert refused.value.settings == frozenset({"web_search"})

    def test_a_pair_refused_together_names_both(self) -> None:
        """opencode withholding its table hears neither, and dropping one fixes neither."""
        from hmz.coganchor.agents import OpencodeAgentConfig

        with pytest.raises(Unserved) as refused:
            OpencodeAgentConfig(
                model="anthropic/claude",
                effort="",
                permission="read-only",
                web_search=False,
                permission_table=False,
            )
        assert refused.value.settings == frozenset({"permission", "web_search"})

    def test_a_withheld_table_says_nothing_about_a_web_nobody_asked_about(self) -> None:
        """`web_search=None` is not a narrowing, so it is not a thing to be refused.

        The three-answer switch has a silence in it, and a silence withholds nothing: a
        config that never raised the subject asks this backend's table for nothing, and the
        table not being written is no loss to it. `not self.web_search` read that silence as
        a no the moment the field's default became None, which would have refused a config
        that had asked for nothing at all.
        """
        from hmz.coganchor.agents import OpencodeAgentConfig

        one = OpencodeAgentConfig(
            model="anthropic/claude",
            effort="",
            permission="bypass",
            permission_table=False,
        )
        assert one.web_search is None


class TestTheDefaultDidNotMove:
    """Nothing changes for a flow that does not ask, which is every flow there is."""

    def test_a_place_that_says_nothing_insists(self) -> None:
        assert AgentDefaults().insist is True
        assert place().insist is True

    def test_a_place_declaring_nothing_still_settles_nothing(self) -> None:
        """Leniency is about refusals, and a place with nothing to declare meets none."""
        one = agent(DshAgent)
        was = one.config  # type: ignore[attr-defined]
        dropped: list[str] = []
        assert runs_at("bench.py", one, place(insist=False), dropped=dropped) == was  # type: ignore[arg-type]
        assert one.config == was  # type: ignore[attr-defined]
        assert dropped == []
