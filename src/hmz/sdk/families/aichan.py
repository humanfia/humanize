"""Ai-chan's conversations (`aichan.*`).

A conversation is made, listed, renamed and forgotten by `aichan.*`. Once made it is a chat
on a host of its own slot, and is talked to as any host is: attached to (`epic.attach`,
which carries a conversation folded away on), answered where she waits on a person
(`epic.answer`) or said into her open turn (`epic.say`), stopped (`epic.stop`), and let go
(`epic.detach`). :meth:`AiChan.say`, :meth:`AiChan.heard` and :meth:`AiChan.stop` are those
calls, made in that order (Section 4.22.5 of daemon.md).
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

__all__ = ["AiChan", "Conversation", "Made", "Reply"]

#: How often her host is asked how it stands while something of hers is waited for.
_LOOK = 0.25


@dataclass(frozen=True)
class Conversation:
    """One Ai-chan conversation, as `aichan.list` answers it."""

    id: int
    """Its number, which names it."""
    title: str
    """Its title: the first line it was made with, until it is renamed."""
    scope: str
    """What she reaches: `daemon`, `workspace` or `epic`."""
    workspace: str
    """The workspace of its host."""
    epic: str
    """The epic of an `epic` scope, else ""."""
    nous: str
    """The nous she thinks with."""
    preset: str
    """What she may do: `read-only` or `danger-full-access`."""
    slot: str
    """The slot of its host, `ai:<hex>`."""
    state: str
    """`running` while her turn is open, `waiting` between turns, `folded` with no host."""
    created: str
    """When it was made, `YYYY-MM-DDTHH:MM:SSZ`."""
    latest: str
    """The start of what was last said in it."""
    updated: str
    """When that was said, as `created` is written."""


@dataclass(frozen=True)
class Made:
    """A conversation just made."""

    id: int
    """Its number."""
    workspace: str
    """The workspace of its host."""
    slot: str
    """The slot of its host."""


@dataclass(frozen=True)
class Reply:
    """What Ai-chan waits on a person with."""

    text: str
    """What she said."""
    mode: str
    """`listen` where her turn is over and she waits for the next line; anything else is a
    question of hers mid-turn, which the next line said answers."""


class AiChan(Family):
    """Ai-chan's conversations."""

    METHODS: ClassVar = (
        "aichan.create",
        "aichan.list",
        "aichan.rename",
        "aichan.forget",
    )

    def create(
        self,
        task: str,
        *,
        scope: str = "daemon",
        workspace: str | None = None,
        epic: str | None = None,
        nous: str | None = None,
        preset: str | None = None,
        idem: str | None = None,
    ) -> Made:
        """Makes a conversation and starts its host, with `task` as its first message.

        Args:
          task: What she is told first; its first line is the conversation's title.
          scope: What she reaches: `daemon`, `workspace` or `epic`.
          workspace: The workspace of a `workspace` or `epic` scope.
          epic: The epic's name, of an `epic` scope.
          nous: The nous she thinks with, None for the one the last conversation was made
            with.
          preset: `read-only` or `danger-full-access`, None for `read-only`.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 400 for a scope, workspace, epic, nous, preset or task said
            wrongly, 404 for an epic not run in that workspace, 409 where her host refuses.
        """
        said = self._call(
            "aichan.create",
            scope=scope,
            workspace=workspace,
            epic=epic,
            nous=nous,
            preset=preset,
            task=task,
            idem=idem,
        )
        return Made(int(said["id"]), str(said["workspace"]), str(said["slot"]))

    def list(self) -> list[Conversation]:
        """Every conversation, newest first. Starts no host."""
        return [
            Conversation(
                int(one["id"]),
                *(
                    # What the daemon has nothing to say of is "", not the word for it.
                    str(one.get(name) or "")
                    for name in (
                        "title",
                        "scope",
                        "workspace",
                        "epic",
                        "nous",
                        "preset",
                        "slot",
                        "state",
                        "created",
                        "latest",
                        "updated",
                    )
                ),
            )
            for one in self._call("aichan.list")["conversations"]
        ]

    def get(self, id: int) -> Conversation:  # noqa: A002 -- the daemon's name for it
        """One conversation, by its number.

        Raises:
          hmz.sdk.Refused: 404 where there is none.
        """
        for one in self.list():
            if one.id == id:
                return one
        from hmz.runtime import Refused

        raise Refused(f"There is no Ai-chan #{id}.", code=404)

    def rename(self, id: int, title: str, *, idem: str | None = None) -> None:  # noqa: A002
        """Gives a conversation another title, whether or not a host holds it.

        Raises:
          hmz.sdk.Refused: 400 for a title of white space alone, 404 for no conversation.
        """
        self._call("aichan.rename", id=id, title=title, idem=idem)

    def forget(self, id: int, *, idem: str | None = None) -> None:  # noqa: A002
        """Forgets a conversation for good, closing its host where one holds it.

        Raises:
          hmz.sdk.Refused: 404 where there is none.
        """
        self._call("aichan.forget", id=id, idem=idem)

    @contextlib.contextmanager
    def _attached(self, one: Conversation) -> Generator[str]:
        """Her host attached to as one frontend, for as long as the block runs."""
        # What the host tells this frontend is read off its status instead: listened for
        # and taken up only so that a client that keeps what it is told does not keep this
        # for good. A client with a listener of its own keeps nothing, and hears it there.
        with contextlib.suppress(RuntimeError):
            self._listens()
        sub = str(
            self._call(
                "epic.attach", workspace=one.workspace, slot=one.slot, replay=False
            )["sub"]
        )
        told = None
        with contextlib.suppress(RuntimeError):
            told = self._heard("epic.event", sub)
        try:
            yield sub
        finally:
            from hmz.runtime import Refused

            # Gone already where her host went, or the session did.
            with contextlib.suppress(Refused, OSError, TimeoutError):
                self._call("epic.detach", sub=sub, wait=10)
            if told is not None:
                told.close()

    def _waited(
        self, sub: str, deadline: float | None, *, after: frozenset[str] = frozenset()
    ) -> tuple[Mapping[str, Any] | None, Mapping[str, Any]]:
        """What she waits on a person with, and how her host stands, once there is either.

        Returns:
          The first question waiting that is none of `after` -- or None where her turn is
          open and nothing new waits -- and the status it was read from. With `after` empty
          this returns as soon as her host says which it is; otherwise only a new question
          ends the wait.

        Raises:
          hmz.sdk.Refused: 409 where her chat is over, which nothing carries on.
          TimeoutError: If the deadline passed.
        """
        from hmz.runtime import Refused

        while True:
            left = None if deadline is None else max(deadline - time.monotonic(), 1.0)
            status = self._call("epic.status", sub=sub, wait=left)
            for one in status.get("pending") or ():
                if str(one["question"]) not in after:
                    return one, status
            turning = status.get("turn") == "running"
            if turning and not after:
                return None, status
            ended: Mapping[str, Any] = status.get("ended") or {}
            # Over however it ended -- failed, crashed, refused: no turn is open, she waits
            # on nobody, and nothing said to her would be heard. A turn stopped is not that:
            # she waits again after it.
            over = ended.get("how") not in (None, "", "stopped")
            if not turning and not status.get("pending") and over:
                why = str(ended.get("why") or "")
                raise Refused(
                    why or "This conversation failed. Start a new one.", code=409
                )
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Ai-chan did not answer in time")
            time.sleep(_LOOK)

    def say(
        self,
        id: int,  # noqa: A002
        text: str,
        *,
        hear: bool = True,
        wait: float | None = None,
    ) -> Reply | None:
        """Says a line to her, and returns what she answers it with.

        The line answers what she waits on -- her wait between turns, or a question of hers
        mid-turn -- and is said into her turn where she waits on nothing. A conversation
        folded away is carried on first.

        Args:
          id: The conversation.
          text: The line.
          hear: Whether to wait for what she says to it.
          wait: How many seconds the whole of it may take, None for as long as it takes.

        Returns:
          What she then waits on a person with, or None where `hear` is false.

        Raises:
          hmz.sdk.Refused: 404 for no conversation, 409 where her chat failed or her host
            refuses the line.
          TimeoutError: If she did not answer within `wait`.
        """
        deadline = None if wait is None else time.monotonic() + wait
        with self._attached(self.get(id)) as sub:
            waiting, status = self._waited(sub, deadline)
            before = frozenset(
                str(one["question"]) for one in status.get("pending") or ()
            )
            if waiting is None:
                self._call("epic.say", sub=sub, text=text)
            else:
                self._call(
                    "epic.answer", sub=sub, question=str(waiting["question"]), text=text
                )
            if not hear:
                return None
            said, _ = self._waited(sub, deadline, after=before or frozenset({""}))
            assert said is not None  # noqa: S101 -- only a new question ends that wait
            return Reply(str(said.get("text") or ""), str(said.get("mode") or ""))

    def heard(self, id: int, *, wait: float | None = None) -> Reply:  # noqa: A002
        """What she waits on a person with, waited for while her turn is open.

        A conversation folded away is carried on, which is how what she said last is read.

        Raises:
          hmz.sdk.Refused: 404 for no conversation, 409 where her chat failed.
          TimeoutError: If her turn did not end within `wait`.
        """
        deadline = None if wait is None else time.monotonic() + wait
        with self._attached(self.get(id)) as sub:
            said, _ = self._waited(sub, deadline, after=frozenset({""}))
            assert said is not None  # noqa: S101 -- only a question ends that wait
            return Reply(str(said.get("text") or ""), str(said.get("mode") or ""))

    def stop(self, id: int) -> None:  # noqa: A002
        """Stops her open turn, leaving the conversation between turns.

        Raises:
          hmz.sdk.Refused: 404 for no conversation, 409 while she is not answering.
        """
        one = self.get(id)
        if one.state == "folded":
            from hmz.runtime import Refused

            # No host holds it, and attaching would start one only to be told the same.
            raise Refused(
                "Ai-chan is not answering, so there is nothing to stop", code=409
            )
        with self._attached(one) as sub:
            self._call("epic.stop", sub=sub)
