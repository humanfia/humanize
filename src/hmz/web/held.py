"""The runs held for a workspace, as the web interface follows them and acts on them.

One link to a host of a workspace's runs, as every frontend holds one -- the workspace's own,
or one chat's beside it, by its `slot` -- and what it tells is
kept here -- the records of the runs it has told of, in order, how each thing stands now, and
the figures worked out of them -- and handed to every page that listens, from wherever that
page last heard. What a page asks of the runs goes back down the same link, and what the runs
refuse is refused with the reason they give. A side question about the run is asked down it
too, of a side conversation the runs open beside the run rather than of the run itself.
"""

from __future__ import annotations

import bisect
import contextlib
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import traceback
from types import NoneType
from typing import TYPE_CHECKING, Any

from .routing import Refusal, Stream, routes

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from hmz.daemon import Link
    from hmz.runtime.watching.btw import Btw, FlowSnapshot

    from .routing import Asked

__all__ = ["ROUTES", "Held"]

#: What a host says of how things stand, each sent again whenever it changes: who is
#: attached, who holds which role, who is away, the run, its sessions and calls, the lines
#: waiting, the questions waiting, what the run has spent, and its board.
STANDING = frozenset(
    {
        "clients",
        "claims",
        "away",
        "run",
        "sessions",
        "calls",
        "waiting",
        "pending",
        "usage",
        "board",
    }
)

#: How many records are kept for a page arriving late: a run's whole story while it is a
#: story of thousands of lines, and its last stretch past that.
_KEPT = 20_000

#: About how much of them, in bytes: the same ceiling a host keeps its own records under, so
#: that a run of long tool outputs is held to it as well as a run of many short lines.
_WEIGHED = 32 << 20

#: What a record weighs besides what it says, in bytes: its keys and its numbers.
_FRAME = 256

#: How many side questions and their answers are kept, for a page arriving late to read.
_SAID = 200

#: How long a stream opened as this interface attaches waits to be told who it is.
_WELCOMED = 2.0

#: How often what a run has done is worked out again while it runs: as often as a clock on
#: the page is worth moving.
_FIGURING = 1.0

#: How long a stream says nothing before it says it is still there.
_QUIET = 15.0

#: How long between tries to reach the runs again, once they have let this go.
_AGAIN = 2.0

#: What each thing a page may ask of the runs takes: each field, what it may be, and what it
#: is where it is not sent -- or `...` where it must be.
_ACTS: dict[str, dict[str, tuple[tuple[type, ...], Any]]] = {
    "start": {
        "flow": ((str,), ...),
        "task": ((str,), ...),
        "agents": ((dict,), {}),
        "envs": ((dict,), {}),
        "params": ((dict, NoneType), None),
        "budget": ((dict, NoneType), None),
        "profile_flow": ((bool,), False),
        "profile_environment": ((bool,), False),
        "resume": ((bool, str), False),
        "backup": ((list, NoneType), None),
    },
    "say": {"text": ((str,), ...), "to": ((str,), "")},
    "answer": {"question": ((str,), ...), "text": ((str,), ...)},
    "stop": {},
    "force": {},
    "afk": {"on": ((bool,), ...), "role": ((str,), "")},
    "claim": {"role": ((str,), ...), "take": ((bool,), False)},
    "release": {"role": ((str,), ...)},
    "board": {"key": ((str,), ...), "value": ((str,), "")},
}


