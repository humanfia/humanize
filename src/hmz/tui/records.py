"""A run held in this process, told as the records every frontend reads a run by.

The interface draws a run from records alone: the run starting, each session it opens, every
event of every turn, the run ending, and which flow calls are going. A record is plain JSON --
names, numbers and words, never the agent or the conversation it is about -- so what is drawn
from one is drawn the same wherever the run is held. Until a run is held somewhere else, one
held here is turned into them here: the builders below make one apiece, and `Following` hangs
off the run to tell them as the run says what it says.

What a record cannot carry is the conversation itself, which three things still reach for: a
word put into a turn, a side question asked of a session, and the board a person shares with
the flow. So `Following` keeps the agent and the conversation behind each key it has told of,
and those three are the only readers of it.
"""

from __future__ import annotations

import json
import os
import threading
import time
import weakref
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from hmz.coganchor.agents import AgentBase, Event, SessionBase
    from hmz.flows import Budget
    from hmz.runtime.flowing import LiveCall

__all__ = ["Following", "called", "ended", "opened", "record", "started"]

#: How often the flow calls going are looked at, in seconds: as often as the line naming them
#: is drawn, and no oftener.
_EVERY = 0.5

#: How many of a run's conversations are kept once the run has let go of them, newest kept:
#: a loop that opens a session a round runs for days, and one ended long ago is asked about
#: by nobody.
_KEPT = 256

#: What keeps the flow calls told in the order they were looked at, whichever run looks: the
#: calls going are every run's in this process, and a look told late would stand for good.
_LOOKING = threading.Lock()


def started(
    run: int,
    *,
    flow: str,
    task: str,
    ref: str = "",
    by: str = "",
    client: str = "",
    roles: Sequence[str] = (),
    outworlders: Sequence[str] = (),
    agents: Mapping[str, str] | None = None,
    envs: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    budget: Budget | None = None,
    resume: str = "",
) -> dict[str, Any]:
    """A run starting: which flow, on what, set up how, and by whom.

    Args:
      run: Which run it is, counted.
      flow: The flow, as it was named.
      task: What it is to do.
      ref: The flow's canonical ref, where it is known yet.
      by: Who started it, as a frontend names itself.
      client: Which frontend that was, or "" for the only one there is.
      roles: Its agent roles, in the order the flow declares them.
      outworlders: Its `Outworlder` roles, likewise.
      agents: What each agent role runs, as `-a` spells one.
      envs: What each environment role is, as `-e` spells one.
      params: What the flow is set up with, as JSON.
      budget: What it may spend, or None for nothing said.
      resume: The epic it picks up, or "" for a run from the top.

    Returns:
      The record, which says when the run began on the monotonic clock every clock it
      draws is read against.
    """
    return {
        "type": "started",
        "run": run,
        "flow": flow,
        "ref": ref,
        "task": task,
        "by": by,
        "client": client,
        "roles": list(roles),
        "outworlders": list(outworlders),
        "agents": dict(agents or {}),
        "envs": dict(envs or {}),
        "params": dict(params or {}),
        "budget": json.loads(budget.model_dump_json()) if budget is not None else {},
        "resume": resume,
        "began": time.monotonic(),
        "at": time.time(),
    }


def opened(
    run: int, role: str, key: str, agent: AgentBase, session: SessionBase | None
) -> dict[str, Any]:
    """A session a run has just opened, before its first turn.

    Args:
      run: Which run opened it.
      role: The role it was opened for.
      key: The transcript it is read on, `<role>/<n>` for the n-th that role opened.
      agent: The agent behind it, named for its role.
      session: Its conversation, or None for a person, who holds none.

    Returns:
      The record: what it runs and which kinds of token its backend counts, which is said
      before its first turn since a kind nothing was spent on is not a kind never counted.
    """
    from hmz.coganchor.agents import HumanAgent

    return {
        "type": "opened",
        "run": run,
        "role": role,
        "key": key,
        "agent": agent.id,
        "cli": agent.backend,
        "model": agent.config.model,
        "counts": sorted(type(agent).counts),
        "forks": session is not None and session.forks,
        "person": isinstance(agent, HumanAgent),
        "kept": "" if isinstance(agent, HumanAgent) else str(agent.kept()),
        "mono": time.monotonic(),
    }


