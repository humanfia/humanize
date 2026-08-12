"""What starts a flow: the file it is in, the agents it takes, and the line naming both.

The line is read here rather than beside the command that carries it out, because the terminal
interface starts a flow from that same line and then keeps the agents -- which is what lets
something typed while the flow runs reach the one working. A reader that lived in the command
line would be one the interface had to reach up into.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    NamedTuple,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from hmz import backends, home

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from pydantic import BaseModel

    from .agents import AgentBase, Isolated, Moment, Remote


#: How many arguments a flow's entry point takes when it says it can be set up with
#: something: the agents, the task, and the model that says what there is to set.
_WITH_A_CONFIG = 3

#: A flow's entry point: called with the agents and the task, and done when it returns --
#: or, for one written as `async def run`, when what it returns has been awaited. Which of
#: the two a flow is, is the flow's own business: `Runner.run` waits for it either way.
type Flow = Callable[..., Awaitable[None] | None]


class NotAFlow(ValueError):  # noqa: N818  -- the name SPEC.md gives it
    """What a command line named, when it was not a flow for the agents it was given.

    Its own kind of error, so that a flow failing as it is imported -- one that reads a prompt
    file beside it and does not find it -- is left to fail as it would anywhere, rather than
    being reported as a command line to correct.
    """


class Running(NamedTuple):
    """One flow that is running now.

    Attributes:
      flow: What it was asked for as -- the name a command line gave, or the one a flow asked
        another for, which is the name worth showing either way.
      since: When it started, on the monotonic clock.
    """

    flow: str
    since: float


#: The flows running now, in the order they started: the one somebody ran, then whatever it
#: called, then whatever that called, each beside the thread it is running on. Kept here
#: rather than asked of the flows, which is the one thing a flow cannot be asked -- it is a
#: Python file and may branch any way it likes -- and read by the interface to say what is
#: running under what.
#:
#: A list rather than a stack, because a flow written as a coroutine may have two of them
#: going at once, and both are running. Under a lock, since a flow runs on whichever thread
#: took it and the interface reads while they run.
_RUNNING: list[tuple[Running, threading.Thread]] = []
_TELLING = threading.Lock()


def running() -> tuple[Running, ...]:
    """Every flow running now, the one that was started first and whatever it called after it.

    A flow says it has ended as it ends, however it ends -- but only a flow that got the
    chance to. One whose thread has gone was abandoned where it stood rather than finished:
    an interface taken down under it, a test that let go of it. So what is running is checked
    against the threads running it, and a flow with no thread left is not one of them.

    Returns:
      One apiece, in the order they started. Empty where nothing is running.
    """
    with _TELLING:
        _RUNNING[:] = [one for one in _RUNNING if one[1].is_alive()]
        return tuple(flow for flow, _ in _RUNNING)


def _entered(flow: str) -> Running:
    """Writes down that a flow has started, for whatever is watching the run.

    Args:
      flow: What it was asked for as.

    Returns:
      The record, to be handed back when it ends.
    """
    one = Running(flow, time.monotonic())
    with _TELLING:
        _RUNNING.append((one, threading.current_thread()))
    return one


def _left(one: Running) -> None:
    """Writes down that a flow has ended, however it ended.

    Args:
      one: What :func:`_entered` answered with.
    """
    with _TELLING:
        _RUNNING[:] = [held for held in _RUNNING if held[0] is not one]


class Place(NamedTuple):
    """One of the agents a flow drives, as the flow's own annotation declared it.

    Attributes:
      name: What the flow calls it, or "" for a flow that said how many it drives and no more.
      person: Whether it is the person at the prompt, who is handed over rather than chosen.
      moments: The moments the agent filling it has to run, which the flow said by writing
        `Annotated[AgentBase, Moment.PERMISSION_REQUEST]` where it declared the place. Empty
        where it asked for nothing in particular, which is most places.
      goal: Whether the flow runs this one under the backend's own goal feature, which it
        said by writing `Annotated[AgentBase, Goal]` where it declared the place. Only three
        backends have one, so a flow built on it is not a flow any agent can drive.
      where: Where the agent filling it may work, which the flow said the same way -- `Remote`
        for one that may be pointed at another machine, an `Isolated` for one that works in a
        container the flow itself names the image of. None for a place the flow said nothing
        about, which runs here and may not be sent anywhere: a flow is written for a shape of
        work, and where its agents work is the flow's to say rather than a setting somebody
        reaches for.
    """

    name: str
    person: bool
    moments: frozenset[Moment]
    where: type[Remote] | Remote | Isolated | None = None
    goal: bool = False


def drives(flow: str | os.PathLike[str]) -> tuple[str, ...]:
    """What a flow calls each of the coding agents it drives, in the order it takes them.

    Read without being given any, so that a caller can ask before it has them -- which is
    what choosing the agents for a flow means.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      One name per agent its entry point declares that somebody has to choose, which is how
      many it has to be given. A flow that declares a plain tuple has not named them, and each
      is "" -- the count is all it said. A place it declared as a :class:`HumanAgent` is not
      among them: nobody chooses what the person at the prompt runs, so nobody is asked.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return tuple(place.name for place in wanted(flow))


def configures(flow: str | os.PathLike[str]) -> type[BaseModel] | None:
    """What a flow can be set up with before it is run, if it takes anything at all.

    A flow says so by taking a third argument annotated with a pydantic model or None: the
    model is the whole of what may be asked, since the fields, their types, what each one is
    for and the combinations the flow refuses are already written down in it. So whatever is
    starting a flow can put the questions to somebody without knowing what any of them mean.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      The model to ask with, or None for a flow that takes the agents and the task and
      nothing else -- which is most of them, and is what every flow was before this.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return _read(flow)[3]


def wanted(flow: str | os.PathLike[str]) -> tuple[Place, ...]:
    """Every agent a flow needs chosen for it, and what each of them has to be able to do.

    What :func:`drives` says, and what the flow asked of each place besides a name: a flow
    that hangs a hook on a moment only some backends run says so in the annotation, and
    whoever is choosing the agents can then offer only the ones that would work.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      One place per agent somebody has to choose, in the order the flow takes them.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return tuple(place for place in _read(flow)[1] if not place.person)


def _read(
    flow: str | os.PathLike[str],
) -> tuple[
    Flow,
    tuple[Place, ...],
    Callable[..., tuple[AgentBase, ...]],
    type[BaseModel] | None,
]:
    """Loads a flow and reads what it says about the agents it drives.

    Args:
      flow: The flow: one that came with humanize, by name, or a file of your own.

    Returns:
      Its entry point, one place per agent it drives, what to hand those agents over as --
      the named tuple the flow declared, or a plain one where it declared that -- and the
      model it can be set up with, or None where it takes no setting up.

    Raises:
      NotAFlow: If the file is not there, is not a flow -- nothing in it marked `@flow()`, or
        one whose `agents` cannot be read or says nothing about how many it takes.
    """
    from hmz.flows import find, inside, loaded

    # Which of the file's flows was asked for, before the name is resolved to a file: a file
    # may hold several, and `humanize1:gen-plan` is one of them.
    wanted = inside(str(flow))
    # Resolved here rather than by whoever is starting one, so that a name works wherever a
    # flow is named -- a command line, an interface, a `Runner` written by hand.
    flow = find(str(flow))
    # The same test `hmz.flows` applies, and for the same reason: a place that cannot
    # be read holds no flow, which `Path.is_file` would raise about rather than answer.
    if not os.path.isfile(flow):  # noqa: PTH113
        raise NotAFlow(f"{flow}: {_unfetched(str(flow))}")
    read = loaded(flow)
    run = _entry(read, wanted)
    if run is None:
        # A file that holds several flows names each of them after itself, so whoever asked
        # for the file alone -- or for one of them under a name it does not have -- is a
        # colon away from what they meant, and saying which ones is what ends it.
        holds = [f"{Path(flow).stem}:{one}" for one in _holds(read)]
        missing = f"{flow}: nothing in it is a flow called {wanted!r}"
        if wanted and holds:
            raise NotAFlow(f"{missing}; it holds {', '.join(holds)}")
        if wanted:
            raise NotAFlow(missing)
        if holds:
            raise NotAFlow(
                f"{flow}: nothing in it is marked @flow(), and it holds "
                f"{', '.join(holds)} -- name the one to run"
            )
        raise NotAFlow(
            f"{flow}: nothing in it is marked @flow() -- a flow is a function marked with "
            "it, which is how a file says which of the functions in it is one"
        )
    try:
        # A function, so that what is read below is what the entry point will be called
        # with: a class or a partial answers with annotations that are somebody else's.
        # Extras and all: what a flow wrote beside the type is what it asks of the agent.
        hinted = (
            get_type_hints(run, include_extras=True) if inspect.isfunction(run) else {}
        )
        declared = hinted.get("agents")
    except NameError as unresolved:
        # A flow whose agents are imported under TYPE_CHECKING states how many it drives
        # where nothing can read it back, which is the one thing a flow is asked to say.
        raise NotAFlow(
            f"{flow}: the flow's agents cannot be read here ({unresolved}) -- import what "
            "the annotation names at runtime, so the count it states can be checked"
        ) from unresolved
    # A named tuple is a tuple that also says what each of its places is for, and `_fields`
    # is where it says it. `_make` builds one from a sequence, exactly as `tuple` does, so
    # the flow is handed the type it asked for either way.
    if (
        run is not None
        and declared is not None
        and (fields := getattr(declared, "_fields", None))
    ):
        kinds = _kinds(declared, run)
        return (
            run,
            tuple(_place(at, kinds.get(at)) for at in fields),
            declared._make,
            _setting(run, hinted),
        )
    # `tuple[AgentBase, ...]` is any number of them, which is no answer to the question.
    declares = get_args(declared)
    if run is None or get_origin(declared) is not tuple or Ellipsis in declares:
        raise NotAFlow(
            f"{flow}: a flow is a function marked @flow() taking (agents, task), whose "
            "agents are annotated with a tuple of a fixed length -- how many agents the "
            "flow drives -- or with a NamedTuple of them, which also says what each is for"
        )
    return (
        run,
        tuple(_place("", kind) for kind in declares),
        tuple,
        _setting(run, hinted),
    )


