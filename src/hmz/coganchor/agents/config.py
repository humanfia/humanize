"""What an agent is configured with, before it has run anything."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

# The one word a line uses for no rung at all, from the module that says what every backend's
# rungs are. Imported rather than repeated: `backends` reaches for nothing but the standard
# library, so naming it here costs a config nothing, and a second spelling of `auto` would be
# a second place for the two halves of one value to disagree.
from hmz.coganchor.backends import AUTO

if TYPE_CHECKING:
    # Named for the type only: a flow that runs its agents here is the common one, and it
    # should not pay to import the half of coganchor that runs a session, nor the docker
    # client behind a container.
    from hmz.coganchor.machines import MachineConfig

__all__ = [
    "CUTOFFS",
    "OUTCOMES",
    "PERMISSIONS",
    "SERVICE_TIERS",
    "UNSAID",
    "AgentConfig",
    "Budget",
    "Unserved",
    "anchored",
]

#: What an agent may do without being asked, loosest last. Named the way these CLIs name them
#: rather than in a vocabulary of humanize's own, so that a rung reads as the thing it is
#: wherever it is shown. Every backend has a ladder of its own and none of them has the same
#: four rungs, so these are the question rather than any one CLI's answer, and each driver
#: says which of its own settings it reaches for:
#:
#: - `read-only`: it may look at anything and change nothing -- no edits, no commands.
#: - `workspace-write`: it may change the workspace it was given, and is stopped at the edge
#:   of it.
#: - `auto`: it may reach for anything, and what it asks for is granted -- which is where a
#:   hook hung on `PERMISSION_REQUEST` gets a say, that being a moment a backend actually
#:   waits on. It is not the only one: on a CLI that takes a hook table written for a single
#:   run, `PRE_TOOL_USE` is served from that table and is waited on at every rung.
#: - `bypass`: nothing is asked and nothing is checked, which is what an unattended flow has
#:   always run its agents at.
#:
#: A backend with no sandbox of its own cannot tell `workspace-write` from `auto`, and says so
#: where it maps them rather than pretending to a rung it has not got.
PERMISSIONS = ("read-only", "workspace-write", "auto", "bypass")


#: The word for no rung at all: humanize says nothing to the CLI about what its agent may do,
#: which leaves it wherever that CLI's own headless run leaves it. Outside :data:`PERMISSIONS`
#: because it is not a rung on the ladder but the absence of one -- the same shape `effort`
#: already has, where `AUTO` becomes "" and every driver knows to say nothing. Loosest of all,
#: so a place declaring nothing goes on settling nothing.
UNSAID = ""

#: Every answer a config may be written with: the ladder, and the silence above it.
_SAYABLE = (*PERMISSIONS, UNSAID)


class Unserved(ValueError):  # noqa: N818  -- what the setting is here, not what went wrong
    """Raised for a setting this backend has no way of carrying."""


#: How quickly a provider is asked to serve one agent, independent of how hard its model
#: reasons. Backends map these common meanings into their own request vocabulary and refuse
#: ``fast`` when they cannot express it exactly.
SERVICE_TIERS = ("default", "fast")

#: When a spent budget takes hold of the turn it was given to, loosest first:
#:
#: - `next-response`: the answer the model is in the middle of is let land, and the turn stops
#:   on it. What comes back is a whole thought rather than half a sentence, and the tokens
#:   already paid for are the ones a flow gets to read.
#: - `immediately`: the turn ends where it stands, whatever it was saying. Which is what a
#:   runaway is stopped by -- an agent six minutes into an answer nobody wants goes on
#:   spending for as long as it is left alone, and waiting for that answer is the cost being
#:   paid rather than avoided.
#:
#: `next-response` waits for an answer to land and does not wait for one forever: three of
#: these backends state what a turn cost only once the turn is over, so nothing arrives
#: mid-turn to stop on -- and a turn that has gone quiet is exactly the one a clock was set
#: for. The wait has an end, and the end of it is the cut-off.
#:
#: How much a backend can be cut off by differs with how it is driven. A CLI whose turn is a
#: process of its own -- one command, or one held open across its turns -- is cut off by
#: ending that process. One whose turn is held somewhere shared, on an app server serving
#: every session of an agent at once, is stopped at the next answer instead: taking that
#: server down would end the turns of every other conversation on it.
CUTOFFS = ("next-response", "immediately")

#: What a turn whose budget is spent comes to:
#:
#: - `end`: it answers with what has been said, so a loop reads a short turn rather than an
#:   exception. Half an answer is still an answer, and a flow that summarises, drafts or
#:   explores would rather have it than nothing.
#: - `fail`: it raises, so a flow that cannot use a truncated answer stops instead of feeding
#:   one forward. It raises `Unrecoverable`, because a budget spent once is spent again on
#:   the next try: a turn taken over on a schedule would burn the same budget every round.
#:
#: `end` is the default because a turn cut off has still done what it did: its edits are on
#: disk and its conversation is open to the next turn, which is the whole difference between
#: a cap and a kill. Read as a failure it would be taken again, on a budget refilled for the
#: retry, and a cap a loop refills every time it is reached is not a cap.
OUTCOMES = ("end", "fail")


@dataclass(frozen=True, slots=True, kw_only=True)
class Budget:
    """What one turn may spend before it is cut off, and what happens when it has.

    Per turn rather than per session: a conversation is many turns, and a cap over all of
    them would be a flow whose tenth round is cut off for what its first round wrote. Every
    turn starts with the whole of it, and what is measured is the rise across that turn.

    Humanize's own rather than a flag handed to the CLI. Two of these backends can be given a
    cap of their own -- Claude Code takes dollars, counted over the process it runs rather
    than over the turn -- and neither is one a flow could be written against: a cap only some
    of them have is a question before it is an answer, and one counted per process is not a
    per-turn cap however it is spelled. So it is held to off the meter every backend feeds.

    A dataclass rather than a handful of arguments so that the question stays one question.
    A budget is already four answers -- how many tokens, how long, when it bites and what it
    leaves behind -- and the ones after it (what it may cost in money, how many tools it may
    reach for) are dimensions of the same thing. Written as a value, a new dimension is a
    field here and a line in :meth:`over`; written as arguments, it is a signature change in
    every place a turn can be asked for.

    Nothing is capped unless it is named::

        session.budget = Budget(seconds=90, when="immediately", then="fail")
        session.budget = Budget()  # and this one is a turn under no budget at all,

    which is what a conversation says to opt out of the budget its agent was configured with.

    Attributes:
      output: Output tokens one turn may come out with, or 0 for as many as it takes. Output
        rather than every kind: what a turn spends its time and most of its money on is what
        it writes, and an input count is what the flow itself put in front of the model.
      seconds: How long one turn may run for on the clock, or 0 for as long as it takes.
        Seconds on the clock rather than seconds the model was talking, for the reason a rate
        is: a turn waiting on a tool, a sandbox or a rate limit is a turn taking that long.
      when: When a spent budget takes hold, as one of :data:`CUTOFFS`.
      then: What the turn comes to once it is spent, as one of :data:`OUTCOMES`.
    """

    output: float = 0.0
    seconds: float = 0.0
    when: str = "next-response"
    then: str = "end"

    def __post_init__(self) -> None:
        # Said where it is written rather than minutes into the turn it was meant to hold: a
        # word no cut-off answers to is a budget that would quietly never bite, which is the
        # one failure a budget must not have.
        if self.when not in CUTOFFS:
            raise ValueError(
                f"when must be one of {', '.join(CUTOFFS)}, not {self.when!r}"
            )
        if self.then not in OUTCOMES:
            raise ValueError(
                f"then must be one of {', '.join(OUTCOMES)}, not {self.then!r}"
            )
        if self.output < 0 or self.seconds < 0:
            raise ValueError("a budget cannot be less than nothing")

    @property
    def bounded(self) -> bool:
        """Whether this budget caps anything at all.

        A budget with nothing named in it is what a session says to run its turns under no
        budget, and it costs nothing to be given one: nothing is measured and no clock is
        started for a turn that cannot run through it.
        """
        return self.output > 0 or self.seconds > 0

    def over(self, *, output: float = 0.0, seconds: float = 0.0) -> str:
        """Which cap this turn has run through, if any, said the way a person would read it.

        The one place a reading is compared with a cap, so that a dimension added to a budget
        is a field above and a line here rather than a change wherever a turn is asked for.

        Args:
          output: Output tokens this turn has come out with so far.
          seconds: How long it has been running, on the clock.

        Returns:
          Why the turn is over budget -- `500 output tokens`, `90s` -- or "" while it is
          still inside every cap it was given.
        """
        if self.output > 0 and output >= self.output:
            return f"{self.output:g} output tokens"
        if self.seconds > 0 and seconds >= self.seconds:
            return f"{self.seconds:g}s"
        return ""


@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    """The settings every session of an agent runs at.

    Frozen, because a session resumes under the settings it opened with: a config that changed
    mid-flow would silently split one conversation across two models.

    Attributes:
      model: The model name or identifier the backend is asked for.
      effort: The reasoning effort the backend is asked for, in the backend's own wording.
      service_tier: How quickly the provider is asked to serve the same model and effort, as
        one of :data:`SERVICE_TIERS`. ``fast`` buys lower latency rather than less reasoning.
      machine: The machine the agent's work lands on, or None to work on this one. One that is
        already running is named by the anchor onto it; one started for the agent is started on
        the first turn and says where it is itself. The agent runs here either way, so its
        credentials and its trajectory stay where a flow can reach them; what moves is the
        project it reads and the commands it runs.
      permission: What this agent may do without being asked, as one of :data:`PERMISSIONS`,
        or :data:`UNSAID` -- not a rung at all, but humanize saying nothing to the CLI and
        leaving it wherever that CLI's own headless run leaves it. :data:`UNSAID` is what an
        agent comes at, because a run nobody configured is a run humanize has nothing to say
        about: a rung is an answer, and an answer nobody gave is not humanize's to invent on
        their behalf. What such a run does is what the same CLI does for whoever types it at a
        shell, out of the settings they already have -- which is the one behaviour a person
        can check for themselves. Every rung is the flow's choice, settled onto the agent from
        the :class:`~hmz.flows.Permission` it runs under; a flow driving an agent unattended
        writes `bypass` and means it, because it watches its agent rather than gating it and a
        turn waiting on an approval nobody is there to give is a flow that has stopped. That is
        a different thing from a flow which never raised the question, and it is said
        differently.
      provider: Which account this agent's turns run as, by the name a provider of its CLI was
        made under, or "" for the CLI as whoever is at this machine already runs it. It is a
        setting of the agent rather than of the flow because it is the agent that signs in:
        two agents of one CLI, one on a subscription and one on somebody's gateway, are two
        accounts running at once, each refreshing its own token and neither able to read the
        other's -- which is what a provider is for.
      goals: Whether backend goals are available to this agent. This is always an explicit
        on/off setting with no inherited state, and it is the flow's to say.
      web_search: Whether this agent may search the web, and None -- which is what it comes
        at -- for one nobody has said either way about. Neither half of the switch goes on the
        command line then, so the CLI reads the internet, or does not, exactly as whoever
        installed it has it set up; the reason is the rung's reason, that a run nobody
        configured is one humanize is not the one answering for. On and off are both the
        flow's choice, read off the `online` of the permission it runs under -- on for work
        that wants the internet, off for a run that must read only this repository, one under a
        rate limit somebody is paying per query on, one whose answers have to be reproducible
        tomorrow. Either is said the same way on every backend that can be told, in both
        directions rather than only one: a CLI whose own web search is off until it is asked
        for is asked for it here, so that on means the same thing wherever it is read. A
        backend with no way of being told refuses being told, the way one with no service tier
        to send refuses `fast` -- an agent that quietly went on searching would be a setting
        that lies -- and refuses nothing where nothing was said, there being nothing then to
        lie about.
      budget: What each turn of each session of this agent may spend before it is cut off, or
        None for a turn that runs until it is done -- which is what an agent nobody has been
        asked about runs at, because a cap nobody chose is a cap that would truncate the one
        turn that needed the room. A conversation may be given one of its own, which is where
        a loop watching what it is costing says so.
    """

    #: Which of this class's own settings are properties of the model rather than of the CLI,
    #: by name. Empty here, because everything :class:`AgentConfig` itself holds is either the
    #: model or a thing about the work; a backend's own config says which of the settings it
    #: added are true of one model and false of the next.
    #:
    #: It exists for one moment: a fallback step onto the same CLI at a different model. That
    #: step carries the whole of what the backend was told, its own vocabulary included, since
    #: the CLI taking over still speaks it -- and a setting that was a fact about the model
    #: that just failed is the one part of that which stops being true when the model changes.
    #: Codex's `model_context_window` handed to the next model is a number that was measured
    #: on something else, and a window too large is a turn that overruns the model's own
    #: rather than a setting anybody would see in a log.
    #:
    #: Declared by the class that holds the setting rather than listed wherever a step is
    #: taken, so that a backend which gains one of these tomorrow says so beside the field
    #: itself. Named fields rather than guessed at: a name is a cheap thing to collide with,
    #: and a setting dropped because it happened to be spelled like a model's is a setting
    #: that goes missing for no reason a reader could find.
    of_model: ClassVar[tuple[str, ...]] = ()

    model: str
    effort: str
    service_tier: str = "default"
    machine: MachineConfig | None = None
    permission: str = UNSAID
    provider: str = ""
    goals: bool = True
    web_search: bool | None = None
    budget: Budget | None = None

    def __post_init__(self) -> None:
        # `auto` is the word a line uses for no rung at all, and this is where it stops being
        # a word: inside, the absence of a rung is "", which every driver already knows to say
        # nothing to its CLI about. Settled here rather than in each driver so that a config
        # built from a spec, from a settings file and from Python are the one same object --
        # and so that `effort == ""` stays the single question a driver has to ask.
        if self.effort == AUTO:
            object.__setattr__(self, "effort", "")
        if self.service_tier not in SERVICE_TIERS:
            raise ValueError(
                "service_tier must be one of "
                f"{', '.join(SERVICE_TIERS)}, not {self.service_tier!r}"
            )
        # Said where it is written, which for a config read back out of an older file is the
        # moment it is read: a rung no backend has a word for is one every driver would have
        # to answer for, so it is refused here where they all pass rather than reached down in
        # one of them as a key that is not there.
        if self.permission not in _SAYABLE:
            raise ValueError(
                f"permission must be one of {', '.join(PERMISSIONS)}, "
                f"not {self.permission!r}"
            )


def anchored(target: str) -> MachineConfig | None:
    """The machine an agent's turns land on, named the way a target is written.

    A machine that is already running is the answer whoever is at a prompt has: they name
    where the work goes -- a container, a host, this machine -- and nothing is brought up or
    taken down for them. Here rather than beside the machines themselves so that a caller
    which may not name that layer can still say where an agent works.

    Args:
      target: Where the work lands, as `ssh://HOST`, `docker://CONTAINER`, `tcp://HOST:PORT`
        or `local[:DIR]`, or "" for this machine.

    Returns:
      The machine to configure an agent with, or None to run its turns here.

    Raises:
      ValueError: If the target cannot be read, said where it is written rather than hours
        into the flow that was configured with it.
    """
    if not target:
        return None
    from hmz.coganchor import AnchorConfig
    from hmz.coganchor.machines import AnchoredConfig

    return AnchoredConfig(anchor=AnchorConfig(target=target))