def record(
    agent: AgentBase,
    session: SessionBase | None,
    event: Event,
    *,
    key: str = "",
    run: int = 0,
) -> dict[str, Any]:
    """One thing a turn said, as every frontend reads it.

    Args:
      agent: Whose turn said it.
      session: Which of its conversations said it, or None for something the agent said for
        all of them -- a question a server puts for every conversation it holds.
      event: What was said.
      key: The transcript it goes on: the conversation's, or for one the agent said, the
        conversation of it working or its newest.
      run: Which run it is of.

    Returns:
      The record. Its `session` is the key only where the event named a conversation, and
      its `ident` what the backend calls that conversation, which is how its log is found.
    """
    return {
        "type": "event",
        "run": run,
        "key": key,
        "session": key if session is not None else "",
        "agent": agent.id,
        "cli": agent.backend,
        "model": agent.config.model,
        "ident": (session.named if session is not None else None) or "",
        "kind": event.kind,
        "text": event.text,
        "whose": event.whose,
        "tokens": dict(event.tokens),
        "spent": dict(event.spent),
        "at": time.time(),
        "mono": time.monotonic(),
    }


def ended(run: int, how: str, why: str = "") -> dict[str, Any]:
    """A run over, and how it went.

    Args:
      run: Which run.
      how: `done`, `stopped`, `budget`, `refused`, `failed` or `crashed`.
      why: What it said about it, or "" for nothing to say.

    Returns:
      The record.
    """
    return {
        "type": "ended",
        "run": run,
        "how": how,
        "why": why,
        "mono": time.monotonic(),
    }


def called(running: Sequence[LiveCall]) -> dict[str, Any]:
    """Every flow call going, oldest first: the running tree, as a snapshot.

    Args:
      running: The calls, as the runtime says them.

    Returns:
      The snapshot: each call's flow by its canonical ref, its name, how deep it is, when it
      started on the monotonic clock, its id, and the call that made it by its place here.
    """
    at = {id(one): index for index, one in enumerate(running)}
    return {
        "type": "calls",
        "calls": [
            {
                "ref": one.ref,
                "name": one.name,
                "depth": one.depth,
                "since": one.since,
                "id": one.id,
                "parent": None if one.parent is None else at.get(id(one.parent)),
            }
            for one in running
        ],
    }


