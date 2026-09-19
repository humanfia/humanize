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
    from collections.abc import Sequence

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
    "AgentDefaults",
    "Budget",
    "Goal",
    "Isolated",
    "Needs",
    "Remote",
    "Unserved",
    "anchored",
    "isolated",
    "rung",
    "searching",
    "tightest",
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

#: Every answer a config may be written with: the ladder, and the silence above it. Loosest
#: last, which is what :func:`tightest` reads it in.
_SAYABLE = (*PERMISSIONS, UNSAID)


class Unserved(ValueError):  # noqa: N818  -- what the setting is here, not what went wrong
    """Raised for a setting this backend has no way of carrying.

    Every shortfall in this layer was a bare `ValueError` with a sentence written where it
    was found, which is everything a person needs and nothing a caller can act on: the one
    place a flow's declaration meets a backend -- `hmz.runtime.flowing.driving.runs_at` --
    could read the sentence and re-raise it, and no more. To drop the one setting that could not be
    carried and settle the rest, it has to know which one that was, and a sentence is not a
    name.

    So the name travels beside the sentence, and the sentence is unchanged: this is a
    `ValueError` still, raised where the old one was and worded as the old one was, so every
    `except ValueError` that caught the shortfall before catches it now and every message
    still reads exactly as it read.

    Attributes:
      settings: The :class:`AgentConfig` fields this backend could not carry, by name. Almost
        always one -- a tier it cannot send, a rung it has no word for, a web search it
        cannot switch off. More than one where a config refuses a pair rather than either
        half of it: opencode withholding its permission table hears neither a narrowing rung
        nor a no about the web, and names both, because dropping one of them leaves the other
        just as unsayable.
    """

    def __init__(self, said: str, *settings: str) -> None:
        """Says what could not be carried, and which settings it was.

        Args:
          said: The sentence, exactly as a bare `ValueError` said it here before.
          settings: The `AgentConfig` field names, one or more.
        """
        super().__init__(said)
        self.settings = frozenset(settings)


def rung(permission: str) -> str:
    """The capability name for one rung, which is how a flow asks for it before its turn.

    Not every backend can be held to every rung. ACP's only word about permission is a
    request a client answers one tool call at a time, and nobody is at a prompt here; the dsh
    runtime bundles no confining executor. Both of them therefore refuse anything below
    `bypass` where the agent is made -- which is the right place for it, but it is also hours
    after somebody chose that backend for a flow that wanted `read-only`. So the ladder has
    words in the capability vocabulary too, one per rung, and
    :attr:`hmz.coganchor.agents.base.AgentBase.rungs` is what each backend answers with.

    Spelled here rather than wherever a name happens to be wanted, so that the driver that
    refuses a rung, the catalogue that lists it and the flow that asks for it are saying one
    word: `rung:` and the rung, in the wording :data:`PERMISSIONS` already uses.

    Args:
      permission: The rung, as :data:`PERMISSIONS` spells it.

    Returns:
      The capability name. :data:`UNSAID` has none and is not meant to: it is not a rung but
      the absence of one, every backend can be told nothing, and a capability every backend
      serves is not a thing to ask about.
    """
    return f"rung:{permission}"


def tightest(was: str, said: str) -> str:
    """The narrower of two rungs, where a rung is narrower than the silence above them all.

    Args:
      was: What the agent already carries.
      said: What the place declares.

    Returns:
      Whichever of them withholds more, and the silence only where both are silent.
    """
    return min(was, said, key=_SAYABLE.index)


def searching(was: bool | None, said: bool | None) -> bool | None:
    """The same, for whether the web may be read: off beats on, and on beats unsaid."""
    return min(was, said, key=(False, True, None).index)


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


