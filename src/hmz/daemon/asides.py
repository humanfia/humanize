"""Side questions about one session of an epic, `btw.*` (Section 4.15 of daemon.md).

A side question is asked beside an epic rather than of it, in a session side copy the host of
that epic opens (`epic.aside`): the workspace's own host for the epic in view on it, the host
of a chat's slot for that chat, and the workspace's own host again for an epic or a chat no
host holds, carried on from where it kept the session. The daemon opens them as a frontend of its
own, of kind `btw`, attached to a host only while a `btw.*` call asks something of it or it
holds a side conversation open, and lets go of it once neither has happened for a minute. Each
side conversation is kept per workspace and per `aside`, the name a client gives it, the same
for every session: :class:`hmz.runtime.watching.btw.Btw` is what asks, here as in the
terminal interface.
"""

from __future__ import annotations

import contextlib
import datetime
import queue
import re
import threading
import time
from typing import TYPE_CHECKING, Any

from hmz.daemon.methods import workspace

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hmz.daemon.hosts import Subscription
    from hmz.daemon.routing import Router
    from hmz.rpc import Call
    from hmz.runtime.watching.btw import Btw, FlowSnapshot
    from hmz.runtime.watching.following import Following

__all__ = ["Asides"]

#: How long the daemon stays attached to a host for side questions nobody asks.
_LINGER = 60.0

#: How long attaching waits for a host to have told the epic so far.
_PATIENCE = 10.0

#: How many side questions and their answers each aside keeps.
_SAID = 200

#: A session, as a side question is asked of one.
_SESSION = re.compile(r"[^/\s]+/[1-9][0-9]*")


def _refused(code: int, message: str) -> Exception:
    from hmz.rpc import RpcError

    return RpcError(code, message)


class _Aside:
    """One aside: whom it asks, about which epic, on which host, and what was said in it."""

    def __init__(
        self, to: str, epic: str, about: FlowSnapshot | None, host: _Host, mode: Btw
    ) -> None:
        self.to, self.epic, self.about, self.host, self.mode = (
            to,
            epic,
            about,
            host,
            mode,
        )
        self.question = ""
        self.said: list[dict[str, Any]] = []


class _Frontend:
    """What the daemon's own frontend of one host is, as a subscription sees a session.

    What it is told is only queued here, under the subscription's lock, and taken on a thread
    of its own: nothing that takes it ever waits on that lock while holding another.
    """

    def __init__(self, heard: Callable[[dict[str, Any]], None]) -> None:
        self.name = "btw"
        self.kind = "btw"
        self.lock = threading.Lock()
        self.subs: dict[str, Any] = {}
        self._heard = heard

    def tell(self, method: str, params: dict[str, Any]) -> None:
        del method
        self._heard(params["message"])


