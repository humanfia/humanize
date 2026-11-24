"""Chats, and the sessions a harness ran on its own (`chat.*`, `chat.harness.*`).

A chat is one conversation with one assistant (Section 8 of core.md), written down under a
name -- its id -- and held, while anybody talks to it, by a host of its own on a chat slot of
its workspace. So there are two ways of naming one, and the methods of a daemon take one or
the other: what is done to the chat as it is written down (`get`, `rename`, `fork`, `delete`)
takes its id, and what is done to it where it is held (`say`, `stop`, `set`, `move`) takes its
workspace and slot. :meth:`Chats.hold` is the way from the first to the second.

A turn is told to whoever follows the chat's host (`epic.attach`, `epic.event`), which
:class:`Turn` does: :meth:`Chats.follow` for a host already known, and :meth:`Chats.ask` for
the whole of saying a line to a chat by its id and hearing what it answers.

    with Client.local() as client:
        started = client.chats.start(workspace, "what is here?", agent="claude/MODEL")
        with client.chats.follow(started.workspace, started.slot) as turn:
            for message in turn:
                ...
        print(turn.answer)
        with client.chats.ask(started.chat, "and how is it tested?") as turn:
            print(turn.wait())
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self

from hmz.runtime import Refused

from . import Family

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from types import TracebackType

    from hmz.sdk.client import Client

    from . import Subscription

__all__ = [
    "Catalogue",
    "Chat",
    "Chats",
    "Entry",
    "Harness",
    "HarnessSession",
    "Held",
    "Listed",
    "Sessions",
    "Started",
    "Turn",
]

Prefer = Literal["native", "flow"]
Permission = Literal["read-only", "workspace-write", "danger-full-access"]

#: How long a call that follows or lets go of a host is given to be answered.
_ANSWERING = 30.0

#: How often a turn waited on looks up, to see whether the daemon is still there.
_LOOKING = 0.5

#: What a refusal is coded where the chat's host has folded away, or holds another already.
_CONFLICT = 409

#: And where no host holds the slot at all.
_GONE = 404

#: How long is waited between two looks at whether a host has let a chat go.
_PAUSE = 0.05

#: How a host's `gone` begins for a frontend that fell behind, which attaches again.
_BEHIND = "too far behind"


@dataclass(frozen=True)
class Chat:
    """One chat as it is written down: a chat row (Section 4.25.5.2 of daemon.md)."""

    id: str
    """Its name, which every method that takes `chat` takes."""
    title: str
    workspace: str
    """The workspace it is of, as an absolute path of the daemon's machine."""
    folderless: bool
    """Whether that workspace is a directory made for the chat alone."""
    workdir: str
    """Where its assistant works."""
    env: str
    """The env its assistant works in, as `-e` writes one after `<role>=`."""
    agent: str
    """Its assistant, as an agent spec."""
    model: str
    began: str
    updated: str
    state: str
    """`asking`, `turn`, `going`, `failed` or `resting` (Section 4.25.5.3 of daemon.md)."""
    slot: str
    """The slot of the host holding it, "" for none."""
    asking: tuple[str, ...]
    """The questions its assistant waits on mid-turn, each `<run>:<question>`."""
    permission: str
    archived: bool
    said: dict[str, Any]
    """Everything the daemon answered, the above included: `spent`, and of `get` the rest."""


@dataclass(frozen=True)
class Listed:
    """One page of the chats written down, newest begun first."""

    chats: tuple[Chat, ...]
    total: int
    """How many there are in all, this page and the others."""
    offset: int
    limit: int


@dataclass(frozen=True)
class Started:
    """A chat started or carried on: its name, and the host that holds it."""

    chat: str
    workspace: str
    slot: str


@dataclass(frozen=True)
class Held:
    """Where a chat is held: what `say`, `stop`, `set`, `move` and `commands` take."""

    workspace: str
    slot: str


