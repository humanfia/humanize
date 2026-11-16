"""Side questions about an epic, `btw.*` (Section 4.15 of daemon.md).

A side question is asked beside an epic rather than of it, in a side conversation the
workspace's own host opens (`epic.aside`). The daemon opens them as a frontend of its own, of
kind `btw`, attached to that host only while a `btw.*` call asks something of it or it holds a
side conversation open, and lets go of it once neither has happened for a minute. Each side
conversation is kept per workspace and per `aside`, the name a client gives it, the same for
every session: :class:`hmz.runtime.watching.btw.Btw` is what asks, here as in the terminal
interface.
"""

from __future__ import annotations

import contextlib
import datetime
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

__all__ = ["Asides"]

#: How long the daemon stays attached to a host for side questions nobody asks.
_LINGER = 60.0

#: How many side questions and their answers each aside keeps.
_SAID = 200


def _refused(code: int, message: str) -> Exception:
    from hmz.rpc import RpcError

    return RpcError(code, message)


class _Aside:
    """One aside: whom it asks, about which epic, and what was said in it."""

    def __init__(self, to: str, epic: str, about: FlowSnapshot | None) -> None:
        self.to, self.epic, self.about = to, epic, about
        self.mode: Btw
        self.question = ""
        self.asked: list[dict[str, str]] = []
        self.said: list[dict[str, Any]] = []


class _Frontend:
    """What the daemon's own frontend of one host is, as a subscription sees a session."""

    def __init__(self, told: Callable[[dict[str, Any]], None]) -> None:
        self.name = "btw"
        self.kind = "btw"
        self.lock = threading.Lock()
        self.subs: dict[str, Any] = {}
        self._told = told

    def tell(self, method: str, params: dict[str, Any]) -> None:
        del method
        self._told(params["message"])


