"""What an atlas is written in: the marks a body declares its graph with.

A flow is a Python file that may branch any way it likes, and the one thing nothing can ask
it is what it is about to do. An atlas is the other bargain: a narrower Python, whose entry
point is read rather than run, and whose shape is therefore a graph that exists before
anything does. This is the half of that an atlas author writes -- the marks. What they are
compiled *to* is :mod:`hmz.runtime.flowing.prophecy`, and the compiling itself is
:mod:`hmz.runtime.flowing.prophesying`: neither is a thing an atlas names, so neither is a
thing this holds.

An atlas is a flow. It is marked, found, named, listed and run the way every other flow is,
so nothing that already knows what a flow is has to learn a second thing::

    from hmz._legacy_flows import Agent, atlas, logic, mind
    from pydantic import BaseModel

    class Agents(NamedTuple):
        writer: Agent
        reviewer: Agent

    class Draft(BaseModel):
        model_config = {"extra": "forbid"}
        text: str

    class Verdict(BaseModel):
        model_config = {"extra": "forbid"}
        done: bool

    @mind
    def write(agent: Agent, task: str) -> Draft: ...

    @logic
    def judge(said: Draft) -> Verdict: ...

    @atlas
    def run(agents: Agents, task: str) -> None:
        draft = write(agents.writer, task)
        verdict = judge(draft)
        while not verdict.done:
            draft = write(agents.writer, task)

There are two kinds of ordinary node and one kind that is a whole flow. A `mind` is a turn:
real work by a real agent, handed the agent the call site names. A `logic` is a Python
function: no agent, no turn, and a decision anything can read. An atlas called by another
atlas is a supernode -- one node from outside, one prophecy from within.

A mind has one way out and a logic may have several. That is the whole of why the two are
told apart: a branch is a decision, and a decision nothing but a model made is a decision no
reading of the flow can state. So the node a branch hangs off is a logic node, and what a
model said reaches a branch by being read by one.

A mark marks and does not wrap, the way :func:`~hmz._legacy_flows.flow` does and for the same
reason: a body is read rather than run, so what the mark said has to travel on the function,
where the reading will find it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = [
    "ATLAS",
    "MARKED",
    "Atlas",
    "Kind",
    "Marked",
    "Sub",
    "atlas",
    "logic",
    "mind",
    "sub",
]

#: What a node is: a turn taken by an agent, a Python function, or a whole atlas of its own.
#: The first two are what a prophecy is made of, and the third is what one prophecy is made of
#: another by, which is what a supernode is.
type Kind = Literal["mind", "logic", "atlas"]

#: Where a marked node keeps what its mark said, and where an atlas keeps that it is one. On
#: the function rather than in a table, for the reason `flow` puts it there: a file is read
#: by running it, and a mark that travels with the thing it describes is a mark there is only
#: one place to look for.
MARKED = "__humanize_node__"
ATLAS = "__humanize_atlas__"


@dataclass(frozen=True, slots=True)
class Atlas:
    """That a function is an atlas, and what the mark said beyond what `Flow` holds.

    An atlas carries this as well as the :class:`~hmz._legacy_flows.Flow` every flow carries, so
    that
    everything which already reads flows goes on reading this one, and only what compiles it
    has to know the difference.

    Attributes:
      name: What it is called inside its own file, which is the half after the colon, and ""
        for the one the file holds under its own name. The same name `flow` takes, and the
        same name a supernode of another file is reached by.
    """

    name: str = ""


@dataclass(frozen=True, slots=True)
class Marked:
    """What `mind` or `logic` marked a function with.

    Attributes:
      kind: Which of the two it is. A mind takes a turn and has one way out; a logic is
        Python and may have several.
      rerun: Whether a run picked up again runs this node again where the last run was
        stopped inside it. True is what a node says by saying nothing: work that was cut off
        partway is work that was not done. False is for a node that has had its effect by
        the time it can be interrupted -- and such a node answers with nothing, since a run
        stepping past it has no answer of its to carry on with.
    """

    kind: Kind
    rerun: bool = True


@dataclass(frozen=True, slots=True)
class Sub:
    """An atlas of another file, as the atlas reaching for it names it.

    Bound at the top of a file and called in a body, which is the one way an atlas reaches a
    flow that is not beside it::

        review = sub("official/review")

    Never called: an atlas's body is read rather than run, and what runs is the prophecy the
    reading compiled. Calling one is therefore an atlas being run some way this module knows
    nothing about, and says so rather than doing something surprising.

    Attributes:
      named: The flow, by the name `-f` takes.
    """

    named: str

    def __call__(self, *args: object, **kwargs: object) -> object:  # noqa: ARG002
        """Refuses: an atlas's body is compiled, and the prophecy is what runs.

        Args:
          args: Whatever the call was written with, which is read where it is written.
          kwargs: The same.

        Raises:
          TypeError: Always. A supernode is run by the prophecy around it, and a body that ran
            would be an atlas being run as though it were an ordinary flow.
        """
        raise TypeError(
            f"{self.named} is a supernode: an atlas's body is compiled rather than run, "
            "so nothing calls this outside the prophecy it was read into"
        )


def sub(named: str) -> Sub:
    """Names the atlas one supernode is, for a body to call it by.

    The counterpart of :func:`~hmz._legacy_flows.load`, and the only one an atlas has: `load`
    answers
    with a flow that may be anything, and an atlas that called one would be a prophecy with a
    hole where a node should be. So an atlas reaches another atlas, by the name `-f` takes,
    and reaches nothing else.

    Args:
      named: The flow, by the name `-f` takes -- `official/review`, `local/triage:pass`.

    Returns:
      Something for a body to call, which nothing ever calls: it is read where it is written,
      and the atlas it names is compiled into the prophecy reading it.
    """
    return Sub(named)


@overload
def mind[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def mind[**P, T](
    *, rerun: bool = True
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def mind[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as a node an agent takes a turn in -- the work itself.

    A mind is handed the agent the call site named and whatever else flows into it, and
    answers with a shape::

        @mind
        def write(agent: Agent, task: str) -> Draft:
            return agent(f"draft this: {task}", schema=Draft)

    It has exactly one way out. What a model said is not a decision until something read it,
    so a branch is hung off a logic node and never off this: a prophecy that branched on a
    turn would be a prophecy whose shape is whatever the model happened to say.

    Args:
      call: The function, when the mark is written with no arguments at all.
      rerun: Whether a run picked up again runs this node again where the last one stopped
        inside it, which is what a node says by saying nothing.

    Returns:
      The function, unchanged but for what it now says about itself.
    """
    return _noded("mind", call, rerun=rerun)