def calls(flow: str | os.PathLike[str]) -> Flow:
    """One flow, ready for another flow to run: what it marked, found by name.

    A flow is a loop over agents, and a loop worth having is one another loop can reach for::

        from hmz.flows import flow
        from hmz.runner import calls

        @flow
        def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
            plan = calls("official/humanize1:gen-plan")
            plan(agents, f"plan this first: {task}")
            agents[0].new()(task)

    The name is the one `-f` takes -- `ralph_loop`, `official/rlar`, `humanize1:gen-plan`, a
    path of your own -- so a flow reaches another flow the way a person does, and a flowverse
    is a library as well as a menu.

    What comes back is the flow's own function, with the run written down around it: what is
    running is what the interface shows, and a flow that called another must not read as the
    flow that was started. It is called the way the flow itself is -- the agents, the task,
    and the config for one that says it takes one -- and answers with whatever the flow
    answers with, so a flow written as a coroutine is awaited by whoever called it::

        await calls("official/rlar")(agents, task)

    Args:
      flow: The flow to call, by the name `-f` takes.

    Returns:
      Something to call with the agents and the task.

    Raises:
      NotAFlow: If there is no such flow, or it is not one. Raised here rather than at the
        call, so that a flow which asks for another by a name that is wrong says so when it is
        asked for rather than an hour into a loop.
    """
    run, places, make, setting = _read(flow)
    named = str(flow)

    def calling(
        agents: Sequence[AgentBase],
        task: str,
        config: BaseModel | dict[str, Any] | None = None,
    ) -> Awaitable[None] | None:
        driven = _handed(named, places, make, agents)
        # Read back through the flow's own model, which is what refuses a config a flow does
        # not take and one it takes another of -- and what puts the settings through its own
        # validators at the moment it is about to run, exactly as a run of it does.
        given = None if config is None else _set_up(named, setting, config)
        settings = () if setting is None else (given,)
        started = _entered(named)
        _wrote(driven, "called", flow=named, task=task)
        try:
            answered = run(driven, task, *settings)
        except BaseException:
            _left(started)
            _wrote(driven, "returned", flow=named)
            raise
        if inspect.isawaitable(answered):
            # A flow written as a coroutine has not run yet: it is running while whoever
            # called it awaits it, so what says it is running has to last that long too.
            return _awaited(answered, driven, started, named)
        _left(started)
        _wrote(driven, "returned", flow=named)
        return None

    return calling


async def _awaited(
    answered: Awaitable[None],
    driven: tuple[AgentBase, ...],
    started: Running,
    named: str,
) -> None:
    """Waits for a called flow that is a coroutine, and writes down that it ended.

    Args:
      answered: What calling it gave back.
      driven: The agents it was called with, for the cycle to write to.
      started: What :func:`_entered` answered with.
      named: The flow, as it was asked for.
    """
    try:
        await answered
    finally:
        _left(started)
        _wrote(driven, "returned", flow=named)


def _handed(
    flow: str,
    places: tuple[Place, ...],
    make: Callable[..., tuple[AgentBase, ...]],
    agents: Sequence[AgentBase],
) -> tuple[AgentBase, ...]:
    """The agents a called flow is handed, as the tuple that flow declared.

    A flow is called with what it drives, so a caller hands over as many agents as the flow
    declares -- and may hand over one fewer where the flow talks to the person, since the
    person is made rather than chosen. Nothing is renamed: the agents belong to the flow that
    was started, and a name changed under it would change what the run has already been
    written down as.

    Args:
      flow: The flow being called, for what a refusal says.
      places: What it declared.
      make: What to build its agents as -- the named tuple it declared, or a plain one.
      agents: What the caller handed over.

    Returns:
      The agents, as the flow declared them.

    Raises:
      NotAFlow: If that is the wrong number of them, if one of them cannot run a moment the
        flow says that place has to, or if one is somewhere the flow does not put it.
    """
    from .agents import HumanAgent

    given = list(agents)
    asked = [place for place in places if not place.person]
    if len(given) == len(places):
        driven = given
    elif len(given) == len(asked):
        # The person is made rather than chosen, exactly as a run of the flow makes one.
        taking = iter(given)
        driven = [HumanAgent() if place.person else next(taking) for place in places]
    else:
        raise NotAFlow(
            f"{flow}: the flow drives {len(asked)} agents, {len(given)} given"
        )
    for agent, place in zip(driven, places, strict=True):
        if short := place.moments - type(agent).moments:
            raise NotAFlow(
                f"{flow}: {place.name or 'the agent'} has to run "
                f"{', '.join(sorted(short))}, which {agent.backend} does not"
            )
        _lands(flow, agent, place)
    return make(driven)


def _wrote(driven: tuple[AgentBase, ...], event: str, **said: Any) -> None:
    """Writes one line about a called flow into the run's own record, where there is one.

    Through the agents rather than through anything of ours: the cycle belongs to the run that
    was started, the agents were handed it as it began, and a flow called from a `Runner` that
    opened none -- a flow run from a test, a flow called from a flow called from nothing --
    has nowhere to write and nothing to say.

    Args:
      driven: The agents the called flow was handed.
      event: What happened.
      said: What is worth saying about it.
    """
    # Asked what it is rather than taken as read: what an agent asks of a journal is that it
    # can be told a session was opened, and this is asking it for something else.
    from .cycle import Cycle

    for agent in driven:
        if isinstance(agent.cycle, Cycle):
            agent.cycle.write(event, **said)
            return


def _lands(flow: str | os.PathLike[str], agent: AgentBase, place: Place) -> None:
    """Settles where one agent's turns land, and refuses a machine the flow did not allow.

    Where an agent works is the flow's to say and not a setting anybody may reach for: a flow
    is written for one shape of work, and one whose agents read this project cannot have one
    of them reading somebody else's. So a place says nothing and its agent runs here, or says
    `Remote` and its agent may be pointed at a machine by whoever chose it, or says `Isolated`
    and the machine is the flow's own -- a container of the image it named, which nobody else
    has any say in.

    Args:
      flow: The flow, for what a refusal says.
      agent: The agent filling the place.
      place: What the flow declared.

    Raises:
      NotAFlow: If the agent was configured to work somewhere the flow does not put it, or if
        it has already opened a session, which is a conversation that cannot be moved.
    """
    from .agents import Isolated, isolated

    called = place.name or "the agent"
    if isinstance(place.where, Isolated):
        if agent.config.machine is not None:
            raise NotAFlow(
                f"{flow}: {called} works in a container of this flow's own, so there is "
                "nothing to point it at"
            )
        try:
            agent.runs_on(isolated(place.where.image))
        except RuntimeError as opened:
            raise NotAFlow(f"{flow}: {called} {opened}") from opened
        return
    if place.where is None and agent.config.machine is not None:
        raise NotAFlow(
            f"{flow}: {called} runs on this machine -- this flow does not say it works "
            "anywhere else, so it cannot be pointed at one"
        )