class Goal:
    """What a flow writes beside an agent it runs under the backend's own goal feature.

    `pursue` is the agent keeping itself going toward an objective it decides for itself is
    met, and four backends have it. A flow built on that is not a flow any agent can drive,
    so it says which of its agents has to have one, by writing this where it declares them::

        class Agents(NamedTuple):
            worker: Annotated[AgentBase, Goal]

    and an agent whose backend has no goal feature is refused before the first turn rather
    than raising in the middle of one, which is where a loop would otherwise find out.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDefaults:
    """What a flow writes beside an agent to say what it runs that one at.

    What an agent may do, whether it keeps itself going, and whether it reads the internet
    are three things about the work rather than three things about the agent: a reviewer that
    may not write is a reviewer whichever CLI fills the place, and a run whose answers have to
    be reproducible tomorrow is one nobody may quietly switch searching back on for. So the
    flow says them, where it declares the place::

        class Agents(NamedTuple):
            builder: AgentBase
            reviewer: Annotated[
                AgentBase, AgentDefaults(permission="read-only", web_search=False)
            ]

    and a place that writes nothing settles nothing, which leaves whoever fills it exactly as
    they came.

    Attributes:
      permission: What the agent may do without being asked, as one of :data:`PERMISSIONS`,
        and :data:`UNSAID` -- the default -- for a place that never raised the subject. A
        place declaring a rung declares it of the work; one with nothing to declare has no
        business tightening whoever fills it, and no business loosening them either.
      goals: Whether the backend's own goal feature is available to it.
      web_search: Whether it may search the web, and None -- the default -- for a place that
        never raised that subject either. Three answers rather than two, because asking for
        the web is as much a declaration as refusing it, and neither is the same as not
        asking.
      insist: Whether a backend that cannot carry one of these refuses the run, which is what
        a place says nothing about and what every place did before there was a word for it.
        A declaration is meant to hold, and a backend that quietly went on searching would be
        a declaration that lies -- so the strict reading is the default and stays the default,
        and a flow that wants it need write nothing.

        `insist=False` is the other honest answer, and it is not "ignore it". It is: settle
        what this backend can be told, drop the one setting it cannot, and say out loud which
        place, which setting, and what the agent will actually do instead. Nothing is left
        carrying an answer the agent will not keep. What it buys is a flow that declares of
        the work rather than of the roster -- a benchmark written to run one task across every
        CLI there is declares `web_search=False` because that is what the comparison needs,
        and three backends with no way of being told should cost it three noisier cells
        rather than three cells that never ran::

            reviewer: Annotated[
                AgentBase, AgentDefaults(web_search=False, insist=False)
            ]

        It covers only the settings that would otherwise lie about themselves -- this rung,
        this answer about the web, and the tier and the effort a config reaches a backend
        already carrying. Deliberately not the features a flow calls: a place that wanted
        `steer` and got an agent without it is a place whose loop breaks at the first
        `interject`, and there is nothing kind about moving that failure from before the
        first turn to five hours in.

    Raises:
      ValueError: If the rung is not one there is, said as the flow is read rather than
        reached down in a driver as a key that is not there.
    """

    permission: str = UNSAID
    goals: bool = True
    web_search: bool | None = None
    insist: bool = True

    def __post_init__(self) -> None:
        if self.permission not in _SAYABLE:
            raise ValueError(
                f"permission must be one of {', '.join(PERMISSIONS)}, "
                f"not {self.permission!r}"
            )


class Remote:
    """What a flow writes beside an agent that may be pointed at another machine.

    Where an agent's turns land is not a setting anybody may reach for: a flow is written for
    one shape of work, and one whose agents read this project cannot have one of them reading
    somebody else's. So a flow says which of its agents may be sent elsewhere, by writing this
    where it declares them::

        class Agents(NamedTuple):
            builder: Annotated[AgentBase, Remote]
            reviewer: AgentBase

    and only that one may be given a machine. The others run here, whatever anybody chooses.
    """


@dataclass(frozen=True, slots=True)
class Isolated:
    """What a flow writes beside an agent that is to work in a container of its own.

    A machine nobody configures: the flow says the image, humanize starts the container, the
    project directory is mounted into it at the path it already has, and the agent -- which
    goes on running here, with its own credentials and its own trajectory -- reaches it
    through coganchor. What is isolated is the tools and the libraries a command finds, not
    the work::

        class Agents(NamedTuple):
            tester: Annotated[AgentBase, Isolated("python:3.12")]

    Attributes:
      image: The image to run, which needs a `python3` for coganchor's target half and
        whatever else the flow expects the agent to reach for.
    """

    image: str = "python:3.12"


@dataclass(frozen=True, slots=True, init=False)
class Needs:
    """What a flow writes beside an agent to say what filling the place takes.

    Most of what a flow builds on, every backend here serves and every machine holds. Some of
    it only some of them do -- a turn that can be talked to while it is still running, a turn
    held to a shape rather than asked to keep to one, a moment only some CLIs reach, a place
    whose tools are an image's rather than this machine's -- and a flow built on one of those
    is not a flow any agent can drive on any machine. Finding that out from the call that
    reached for it is finding it out hours in, so the flow says what the place takes where it
    declares the place::

        class Agents(NamedTuple):
            builder: Annotated[AgentBase, Needs("goal", "steer")]
            tester: Annotated[AgentBase, Remote, Needs(where=("remote", "isolated"))]

    and an agent whose backend serves none of it, or a machine whose settings do not come to
    it, is refused before the first turn. By name rather than by feature, and by the names
    everything else here already goes under: `hmz.runtime.flowing.checking.catalogue` is
    where they are written down, together with which backends serve each.

    Attributes:
      of_agent: What the backend filling the place has to serve, out of the agent vocabulary
        -- `goal`, `pursue`, `steer`, `shape`, `tools`, `fork`, `search`, `swarm`, `resume`,
        `narrate`, `tier:fast`, each rung it can be held to as `rung:<its own name>`, each
        kind of token as `counts:<its own name>`, a moment only some backends reach as
        `moment:<its own name>`, and a setting only some of their configs carry as
        `settings:<its own field>` -- Cursor's `settings:trust`, Codex's `settings:features`,
        ZCode's `settings:delivery`. One word apiece: a setting is asked for under the name
        derived from its field and under no second one, so that a field renamed leaves no name
        behind promising what nothing serves. What every backend here serves counts as served,
        so a place that names one of those is filled by anything rather than by nothing. Read
        off the driver class and off the facts written down about the CLI, neither of which
        needs an agent to have run, so a flow that cannot be driven by what it was given says
        so before it opens anything.

        `anchor:hooked` and `anchor:preloaded` are asked here and not under `where`. They are
        the two roads humanize reaches a turn down from *inside* the process it started -- a
        hook table written for one run, a variable the runtime reads before it starts -- and
        both are the CLI's own to take, declared by
        :meth:`hmz.coganchor.backends.Profile.tags`. An agent pointed at another machine loses
        them, since none of that reaches a process somewhere else, and it is refused rather
        than quietly given the weaker thing.
      where: What the machine its turns land on has to come to, out of the place vocabulary
        -- `remote`, `isolated`, `managed`, `linux`, `darwin`, and the road an anchor reaches
        it by, `anchor:native-cli` or `anchor:supervised`. Read off that machine's own
        settings, :attr:`~hmz.coganchor.machines.MachineConfig.capabilities`, so that a place which
        will not do is refused before an image has been pulled; a place asked for nothing in
        particular may be filled by an agent that was pointed nowhere, whose machine comes to
        nothing at all.

    Each name belongs to exactly one of the two, and one written in the other half is
    refused where the place is filled rather than answered wrongly. It used to be answered
    wrongly both ways: `Needs("isolated")` was satisfied by every backend there is, a machine
    capability carrying no backends and no backends meaning all of them, and
    `Needs(where=("anchor:hooked",))` was refused by every machine there is, no machine's
    settings having ever carried one. `hmz.runtime.flowing.checking.catalogue` is where the
    names are written down, each saying which half asks for it.

    Raises:
      TypeError: If `where` was written as one name rather than as a sequence of them.
        `Needs(where="remote")` is five capabilities spelled a letter each, and it is the one
        slip here a type checker cannot see -- a string being a sequence of strings -- so it
        is said as the flow is read rather than reached down in a refusal that names letters.
    """

    of_agent: frozenset[str]
    where: frozenset[str]

    def __init__(self, *of_agent: str, where: Sequence[str] = ()) -> None:
        """Initializes what a place takes, as the flow wrote it.

        Written out rather than generated, because what the flow writes is two different
        kinds of thing: what the agent has to serve reads as a list of words and is taken as
        one, and what the machine has to come to is said apart from it so that neither is
        ever read as the other.

        Args:
          *of_agent: What the backend filling the place has to serve.
          where: What the machine its turns land on has to come to.

        Raises:
          TypeError: If `where` was written as one name rather than as a sequence of them.
        """
        # A string is a sequence of strings, so this one slip is the one that would not be
        # caught anywhere: `where="remote"` is five capabilities spelled a letter each, and
        # the refusal it earns names letters. Everything else written wrong here is a type
        # error where the flow wrote it.
        if isinstance(where, str):
            raise TypeError(
                f"where must be a sequence of names rather than one name: "
                f"Needs(where=({where!r},))"
            )
        object.__setattr__(self, "of_agent", frozenset(of_agent))
        object.__setattr__(self, "where", frozenset(where))


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
        can check for themselves. Every rung is the flow's choice, written as an
        :class:`AgentDefaults` beside the place it declares and settled onto the agent before
        its first turn; a flow driving an agent unattended writes `bypass` and means it,
        because it watches its agent rather than gating it and a turn waiting on an approval
        nobody is there to give is a flow that has stopped. That is a different thing from a
        flow which never raised the question, and it is said differently.
      provider: Which account this agent's turns run as, by the name a provider of its CLI was
        made under, or "" for the CLI as whoever is at this machine already runs it. It is a
        setting of the agent rather than of the flow because it is the agent that signs in:
        two agents of one CLI, one on a subscription and one on somebody's gateway, are two
        accounts running at once, each refreshing its own token and neither able to read the
        other's -- which is what a provider is for.
      goals: Whether backend goals are available to this agent. This is always an explicit
        on/off setting with no inherited state, and it is the flow's to say: an
        `AgentDefaults` beside the place says it, and a place run under a `Goal` has them on
        and cannot be talked out of it.
      web_search: Whether this agent may search the web, and None -- which is what it comes
        at -- for one nobody has said either way about. Neither half of the switch goes on the
        command line then, so the CLI reads the internet, or does not, exactly as whoever
        installed it has it set up; the reason is the rung's reason, that a run nobody
        configured is one humanize is not the one answering for. On and off are both the
        flow's choice, written as an `AgentDefaults` beside the place -- on for work that
        wants the internet, off for a run that must read only this repository, one under a
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


def isolated(image: str, workspace: str | None = None) -> MachineConfig:
    """A container of the agent's own, holding the project directory it is to work in.

    What :class:`Isolated` comes to, built where a flow's declaration is read rather than by
    whoever is choosing agents: an isolated agent is one nobody configures, so nothing above
    this is asked which image or which directory.

    Args:
      image: The image to run.
      workspace: The directory to mount, defaulting to the one the flow is running in. It is
        mounted rather than copied, at the path it already has, so the work outlives the
        container.

    Returns:
      The machine to configure such an agent with.
    """
    from hmz.coganchor.machines import DockerConfig

    return DockerConfig(image=image, workspace=workspace)
