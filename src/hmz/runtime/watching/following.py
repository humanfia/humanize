"""The runs one frontend follows, worked out from the records their host sends.

A host tells every frontend the same records -- a run starting, a session opening, what each
turn says and what it cost, a run ending -- and what a frontend draws of a run is worked out
from them: who is working and who handed to whom, and what each model has cost. Worked out here
once, for every frontend alike, rather than in each of them: two frontends drawing one run must
draw the same figures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .monitor import Monitor
from .tally import Seen, Tally

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Following"]


class Following:
    """The runs one frontend follows: the one in front of it, and any still unwinding behind.

    Fed the host's records as they arrive, on whichever thread they arrive on; what it keeps is
    read by whatever draws the run.

    Attributes:
      run: The run in front of the frontend, as its host numbers runs, or 0 before any.
      monitor: That run's graph, and its bill per model.
      tally: What that run has cost, read from the logs its agents keep as they go.
      seen: That run's sessions, by the key a frontend names one by, `<role>/<n>`.
    """

    def __init__(self) -> None:
        self.run = 0
        self.monitor = Monitor()
        self.tally = Tally([], self.monitor)
        self.seen: dict[str, Seen] = {}
        # Every run being followed, by number. A run stopped and still unwinding behind the
        # next is counted until it ends, which is when its last turn's tokens are in.
        self._followed: dict[int, tuple[Monitor, Tally]] = {}

    def started(self, record: Mapping[str, Any]) -> None:
        """Takes a run that has just started as the one in front of the frontend.

        Args:
          record: The run, as it started -- or as a `run` snapshot says it, for a run whose
            start was not kept for this frontend to read back.
        """
        self.run = int(record["run"])
        # The conversations of the run before this one went with it: this run's first
        # conversation is its role's first again.
        self.seen = {}
        self.monitor = Monitor(began=record["began"])
        # What the run costs is read from the logs the agents keep, which they write as they
        # go: a backend only says what a turn cost once the turn is over, and a turn is long.
        self.tally = Tally([], self.monitor)
        self._followed[self.run] = (self.monitor, self.tally)
        self.tally.watch()

    def opened(self, record: Mapping[str, Any]) -> Seen | None:
        """Takes one session a run has just opened as one of the run's own.

        Told on the run's own thread, before the session's first turn: what its backend counts
        is said to the monitor, and its logs are read for what it spends.

        Args:
          record: The session, as it opened.

        Returns:
          The session, or None for a person, who holds no conversation to count.
        """
        if record["person"]:
            return None
        seen = Seen(
            record["agent"],
            record["cli"],
            record["model"],
            frozenset(record["counts"]),
            kept=record.get("kept", ""),
            since=float(record.get("wall") or 0.0),
        )
        if record["run"] == self.run:
            self.seen[record["key"]] = seen
        followed = self._followed.get(record["run"])
        if followed is None:
            return seen
        monitor, tally = followed
        # What its backend counts, said before its first turn: a kind nothing was spent on
        # this turn is missing from that turn's reckoning exactly as a kind the CLI never
        # counts is, and what is drawn of a run driving two backends has to tell the two
        # apart to say which of its figures are whole.
        monitor.reporting(seen.id, seen.counts)
        tally.add(seen)
        return seen

    def heard(self, record: Mapping[str, Any]) -> str | None:
        """Takes what one thing a turn said means for the run: who is working, and what it cost.

        Called before anything is drawn of it: drawing a line raises once a frontend has
        gone, and what a watcher raises is swallowed, so accounting after it would be lost.

        Args:
          record: What was said, by whose turn and in which of its conversations.

        Returns:
          The conversation it was said in, `<role>/<n>`, where the run it is of is the one in
          front of the frontend -- or None, for something said outside any conversation or
          by a run unwinding behind the next, which numbers its conversations from one as
          that one does and so is the agent's alone.
        """
        agent, kind, text = record["agent"], record["kind"], record["text"]
        now: float = record["mono"]
        # The kinds go with the tokens where a turn spent them all on one model, which is the
        # ordinary turn: `spent` is that whole turn's cost by kind. A turn that named two --
        # an agent that reached for a cheaper model for a sub-turn -- says what each of them
        # cost and says the kinds of the pair together, and nothing in it says which of the
        # two a cached read was made against. So they are divided by what each model took,
        # rather than dropped: a turn whose kinds are dropped is a turn counted as tokens of
        # no kind at all, which is a turn missing from every per-kind figure and priced at
        # nothing. Where the CLI's own log is read as well, the exact split is in it, and the
        # fullest reckoning is the one the money and the kinds are both read off.
        tokens: dict[str, int] = record["tokens"]
        spent: dict[str, float] = record["spent"]
        whole = sum(tokens.values())
        ours = record["run"] == self.run
        numbered: str | None = (record["session"] or None) if ours else None
        for model, count in tokens.items():
            if not spent:
                broken = None
            elif len(tokens) == 1:
                broken = dict(spent)  # the whole turn, on the one model it named
            elif whole > 0:
                broken = {kind: one * count / whole for kind, one in spent.items()}
            else:
                # Two models and nothing on either. There is nothing to divide by and
                # nothing to divide, and a turn whose accounting raised would lose the
                # line it was about: what a watcher raises is swallowed.
                broken = None
            self.monitor.spend(
                agent, count, model=model, now=now, kinds=broken, session=numbered
            )
        # Anything at all the agent did, token or not: a tool, a word, an answer. A turn
        # spends most of its minutes between the counts it reports, and a figure worked out
        # only when one arrives stands still through all of them.
        self.monitor.stirring()
        seen = self.seen.get(record["session"]) if numbered is not None else None
        if seen is not None and record["ident"] not in ("", *seen.idents):
            # What the backend calls it, which is the name its log is kept under.
            seen.idents = seen.idents | {record["ident"]}
        if kind == "begins":
            self.monitor.begins(agent, record["model"], now=now, session=numbered)
        elif kind == "ends":
            self.monitor.ends(agent, now=now, session=numbered)
        elif kind in ("subagent", "subagent-ends"):
            # An agent this one started of its own, counted whether or not anything draws
            # it: a fleet nobody counted would be an agent working with nothing under it.
            named, _, about = text.partition(" ")
            if kind == "subagent":
                self.monitor.started(
                    agent, record["whose"], about or named, session=numbered
                )
            else:
                self.monitor.finished(
                    agent, record["whose"], about or named, session=numbered
                )
        return numbered

    def ended(self, record: Mapping[str, Any]) -> None:
        """Takes a run that has ended: its tally is read a last time, and its clocks stop.

        Args:
          record: The run, as it ended.
        """
        followed = self._followed.pop(record["run"], None)
        if followed is None:
            return
        monitor, tally = followed
        tally.stops()  # read once more, for what the last turn wrote on its way out
        monitor.stops()  # the clock the rate is over is the run's, and it is over
