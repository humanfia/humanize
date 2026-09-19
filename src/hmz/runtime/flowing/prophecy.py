"""What an atlas compiles to: the prophecy a run of one walks, and the file it ships in.

An atlas is written with the marks in :mod:`hmz.flows.atlas` and read by
:mod:`hmz.runtime.flowing.prophesying`. This is what that reading answers with -- the nodes,
the edges, the shapes that flow along them -- and what :mod:`hmz.runtime.flowing.stepping`
walks a run over. None of it is a thing an atlas author writes, which is why it is here and
not beside the marks: a flow names what it declares, and never what its declaration was
turned into.

A prophecy is canonical: the same atlas written twice the same way compiles to the same text,
byte for byte, and :func:`digest` over that text is what a run picked up again checks itself
against. An atlas rewritten between two runs is a different prophecy, and a run that carried
on into it would be a run resuming into somewhere it had never been.

A flowverse may ship one beside the atlas it compiled, which is `prophecy.pkl`: the compiling
is where an atlas is refused, so a repository that has been through it has an answer worth
carrying. It is read back here and nowhere else -- and read back to this module's own tuples
and nothing else, since the file is opened by a reading whose whole promise is that it
executes nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    import os

    from hmz.flows.atlas import Kind

__all__ = [
    "AGENTS",
    "CONFIG",
    "INPUT",
    "Edge",
    "Field",
    "Node",
    "Prophecy",
    "Reads",
    "Shape",
    "Shipped",
    "When",
    "canonical",
    "digest",
    "kept",
    "shipped",
    "told",
]

#: What a node reads when it is handed one of the run's agents rather than a value: the
#: agents are what the run was started with rather than anything a node answered, so they
#: are named where a node id would be. Not an identifier, so nothing an atlas can write
#: collides with it.
AGENTS = "@agents"

#: And what it reads when it is handed the flow's own input -- the task a command line gave,
#: or the shape a supernode was called with.
INPUT = "@input"

#: And what it reads when it is handed what the run was set up with, for an atlas that says
#: it takes a config.
CONFIG = "@config"

class Field(NamedTuple):
    """One field of one shape, as the compiling read it off the model that declares it.

    Attributes:
      name: What the field is called.
      shape: The shape it holds, by name.
      required: Whether the model refuses to be built without it, which is what an edge is
        held to: what flows in has to cover what the far end cannot do without.
    """

    name: str
    shape: str
    required: bool


class Shape(NamedTuple):
    """One thing that may flow along an edge, read off the atlas's own files.

    Attributes:
      name: The model's name, or the plain kind -- `str`, `int`, `float`, `bool`.
      fields: One per field the model declares, in the order it declares them, and nothing at
        all for a plain kind, which has none.
    """

    name: str
    fields: tuple[Field, ...] = ()


class Reads(NamedTuple):
    """Where one of a node's arguments comes from.

    A name rather than the node that answered it, because a body may bind a name twice --
    which is what a loop is, the second binding being the one the next round reads. So a run
    keeps what each name holds now, and a node says which of them it wants.

    Attributes:
      reads: The name it reads: one the body bound, or :data:`AGENTS` for the run's agents,
        :data:`INPUT` for what the flow itself was called with, and :data:`CONFIG` for what
        it was set up with.
      field: The field read off it, and "" for the whole of it.
    """

    reads: str
    field: str = ""


class When(NamedTuple):
    """What has to hold for one edge to be the way out that is taken.

    Attributes:
      reads: The name the branch reads, which is one a node bound.
      field: The field read off it, and "" for the whole of it.
      truth: Whether this is the way out taken when that reads as true or as false.
    """

    reads: str
    field: str
    truth: bool


class Node(NamedTuple):
    """One node of a prophecy: one call site of the body it was compiled from.

    A node is a call site rather than a function, since a body that calls one function twice
    is a prophecy with two nodes in it -- each with its own answer, its own place in the run,
    and its own line in what a run picked up again has already done.

    Attributes:
      at: The node id: what it calls, and `:2`, `:3` after it where the body calls that same
        thing more than once. Read off the body's shape rather than off a line number, so
        that a file reformatted compiles to the prophecy it already was.
      kind: Which of the three it is.
      calls: The function it runs, by the name the atlas's own files declare it under -- or,
        for a supernode from another file, the flow by the name `-f` takes.
      takes: Where each of its arguments comes from, in the order it takes them.
      binds: The name its answer is bound to, and "" for a node whose answer nothing takes.
      gives: The shape it answers with, and "" for a node that answers with nothing.
      rerun: Whether a run picked up again runs it again where the last run stopped inside
        it, or steps past it.
      under: For a supernode, the prophecy it is, by the name that prophecy is called. "" for
        every other node.
    """

    at: str
    kind: Kind
    calls: str
    takes: tuple[Reads, ...] = ()
    binds: str = ""
    gives: str = ""
    rerun: bool = True
    under: str = ""


class Edge(NamedTuple):
    """One way from one node to the next.

    Attributes:
      out_of: The node it leaves, and "" for the way into the prophecy.
      into: The node it arrives at, and "" for the way out of it, which is where the run
        ends.
      when: What has to hold for this to be the way taken, and None for a node's only one.
      answers: For a way out of the prophecy, the name the run answers with -- which is what
        the `return` named, and not whatever the last node happened to say. "" everywhere
        else, and for an atlas that answers with nothing.
    """

    out_of: str
    into: str
    when: When | None = None
    answers: str = ""


class Prophecy(NamedTuple):
    """One atlas, compiled: the whole of what a run of it will do.

    Attributes:
      name: The flow, as it was asked for -- which for a supernode of another file is the
        name `-f` takes, and for one beside it is that file's own name for it.
      takes: The shape the flow is called with, which is `str` for one a command line runs
        and a model for one that is only ever a supernode.
      gives: The shape it answers with, and "" for one that answers with nothing.
      config: The shape it is set up with, and "" for one that takes no setting up -- which
        every supernode is, what is set up being the run rather than a node of it.
      agents: What the atlas calls each of the agents it drives, in the order it takes them.
      nodes: Every node, by node id.
      edges: Every way from one node to another, the way in and the way out included.
      shapes: Every shape anything in it carries, the ones its supernodes carry included.
      prophecies: One per supernode, which is the sub-atlas that node is.
    """

    name: str
    takes: str
    gives: str
    config: str
    agents: tuple[str, ...]
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    shapes: tuple[Shape, ...]
    prophecies: tuple[Prophecy, ...] = ()

    def node(self, at: str) -> Node | None:
        """The node of that id, or None where the prophecy holds none.

        Args:
          at: The node id.

        Returns:
          The node.
        """
        return next((one for one in self.nodes if one.at == at), None)

    def out_of(self, at: str) -> tuple[Edge, ...]:
        """Every way out of one node, in the order they are to be tried.

        Args:
          at: The node id, or "" for the way into the prophecy.

        Returns:
          The edges, the guarded ones first: a node with a branch and a way out that is
          taken otherwise is read as the branch it is rather than as a coin toss.
        """
        found = [one for one in self.edges if one.out_of == at]
        return tuple(sorted(found, key=lambda one: one.when is None))

    def under(self, named: str) -> Prophecy | None:
        """The sub-prophecy of that name, or None where this prophecy holds none.

        Args:
          named: What the supernode said it was.

        Returns:
          The prophecy.
        """
        return next((one for one in self.prophecies if one.name == named), None)


def canonical(prophecy: Prophecy) -> str:
    """One prophecy as the text two readings of the same atlas both answer with.

    Canonical means what it says: everything ordered by what it is rather than by where it
    was written, so a body reformatted, a comment added or two nodes swapped where nothing
    depends on the order compile to the same bytes. That is what makes :func:`digest` worth
    keeping -- a run picked up again asks whether the atlas is still the atlas it was, and an
    answer that changed when somebody reflowed a docstring would be no answer.

    Args:
      prophecy: The compiled atlas.

    Returns:
      JSON, keys sorted, one line: what a script diffs and what a person reads.
    """
    import json

    return json.dumps(_written(prophecy), sort_keys=True, ensure_ascii=False)


def _written(prophecy: Prophecy) -> dict[str, Any]:
    """One prophecy as the plain objects :func:`canonical` writes out.

    Read off the tuples themselves rather than field by field: everything here is a
    NamedTuple, so a field added to one later is a field the canonical text carries and the
    digest sees -- where a hand-written list of them would drop it without saying so, and
    two prophecies that differ would hash the same.

    Args:
      prophecy: The compiled atlas.

    Returns:
      Its nodes by id, its edges in order, its shapes by name and the prophecies under it by
      name -- each sorted, since the order a body happens to be written in is not part of
      what the atlas is.
    """
    return prophecy._asdict() | {
        "nodes": [one._asdict() for one in sorted(prophecy.nodes)],
        "edges": [one._asdict() for one in sorted(prophecy.edges, key=_ordered)],
        "shapes": [one._asdict() for one in sorted(prophecy.shapes)],
        "prophecies": [
            _written(one)
            for one in sorted(prophecy.prophecies, key=lambda one: one.name)
        ],
    }


def _ordered(edge: Edge) -> tuple[str, str, tuple[str, str, bool], str]:
    """One edge as something two of them can be sorted by, an absent guard and all."""
    return (edge.out_of, edge.into, edge.when or ("", "", False), edge.answers)


#: What a shipped prophecy is written with. Fixed rather than highest, so that the same
#: prophecy written by two installations is the same bytes -- a flowverse ships one, and a
#: file whose contents moved under a Python upgrade is a file every checkout re-writes.
_PROTOCOL = 5


def kept(prophecy: Prophecy) -> bytes:
    """One prophecy as the bytes a flowverse ships beside the atlas it compiled.

    Args:
      prophecy: The compiled atlas.

    Returns:
      What goes in `prophecy.pkl`.
    """
    import pickle

    return pickle.dumps(prophecy, protocol=_PROTOCOL)


#: The only classes a shipped prophecy is allowed to name. A pickle says which class to
#: build as it goes, and the reader that took it at its word would run whatever the file
#: asked for -- which the static reading of a flow, whose whole promise is that it executes
#: nothing, must not do for a file it found in a directory it was pointed at.
_SHAPES = frozenset({"Edge", "Field", "Node", "Prophecy", "Reads", "Shape", "When"})


def told(said: bytes) -> Prophecy | None:
    """One shipped prophecy read back, or None where those bytes are not one.

    Note:
      Nothing but a prophecy is built. A pickle names the class to build at every step, so
      one read as it comes runs whatever the file names -- and this file is read by the
      static reading of a flow, which is pointed at code nobody has read and promises to
      execute none of it. So the classes are held to this module's own tuples, and bytes
      naming anything else are bytes that are not a prophecy.

    Args:
      said: The bytes.

    Returns:
      The prophecy, or None for bytes that are not one -- truncated, written by something
      else, written by a humanize whose prophecies had another shape, or naming a class no
      prophecy is made of.
    """
    import io
    import pickle
    import sys as running

    class _Only(pickle.Unpickler):
        """An unpickler that builds this module's own tuples and refuses everything else."""

        def find_class(self, module: str, name: str) -> Any:
            """Refuses every class a prophecy is not made of.

            Args:
              module: The module the bytes name.
              name: The class in it they name.

            Returns:
              The class, for the tuples a prophecy is made of.

            Raises:
              UnpicklingError: For anything else, which is what makes reading this safe.
            """
            if module == __name__ and name in _SHAPES:
                return getattr(running.modules[__name__], name)
            raise pickle.UnpicklingError(f"a prophecy is not made of {module}.{name}")

    try:
        held = _Only(io.BytesIO(said)).load()
    except Exception:  # noqa: BLE001 -- anything a pickle raises is a file that is not one
        return None
    if not isinstance(held, Prophecy):
        return None
    try:
        canonical(held)
    except (AttributeError, TypeError, ValueError):
        # A named tuple of the right class holding the wrong things: written by a humanize
        # whose nodes had another shape, which is a prophecy to compile again rather than
        # one to walk.
        return None
    return held


