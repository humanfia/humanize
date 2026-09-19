"""The whole of what a flow imports: what it drives, the mark, and the words for a turn.

A flow is a directory: an `__init__.py` that is the flow itself, whatever that imports beside
it, and a `skills/` of the skills it brings -- laid out the way every one of these CLIs lays a
skill out, one directory apiece with a `SKILL.md` in it. So a flow is a thing that can be
copied, forked and edited whole, and what it needs to do its work travels with it.

A flow is a function marked with :func:`flow`, and nothing else is one. `@flow()` is the flow
its directory holds under the directory's own name; `@flow(name="draft")` is one of several it
holds, called `<flow>:draft` -- so that three phases of one thing live in one flow and are
three things to run. What the function is called is the flow's own business: `run`, `main`,
`draft_it`, all the same to a name that never mentions it.

And this is the whole of what a flow imports::

    from hmz.flows import Agent, Moment, flow

    @flow
    def run(agents: tuple[Agent, Agent], task: str) -> None:
        ...

One import rather than four, because a flow is written against one thing: what it drives, what
it may ask of it, and what it is worth saying about a turn. Which of humanize's own modules any
of that is written in is humanize's business -- a flow that named them would be a flow that
breaks when one of them moves, and a flow is somebody else's repository.

So what is here is only ever what writing a flow takes, and it is a short list. The interfaces
a flow drives, in [agent.py](agent.py). The marks an atlas declares its graph with, in
[atlas.py](atlas.py). The mark that makes a function a flow, and what that mark says, here.
Everything else is handed through: the vocabulary a turn is described in from
:mod:`hmz.coganchor.agents`, the facts about the CLIs and what each of them runs, where
humanize keeps what outlives a run, and calling another flow -- which is `load`, and is
:mod:`hmz.runtime.flowing.driving`'s.

What is *not* here is everything humanize does *to* a flow. Finding one, listing them, reading
one without running it, driving one, compiling an atlas, fetching the skills a flow named,
walking a prophecy: none of it is a thing a flow names, so none of it is a thing a flow can
break on. All of it is :mod:`hmz.runtime.flowing`, which is written against this and which this
never imports at the top of the file.

What is handed through is fetched when a flow names it rather than imported with this module.
This is also what a command line is routed through before it knows whether it names a flow at
all, so importing it must cost no more than reading a directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, overload

from .agent import Agent, Driven, Person, Session
from .atlas import Atlas, Kind, Marked, Sub, atlas, logic, mind, sub

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from hmz import home
    from hmz.coganchor import backends, models
    from hmz.coganchor.agents import (
        EVERYWHERE,
        PERMISSIONS,
        SWARM,
        UNSAID,
        WINDOW,
        AgentConfig,
        AgentDefaults,
        Allowance,
        Board,
        Budget,
        Event,
        Failed,
        Goal,
        Hook,
        Hooks,
        HumanAgent,
        Hung,
        Isolated,
        Item,
        Moment,
        Needs,
        Occasion,
        Question,
        Refused,
        Remote,
        Stopped,
        Tool,
        Unhooked,
        Unrecoverable,
        Usage,
        Verdict,
    )
    from hmz.coganchor.backends import Model, Profile
    from hmz.runtime.flowing.driving import NotAFlow, Running, container, load, running

__all__ = [
    "EVERYWHERE",
    "PERMISSIONS",
    "SWARM",
    "UNSAID",
    "WINDOW",
    "Agent",
    "AgentConfig",
    "AgentDefaults",
    "Allowance",
    "Atlas",
    "Board",
    "Budget",
    "Driven",
    "Event",
    "Failed",
    "Flow",
    "Goal",
    "Hook",
    "Hooks",
    "HumanAgent",
    "Hung",
    "Isolated",
    "Item",
    "Kind",
    "Marked",
    "Model",
    "Moment",
    "Needs",
    "NotAFlow",
    "Occasion",
    "Person",
    "Profile",
    "Question",
    "Refused",
    "Remote",
    "Running",
    "Session",
    "Stopped",
    "Sub",
    "Tool",
    "Unhooked",
    "Unrecoverable",
    "Usage",
    "Verdict",
    "atlas",
    "backends",
    "container",
    "flow",
    "home",
    "load",
    "logic",
    "mind",
    "models",
    "running",
    "sub",
]

#: The two modules of humanize's own that a flow reaches through here whole: what each CLI
#: is, and what each of them runs. A loop that turns the effort down when a model starts
#: writing less asks the second of them what rungs there are, which is a question about a
#: backend rather than about any agent -- so it is handed through as it stands rather than
#: flattened into a name apiece. Under the name the flow writes rather than the one the
#: module is at: a flow says `flows.backends`, and where humanize keeps that is humanize's
#: own to move.
_MODULES = {"backends": "hmz.coganchor.backends", "models": "hmz.coganchor.models"}

#: And the names a flow imports from here that are written down elsewhere: the vocabulary a
#: turn is described in, where humanize keeps what outlives a run, and what it takes for one
#: flow to run another -- which is the runtime's, being the thing that drives a flow, and is
#: handed through so that a flow calling a flow writes the one import it already has.
_ELSEWHERE = {
    "AgentConfig": "hmz.coganchor.agents",
    "AgentDefaults": "hmz.coganchor.agents",
    "Allowance": "hmz.coganchor.agents",
    "Board": "hmz.coganchor.agents",
    "Budget": "hmz.coganchor.agents",
    "EVERYWHERE": "hmz.coganchor.agents",
    "Event": "hmz.coganchor.agents",
    "Failed": "hmz.coganchor.agents",
    "Goal": "hmz.coganchor.agents",
    "Hook": "hmz.coganchor.agents",
    "Hooks": "hmz.coganchor.agents",
    "HumanAgent": "hmz.coganchor.agents",
    "Hung": "hmz.coganchor.agents",
    "Isolated": "hmz.coganchor.agents",
    "Item": "hmz.coganchor.agents",
    "Model": "hmz.coganchor.backends",
    "Moment": "hmz.coganchor.agents",
    "Needs": "hmz.coganchor.agents",
    "NotAFlow": "hmz.runtime.flowing.driving",
    "Occasion": "hmz.coganchor.agents",
    "PERMISSIONS": "hmz.coganchor.agents",
    "Profile": "hmz.coganchor.backends",
    "Question": "hmz.coganchor.agents",
    "Refused": "hmz.coganchor.agents",
    "Remote": "hmz.coganchor.agents",
    "Running": "hmz.runtime.flowing.driving",
    "SWARM": "hmz.coganchor.agents",
    "Stopped": "hmz.coganchor.agents",
    "Tool": "hmz.coganchor.agents",
    "UNSAID": "hmz.coganchor.agents",
    "Unhooked": "hmz.coganchor.agents",
    "Unrecoverable": "hmz.coganchor.agents",
    "Usage": "hmz.coganchor.agents",
    "Verdict": "hmz.coganchor.agents",
    "WINDOW": "hmz.coganchor.agents",
    "container": "hmz.runtime.flowing.driving",
    "home": "hmz",
    "load": "hmz.runtime.flowing.driving",
    "running": "hmz.runtime.flowing.driving",
}


def __getattr__(name: str) -> object:
    """Hands through what a flow imports from here that is written down elsewhere.

    Fetched when it is asked for rather than imported at the top of this file, because this
    module is also what a list of flows is drawn from and what `hmz exec --help` loads to say
    what the line takes: importing it must not cost every coding agent driver there is. A flow
    that actually names one of these is a flow about to be run, and pays for it then.

    Args:
      name: What was asked for.

    Returns:
      The same object the module it is written in holds, so that a flow and humanize itself
      are talking about one thing -- `Moment.STOP` here is `Moment.STOP` there.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    from importlib import import_module

    if (whole := _MODULES.get(name)) is not None:
        return import_module(whole)
    where_ = _ELSEWHERE.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)