def _unfetched(named: str) -> str:
    """Why a flow that was named is not there, as far as that can be told.

    Args:
      named: What was asked for, as it was written.

    Returns:
      The reason: that the flowverse it named has not been fetched yet, where that is what
      happened, and otherwise that there is no such file. A flowverse is offered before it is
      fetched -- `official` is there from the start -- so "no such file" would be the answer
      to a name that is right, given by the one thing that knows it has not been downloaded.
    """
    from hmz.flows import flowverses

    whose, _, rest = named.partition("/")
    for verse in flowverses():
        if verse.name == whose and rest and not verse.fetched:
            return (
                f"the {whose} flowverse has not been fetched yet -- open /flow and press "
                "ctrl+r on it"
            )
    return "no Python file to read a flow from"


def _entry(inside: dict[str, Any], wanted: str) -> Callable[..., Any] | None:
    """The flow a file was asked for, out of everything in it.

    By what it was marked with and never by what it is called: a file is run to be read, and
    the functions it leaves behind are its flows, whatever it imported and whatever it broke a
    flow into. `@flow()` is the one the file holds under its own name.

    Args:
      inside: What running the file left behind.
      wanted: Which of its flows was asked for, or "" for the one it holds under its own name.

    Returns:
      The entry point, or None where the file holds no such flow.
    """
    from hmz.flows import Flow

    for one in inside.values():
        said = getattr(one, "__humanize_flow__", None)
        if isinstance(said, Flow) and said.name == wanted:
            return cast("Callable[..., Any]", one)
    return None


def _holds(inside: dict[str, Any]) -> list[str]:
    """What a file calls each of the flows it holds under a name of its own.

    Args:
      inside: What running the file left behind.

    Returns:
      One name apiece, in the order the file declared them. Its `run` is not among them: it
      is the flow the file holds under its own name, and has no name of its own.
    """
    from hmz.flows import Flow

    said = (getattr(one, "__humanize_flow__", None) for one in inside.values())
    return [one.name for one in said if isinstance(one, Flow) and one.name]


def _set_up(
    flow: str | os.PathLike[str],
    setting: type[BaseModel] | None,
    config: BaseModel | dict[str, Any],
) -> BaseModel:
    """Reads a config back into the model the flow has just declared.

    Read back rather than taken as it comes, because a flow is loaded by running its file:
    the class it declared last time is not the class it declares this time, so what was set
    up against one is a stranger to the other. What survives that is the fields, which is
    what a config is -- and reading them back is also what puts them through the flow's own
    validators one last time, at the moment the flow is about to run. A mapping of the same
    fields, which is what a YAML file of them reads as, is read back the same way.

    Args:
      flow: The flow, for what a refusal says.
      setting: What it says it can be set up with, or None where it said nothing.
      config: What it is being set up with.

    Returns:
      The same settings, as an instance of the model this loading of the flow declared.

    Raises:
      NotAFlow: If the flow takes no config, or takes another one, or will not accept these
        settings -- each of which is a caller to correct before anything runs.
    """
    from pydantic import ValidationError

    if setting is None:
        raise NotAFlow(f"{flow}: the flow takes no config, and one was given")
    if not isinstance(config, dict) and type(config).__name__ != setting.__name__:
        raise NotAFlow(
            f"{flow}: the flow takes a {setting.__name__} to be set up with, not a "
            f"{type(config).__name__}"
        )
    fields = config if isinstance(config, dict) else config.model_dump()
    try:
        return setting.model_validate(fields)
    except ValidationError as refused:
        raise NotAFlow(f"{flow}: {refused}") from refused


def _setting(run: Flow, hinted: dict[str, object]) -> type[BaseModel] | None:
    """The model a flow says it can be set up with, read off its third argument.

    Third rather than named, because that is where it is: `run(agents, task, config)` is the
    entry point, and a flow which takes nothing more has two arguments and is left alone.

    Args:
      run: The flow's entry point.
      hinted: Its annotations, resolved.

    Returns:
      The model, or None where the flow takes no third argument or annotated it with
      something that is not one -- a flow is not refused for the shape of an argument
      nothing has to fill.
    """
    from pydantic import BaseModel

    taken = list(inspect.signature(run).parameters)
    if len(taken) < _WITH_A_CONFIG:
        return None
    kind = hinted.get(taken[_WITH_A_CONFIG - 1])
    # `Model | None` is the annotation a flow writes, and is two arguments to a union; one
    # written as the model alone is the same question with no way to answer it as unasked.
    for said in (*get_args(kind), kind):
        if isinstance(said, type) and issubclass(said, BaseModel):
            return said
    return None


def _kinds(declared: type, run: Flow) -> dict[str, object]:
    """What a flow annotated each place of its agents with, resolved where it can be.

    Against the flow's own globals, which are where its names are: a flow loaded by running
    the file is not a module anything can look up, so the class cannot resolve its own
    annotations on its own.

    Args:
      declared: The named tuple the flow declared its agents as.
      run: Its entry point, which is what carries those globals.

    Returns:
      One annotation per place, resolved if they could be resolved and as they were written
      if they could not -- a name that will not resolve is still a name to read.
    """
    try:
        return dict(
            get_type_hints(
                declared, globalns=dict(run.__globals__), include_extras=True
            )
        )
    except (NameError, TypeError):
        return dict(getattr(declared, "__annotations__", {}))


def _place(name: str, kind: object) -> Place:
    """One place in a flow's agents, read off what the flow annotated it with.

    Args:
      name: What the flow calls it, or "" where it named none of them.
      kind: The annotation, which may be an `Annotated` carrying what the flow asks of
        whoever fills the place.

    Returns:
      The place.
    """
    moments = frozenset(_moments(kind))
    where = _where(kind)
    goal = _goal(kind)
    if get_origin(kind) is Annotated:
        kind = get_args(kind)[0]
    return Place(
        name=name, person=_is_person(kind), moments=moments, where=where, goal=goal
    )


def _where(kind: object) -> type[Remote] | Remote | Isolated | None:
    """Where a flow said the agent filling a place may work.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      What it wrote beside the type -- `Remote`, or an `Isolated` naming an image -- and None
      for a place it annotated with the type alone, which is one that works here.
    """
    from .agents import Isolated, Remote

    if get_origin(kind) is not Annotated:
        return None
    for said in get_args(kind)[1:]:
        if said is Remote or isinstance(said, (Remote, Isolated)):
            return said
    return None


def _goal(kind: object) -> bool:
    """Whether a flow said the agent filling a place is run under its backend's goal feature.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      True if it wrote `Goal` beside the type, and False for a place annotated with the type
      alone -- which is one driven by turns like every other.
    """
    from .agents import Goal

    if get_origin(kind) is not Annotated:
        return False
    return any(said is Goal for said in get_args(kind)[1:])


def _moments(kind: object) -> tuple[Moment, ...]:
    """The moments a flow asked the agent filling a place to run.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      Whatever moments it wrote beside the type, in the order it wrote them, and nothing at
      all for a place it annotated with the type alone.
    """
    from .agents import Moment

    if get_origin(kind) is not Annotated:
        return ()
    return tuple(said for said in get_args(kind)[1:] if isinstance(said, Moment))


def _is_person(kind: object) -> bool:
    """Whether a place in a flow's agents is the person at the prompt.

    Args:
      kind: What the flow annotated that place with, which is the class itself, or its name
        where the flow put its annotations off until they are asked for.

    Returns:
      True if it is a `HumanAgent`, which is a place nobody is asked to configure.
    """
    from .agents import HumanAgent

    if isinstance(kind, str):
        # Read by the word it names rather than by what that word means, which is all there
        # is to go on: the first thing inside an `Annotated[...]` is the type it is about.
        said = kind.removeprefix("Annotated[").split(",")[0].strip()
        return said.rpartition(".")[2] == HumanAgent.__name__
    return kind is HumanAgent


