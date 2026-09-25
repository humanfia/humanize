"""The flows there are, and the places they come from, as two objects rather than two modules.

What a flow is, is :mod:`hmz.flows`; finding one, reading one and running one is
:mod:`hmz.runtime.flowing`, and where the fetched ones are kept is the `verses` inside it.
All of it is reached from here so that a command line, an interface and a
daemon ask the one object rather than three modules apiece -- and so that the handful of
answers all three of them need spelled the same way, such as where a flowverse came from, are
spelled once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from pathlib import Path

    from hmz.runtime.flowing import Declaration, Flowverse, LiveCall, Offer

__all__ = ["Flows", "Flowverses"]

#: For a directory under the flowverses home that is not a clone of anything, or is one whose
#: origin cannot be read. Its flows are still offered, so it is still listed -- but where it
#: came from is a question it has no answer to, which is not the same as having come from here.
_NOWHERE = "-"


class Flowverses:
    """Where flows come from: what places there are, and the three things that happen to one.

    The same directories every way in walks, so that a flowverse added from a command line is
    one the interface offers a moment later.
    """

    def all(self) -> list[Flowverse]:
        """Every place there is, in the order their flows are offered."""
        from hmz.runtime.flowing import verses

        return verses.flowverses()

    def nearest(self) -> list[Flowverse]:
        """The same places, in the order a flow's name is looked up in."""
        from hmz.runtime.flowing import verses

        return verses.nearest()

    def find(self, name: str) -> Flowverse | None:
        """The place called this, or None for a name none answers to."""
        from hmz.runtime.flowing import verses

        return verses.named(name)

    def add(self, url: str, name: str = "") -> Flowverse:
        """Fetches a place and offers its flows under a name.

        Args:
          url: A URL, a path, or `owner/repo` for one on GitHub.
          name: What to keep it under, defaulting to the repository's own name.

        Returns:
          The flowverse, fetched.

        Raises:
          ValueError: If the name is taken, is one of the ones always there, or is not one a
            directory may be called.
          OSError: If it cannot be cloned or kept.
        """
        from hmz.runtime.flowing import verses

        return verses.add(url, name)

    def fetch(self, name: str) -> Flowverse:
        """Fetches one again, or for the first time.

        Args:
          name: What it is listed under.

        Returns:
          The flowverse, as it now stands.

        Raises:
          ValueError: If no place answers to that name, or it is one nothing fetches.
          OSError: If git refused.
        """
        from hmz.runtime.flowing import verses

        return verses.fetch(name)

    def remove(self, name: str) -> bool:
        """Takes one away, flows and all.

        Args:
          name: What it is listed under.

        Returns:
          Whether there was one to take away.

        Raises:
          ValueError: If it is one of the ones that are always there.
          OSError: If the directory will not go.
        """
        from hmz.runtime.flowing import verses

        return verses.remove(name)

    def holds(self, one: Flowverse) -> list[Offer]:
        """What one place holds, by the name each flow is offered under.

        Reading a flow means running it, so this is the one question about a place with no
        cheap answer -- and it is asked of the place named rather than of all of them.

        Args:
          one: The flowverse.

        Returns:
          One offer per flow in it: just the ones in the package for humanize's own before it
          has been fetched, and nothing at all for any other that has not been.
        """
        from hmz.runtime.flowing import offers

        return offers(one)

    def edited(self, one: Flowverse) -> bool:
        """Whether one has anything written into it that fetching it again would undo.

        Asked by whatever fetches without being asked to. A fetch resets the clone to what the
        repository says now, which is a fair thing to do on a key somebody pressed and not a
        fair thing to do behind them.

        Args:
          one: The flowverse.

        Returns:
          Whether there is anything of somebody's own in it, and False for one that is not a
          clone at all -- there being no fetch to take anything away.
        """
        from hmz.runtime.flowing import verses

        return verses.edited(one.at)

    def standing(self, one: Flowverse) -> str:
        """Which commit its clone stands at, which a fetch moves only where it brought something.

        Asked either side of a fetch by whatever fetches without being asked to. Most of those
        fetches bring nothing down -- the repository has not moved since the last one -- and
        everything that reads a place's flows reads them by running them, so what is done
        about a fetch that landed is worth doing only about the ones that landed something.

        Args:
          one: The flowverse.

        Returns:
          The commit, and "" for a directory that is not a clone -- which is what a place
          nobody has fetched yet reads as, and compares unequal to whatever it stands at once
          it has been.
        """
        from hmz.runtime.flowing import verses

        return verses.standing(one.at)

    def where(self, name: str) -> Path:
        """The directory one place is kept in, whether or not anything has been fetched into it."""
        from hmz.runtime.flowing import verses

        return verses.where(name)

    def plain(self, url: str) -> str:
        """A URL with whatever was signed into it taken out, as it may be printed."""
        from hmz.runtime.flowing import verses

        return verses.plain(url)

    def whence(self, one: Flowverse, nowhere: str = _NOWHERE) -> str:
        """Where a place came from, as it may be shown to somebody.

        Asked of which flowverse it is rather than of whether its URL is empty. An empty URL
        means two different things -- the two directories your own flows live in, and a
        directory whose origin could not be read -- and answering both with the first would
        put your name on somebody else's flows.

        Args:
          one: The flowverse.
          nowhere: What to say for a directory that is not a clone of anything, or is one
            whose origin cannot be read. Whoever is showing it says it: a listing has a
            column of them and a sheet has a sentence.

        Returns:
          The URL with anything secret in it taken out, or what it is instead for the ones
          that have none. Scrubbed here rather than at each of the places that shows it: this
          line is printed every time the places are listed, and a token printed once is a
          token in the log of every job that ran it.
        """
        from hmz.runtime.flowing.verses import MINE, plain

        if one.name in MINE:
            return f"your own flows in {MINE[one.name]}"
        return plain(one.url) if one.url else nowhere


