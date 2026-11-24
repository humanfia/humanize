"""Every nous a daemon knows, concrete and virtual (`nous.*`).

A concrete nous is `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`; a virtual one is a name for a graph of
other nous. Either has its tries, its way of waiting between them, its limit, and the graph a
turn goes to once those are spent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["Book", "Entry", "Failed", "Graph", "Kind", "Member", "Node", "Nous"]

#: A graph as a call takes one: a nous, a list of them tried in turn, or `start` and `nodes`.
type Written = str | Sequence[str] | Mapping[str, Any]


@dataclass(frozen=True)
class Member:
    """One nous a balancing node picks among, and how often."""

    nous: str
    weight: int


@dataclass(frozen=True)
class Node:
    """One node of a graph: a nous to use, or several to balance among."""

    id: str
    use: str
    """The nous it uses, `""` for a node that balances."""
    balance: str
    """The strategy it picks by, `""` for a node that uses one nous."""
    among: tuple[Member, ...]
    spread: int
    """How many of them a balancing node spreads a turn over, `0` for one."""
    on: dict[str, str]
    """Where a turn goes on each fault, by the fault; `*` is any other."""


@dataclass(frozen=True)
class Graph:
    """A graph of nous: where a turn starts, and where it goes as each fails."""

    start: str
    nodes: tuple[Node, ...]

    def sent(self) -> dict[str, Any]:
        """It, as `nous.set` takes one."""
        return {
            "start": self.start,
            "nodes": [
                {
                    "id": one.id,
                    "use": one.use,
                    "balance": one.balance,
                    "among": [
                        {"nous": each.nous, "weight": each.weight} for each in one.among
                    ],
                    "spread": one.spread,
                    "on": dict(one.on),
                }
                for one in self.nodes
            ],
        }


@dataclass(frozen=True)
class Entry:
    """What is written of one nous."""

    name: str
    virtual: bool
    tries: int
    """How many more goes a turn that fails there is given."""
    policy: str
    """How long is waited between them, as one of the book's `policies`."""
    timeout: float
    """How many seconds a turn is given, `0` for no limit."""
    graph: Graph | None
    """What a virtual nous stands for; None for a concrete one."""
    then: Graph | None
    """Where a turn goes once its tries are spent; None for nowhere."""


@dataclass(frozen=True)
class Kind:
    """One way of waiting, or of picking, there is: its name and what it does."""

    name: str
    about: str


@dataclass(frozen=True)
class Failed:
    """One harness that would not say what it runs as one account."""

    cli: str
    account: str
    why: str


@dataclass(frozen=True)
class Book:
    """Every nous written, and everything one can be written with."""

    nous: tuple[Entry, ...]
    policies: tuple[Kind, ...]
    """The ways of waiting between tries."""
    default: str
    """The policy a nous written without one waits by."""
    strategies: tuple[Kind, ...]
    """The ways a balancing node picks."""
    faults: tuple[str, ...]
    """Every fault an edge can be for, and `*`."""
    concrete: tuple[str, ...]
    """Every concrete nous the daemon's harnesses last said they run, without an effort."""
    scanning: bool
    """Whether a scan is going on."""
    failed: tuple[Failed, ...]
    """What a scan could not ask; empty from any other call."""
    said: dict[str, Any]
    """Everything the daemon answered."""

    def entry(self, name: str) -> Entry | None:
        """What is written of the nous of that name, or None."""
        return next((one for one in self.nous if one.name == name), None)


def _graph(said: Mapping[str, Any] | None) -> Graph | None:
    if said is None:
        return None
    return Graph(
        start=str(said["start"]),
        nodes=tuple(
            Node(
                id=str(one["id"]),
                use=str(one.get("use") or ""),
                balance=str(one.get("balance") or ""),
                among=tuple(
                    Member(str(each["nous"]), int(each.get("weight", 1)))
                    for each in one.get("among") or ()
                ),
                spread=int(one.get("spread") or 0),
                on=dict(one.get("on") or {}),
            )
            for one in said.get("nodes") or ()
        ),
    )