def _finished(running: Awaitable[None]) -> None:
    """Runs a flow that is a coroutine, until it returns.

    A flow may be written as ``async def run``, which is how one drives many agents at once:
    the loop is the flow's own, started here and closed when the flow returns, so that a flow
    which awaits nothing and one which awaits ten thousand turns are both just run. Starting
    the flow is the same call either way -- whatever is driving one is driving a flow, not an
    event loop, and none of them has to know which kind it took.

    Args:
      running: The flow, as the coroutine calling it made.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    async def flowing() -> None:
        # A coroutine of our own around it: `asyncio.run` takes one of those, and what a
        # flow answered with is whatever awaiting it is spelled as where the flow was written.
        await running

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(flowing())  # nothing is turning here, which is the ordinary way in
        return
    # Started from a thread that is already running a loop of its own -- an interface, a test.
    # A flow cannot be run on that one: it would be the flow waiting for turns that are
    # waiting for the loop the flow is holding, which is a run that never takes its first.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="humanize-flow") as apart:
        apart.submit(asyncio.run, flowing()).result()


class Runner:
    """A flow, loaded from a file and handed the agents it was written for.

    A flow is a Python file with a ``run(agents: tuple[...], task: str)`` in it, and the tuple
    is how many agents it drives -- the one thing about a flow that cannot be read off the
    command line starting it. Checking it before anything runs is what keeps a two-agent flow
    started with one agent from failing on an unpacking hours into a loop, with a turn's work
    already behind it. A flow that declares a NamedTuple instead has also said what each of
    its agents is for, and they are called that from here on.
    """

    def __init__(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        config: BaseModel | dict[str, Any] | None = None,
    ) -> None:
        """Loads the flow and holds the agents to drive it with.

        Args:
          flow: The Python file the flow is written in. It is run to be read, so whatever it
            does as it is imported happens here, and fails here as it would anywhere.
          agents: The agents to hand it, as many as it declares.
          config: What it was set up with, for a flow that says it can be -- an instance of
            the model :func:`configures` answers with, or the fields to build one from, which
            is what a YAML file of them reads as. None is a flow left as it comes, and is
            what a flow that takes no setting up is given either way.

        Raises:
          NotAFlow: If the file is not there, is not a flow -- nothing in it marked
            ``@flow()``, or one whose ``agents`` cannot be read or says nothing about how many
            it takes -- or is a
            flow that drives a different number of agents than were given, or one of them
            cannot run a moment the flow said that place has to, or was set up with something
            that is not what it asked for.
        """
        from .agents import HumanAgent

        run, places, make, setting = _read(flow)
        if config is not None:
            config = _set_up(flow, setting, config)
        asked = [place for place in places if not place.person]
        if len(asked) != len(agents):
            raise NotAFlow(
                f"{flow}: the flow drives {len(asked)} agents, {len(agents)} given"
            )
        # Before the first turn, for the reason the count is: a flow that hangs a hook on a
        # moment its agent does not run would otherwise find out hours into a loop, from a
        # hook that raised where it was hung rather than from the line that chose the agent.
        for agent, place in zip(agents, asked, strict=True):
            if short := place.moments - type(agent).moments:
                raise NotAFlow(
                    f"{flow}: {place.name or 'the agent'} has to run "
                    f"{', '.join(sorted(short))}, which {agent.backend} does not"
                )
            if place.goal and not type(agent).pursues:
                raise NotAFlow(
                    f"{flow}: {place.name or 'the agent'} is run under a goal, which "
                    f"{agent.backend} has no feature for"
                )
            _lands(flow, agent, place)
        # The person at the prompt is made here rather than given: nobody chooses what they
        # run, so nothing upstream of this was ever asked about them.
        given = iter(agents)
        driven = [HumanAgent() if place.person else next(given) for place in places]
        for agent, place in zip(driven, places, strict=True):
            if place.name:
                agent.rename(place.name)
        self._run: Flow = run
        # Only for a flow that said it takes one, so that every flow written before there
        # was such a thing is still called with the two arguments it declares.
        self._config: BaseModel | None = config if setting is not None else None
        self._setting = setting
        # As the flow declared them: a flow whose agents are a NamedTuple reaches them by
        # name, and one that unpacks a plain tuple sees no difference.
        self._agents = make(driven)
        self._flow = str(
            flow
        )  # as it was named, which is what a run of it is named after

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """Every agent this drives, in the order the flow takes them.

        Which is not what it was given: a flow that says it talks to the person is driving
        one more agent than anybody chose, and whatever is driving the flow has to reach
        that one too -- it is the one thing here that answers with what was typed.
        """
        return tuple(self._agents)

    def run(self, task: str) -> None:
        """Runs the flow in this directory, for as long as it keeps running.

        The run is written down as it happens: which agents were driven, at what, and which
        sessions each of them opened. Nothing else knows a session was part of a run -- the
        backends log them one by one, under ids of their own -- and the run is over the moment
        this returns, however it returns.

        A flow written as ``async def run`` is run to its return here too, on a loop of its
        own: this waits for the flow either way, so that whatever started one is holding a
        run rather than a coroutine somebody has to remember to await.

        Args:
          task: What the flow is to have its agents do.
        """
        import inspect

        from .cycle import Cycle

        # Written down as running before it is: what a flow calls is written down the same
        # way, so that whatever is watching reads one list of what is running under what,
        # rather than a flow it was told about and a flow it was not.
        started = _entered(self._flow)
        try:
            with Cycle(self._flow, self._agents, task) as cycle:
                for agent in self._agents:
                    agent.cycle = cycle
                if self._setting is None:
                    running_now = self._run(self._agents, task)
                else:
                    # As it was set up, or as it comes: a flow that takes a config takes None
                    # for the run nobody set up, which is the default the flow declared.
                    running_now = self._run(self._agents, task, self._config)
                # Read off what the call answered rather than off the function: a flow is what
                # it does when it is called, and one wrapped in something of its own -- a
                # decorator that times its rounds -- is the same flow.
                if inspect.isawaitable(running_now):
                    _finished(running_now)
        finally:
            _left(started)


def read_agent(
    spec: str,
) -> tuple[backends.Profile, str, str, str, str | None]:
    """Reads and validates one command-line agent specification.

    Args:
      spec: The short or written-out form accepted by ``-a``.

    Returns:
      The backend, model, effort, provider and optional permission rung.

    Raises:
      ValueError: If the specification is malformed or names no permission rung there is.
    """
    from .agents import PERMISSIONS

    parsed = backends.read(spec)
    permission = parsed[-1]
    if permission is not None and permission not in PERMISSIONS:
        raise ValueError(
            f"permission must be one of {', '.join(PERMISSIONS)}, not {permission!r}"
        )
    return parsed


def flow_and_agents(
    argv: list[str],
) -> tuple[str, list[AgentBase], str, dict[str, Any] | None]:
    """Reads an `hmz exec` line into a flow, the agents to drive it, the task, and its setup.

    A flow says how many agents it drives, and this is where they come from: one for each, in
    the order the flow takes them, at the model and effort each is to run at.

    Args:
      argv: What followed the command name.

    Returns:
      The flow's path, the agents to drive it with, the task, and what to set the flow up
      with -- the YAML file `-c` named, read but not yet checked against the flow's own
      model, or None where the line named none.

    Raises:
      SystemExit: If the line does not name a flow and an agent apiece, or names a config
        that cannot be read, as argparse rejects it.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz exec", description="Run an agent flow in this directory."
    )
    parser.add_argument(
        "-f",
        "--flow",
        required=True,
        metavar="FLOW",
        help="the flow to drive: one humanize ships or a flowverse holds, by name, or a file "
        "of your own; `<flow>:<name>` for one of several in a file",
    )
    parser.add_argument(
        "-a",
        "--agent",
        action="append",
        # Once for each agent the flow drives, which for a flow that talks only to the person
        # at the prompt is none: the person is handed over rather than chosen, so a line that
        # named one would be naming what nobody picks. A line short of an agent the flow does
        # need is caught where every other miscount is, by the flow's own declaration.
        default=[],
        dest="agents",
        metavar="CLI/MODEL:EFFORT",
        help="one agent, repeated once for each the flow drives, in the order it takes "
        "them; also written cli=CLI,model=MODEL,effort=EFFORT with optional "
        "permission=PERMISSION. CLI is one of "
        f"{', '.join(sorted(one.name for one in backends.PROFILES))}",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="a YAML file of what to set the flow up with, one field per line, as the flow "
        "declares them; only for a flow that says it can be set up",
    )
    parser.add_argument(
        "task",
        help="what the flow is to have the agents do, after -- if it starts with a dash",
    )
    args = parser.parse_args(argv)
    held = None
    if args.config is not None:
        try:
            held = set_up_from(args.config)
        except ValueError as why:
            parser.error(str(why))

    # Only now that the line is known to name agents: `--help` has already exited, and it
    # should not have paid for three backends to say what it takes.
    from .agents import DRIVEN

    agents: list[AgentBase] = []
    for spec in args.agents:
        try:
            profile, model, effort, provider, permission = read_agent(spec)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
        agent, config = DRIVEN[profile.name]
        # Named rather than looked up: an account that is not there is caught by the agent
        # the first time it needs one, which says whose it was and what it was called.
        configured = (
            config(model=model, effort=effort, provider=provider)
            if permission is None
            else config(
                model=model,
                effort=effort,
                provider=provider,
                permission=permission,
            )
        )
        agents.append(agent(configured))
    return args.flow, agents, args.task, held