@dataclass(frozen=True)
class Entry:
    """One thing a line of a chat can start with."""

    sigil: str
    """`/`, `$`, `!` or `@`."""
    name: str
    about: str
    how: str
    """How a native entry is served: `pass`, `call`, `emulate`, `refuse`; "" for the rest."""
    source: str
    """`native` for the harness's own, `hmz` for a name hmz keeps, `flow` for a flow."""


@dataclass(frozen=True)
class Catalogue:
    """What a chat's lines can start with, and how the chat is set."""

    entries: tuple[Entry, ...]
    prefer: str
    """What a `$` name both a native entry and a flow answer to runs: `native` or `flow`."""
    prefer_from: str
    """`chat` where the chat overrides the setting, `settings` otherwise."""
    permission: str | None
    """The chat's permission as last set; None for an Ai-chan conversation."""
    listed: bool
    """Whether the catalogue is all its harness lists, which it is once a turn was taken."""


@dataclass(frozen=True)
class HarnessSession:
    """One session a harness ran on its own in a workspace (Section 4.25.8.3 of daemon.md)."""

    id: str
    harness: str
    title: str
    workspace: str
    model: str
    began: str
    updated: str
    continuable: bool
    """Whether :meth:`Harness.adopt` can go on from it in a chat."""
    trace: Any = None
    """What was said in it, where it was asked for."""


@dataclass(frozen=True)
class Sessions:
    """One page of a workspace's harness sessions, last written first."""

    sessions: tuple[HarnessSession, ...]
    total: int
    offset: int
    limit: int


def _chat(said: Mapping[str, Any]) -> Chat:
    return Chat(
        id=str(said["id"]),
        title=str(said["title"]),
        workspace=str(said["workspace"]),
        folderless=bool(said["folderless"]),
        workdir=str(said["workdir"]),
        env=str(said["env"]),
        agent=str(said["agent"]),
        model=str(said["model"]),
        began=str(said["began"]),
        updated=str(said["updated"]),
        state=str(said["state"]),
        slot=str(said["slot"]),
        asking=tuple(str(one) for one in said["asking"]),
        permission=str(said["permission"]),
        archived=bool(said["archived"]),
        said=dict(said),
    )


def _session(said: Mapping[str, Any]) -> HarnessSession:
    return HarnessSession(
        id=str(said["id"]),
        harness=str(said["harness"]),
        title=str(said["title"]),
        workspace=str(said["workspace"]),
        model=str(said["model"]),
        began=str(said["began"]),
        updated=str(said["updated"]),
        continuable=bool(said["continuable"]),
        trace=said.get("trace"),
    )


class _Attached(Family):
    """What follows a host as a frontend, and so lets one go."""

    def _detaches(self, sub: str) -> None:
        """Lets a host go (`epic.detach`); one gone already, or a session ended, is let be."""
        try:
            self._call("epic.detach", sub=sub, wait=_ANSWERING)
        except (Refused, TimeoutError):
            return


def _taken(message: Mapping[str, Any]) -> list[str]:
    """The lines one message says were taken: as an answer, or into a turn that is open."""
    kind = message.get("type")
    texts: list[Any] = []
    if kind in ("answered", "said"):
        texts = [message.get("text")]
    elif kind == "waiting":
        given: list[dict[str, Any]] = message.get("given") or []
        texts = [one.get("text") for one in given]
    elif kind == "unheld":
        texts = list(message.get("texts") or [])
    return [str(text or "").strip() for text in texts]