class Held:
    """The runs of one workspace, as this interface follows them through its link.

    Args:
      linking: What makes a link to them, attached: the first one, and another each time the
        runs let one go.
      again: Whether to reach them again once they let this go -- not a chat's, which goes
        when it folds away and is carried on by a host of its own.
    """

    def __init__(self, linking: Callable[[], Link], *, again: bool = True) -> None:
        from hmz.runtime.watching.following import Following

        self._linking = linking
        self._reaches = again
        self._changed = threading.Condition()
        self._closed = False
        # Everything below is one link's, and is made again with the next.
        self._epoch = ""
        self._seqs: list[int] = []
        self._records: list[dict[str, Any]] = []
        self._weights: list[int] = []
        self._weight = 0
        self._standing: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, int] = {}
        self._version = 0
        self._figures: dict[str, Any] | None = None
        self._figured = 0
        self._following = Following()
        self._me = ""
        self._gone = ""
        #: The asides pages opened, by the name the page gave each.
        self._asides: dict[str, _Aside] = {}
        self._link = self._attached(linking())
        threading.Thread(target=self._figuring, daemon=True, name="hmz-web").start()

    @property
    def me(self) -> str:
        """What the runs call this interface, as they said when it attached."""
        return self._me

    @property
    def gone(self) -> str:
        """Why the runs let this interface go, or "" while it is attached to them."""
        return self._gone

    def standing(self, kind: str) -> dict[str, Any] | None:
        """How one thing stands, as the runs last said it.

        Args:
          kind: Which, out of `STANDING`.

        Returns:
          What they said, or None where they have said nothing of it.
        """
        with self._changed:
            return self._standing.get(kind)

    def records(self, run: int = 0) -> list[dict[str, Any]]:
        """The records kept, in the order they were told.

        Args:
          run: Only those of this run, or 0 for every run's.

        Returns:
          Them.
        """
        with self._changed:
            return [one for one in self._records if not run or one.get("run") == run]

    def asks(self, do: str, said: dict[str, Any]) -> dict[str, Any]:
        """Asks the runs one thing a page asked for, as the page sent it.

        Args:
          do: What, out of what a page may ask.
          said: What the page sent with it.

        Returns:
          What the runs answered.

        Raises:
          Refusal: If the page may not ask that, sent what it does not take, or the runs
            refused it -- with what the runs said.
        """
        takes = _ACTS.get(do)
        if takes is None:
            raise Refusal(f"There is no {do} to ask of an epic.", 404)
        if extra := sorted(set(said) - set(takes)):
            raise Refusal(f"{do} takes no {', '.join(extra)}.")
        asked: dict[str, Any] = {"do": do}
        for name, (kinds, otherwise) in takes.items():
            value = said.get(name, otherwise)
            if value is ... or not isinstance(value, kinds):
                raise Refusal(f"{do} takes {name} as {_named(kinds)}.")
            asked[name] = value
        from hmz.daemon import Refused

        try:
            return self._link.asked(asked)
        except Refused as why:
            raise Refusal(str(why), 409) from why
        except (OSError, TimeoutError) as why:
            raise Refusal(f"The epics could not be asked: {why}", 503) from why

    def btw(
        self,
        question: str,
        aside: str,
        to: str = "",
        *,
        epic: str = "",
        workspace: str,
        source: Callable[[Mapping[str, Any] | None, list[str]], dict[str, str] | None],
        about: FlowSnapshot | None = None,
        opening: Callable[[str], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Asks one side question about the run, beside it rather than of it.

        The first question to an aside opens a side conversation on whom it asks, which every
        question to it after goes on in, as the terminal interface's `/btw` does, until
        :meth:`unbtw`. Whom an aside asks is never changed: another is another aside.

        Args:
          question: What was asked.
          aside: The aside it is asked in, by the name the page gave it.
          to: Whom an aside this question opens asks: `<agent>/<n>`, or "" for the btw agent.
          epic: The epic that aside is about, by name, or "" for the run going.
          workspace: Where the runs are, as the question is told it.
          source: What the btw agent is opened as, given the run as the runs last said it
            and its conversations.
          about: An epic the runs hold no more, frozen, told in place of the run going: its
            sessions are those the btw agent may ask.
          opening: What opens a side conversation of one of that epic's sessions, by
            `<agent>/<n>`, as a link's `aside` takes it: carried on from where it was kept.

        Returns:
          The aside, whom it asks, the question, the answer, and each conversation the btw
          agent asked on the way to it.

        Raises:
          Refusal: If the last question asked of it is still being answered, nothing
            answered, or the runs would not open a side conversation.
        """
        from hmz.daemon import Refused
        from hmz.runtime.watching.btw import Btw, Left

        with self._changed:
            one = self._asides.get(aside)
            if one is None:
                one = _Aside(to, epic, about)
                one.mode = Btw(
                    to,
                    aside=self._aside
                    if opening is None
                    else _recalling(opening, self._aside),
                    unaside=self._unaside,
                    sessions=lambda: (
                        list(self._following.seen)
                        if about is None
                        else [key for key, _ in about.sessions]
                    ),
                    source=lambda: source(
                        self.standing("run"), list(self._following.seen)
                    ),
                    asking=lambda key, asking: one.asked.append(
                        {"to": key, "question": asking}
                    ),
                )
                self._asides[aside] = one
            if one.question:
                raise Refusal(
                    "btw is still answering the last question asked of it.", 409
                )
            snapshot = one.about or self._snapshot(workspace)
            # Taken before the lock is let go, so that a second question finds it busy.
            one.question, one.asked = question, []
        try:
            answer = one.mode.ask(question, snapshot)
        except Left as why:
            raise Refusal(
                "A new epic started, which closed what was asked.", 409
            ) from why
        except Refused as why:
            raise Refusal(str(why), 409) from why
        except (OSError, TimeoutError) as why:
            raise Refusal(f"The epics could not be asked: {why}", 503) from why
        finally:
            with self._changed:
                one.question = ""
        if not answer:
            raise Refusal("The agent returned no answer.", 502)
        said = {
            "aside": aside,
            "to": one.to,
            "question": question,
            "answer": answer,
            "asked": list(one.asked),
        }
        with self._changed:
            one.said = [*one.said, said][-_SAID:]
        return said

    def sessions(self) -> list[str]:
        """The conversations of the run in front of this interface, `<agent>/<n>` apiece."""
        with self._changed:
            return list(self._following.seen)

    def asides(self, epic: str = "") -> list[dict[str, Any]]:
        """The asides open about one epic, in the order they were opened, as they stand.

        Args:
          epic: The epic, by the name they were opened with, "" for the run going.

        Returns:
          Each one's name, whom it asks, the question it is answering ("" for none) and whom
          the btw agent has asked on the way to it so far, and what was said in it.
        """
        with self._changed:
            return [
                {
                    "aside": name,
                    "to": one.to,
                    "question": one.question,
                    "asked": list(one.asked),
                    "said": list(one.said),
                }
                for name, one in self._asides.items()
                if one.epic == epic
            ]

    def holds(self, aside: str) -> bool:
        """Whether an aside is open, by the name the page gave it."""
        with self._changed:
            return aside in self._asides

    def unbtw(self, aside: str | None = None) -> None:
        """Closes asides, and the side conversations they opened.

        Args:
          aside: The one aside, by its name, or None for every one.
        """
        if aside is None:
            self._leaves()
            return
        with self._changed:
            one = self._asides.pop(aside, None)
        if one is not None:
            one.mode.close()

    def _leaves(self, *, unasking: bool = True, going: bool = False) -> None:
        """Leaves btw mode altogether, closing every side conversation and what was said in it.

        Args:
          unasking: Whether to ask the runs to close them, which nothing need do of the side
            conversations of a link that has gone: they went with it.
          going: Whether to close only those about the run going, and none about an epic the
            runs hold no more.
        """
        with self._changed:
            left = [
                one for one in self._asides.values() if not going or one.about is None
            ]
            self._asides = {
                name: one for name, one in self._asides.items() if one not in left
            }
        for one in left:
            one.mode.close(unasking=unasking)

    def figures(self) -> dict[str, Any] | None:
        """What the run in front of this interface has done and cost, as last worked out."""
        with self._changed:
            return self._figures

    def stream(self) -> Stream:
        """The records and the standing of the runs, for a page to follow as they come.

        Returns:
          A stream that starts with how everything stands and every record the page has not
          heard, then carries on with each as it comes. A page that heard another link's
          records -- the runs let this go, and it attached again -- is told to start over.
        """
        return Stream(self._events)

    def close(self) -> None:
        """Lets go of the runs, which carry on without this interface."""
        with self._changed:
            self._closed = True
            self._changed.notify_all()
            following = self._following
        # Nothing to ask on the way out: every side conversation this opened goes with it.
        self._leaves(unasking=False)
        following.close()
        self._link.close()

    def _attached(self, link: Link) -> Link:
        """Starts following the runs over a new link, from nothing, and returns the link."""
        from hmz.runtime.watching.following import Following

        with self._changed:
            self._epoch = secrets.token_hex(4)
            self._seqs, self._records = [], []
            self._weights, self._weight = [], 0
            self._standing, self._versions = {}, {}
            followed, self._following = self._following, Following()
            self._figures = None
            self._me = self._gone = ""
            self._version += 1
            self._changed.notify_all()
        # What the last link was following is followed no more, and the side conversations
        # went with the link they were opened on.
        followed.close()
        self._leaves(unasking=False)
        link.heard(self._told)
        return link

    def _aside(self, **said: Any) -> dict[str, Any]:
        """Asks the runs about a side conversation, down whichever link is held now."""
        return self._link.aside(**said)

    def _unaside(self, side: str) -> None:
        """Closes one side conversation, quietly: one already gone is closed."""
        from hmz.daemon import Refused

        with contextlib.suppress(Refused, OSError, TimeoutError):
            self._link.asked({"do": "unaside", "side": side})

    def _snapshot(self, workspace: str) -> FlowSnapshot:
        """The run as a side question is told it, out of what the runs last said of it."""
        standing = self._standing
        run: dict[str, Any] = standing.get("run") or {}
        calls: list[dict[str, Any]] = (standing.get("calls") or {}).get("calls") or []
        waiting: dict[str, Any] = standing.get("waiting") or {}
        pending: list[dict[str, Any]] = (standing.get("pending") or {}).get(
            "pending"
        ) or []
        return self._following.snapshot(
            flow=" ▸ ".join(str(one.get("name")) for one in calls)
            or str(run.get("flow") or ""),
            task=str(run.get("task") or ""),
            workspace=workspace,
            going=run.get("state") not in (None, "idle"),
            working=list((standing.get("sessions") or {}).get("working") or []),
            waiting=len(waiting.get("queued") or []) + len(waiting.get("given") or []),
            waiting_for_input=any(one.get("mode") == "listen" for one in pending),
        )

    def _told(self, message: dict[str, Any]) -> None:
        """Takes one message the runs sent, on the link's own thread."""
        kind = str(message.get("type") or "")
        with self._changed:
            if "seq" in message:
                weight = len(str(message.get("text") or "")) + _FRAME
                self._seqs.append(int(message["seq"]))
                self._records.append(message)
                self._weights.append(weight)
                self._weight += weight
                self._trims()
            elif kind in STANDING:
                self._version += 1
                self._standing[kind], self._versions[kind] = message, self._version
            elif kind == "welcome":
                self._me = str(message.get("client") or "")
            elif kind == "gone":
                self._gone = str(
                    message.get("why") or "the epics let this interface go"
                )
            self._changed.notify_all()
        # Kept first and followed after: what is worked out of a record is the page's figures,
        # and a record that cannot be worked out is still a record a page reads.
        self._follows(kind, message)
        if kind == "gone" and self._reaches:
            threading.Thread(target=self._again, daemon=True, name="hmz-web").start()

    def _trims(self) -> None:
        """Lets the oldest records go, past as many or as much as are kept. Under the lock."""
        dropped = 0
        while len(self._records) - dropped > _KEPT or (
            self._weight > _WEIGHED and len(self._records) - dropped > 1
        ):
            self._weight -= self._weights[dropped]
            dropped += 1
        if dropped:
            del self._seqs[:dropped], self._records[:dropped], self._weights[:dropped]

    def _follows(self, kind: str, message: dict[str, Any]) -> None:
        """Works out what one message means for the run's figures."""
        following = self._following
        if kind == "started":
            following.started(message)
            # A side conversation is about the run it was opened on, and that run has gone:
            # closed on a thread of its own, since closing one asks the runs.
            threading.Thread(
                target=self._leaves,
                kwargs={"going": True},
                daemon=True,
                name="hmz-web",
            ).start()
        elif kind == "printed":
            following.printed(str(message.get("text") or ""))
        elif kind == "opened":
            following.opened(message)
        elif kind == "event":
            following.heard(message)
        elif kind == "ended":
            following.ended(message)
        elif (
            kind == "run"
            and message.get("state") == "running"
            and int(message.get("run") or 0) > following.run
        ):
            # A run whose start was not kept for this interface to read back, which is one
            # older than the most that is kept: it starts here instead.
            following.started(message)

    def _again(self) -> None:
        """Reaches the runs again once they have let this go, until it is closed."""
        while True:
            with self._changed:
                if self._closed:
                    return
            time.sleep(_AGAIN)
            try:
                link = self._linking()
            except Exception:  # noqa: BLE001, S112 -- not there yet; tried again in a moment
                continue
            with self._changed:
                closed = self._closed
            if closed:
                link.close()
                return
            self._link = self._attached(link)
            return

    def _figuring(self) -> None:
        """Works out what the run has done, for as long as this interface is open."""
        failed = ""
        while True:
            with self._changed:
                if self._closed:
                    return
                following = self._following
            try:
                figures = _figures(following) if following.run else None
            except Exception as why:  # noqa: BLE001 -- drawn as last worked out, and said once
                if str(why) != failed:
                    failed = str(why)
                    traceback.print_exc(file=sys.stderr)
                time.sleep(_FIGURING)
                continue
            failed = ""
            with self._changed:
                if figures != self._figures and following is self._following:
                    self._figures, self._figured = figures, self._figured + 1
                    self._changed.notify_all()
            time.sleep(_FIGURING)

    def _events(
        self, last: str, going: threading.Event
    ) -> Iterator[tuple[str, str, Any] | None]:
        """Everything a page has not heard, then everything as it comes."""
        with self._changed:
            # Who this interface is, the runs say first of all; a page told nobody would read
            # every question this interface holds as another's.
            self._changed.wait_for(lambda: bool(self._me) or self._closed, _WELCOMED)
            epoch = self._epoch
            heard, _, seq = last.partition(":")
            after = int(seq) if heard == epoch and seq.isdigit() else 0
            me = self._me
        yield "", "hello", {"epoch": epoch, "me": me}
        told: dict[str, int] = {}
        figured = -1
        while not going.is_set():
            with self._changed:
                if self._epoch != epoch:
                    break
                fresh, standing, figures, gone = self._since(after, told, figured)
                if not (fresh or standing or figures is not None or gone):
                    self._changed.wait(_QUIET)
                    if self._closed:
                        break
                    fresh, standing, figures, gone = self._since(after, told, figured)
                figured = self._figured
            if not (fresh or standing or figures is not None or gone):
                yield None
                continue
            for record in fresh:
                after = int(record["seq"])
                yield f"{epoch}:{after}", "record", record
            for one in standing:
                yield "", "standing", one
            if figures is not None:
                yield "", "figures", figures
            if gone:
                yield "", "gone", {"why": gone}
                return
        # The runs let this go and it attached again, or the interface is closing: a page
        # told so starts over, from how the new link says everything stands.
        yield "", "again", {}

    def _since(
        self, after: int, told: dict[str, int], figured: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, str]:
        """What a page has not heard, under the lock: records, standing, figures, and gone."""
        fresh = self._records[bisect.bisect_right(self._seqs, after) :]
        standing: list[dict[str, Any]] = []
        for kind, version in self._versions.items():
            if told.get(kind) != version:
                told[kind] = version
                standing.append(self._standing[kind])
        figures = self._figures if self._figured != figured else None
        return fresh, standing, figures, self._gone


class _Aside:
    """One aside a page opened: whom it asks, about which epic, and what was said in it.

    Attributes:
      to: Whom it asks: `<agent>/<n>`, or "" for the btw agent.
      epic: The epic it is about, by name, or "" for the run going.
      about: That epic, frozen, where the runs hold it no more; None for the run going.
      mode: The side conversations it opened.
      question: The question it is answering, or "" for none.
      asked: Each conversation the btw agent has asked on the way to that answer so far.
      said: Each question answered in it, the latest `_SAID`.
    """

    def __init__(self, to: str, epic: str, about: FlowSnapshot | None) -> None:
        self.to, self.epic, self.about = to, epic, about
        self.mode: Btw
        self.question = ""
        self.asked: list[dict[str, str]] = []
        self.said: list[dict[str, Any]] = []


def _named(kinds: tuple[type, ...]) -> str:
    """What a field may be, as a page is told it."""
    names = {
        str: "text",
        bool: "true or false",
        dict: "an object",
        NoneType: "null",
    }
    return " or ".join(names.get(one, one.__name__) for one in kinds)


def _figures(following: Any) -> dict[str, Any]:
    """What a run has done and cost, as a page draws it: the figures every frontend draws."""
    from hmz.coganchor.prices import money
    from hmz.runtime.watching.monitor import lasting, tallied, thousands

    monitor = following.monitor
    moment = time.monotonic()
    ended = monitor.until
    elapsed = max(0.0, (ended if ended is not None else moment) - monitor.began)
    agents = monitor.shape()
    sessions = monitor.shape(sessions=True)
    spending = monitor.spending()
    lines = tallied(monitor)

    def node(name: str, shape: Any) -> dict[str, Any]:
        return {
            "name": name,
            "turns": shape.turns.get(name, 0),
            "working": name in shape.working,
            "since": round(shape.since.get(name, 0.0), 1),
            "lasting": lasting(shape.since.get(name, 0.0)),
            "used": shape.used.get(name, 0),
            "tokens": thousands(shape.used.get(name, 0)),
            "under": [
                {"whose": one.whose, "about": one.about, "working": one.working}
                for one in shape.under.get(name, ())
            ],
        }

    return {
        "run": following.run,
        "elapsed": round(elapsed, 1),
        "lasting": lasting(elapsed),
        "ended": ended is not None,
        "agents": [node(name, agents) for name in agents.turns],
        "sessions": [node(key, sessions) for key in sessions.turns],
        "handovers": [
            {"from": sender, "to": receiver, "count": count}
            for (sender, receiver), count in agents.handovers.items()
        ],
        "latest": list(agents.latest) if agents.latest else None,
        "spending": [
            {
                "model": spend.model,
                "tokens": spend.tokens,
                "rate": round(spend.rate, 1),
                "dollars": spend.dollars,
                "money": money(spend.dollars) if spend.dollars is not None else "",
                "kinds": dict(spend.kinds),
            }
            for spend in spending
        ],
        "reckoning": [
            {"kind": one.kind, "tokens": one.tokens, "whole": one.whole}
            for one in monitor.reckoning()
        ],
        "tally": list(lines) if lines else [],
    }


def _held(asked: Asked) -> dict[str, Any]:
    import socket

    from hmz.coganchor import __version__, releases

    places = asked.site.places
    return {
        "machine": socket.gethostname().split(".")[0],
        # The WSL distribution hmz runs in, as Windows names it; None outside WSL.
        "wsl": os.environ.get("WSL_DISTRO_NAME") or None,
        "here": str(places.here),
        "version": __version__,
        "newer": releases.newer() or "",
        "running": places.running(),
    }


def _workspace(asked: Asked) -> str:
    """The workspace a request is about: its `workspace`, as a query or in what it sent."""
    said = (
        asked.body["workspace"]
        if "workspace" in asked.body
        else asked.query.get("workspace", "")
    )
    if not isinstance(said, str):
        raise Refusal("Say the workspace as a path.")
    return said


def _slot(asked: Asked) -> str:
    """Which of the workspace's hosts a request is about: its `slot`, "" for the workspace's own."""
    from hmz.daemon import where

    said = asked.body["slot"] if "slot" in asked.body else asked.query.get("slot", "")
    try:
        return where.slot(said)
    except ValueError as why:
        raise Refusal(f"{why}.") from why


def _chats(flow: object) -> bool:
    """Whether a flow named to start is the built-in chat, however it was named."""
    return isinstance(flow, str) and re.split(r"[/#:]", flow.rstrip("/#"))[-1] == "chat"


def _streams(asked: Asked) -> Stream:
    return asked.site.places.stream(_workspace(asked), _slot(asked))


def _acts(asked: Asked) -> dict[str, Any]:
    said = {
        name: value
        for name, value in asked.body.items()
        if name not in ("workspace", "slot")
    }
    workspace = _workspace(asked)
    slot = _slot(asked)
    if asked.matched["do"] != "start":
        return asked.site.places.held(workspace, slot).asks(asked.matched["do"], said)
    scratch = said.pop("scratch", False)
    if not isinstance(scratch, bool):
        raise Refusal("start takes scratch as bool.")
    if scratch:
        # Started in no workspace: in a directory of its own, made for it alone.
        workspace = tempfile.mkdtemp(prefix="hmz-")
    from hmz.daemon import where

    from .flows import remembered

    # Started as it is set up is set up so from then on, as `/flow` saves it -- and
    # somewhere an epic was started is somewhere to offer the next.
    place = asked.site.places.of(workspace)
    remembered(place.hmz, said)
    if "slot" not in asked.body and _chats(said.get("flow")):
        # A chat started without saying where is a new chat's, on a host of its own: it takes
        # no flow's turn, and starting one ends no other.
        slot = where.chat()
    held = asked.site.places.held(workspace, slot, starts=True)
    return held.asks("start", said) | {"slot": slot, "workspace": str(place.workspace)}


def _btw(asked: Asked) -> dict[str, Any]:
    places = asked.site.places
    workspace = _workspace(asked)
    place = places.of(workspace)
    question = " ".join(asked.text("question").split())
    if not question:
        raise Refusal("Say question, as text.")
    aside = asked.text("aside")
    to, epic = asked.text("to", required=False), asked.text("epic", required=False)
    # Asked through the workspace's own host, of an epic's session as it was kept: a chat's,
    # held by a host of its own or folded away, included.
    held = places.held(workspace)
    about = opening = None
    # Whom an aside open already asks, and about which epic, is what it opened on.
    opens = not held.holds(aside)
    if opens and not to and not _answers():
        from hmz.runtime.watching.btw import NOBODY

        raise Refusal(NOBODY, 409)
    if opens and epic and not _held_still(held, epic, to):
        # An epic the runs hold no more, or a session of one: told that epic rather than the
        # run going, and each of its sessions carried on from where that epic kept it.
        about, opening = _recalled(asked.site.runs.named(epic))
        if to:
            opening(to)
    return held.btw(
        question,
        aside,
        to,
        epic=epic,
        workspace=str(place.workspace),
        source=_source,
        about=about,
        opening=opening,
    )


def _held_still(held: Held, epic: str, to: str) -> bool:
    """Whether an epic, or a session of it, is one the runs still hold: theirs, and known."""
    run = held.standing("run") or {}
    return run.get("epic") == epic and (not to or to in held.sessions())


def _recalled(ran: Any) -> tuple[FlowSnapshot, Callable[[str], dict[str, Any]]]:
    """An epic written down, as side questions about it and its sessions are asked.

    Args:
      ran: The epic.

    Returns:
      The epic, frozen, as a side question is told it, its sessions by `<agent>/<n>`; and
      what opens a side conversation of one of them, by `<agent>/<n>` -- the n-th its agent
      opened -- as a link's `aside` takes it: its agent, its conversation and where it was
      kept. That raises a Refusal for a session the epic did not open, or whose agent it did
      not write down.
    """
    from hmz.runtime.epic import where
    from hmz.runtime.watching.btw import AgentProgress, FlowSnapshot

    # One written before an agent had a name of its own went by its role.
    drove = {one.name or one.agent: one for one in ran.agents}
    sessions: dict[str, Any] = {}
    opened: dict[str, int] = {}
    for session in ran.sessions:
        opened[session.agent] = opened.get(session.agent, 0) + 1
        sessions[f"{session.agent}/{opened[session.agent]}"] = session

    def opening(key: str) -> dict[str, Any]:
        session = sessions.get(key)
        if session is None:
            raise Refusal(f"{ran.name} opened no session {key}.", 404)
        runs = drove[session.agent].spec if session.agent in drove else ""
        if not runs:
            raise Refusal(
                f"{ran.name} says nothing of what {session.agent} ran as.", 404
            )
        return {
            "runs": runs,
            "recall": session.ident,
            "kept": str(where(ran.at, session)),
            "cwd": ran.workspace,
        }

    began, ended = _moment(ran.began), _moment(ran.ended)
    about = FlowSnapshot(
        flow=ran.flow,
        task=ran.task,
        workspace=ran.workspace,
        elapsed=max(0.0, ended - began) if began and ended else 0.0,
        finished=True,
        agents=tuple(
            AgentProgress(
                agent=one.name or one.agent,
                model=one.model,
                turns=0,
                working=False,
                role=one.agent,
            )
            for one in ran.agents
        ),
        sessions=tuple(
            (
                key,
                f"ended, model={drove[one.agent].model if one.agent in drove else ''}",
            )
            for key, one in sessions.items()
        ),
    )
    return about, opening


def _recalling(
    opening: Callable[[str], dict[str, Any]], aside: Callable[..., Mapping[str, Any]]
) -> Callable[..., Mapping[str, Any]]:
    """What asks the runs about a side conversation of an epic written down.

    Args:
      opening: What opens a side conversation of one of its sessions, by `<agent>/<n>`.
      aside: What asks the runs about a side conversation of the run going.

    Returns:
      `aside`, but for a session asked by its key, which is carried on from where that epic
      kept it: forked, or a copy of its agent opened afresh.
    """

    def asks(**said: Any) -> Mapping[str, Any]:
        key = said.pop("key", None)
        if key is not None:
            how = opening(key)
            said = (
                {**how, **said} if said.get("fork") else {"runs": how["runs"], **said}
            )
        return aside(**said)

    return asks


def _moment(stamp: str) -> float:
    """A moment an epic wrote down, in seconds since the epoch, or 0 for none."""
    import datetime

    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0


def _answers() -> str:
    """The agent the settings name to answer The Epic, as they say it now, or "" for nobody.

    Read afresh rather than from what this server read once: a change made on any page, or in
    the terminal, is who the next side conversation of The Epic opens as.
    """
    from hmz.coganchor import settings

    said = settings.read().get("btw")
    return said if isinstance(said, str) else ""


def _source(
    run: Mapping[str, Any] | None, sessions: list[str]
) -> dict[str, str] | None:
    """What The Epic is opened as, as the terminal interface opens it: what the settings name."""
    from hmz.runtime.kept import read_back, written
    from hmz.runtime.watching.btw import opened_as

    del run, sessions  # no agent of the epic stands in for the one the settings name
    said = read_back(answers) if (answers := _answers()) else None
    return opened_as(written(said) if said is not None else "")


def _asides(asked: Asked) -> dict[str, Any]:
    workspace = _workspace(asked)
    # Read of the runs this follows, never reaching runs it does not: nothing was asked there.
    held = asked.site.places.attached(workspace)
    epic = asked.query.get("epic", "")
    # Who answers The Epic: what the settings name, "" for nobody.
    return {
        "asides": held.asides(epic) if held is not None else [],
        "default": _answers(),
    }


def _unbtw(asked: Asked) -> dict[str, Any]:
    aside = asked.body.get("aside")
    if aside is not None and not isinstance(aside, str):
        raise Refusal("Say aside as the aside to close, or nothing for every one.")
    held = asked.site.places.attached(_workspace(asked))
    if held is not None:
        held.unbtw(aside)
    return {"ok": True}


#: What a page reads of the runs, follows of them, and asks of them.
ROUTES = routes(
    ("GET", "/api/held", _held),
    ("GET", "/api/held/stream", _streams),
    ("POST", "/api/held/{do}", _acts),
    ("GET", "/api/btw", _asides),
    ("POST", "/api/btw", _btw),
    ("POST", "/api/btw/leave", _unbtw),
)