def set_up_from(said: str | os.PathLike[str]) -> dict[str, Any]:
    """Reads what a flow is to be set up with out of a file of it.

    The file is what `/config` would have been walked through, written down: one field per
    line, under the names the flow declared. It is not checked here -- the flow's own model
    is what checks it, and the model is not there until the flow is loaded.

    Args:
      said: The path to the YAML.

    Returns:
      What it holds, field by field, and nothing at all for a file that is empty.

    Raises:
      ValueError: If the file cannot be read, or holds something that is not a mapping.
    """
    import yaml

    try:
        held = yaml.safe_load(Path(said).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as why:
        raise ValueError(f"cannot read {said}: {why}") from why
    if held is None:
        return {}
    if not isinstance(held, dict):
        raise ValueError(  # noqa: TRY004 -- a file to correct, not a caller's type error
            f"{said}: a flow is set up from a mapping, not a {type(held).__name__}"
        )
    return cast("dict[str, Any]", held)


# What follows runs writer jobs apart from one another: each in a Git worktree of its own,
# leased from one frozen base commit, driven as a subprocess with that worktree for a cwd,
# and read back afterwards purely from what Git says it left behind. Nothing here touches
# how a single flow runs -- `Runner.run` above is that, and stays as it is.

#: The identity the coordinator commits and cherry-picks as, pinned onto each Git command
#: so a run reads the same everywhere and nobody's own configuration is read or written.
#: Signing is off for the same reason: a result commit asserts what a worktree held, not
#: who was at the keyboard.
_AS_HUMANIZE = (
    "-c",
    "user.name=humanize",
    "-c",
    "user.email=humanize@localhost",
    "-c",
    "commit.gpgsign=false",
)

_HUMANIZE_IDENTITY = {
    "GIT_AUTHOR_NAME": "humanize",
    "GIT_AUTHOR_EMAIL": "humanize@localhost",
    "GIT_COMMITTER_NAME": "humanize",
    "GIT_COMMITTER_EMAIL": "humanize@localhost",
}

#: What Git leaves in its own directory while an operation is half done. A writer that went
#: to its end mid-merge or mid-rebase has not left a snapshot anybody can vouch for, so any
#: of these in a worktree refuses it.
_HALF_DONE = (
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "BISECT_LOG",
    "rebase-apply",
    "rebase-merge",
)

#: How long a terminated writer gets to go of its own accord before it is killed outright,
#: in seconds. Terminating is the polite form; an interrupt cannot wait forever on a writer
#: that ignores it.
_PATIENCE = 10.0


class _RunError(Exception):
    """Why a stage of a worktree run could not go on, said plainly.

    Raised only after the first worktree exists, and caught before it leaves the
    coordinator: from outside, everything past that point is a result, not an exception,
    so a caller holding several runs is not unwound by one of them.
    """


class _GitError(_RunError):
    """A Git command that did not do what was asked: what, where, and what Git said."""

    def __init__(
        self, action: str, cwd: Path, returncode: int | None, stderr: str
    ) -> None:
        said = stderr.strip() or "(nothing on stderr)"
        super().__init__(f"{action} (in {cwd}): exit {returncode}: {said}")


def _ran(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Runs one Git command where it is told to, and answers with whatever happened.

    Args:
      cwd: Where to run it -- always said, never inherited, which is what lets the
        coordinator work several worktrees without moving itself.
      *args: The command, after ``git``.

    Returns:
      The completed process, output captured, exit code unjudged.

    Raises:
      _GitError: If Git itself could not be started.
    """
    try:
        environment = None
        if args[: len(_AS_HUMANIZE)] == _AS_HUMANIZE:
            environment = os.environ | _HUMANIZE_IDENTITY
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError) as unrunnable:
        raise _GitError(
            f"running git {args[0]}", cwd, None, str(unrunnable)
        ) from unrunnable


def _git(cwd: Path, *args: str, action: str) -> str:
    """Runs one Git command that has to succeed, and answers with its stdout.

    Args:
      cwd: Where to run it.
      *args: The command, after ``git``.
      action: What the command is doing, for the reader of a refusal.

    Returns:
      The command's stdout, exactly as written -- a ``-z`` listing keeps its terminators.

    Raises:
      _GitError: If the command could not run or did not exit zero.
    """
    done = _ran(cwd, *args)
    if done.returncode != 0:
        raise _GitError(action, cwd, done.returncode, done.stderr)
    return done.stdout


def _git_holds(cwd: Path, *args: str, action: str) -> bool:
    """Asks Git a yes-or-no question: exit zero is yes, exit one is no.

    Args:
      cwd: Where to ask.
      *args: The question, after ``git`` -- ``merge-base --is-ancestor``,
        ``diff --cached --quiet``, and their kind.
      action: What is being asked, for the reader of a refusal.

    Returns:
      What Git answered.

    Raises:
      _GitError: If Git answered with anything but yes or no.
    """
    done = _ran(cwd, *args)
    if done.returncode in (0, 1):
        return done.returncode == 0
    raise _GitError(action, cwd, done.returncode, done.stderr)


def _on_branch(cwd: Path) -> str | None:
    """The branch a worktree has checked out, or None for the detached HEAD it was leased at.

    Args:
      cwd: The worktree.

    Returns:
      The short branch name, or None.
    """
    said = _ran(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
    return said.stdout.strip() if said.returncode == 0 else None


def _standing(cwd: Path) -> str:
    """What ``git status`` says stands uncommitted in a worktree, untracked files and all.

    Args:
      cwd: The worktree.

    Returns:
      The porcelain listing: empty is clean, and ignored files do not count.

    Raises:
      _GitError: If status itself failed.
    """
    return _git(
        cwd,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        action="reading the working tree's status",
    ).strip()


@dataclass(frozen=True, slots=True)
class WorktreeJob:
    """One writer to run apart: a name to answer to, and the command that is the writer.

    Attributes:
      name: What the job's results answer to. Non-empty, and no two jobs of one run share
        it; the worktree's path comes from the job's place in the run, not from this.
      argv: The complete command, run without a shell -- an ``hmz exec`` line as a rule,
        though anything that edits files where it is started will do. It is not reparsed
        or rebuilt: whatever agents it drives are its own business.
    """

    name: str
    argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorktreeJobResult:
    """What one writer job came to, read off its process and its worktree's Git state.

    Attributes:
      name: The job's name, as given.
      status: Where it ended. "committed" is a writer whose leavings became one result
        commit; "no_change" one whose worktree matched the base when it was done; both are
        successes. "finished" is a writer that exited zero in a run that failed elsewhere,
        its worktree left exactly as the writer left it; "failed" is one that did not exit
        zero, could not start, or left Git state nobody can vouch for; "not_started" is a
        job the run never reached.
      worktree_path: Where its worktree is, or None if none was ever made. The path stands
        whether or not the worktree was cleaned away at the end.
      returncode: How the writer exited -- negative for a signal, None if it never ran.
      source_commit: The one result commit made in its worktree, or None.
      integrated_commit: The commit that carries this job's change on the integration line,
        recorded so cleaning the writer's worktree cannot orphan the result. None for a job
        that changed nothing or was never integrated.
      changed_paths: Every path the result commit touches, relative to the repository root.
      error: Why it failed, or None.
    """

    name: str
    status: str
    worktree_path: str | None
    returncode: int | None
    source_commit: str | None
    integrated_commit: str | None
    changed_paths: tuple[str, ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class WorktreeCheckResult:
    """One check command's outcome, in the order the checks were given.

    A check that was never reached -- one after the first failure -- has no result at all.

    Attributes:
      argv: The command, as given.
      returncode: How it exited, or None if it could not start.
      error: Why it counts as failed, or None for a check that passed.
    """

    argv: tuple[str, ...]
    returncode: int | None
    error: str | None


@dataclass(frozen=True, slots=True)
class WorktreeRunResult:
    """Everything observable about one worktree run, and nothing a writer merely said.

    Attributes:
      status: "published" when the target branch carries every job's result; "unchanged"
        when no job changed anything and the checks still passed from the base; "failed"
        for everything else, with the scene kept for whoever comes to look.
      repo_root: The repository the run worked, as pinned before anything was made.
      target_branch: The branch that was checked out at the start, and the only one a
        success moves.
      base_sha: The commit every worktree was leased from.
      published_sha: Where the target branch ended, or None for a run that published
        nothing.
      jobs: One result per job, in the order the jobs were given.
      checks: One result per check that ran, in the order the checks were given.
      kept_paths: Every worktree left on disk -- the whole scene after a failure, or
        whatever a cleaning error left behind after a success.
      cleanup_errors: What went wrong cleaning up, none of which changes the status: a
        published run with a stubborn directory is still published.
      error: What ended a failed run, or None.
    """

    status: str
    repo_root: str
    target_branch: str
    base_sha: str
    published_sha: str | None
    jobs: tuple[WorktreeJobResult, ...]
    checks: tuple[WorktreeCheckResult, ...]
    kept_paths: tuple[str, ...]
    cleanup_errors: tuple[str, ...]
    error: str | None


@dataclass(slots=True)
class _Writing:
    """One job's unfolding state, frozen into a :class:`WorktreeJobResult` at the end."""

    job: WorktreeJob
    path: Path | None = None
    returncode: int | None = None
    source_commit: str | None = None
    integrated_commit: str | None = None
    changed_paths: tuple[str, ...] = ()
    status: str = "not_started"
    error: str | None = None

    def result(self) -> WorktreeJobResult:
        """This job's state, as the run's caller is handed it."""
        return WorktreeJobResult(
            name=self.job.name,
            status=self.status,
            worktree_path=None if self.path is None else str(self.path),
            returncode=self.returncode,
            source_commit=self.source_commit,
            integrated_commit=self.integrated_commit,
            changed_paths=self.changed_paths,
            error=self.error,
        )


def _refused(
    jobs: tuple[WorktreeJob, ...], checks: tuple[tuple[str, ...], ...], at_once: int
) -> None:
    """Refuses arguments nothing should be built from, before anything is.

    Args:
      jobs: The writer jobs, as given.
      checks: The check commands, as given.
      at_once: The concurrency bound, as given.

    Raises:
      ValueError: If there are no jobs, a job has no name or no command, two jobs share a
        name, a check is empty, or the bound is negative.
    """
    if not jobs:
        raise ValueError("a worktree run needs at least one job")
    if any(not job.name for job in jobs):
        raise ValueError("every job needs a name for its results to answer to")
    names = [job.name for job in jobs]
    if len(set(names)) != len(names):
        taken = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(f"job names have to be unique: {', '.join(taken)} repeat")
    if short := [job.name for job in jobs if not job.argv]:
        raise ValueError(f"a job is a command, and {', '.join(short)} have none")
    if any(not tuple(check) for check in checks):
        raise ValueError("an empty check checks nothing, and would run nothing")
    if at_once < 0:
        raise ValueError(f"at_once is a bound or 0 for no bound, not {at_once}")


def _pinned(managed_root: Path) -> tuple[Path, str, str]:
    """Reads and pins where a run starts from: the repository, its branch, its commit.

    Everything later holds itself to these three: the worktrees are leased from the
    commit, the checks are judged against it, and publishing refuses to move anything
    but the branch -- and only from exactly here.

    Args:
      managed_root: Where the run would keep its worktrees, refused if it sits inside
        the repository it mirrors.

    Returns:
      The repository root, the checked-out branch, and the commit it stands at.

    Raises:
      ValueError: If this is not a clean Git worktree standing on a branch with a commit
        under it, or Git cannot be run at all.
    """
    here = Path.cwd()
    try:
        root = Path(
            _git(
                here,
                "rev-parse",
                "--show-toplevel",
                action="finding the repository this directory is in",
            ).strip()
        ).resolve()
    except _GitError as lost:
        raise ValueError(str(lost)) from lost
    branch = _on_branch(root)
    if branch is None:
        raise ValueError(
            f"{root}: HEAD is detached; a run needs the branch it will publish to"
        )
    try:
        base = _git(
            root, "rev-parse", "HEAD", action="resolving the commit to lease from"
        ).strip()
        clean = not _standing(root)
    except _GitError as unread:
        raise ValueError(str(unread)) from unread
    if not clean:
        raise ValueError(
            f"{root}: the working tree is not clean; commit or put away what stands "
            "before a run, so what was published can be told from what was already there"
        )
    if managed_root.resolve().is_relative_to(root.resolve()):
        raise ValueError(
            f"{managed_root}: worktrees cannot be kept inside the repository they "
            "mirror -- point HUMANIZE_HOME somewhere outside it"
        )
    return root, branch, base


def _driven(writings: list[_Writing], at_once: int) -> None:
    """Runs every writer to its end, each in its own worktree, at most `at_once` at a time.

    The subprocess is the whole of the isolation: each is started with its worktree for a
    cwd and nothing else changed, so a writer's own environment, streams and signals are
    exactly what they would be anywhere. The coordinator itself never moves.

    An interrupt ends the writers rather than leaving them running into the next stage:
    whatever is underway is terminated and waited for, nothing further is started, and the
    interrupt goes on up with every worktree kept as it stood.

    Args:
      writings: One per job, each holding the worktree already leased for it. How each
        writer ended is written back onto it.
      at_once: The bound, or 0 to run them all at once.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    guard = threading.Lock()
    stop = threading.Event()
    running: dict[int, subprocess.Popen[bytes]] = {}

    def write(index: int) -> None:
        writing = writings[index]
        argv, path = writing.job.argv, writing.path
        assert path is not None  # leased before anything is driven  # noqa: S101
        with guard:
            if stop.is_set():
                writing.error = f"{writing.job.name}: not started; the run was ended"
                writing.status = "failed"
                return
            try:
                writer = subprocess.Popen(list(argv), cwd=path)
            except (OSError, ValueError) as unrunnable:
                writing.error = (
                    f"{writing.job.name}: cannot start {argv[0]}: {unrunnable}"
                )
                writing.status = "failed"
                return
            running[index] = writer
        returncode = writer.wait()
        with guard:
            running.pop(index, None)
        writing.returncode = returncode
        if returncode == 0:
            writing.status = "finished"
        elif returncode < 0:
            writing.error = (
                f"{writing.job.name}: the writer was ended by signal {-returncode}"
            )
            writing.status = "failed"
        else:
            writing.error = f"{writing.job.name}: the writer exited {returncode}"
            writing.status = "failed"

    pool = ThreadPoolExecutor(
        max_workers=at_once or len(writings), thread_name_prefix="humanize-writer"
    )
    futures = [pool.submit(write, index) for index in range(len(writings))]
    try:
        for future in futures:
            future.result()
    except BaseException:
        # An interrupt, almost always. The writers are this run's to end: terminated,
        # then waited for -- killed if terminating went unheard -- so no direct child of
        # ours is still writing when the caller hears.
        with guard:
            stop.set()
            underway = list(running.values())
        for writer in underway:
            writer.terminate()
        for writer in underway:
            try:
                writer.wait(timeout=_PATIENCE)
            except subprocess.TimeoutExpired:
                writer.kill()
                writer.wait()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)


def _reckoned(writing: _Writing, base: str) -> None:
    """Reads one finished writer's worktree back into at most one commit on the base.

    The writer said nothing about what it did, and is not asked: staged, unstaged,
    untracked, deleted and renamed work alike are what the snapshot is, and any commits
    the writer made of its own are flattened into the same one. A worktree that matches
    the base is a result too -- no change -- and gets no empty commit.

    Args:
      writing: The job, exited zero, its worktree still as the writer left it. What the
        reckoning finds is written back onto it.
      base: The commit the worktree was leased from, the result's one parent.

    Raises:
      _RunError: If the writer moved onto a branch, left the base's line of descent, left
        unmerged entries or a half-done Git operation, or any of the reading and
        committing itself failed -- none of which a writer's own exit code overrides.
    """
    path, name = writing.path, writing.job.name
    assert path is not None  # leased before anything is reckoned  # noqa: S101
    if (branch := _on_branch(path)) is not None:
        raise _RunError(
            f"{name}: the writer moved onto branch {branch!r}; a worktree is leased "
            "detached, and its snapshot is read from where it was left"
        )
    for trace in _HALF_DONE:
        spot = _git(
            path,
            "rev-parse",
            "--git-path",
            trace,
            action=f"locating {trace}",
        ).strip()
        if (path / spot).exists():
            raise _RunError(
                f"{name}: a half-done Git operation ({trace}) is in the worktree; "
                "nothing it holds can be vouched for as the writer's result"
            )
    if _git(
        path, "ls-files", "--unmerged", action="looking for unmerged entries"
    ).strip():
        raise _RunError(f"{name}: unmerged entries are in the worktree's index")
    if not _git_holds(
        path,
        "merge-base",
        "--is-ancestor",
        base,
        "HEAD",
        action="checking the worktree still descends from the base",
    ):
        raise _RunError(
            f"{name}: the worktree's HEAD no longer descends from {base}; whatever "
            "stands there is not this run's work to publish"
        )
    _git(
        path,
        "reset",
        "--soft",
        base,
        action=f"gathering {name}'s commits onto the base",
    )
    _git(path, "add", "-A", action=f"staging everything {name} left")
    if _git_holds(
        path, "diff", "--cached", "--quiet", action="asking whether anything changed"
    ):
        if left := _standing(path):
            raise _RunError(
                f"{name}: the no-change worktree is not clean after it was staged: {left}"
            )
        writing.status = "no_change"
        return
    _git(
        path,
        *_AS_HUMANIZE,
        "commit",
        "-m",
        f"humanize worktree: {name}",
        action=f"committing {name}'s snapshot",
    )
    sha = _git(path, "rev-parse", "HEAD", action="reading the result commit").strip()
    lineage = _git(
        path,
        "rev-list",
        "--parents",
        "-n",
        "1",
        "HEAD",
        action="reading the result commit's parents",
    ).split()
    if lineage != [sha, base]:
        raise _RunError(
            f"{name}: the result commit does not sit alone on the base: {lineage}"
        )
    writing.source_commit = sha
    if left := _standing(path):
        raise _RunError(
            f"{name}: the worktree is not clean after its snapshot was committed: {left}"
        )
    listed = _git(
        path,
        "diff",
        "--name-only",
        "-z",
        base,
        sha,
        action="listing the paths the result touches",
    )
    writing.changed_paths = tuple(one for one in listed.split("\0") if one)
    writing.status = "committed"


def _checked(
    checks: tuple[tuple[str, ...], ...], where: Path
) -> tuple[tuple[WorktreeCheckResult, ...], str | None]:
    """Runs the caller's checks in order, stopping at the first that does not pass.

    Args:
      checks: The commands, each an argv run without a shell, with the caller's own
        environment and streams.
      where: The integration worktree, every check's cwd.

    Returns:
      One result per check that ran, and why the run cannot publish -- a failed check, or
      a worktree the checks themselves dirtied -- or None if everything held.
    """
    outcomes: list[WorktreeCheckResult] = []
    for check in checks:
        argv = tuple(check)
        try:
            done = subprocess.run(list(argv), cwd=where, check=False)
        except (OSError, ValueError) as unrunnable:
            outcomes.append(
                WorktreeCheckResult(
                    argv=argv,
                    returncode=None,
                    error=f"cannot start {argv[0]}: {unrunnable}",
                )
            )
            return tuple(outcomes), f"check {argv[0]} could not start: {unrunnable}"
        if done.returncode != 0:
            outcomes.append(
                WorktreeCheckResult(
                    argv=argv,
                    returncode=done.returncode,
                    error=f"exited {done.returncode}",
                )
            )
            return tuple(outcomes), f"check {argv[0]} exited {done.returncode}"
        outcomes.append(WorktreeCheckResult(argv=argv, returncode=0, error=None))
    try:
        left = _standing(where)
    except _RunError as unread:
        return tuple(outcomes), str(unread)
    if left:
        # What was checked has to be what is published, and a check that wrote into the
        # worktree has made those two things different.
        return tuple(
            outcomes
        ), f"the checks left the integration worktree dirty: {left}"
    return tuple(outcomes), None


def _integration_unchanged(where: Path, tip: str) -> str | None:
    """Why the integration worktree no longer holds the checked result, if it moved."""
    try:
        if branch := _on_branch(where):
            return (
                f"the integration worktree moved onto branch {branch!r} during the checks; "
                "it was leased detached"
            )
        settled = _git(
            where, "rev-parse", "HEAD", action="re-reading the integration tip"
        ).strip()
    except _RunError as unread:
        return str(unread)
    if settled != tip:
        return (
            f"the integration worktree moved from the tip {tip} to {settled} during "
            "the checks; what was checked is no longer the writers' result"
        )
    return None


def _still_at_base(root: Path, branch: str, base: str) -> None:
    """Refuses a main worktree that no longer stands exactly where the run began."""
    if (standing_on := _on_branch(root)) != branch:
        raise _RunError(
            f"the main worktree is on {standing_on or 'a detached HEAD'!r}, no longer "
            f"on {branch!r}; nothing is published over somebody else's move"
        )
    head = _git(root, "rev-parse", "HEAD", action="re-reading the main HEAD").strip()
    ref = _git(
        root,
        "rev-parse",
        f"refs/heads/{branch}",
        action="re-reading the target branch",
    ).strip()
    if head != base or ref != base:
        raise _RunError(
            f"{branch} moved while the run was underway ({base} -> {ref}); its new "
            "commits are somebody's work, and nothing is published over them"
        )
    if left := _standing(root):
        raise _RunError(
            f"the main working tree changed while the run was underway: {left}"
        )


def _published(root: Path, integration: Path, branch: str, base: str, tip: str) -> None:
    """Fast-forwards the target branch to the integration tip, from the main worktree.

    Only if the main worktree still stands exactly where the run began: same branch, same
    commit, nothing uncommitted. Anything else is somebody else's work in progress, and
    the one safe thing to do with it is nothing.

    Args:
      root: The repository's main worktree.
      integration: The integration worktree, whose tree the published one has to match.
      branch: The branch pinned at the start.
      base: The commit pinned at the start.
      tip: The integration tip to publish.

    Raises:
      _RunError: If the integration worktree or the main worktree moved, the fast-forward
        failed, or what stands published is not what passed the checks. Nothing is reset,
        rebased or forced either way.
    """
    _still_at_base(root, branch, base)
    _git(
        root,
        "merge",
        "--ff-only",
        tip,
        action=f"fast-forwarding {branch} to the integration tip",
    )
    landed = _git(
        root, "rev-parse", "HEAD", action="verifying the published HEAD"
    ).strip()
    if landed != tip:
        raise _RunError(f"publishing landed on {landed}, not the integration tip {tip}")
    if (now_on := _on_branch(root)) != branch:
        raise _RunError(
            f"the fast-forward left the main worktree on {now_on or 'a detached HEAD'!r}"
            f", not {branch!r}; a branch switched under it was moved in its place"
        )
    ref = _git(
        root,
        "rev-parse",
        f"refs/heads/{branch}",
        action="verifying the published branch",
    ).strip()
    if ref != tip:
        raise _RunError(
            f"{branch} stands at {ref}, not the integration tip {tip}, after publishing"
        )
    if left := _standing(root):
        raise _RunError(f"the main working tree is not clean after publishing: {left}")
    published = _git(
        root, "rev-parse", "HEAD^{tree}", action="reading the published tree"
    ).strip()
    checked = _git(
        integration, "rev-parse", "HEAD^{tree}", action="re-reading the checked tree"
    ).strip()
    if published != checked:
        raise _RunError(
            f"the published tree {published} is not the tree the checks passed on "
            f"({checked})"
        )


def _kept_back(root: Path, run_dir: Path, path: Path, head: str) -> str | None:
    """Why one worktree is not this run's to remove, or None when it verifiably is.

    Every question is asked of the worktree itself, at the moment of removal: a path from
    outside the run's own directory, one Git no longer lists, one standing on some other
    commit, or one with uncommitted work is left where it is, whatever the records say.

    Args:
      root: The repository's main worktree, where the listing is read.
      run_dir: The one directory this run's worktrees live under.
      path: The worktree to be removed.
      head: The commit its HEAD was recorded at.

    Returns:
      The refusal, or None.
    """
    if not path.resolve().is_relative_to(run_dir.resolve()):
        return f"{path}: not under this run's directory, so not this run's to remove"
    try:
        listed = _git(
            root, "worktree", "list", "--porcelain", action="listing the worktrees"
        )
        registered = {
            Path(line.removeprefix("worktree ")).resolve()
            for line in listed.splitlines()
            if line.startswith("worktree ")
        }
        if path.resolve() not in registered:
            return f"{path}: not a worktree Git knows of"
        standing_at = _git(
            path, "rev-parse", "HEAD", action="re-reading the worktree's HEAD"
        ).strip()
        if standing_at != head:
            return f"{path}: HEAD is {standing_at}, not the recorded {head}"
        if left := _standing(path):
            return f"{path}: not clean, and what stands there may be somebody's: {left}"
    except _RunError as unread:
        return str(unread)
    return None


def _cleared(
    root: Path, run_dir: Path, leases: list[tuple[Path, str]]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Removes a fully successful run's worktrees, each verified to be exactly as recorded.

    ``--force`` is what lets Git delete the ignored leavings of a build or a test run; the
    verification above it is what keeps it from ever deleting tracked work, because a
    worktree that is not clean is not removed at all.

    Args:
      root: The repository's main worktree.
      run_dir: The one directory this run's worktrees live under, removed too once empty.
      leases: Each worktree and the commit its HEAD was recorded at.

    Returns:
      The paths left behind and why, both empty when everything went.
    """
    kept: list[str] = []
    errors: list[str] = []
    for path, head in leases:
        refusal = _kept_back(root, run_dir, path, head)
        if refusal is None:
            try:
                _git(
                    root,
                    "worktree",
                    "remove",
                    "--force",
                    str(path),
                    action=f"removing the worktree at {path}",
                )
            except _RunError as undone:
                refusal = str(undone)
        if refusal is not None:
            kept.append(str(path))
            errors.append(refusal)
    try:
        run_dir.rmdir()  # only ever an empty directory; anything left keeps it
    except OSError:
        if not kept:
            kept.append(str(run_dir))
            errors.append(f"{run_dir}: could not be removed")
    return tuple(kept), tuple(errors)


def run_worktrees(
    jobs: Sequence[WorktreeJob],
    *,
    checks: Sequence[Sequence[str]] = (),
    at_once: int = 0,
) -> WorktreeRunResult:
    """Runs writer jobs in parallel, each in a Git worktree of its own, and publishes the whole.

    Every worktree is leased detached from the one commit the repository stands at, so the
    jobs share a base and nothing else: files, index and HEAD are each writer's own. What a
    writer leaves behind is read back from Git alone -- flattened to at most one commit per
    job -- then cherry-picked in the order the jobs were given onto an integration worktree,
    where the checks run. Only when every job succeeded, every check passed, and the main
    worktree still stands exactly where it started does the target branch fast-forward; a
    fully successful run then removes its worktrees, and any other outcome keeps them all
    for whoever comes to look.

    This is cooperative isolation for files, not a security boundary: the subprocesses
    still share the host, the object database, the refs and the caller's credentials.

    Args:
      jobs: The writers, uniquely named, each a complete argv run with its worktree for a
        cwd -- ``("hmz", "exec", ...)`` as a rule.
      checks: Commands to run in the integration worktree once everything is picked, each
        an argv, in order; all of them have to exit zero.
      at_once: How many writers may run at the same time, or 0 for all of them.

    Returns:
      What observably happened, job by job and check by check. Nothing a writer printed
      or claimed is in it.

    Raises:
      ValueError: If the arguments or the repository are unfit, found out before any
        worktree exists. From the first lease on, failure is a returned result instead.
      KeyboardInterrupt: On an interrupt, after the writers have been terminated and
        waited for; the worktrees made so far are kept.
    """
    import uuid

    held = tuple(jobs)
    wanted_checks = tuple(tuple(check) for check in checks)
    _refused(held, wanted_checks, at_once)
    managed_root = (home() / "worktrees").resolve()
    root, branch, base = _pinned(managed_root)
    run_dir = managed_root / str(uuid.uuid4())
    writings = [_Writing(job=job) for job in held]

    def come_out(
        status: str,
        *,
        published: str | None = None,
        ran: tuple[WorktreeCheckResult, ...] = (),
        kept: tuple[str, ...] = (),
        cleanup: tuple[str, ...] = (),
        error: str | None = None,
    ) -> WorktreeRunResult:
        return WorktreeRunResult(
            status=status,
            repo_root=str(root),
            target_branch=branch,
            base_sha=base,
            published_sha=published,
            jobs=tuple(writing.result() for writing in writings),
            checks=ran,
            kept_paths=kept,
            cleanup_errors=cleanup,
            error=error,
        )

    created: list[Path] = []

    def scene() -> tuple[str, ...]:
        return tuple(str(path) for path in created)

    # The leases, one by one: worktree bookkeeping shares the repository's own metadata,
    # so only the writers themselves ever run in parallel.
    run_dir.mkdir(parents=True)
    for index, writing in enumerate(writings):
        path = run_dir / f"writer-{index}"
        try:
            _git(
                root,
                "worktree",
                "add",
                "--detach",
                str(path),
                base,
                action=f"leasing a worktree for {writing.job.name}",
            )
        except _RunError as unleased:
            writing.error = str(unleased)
            return come_out("failed", kept=scene(), error=str(unleased))
        writing.path = path
        created.append(path)

    _driven(writings, at_once)
    if wrong := [writing.error for writing in writings if writing.status == "failed"]:
        # The other writers were still waited to their ends; their worktrees stand
        # exactly as left, unreckoned, because reading them would disturb the scene.
        return come_out("failed", kept=scene(), error=wrong[0])

    for writing in writings:
        try:
            _reckoned(writing, base)
        except _RunError as unvouched:
            writing.status = "failed"
            writing.error = str(unvouched)
            return come_out("failed", kept=scene(), error=str(unvouched))

    integration = run_dir / "integration"
    try:
        _git(
            root,
            "worktree",
            "add",
            "--detach",
            str(integration),
            base,
            action="leasing the integration worktree",
        )
    except _RunError as unleased:
        return come_out("failed", kept=scene(), error=str(unleased))
    created.append(integration)

    tip = base
    for writing in writings:
        if writing.source_commit is None:
            continue  # no change: nothing to pick, and no empty commit to make
        try:
            _git(
                integration,
                *_AS_HUMANIZE,
                "cherry-pick",
                writing.source_commit,
                action=f"integrating {writing.job.name}",
            )
        except _RunError as conflicted:
            # Left exactly as Git stopped, conflict markers and all: an abort would
            # destroy the one thing that says what collided with what.
            return come_out("failed", kept=scene(), error=str(conflicted))
        tip = _git(
            integration, "rev-parse", "HEAD", action="reading the integration tip"
        ).strip()
        writing.integrated_commit = tip

    ran, unpassed = _checked(wanted_checks, integration)
    if unpassed is not None:
        return come_out("failed", ran=ran, kept=scene(), error=unpassed)
    if moved := _integration_unchanged(integration, tip):
        return come_out("failed", ran=ran, kept=scene(), error=moved)

    if tip == base:
        try:
            _still_at_base(root, branch, base)
        except _RunError as moved:
            return come_out("failed", ran=ran, kept=scene(), error=str(moved))
        outcome, published = "unchanged", None
    else:
        try:
            _published(root, integration, branch, base, tip)
        except _RunError as unmoved:
            return come_out("failed", ran=ran, kept=scene(), error=str(unmoved))
        outcome, published = "published", tip

    leases = [
        (path, writing.source_commit or base)
        for writing in writings
        if (path := writing.path) is not None
    ]
    leases.append((integration, tip))
    kept, cleanup = _cleared(root, run_dir, leases)
    return come_out(outcome, published=published, ran=ran, kept=kept, cleanup=cleanup)
