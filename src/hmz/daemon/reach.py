"""Ai-chan's reach: what the session of one Ai-chan conversation may call, and see.

Every Ai-chan conversation is fixed, when it is made, to a scope -- the daemon, one workspace or
one epic -- and a permission: a preset, `read-only` or `danger-full-access`, and a network
(Section 14 of core.md). Its host is told the socket of a link of its own, its scoped link, and
every session over it carries the conversation's reach (Section 4.21 of daemon.md): each call is
held to it by the method's `x-hmz-reach` and `x-hmz-writes` in the OpenRPC document, refused 403
by the first of four rules that holds, and the lists it is answered are cut to what it reaches.

The conversations themselves are kept here too, in `<home>/ai/<machine>/conversations.yaml`
(Section 4.16 of files.md), together with what starts the host of an `ai:` slot and listens on
its scoped link while that host is up.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import shutil
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz.coganchor import unix
from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hmz.daemon.hosts import Hosted, Hosts
    from hmz.daemon.sessions import Session
    from hmz.rpc import Pipe

__all__ = [
    "FLOW",
    "KIND",
    "LINK",
    "PRESETS",
    "ROLE",
    "SCOPES",
    "Conversations",
    "Held",
    "Links",
    "Reach",
    "conversations",
    "epic_at",
    "epics",
    "holding",
    "notices",
    "ran_in",
]

#: A flow an `ai:` slot runs in place of her chat (Section 14.4 of core.md), by the name it is
#: offered under -- a test's stand-in -- or "" for her chat.
FLOW = ""

#: The one agent role such a flow declares, which a conversation's nous fills.
ROLE = "ai_chan"

#: What Ai-chan's session says it is in `session.hello`.
KIND = "ai-chan"

#: The variable that names the scoped link to the host of an `ai:` slot (Section 3.11.2.17 of
#: files.md).
LINK = "HUMANIZE_AICHAN_LINK"

#: What a conversation may reach, widest first.
SCOPES = ("daemon", "workspace", "epic")

#: What a conversation may change.
PRESETS = ("read-only", "danger-full-access")


#: How often the host of a conversation is asked whether it has named its epic yet.
_NAMING = 0.2

#: How often a conversation's host is asked what was last said in it, once it is named, in
#: seconds.
_FOLLOWING = 1.0

#: How much of what was last said in a conversation is kept as its `latest`, in characters.
_LATEST = 120

#: How often a scoped link looks at whether it has been closed.
_TICK = 0.5


@dataclass(frozen=True)
class Reach:
    """What one Ai-chan conversation may reach and change.

    Attributes:
      id: The conversation's `id`.
      scope: `daemon`, `workspace` or `epic`.
      workspace: The workspace of its host: of its scope, or `<home>/ai/<machine>`.
      epic: The epic name of an `epic` scope, else "".
      preset: `read-only` or `danger-full-access`.
      network: Whether its harness may reach the network.
    """

    id: int
    scope: str
    workspace: str
    epic: str
    preset: str
    network: bool

    @classmethod
    def of(cls, conversation: Mapping[str, Any]) -> Reach:
        """The reach of a conversation as it is recorded."""
        return cls(
            int(conversation["id"]),
            str(conversation["scope"]),
            str(conversation["workspace"]),
            str(conversation.get("epic") or ""),
            str(conversation["preset"]),
            conversation.get("network") is True,
        )


#: The reach of the call being carried out, held as :class:`Held`, or None for a call of a
#: session that carries none.
holding: contextvars.ContextVar[Held | None] = contextvars.ContextVar(
    "holding", default=None
)


def epics() -> Callable[[str, str], bool] | None:
    """Whether the call being carried out may be told of an epic, by name and workspace.

    Returns:
      None where the call's session carries no reach.
    """
    held = holding.get()
    return None if held is None else held.epic


def conversations() -> Conversations:
    """The Ai-chan conversations of this machine: the daemon's own, where this process is it."""
    from hmz.daemon import routing

    return routing.serving.links.kept if routing.serving else Conversations()