class Turn(_Attached):
    """One turn of a chat, as its host tells it: iterated until the turn is done.

    Iterating yields each message the host sends (Section 4.9 of daemon.md) -- a history
    record, which carries `seq`, or a snapshot -- and ends once the chat is between turns
    again, or has ended, or its host has gone. What the turn came to is kept here as it is
    heard, so that it can be read while iterating and after. Closing it lets the host go as a
    frontend and leaves the chat as it is.
    """

    def __init__(
        self,
        client: Client,
        workspace: str,
        slot: str,
        *,
        replay: bool = True,
        line: str | None = None,
    ) -> None:
        """Attaches to a chat's host. Made by :meth:`Chats.follow` and :meth:`Chats.ask`.

        Args:
          client: The client the host is followed through.
          workspace: The chat's workspace.
          slot: The slot of the host holding it.
          replay: Whether what the host has said so far is heard first: so for a host just
            started, whose turn may be under way, and not for one that held the chat before
            the line this turn answers was said.
          line: The line this turn answers, where it is said to a host that held the chat
            already: nothing is kept of what the host says until it says that line was
            taken, so that a turn open before it is not heard as the one answering it.

        Raises:
          hmz.sdk.Refused: If the host has folded away or cannot be attached to.
        """
        self.workspace = workspace
        self.slot = slot
        self.answer: str | None = None
        """What the turn answered, as its last `result` says; None where none has."""
        self.failed = ""
        """What the harness said where the turn failed, "" where it did not."""
        self.notes: list[str] = []
        """What the chat said beside an answer: why a line was refused, that the conversation
        is a new one."""
        self.ended: tuple[str, str] | None = None
        """How the chat ended and why, where it did: `ended.how` and `ended.why`, or `gone`
        and what the host said as it let go."""
        self.done = False
        """Whether the turn was taken and the chat is between turns."""
        super().__init__(client)
        # Whether the line has been seen taken -- a turn going or answering, or the chat
        # asking for its next line: a `turn` of `done` before any is a chat whose turn has
        # not opened yet, not one whose turn is done.
        self._going = False
        self._state = ""
        self._line = None if line is None else line.strip()
        # Where the subscription has got to, to attach again from where it was left.
        self._since: dict[str, Any] | None = None
        self._told: Subscription | None = None
        self._attaches(replay=replay)

    def _attaches(self, *, replay: bool) -> None:
        self._listens()
        said = self._call(
            "epic.attach",
            workspace=self.workspace,
            slot=self.slot,
            replay=None if replay else False,
            since=None if self._since is None else dict(self._since),
            wait=_ANSWERING,
        )
        self._told = self._heard("epic.event", str(said["sub"]))

    def __iter__(self) -> Iterator[Mapping[str, Any]]:
        """Each message of the turn, until it is done or the chat has ended.

        Raises:
          ConnectionError: If the session with the daemon ended meanwhile.
          hmz.sdk.Refused: If the host let go of this for falling behind and could not be
            attached to again.
        """
        while not self.done and self.ended is None and self._told is not None:
            told = self._told.next(_LOOKING)
            if told is None:
                if self._client.wait(0):
                    raise ConnectionError("the session with the daemon ended")
                continue
            message: Any = told.get("message")
            if not isinstance(message, dict):
                continue
            behind = self._takes(message)  # pyright: ignore[reportUnknownArgumentType]
            yield message
            if behind:
                # The host ended the subscription; the next goes on from where it got to.
                self._told.close()
                self._attaches(replay=True)

    def wait(self) -> str | None:
        """Hears the turn out, and returns what it answered."""
        for _ in self:
            pass
        return self.answer

    def _takes(self, message: Mapping[str, Any]) -> bool:
        """Keeps what one message says of the turn; whether the host says to attach again."""
        kind, seq = message.get("type"), message.get("seq")
        if kind == "welcome":
            self._since = {"epoch": message.get("epoch"), "seq": 0}
        elif isinstance(seq, int) and self._since is not None:
            self._since["seq"] = seq
        if self._line is not None:
            # Whatever is said before the line is taken is of a turn before it.
            # An answer is taken whatever it is recorded as: the number of an option is
            # written down as the option.
            if kind == "answered" or self._line in _taken(message):
                self._line, self._going = None, True
            elif kind == "run":
                self._state = str(message.get("turn") or "")
        elif kind == "event":
            if message.get("kind") == "result":
                self._going = True
                self.answer = str(message.get("text") or "").strip()
                self._settles()
            elif message.get("kind") == "failed":
                self.failed = str(message.get("text") or "")
        elif kind == "asked" and message.get("mode") == "listen":
            # The chat asks for its next line, so the one it was said is taken, by a turn or
            # by none: a `!` command it ran, or a line it refused, which it says why of here
            # alone. Ahead of what a turn answered it says what only the conversation says.
            said = str(message.get("text") or "").strip()
            if self.answer is not None:
                said = said.removesuffix(self.answer).strip()
            elif self.failed:
                said = ""
            if said:
                self.notes.append(said)
            self._going = True
            self._settles()
        elif kind == "run":
            self._state = str(message.get("turn") or "")
            if self._state == "running":
                self._going = True
            self._settles()
        if kind == "ended":
            self.ended = (str(message.get("how") or ""), str(message.get("why") or ""))
        elif kind == "gone":
            why = str(message.get("why") or "")
            if why.startswith(_BEHIND):
                return True
            self.ended = ("gone", why)
        return False

    def _settles(self) -> None:
        if self._state == "done" and self._going:
            self.done = True

    def close(self) -> None:
        """Lets the host go as a frontend; the chat goes on as it is."""
        told, self._told = self._told, None
        if told is not None:
            # Let go first, so that nothing is said to a subscription nobody hears.
            self._detaches(told.sub)
            told.close()

    def __enter__(self) -> Self:
        """Follows the turn for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Lets the host go, however the block ended."""
        self.close()