class _Host:
    """The daemon's frontend of one host of a workspace, and what that host told it."""

    def __init__(self, held: _Workspace, slot: str) -> None:
        from hmz.runtime.watching.following import Following

        self.held = held
        self.slot = slot
        self.sub: Subscription | None = None
        self.following = Following()
        self.standing: dict[str, dict[str, Any]] = {}
        #: Whether the host has told the epic so far, after which an epic starting is new.
        self.live = False
        self.used = time.monotonic()
        #: Held while the daemon's frontend is being attached, so that it is attached once.
        self._attaching = threading.Lock()

    def attached(self) -> Subscription:
        """The daemon's frontend of the host, attached where it is not, once it is told all."""
        with self._attaching:
            return self._attaches()

    def _attaches(self) -> Subscription:
        from hmz.daemon.hosts import Subscription
        from hmz.runtime.watching.following import Following

        lock = self.held.lock
        with lock:
            self.used = time.monotonic()
            sub = self.sub
        if sub is not None and not sub.gone:
            return sub
        hosted = self.held.router.hosts.opened(self.held.named, self.slot)
        heard: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        sub = Subscription(_Frontend(heard.put), "btw", hosted, figures=False)  # pyright: ignore[reportArgumentType]
        sub.client = hosted.attach(sub, replay=True, since=None)
        with lock:
            self.following.close()
            self.following, self.standing, self.live = Following(), {}, False
            following = self.following
            self.sub = sub
        threading.Thread(
            target=self._hears,
            args=(sub, heard, following),
            daemon=True,
            name="hmz-btw",
        ).start()
        sub.opened()
        with lock:
            lock.wait_for(lambda: self.live or sub.gone, timeout=_PATIENCE)
        threading.Thread(
            target=self._lingers, args=(sub,), daemon=True, name="hmz-btw"
        ).start()
        return sub

    def aside(self, **said: Any) -> Mapping[str, Any]:
        """Asks the host about a side conversation, as a link's `aside` does."""
        from hmz.runtime import Refused

        sub = self.attached()
        answer = sub.hosted.ask(sub.client, {"do": "aside", **said})
        if not answer.get("ok"):
            raise Refused(str(answer.get("why") or "refused"))
        return answer

    def unaside(self, side: str) -> None:
        """Closes one side conversation, quietly: one already gone is closed."""
        with self.held.lock:
            sub = self.sub
        if sub is not None and not sub.gone:
            with contextlib.suppress(Exception):
                sub.hosted.ask(sub.client, {"do": "unaside", "side": side})

    def _hears(
        self,
        sub: Subscription,
        heard: queue.SimpleQueue[dict[str, Any]],
        following: Following,
    ) -> None:
        """Takes what the host tells one subscription, in order, until it has gone."""
        while True:
            try:
                message = heard.get(timeout=1.0)
            except queue.Empty:
                if sub.gone:
                    # Ended without a word: what it held on the host went with it.
                    self.held.closed(self)
                    return
                continue
            self._told(message, following)
            if message.get("type") == "gone":
                return

    def _told(self, message: dict[str, Any], following: Following) -> None:
        kind = str(message.get("type") or "")
        lock = self.held.lock
        with lock:
            if following is not self.following:
                return
            if "seq" not in message and kind not in ("welcome", "live", "gone"):
                self.standing[kind] = message
            # Before `live` the host is telling the epic so far: an epic it tells of as
            # started is the one going, not a new one.
            new = kind == "started" and self.live
            if kind == "live":
                self.live = True
                lock.notify_all()
        with contextlib.suppress(Exception):
            if kind == "started":
                following.started(message)
            elif kind == "printed":
                following.printed(str(message.get("text") or ""))
            elif kind == "opened":
                following.opened(message)
            elif kind == "event":
                following.heard(message)
            elif kind == "ended":
                following.ended(message)
        if new or kind == "gone":
            # The host closed every side conversation it held: those about the epic it was
            # going have gone with it, and those about an earlier one open again when asked.
            self.held.closed(self)
        if kind == "gone":
            with lock:
                lock.notify_all()

    def snapshot(self) -> FlowSnapshot:
        """The epic going on the host, as a side question is told it."""
        with self.held.lock:
            standing = dict(self.standing)
            following = self.following
        run: dict[str, Any] = standing.get("run") or {}
        calls: list[dict[str, Any]] = (standing.get("calls") or {}).get("calls") or []
        waiting: dict[str, Any] = standing.get("waiting") or {}
        pending: list[dict[str, Any]] = (standing.get("pending") or {}).get(
            "pending"
        ) or []
        return following.snapshot(
            flow=" ▸ ".join(str(one.get("name")) for one in calls)
            or str(run.get("flow") or ""),
            task=str(run.get("task") or ""),
            workspace=self.held.named,
            going=run.get("state") not in (None, "idle"),
            waiting=len(waiting.get("queued") or []) + len(waiting.get("given") or []),
            waiting_for_input=any(one.get("mode") == "listen" for one in pending),
        )

    def _lingers(self, sub: Subscription) -> None:
        """Lets go of the host once nothing has been asked and nothing held for a minute."""
        while True:
            time.sleep(1.0)
            if sub.gone:
                return
            with self.held.lock:
                if self.sub is not sub:
                    return
                if any(one.host is self for one in self.held.asides.values()):
                    self.used = time.monotonic()
                if time.monotonic() - self.used < _LINGER:
                    continue
                self.sub = None
            sub.dropped()
            return