def notices() -> Callable[[Mapping[str, Any]], bool] | None:
    """Whether the call being carried out may be told of a notice.

    Returns:
      None where the call's session carries no reach.
    """
    held = holding.get()
    return None if held is None else held.notice


@functools.cache
def _annotated() -> dict[str, tuple[dict[str, str], bool]]:
    """Each method's `x-hmz-reach` and `x-hmz-writes`, by name."""
    from hmz.rpc import document

    return {
        str(one["name"]): (
            cast("dict[str, str]", one.get("x-hmz-reach") or {"scope": "never"}),
            one.get("x-hmz-writes") is not False,
        )
        for one in cast("list[dict[str, Any]]", document()["methods"])
    }


def _whole(said: object) -> str:
    """A workspace as a call names it, whole where it can be, else as it was said."""
    path = Path(str(said)).expanduser()
    return where.workspace(path) if path.is_absolute() else str(said)


class Held:
    """One call of a session that carries a reach, as the daemon holds it to that reach.

    Args:
      reach: The reach.
      session: The session, whose epic subscriptions the call may name.
      hosts: Every host the daemon holds.
      kept: The Ai-chan conversations, whose epics no reach reaches.
    """

    def __init__(
        self, reach: Reach, session: Session, hosts: Hosts, kept: Conversations
    ) -> None:
        self.reach = reach
        self._session = session
        self._hosts = hosts
        self._kept = kept

    @functools.cached_property
    def _epics(self) -> set[str]:
        """The epics of every Ai-chan conversation, read once for the call."""
        return self._kept.epics()

    # -- refusals (Section 4.21.3 of daemon.md)

    def refusal(self, method: str, params: Mapping[str, Any]) -> str | None:
        """Why a call is refused 403, by the first rule that holds, or None where it is not."""
        annotated, writes = _annotated().get(method, ({"scope": "never"}, True))
        scope = annotated.get("scope", "never")
        if method == "epic.attach":
            if params.get("scratch") is True:
                scope = "daemon"
            if params.get("slot") in ("chat:", "exec:"):
                writes = True
        if method == "epic.aside" and any(
            params.get(one) for one in ("runs", "recall", "kept", "cwd")
        ):
            # An agent and a directory the call chooses, which the host confines by no reach.
            scope = "never"
        if method == "flows.check":
            from hmz.runtime.flowing.loading import parse
            from hmz.runtime.flowing.verses import pathed

            # A flow named by a path or a repository is loaded, and so run, in the daemon's
            # own process: only one named as it is on offer is one a `read-only` Ai-chan
            # cannot have written. Read as the loader reads it, so that no spelling of a
            # path is a name here; what is no ref at all loads nothing.
            with contextlib.suppress(ValueError):
                ref = parse(cast("str", params.get("flow")))
                writes = ref.url is not None or pathed(ref.where)
        if scope == "never":
            return f"Ai-chan cannot call {method}."
        workspace, slot = self._names(annotated, params)
        if slot.startswith("ai:"):
            return "Ai-chan cannot reach an Ai-chan conversation."
        if workspace is None and scope in ("workspace", "epic") and "sub" in annotated:
            # A subscription that is not there: the call is refused 410 as it is carried out.
            scope = "any"
        elif workspace is None and "workspace" in annotated:
            scope = "daemon"
        what = self._out(scope, annotated, params, workspace or "", slot)
        if what:
            return f"{method} is out of Ai-chan's scope: {what}."
        if writes and self.reach.preset == "read-only":
            return f"Ai-chan is read-only, and {method} changes things."
        return None

    def _names(
        self, annotated: Mapping[str, str], params: Mapping[str, Any]
    ) -> tuple[str | None, str]:
        """The workspace and the slot of the host a call names, None for no workspace."""
        if "sub" in annotated:
            with self._session.lock:
                sub = self._session.subs.get(str(params.get(annotated["sub"])))
            if sub is None:
                return None, ""
            hosted = cast("Hosted", sub.hosted)
            return hosted.workspace, hosted.slot
        said = params.get(annotated.get("workspace", ""))
        slot = params.get(annotated.get("slot", ""))
        return (
            None if said is None else _whole(said),
            slot if isinstance(slot, str) else "",
        )

    def _out(
        self,
        scope: str,
        annotated: Mapping[str, str],
        params: Mapping[str, Any],
        workspace: str,
        slot: str,
    ) -> str:
        """What a call acts on that the reach does not reach, or "" where it reaches it."""
        if scope == "daemon":
            return "" if self.reach.scope == "daemon" else "the daemon"
        if scope == "workspace":
            return "" if self.workspace(workspace) else f"the workspace {workspace}"
        if scope != "epic":
            return ""
        if "epic" in annotated and "sub" not in annotated:
            # Or the chat a side question names in its place (Section 4.15.1 of daemon.md).
            epic = str(params.get(annotated["epic"]) or params.get("chat") or "")
            if not epic and workspace:
                hosted = self._hosts.get(workspace, slot)
                epic = _held(hosted.status()) if hosted else ""
                return "" if self.epic(epic, workspace) else f"the epic {epic}"
            # An epic named is reached by where it was run, not by the workspace named.
            if self.reach.scope == "workspace" and not self.workspace(
                workspace or self.reach.workspace
            ):
                return f"the workspace {workspace}"
            return "" if self.epic(epic) else f"the epic {epic}"
        if self.host(workspace, slot):
            return ""
        return f"the host {slot} of {workspace}" if slot else f"the host of {workspace}"

    # -- what it reaches (Section 4.21.1 of daemon.md)

    def workspace(self, workspace: str) -> bool:
        """Whether it reaches a workspace."""
        scope = self.reach.scope
        return scope == "daemon" or (
            scope == "workspace" and workspace == self.reach.workspace
        )

    def epic(self, name: str, workspace: str = "") -> bool:
        """Whether it reaches an epic, by its name and, where known, its workspace."""
        if not name or name in self._epics:
            return False
        scope = self.reach.scope
        if scope == "epic":
            return name == self.reach.epic
        if scope == "daemon":
            return True
        ran = _whole(workspace) if workspace else ran_in(name)
        return ran == self.reach.workspace

    def host(self, workspace: str, slot: str, epic: str | None = None) -> bool:
        """Whether it reaches a host; `epic` the one it holds, where already known."""
        if slot.startswith("ai:"):
            return False
        if self.reach.scope != "epic":
            return self.workspace(workspace)
        if epic is None:
            hosted = self._hosts.get(workspace, slot)
            epic = _held(hosted.status()) if hosted else ""
        return bool(epic) and epic == self.reach.epic

    def notice(self, notice: Mapping[str, Any]) -> bool:
        """Whether it may be told of a notice, by the host it names."""
        return self.host(
            str(notice.get("workspace") or ""),
            str(notice.get("slot") or ""),
            _held(notice),
        )

    # -- answers cut to it (Section 4.21.4 of daemon.md)

    def answered(self, method: str, answer: Any) -> Any:
        """An answer with every entry it does not reach left out."""
        if not isinstance(answer, dict):
            return answer
        said = cast("dict[str, Any]", answer)
        if method == "hosts.list":
            held = cast("list[dict[str, Any]]", said["held"])
            return said | {
                "held": [
                    one
                    for one in held
                    if self.host(str(one["workspace"]), str(one["slot"] or ""))
                ]
            }
        if method == "hosts.running":
            running = cast("list[dict[str, Any]]", said["running"])
            return said | {
                "running": [
                    one
                    for one in running
                    if self.host(
                        str(one["workspace"]), str(one["slot"] or ""), _held(one)
                    )
                ]
            }
        if method == "workspaces.list":
            listed = cast("list[dict[str, Any]]", said["workspaces"])
            return said | {
                "workspaces": [one for one in listed if self.workspace(one["path"])]
            }
        if method == "notices.list":
            told = cast("list[dict[str, Any]]", said["notices"])
            return said | {"notices": [one for one in told if self.notice(one)]}
        return said