@dataclass(frozen=True, slots=True)
class Flow:
    """What a flow says about itself where it is written.

    Attributes:
      name: What it is called inside its own directory, which is the half after the colon.
        "" for the one it holds under the directory's own name, which is what `@flow()` marks.
      about: One line saying what it does, for whoever is choosing between them. Read off the
        function's own docstring where the decorator was not told one, and off the module's
        where the flow is one flow and its function says nothing.
      skills: The skills it works by that live somewhere else, each a git repository anything
        can clone with an optional `#<skill>` saying which of the ones in it is wanted. What
        the flow keeps in its own `skills/` is not among them: that is every flow in the
        directory's, and is found by looking rather than by being declared.
      resumable: Whether it can be picked up where the last run of it left off. One that says
        so is handed a dict as its last argument -- what it wrote there last time -- which is
        kept in the run's own epic and read back into the run after it. A flow that says
        nothing is run from the top every time, which is what every flow was before this.
      selectable: Whether people are offered this flow in lists and the flow picker. An
        internal composition may set this false while remaining callable by name.
      budget: What the flow says a run of it may spend, or None for a flow with no opinion --
        which is every flow written before there was such a thing, and which runs under
        whatever this workspace was set up with. Three states rather than two, and the third
        is the whole of the exemption from being asked about an unbounded run: an
        `Allowance()` written out is a flow saying in its own file that it is *meant* to run
        under nothing, which is what `chat` is. A flow never holds itself to it -- the run
        does, whatever the flow said -- so this is a default and not an implementation.
    """

    name: str = ""
    about: str = ""
    skills: tuple[str, ...] = ()
    resumable: bool = False
    selectable: bool = True
    budget: Allowance | None = None