class _Workspace:
    """The side conversations of one workspace, and the daemon's frontends of its hosts."""

    def __init__(self, router: Router, named: str) -> None:
        self.named = named
        self.router = router
        self.lock = threading.Condition()
        self.hosts: dict[str, _Host] = {}
        self.asides: dict[str, _Aside] = {}

    def host(self, slot: str) -> _Host:
        """The daemon's frontend of one slot's host, made the first time."""
        with self.lock:
            held = self.hosts.get(slot)
            if held is None:
                held = self.hosts[slot] = _Host(self, slot)
            return held

    def holding(self, epic: str) -> _Host | None:
        """The host of the workspace whose epic or chat going, stopping or last is `epic`."""
        for hosted in self.router.hosts.listed():
            if hosted.workspace != self.named:
                continue
            status = hosted.status()
            if epic in (status.get("epic"), status.get("chat")):
                return self.host(hosted.slot)
        return None

    def opens(self, aside: str, to: str, epic: str) -> _Aside:
        """An aside asked for the first time, on the host of its epic, kept by its name.

        Raises:
          RpcError: 404 for a session there is none of.
        """
        from hmz.runtime.watching.btw import Btw

        host = self.holding(epic) if epic else self.host("")
        seen = False
        if host is not None:
            host.attached()
            with self.lock:
                seen = to in host.following.seen
            if not seen and not epic:
                raise _refused(404, f"{to} has no conversation to ask")
        if host is not None and seen:
            held = host
            about: FlowSnapshot | None = None
            mode = Btw(
                to,
                aside=held.aside,
                unaside=held.unaside,
                sessions=lambda: list(held.following.seen),
            )
        else:
            # An epic, or a session of it, that no host holds any more: carried on from where
            # that epic kept the session, on the workspace's own host.
            about, opening = _recalled(epic)
            opening(to)
            held = self.host("")
            held.attached()
            mode = Btw(
                to,
                aside=_recalling(opening, held.aside),
                unaside=held.unaside,
                sessions=lambda: (to,),
            )
        with self.lock:
            return self.asides.setdefault(aside, _Aside(to, epic, about, held, mode))

    def closed(self, host: _Host) -> None:
        """Takes the side conversations a host closed: an epic started on it, or it went."""
        with self.lock:
            going = {
                name: one
                for name, one in self.asides.items()
                if one.host is host and one.about is None
            }
            earlier = [
                one
                for one in self.asides.values()
                if one.host is host and one.about is not None
            ]
            self.asides = {k: v for k, v in self.asides.items() if k not in going}
        for one in going.values():
            one.mode.close(unasking=False)
        for one in earlier:
            one.mode.forget()

    def leave(self, aside: str | None = None) -> None:
        """Closes asides: one by name, or every one."""
        with self.lock:
            left = {
                name: one
                for name, one in self.asides.items()
                if aside is None or name == aside
            }
            self.asides = {k: v for k, v in self.asides.items() if k not in left}
        for one in left.values():
            one.mode.close()

    def drops(self, aside: str, one: _Aside) -> None:
        """Closes an aside whose first question failed, which holds the host for nothing."""
        with self.lock:
            if self.asides.get(aside) is not one or one.said:
                return
            del self.asides[aside]
        one.mode.close()