def _held(said: Mapping[str, Any]) -> str:
    """The epic a host, a notice or a run going names, or the chat, which a reach reaches alike."""
    return str(said.get("epic") or said.get("chat") or "")


def ran_in(name: str) -> str:
    """The workspace an epic was run in or a chat had in, by its name, or "" for neither."""
    from hmz.runtime.epic import read

    at = epic_at(name)
    if at is not None and (ran := read(at)) is not None:
        return _whole(ran.workspace) if ran.workspace else ""
    return ""


def epic_at(name: str) -> Path | None:
    """The directory of a chat or an epic, by its name, or None where there is none.

    An Ai-chan conversation is kept as a chat is, one an earlier hmz began as an epic among
    them once the daemon has moved it (Section 6.12.14 of files.md): until then it is
    neither, and is not read or carried on (Section 8.7.10 of core.md).
    """
    from hmz.runtime.epic import chats, chatted, every

    kept = (one for one in every() if one.name == name and not chatted(one))
    return next((at for at in (*chats(), *kept) if at.name == name), None)


def _left(name: str) -> bool:
    """Whether a name is that of a chat an earlier hmz kept as an epic, not yet moved."""
    from hmz.runtime.epic import chatted, every

    return any(at.name == name and chatted(at) for at in every())


def preview(text: object) -> str:
    """What a conversation's `latest` is of something said in it: one line, cut short.

    Its whitespace made single spaces, and cut at 120 characters (Section 4.22.3.1 of
    daemon.md).
    """
    return " ".join(str(text or "").split())[:_LATEST]