class Shipped(NamedTuple):
    """What one flow's own directory ships beside its entry point.

    Attributes:
      at: The file it is in, which is `prophecy.pkl` beside the flow.
      prophecy: What it says, and None for bytes that are not a prophecy at all -- which is
        a file to compile again rather than a graph to guess at. Every reader of a shipped
        prophecy decides that for itself: one refuses the run, one says so as a finding.
    """

    at: Path
    prophecy: Prophecy | None


def shipped(under: str | os.PathLike[str]) -> Shipped | None:
    """The prophecy one flow's own directory ships, where it ships one.

    The one place `prophecy.pkl` is opened. Where it is, whether it is there, and what it
    takes to read it back are one rule rather than one per reader -- and what to do about a
    file that will not read back is each reader's own, since a run refuses and a checking
    says so.

    Args:
      under: The flow's own directory. A flow that is a single file has none, and passing
        the file is answered the same way as passing a directory with nothing in it.

    Returns:
      Where it is and what it says, or None where the flow ships nothing.
    """
    from .finding import PROPHECY

    at = Path(under) / PROPHECY
    if not at.is_file():
        return None
    return Shipped(at, told(at.read_bytes()))


def digest(prophecy: Prophecy) -> str:
    """What one compiled atlas is, in sixteen characters.

    What it is for is a run picked up again: what a run has already done is written down
    against the prophecy it was doing it in, and an atlas rewritten between two runs of it is a
    different prophecy whose nodes happen to share their names. Carrying on into it would be a
    run resuming into somewhere it has never been, so the digest is checked and a run whose
    prophecy has moved starts from the top.

    Args:
      prophecy: The compiled atlas.

    Returns:
      The first sixteen hex characters of the SHA-256 of :func:`canonical`.
    """
    import hashlib

    return hashlib.sha256(canonical(prophecy).encode()).hexdigest()[:16]