class Asides:
    """Every workspace's side conversations, as `btw.*` asks them."""

    def __init__(self, router: Router) -> None:
        self._router = router
        self._lock = threading.Lock()
        self._held: dict[str, _Workspace] = {}

    def _of(self, named: str) -> _Workspace:
        with self._lock:
            held = self._held.get(named)
            if held is None:
                held = self._held[named] = _Workspace(self._router, named)
            return held

    def listed(self, call: Call) -> dict[str, Any]:
        """`btw.list`: the asides open about one epic or one chat, attaching to nothing."""
        named = workspace(call.params["workspace"])
        epic = str(call.params.get("chat") or call.params.get("epic") or "")
        with self._lock:
            held = self._held.get(named)
        asides: list[dict[str, Any]] = []
        if held is not None:
            with held.lock:
                asides = [
                    {
                        "aside": name,
                        "to": one.to,
                        "question": one.question,
                        "said": list(one.said),
                    }
                    for name, one in held.asides.items()
                    if one.epic == epic
                ]
        return {"asides": asides}

    def leave(self, call: Call) -> dict[str, Any]:
        """`btw.leave`: closes one aside, or every one of the workspace."""
        named = workspace(call.params["workspace"])
        aside = call.params.get("aside")
        with self._lock:
            held = self._held.get(named)
        if held is not None:
            held.leave(str(aside) if aside is not None else None)
        return {}

    def ask(self, call: Call) -> dict[str, Any]:
        """`btw.ask`: one side question, in the aside it names, opened the first time."""
        from hmz.runtime import Refused
        from hmz.runtime.watching.btw import Left

        named = workspace(call.params["workspace"])
        question = " ".join(str(call.params["question"]).split())
        aside = str(call.params["aside"])
        to = str(call.params.get("to") or "")
        epic = str(call.params.get("chat") or call.params.get("epic") or "")
        held = self._of(named)
        with held.lock:
            one = held.asides.get(aside)
        if one is None:
            if not _SESSION.fullmatch(to):
                raise _refused(
                    400, "A side question is asked of a session, as <agent>/<n>."
                )
            one = held.opens(aside, to, epic)
        with held.lock:
            if one.question:
                raise _refused(
                    409, "btw is still answering the last question asked of it."
                )
            one.question = question
        answer = ""
        try:
            one.host.attached()
            answer = one.mode.ask(question, one.about or one.host.snapshot())
        except Left:
            raise _refused(
                409, "A new epic started, which closed what was asked."
            ) from None
        except Refused as why:
            raise _refused(409, str(why)) from None
        finally:
            with held.lock:
                one.question = ""
                one.host.used = time.monotonic()
            if not answer:
                held.drops(aside, one)
        if not answer:
            raise _refused(502, "The agent returned no answer.")
        said = {"aside": aside, "to": one.to, "question": question, "answer": answer}
        with held.lock:
            one.said = [*one.said, said][-_SAID:]
        return said


def _named(epic: str) -> Any:
    """An epic or a chat written down, by its name, of whichever workspace.

    Raises:
      RpcError: 404 where there is none.
    """
    from hmz.runtime.epic import chats, every, read

    if epic and "/" not in epic and not epic.startswith("."):
        for at in (*every(), *chats()):
            if at.name == epic and (ran := read(at)) is not None:
                return ran
    raise _refused(404, f"There is no epic {epic}.")


def _recalled(epic: str) -> tuple[FlowSnapshot, Callable[[str], dict[str, Any]]]:
    """An epic written down, as side questions about its sessions are asked."""
    from hmz.runtime.epic import where
    from hmz.runtime.watching.btw import AgentProgress, FlowSnapshot

    ran = _named(epic)
    drove = {one.name or one.agent: one for one in ran.agents}
    sessions: dict[str, Any] = {}
    opened: dict[str, int] = {}
    for session in ran.sessions:
        opened[session.agent] = opened.get(session.agent, 0) + 1
        sessions[f"{session.agent}/{opened[session.agent]}"] = session

    def opening(key: str) -> dict[str, Any]:
        session = sessions.get(key)
        if session is None:
            raise _refused(404, f"{ran.name} opened no session {key}.")
        runs = drove[session.agent].spec if session.agent in drove else ""
        if not runs:
            raise _refused(
                404, f"{ran.name} says nothing of what {session.agent} ran as."
            )
        return {
            "runs": runs,
            "recall": session.ident,
            "kept": str(where(ran.at, session)),
            "cwd": ran.workspace,
        }

    began, ended = _moment(ran.began), _moment(ran.ended)
    about = FlowSnapshot(
        # A chat has no flow to name, and says what it is instead (Section 9.4.2 of core).
        flow="chat" if ran.chat else ran.flow,
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
    )
    return about, opening


def _recalling(
    opening: Callable[[str], dict[str, Any]], aside: Callable[..., Mapping[str, Any]]
) -> Callable[..., Mapping[str, Any]]:
    """`aside`, but for a session asked by its key, carried on from where its epic kept it."""

    def asks(**said: Any) -> Mapping[str, Any]:
        key = said.pop("key", None)
        if key is not None:
            how = opening(key)
            said = (
                {**how, **said}
                if said.get("fork")
                else {"runs": how["runs"], "cwd": how["cwd"], **said}
            )
        return aside(**said)

    return asks


def _moment(stamp: str) -> float:
    """A moment an epic wrote down, in seconds since the epoch, or 0 for none."""
    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0