class _Workspace:
    """The side conversations of one workspace, and the daemon's frontend of its host."""

    def __init__(self, router: Router, named: str) -> None:
        from hmz.runtime.watching.following import Following

        self.named = named
        self._router = router
        self.lock = threading.Condition()
        self.sub: Subscription | None = None
        self.following = Following()
        self.standing: dict[str, dict[str, Any]] = {}
        self.asides: dict[str, _Aside] = {}
        self.used = time.monotonic()
        #: Held while the daemon's frontend is being attached, so that it is attached once.
        self._attaching = threading.Lock()

    def attached(self) -> Subscription:
        """The daemon's frontend of the workspace's own host, attached where it is not."""
        with self._attaching:
            return self._attaches()

    def _attaches(self) -> Subscription:
        from hmz.daemon.hosts import Subscription
        from hmz.runtime.watching.following import Following

        with self.lock:
            self.used = time.monotonic()
            if self.sub is not None and not self.sub.gone:
                return self.sub
            self.following.close()
            self.following, self.standing = Following(), {}
        hosted = self._router.hosts.opened(self.named, "")
        frontend = _Frontend(self._told)
        sub = Subscription(frontend, "btw", hosted, figures=False)  # pyright: ignore[reportArgumentType]
        sub.client = hosted.attach(sub, replay=True, since=None)
        sub.opened()
        with self.lock:
            self.sub = sub
        threading.Thread(target=self._lingers, daemon=True, name="hmz-btw").start()
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
        with self.lock:
            sub = self.sub
        if sub is not None and not sub.gone:
            with contextlib.suppress(Exception):
                sub.hosted.ask(sub.client, {"do": "unaside", "side": side})

    def _told(self, message: dict[str, Any]) -> None:
        kind = str(message.get("type") or "")
        following = self.following
        with self.lock:
            if "seq" not in message and kind not in ("welcome", "live", "gone"):
                self.standing[kind] = message
        with contextlib.suppress(Exception):
            if kind == "started":
                following.started(message)
                # A side conversation is about the epic it was opened on, which has gone.
                threading.Thread(
                    target=self.leave, kwargs={"going": True}, daemon=True
                ).start()
            elif kind == "printed":
                following.printed(str(message.get("text") or ""))
            elif kind == "opened":
                following.opened(message)
            elif kind == "event":
                following.heard(message)
            elif kind == "ended":
                following.ended(message)
            elif kind == "gone":
                self.leave(unasking=False)

    def leave(
        self, aside: str | None = None, *, unasking: bool = True, going: bool = False
    ) -> None:
        """Closes asides: one by name, those about the epic going, or every one."""
        with self.lock:
            left = [
                one
                for name, one in self.asides.items()
                if (aside is None or name == aside) and (not going or one.about is None)
            ]
            self.asides = {k: v for k, v in self.asides.items() if v not in left}
        for one in left:
            one.mode.close(unasking=unasking)

    def snapshot(self) -> FlowSnapshot:
        """The epic going, as a side question is told it."""
        with self.lock:
            standing = dict(self.standing)
        run: dict[str, Any] = standing.get("run") or {}
        calls: list[dict[str, Any]] = (standing.get("calls") or {}).get("calls") or []
        waiting: dict[str, Any] = standing.get("waiting") or {}
        pending: list[dict[str, Any]] = (standing.get("pending") or {}).get(
            "pending"
        ) or []
        return self.following.snapshot(
            flow=" ▸ ".join(str(one.get("name")) for one in calls)
            or str(run.get("flow") or ""),
            task=str(run.get("task") or ""),
            workspace=self.named,
            going=run.get("state") not in (None, "idle"),
            working=list((standing.get("sessions") or {}).get("working") or []),
            waiting=len(waiting.get("queued") or []) + len(waiting.get("given") or []),
            waiting_for_input=any(one.get("mode") == "listen" for one in pending),
        )

    def _lingers(self) -> None:
        """Lets go of the host once nothing has been asked and nothing held for a minute."""
        while True:
            time.sleep(1.0)
            with self.lock:
                sub = self.sub
                if sub is None or sub.gone:
                    return
                if self.asides or any(one.question for one in self.asides.values()):
                    self.used = time.monotonic()
                if time.monotonic() - self.used < _LINGER:
                    continue
                self.sub = None
            sub.dropped()
            return


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
        """`btw.list`: the asides open about one epic, attaching to nothing."""
        named = workspace(call.params["workspace"])
        epic = str(call.params.get("epic") or "")
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
                        "asked": list(one.asked),
                        "said": list(one.said),
                    }
                    for name, one in held.asides.items()
                    if one.epic == epic
                ]
        return {"asides": asides, "default": _answers()}

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
        from hmz.runtime.watching.btw import NOBODY, Btw, Left

        named = workspace(call.params["workspace"])
        question = " ".join(str(call.params["question"]).split())
        aside = str(call.params["aside"])
        to = str(call.params.get("to") or "")
        epic = str(call.params.get("epic") or "")
        held = self._of(named)
        with held.lock:
            opens = aside not in held.asides
        if opens and not to and not _answers():
            raise _refused(409, NOBODY)
        about: FlowSnapshot | None = None
        opening: Callable[[str], dict[str, Any]] | None = None
        if opens:
            held.attached()
            if epic and not _still(held, epic, to):
                about, opening = _recalled(epic)
                if to:
                    opening(to)
        with held.lock:
            one = held.asides.get(aside)
            if one is None:
                one = _Aside(to, epic, about)
                kept = one
                frozen = about
                one.mode = Btw(
                    to,
                    aside=held.aside
                    if opening is None
                    else _recalling(opening, held.aside),
                    unaside=held.unaside,
                    sessions=lambda: (
                        list(held.following.seen)
                        if frozen is None
                        else [key for key, _ in frozen.sessions]
                    ),
                    source=_source,
                    asking=lambda key, asking: kept.asked.append(
                        {"to": key, "question": asking}
                    ),
                )
                held.asides[aside] = one
            if one.question:
                raise _refused(
                    409, "btw is still answering the last question asked of it."
                )
            one.question, one.asked = question, []
            held.used = time.monotonic()
        try:
            held.attached()
            answer = one.mode.ask(question, one.about or held.snapshot())
        except Left:
            raise _refused(
                409, "A new epic started, which closed what was asked."
            ) from None
        except Refused as why:
            raise _refused(409, str(why)) from None
        finally:
            with held.lock:
                one.question = ""
                held.used = time.monotonic()
        if not answer:
            raise _refused(502, "The agent returned no answer.")
        said = {
            "aside": aside,
            "to": one.to,
            "question": question,
            "answer": answer,
            "asked": list(one.asked),
        }
        with held.lock:
            one.said = [*one.said, said][-_SAID:]
        return said


def _still(held: _Workspace, epic: str, to: str) -> bool:
    """Whether an epic, or a session of it, is one the host still holds."""
    with held.lock:
        run = held.standing.get("run") or {}
    return run.get("epic") == epic and (not to or to in held.following.seen)


def _named(epic: str) -> Any:
    """An epic written down, by its name, of whichever workspace.

    Raises:
      RpcError: 404 where there is none.
    """
    from hmz.runtime.epic import every, read

    if epic and "/" not in epic and not epic.startswith("."):
        for at in every():
            if at.name == epic and (ran := read(at)) is not None:
                return ran
    raise _refused(404, f"There is no epic {epic}.")


def _recalled(epic: str) -> tuple[FlowSnapshot, Callable[[str], dict[str, Any]]]:
    """An epic written down, as side questions about it and its sessions are asked."""
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
    """`aside`, but for a session asked by its key, carried on from where its epic kept it."""

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
    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0


def _answers() -> str:
    """The agent the setting `btw` names, as it says it now, or "" for nobody."""
    from hmz.coganchor import settings

    said = settings.read().get("btw")
    return said if isinstance(said, str) else ""


def _source() -> dict[str, str] | None:
    """What the btw agent is opened as: what the setting `btw` names."""
    from hmz.runtime.kept import read_back, written
    from hmz.runtime.watching.btw import opened_as

    said = read_back(answers) if (answers := _answers()) else None
    return opened_as(written(said) if said is not None else "")
