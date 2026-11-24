"""`hmz btw`: side questions asked of a session of an epic or a chat, and what they opened."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from hmz.cli.tree import WORKSPACE, Arg, Command, Example, Field, table, workspace
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call
    from hmz.sdk.families.btw import Aside

__all__ = ["COMMANDS"]

_EPIC = Arg(
    ("--epic",),
    "the epic the side questions are about, by its name; when not given, the epic in "
    "view in the workspace",
    metavar="NAME",
)
_CHAT = Arg(
    ("--chat",),
    "the chat the side questions are about, by its name, in place of `--epic`",
    metavar="NAME",
)

_ANSWERED = (
    Field("said[].question", "string", "one question that was asked"),
    Field("said[].answer", "string", "the answer to that question"),
)


def _about(call: Call) -> tuple[str | None, str | None]:
    """The epic or the chat a line is about.

    Raises:
      hmz.sdk.Refused: If it names both.
    """
    from hmz.sdk import Refused

    if call.epic is not None and call.chat is not None:
        raise Refused(t("Give `--epic` or `--chat`, not both."))
    return call.epic, call.chat


def _said(aside: Aside) -> list[dict[str, str]]:
    return [{"question": one.question, "answer": one.answer} for one in aside.said]


def _ask(call: Call) -> None:
    from hmz.sdk import Refused

    epic, chat = _about(call)
    to: str | None = call.to
    if to is None and call.aside is not None:
        # A side conversation goes on with the session its first question named.
        asides = call.client.btw.list(workspace(call), epic=epic, chat=chat)
        to = next((one.to for one in asides if one.aside == call.aside), None)
    if to is None:
        # A chat is one conversation, asked about as that: the last it opened.
        if call.chat is None:
            raise Refused(t("Pick the conversation to ask first."))
        sessions = call.client.btw.sessions(chat=call.chat)
        if not sessions:
            raise Refused(t("This chat has said nothing to ask about yet."))
        to = sessions[-1].key
    answer = call.client.btw.ask(
        workspace(call), call.question, to=to, aside=call.aside, epic=epic, chat=chat
    )
    call.answers(
        {
            "aside": answer.aside,
            "to": answer.to,
            "question": answer.question,
            "answer": answer.answer,
        },
        [answer.answer],
    )
    if call.aside is None and not call.json:
        said = t(
            "Side conversation {name}: pass `--aside {name}` to ask the next question "
            "in it.",
            name=answer.aside,
        )
        print(said, file=sys.stderr)


def _sessions(call: Call) -> None:
    from hmz.sdk import Refused

    epic, chat = _about(call)
    if epic is None and chat is None:
        raise Refused(t("Name an epic with `--epic` or a chat with `--chat`."))
    sessions = call.client.btw.sessions(epic=epic, chat=chat)
    call.answers(
        {
            "sessions": [
                {"session": one.key, "agent": one.agent, "harness": one.harness}
                for one in sessions
            ]
        },
        table([[one.key, one.harness] for one in sessions]),
    )


def _list(call: Call) -> None:
    epic, chat = _about(call)
    asides = call.client.btw.list(workspace(call), epic=epic, chat=chat)
    call.answers(
        {
            "asides": [
                {
                    "aside": one.aside,
                    "to": one.to,
                    "question": one.question,
                    "said": _said(one),
                }
                for one in asides
            ]
        },
        table(
            [[one.aside, one.to, str(len(one.said)), one.question] for one in asides]
        ),
    )


def _show(call: Call) -> None:
    from hmz.sdk import Refused

    epic, chat = _about(call)
    asides = call.client.btw.list(workspace(call), epic=epic, chat=chat)
    found = next((one for one in asides if one.aside == call.aside), None)
    if found is None:
        raise Refused(t("There is no side conversation {name}.", name=call.aside))
    lines: list[str] = []
    for one in found.said:
        lines.extend([f"> {one.question}", one.answer, ""])
    call.answers(
        {
            "aside": found.aside,
            "to": found.to,
            "question": found.question,
            "said": _said(found),
        },
        lines[:-1],
    )


def _leave(call: Call) -> None:
    from hmz.sdk import Refused

    aside: str | None = call.aside or None
    if (aside is None) != bool(call.all):
        raise Refused(t("Name one side conversation or give `--all`."))
    call.client.btw.leave(workspace(call), aside)
    document: dict[str, Any] = {"aside": aside}
    call.answers(document, [t("Closed.")])


COMMANDS = (
    Command(
        "btw",
        "ask side questions of a session of an epic or chat",
        says="A side question asks one session of an epic or a chat about itself. A "
        "read-only copy of that session answers in a side conversation, so the question "
        "never reaches the epic or the chat. These commands ask one, list the side "
        "conversations that are open, and close them.",
        commands=(
            Command(
                "ask",
                "ask a side question and print the answer",
                says="The first question opens a side conversation and prints its name on "
                "standard error; give that name as `--aside` to ask the next question in "
                "the same side conversation. Without `--epic` or `--chat` the question is "
                "about the epic in view in the workspace.",
                args=(
                    Arg(("question",), "the question to ask"),
                    Arg(
                        ("--to",),
                        "the session to ask, written `<agent>/<n>` as `hmz btw sessions` "
                        "prints it; with `--chat` and no `--to`, the chat's newest "
                        "session is asked",
                        metavar="SESSION",
                    ),
                    Arg(
                        ("--aside",),
                        "the side conversation to go on in, by its name; when not given, "
                        "a new side conversation is opened",
                        metavar="NAME",
                    ),
                    WORKSPACE,
                    _EPIC,
                    _CHAT,
                ),
                examples=(
                    Example(
                        'hmz btw ask "What are you changing right now?" --to Ada/1',
                        "asks session Ada/1 of the epic in view in this folder a side "
                        "question",
                    ),
                    Example(
                        'hmz btw ask "Why did the tests fail?" '
                        "--chat 20261117T100000-ab12cd",
                        "asks the newest session of that chat a side question",
                    ),
                    Example(
                        'hmz btw ask "And after that?" --to Ada/1 --aside 3f9c2a1b',
                        "asks the next question in the side conversation named 3f9c2a1b",
                    ),
                ),
                prints="Prints the answer on standard output, and the name of a side "
                "conversation it opened on standard error.",
                output=(
                    Field(
                        "aside",
                        "string",
                        "the name of the side conversation it was asked in",
                    ),
                    Field(
                        "to", "string", "the session that was asked, as `<agent>/<n>`"
                    ),
                    Field("question", "string", "the question that was asked"),
                    Field("answer", "string", "the answer the session's copy gave"),
                ),
                methods=("btw.ask", "btw.list", "chat.get"),
                see=("btw sessions", "btw list", "btw leave"),
                run=_ask,
            ),
            Command(
                "sessions",
                "list the sessions of an epic or a chat",
                args=(
                    Arg(
                        ("--epic",),
                        "the epic whose sessions are listed, by its name",
                        metavar="NAME",
                    ),
                    Arg(
                        ("--chat",),
                        "the chat whose sessions are listed, by its name",
                        metavar="NAME",
                    ),
                ),
                examples=(
                    Example(
                        "hmz btw sessions --epic 20261117T100000.000Z-ab12cd",
                        "lists the sessions of that epic, oldest first",
                    ),
                    Example(
                        "hmz btw sessions --chat 20261117T100000-ab12cd --json "
                        "| jq -r '.sessions[-1].session'",
                        "prints the newest session of that chat",
                    ),
                ),
                prints="Prints one line per session, oldest first: the session as `--to` "
                "takes it, and its harness.",
                output=(
                    Field("sessions", "list", "the sessions, oldest first"),
                    Field(
                        "sessions[].session",
                        "string",
                        "the session as `--to` takes it, `<agent>/<n>`",
                    ),
                    Field(
                        "sessions[].agent",
                        "string",
                        "the name of the agent whose session it is",
                    ),
                    Field(
                        "sessions[].harness",
                        "string",
                        "the harness that ran the session",
                    ),
                ),
                methods=("runs.get", "chat.get"),
                see=("btw ask",),
                run=_sessions,
            ),
            Command(
                "list",
                "list the side conversations open about an epic or chat",
                args=(WORKSPACE, _EPIC, _CHAT),
                examples=(
                    Example(
                        "hmz btw list",
                        "lists the side conversations open about the epic in view in "
                        "this folder",
                    ),
                    Example(
                        "hmz btw list --chat 20261117T100000-ab12cd --json",
                        "lists the side conversations open about that chat, as JSON",
                    ),
                ),
                prints="Prints one line per side conversation, in the order opened: its "
                "name, the session it asks, how many questions it has answered, and the "
                "question it is answering now.",
                output=(
                    Field(
                        "asides",
                        "list",
                        "the side conversations open, in the order opened",
                    ),
                    Field(
                        "asides[].aside", "string", "the name of the side conversation"
                    ),
                    Field("asides[].to", "string", "the session it asks"),
                    Field(
                        "asides[].question",
                        "string",
                        "the question it is answering now, empty when it is answering "
                        "none",
                    ),
                    Field(
                        "asides[].said",
                        "list",
                        "the questions it has answered, oldest first, each with "
                        "`question` and `answer`",
                    ),
                ),
                methods=("btw.list",),
                see=("btw show", "btw ask", "btw leave"),
                run=_list,
            ),
            Command(
                "show",
                "print the questions and answers of one side conversation",
                args=(
                    Arg(
                        ("aside",),
                        "the name of the side conversation, as `hmz btw list` prints it",
                    ),
                    WORKSPACE,
                    _EPIC,
                    _CHAT,
                ),
                examples=(
                    Example(
                        "hmz btw show 3f9c2a1b",
                        "prints every side question asked in side conversation 3f9c2a1b "
                        "and its answer",
                    ),
                    Example(
                        "hmz btw show 3f9c2a1b --json | jq -r '.said[-1].answer'",
                        "prints the latest answer of side conversation 3f9c2a1b",
                    ),
                ),
                prints="Prints each question on a line starting with `>`, followed by its "
                "answer, oldest first.",
                output=(
                    Field("aside", "string", "the name of the side conversation"),
                    Field("to", "string", "the session it asks"),
                    Field(
                        "question",
                        "string",
                        "the question it is answering now, empty when it is answering "
                        "none",
                    ),
                    Field("said", "list", "the questions answered in it, oldest first"),
                    *_ANSWERED,
                ),
                methods=("btw.list",),
                see=("btw list", "btw ask"),
                run=_show,
            ),
            Command(
                "leave",
                "close one side conversation, or every one in the workspace",
                args=(
                    Arg(
                        ("aside",),
                        "the name of the side conversation to close; left out with "
                        "`--all`",
                        default="",
                    ),
                    Arg(("--all",), "close every side conversation of the workspace"),
                    WORKSPACE,
                ),
                examples=(
                    Example(
                        "hmz btw leave 3f9c2a1b",
                        "closes the side conversation named 3f9c2a1b",
                    ),
                    Example(
                        "hmz btw leave --all -w ~/project",
                        "closes every side conversation of the workspace ~/project",
                    ),
                ),
                prints="Prints that it was closed.",
                output=(
                    Field(
                        "aside",
                        "string|null",
                        "the name of the side conversation closed, or null when every "
                        "one was closed",
                    ),
                ),
                methods=("btw.leave",),
                see=("btw list",),
                run=_leave,
            ),
        ),
    ),
)