class Harness(Family):
    """The sessions each harness ran on its own in a workspace (`chat.harness.*`)."""

    METHODS: ClassVar = ("chat.harness.list", "chat.harness.get", "chat.harness.adopt")

    def list(
        self, workspace: str, *, offset: int | None = None, limit: int | None = None
    ) -> Sessions:
        """The harness sessions of a workspace, last written first.

        Args:
          workspace: The workspace, as an absolute path of the daemon's machine.
          offset: How many to pass over, None for none.
          limit: How many at most, None for the daemon's 50; at most 200.
        """
        said = self._call(
            "chat.harness.list", workspace=workspace, offset=offset, limit=limit
        )
        return Sessions(
            tuple(_session(one) for one in said["sessions"]),
            int(said["total"]),
            int(said["offset"]),
            int(said["limit"]),
        )

    def get(
        self, workspace: str, harness: str, session: str, *, trace: bool | None = None
    ) -> HarnessSession:
        """One harness session, and with `trace` what was said in it.

        Raises:
          hmz.sdk.Refused: 404 if it is no harness session of the workspace.
        """
        return _session(
            self._call(
                "chat.harness.get",
                workspace=workspace,
                harness=harness,
                session=session,
                trace=trace,
            )
        )

    def adopt(
        self,
        workspace: str,
        harness: str,
        session: str,
        *,
        agent: str | None = None,
        idem: str | None = None,
    ) -> str:
        """Makes a chat that goes on from a copy of a harness session.

        Args:
          workspace: The workspace the session worked in.
          harness: The harness that kept it.
          session: The id its harness gave it.
          agent: An agent of that harness to go on with, None for the session's own model.
          idem: The key this is done once under.

        Returns:
          The new chat's name.

        Raises:
          hmz.sdk.Refused: 409 if a session of that harness cannot be continued.
        """
        said = self._call(
            "chat.harness.adopt",
            workspace=workspace,
            harness=harness,
            session=session,
            agent=agent,
            idem=idem,
        )
        return str(said["chat"])


