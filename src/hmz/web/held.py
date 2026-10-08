"""The runs held for this workspace, as the web interface follows them and acts on them.

One link to the host of the workspace's runs, as every frontend holds one: what it tells is
kept here -- the records of the runs it has told of, in order, how each thing stands now, and
the figures worked out of them -- and handed to every page that listens, from wherever that
page last heard. What a page asks of the runs goes back down the same link, and what the runs
refuse is refused with the reason they give. A side question about the run is asked down it
too, of a side conversation the runs open beside the run rather than of the run itself.
"""

from __future__ import annotations

import bisect
import contextlib
import functools
import secrets
import threading
import time
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
        "profile": ((bool,), False),
        "resume": ((bool, str), False),
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
    """

    def __init__(self, linking: Callable[[], Link]) -> None:
        from hmz.runtime.watching.following import Following

        self._linking = linking
        self._changed = threading.Condition()
        self._closed = False
        # Everything below is one link's, and is made again with the next.
        self._epoch = ""
        self._seqs: list[int] = []
        self._records: list[dict[str, Any]] = []
        self._standing: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, int] = {}
        self._version = 0
        self._figures: dict[str, Any] | None = None
        self._figured = 0
        self._following = Following()
        self._me = ""
        self._gone = ""
        #: Btw mode, by the conversation it asks -- "" for the btw agent -- and what the btw
        #: agent asked on the way to its last answer.
        self._asides: dict[str, Btw] = {}
        self._hops: dict[str, list[dict[str, str]]] = {}
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
            raise Refusal(f"There is no {do} to ask of a run.", 404)
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
            raise Refusal(f"The runs could not be asked: {why}", 503) from why

    def btw(
        self,
        question: str,
        target: str,
        *,
        workspace: str,
        source: Callable[[Mapping[str, Any] | None, list[str]], dict[str, str] | None],
    ) -> dict[str, Any]:
        """Asks one side question about the run, beside it rather than of it.

        The first question to a conversation opens a side one on it, which every question
        after goes on in, as the terminal interface's `/btw` does, until :meth:`unbtw`.

        Args:
          question: What was asked.
          target: The conversation asked, `<role>/<n>`, or "" for the btw agent.
          workspace: Where the runs are, as the question is told it.
          source: What the btw agent is opened as, given the run as the runs last said it
            and its conversations.

        Returns:
          The answer, and each conversation the btw agent asked on the way to it.

        Raises:
          Refusal: If the last question asked of it is still being answered, nothing
            answered, or the runs would not open a side conversation.
        """
        from hmz.daemon import Refused
        from hmz.runtime.watching.btw import Btw, Left

        with self._changed:
            mode = self._asides.get(target)
            if mode is None:
                told: list[dict[str, str]] = []
                mode = Btw(
                    target,
                    aside=self._aside,
                    unaside=self._unaside,
                    sessions=lambda: list(self._following.seen),
                    source=lambda: source(
                        self.standing("run"), list(self._following.seen)
                    ),
                    asking=lambda key, asking: told.append(
                        {"to": key, "question": asking}
                    ),
                )
                self._asides[target], self._hops[target] = mode, told
            if mode.busy:
                raise Refusal(
                    "btw is still answering the last question asked of it.", 409
                )
            mode.busy = True
            hops = self._hops[target]
            hops.clear()
            snapshot = self._snapshot(workspace)
        try:
            answer = mode.ask(question, snapshot)
        except Left as why:
            raise Refusal(
                "A new run started, which closed what was asked.", 409
            ) from why
        except Refused as why:
            raise Refusal(str(why), 409) from why
        except (OSError, TimeoutError) as why:
            raise Refusal(f"The runs could not be asked: {why}", 503) from why
        if not answer:
            raise Refusal("The agent returned no answer.", 502)
        return {"answer": answer, "asked": list(hops)}

    def unbtw(self, target: str | None = None) -> None:
        """Leaves btw mode, closing the side conversations it opened.

        Args:
          target: The one conversation asked, or None for every one.
        """
        with self._changed:
            if target is None:
                left, self._asides = list(self._asides.values()), {}
            else:
                left = [one] if (one := self._asides.pop(target, None)) else []
        for one in left:
            one.close()

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
            left, self._asides = list(self._asides.values()), {}
        # Nothing to ask on the way out: every side conversation this opened goes with it.
        for one in left:
            one.close(unasking=False)
        self._link.close()

    def _attached(self, link: Link) -> Link:
        """Starts following the runs over a new link, from nothing, and returns the link."""
        from hmz.runtime.watching.following import Following

        with self._changed:
            self._epoch = secrets.token_hex(4)
            self._seqs, self._records = [], []
            self._standing, self._versions = {}, {}
            self._figures, self._following = None, Following()
            self._me = self._gone = ""
            self._version += 1
            left, self._asides = list(self._asides.values()), {}
            self._changed.notify_all()
        # The side conversations went with the link they were opened on.
        for one in left:
            one.close(unasking=False)
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
                self._seqs.append(int(message["seq"]))
                self._records.append(message)
                if len(self._records) > _KEPT:
                    del self._seqs[:-_KEPT], self._records[:-_KEPT]
            elif kind in STANDING:
                self._version += 1
                self._standing[kind], self._versions[kind] = message, self._version
            elif kind == "welcome":
                self._me = str(message.get("client") or "")
            elif kind == "gone":
                self._gone = str(message.get("why") or "the runs let this interface go")
            self._changed.notify_all()
        # Kept first and followed after: what is worked out of a record is the page's figures,
        # and a record that cannot be worked out is still a record a page reads.
        self._follows(kind, message)
        if kind == "gone":
            threading.Thread(target=self._again, daemon=True, name="hmz-web").start()

    def _follows(self, kind: str, message: dict[str, Any]) -> None:
        """Works out what one message means for the run's figures."""
        following = self._following
        if kind == "started":
            following.started(message)
            # A side conversation is about the run it was opened on, and that run has gone:
            # closed on a thread of its own, since closing one asks the runs.
            with self._changed:
                left, self._asides = list(self._asides.values()), {}
            for one in left:
                threading.Thread(target=one.close, daemon=True, name="hmz-web").start()
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
        while True:
            with self._changed:
                if self._closed:
                    return
                following = self._following
            figures = _figures(following) if following.run else None
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
    from hmz.coganchor import __version__

    held = asked.site.held
    return {
        "workspace": str(asked.site.hmz.workspace),
        "version": __version__,
        "me": held.me,
        "gone": held.gone,
        "run": held.standing("run"),
    }