class Flows:
    """The flows there are: what is offered, what one of them takes, and what one says it is."""

    def __init__(self) -> None:
        self._verses = Flowverses()

    @property
    def verses(self) -> Flowverses:
        """Where the flows come from."""
        return self._verses

    def all(self) -> list[Offer]:
        """Every flow there is to run, by the name `-f` takes."""
        from hmz.runtime.flowing import found

        return found()

    def find(self, named: str) -> str:
        """The file one flow is written in.

        Args:
          named: The flow, by the name it is offered under or by a path to a file.

        Returns:
          The path to run, resolved -- and `named` itself where nothing answers to it, so
          that whatever asked hears the name back rather than an exception it would have to
          tell apart from a flow that is genuinely called that. Whether a flow is there is
          answered by what comes back being a file.
        """
        from hmz.runtime.flowing import find

        return find(named)

    def about(self, named: str) -> str:
        """The line a flow says about itself, and "" for one that says nothing."""
        from hmz.runtime.flowing import about

        return about(named)

    def declared(self, named: str | os.PathLike[str]) -> Declaration:
        """Everything a flow declares: its agent and environment roles, params and marks.

        What a picker offers a flow's roles from, and what a line naming them is read
        against -- the roles the runtime fills among them, marked as such.

        Args:
          named: The flow, by the name `-f` takes, a path, or a ref.

        Returns:
          The declaration.

        Raises:
          FlowException: If the flow cannot be loaded -- not there, not a ref, written wrong
            -- as the flow API names what went wrong.
        """
        from hmz.runtime.flowing import resolved

        return resolved(str(named)).describe()

    def resumes(self, named: str | os.PathLike[str]) -> bool:
        """Whether a flow says it can be picked up where the last run of it left off."""
        return self.declared(named).resumable

    def fork(self, named: str, into: str | os.PathLike[str] | None = None) -> str:
        """Copies a flow into this project's own flows, whole -- what it imports and all.

        Args:
          named: The flow, by the name it is offered under.
          into: Where to put it, defaulting to this project's own flows.

        Returns:
          The directory it was copied to, spelled as it was reached -- this project's own
          flows are named from the project, so a copy that went there is named from there
          too. The name it is offered under from now on is the one it already had, yours
          being looked in first: `official/rlar` forked is `rlar`.

        Raises:
          ValueError: If nothing of that name is a flow, or there is already one of that
            name here -- which is a copy to edit, run or take away rather than one to write
            over.
          OSError: If it cannot be copied.
        """
        from hmz.runtime.flowing import fork

        return fork(named, into)

    def running(self) -> tuple[LiveCall, ...]:
        """Every flow call going in this process now, oldest first.

        Each says its flow, how deep it is and which call made it: the running tree, read the
        same way from anywhere, inside a flow or out.
        """
        from hmz.runtime.flowing import running

        return running()