class Chats(_Attached):
    """Chats, and the sessions a harness ran on its own."""

    METHODS: ClassVar = (
        "chat.start",
        "chat.say",
        "chat.commands",
        "chat.set",
        "chat.move",
        "chat.stop",
        "chat.list",
        "chat.get",
        "chat.rename",
        "chat.agent",
        "chat.fork",
        "chat.archive",
        "chat.unarchive",
        "chat.backup",
        "chat.delete",
        *Harness.METHODS,
    )

    @property
    def harness(self) -> Harness:
        """The sessions each harness ran on its own, which a chat can go on from."""
        return Harness(self._client)

    def start(
        self,
        workspace: str | None,
        task: str,
        *,
        agent: str | None = None,
        resume: str | None = None,
        prefer: Prefer | None = None,
        permission: Permission | None = None,
        worktree: bool | None = None,
        env: str | None = None,
        remember: bool | None = None,
        slot: str = "chat:",
        idem: str | None = None,
    ) -> Started:
        """Starts a chat on a host of its own, or carries one on.

        Args:
          workspace: The workspace, as an absolute path of the daemon's machine; None for
            no folder, where the daemon makes a directory for the chat alone.
          task: Its first message, or the one that carries it on; empty only with `resume`,
            which carries the chat on with nothing said.
          agent: Its assistant, as an agent spec; with `resume`, None for the chat's own.
          resume: The name of a chat of the workspace to carry on.
          prefer: What a `$` name both a native entry and a flow answer to runs.
          permission: What its assistant may change, None for `workspace-write` or, with
            `resume`, what the chat records.
          worktree: Whether its assistant works in a new git worktree of the workspace.
          env: The env its assistant works in, as `-e` writes one after `<role>=`; with
            `resume`, where the chat is carried on, which moves it.
          remember: Whether `agent` is written as the workspace's chat agent.
          slot: The chat slot it is started on, `chat:` alone for a new one.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: As Section 4.25.1 of daemon.md states.
        """
        sub = None
        if workspace is None:
            # A directory made for the chat alone, with a chat's host of its own there,
            # which the chat then starts on.
            self._listens()
            made = self._call(
                "epic.attach", slot=slot, scratch=True, replay=False, wait=_ANSWERING
            )
            workspace, slot, sub = (
                str(made["workspace"]),
                str(made["slot"]),
                made["sub"],
            )
        try:
            said = self._call(
                "chat.start",
                workspace=workspace,
                slot=slot,
                agent=agent,
                task=task,
                resume=resume,
                prefer=prefer,
                permission=permission,
                worktree=worktree,
                env=env,
                remember=remember,
                idem=idem,
            )
        finally:
            if sub is not None:
                # Nothing of that host is heard here: whoever follows the chat attaches.
                self._detaches(str(sub))
                self._heard("epic.event", str(sub)).close()
        return Started(str(said["chat"]), workspace, str(said["slot"]))

    def hold(self, chat: str) -> Held:
        """Where a chat is held, carried on with nothing said where no host holds it.

        What `say`, `stop`, `set`, `move` and `commands` take is a workspace and a slot,
        and a chat nobody talks to has no slot. This gives it one: its host then stands by
        between turns, and folds away again if nothing is said.

        Args:
          chat: The chat's name.

        Raises:
          hmz.sdk.Refused: 404 if there is no such chat.
        """
        one = self.get(chat)
        if one.slot:
            return Held(one.workspace, one.slot)
        started = self.start(one.workspace, "", resume=chat)
        return Held(started.workspace, started.slot)

    def say(
        self, workspace: str, slot: str, text: str, *, idem: str | None = None
    ) -> None:
        """Says the next line of a chat where it is held; an empty line ends it there.

        Raises:
          hmz.sdk.Refused: 400 for a line the frontend serves, 404 where no host holds the
            slot, 409 where the chat has folded away.
        """
        self._call("chat.say", workspace=workspace, slot=slot, text=text, idem=idem)

    def rest(self, chat: str, *, seconds: float = 10.0) -> bool:
        """Ends a chat on the host that holds it, and waits for that host to let it go.

        An empty line ends a chat where it is held (Section 8.4.7 of core.md); the chat is
        then carried on by whoever next says something to it. For a program that has heard
        the turn it asked for and will say no more.

        Args:
          chat: The chat's name.
          seconds: How long the host is given to let go.

        Returns:
          Whether no host holds the chat now.

        Raises:
          hmz.sdk.Refused: 404 if there is no such chat.
        """
        import time

        one = self.get(chat)
        if one.slot:
            try:
                self.say(one.workspace, one.slot, "")
            except Refused as why:
                # Folded away already, which is what was wanted of it.
                if why.code not in (_CONFLICT, _GONE):
                    raise
        until = time.monotonic() + seconds
        while one.slot and time.monotonic() < until:
            time.sleep(_PAUSE)
            one = self.get(chat)
        return not one.slot

    def follow(
        self,
        workspace: str,
        slot: str,
        *,
        replay: bool = True,
        line: str | None = None,
    ) -> Turn:
        """Follows the host that holds a chat, to hear its turn as it is taken.

        Args:
          workspace: The chat's workspace.
          slot: The slot of the host holding it.
          replay: Whether what the host has said so far is heard first. Right for a host
            :meth:`start` just started; wrong for one a line is about to be said to, whose
            last turn would be heard as this one.
          line: The line about to be said to that host, which the turn heard is then the
            one that takes.

        Raises:
          hmz.sdk.Refused: 409 if the host has folded away.
        """
        return Turn(self._client, workspace, slot, replay=replay, line=line)

    def ask(self, chat: str, text: str, *, idem: str | None = None) -> Turn:
        """Says a line to a chat by its name, and follows the turn that answers it.

        The chat is held first (:meth:`hold`), so that the line is said to a host either
        way, and what the daemon refuses of a line it refuses of this one.

        Args:
          chat: The chat's name.
          text: The line, which says something.
          idem: The key the line is said once under.

        Returns:
          The turn, to iterate or :meth:`Turn.wait` on.

        Raises:
          hmz.sdk.Refused: 404 if there is no such chat, and as `chat.say` refuses.
        """
        for again in (True, False):
            held = self.hold(chat)
            try:
                turn = self.follow(held.workspace, held.slot, replay=False, line=text)
            except Refused as why:
                # Folded away since it was read: held again, once.
                if again and why.code == _CONFLICT:
                    continue
                raise
            try:
                self.say(held.workspace, held.slot, text, idem=idem)
            except Refused as why:
                turn.close()
                if again and why.code == _CONFLICT:
                    continue
                raise
            return turn
        raise AssertionError("unreachable")

    def commands(self, workspace: str, slot: str) -> Catalogue:
        """What the lines of a chat can start with, and its preference and permission."""
        said = self._call("chat.commands", workspace=workspace, slot=slot)
        return Catalogue(
            tuple(
                Entry(
                    str(one["sigil"]),
                    str(one["name"]),
                    str(one["about"]),
                    str(one["how"]),
                    str(one["source"]),
                )
                for one in said["entries"]
            ),
            str(said["prefer"]),
            str(said["prefer_from"]),
            None if said["permission"] is None else str(said["permission"]),
            bool(said["listed"]),
        )

    def set(
        self,
        workspace: str,
        slot: str,
        *,
        prefer: Prefer | None = None,
        permission: Permission | None = None,
        idem: str | None = None,
    ) -> None:
        """Overrides a chat's preference for `$` names, or sets its permission.

        The permission holds from the chat's next turn.

        Raises:
          hmz.sdk.Refused: 400 where neither is given or one is not a value it takes.
        """
        self._call(
            "chat.set",
            workspace=workspace,
            slot=slot,
            prefer=prefer,
            permission=permission,
            idem=idem,
        )

    def move(
        self, workspace: str, slot: str, env: str, *, idem: str | None = None
    ) -> str:
        """Moves a chat to another env, between turns.

        Args:
          workspace: The chat's workspace.
          slot: The slot of the host holding it.
          env: The env, as `-e` writes one after `<role>=`.
          idem: The key this is done once under.

        Returns:
          Where the chat works from then on, written likewise.

        Raises:
          hmz.sdk.Refused: 409 while a turn is open, or where the env cannot be reached.
        """
        said = self._call(
            "chat.move", workspace=workspace, slot=slot, env=env, idem=idem
        )
        return str(said["env"])

    def stop(self, workspace: str, slot: str, *, idem: str | None = None) -> None:
        """Stops a chat's open turn, leaving the chat between turns.

        Raises:
          hmz.sdk.Refused: 409 while no turn is open.
        """
        self._call("chat.stop", workspace=workspace, slot=slot, idem=idem)

    def list(
        self,
        *,
        workspace: str | None = None,
        archived: bool | None = None,
        q: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> Listed:
        """The chats written down, newest begun first.

        Args:
          workspace: Only that workspace's chats, None for every workspace's.
          archived: True for the archived chats alone; otherwise those not archived.
          q: Text found in the title, the first message or the name.
          offset: How many to pass over, None for none.
          limit: How many at most, None for the daemon's 50; at most 200.
        """
        said = self._call(
            "chat.list",
            workspace=workspace,
            archived=archived,
            q=q,
            offset=offset,
            limit=limit,
        )
        return Listed(
            tuple(_chat(one) for one in said["chats"]),
            int(said["total"]),
            int(said["offset"]),
            int(said["limit"]),
        )

    def get(self, chat: str, *, trace: bool | None = None) -> Chat:
        """One chat, whole; with `trace`, what was said in it, as `said["trace"]`.

        Raises:
          hmz.sdk.Refused: 404 if there is no such chat.
        """
        return _chat(self._call("chat.get", chat=chat, trace=trace))

    def rename(self, chat: str, title: str, *, idem: str | None = None) -> Chat:
        """Changes a chat's title, and returns the chat as it then is."""
        return _chat(self._call("chat.rename", chat=chat, title=title, idem=idem))

    def agent(self, chat: str, agent: str, *, idem: str | None = None) -> Chat:
        """Carries a chat on with another model or effort of its own harness and account.

        Raises:
          hmz.sdk.Refused: 409 for an agent of another harness or account.
        """
        return _chat(self._call("chat.agent", chat=chat, agent=agent, idem=idem))

    def fork(self, chat: str, *, idem: str | None = None) -> str:
        """Makes a chat that goes on from a copy of this one's conversation so far.

        Returns:
          The new chat's name.

        Raises:
          hmz.sdk.Refused: 409 while the chat's turn is open.
        """
        return str(self._call("chat.fork", chat=chat, idem=idem)["chat"])

    def archive(self, chat: str, *, idem: str | None = None) -> Chat:
        """Archives a chat, which hides it from the list."""
        return _chat(self._call("chat.archive", chat=chat, idem=idem))

    def unarchive(self, chat: str, *, idem: str | None = None) -> Chat:
        """Puts an archived chat back in the list."""
        return _chat(self._call("chat.unarchive", chat=chat, idem=idem))

    def backup(
        self,
        chat: str,
        *,
        to: Sequence[str] | None = None,
        idem: str | None = None,
    ) -> list[str]:
        """Backs a chat up, queued and not waited on.

        Args:
          chat: The chat's name.
          to: The names of the targets, None for those the chat was started with.
          idem: The key this is done once under.

        Returns:
          The targets it was queued for.

        Raises:
          hmz.sdk.Refused: 400 for a target that is none, 409 where there is no target.
        """
        said = self._call(
            "chat.backup", chat=chat, to=None if to is None else list(to), idem=idem
        )
        return [str(one) for one in said["queued"]]

    def delete(self, chat: str, *, idem: str | None = None) -> None:
        """Removes a chat and the sessions it kept, for good.

        Raises:
          hmz.sdk.Refused: 409 while the chat's turn is open.
        """
        self._call("chat.delete", chat=chat, idem=idem)

    def remembered(self, workspace: str) -> str:
        """The chat agent a workspace remembers (`settings.get`), "" where it has none."""
        said = self._call("settings.get", workspace=workspace)
        return str(said.get("chat") or "")
