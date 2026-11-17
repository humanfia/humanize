"""Every nous written down, and what can happen to one, as one object.

A nous is what an agent thinks with: a concrete one, `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`, or a
virtual one, a name that stands for a graph of other nous. Each is tried again as its envelope
says and then carried to its `then`. The file is :mod:`hmz.coganchor.nous`; this is what every
way in asks, so that a nous written from a command line is one the interface reads back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hmz.coganchor.nous import Graph, Member, Nous, Policy, Strategy

__all__ = ["NousBook"]


class NousBook:
    """Every nous written down, and the things that can happen to one."""

    def all(self) -> list[Nous]:
        """Every nous, in the order written down."""
        from hmz.coganchor import nous

        return nous.every()

    @property
    def default(self) -> str:
        """How a failed turn waits unless somebody said otherwise."""
        from hmz.coganchor import nous

        return nous.DEFAULT

    def policies(self) -> tuple[Policy, ...]:
        """How long a failed turn waits before it is taken again, plainest first."""
        from hmz.coganchor import nous

        return nous.POLICIES

    def named(self, policy: str) -> Policy | None:
        """The wait one name means, or None for a name none of them goes by."""
        from hmz.coganchor import nous

        return nous.named(policy)

    def strategies(self) -> tuple[Strategy, ...]:
        """How a balance node may pick, built in first and then those added."""
        from hmz.coganchor import nous

        return nous.strategies()

    def strategy(
        self, name: str, about: str, picks: Callable[[Sequence[Member]], str]
    ) -> Strategy:
        """Adds a strategy of one's own, for this process's balance nodes to pick by.

        Raises:
          ValueError: For a name already built in, or one that is not a word.
        """
        from hmz.coganchor import nous

        return nous.strategy(name, about, picks)

    def reads(self, said: str) -> str:
        """One nous as it is written down, and "" for a text that is no nous."""
        from hmz.coganchor import nous

        return nous.reads(said)

    def spec(
        self, backend: str, model: str, provider: str = "", effort: str = ""
    ) -> str:
        """One concrete nous, out of the four things it is."""
        from hmz.coganchor import nous

        return nous.spec(backend, model, provider, effort)

    def rule(self, said: str) -> Nous:
        """What is written down about one nous, which says nothing where nothing is."""
        from hmz.coganchor import nous

        return nous.rule(said)

    def graph(self, said: object) -> Graph | None:
        """A graph out of a nous, a list of nous tried in turn, or `start` and `nodes`.

        Raises:
          TypeError: For a shape that is none of those.
        """
        from hmz.coganchor import nous

        return nous.graph_of(said)

    def put(self, nous: Nous) -> Nous:
        """Writes one nous down, whole, in place of whatever was under its name.

        Raises:
          ValueError: For a nous that cannot be.
        """
        from hmz.coganchor import nous as nous_

        return nous_.put(nous)

    def virtual(
        self,
        name: str,
        graph: object,
        *,
        tries: int = 0,
        policy: str = "",
        timeout: float = 0.0,
        then: object = None,
    ) -> Nous:
        """Writes one virtual nous down: a name that stands for a graph.

        Args:
          name: What agents name it by.
          graph: Its graph, in any shape :meth:`graph` reads.
          tries: How many times over the graph is walked again before `then`.
          policy: How long to wait between those walks, or "" for the default.
          timeout: The longest the walking again may go on for, 0 for no limit.
          then: Where a turn goes once those walks are spent, or None for nowhere.

        Raises:
          ValueError: For a nous that cannot be.
          TypeError: For a graph of no shape there is.
        """
        from hmz.coganchor import nous

        return nous.put(
            nous.Nous(
                name,
                tries,
                policy or nous.DEFAULT,
                timeout,
                nous.graph_of(graph),
                nous.graph_of(then),
            )
        )

    def retrying(self, said: str, tries: int, policy: str, timeout: float) -> Nous:
        """Says how a failed turn at one nous is taken again before its `then`.

        Raises:
          ValueError: If it is not a nous, or the numbers are not ones to try again by.
        """
        from hmz.coganchor import nous

        return nous.retrying(said, tries, policy, timeout)

    def then(self, said: str, to: Graph | Sequence[str] | None) -> Nous:
        """Says where one nous's turns go once its tries are spent.

        Args:
          said: The nous.
          to: A graph, the nous tried one after another, or None or nothing for nowhere.

        Raises:
          ValueError: For a graph that cannot be.
        """
        from hmz.coganchor import nous

        return nous.then(said, to)

    def clear(self, said: str) -> bool:
        """Takes one nous away; whether there was one.

        Raises:
          ValueError: For a virtual nous another nous still names.
        """
        from hmz.coganchor import nous

        return nous.clear(said)

    def renamed(self, said: str, name: str) -> Nous:
        """Gives a virtual nous another name, every graph naming it following.

        Raises:
          ValueError: For a name that is no virtual nous, or one already taken.
        """
        from hmz.coganchor import nous

        return nous.renamed(said, name)

    def entry(self, said: str) -> str:
        """The concrete nous a walk of this nous starts at.

        Raises:
          ValueError: For a name that is no nous, or one with no concrete nous in it.
        """
        from hmz.coganchor import nous

        return nous.entry(said)