def _streams(asked: Asked) -> Stream:
    return asked.site.held.stream()


def _acts(asked: Asked) -> dict[str, Any]:
    return asked.site.held.asks(asked.matched["do"], asked.body)


#: What a page reads of the runs held here and asks of them.
def _btw(asked: Asked) -> dict[str, Any]:
    site = asked.site
    question = " ".join(asked.text("question").split())
    return site.held.btw(
        question,
        asked.text("to", required=False),
        workspace=str(site.hmz.workspace),
        source=functools.partial(_source, site.hmz),
    )


def _source(
    hmz: Any, run: Mapping[str, Any] | None, sessions: list[str]
) -> dict[str, str] | None:
    """What the btw agent is opened as, as the terminal interface opens it.

    The agent `/settings` names; or the run's first role, as its conversation or as the
    agent it was started with; or, with no run to read, as this workspace's default flow was
    last set up.
    """
    from hmz.runtime.kept import read_back, written
    from hmz.runtime.watching.btw import opened_as

    settings = hmz.settings
    said = read_back(settings.btw) if settings.btw else None
    if run and run.get("roles"):
        agents: Mapping[str, Any] = run.get("agents") or {}
        roles = {str(role): str(agents.get(role) or "") for role in run["roles"]}
    elif settings.flow:
        roles = {
            role: written(runs) for role, runs in settings.agents(settings.flow).items()
        }
    else:
        roles = {}
    return opened_as(written(said) if said is not None else "", roles, sessions)


def _unbtw(asked: Asked) -> dict[str, Any]:
    target = asked.body.get("to")
    if target is not None and not isinstance(target, str):
        raise Refusal("Say to as the conversation asked, or nothing for every one.")
    asked.site.held.unbtw(target)
    return {"ok": True}


#: What a page reads of the runs, follows of them, and asks of them.
ROUTES = routes(
    ("GET", "/api/held", _held),
    ("GET", "/api/held/stream", _streams),
    ("POST", "/api/held/{do}", _acts),
    ("POST", "/api/btw", _btw),
    ("POST", "/api/btw/leave", _unbtw),
)