@overload
def logic[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def logic[**P, T](
    *, rerun: bool = True
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def logic[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as a node that is Python -- the deciding, the counting, the shaping.

    A logic drives no agent and takes no turn::

        @logic
        def judge(said: Draft) -> Verdict:
            return Verdict(done=said.text.endswith("."))

    It may have several ways out, which is what a branch in an atlas's body is: the value it
    answered with is read by the `if` or the `while` that follows it, and each way out is one
    answer to that reading.

    Args:
      call: The function, when the mark is written with no arguments at all.
      rerun: Whether a run picked up again runs this node again where the last one stopped
        inside it, which is what a node says by saying nothing.

    Returns:
      The function, unchanged but for what it now says about itself.
    """
    return _noded("logic", call, rerun=rerun)


def _noded[**P, T](
    kind: Kind, call: Callable[P, T] | None, *, rerun: bool
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks one function as a node, whichever of the two kinds it is.

    What the two marks share is the whole of how a decorator written bare and one written
    with arguments are told apart, which is a protocol worth having in one place rather than
    two: what differs between them is which kind it is, and what each says for itself.

    Args:
      kind: Which kind of node the mark makes it.
      call: The function, where the mark was written with no arguments at all.
      rerun: Whether a run picked up inside it runs it again.

    Returns:
      The function where there was one, and something to mark one where there was not.
    """

    def marks(said: Callable[P, T]) -> Callable[P, T]:
        setattr(said, MARKED, Marked(kind, rerun=rerun))
        return said

    return marks if call is None else marks(call)


@overload
def atlas[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def atlas[**P, T](
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    selectable: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def atlas[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    selectable: bool = True,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as an atlas: a flow whose body is a graph rather than a program.

    Everything :func:`~hmz._legacy_flows.flow` marks a flow with, this marks too -- the name, the
    line it says about itself, the skills it works by, whether it is offered in a list -- so
    an atlas is found, listed, chosen and run exactly as any other flow is. What it adds is
    that the body is read instead of executed::

        @atlas
        def run(agents: Agents, task: str) -> None:
            draft = write(agents.writer, task)
            verdict = judge(draft)

    The body is a declaration. Each statement in it is one node; the branches between them
    are the edges; and what actually runs is the prophecy that reading compiled, one node at a
    time, which is what lets a run be picked up in the middle of one.

    An atlas can always be picked up again, and says so without being asked: a prophecy is a
    list of nodes with an answer apiece, so what a run of one has done so far is something
    the run itself writes down. Nothing in the body writes state and nothing is handed a
    dict; a node that ran is a node whose answer was kept.

    An atlas that takes a shape rather than a task is a supernode and nothing else::

        @atlas(name="review")
        def review(agents: Agents, draft: Draft) -> Verdict:
            ...

    Args:
      call: The function, when the mark is written with no arguments at all.
      name: What to call this one among the flows its file holds, or "" for the one it holds
        under the file's own name.
      about: One line saying what it does, defaulting to the first line of its docstring.
      skills: The skills it works by that are somewhere else, one git URL apiece.
      selectable: Whether to offer it in flow lists and the flow picker.

    Returns:
      The function, unchanged but for what it now says about itself -- both marks, since an
      atlas is a flow and everything that reads flows must go on reading this one.
    """
    from . import flow

    def marks(said: Callable[P, T]) -> Callable[P, T]:
        setattr(said, ATLAS, Atlas(name=name))
        return flow(
            name=name,
            about=about,
            skills=skills,
            resumable=True,
            selectable=selectable,
        )(said)

    return marks if call is None else marks(call)
