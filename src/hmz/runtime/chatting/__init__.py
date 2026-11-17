"""Chats: one person talking to one coding agent, in one conversation, with no flow around it.

A chat is its own kind of epic (Section 8 of [CORE]), beside the epics flows run. It has one
assistant agent, one conversation, one workspace on this machine, and nothing else: no params,
no budget, no outworlder. What the person says is the next turn; what the assistant answers is
shown to them; a question it stops to ask mid-turn is put to them and their next line answers
it. The first turn is the one allowed to fail out loud, and ends the chat failed; a later one
that fails is said in the conversation and the chat goes on.

A chat takes the input its harness takes natively (Section 8.9 of [CORE]): what a line typed in
a chat means is :func:`resolve`'s answer, from the harness's catalog
(:class:`hmz.coganchor.agents.native.NativeCommand`), the names hmz keeps for itself
(:data:`RESERVED`), the flows installed here, and the chat's preference for a `$` name that is
both a native skill and a flow.

This module is the contract the rest of hmz is written against. :class:`Chat` is what a chat
host runs; its body is filled in by the chat runner's own change, and until then it raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from pathlib import Path

    from hmz.coganchor.agents.native import NativeCommand

#: What `$<name>` means where it names both a native skill and a flow.
Prefer = Literal["native", "flow"]

#: The `/` commands every frontend keeps for hmz in a chat (Section 8.9 of [CORE]). Those the
#: harnesses also have -- `clear`, `resume`, `exit`, `quit`, `btw` -- do in a chat what the
#: harness's own command of that name does.
RESERVED: frozenset[str] = frozenset(
    {
        "btw",
        "chat",
        "clear",
        "epics",
        "exit",
        "flow",
        "prefer",
        "quit",
        "resume",
        "settings",
    }
)


@dataclass(frozen=True, slots=True)
class Resolved:
    """What one line typed in a chat is.

    Attributes:
      kind: `reserved`, an hmz command (`name` is which); `flow`, a flow to start (`name`
        is which, `rest` its task); `native`, the harness's own input, served as `entry`
        says; `refused`, input the chat cannot take, `why` saying why; `prose`, words said
        to the assistant.
      name: The command, flow or native name, where there is one.
      rest: What follows the name.
      entry: The catalog entry a `native` line is served by.
      why: Why a `refused` line was refused.
    """

    kind: Literal["reserved", "flow", "native", "refused", "prose"]
    name: str = ""
    rest: str = ""
    entry: NativeCommand | None = None
    why: str = ""


def resolve(
    line: str,
    *,
    catalog: Sequence[NativeCommand],
    flows: Collection[str],
    prefer: Prefer,
) -> Resolved:
    """Reads one line typed in a chat as Section 8.9 of [CORE] says to.

    Args:
      line: The line, stripped.
      catalog: The harness's native catalog for the conversation, empty for none.
      flows: The names a flow can be named by here, as a `$` line names one.
      prefer: The chat's preference, which decides a `$` name that is both.

    Returns:
      What the line is.
    """
    if not line or line[0] not in "/$!@":
        return Resolved("prose")
    sigil, body = line[0], line[1:]
    name, _, rest = body.partition(" ")
    rest = rest.strip()
    if sigil == "/" and name in RESERVED:
        return Resolved("reserved", name, rest)
    if sigil in "!@":
        entry = next((e for e in catalog if e.sigil == sigil), None)
        if entry is None:
            return Resolved("prose")
        if entry.how == "refuse":
            return Resolved("refused", "", body, entry, entry.about)
        return Resolved("native", "", body, entry)
    entry = next((e for e in catalog if e.sigil == sigil and e.name == name), None)
    if sigil == "$":
        flow = name in flows
        if entry is not None and (not flow or prefer == "native"):
            return Resolved("native", name, rest, entry)
        if flow:
            return Resolved("flow", name, rest)
        return Resolved("prose")
    if entry is not None:
        if entry.how == "refuse":
            return Resolved(
                "refused",
                name,
                rest,
                entry,
                f"/{name} is served only by the harness's own interactive interface",
            )
        return Resolved("native", name, rest, entry)
    if any(e.sigil == "/" for e in catalog):
        return Resolved("refused", name, rest, None, f"no such command: /{name}")
    return Resolved("prose")


@dataclass(frozen=True, slots=True)
class ChatSpec:
    """What a chat is started with.

    Attributes:
      workspace: The workspace it is had in, on this machine.
      agent: The assistant, as `-a` spells an agent (`claude/MODEL:high`).
      task: The first message.
      resume: The epic directory of a chat to carry on, or None for a new one.
      prefer: This chat's own preference, or None to go by the person's setting.
    """

    workspace: Path
    agent: str
    task: str
    resume: Path | None = None
    prefer: Prefer | None = None


@dataclass(frozen=True, slots=True)
class ChatEnd:
    """How a chat ended.

    Attributes:
      epic: Its epic directory.
      state: `stopped`, or `failed` where its first turn failed.
      why: What the harness said, for a chat that failed.
    """

    epic: Path
    state: Literal["stopped", "failed"]
    why: str = ""


class Person(Protocol):
    """The person a chat is had with, as the host that holds it reaches them."""

    async def next(self, answered: str) -> str:
        """Shows the assistant's answer and waits for the next message; "" ends the chat."""
        ...

    async def ask(self, question: str, options: Sequence[str]) -> str | None:
        """Puts a question the assistant asked mid-turn; None where nobody answers it."""
        ...

    def shell(self, command: str, out: str, err: str, status: int) -> None:
        """Shows a `!` command run for the chat, with what it printed."""
        ...


class Chat:
    """One chat, as the host that holds it runs it.

    The contract, which the chat runner fills in:

    - :meth:`run` takes the first turn from `spec.task` and every later one from
      :meth:`Person.next`, until that answers "" or the host goes away.
    - A line the person says is read by :func:`resolve`; a `native` one is taken as a turn
      marked native (`TurnRequest(native=True)`), except a `!` line the catalog says to
      emulate, which is run in the workspace under the assistant's confinement, shown with
      :meth:`Person.shell`, and carried into the next turn as `<bash-input>`,
      `<bash-stdout>` and `<bash-stderr>` blocks ahead of its message.
    - The conversation is kept in the epic as it stands when the chat ends, and a chat
      carried on (`spec.resume`) goes on in the same epic and the same conversation, or says
      why it cannot and goes on in a new one.
    - The epic record says `kind: chat`, and `prefer` where this chat has its own.
    """

    def __init__(self, spec: ChatSpec, *, person: Person) -> None:
        """Sets a chat up; nothing is started until :meth:`run`.

        Args:
          spec: What it is started with.
          person: Who it is had with.
        """
        self.spec = spec
        self.person = person
        self._prefer: Prefer | None = spec.prefer

    @property
    def prefer(self) -> Prefer | None:
        """This chat's own preference, or None where it goes by the person's setting."""
        return self._prefer

    def prefers(self, prefer: Prefer) -> None:
        """Sets this chat's own preference, recorded in its epic.

        Args:
          prefer: What `$<name>` means here where it names both.
        """
        raise NotImplementedError

    def natives(self) -> list[NativeCommand]:
        """The assistant's native catalog, as its conversation stands; empty before it opens."""
        raise NotImplementedError

    async def run(self) -> ChatEnd:
        """Has the chat, from its first message to its last.

        Returns:
          How it ended.

        Raises:
          HarnessError: Where the first turn of a chat that is not carried on fails, with what
            the harness said; the epic is ended failed first.
        """
        raise NotImplementedError