class Following:
    """One run held here, told as records, and the agent and conversation behind each key.

    Its conversations are numbered as the run opens them -- `builder/2` is the second a
    builder opened, whichever spoke first -- which is the key a record names a transcript, a
    node of the monitor and a side question by. What an agent says for all of its
    conversations goes on the one of them working, or on its newest.
    """

    def __init__(
        self,
        run: int,
        told: Callable[[dict[str, Any]], None],
        *,
        waiting: Callable[[], list[str]] | None = None,
        running: Callable[[], Sequence[LiveCall]] = tuple,
    ) -> None:
        """Follows a run that has said nothing yet.

        Args:
          run: Which run it is, counted, as every record of it says.
          told: Where each record goes, on whichever thread the run said it.
          waiting: What a turn of it folds into its prompt as it starts, hung on each agent
            as the run opens it.
          running: The flow calls going in this process, looked at for as long as it runs.
        """
        self.run = run
        self._told = told
        self._waiting = waiting
        self._running = running
        self._lock = threading.Lock()
        #: Which key each conversation is, held weakly: a loop that opens a session a round
        #: would otherwise keep every one it ever opened.
        self._numbered: weakref.WeakKeyDictionary[SessionBase, str] = (
            weakref.WeakKeyDictionary()
        )
        self._opened_of: dict[str, int] = {}
        #: The conversations with a turn open, which is where what an agent says for all of
        #: them goes.
        self._working: weakref.WeakSet[SessionBase] = weakref.WeakSet()
        #: The agent behind every key, as long as the run is held; and the newest of their
        #: conversations, held here as well as by whatever holds them, since the agents hold
        #: theirs weakly and one that has ended is still one to ask about.
        self._agents: dict[str, AgentBase] = {}
        self._kept: dict[str, SessionBase] = {}
        self._over = threading.Event()

    def starts(self, **started_with: Any) -> None:
        """Tells the run starting, and looks at its flow calls from now until it ends.

        Args:
          started_with: What `started` takes after the run, bar who started it.
        """
        by = f"{os.environ.get('USER', '')}@tui"
        self._told(started(self.run, by=by, **started_with))

        def watching() -> None:
            while not self._over.wait(_EVERY):
                self._looks()

        threading.Thread(target=watching, daemon=True).start()

    def opens(self, role: str, agent: AgentBase, session: SessionBase | None) -> None:
        """Tells one session the run has just opened, which is what `Run.opened` calls.

        Numbered now, in the order the run opens them, rather than as each first speaks.

        Args:
          role: The role it was opened for.
          agent: The agent behind it.
          session: Its conversation, or None for a person.
        """
        key = self._key_of(agent, session)
        # Whichever turn of it starts next takes the oldest line that was held.
        agent.waiting = self._waiting
        with self._lock:
            self._agents.setdefault(key, agent)
            if session is not None and key not in self._kept:
                self._kept[key] = session
                while len(self._kept) > _KEPT:
                    del self._kept[next(iter(self._kept))]
        self._told(opened(self.run, role, key, agent, session))

    def hears(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Tells one thing a turn said, which is what `Run.watch` calls.

        Args:
          agent: Whose turn said it.
          session: Which of its conversations, or None for the agent's own.
          event: What was said.
        """
        if session is not None and event.kind == "begins":
            self._working.add(session)
        elif session is not None and event.kind == "ends":
            self._working.discard(session)
        key = self._key_of(agent, session)
        self._told(record(agent, session, event, key=key, run=self.run))

    def ends(self, how: str, why: str = "") -> None:
        """Tells the run over, having said the flow calls it leaves going.

        Args:
          how: How it went, as `ended` takes it.
          why: What it said about it.
        """
        self._over.set()
        self._looks()
        self._told(ended(self.run, how, why))

    def behind(self) -> list[tuple[str, AgentBase, SessionBase | None]]:
        """Every key told of, oldest first, with what is behind it.

        Returns:
          The key, the agent, and its conversation -- None for a person, and for one that
          nothing holds any more.
        """
        with self._lock:
            keys = list(self._agents)
        return [(key, *self.at(key)) for key in keys]

    def at(self, key: str) -> tuple[AgentBase, SessionBase | None]:
        """What is behind one key: its agent, and its conversation while anything holds it.

        Args:
          key: The key, as a record names it.

        Returns:
          The agent and the conversation, the conversation None where it has gone.

        Raises:
          KeyError: For a key this run never told of.
        """
        with self._lock:
            agent = self._agents[key]
            session = self._kept.get(key)
        if session is None:
            held = agent.sessions
            with self._lock:
                session = next(
                    (one for one in held if self._numbered.get(one) == key), None
                )
        return agent, session

    def _key_of(self, agent: AgentBase, session: SessionBase | None) -> str:
        """The transcript a conversation's lines go on, numbering it the first time.

        Args:
          agent: Whose conversation it is.
          session: The conversation, or None for something the agent said for all of them.

        Returns:
          `<role>/<n>` for the n-th conversation the role opened, counting from one; the one
          working or the newest for the agent's own; and the role alone where it has none.
        """
        if session is None:
            held = agent.sessions
            session = next(
                (one for one in reversed(held) if one in self._working), None
            ) or next(reversed(held), None)
        if session is None:
            return agent.id
        with self._lock:
            key = self._numbered.get(session)
            if key is None:
                counted = self._opened_of[agent.id] = (
                    self._opened_of.get(agent.id, 0) + 1
                )
                key = self._numbered[session] = f"{agent.id}/{counted}"
        return key

    def _looks(self) -> None:
        """Tells the flow calls going, as they are now."""
        with _LOOKING:
            self._told(called(self._running()))
