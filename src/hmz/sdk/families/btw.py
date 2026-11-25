"""Side questions asked beside an epic or a chat (`btw.*`).

A side question is asked of one session of an epic or a chat, in a side conversation that
copies the session and never reaches it (Section 9 of core.md). The daemon keeps each side
conversation under the name its first question gave it, per workspace, until it is left.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Answer", "Aside", "Session", "SideQuestions"]


@dataclass(frozen=True)
class Answer:
    """One side question, answered."""

    aside: str
    """The side conversation it was asked in."""
    to: str
    """The session asked, as `<agent>/<n>`."""
    question: str
    """What was asked."""
    answer: str
    """What the session's side copy said."""


@dataclass(frozen=True)
class Aside:
    """One side conversation the daemon holds open."""

    aside: str
    """Its name, as the question that opened it gave it."""
    to: str
    """The session it asks, as `<agent>/<n>`."""
    question: str
    """The question it is answering now, "" for none."""
    said: tuple[Answer, ...]
    """Every question answered in it, oldest first, the latest 200."""


@dataclass(frozen=True)
class Session:
    """One session of an epic or a chat, which a side question can be asked of."""

    key: str
    """What it is asked as: `<agent>/<n>`, the agent's name and which of its sessions."""
    agent: str
    """The agent's name."""
    harness: str
    """The harness that ran it."""


def _answer(said: Mapping[str, Any]) -> Answer:
    return Answer(
        str(said["aside"]), str(said["to"]), str(said["question"]), str(said["answer"])
    )


class SideQuestions(Family):
    """Side questions asked beside an epic or a chat."""

    METHODS: ClassVar = ("btw.list", "btw.ask", "btw.leave")

    def list(
        self, workspace: str, *, epic: str | None = None, chat: str | None = None
    ) -> list[Aside]:
        """The side conversations open about an epic, or about a chat, in the order opened.

        Args:
          workspace: The workspace, an absolute path of the daemon's machine.
          epic: The epic's name, None for the epic in view on the workspace's own host.
          chat: A chat's name, in place of `epic`.
        """
        said = self._call("btw.list", workspace=workspace, epic=epic, chat=chat)
        return [
            Aside(
                str(one["aside"]),
                str(one["to"]),
                str(one.get("question") or ""),
                tuple(_answer(each) for each in one.get("said") or ()),
            )
            for one in said["asides"]
        ]

    def sessions(
        self, *, epic: str | None = None, chat: str | None = None
    ) -> list[Session]:
        """The sessions of an epic or a chat written down, oldest first, each as it is asked.

        Read from `runs.get` for an epic and `chat.get` for a chat, and keyed as the epic
        going keyed them: an agent's sessions counted from 1 in the order it opened them.

        Args:
          epic: The epic's name.
          chat: The chat's name, in place of `epic`.

        Raises:
          ValueError: Unless exactly one of the two is named.
          hmz.sdk.Refused: 404 where there is no such epic or chat.
        """
        if (epic is None) == (chat is None):
            raise ValueError("name an epic or a chat, and not both")
        if chat is not None:
            said = self._call("chat.get", chat=chat)
        else:
            said = self._call("runs.get", name=epic)
        counted: dict[str, int] = {}
        found: list[Session] = []
        for one in said.get("sessions") or ():
            agent = str(one["agent"])
            counted[agent] = counted.get(agent, 0) + 1
            found.append(
                Session(
                    f"{agent}/{counted[agent]}", agent, str(one.get("backend") or "")
                )
            )
        return found

    def ask(
        self,
        workspace: str,
        question: str,
        *,
        to: str,
        aside: str | None = None,
        epic: str | None = None,
        chat: str | None = None,
        wait: float | None = None,
    ) -> Answer:
        """Asks a side question of one session, and returns its answer.

        The first question to an `aside` opens a side conversation on `to`; every later one
        goes on in it, of that session and epic whatever this is given.

        Args:
          workspace: The workspace, an absolute path of the daemon's machine.
          question: What to ask.
          to: The session asked, as `<agent>/<n>`.
          aside: The side conversation, None for a new one, named here.
          epic: The epic it is about, None for the epic in view on the workspace's own host.
          chat: The chat it is about, in place of `epic`.
          wait: How many seconds the answer is waited for, None for as long as it takes.

        Raises:
          hmz.sdk.Refused: 400 for a `to` that names no session, 404 for a session the epic
            did not open, 409 while the side conversation still answers, 502 for no answer.
          TimeoutError: If no answer came within `wait`.
        """
        return _answer(
            self._call(
                "btw.ask",
                workspace=workspace,
                question=question,
                aside=uuid.uuid4().hex[:8] if aside is None else aside,
                to=to,
                epic=epic,
                chat=chat,
                wait=wait,
            )
        )

    def leave(self, workspace: str, aside: str | None = None) -> None:
        """Closes one side conversation of a workspace, or every one.

        Args:
          workspace: The workspace, an absolute path of the daemon's machine.
          aside: The side conversation, None for every one of the workspace.
        """
        self._call("btw.leave", workspace=workspace, aside=aside)
