"""`hmz attach` -- one more frontend of the runs a host is holding in this directory.

    hmz attach -c reviewer        # answer for the reviewer, and read everything else
    hmz attach --json             # every message as NDJSON; a request a line on stdin

A run held for frontends is read by as many of them at once as want to: an interface, a bot
written against the SDK, and this. Each claims the `Outworlder` roles it answers for -- a
role somebody else holds is theirs alone to answer -- and reads what every agent says, what
every question was, and who answered it.

A line typed here answers the oldest question this frontend may answer, and is otherwise said
to the run, into whichever turn is open or the next to start. `/afk`, `/claim`, `/release`
and `/stop` are what they are at the interface. Nothing here starts a run: whoever holds the
runs does, and this follows the one going -- or the next one, where none is -- until it ends.
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

    from hmz.daemon import Link

    from .output import Out, Shown

__all__ = ["attach"]

#: The mark a line said to the run is set on, as the interface marks one.
_YOURS = "❯"
_SAID = "⏺" if sys.platform == "darwin" else "●"
_DOT = " · "


def _line() -> argparse.ArgumentParser:
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz attach",
        description="Attach to runs in this directory as an additional frontend to "
        "view agent messages, questions asked by the run, and who answered them. "
        "Typing input answers the oldest question you can answer, or sends a "
        "message to the run. The commands /afk [on|off] [ROLE], /claim ROLE, "
        "/release ROLE, and /stop work as they do in the terminal interface. Does "
        "not start a run; follows the current or next run until it ends.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="stream messages as newline-delimited JSON and read JSON requests from "
        "stdin",
    )
    parser.add_argument(
        "-c",
        "--claim",
        action="append",
        default=[],
        metavar="ROLE",
        help="answer exclusively for this Outworlder role; can be specified "
        "multiple times",
    )
    return parser


class _Following:
    """One frontend's reading of the runs, and when it has read what it came for."""

    def __init__(self, link: Link, out: Out, shown: Shown) -> None:
        self.link = link
        self.done = threading.Event()
        self._out = out
        self._shown = shown
        self._lock = threading.Lock()
        self._live = False
        self._followed: int | None = None
        self._run: dict[str, Any] = {}
        self._claims: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._pending: list[dict[str, Any]] = []
        self._away: dict[str, Any] = {"all": False, "of": {}}

    # -- what arrives, on the link's own thread

    def heard(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if self._out.as_json:
            self._out.record(**message)
        else:
            self._shows(message)
        with self._lock:
            if kind == "run":
                self._run = message
            elif kind == "claims":
                was, self._claims = self._claims, dict(message.get("claims") or {})
                if self._live and not self._out.as_json:
                    self._claimed(was)
            elif kind == "clients":
                clients: list[dict[str, str]] = message.get("clients") or []
                self._names = {one["client"]: one["name"] for one in clients}
            elif kind == "pending":
                self._pending = list(message.get("pending") or [])
            elif kind == "away":
                self._away = message
            elif kind == "live":
                self._live = True
                state = self._run.get("state")
                if state == "running":
                    self._followed = self._run.get("run")
                elif state == "stopping":
                    self._followed = self._run.get("stopping")
            elif kind == "started" and self._live and self._followed is None:
                self._followed = message.get("run")
            elif (
                kind == "ended" and self._live and message.get("run") == self._followed
            ) or kind == "gone":
                self.done.set()

    def _shows(self, message: dict[str, Any]) -> None:
        """One message as a line for a person, where it is one worth a line."""
        kind = message.get("type")
        line = self._out.line
        if kind == "event":
            self._shown.told(message)
        elif kind == "welcome":
            line((f"hmz attach: connected as {message.get('name')}", "dim"))
        elif kind == "started":
            started = f"{message.get('flow')} started by {message.get('by')}"
            line((f"{_SAID} ", "dim"), (f"{started}: {message.get('task')}", "dim"))
        elif kind == "asked":
            self._asked(message)
        elif kind == "answered":
            line(
                (f"{_YOURS} ", ""),
                (str(message.get("text")), ""),
                (f"{_DOT}{message.get('by')} for {message.get('role')}", "dim"),
            )
        elif kind == "withdrawn":
            line((f"   question withdrawn: {message.get('why')}", "dim"))
        elif kind == "said":
            line(
                (f"{_YOURS} ", ""),
                (str(message.get("text")), ""),
                (
                    f"{_DOT}{message.get('by')} to {message.get('key') or 'the run'}",
                    "dim",
                ),
            )
        elif kind == "refused":
            line(
                ("hmz: ", "red"),
                (
                    (
                        f"{message.get('agent')} rejected the message: "
                        f"{message.get('because')}"
                    ),
                    "red",
                ),
            )
        elif kind == "unheld":
            put = f"   sent to {message.get('agent')}, which ended its turn"
            line((f"{put} without acknowledging receipt", "dim"))
        elif kind == "dropped":
            held: list[dict[str, Any]] = [
                *(message.get("given") or []),
                *(message.get("queued") or []),
            ]
            never = [str(one.get("text")) for one in held]
            line(
                (
                    f"   never sent ({message.get('because')}): {' | '.join(never)}",
                    "dim",
                )
            )
        elif kind == "printed":
            line((str(message.get("text")), ""))
        elif kind == "stopping":
            line((f"— {message.get('by')} is stopping the flow —", "dim"))
        elif kind == "ended":
            self._ended(message)
        elif kind == "gone":
            line((f"hmz attach: {message.get('why')}", "dim"))

    def _claimed(self, was: dict[str, str]) -> None:
        """Says which roles have become this frontend's, or stopped being. Under the lock."""
        mine = self.link.client
        for role, owner in self._claims.items():
            if owner == mine and was.get(role) != mine:
                self._out.line((f"hmz attach: {role} is claimed by you", "dim"))
        for role, owner in was.items():
            if owner == mine and self._claims.get(role) != mine:
                now = self._claims.get(role)
                taken = (
                    f"now claimed by {self._names.get(now, now)}"
                    if now
                    else "unclaimed"
                )
                self._out.line((f"hmz attach: {role} is {taken}", "dim"))

    def _asked(self, message: dict[str, Any]) -> None:
        role = str(message.get("role"))
        with self._lock:
            live = self._live
            owner = self._claims.get(role)
            name = self._names.get(owner or "", owner or "")
        # Whose it is, once that is known: a question read back from before this frontend
        # arrived is read before who holds what is.
        whose = (
            ""
            if not live
            else f"{_DOT}claimed by you"
            if owner == self.link.client
            else f"{_DOT}claimed by {name}"
            if owner
            else f"{_DOT}unclaimed"
        )
        self._out.line(
            (f"{_SAID} ", "yellow"),
            (f"{role}: {message.get('text')}", "yellow"),
            (whose, "dim"),
        )
        for at, option in enumerate(message.get("options") or [], 1):
            self._out.line((f"      {at}. {option}", "dim"))

    def _ended(self, message: dict[str, Any]) -> None:
        how, why = message.get("how"), message.get("why")
        if how == "done":
            self._out.line(("— the flow is done —", "dim"))
        elif how == "stopped":
            self._out.line(("— the flow stopped —", "dim"))
        elif how == "budget":
            self._out.line((f"hmz: stopped -- {why}", "yellow"))
        else:
            self._out.line((f"hmz: the flow {how}: {why}", "red"))

    # -- what is typed, on a thread of its own

    def reads(self) -> None:
        """Takes stdin a line at a time until it ends, which is not the end of following."""
        for typed in sys.stdin:
            said = typed.rstrip("\n")
            if not said.strip():
                continue
            try:
                if self._out.as_json:
                    self._asks(said)
                else:
                    self._says(said)
            except Exception as why:  # noqa: BLE001 -- said, and the next line read
                # A refusal, a host gone quiet or a line nothing could make sense of: said,
                # and reading goes on, since a reader that stopped would take nothing more.
                self._out.line(
                    ("hmz: ", "red"), (str(why) or type(why).__name__, "red")
                )

    def _asks(self, typed: str) -> None:
        """One request object, passed through, and its answer written as a reply."""
        import json

        from hmz.runtime import Refused

        try:
            said: object = json.loads(typed)
        except ValueError:
            said = None
        if not isinstance(said, dict):
            self._out.record(type="reply", to="", ok=False, why="not a request object")
            return
        request: dict[str, Any] = said  # pyright: ignore[reportUnknownVariableType]
        try:
            answer = self.link.asked(request)
        except Refused as why:
            answer = {"ok": False, "why": str(why)}
        self._out.record(type="reply", to=request.get("id", ""), **answer)

    def _says(self, typed: str) -> None:
        """One line, as the interface takes one: a command, an answer, or a word to the run."""
        if typed.startswith("/"):
            self._commands(typed)
            return
        with self._lock:
            asked = next(
                (
                    one
                    for one in self._pending
                    if one.get("owner") in (None, self.link.client)
                ),
                None,
            )
        if asked is not None:
            self.link.answer(str(asked.get("question")), typed)
        else:
            self.link.say(typed)

    def _commands(self, typed: str) -> None:
        named, *argv = typed[1:].split() or [""]
        if named == "stop":
            self.link.stop()
        elif named in ("claim", "release") and len(argv) == 1:
            if named == "claim":
                self.link.claim(argv[0])
            else:
                self.link.release(argv[0])
            self._out.line((f"hmz attach: {argv[0]} {named}ed", "dim"))
        elif named == "afk" and len(argv) <= 2:  # noqa: PLR2004 -- a switch and a role
            switch = [one for one in argv if one in ("on", "off")]
            role = next((one for one in argv if one not in ("on", "off")), "")
            with self._lock:
                of: dict[str, Any] = self._away.get("of") or {}
                now = (
                    bool(of.get(role, self._away.get("all")))
                    if role
                    else bool(self._away.get("all"))
                )
            on = switch[0] == "on" if switch else not now
            self.link.afk(on=on, role=role)
            self._out.line(
                (
                    f"hmz attach: {'away' if on else 'here'}{f' as {role}' if role else ''}",
                    "dim",
                )
            )
        else:
            takes = "/afk [on|off] [ROLE], /claim ROLE, /release ROLE and /stop"
            self._out.line(
                ("hmz: ", "red"),
                (f"unknown command: {typed}; available commands: {takes}", "red"),
            )


def attach(argv: list[str]) -> int:
    """Reads the runs held in this directory as one more frontend, until the run ends.

    Args:
      argv: What followed `attach`.

    Returns:
      Zero once the run followed has ended or the host let go, one where nothing is held
      here to read, and two where a role asked for is somebody else's.
    """
    said = _line().parse_args(argv)
    from hmz import daemon
    from hmz.runtime import Refused

    from .output import Out, Shown

    found = daemon.running()
    if found is None:
        print("hmz attach: nothing to attach to in this directory", file=sys.stderr)
        return 1
    if not found.protocol:
        print(f"hmz attach: {daemon.older(found)}", file=sys.stderr)
        return 1
    try:
        link = found.link(kind="cli")
    except OSError as why:
        print(f"hmz attach: {why}", file=sys.stderr)
        return 1
    with link, Out(as_json=said.json) as out:
        for role in said.claim:
            try:
                link.claim(role)
            except Refused as why:
                print(f"hmz attach: error: {why}", file=sys.stderr)
                return 2
        following = _Following(link, out, Shown(out))
        link.heard(following.heard)
        threading.Thread(target=following.reads, daemon=True, name="stdin").start()
        try:
            while not following.done.wait(0.5):
                pass
        except KeyboardInterrupt:
            # Letting go, which leaves the run to whoever else is reading it.
            print("hmz attach: detached", file=sys.stderr)
    return 0
