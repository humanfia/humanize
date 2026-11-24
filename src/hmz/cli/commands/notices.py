"""`hmz notices`: what a daemon tells its person, listed and followed as it is said."""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from dataclasses import asdict
from typing import TYPE_CHECKING, Final

from hmz.cli.tree import DONE, Arg, Command, Example, Exit, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call
    from hmz.sdk.families.notices import Notice

__all__ = ["COMMANDS"]

#: What `hmz notices follow` ends with once it is interrupted: 128 and the signal's number.
INTERRUPTED: Final = 130

#: Every kind of notice (Section 4.19.1.1 of daemon.md), and what the page calls each.
_KINDS: Final = {
    "done": "Done",
    "failed": "Failed",
    "stopped": "Stopped",
    "asked": "Question",
    "listening": "Waiting",
}

#: What Markdown opens a line with -- a fence, a heading, a quote, a list -- which says nothing.
_OPENS = re.compile(r"^\s*(?:(?:```|~~~).*|(?:#{1,6}|>|[-*+]|\d+[.)])(?:\s+|$))+")

_KIND = Arg(
    ("--kind",),
    "print only notices of this kind",
    metavar="KIND",
    choices=tuple(_KINDS),
    many=True,
)


def _fields(under: str) -> tuple[Field, ...]:
    """The fields of one notice, each named under where a document holds it."""
    return (
        Field(
            f"{under}id",
            "integer",
            "its number, greater than that of every earlier notice",
        ),
        Field(
            f"{under}kind",
            "string",
            "`done`, `failed`, `stopped`, `asked` or `listening`",
        ),
        Field(f"{under}workspace", "string", "the workspace of the host it is about"),
        Field(f"{under}slot", "string", "the slot of that host"),
        Field(
            f"{under}epic",
            "string",
            "the name of the epic it is about, empty for a chat",
        ),
        Field(
            f"{under}chat",
            "string",
            "the name of the chat it is about, empty for an epic",
        ),
        Field(f"{under}flow", "string", "the epic's flow, `chat` for a chat"),
        Field(f"{under}task", "string", "the epic's task, or the chat's first message"),
        Field(f"{under}role", "string", "the role a question is asked of, else empty"),
        Field(
            f"{under}text",
            "string",
            "what it says: the question, the reply, or why it failed",
        ),
        Field(f"{under}at", "number", "when it was made, seconds since the Unix epoch"),
    )


def _line(text: str) -> str:
    """What a text says in one line: the first of its lines that says anything."""
    for line in text.split("\n"):
        said = _OPENS.sub("", line).strip()
        if any(letter.isalnum() for letter in said):
            return said
    return ""


def _row(notice: Notice) -> list[str]:
    """A notice as its line's columns: number, when, kind, what it is of, what it says."""
    when = datetime.datetime.fromtimestamp(notice.at).astimezone()
    return [
        str(notice.id),
        f"{when:%Y-%m-%d %H:%M:%S}",
        t(_KINDS.get(notice.kind, notice.kind)),
        notice.chat or notice.epic,
        _line(notice.text) or _line(notice.task),
    ]


def _wanted(call: Call, notice: Notice) -> bool:
    return not call.kind or notice.kind in call.kind


def _list(call: Call) -> None:
    # The newest there is, whichever were asked for: where following takes up from.
    listed, last = call.client.notices.kept(call.after)
    notices = [one for one in listed if _wanted(call, one)]
    call.answers(
        {"notices": [asdict(one) for one in notices], "last": last},
        table([_row(one) for one in notices]),
    )


def _follow(call: Call) -> int:
    try:
        for notice in call.client.notices.follow(call.after):
            if not _wanted(call, notice):
                continue
            said = (
                json.dumps(asdict(notice), ensure_ascii=False)
                if call.json
                else "  ".join(_row(notice)).rstrip()
            )
            # At once: whoever reads a pipe is waiting for this line, not for a full buffer.
            print(said, flush=True)
    except KeyboardInterrupt:
        return INTERRUPTED
    except BrokenPipeError:
        # Whoever read the lines has gone, and so has anything left to say to it.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return DONE


COMMANDS = (
    Command(
        "notices",
        "list and follow what this daemon tells you about your epics and chats",
        says="The daemon makes a notice when an epic or a chat is done, fails, is "
        "stopped, asks you a question, or waits for what to say next. Each notice has a "
        "number greater than every earlier one. These commands list the notices kept and "
        "follow new ones as they arrive.",
        commands=(
            Command(
                "list",
                "list the notices the daemon keeps, oldest first",
                args=(
                    Arg(
                        ("--after",),
                        "list only the notices after the one with this number",
                        metavar="ID",
                        kind=int,
                    ),
                    _KIND,
                ),
                examples=(
                    Example(
                        "hmz notices list", "lists the latest notices, oldest first"
                    ),
                    Example(
                        "hmz notices list --after 41 --kind failed --kind asked --json",
                        "lists, as JSON, what failed or asked a question since notice 41",
                    ),
                ),
                prints="Prints one line per notice, oldest first: its number, the local "
                "time, its kind, the chat or epic it is about, and what it says.",
                output=(
                    Field(
                        "notices",
                        "list",
                        "the notices, oldest first, at most the latest 200",
                    ),
                    *_fields("notices[]."),
                    Field(
                        "last",
                        "integer",
                        "the number of the newest notice the daemon has made, 0 when "
                        "there is none; `hmz notices follow --after` takes it",
                    ),
                ),
                methods=("notices.list",),
                see=("notices follow",),
                run=_list,
            ),
            Command(
                "follow",
                "print each notice as it arrives, until interrupted",
                says="Prints one line for each notice as the daemon makes it and runs "
                "until you press ctrl+c. With `--after` it first prints the notices kept "
                "after that number. With `--json` each notice is one JSON object on a "
                "line of its own.",
                args=(
                    Arg(
                        ("--after",),
                        "first print the notices kept after the one with this number; "
                        "when not given, only notices made from now on are printed",
                        metavar="ID",
                        kind=int,
                    ),
                    _KIND,
                ),
                examples=(
                    Example("hmz notices follow", "prints each notice as it arrives"),
                    Example(
                        "hmz notices follow --kind asked --json | jq -r .text",
                        "prints each question an epic asks you, as it is asked",
                    ),
                    Example(
                        'hmz notices follow --after "$(hmz notices list --json '
                        '| jq .last)"',
                        "follows on from the newest notice, missing none made in between",
                    ),
                ),
                prints="Prints one line per notice as it arrives: its number, the local "
                "time, its kind, the chat or epic it is about, and what it says. With "
                "`--json`, prints one object per line instead.",
                output=_fields(""),
                exits=(Exit(INTERRUPTED, "interrupted with ctrl+c"),),
                methods=("notices.subscribe", "notices.unsubscribe"),
                see=("notices list",),
                run=_follow,
            ),
        ),
    ),
)