def _kinds(said: Sequence[Mapping[str, Any]] | None) -> tuple[Kind, ...]:
    return tuple(
        Kind(str(one["name"]), str(one.get("about") or "")) for one in said or ()
    )


def _book(said: Mapping[str, Any]) -> Book:
    return Book(
        nous=tuple(
            Entry(
                name=str(one["name"]),
                virtual=bool(one.get("virtual")),
                tries=int(one.get("tries") or 0),
                policy=str(one.get("policy") or ""),
                timeout=float(one.get("timeout") or 0),
                graph=_graph(one.get("graph")),
                then=_graph(one.get("then")),
            )
            for one in said.get("nous") or ()
        ),
        policies=_kinds(said.get("policies")),
        default=str(said.get("default") or ""),
        strategies=_kinds(said.get("strategies")),
        faults=tuple(said.get("faults") or ()),
        concrete=tuple(said.get("concrete") or ()),
        scanning=bool(said.get("scanning")),
        failed=tuple(
            Failed(str(one["cli"]), str(one["account"]), str(one["why"]))
            for one in said.get("failed") or ()
        ),
        said=dict(said),
    )


def _sent(graph: Graph | Written | None) -> Any:
    if isinstance(graph, Graph):
        return graph.sent()
    if graph is None or isinstance(graph, str):
        return graph
    return dict(graph) if isinstance(graph, Mapping) else list(graph)


class Nous(Family):
    """Every nous a daemon knows."""

    METHODS: ClassVar = (
        "nous.list",
        "nous.scan",
        "nous.set",
        "nous.rename",
        "nous.clear",
    )

    def list(self) -> Book:
        """Every nous written, and what one can be written with. Asks no harness."""
        return _book(self._call("nous.list"))

    def scan(self, *, idem: str | None = None, wait: float | None = None) -> Book:
        """Asks every installed harness what it runs, as each of its accounts.

        Args:
          idem: The key this is done once under.
          wait: How many seconds the scan is waited for, None for as long as it takes.

        Returns:
          The book as it is afterwards, `failed` naming each harness that would not answer:
          one that does not answer does not fail the call.
        """
        return _book(self._call("nous.scan", idem=idem, wait=wait))

    def set(
        self,
        name: str,
        *,
        tries: int | None = None,
        policy: str | None = None,
        timeout: float | None = None,
        graph: Graph | Written | None = None,
        then: Graph | Written | None = None,
        idem: str | None = None,
    ) -> Book:
        """Writes a nous, whole: what is not given is written as its default, not kept.

        Args:
          name: The nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, any other
            name for a virtual one.
          tries: How many more goes a turn that fails there is given; None for `0`.
          policy: How long is waited between them; None for the book's `default`.
          timeout: How many seconds a turn is given; None or `0` for no limit.
          graph: What a virtual nous stands for: a :class:`Graph`, a nous, a list of nous
            tried in turn, or a mapping of `start` and `nodes`. None for a concrete nous.
          then: Where a turn goes once its tries are spent, in the same shapes; None for
            nowhere.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 400 for a value that is not one.
        """
        return _book(
            self._call(
                "nous.set",
                name=name,
                tries=tries,
                policy=policy,
                timeout=timeout,
                graph=_sent(graph),
                then=_sent(then),
                idem=idem,
            )
        )

    def rename(self, name: str, to: str, *, idem: str | None = None) -> Book:
        """Renames a virtual nous, in every graph that names it too.

        Raises:
          hmz.sdk.Refused: 400 for a name that cannot be given.
        """
        return _book(self._call("nous.rename", name=name, to=to, idem=idem))

    def clear(self, name: str, *, idem: str | None = None) -> Book:
        """Removes what is written of a nous.

        Raises:
          hmz.sdk.Refused: 404 for a nous with nothing written; 400 for one another names.
        """
        return _book(self._call("nous.clear", name=name, idem=idem))