#: Where a decorated function keeps what it said about itself. On the function rather than in
#: a table, because a file is read by running it: a table would be one more thing to find,
#: and this travels with the thing it describes.
_SAID = "__humanize_flow__"


@overload
def flow[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def flow[**P, T](
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    resumable: bool = False,
    selectable: bool = True,
    budget: Allowance | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def flow[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    resumable: bool = False,
    selectable: bool = True,
    budget: Allowance | None = None,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as a flow. Nothing else is one.

    Written with no name, it is the flow its file holds under the file's own name::

        @flow
        def run(agents: tuple[Agent], task: str) -> None:
            ...

    is `ralph_loop`, in `ralph_loop/__init__.py`. Written with one, it is one of several that
    flow holds, and is called `<flow>:<name>`::

        @flow(name="gen-idea", about="opens a loose idea into a repo-grounded draft")
        def first_pass(agents: Agents, task: str) -> None:
            ...

    is `humanize1:gen-idea`. What the function is called is the flow's own business either
    way: a name that is written down where a flow is run is a name to keep, and one taken
    from the function would change under whoever renamed it.

    A flow may also name skills that live somewhere else, which are mounted onto every session
    its agents open alongside the ones in its own `skills/`::

        @flow(skills=("https://github.com/humanfia/flowverse#deep-research",))

    And a flow may say that it can be picked up where the last run of it left off, which is
    what a loop that is meant to run for a week is::

        @flow(resumable=True)
        def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
            state["round"] = state.get("round", 0) + 1

    Such a flow is handed a dict as its last argument -- after the config, for one that takes
    a config -- holding whatever it wrote there last time. It is kept in the run's own epic
    and saved as the flow writes it, so a run that was stopped or killed is one the next run
    picks up from rather than one whose week is gone.

    A helper used only by another flow remains callable without cluttering the flow picker::

        @flow(name="engine", selectable=False)
        def engine(agents: tuple[Agent], task: str) -> None:
            ...

    And a flow may say what a run of it is worth, which whoever runs it can then override::

        @flow(budget=Allowance(hours=6, tokens=10.0, dollars=50))

    Saying nothing is a flow with no opinion, and it runs under whatever the workspace was
    set up with. Saying `Allowance()` is a flow claiming it is meant to run under nothing at
    all -- which `chat` is, being a conversation that ends when the person stops typing --
    and is what exempts it from being asked to confirm an unbounded run. A flow does not hold
    itself to any of this: what holds a run to it is every session of every agent in it, so
    this is a default the run reads and never a thing the flow implements.

    Args:
      call: The function, when the decorator is written with no arguments at all.
      name: What to call this one among the flows its directory holds, or "" for the one it
        holds under the directory's own name.
      about: One line saying what it does, defaulting to the first line of its docstring.
      skills: The skills it works by that are somewhere else, one git URL apiece with an
        optional `#<skill>`. What it keeps in its own `skills/` needs no declaring.
      resumable: Whether it takes the state of the last run of it, and is handed a dict to
        write the next run's into.
      selectable: Whether to offer it in flow lists and the flow picker. False keeps an
        internal composition callable by name without presenting it as a flow to start.
      budget: What a run of it may spend by default, None for a flow with no opinion, and
        `Allowance()` for one that means to run under nothing at all.

    Returns:
      The function, unchanged but for what it now says about itself: a flow is called the way
      it always was, and a decorator that wrapped it would put itself between the flow and
      whatever reads its arguments.
    """

    def marks(said: Callable[P, T]) -> Callable[P, T]:
        setattr(
            said,
            _SAID,
            Flow(
                name=name,
                about=about or _first(said.__doc__),
                skills=tuple(skills),
                resumable=resumable,
                selectable=selectable,
                budget=budget,
            ),
        )
        return said

    return marks if call is None else marks(call)


def _first(said: str | None) -> str:
    """The first line of a docstring, which is what a flow says about itself in a list.

    "" for a docstring that is blank, which is a docstring somebody left room in rather than
    a flow to refuse: a flow says what it does or it does not.
    """
    lines = (said or "").strip().splitlines()
    return lines[0].strip() if lines else ""