def heard(status: Mapping[str, Any]) -> tuple[str, str]:
    """What Ai-chan last answered, as her host says it: what it waits between turns on.

    Returns:
      Which wait that is, another each turn, and what she answered; or two "".
    """
    pending = cast("list[dict[str, Any]]", status.get("pending") or [])
    return next(
        (
            (str(one.get("question") or ""), preview(one.get("text")))
            for one in reversed(pending)
            if one.get("mode") == "listen"
        ),
        ("", ""),
    )


def turning(status: Mapping[str, Any]) -> bool:
    """Whether Ai-chan's turn is open, as her host says it (Section 4.22.3.2 of daemon.md)."""
    if "turn" in status:
        return status["turn"] == "running"
    # Her turn is open while her epic runs and asks nobody what to say next.
    pending = cast("list[dict[str, Any]]", status.get("pending") or [])
    listening = any(one.get("mode") == "listen" for one in pending)
    return status.get("state") == "running" and not listening


class Conversations:
    """Every Ai-chan conversation not forgotten, as `conversations.yaml` keeps them.

    And the epic of each one forgotten, by its name, as `forgotten.yaml` keeps them.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    @functools.cached_property
    def at(self) -> Path:
        """`<home>/ai/<machine>/`, which holds them, and is the workspace of a `daemon` scope."""
        from hmz import home
        from hmz.trust.identity import machine_id

        return home() / "ai" / machine_id()

    def scratch(self, ident: int) -> Path:
        """The scratch directory of a conversation."""
        return self.at / str(ident)

    def all(self) -> list[dict[str, Any]]:
        """Every conversation, in the order made."""
        held = [
            cast("dict[str, Any]", one)
            for one in self._listed("conversations.yaml")
            if isinstance(one, dict)
        ]
        return [one for one in held if isinstance(one.get("id"), int)]

    def _listed(self, name: str) -> list[object]:
        """The YAML list one of its files holds, or none where it holds none."""
        try:
            said: object = yaml.safe_load((self.at / name).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            return []
        return cast("list[object]", said) if isinstance(said, list) else []

    def of(self, slot: str) -> dict[str, Any] | None:
        """The conversation of a slot, or None."""
        return next((one for one in self.all() if one.get("slot") == slot), None)

    def epics(self) -> set[str]:
        """The epic of every conversation that has one, kept or forgotten, by its name."""
        kept = {str(one["record"]) for one in self.all() if one.get("record")}
        return kept | {str(one) for one in self._listed("forgotten.yaml")}

    def made(self, said: Mapping[str, Any]) -> dict[str, Any]:
        """Records a new conversation, its `id` the next, and makes its scratch directory.

        Args:
          said: Every key of its entry but `id`, `record`, `created` and `updated`.
        """
        with self._lock:
            held = self.all()
            ident = max((int(one["id"]) for one in held), default=0) + 1
            now = where.now()
            made = {
                "id": ident,
                **said,
                "record": "",
                "created": now,
                "updated": now,
            }
            self._writes([*held, made])
            self.scratch(ident).mkdir(mode=0o700, exist_ok=True)
            return made

    def changed(self, ident: int, **said: Any) -> None:
        """Writes down what changed of one conversation."""
        with self._lock:
            held = self.all()
            for one in held:
                if one["id"] == ident:
                    one.update(said)
            self._writes(held)

    def forgot(self, ident: int, record: str = "") -> dict[str, Any] | None:
        """Forgets one conversation and its scratch directory; None where there was none.

        Args:
          ident: Its `id`.
          record: Its epic where its entry names none yet, as its host says it, or "".
        """
        with self._lock:
            held = self.all()
            gone = next((one for one in held if one["id"] == ident), None)
            if gone is None:
                return None
            # Its epic is written down first: it is never one no file says is hers.
            if epic := str(gone.get("record") or record):
                self._writes([*self._listed("forgotten.yaml"), epic], "forgotten.yaml")
            self._writes([one for one in held if one is not gone])
        shutil.rmtree(self.scratch(ident), ignore_errors=True)
        return gone

    def _writes(self, held: list[Any], name: str = "conversations.yaml") -> None:
        from hmz.coganchor import atomic

        self.at.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic.writes(
            self.at / name,
            yaml.safe_dump(held, sort_keys=False, allow_unicode=True),
            mode=0o600,
        )


class Links:
    """The hosts of `ai:` slots, and the scoped link each listens on while its host is up.

    Args:
      admit: Takes a session over a scoped link on, carrying a reach.
      dropped: Closes every session carrying the reach of a conversation, by its `id`.
    """

    def __init__(
        self,
        admit: Callable[[Pipe, Reach], object],
        dropped: Callable[[int], None],
    ) -> None:
        self._admit = admit
        self._dropped = dropped
        self._lock = threading.Lock()
        self._open: dict[str, tuple[socket.socket, int]] = {}
        self.kept = Conversations()
        #: The task each new conversation is made with, by slot, until its host takes it:
        #: what a conversation is told first is not kept beside it.
        self.tasks: dict[str, str] = {}

    @staticmethod
    def path(slot: str) -> Path:
        """The socket of the scoped link of a slot (Section 7.6.9 of files.md)."""
        return where.at() / f"ai-{slot.removeprefix('ai:')}.sock"

    def before(self, workspace: str, slot: str) -> dict[str, str]:
        """Listens on the scoped link of a host about to start, and answers what it is told.

        Raises:
          RpcError: 404 for a slot of no conversation of that workspace.
        """
        from hmz.rpc import Code, RpcError

        conversation = self.kept.of(slot)
        if conversation is None or conversation["workspace"] != workspace:
            raise RpcError(Code.NOT_FOUND, f"There is no Ai-chan conversation {slot}.")
        path = self.path(slot)
        reach = Reach.of(conversation)
        with self._lock:
            if slot not in self._open:
                path.unlink(missing_ok=True)
                listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    with unix.reached(path) as reaching:
                        listening.bind(reaching)
                    path.chmod(0o600)
                    listening.listen(16)
                except OSError:
                    listening.close()
                    raise
                listening.settimeout(_TICK)
                self._open[slot] = (listening, reach.id)
                threading.Thread(
                    target=self._takes,
                    args=(listening, reach),
                    name="hmz-ai-link",
                    daemon=True,
                ).start()
        return {LINK: str(path)}

    def _takes(self, listening: socket.socket, reach: Reach) -> None:
        from hmz.reach.pipes import SocketPipe

        while True:
            try:
                one, _ = listening.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            one.settimeout(None)
            self._admit(SocketPipe(one, trusted=True), reach)

    def after(self, hosted: Hosted) -> None:
        """Starts the chat of a conversation's host, which has just come up (Section 4.22.5).

        Anew, its task the first message, the first time; carrying it on every later time.
        Its name is written down once the host has named it, and what she last answered as
        she answers it, for as long as the host is up.

        Raises:
          RpcError: 404 where the conversation was forgotten, and 409 where the host refused.
        """
        from hmz.rpc import Code, RpcError

        conversation = self.kept.of(hosted.slot)
        if conversation is None:
            raise RpcError(
                Code.NOT_FOUND, f"There is no Ai-chan conversation {hosted.slot}."
            )
        record = str(conversation.get("record") or "")
        picked = epic_at(record) if record else None
        if record and picked is None and _left(record):
            # Not begun anew either, which would name another record and lose this one.
            raise RpcError(
                Code.NOT_FOUND,
                f"There is no chat {record}: an earlier hmz kept it as an epic, and it is "
                "moved among the chats the next time the daemon starts.",
            )
        task = "" if picked else self.tasks.get(hosted.slot, "")
        reach = {
            key: conversation[key]
            for key in ("id", "scope", "workspace", "epic", "preset", "network")
        }
        if FLOW:
            answer = hosted.started(
                {
                    "do": "start",
                    "flow": FLOW,
                    "task": task,
                    "agents": {ROLE: conversation["nous"]},
                    "params": reach,
                    "budget": {"cost": "Infinity"},
                    "resume": str(picked) if picked else False,
                }
            )
        else:
            # Her chat, its assistant playing her role (Section 14.4 of core.md).
            answer = hosted.chat(
                {
                    "do": "start",
                    "by": "hmz",
                    "agent": conversation["nous"],
                    "task": task,
                    "resume": str(picked) if picked else None,
                    "ai": reach,
                    "scratch": str(self.kept.scratch(int(conversation["id"]))),
                }
            )
        self.tasks.pop(hosted.slot, None)
        if not answer.get("ok"):
            raise RpcError(Code.CONFLICT, str(answer.get("why") or "refused"))
        threading.Thread(
            target=self._follows,
            args=(hosted, conversation),
            kwargs={"named": bool(picked)},
            name="hmz-ai-epic",
            daemon=True,
        ).start()

    def _follows(
        self, hosted: Hosted, conversation: Mapping[str, Any], *, named: bool
    ) -> None:
        """Writes down what a conversation's host says of it, until that host goes.

        What it writes it in, once it has named it, and what Ai-chan last answered with when
        she did, each time she has (Section 4.16.2 of files.md): what `aichan.list` says of a
        conversation no host holds.

        Args:
          hosted: Its host.
          conversation: Its entry, as the host came up.
          named: Whether its entry names what it is written in already.
        """
        ident = int(conversation["id"])
        # Whether a turn of hers was seen open in this host's life. Carried on, it comes up
        # waiting on what was written already, or on why it could not be carried on: no answer
        # of hers, which the first wait it is heard on is taken for until a turn was seen.
        turned = not named
        # Which wait she was last heard on: another one is another answer, the same words or not.
        waited: str | None = None
        while hosted.peer is not None and not hosted.peer.closed:
            status = hosted.status()
            said: dict[str, Any] = {}
            epic = str(status.get("chat") or status.get("epic") or "")
            if not named and epic:
                said["record"] = epic
                named = True
            turned = turned or turning(status)
            wait, answered = heard(status)
            if (wait or answered) and wait != waited:
                if turned and answered:
                    said |= {"latest": answered, "updated": where.now()}
                # A turn too short to be seen open is still one: every wait after this one.
                waited, turned = wait, True
            if said:
                self.kept.changed(ident, **said)
            time.sleep(_FOLLOWING if named else _NAMING)

    def went(self, slot: str) -> None:
        """Stops listening on a slot's scoped link, and closes every session over it."""
        with self._lock:
            held = self._open.pop(slot, None)
        if held is None:
            return
        listening, ident = held
        with contextlib.suppress(OSError):
            listening.close()
        self.path(slot).unlink(missing_ok=True)
        self._dropped(ident)

    def close(self) -> None:
        """Stops listening on every scoped link, as the daemon goes."""
        with self._lock:
            slots = list(self._open)
        for slot in slots:
            self.went(slot)
