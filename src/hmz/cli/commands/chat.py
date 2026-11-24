"""`hmz chat`: chats with an agent, started, said to and managed from a command line.

    id=$(hmz chat start --json -a claude/MODEL:high "what is here?" | jq -r .chat)
    hmz chat say "$id" "and how is it tested?"
    hmz chat list
    hmz chat rename "$id" "the tests"

A chat is one conversation with one assistant (Section 8 of core.md), written down by the
daemon under an id and held, while anybody talks to it, by a host of its own. `start` and
`say` each take one turn of one: the line is said, the host is followed as one more frontend
until the chat is between turns again, and what the turn answered is printed -- drawn as
`hmz exec` draws a turn, by the same :class:`hmz.cli.output.Shown`, for a person; as one
JSON document, or a line a record, for a program. A host one of them started is ended once
its turn is done, since nobody is at a prompt to say the next line; the chat is carried on
by the next `say`.

A signal leaves the chat to its host rather than stopping its turn (Section 15.3 of cli.md).

Everything else is one call of `chat.*` (Section 4.25 of daemon.md), named for it. What the
daemon takes by workspace and slot -- `stop`, `set`, `move`, `commands` -- takes the chat's
id here as everything else does, and a chat no host holds is carried on with nothing said
to be given one.
"""

from __future__ import annotations

import contextlib
import json
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.cli.tree import REFUSED, Arg, Command, Example, Exit, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence

    from hmz.cli.output import Out, Shown
    from hmz.cli.tree import Call
    from hmz.sdk.families.chats import Chat, HarnessSession, Started, Turn

__all__ = ["COMMANDS"]

#: How much of a title a listing shows, on its one line.
_TITLE = 60

_PERMISSIONS = ("read-only", "workspace-write", "danger-full-access")
_PREFERS = ("native", "flow")

#: What a call is refused with where the session with the daemon has ended.
_WENT = 503

#: What `show` prints of a chat, a line apiece, in this order: each a field of its document.
_SHOWN = (
    "id", "title", "state", "agent", "model", "permission", "env", "workdir", "workspace",
    "began", "updated", "archived", "slot", "prefer", "forked", "adopted", "task",
)  # fmt: skip

#: And of a harness session.
_SESSION = (
    "id", "harness", "title", "workspace", "model", "began", "updated", "continuable",
)  # fmt: skip


class _Left(BaseException):
    """A signal, taken while a chat is followed: leave it to its host, and exit as it says."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


@contextlib.contextmanager
def _leaving() -> Generator[list[int]]:
    """Leaves the chat to its host on an interrupt, a terminate or a hangup.

    Raised from the signal's own frame, which is this thread waiting on the turn or a call:
    there is nothing to unwind but this process's session, which closing lets go of, and the
    chat goes on without it (Section 15.3.3 of cli.md).

    Yields:
      Where the signal that ended it is written, once one has.
    """

    def leaves(signum: int, _frame: object) -> None:
        raise _Left(signum)

    was: dict[int, Any] = {}
    for one in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        with contextlib.suppress(ValueError):  # off the main thread, where none reaches
            # A signal somebody chose to have ignored stays so, as it does for `hmz exec`.
            if signal.getsignal(one) != signal.SIG_IGN:
                was[one] = signal.signal(one, leaves)
    left: list[int] = []
    try:
        yield left
    except _Left as signalled:
        left.append(signalled.signum)
    finally:
        for one, before in was.items():
            signal.signal(one, signal.SIG_DFL if before is None else before)


def _folder(given: str | None) -> str:
    """A workspace as the daemon knows it by: the whole path, a `~` left for it to expand."""
    if given and given.startswith("~"):
        return given
    return str(Path(given or ".").resolve())


def _line(chat: Chat) -> list[str]:
    """One chat as the cells of its line: its id, its state and its title."""
    title = " ".join(chat.title.split())
    title = title if len(title) <= _TITLE else f"{title[: _TITLE - 1]}…"
    return [chat.id, chat.state, title]


def _row(call: Call, chat: Chat) -> None:
    """Answers with one chat as it then is: its row, or its line."""
    call.answers(chat.said, table([_line(chat)]))


def _fields(said: Mapping[str, Any], names: Sequence[str]) -> list[list[str]]:
    """What a document says under each name, a row apiece, the ones saying nothing left out."""
    rows: list[list[str]] = []
    for name in names:
        value = said.get(name)
        if value in (None, "", [], {}):
            continue
        shown = json.dumps(value) if isinstance(value, (bool, list, dict)) else value
        rows.append([name, " ".join(str(shown).split())])
    return rows


def _traced(trace: Any) -> list[str]:
    """What each session of a trace said and did, a line an action."""
    lines: list[str] = []
    sessions: list[dict[str, Any]] = (
        cast("list[dict[str, Any]]", trace) if isinstance(trace, list) else []
    )
    for session in sessions:
        lines.extend(["", f"{session.get('agent') or ''}  {session.get('key') or ''}"])
        actions: list[dict[str, Any]] = session.get("actions") or []
        lines.extend(
            f"  {' '.join(str(action.get('name') or '').split())}" for action in actions
        )
    return lines


def _shell(out: Out, record: Mapping[str, Any]) -> None:
    """Shows a `!` command run for the chat as a shell would: its output on stdout.

    The command, what it wrote as errors and how it exited where that was not well are drawn
    on stderr, where the turn is.
    """
    out.line(("! ", "yellow"), (str(record.get("command") or ""), ""))
    if said := str(record.get("out") or "").rstrip("\n"):
        out.answer(said)
    if err := str(record.get("err") or "").rstrip("\n"):
        out.line((err, "red"))
    status = record.get("status")
    if isinstance(status, int) and status:
        out.line((f"exit {status}", "dim"))


def _draws(out: Out, shown: Shown, message: Mapping[str, Any]) -> None:
    """Draws one message of a chat's host, as `hmz exec` draws an epic's."""
    kind = message.get("type")
    if kind == "event":
        shown.heard(
            str(message.get("agent")), message.get("session") or None, dict(message)
        )
    elif kind == "opened":
        from hmz.sdk.running import Opened

        shown.opened(
            str(message.get("role") or ""),
            Opened(
                key=str(message.get("key") or ""),
                role=str(message.get("role") or ""),
                agent=str(message.get("agent") or ""),
                cli=str(message.get("cli") or ""),
                model=str(message.get("model") or ""),
                person=bool(message.get("person")),
                env=message.get("env"),
                harness=str(message.get("harness") or ""),
            ),
        )
    elif kind == "notice":
        out.aside(str(message.get("text") or ""))
    elif kind == "printed":
        out.printed(str(message.get("text") or ""))
    elif kind == "shell":
        _shell(out, message)


def _hears(call: Call, turn: Turn) -> None:
    """Hears a turn out, saying it as it goes in whichever way was asked for."""
    if call.events:
        for message in turn:
            # A history record, which a snapshot of the host's state is not, nor the mark
            # between what was replayed and what is said as it happens.
            if isinstance(message.get("seq"), int) and message.get("type") != "live":
                print(json.dumps(message, ensure_ascii=False), flush=True)
        return
    if call.json:
        turn.wait()
        return
    from hmz.cli.output import Out, Shown

    with Out() as out, Shown(out) as shown:
        noted = 0
        for message in turn:
            _draws(out, shown, message)
            for note in turn.notes[noted:]:
                out.aside(note)
            noted = len(turn.notes)


def _answers(call: Call, started: Started, turn: Turn | None) -> int | None:
    """Says how a turn went, or that none was waited for, and answers the exit status."""
    said = {"chat": started.chat, "workspace": started.workspace, "slot": started.slot}
    if turn is None:
        call.answers(
            {**said, "answer": "", "notes": [], "detached": True}, [started.chat]
        )
        return None
    how, why = turn.ended or ("", "")
    if turn.failed or how in ("failed", "crashed", "gone"):
        # A turn that failed is said in the conversation and the chat goes on (Section
        # 8.4.10 of core.md), but it is still the one turn this was asked for.
        message = turn.failed or why or t("The turn failed.")
        if call.json:
            error = {"code": 0, "message": message}
            print(json.dumps({"error": error, **said}, ensure_ascii=False))
        else:
            print(f"hmz {' '.join(call.path)}: {message}", file=sys.stderr)
        return REFUSED
    call.answers(
        {**said, "answer": turn.answer or "", "notes": turn.notes, "detached": False}
    )
    return None


def _ends(call: Call, started: Started, turn: Turn) -> None:
    """Ends a host this command started, once its turn is done.

    The chat is between turns and nobody is here to say the next message, so the next
    message is the empty one that ends it (Section 8.4.8 of core.md) -- waited on, so that
    the next command finds the chat at rest rather than on a host that is going. The turn
    is what was asked for, so a chat that folded away meanwhile is no failure.
    """
    from hmz.sdk import Refused

    if turn.done:
        with contextlib.suppress(Refused, TimeoutError):
            call.client.chats.rest(started.chat)


@contextlib.contextmanager
def _reached() -> Generator[None]:
    """Says a session that ended under a call as what it is: a daemon not reached."""
    from hmz.sdk import Refused

    try:
        yield
    except Refused as why:
        if why.code != _WENT:
            raise
        raise ConnectionError(str(why)) from why


def _start(call: Call) -> int | None:
    from hmz.sdk import Refused

    # A line a record is a program's reading too: what ends it is the document.
    call.json = call.json or call.events
    if call.no_folder and call.worktree:
        raise Refused(t("A worktree needs a folder"))
    code = None
    with _leaving() as left, _reached():
        chats = call.client.chats
        workspace = None if call.no_folder else _folder(call.workspace)
        agent = call.agent or (chats.remembered(workspace) if workspace else "")
        if not agent:
            raise Refused(
                t("No agent is remembered for this folder; name one with `-a`.")
            )
        started = chats.start(
            workspace,
            call.message,
            agent=agent,
            env=call.env,
            permission=call.permission,
            prefer=call.prefer,
            worktree=call.worktree or None,
            remember=call.remember or None,
        )
        if call.detach:
            return _answers(call, started, None)
        if not call.json:
            # The id it is carried on by, and listed by: on standard error, as the turn is.
            print(t("Chat {id}", id=started.chat), file=sys.stderr)
        with chats.follow(started.workspace, started.slot) as turn:
            _hears(call, turn)
        # Said before the host is ended, which what the turn came to does not wait on.
        code = _answers(call, started, turn)
        _ends(call, started, turn)
    return 128 + left[0] if left else code


def _say(call: Call) -> int | None:
    from hmz.sdk import Refused
    from hmz.sdk.families.chats import Started

    call.json = call.json or call.events
    if not call.message.strip():
        raise Refused(t("The message is empty; a turn starts with something said."))
    code = None
    with _leaving() as left, _reached():
        chats = call.client.chats
        if call.detach:
            held = chats.hold(call.chat)
            chats.say(held.workspace, held.slot, call.message)
            said = Started(call.chat, held.workspace, held.slot)
            return _answers(call, said, None)
        # A host that held the chat already is somebody else's to end; one this starts is not.
        ours = not chats.get(call.chat).slot
        with chats.ask(call.chat, call.message) as turn:
            _hears(call, turn)
        started = Started(call.chat, turn.workspace, turn.slot)
        code = _answers(call, started, turn)
        if ours:
            _ends(call, started, turn)
    return 128 + left[0] if left else code


def _list(call: Call) -> None:
    listed = call.client.chats.list(
        workspace=None if call.all else _folder(call.workspace),
        archived=call.archived or None,
        q=call.search,
        offset=call.offset,
        limit=call.limit,
    )
    call.answers(
        {
            "chats": [one.said for one in listed.chats],
            "total": listed.total,
            "offset": listed.offset,
            "limit": listed.limit,
        },
        table([_line(one) for one in listed.chats]),
    )


def _show(call: Call) -> None:
    chat = call.client.chats.get(call.chat, trace=call.trace or None)
    lines = table(_fields(chat.said, _SHOWN))
    call.answers(chat.said, [*lines, *_traced(chat.said.get("trace"))])


def _rename(call: Call) -> None:
    _row(call, call.client.chats.rename(call.chat, call.title))


def _archive(call: Call) -> None:
    _row(call, call.client.chats.archive(call.chat))


def _unarchive(call: Call) -> None:
    _row(call, call.client.chats.unarchive(call.chat))


def _agent(call: Call) -> None:
    _row(call, call.client.chats.agent(call.chat, call.agent))


def _fork(call: Call) -> None:
    forked = call.client.chats.fork(call.chat)
    call.answers({"chat": forked}, [forked])


def _delete(call: Call) -> None:
    from hmz.sdk import Refused

    chats = call.client.chats
    if not call.yes:
        # Never asked of anything but somebody at a terminal: a line read off a pipe is not
        # a yes, and a program reading one document is not somebody to ask.
        if call.json or not sys.stdin.isatty():
            raise Refused(t("Nobody is at a terminal to ask; pass `--yes` to delete."))
        named = "  ".join(_line(chats.get(call.chat)))
        question, warning = (
            t("Delete {name}?", name=named),
            t("It cannot be brought back."),
        )
        print(f"{question} {warning} [y/N] ", end="", file=sys.stderr, flush=True)
        if sys.stdin.readline().strip().lower() not in ("y", "yes"):
            raise Refused(t("Chat {id} was not deleted.", id=call.chat))
    chats.delete(call.chat)
    call.answers({"deleted": call.chat})


def _stop(call: Call) -> None:
    chats = call.client.chats
    held = chats.hold(call.chat)
    chats.stop(held.workspace, held.slot)
    call.answers({"stopped": call.chat}, [t("Stopped")])


def _set(call: Call) -> None:
    chats = call.client.chats
    held = chats.hold(call.chat)
    chats.set(held.workspace, held.slot, prefer=call.prefer, permission=call.permission)
    now = chats.commands(held.workspace, held.slot)
    said = {
        "chat": call.chat,
        "permission": now.permission,
        "prefer": now.prefer,
        "prefer_from": now.prefer_from,
    }
    call.answers(said, table(_fields(said, ("permission", "prefer", "prefer_from"))))


def _move(call: Call) -> None:
    chats = call.client.chats
    chat = chats.get(call.chat)
    if chat.slot:
        env = chats.move(chat.workspace, chat.slot, call.env)
    else:
        # Carried on there, which is the move: where it worked may be out of reach by now.
        chats.start(chat.workspace, "", resume=call.chat, env=call.env)
        env = chats.get(call.chat).env
    call.answers({"chat": call.chat, "env": env}, [env])


def _commands(call: Call) -> None:
    chats = call.client.chats
    held = chats.hold(call.chat)
    found = chats.commands(held.workspace, held.slot)
    call.answers(
        {
            "entries": [
                {
                    "sigil": one.sigil,
                    "name": one.name,
                    "about": one.about,
                    "how": one.how,
                    "source": one.source,
                }
                for one in found.entries
            ],
            "prefer": found.prefer,
            "prefer_from": found.prefer_from,
            "permission": found.permission,
            "listed": found.listed,
        },
        table(
            [
                [f"{one.sigil}{one.name}", one.source, " ".join(one.about.split())]
                for one in found.entries
            ]
        ),
    )


def _backup(call: Call) -> None:
    queued = call.client.chats.backup(call.chat, to=call.to)
    call.answers({"queued": queued}, queued)


def _session(one: HarnessSession) -> dict[str, Any]:
    said: dict[str, Any] = {
        "id": one.id,
        "harness": one.harness,
        "title": one.title,
        "workspace": one.workspace,
        "model": one.model,
        "began": one.began,
        "updated": one.updated,
        "continuable": one.continuable,
    }
    if one.trace is not None:
        said["trace"] = one.trace
    return said


def _harness_list(call: Call) -> None:
    found = call.client.chats.harness.list(
        _folder(call.workspace), offset=call.offset, limit=call.limit
    )
    rows: list[list[str]] = []
    for one in found.sessions:
        title = " ".join(one.title.split())
        title = title if len(title) <= _TITLE else f"{title[: _TITLE - 1]}…"
        rows.append([one.harness, one.id, one.updated, title])
    call.answers(
        {
            "sessions": [_session(one) for one in found.sessions],
            "total": found.total,
            "offset": found.offset,
            "limit": found.limit,
        },
        table(rows),
    )


def _harness_show(call: Call) -> None:
    one = call.client.chats.harness.get(
        _folder(call.workspace), call.harness, call.session, trace=call.trace or None
    )
    said = _session(one)
    call.answers(said, [*table(_fields(said, _SESSION)), *_traced(one.trace)])


def _harness_adopt(call: Call) -> None:
    chat = call.client.chats.harness.adopt(
        _folder(call.workspace), call.harness, call.session, agent=call.agent
    )
    call.answers({"chat": chat}, [chat])


_CHAT = Arg(("chat",), "the chat's id, as `hmz chat list` prints it")
_LIMIT = Arg(("--limit",), "how many to list at most, up to 200", metavar="N", kind=int)
_OFFSET = Arg(("--offset",), "how many of the newest to skip", metavar="N", kind=int)
_DETACH = Arg(
    ("--detach",),
    "return as soon as the message is sent, without waiting for "
    "the answer; read the answer later with `hmz chat show`",
)
_EVENTS = Arg(
    ("--events",),
    "print each record of the turn as one JSON object per line "
    "while it happens, and the final JSON document as the last "
    "line",
)
_PREFER = Arg(
    ("--prefer",),
    "which one a `$name` line runs when both a skill of the "
    "harness (`native`) and a flow (`flow`) have that name",
    choices=_PREFERS,
)
_HARNESS = Arg(
    ("harness",),
    "the harness that ran the session, as `hmz chat harness list` prints it",
)
_SESSION_ID = Arg(
    ("session",), "the harness session's id, as `hmz chat harness list` prints it"
)
_HARNESS_FOLDER = Arg(
    ("-w", "--workspace"),
    "the folder the harness sessions worked in; when not given, the current folder",
    metavar="DIR",
)

#: The signals `start` and `say` are ended by, as the statuses they then exit with.
_SIGNALS = (
    Exit(129, "a hangup (SIGHUP) ended the command; the chat goes on in the daemon"),
    Exit(
        130,
        "an interrupt (ctrl+c, SIGINT) ended the command; the chat "
        "goes on in the daemon",
    ),
    Exit(
        143,
        "a termination signal (SIGTERM) ended the command; the chat "
        "goes on in the daemon",
    ),
)

#: The document `start` and `say` print.
_TURN = (
    Field(
        "chat",
        "string",
        "the chat's id, which the other `hmz chat` commands take; "
        "also present beside `error` when the turn failed",
    ),
    Field("workspace", "string", "the folder the chat is of, as an absolute path"),
    Field("slot", "string", "the slot of the host that holds the chat"),
    Field("answer", "string", "what the agent answered; empty with `--detach`"),
    Field(
        "notes",
        "list",
        "what the chat said beside the answer, such as why it refused the message",
    ),
    Field(
        "detached",
        "boolean",
        "whether the command returned without waiting for the answer",
    ),
)


def _chat_fields(under: str = "") -> tuple[Field, ...]:
    """The fields of a chat row, as they are named under a place in a document."""
    return (
        Field(f"{under}id", "string", "the chat's id"),
        Field(f"{under}title", "string", "the chat's title"),
        Field(
            f"{under}state",
            "string",
            "`turn` while the agent works, `asking` while it waits for an"
            " answer, `going` while a host holds the chat between turns, "
            "`failed`, or `resting`",
        ),
        Field(
            f"{under}agent",
            "string",
            "the chat's agent, written HARNESS[@ACCOUNT]/MODEL[:EFFORT]",
        ),
        Field(f"{under}model", "string", "the model the agent runs"),
        Field(
            f"{under}permission",
            "string",
            "what the agent may change: `read-only`, `workspace-write` or"
            " `danger-full-access`",
        ),
        Field(
            f"{under}env",
            "string",
            "the environment the agent works in, written BACKEND[@RUNTIME][/DIRECTORY]",
        ),
        Field(f"{under}workdir", "string", "the directory the agent works in"),
        Field(
            f"{under}workspace",
            "string",
            "the folder the chat is of, as an absolute path",
        ),
        Field(f"{under}folderless", "boolean", "whether the chat is of no folder"),
        Field(
            f"{under}slot",
            "string",
            "the slot of the host that holds the chat, empty when none does",
        ),
        Field(f"{under}asking", "list", "the questions the agent asked and waits on"),
        Field(f"{under}began", "string", "when the chat started, ISO 8601"),
        Field(f"{under}updated", "string", "when the chat was last written, ISO 8601"),
        Field(f"{under}archived", "boolean", "whether the chat is archived"),
        Field(
            f"{under}spent",
            "object",
            "what the chat has used: tokens, and cost where priced",
        ),
    )


def _session_fields(under: str = "") -> tuple[Field, ...]:
    """The fields of a harness session row, likewise."""
    return (
        Field(f"{under}id", "string", "the id the harness gave the session"),
        Field(f"{under}harness", "string", "the harness that ran it"),
        Field(f"{under}title", "string", "the first line the person said in it"),
        Field(f"{under}workspace", "string", "the folder it worked in"),
        Field(
            f"{under}model",
            "string",
            "the model it last ran on, empty where its log gives none",
        ),
        Field(f"{under}began", "string", "when it started, in ISO 8601"),
        Field(
            f"{under}updated", "string", "when its log was last written, in ISO 8601"
        ),
        Field(
            f"{under}continuable",
            "boolean",
            "whether `hmz chat harness adopt` can continue it in a chat",
        ),
    )


def _page(of: str, says: str) -> tuple[Field, ...]:
    """The fields every page of a listing has, around the list it is of."""
    return (
        Field(of, "list", says),
        Field("total", "integer", "how many there are in all, beyond this page too"),
        Field("offset", "integer", "how many were skipped"),
        Field("limit", "integer", "how many were listed at most"),
    )


_ID = "20261117T100000.000Z-ab12cd"

_HARNESS_COMMANDS = (
    Command(
        "list",
        "list the harness sessions of this folder, last written first",
        args=(_HARNESS_FOLDER, _LIMIT, _OFFSET),
        examples=(
            Example(
                "hmz chat harness list", "list the harness sessions of this folder"
            ),
            Example(
                "hmz chat harness list --json | "
                "jq -r '.sessions[] | select(.continuable) | .id'",
                "print the ids of the harness sessions that can be continued, with jq",
            ),
        ),
        prints="Prints one line per harness session: harness, id, when it "
        "was last written, and title.",
        output=(
            *_page("sessions", "the harness sessions, last written first"),
            *_session_fields("sessions[]."),
        ),
        methods=("chat.harness.list",),
        see=("chat harness show", "chat harness adopt"),
        run=_harness_list,
    ),
    Command(
        "show",
        "print one harness session, and what was said in it",
        args=(
            _HARNESS,
            _SESSION_ID,
            _HARNESS_FOLDER,
            Arg(
                ("--trace",),
                "also print what was said and done in the harness session, "
                "read from its logs",
            ),
        ),
        examples=(
            Example(
                "hmz chat harness show claude 7c1d0f5e",
                "print one harness session of Claude Code",
            ),
            Example(
                "hmz chat harness show claude 7c1d0f5e --trace --json | jq .trace",
                "read what was said in a harness session as JSON",
            ),
        ),
        prints="One line per field, name then value; with `--trace`, what "
        "each harness session said and did after them.",
        output=(
            *_session_fields(),
            Field(
                "trace",
                "list",
                "with `--trace`, what was said and done in the harness session",
            ),
        ),
        methods=("chat.harness.get",),
        see=("chat harness list", "chat harness adopt"),
        run=_harness_show,
    ),
    Command(
        "adopt",
        "continue a harness session in a new chat",
        says="Copies the harness session into a new chat of the folder and"
        " prints the chat's id; the session stays as it is. Send a "
        "message with `hmz chat say`.",
        args=(
            _HARNESS,
            _SESSION_ID,
            _HARNESS_FOLDER,
            Arg(
                ("-a", "--agent"),
                "an agent of the same harness to continue with, as "
                "HARNESS[@ACCOUNT]/MODEL[:EFFORT]; by default, the session's "
                "own model",
                metavar="AGENT",
            ),
        ),
        examples=(
            Example(
                "hmz chat harness adopt claude 7c1d0f5e",
                "continue a harness session of Claude Code in a new chat",
            ),
            Example(
                "hmz chat say $(hmz chat harness adopt codex 019a2b -a codex/gpt-5.2:high) "
                '"Carry on"',
                "continue a harness session of Codex with another model, and "
                "send the new chat a message",
            ),
        ),
        prints="Prints the new chat's id.",
        output=(Field("chat", "string", "the new chat's id"),),
        methods=("chat.harness.adopt",),
        see=("chat harness list", "chat say"),
        run=_harness_adopt,
    ),
)

COMMANDS = (
    Command(
        "chat",
        "start chats with an agent, send messages, and manage them",
        says="A chat is one conversation with one agent in a folder, kept "
        "by the daemon under an id. `hmz chat start` and `hmz chat "
        "say` each print the agent's answer.",
        commands=(
            Command(
                "start",
                "start a chat and print the agent's answer",
                says="Starts a chat in the current folder, sends MESSAGE and waits"
                " for the answer. A failed turn exits with status 1; a signal"
                " leaves the chat going in the daemon.",
                args=(
                    Arg(
                        ("message",),
                        "the chat's first message; put `--` before a message that "
                        "starts with a dash",
                    ),
                    Arg(
                        ("-a", "--agent"),
                        "the agent to talk to, written "
                        "HARNESS[@ACCOUNT]/MODEL[:EFFORT]; when not given, the agent "
                        "remembered for the folder",
                        metavar="AGENT",
                    ),
                    Arg(
                        ("-e", "--env"),
                        "the environment the agent works in, written "
                        "BACKEND[@RUNTIME][/DIRECTORY]; when not given, the folder "
                        "itself",
                        metavar="ENV",
                    ),
                    Arg(
                        ("-w", "--workspace"),
                        "the folder the chat is of; when not given, the current "
                        "directory",
                        metavar="DIR",
                    ),
                    Arg(
                        ("--no-folder",),
                        "start the chat in no folder; the daemon makes a directory "
                        "for this chat alone",
                    ),
                    Arg(
                        ("--worktree",),
                        "A new git worktree of the folder, which the folder itself is "
                        "left out of",
                    ),
                    Arg(
                        ("--permission",),
                        "what the agent may change; `workspace-write` when not given",
                        choices=_PERMISSIONS,
                    ),
                    _PREFER,
                    Arg(
                        ("--remember",),
                        "remember the agent for this folder, so that the next chat "
                        "started here without `-a` uses it",
                    ),
                    _DETACH,
                    _EVENTS,
                ),
                examples=(
                    Example(
                        'hmz chat start -a claude/claude-haiku-4-5 "What does charge() do?"',
                        "start a chat in this folder and print the agent's answer",
                    ),
                    Example(
                        "id=$(hmz chat start --json -a codex/gpt-5.2:high "
                        '"Fix the failing test" | jq -r .chat)',
                        "start a chat from a script and keep its id for `hmz chat say`",
                    ),
                    Example(
                        "hmz chat start --worktree --permission read-only "
                        '"Review the parser"',
                        "start a chat in a new git worktree of the folder, with an "
                        "agent that may only read",
                    ),
                    Example(
                        'hmz chat start --detach "Run the whole test suite"',
                        "start a chat without waiting, and print its id",
                    ),
                ),
                prints="Prints the agent's answer on standard output, and the chat's"
                " id and the turn as it goes on standard error.",
                output=_TURN,
                exits=_SIGNALS,
                methods=(
                    "chat.start",
                    "chat.say",
                    "epic.attach",
                    "epic.detach",
                    "settings.get",
                ),
                see=("chat say", "chat show", "chat list"),
                run=_start,
            ),
            Command(
                "say",
                "send the next message to a chat and print the answer",
                says="Sends MESSAGE as the chat's next turn and waits until the "
                "agent has answered. A chat that is resting is carried on "
                "first; a failed turn exits with status 1.",
                args=(
                    _CHAT,
                    Arg(
                        ("message",),
                        "the next message; put `--` before a message that starts with"
                        " a dash",
                    ),
                    _DETACH,
                    _EVENTS,
                ),
                examples=(
                    Example(
                        f'hmz chat say {_ID} "And how is it tested?"',
                        "send the next message to a chat and print the answer",
                    ),
                    Example(
                        'hmz chat say --json "$id" "Now run the linter" | jq -r .answer',
                        "send a message from a script and read the answer out of the "
                        "JSON document with jq",
                    ),
                    Example(
                        'hmz chat say --events "$id" "Now run the linter"',
                        "follow the turn as JSON lines, one record per line",
                    ),
                ),
                prints="Prints the agent's answer on standard output, and the chat's"
                " id and the turn as it goes on standard error.",
                output=_TURN,
                exits=_SIGNALS,
                methods=(
                    "chat.get",
                    "chat.say",
                    "chat.start",
                    "epic.attach",
                    "epic.detach",
                ),
                see=("chat start", "chat stop", "chat show"),
                run=_say,
            ),
            Command(
                "list",
                "list the chats of this folder, newest first",
                args=(
                    Arg(
                        ("-w", "--workspace"),
                        "the folder whose chats are listed; by default, the current "
                        "directory",
                        metavar="DIR",
                    ),
                    Arg(("--all",), "list the chats of every folder"),
                    Arg(
                        ("--archived",), "list the archived chats instead of the others"
                    ),
                    Arg(
                        ("-q", "--search"),
                        "only the chats whose title, first message or id contains "
                        "this text",
                        metavar="TEXT",
                    ),
                    _LIMIT,
                    _OFFSET,
                ),
                examples=(
                    Example("hmz chat list", "list the chats of this folder"),
                    Example(
                        "hmz chat list --all --json | "
                        """jq -r '.chats[] | select(.state == "turn") | .id'""",
                        "print the ids of the chats of every folder whose turn is "
                        "open, with jq",
                    ),
                    Example(
                        "hmz chat list --archived -q parser",
                        "find archived chats by a word in their title",
                    ),
                ),
                prints="One line per chat: id, state, title.",
                output=(
                    *_page("chats", "the chats, newest first"),
                    *_chat_fields("chats[]."),
                ),
                methods=("chat.list",),
                see=("chat show", "chat start"),
                run=_list,
            ),
            Command(
                "show",
                "print one chat, its state and what was said",
                args=(
                    _CHAT,
                    Arg(
                        ("--trace",),
                        "also print what was said and done in the chat, read from its"
                        " logs",
                    ),
                ),
                examples=(
                    Example(f"hmz chat show {_ID}", "print one chat"),
                    Example(
                        'until [ "$(hmz chat show "$id" --json | jq -r .state)" != turn ]; '
                        "do sleep 2; done",
                        "wait for a detached chat's turn to finish by reading its "
                        "state with jq",
                    ),
                ),
                prints="One line per field, name then value; with `--trace`, what "
                "each harness session said and did after them.",
                output=(
                    *_chat_fields(),
                    Field("at", "string", "the directory the chat is written down in"),
                    Field("task", "string", "the chat's first message, whole"),
                    Field(
                        "prefer",
                        "string",
                        "what the chat set a `$name` to run, `native` or `flow`, "
                        "empty when it follows the settings",
                    ),
                    Field(
                        "forked",
                        "string",
                        "the id of the chat this one was forked from, empty for none",
                    ),
                    Field(
                        "adopted",
                        "string",
                        "the harness session this chat continues, as HARNESS:ID, "
                        "empty for none",
                    ),
                    Field("agents", "list", "the agents of the chat"),
                    Field("sessions", "list", "the harness sessions the chat opened"),
                    Field(
                        "earlier",
                        "integer",
                        "how many of its harness sessions were opened before the chat"
                        " was last carried on",
                    ),
                    Field(
                        "backup", "list", "the backup targets the chat was started with"
                    ),
                    Field(
                        "backed",
                        "object",
                        "how each backup of the chat went, by target",
                    ),
                    Field(
                        "trace",
                        "list",
                        "with `--trace`, what each harness session said and did, read"
                        " from its logs",
                    ),
                ),
                methods=("chat.get",),
                see=("chat list", "chat commands"),
                run=_show,
            ),
            Command(
                "rename",
                "change a chat's title",
                args=(_CHAT, Arg(("title",), "the new title, at most 240 characters")),
                examples=(
                    Example(
                        f'hmz chat rename {_ID} "Discount codes"', "give a chat a title"
                    ),
                ),
                prints="The chat's line, as `hmz chat list` prints it.",
                output=_chat_fields(),
                methods=("chat.rename",),
                see=("chat list",),
                run=_rename,
            ),
            Command(
                "fork",
                "make a new chat that goes on from this one's turns",
                args=(_CHAT,),
                examples=(
                    Example(
                        f"hmz chat fork {_ID}",
                        "fork a chat and print the new chat's id",
                    ),
                    Example(
                        'hmz chat say $(hmz chat fork "$id") "Try it the other way"',
                        "fork a chat and send the fork a message",
                    ),
                ),
                prints="Prints the new chat's id.",
                output=(Field("chat", "string", "the new chat's id"),),
                methods=("chat.fork",),
                see=("chat say",),
                run=_fork,
            ),
            Command(
                "archive",
                "archive a chat, hiding it from the list",
                args=(_CHAT,),
                examples=(Example(f"hmz chat archive {_ID}", "archive a chat"),),
                prints="The chat's line, as `hmz chat list` prints it.",
                output=_chat_fields(),
                methods=("chat.archive",),
                see=("chat unarchive", "chat list"),
                run=_archive,
            ),
            Command(
                "unarchive",
                "put an archived chat back in the list",
                args=(_CHAT,),
                examples=(
                    Example(
                        f"hmz chat unarchive {_ID}",
                        "put an archived chat back in the list",
                    ),
                ),
                prints="The chat's line, as `hmz chat list` prints it.",
                output=_chat_fields(),
                methods=("chat.unarchive",),
                see=("chat archive", "chat list"),
                run=_unarchive,
            ),
            Command(
                "delete",
                "permanently delete a chat and its harness sessions",
                says="Asks before deleting unless `--yes` is given; without a "
                "terminal on standard input it deletes nothing without "
                "`--yes`. A deleted chat cannot be brought back.",
                args=(_CHAT, Arg(("-y", "--yes"), "delete without asking")),
                examples=(
                    Example(
                        f"hmz chat delete {_ID}",
                        "delete a chat after confirming at the terminal",
                    ),
                    Example(
                        'hmz chat delete --yes "$id"',
                        "delete a chat from a script without being asked",
                    ),
                ),
                prints="Prints nothing on standard output, and asks the question on "
                "standard error.",
                output=(
                    Field("deleted", "string", "the id of the chat that was deleted"),
                ),
                methods=("chat.get", "chat.delete"),
                see=("chat archive",),
                run=_delete,
            ),
            Command(
                "stop",
                "stop a chat's open turn, leaving it between turns",
                args=(_CHAT,),
                examples=(
                    Example(f"hmz chat stop {_ID}", "stop the turn a chat is taking"),
                ),
                prints="Prints `Stopped`.",
                output=(
                    Field(
                        "stopped", "string", "the id of the chat whose turn was stopped"
                    ),
                ),
                methods=("chat.get", "chat.start", "chat.stop"),
                see=("chat say", "chat show"),
                run=_stop,
            ),
            Command(
                "set",
                "set a chat's permission or what `$name` runs in it",
                says="Sets either or both. A permission holds from the chat's next"
                " turn; a resting chat is carried on first, with nothing "
                "said.",
                args=(
                    _CHAT,
                    Arg(
                        ("--permission",),
                        "what the agent may change, from the next turn",
                        choices=_PERMISSIONS,
                    ),
                    _PREFER,
                ),
                examples=(
                    Example(
                        f"hmz chat set {_ID} --permission read-only",
                        "let a chat's agent only read from its next turn",
                    ),
                    Example(
                        'hmz chat set "$id" --prefer flow',
                        "have `$name` lines of a chat run flows rather than the "
                        "harness's skills",
                    ),
                ),
                prints="Prints the chat's permission and preference as they then "
                "are, one per line.",
                output=(
                    Field("chat", "string", "the chat's id"),
                    Field(
                        "permission",
                        "string|null",
                        "what the agent may change, or null for an Ai-chan chat",
                    ),
                    Field(
                        "prefer",
                        "string",
                        "what a `$name` both a skill and a flow answer to runs: "
                        "`native` or `flow`",
                    ),
                    Field(
                        "prefer_from",
                        "string",
                        "`chat` where the chat sets it itself, `settings` where it "
                        "follows the settings",
                    ),
                ),
                methods=("chat.get", "chat.start", "chat.set", "chat.commands"),
                see=("chat commands", "chat move", "chat agent"),
                run=_set,
            ),
            Command(
                "move",
                "move a chat to another environment between turns",
                args=(
                    _CHAT,
                    Arg(
                        ("env",),
                        "the environment to move to, written "
                        "BACKEND[@RUNTIME][/DIRECTORY]",
                    ),
                ),
                examples=(
                    Example(
                        f"hmz chat move {_ID} ssh@gpu-box/srv/repo",
                        "move a chat to a folder on a runtime reached over ssh",
                    ),
                    Example(
                        'hmz chat move "$id" local/~/shop',
                        "move a chat back to a folder of this machine",
                    ),
                ),
                prints="Prints the environment the chat works in from then on.",
                output=(
                    Field("chat", "string", "the chat's id"),
                    Field(
                        "env",
                        "string",
                        "the environment the chat works in from then on",
                    ),
                ),
                methods=("chat.get", "chat.start", "chat.move"),
                see=("chat set", "chat show"),
                run=_move,
            ),
            Command(
                "agent",
                "carry a chat on with another model or effort",
                args=(
                    _CHAT,
                    Arg(
                        ("agent",),
                        "the agent to go on with, written "
                        "HARNESS[@ACCOUNT]/MODEL[:EFFORT], of the chat's own harness "
                        "and account",
                    ),
                ),
                examples=(
                    Example(
                        f"hmz chat agent {_ID} claude/claude-opus-5:high",
                        "carry a chat on with another model at high effort",
                    ),
                ),
                prints="The chat's line, as `hmz chat list` prints it.",
                output=_chat_fields(),
                methods=("chat.agent",),
                see=("chat set", "chat show"),
                run=_agent,
            ),
            Command(
                "commands",
                "list what a chat's lines can start with",
                args=(_CHAT,),
                examples=(
                    Example(
                        f"hmz chat commands {_ID}",
                        "list what a chat's lines can start with",
                    ),
                    Example(
                        'hmz chat commands "$id" --json | '
                        """jq -r '.entries[] | select(.source == "flow") | .name'""",
                        "print the names of the flows a chat can start, with jq",
                    ),
                ),
                prints="Prints one line per entry: sigil and name, where it comes "
                "from, and what it does.",
                output=(
                    Field("entries", "list", "what a line can start with"),
                    Field("entries[].sigil", "string", "`/`, `$`, `!` or `@`"),
                    Field("entries[].name", "string", "the name after the sigil"),
                    Field("entries[].about", "string", "what it does"),
                    Field(
                        "entries[].how",
                        "string",
                        "how hmz serves an entry of the harness: `pass`, `call`, "
                        "`emulate` or `refuse`; empty for the others",
                    ),
                    Field(
                        "entries[].source",
                        "string",
                        "`native` for the harness's own, `hmz` for a command of hmz, "
                        "`flow` for a flow",
                    ),
                    Field(
                        "prefer",
                        "string",
                        "what a `$name` both a skill and a flow answer to runs: "
                        "`native` or `flow`",
                    ),
                    Field(
                        "prefer_from",
                        "string",
                        "`chat` where the chat sets it itself, `settings` where it "
                        "follows the settings",
                    ),
                    Field(
                        "permission",
                        "string|null",
                        "what the agent may change, or null for an Ai-chan chat",
                    ),
                    Field(
                        "listed",
                        "boolean",
                        "whether the list is everything the harness lists, which it "
                        "is once the chat has taken a turn",
                    ),
                ),
                methods=("chat.get", "chat.start", "chat.commands"),
                see=("chat set", "chat say"),
                run=_commands,
            ),
            Command(
                "backup",
                "back a chat up to its backup targets, or those named",
                args=(
                    _CHAT,
                    Arg(
                        ("--to",),
                        "a backup target to back up to; when not given, the targets "
                        "the chat was started with",
                        metavar="TARGET",
                        many=True,
                    ),
                ),
                examples=(
                    Example(f"hmz chat backup {_ID}", "back a chat up to its targets"),
                    Example(
                        'hmz chat backup "$id" --to lab',
                        "back a chat up to the target named `lab`",
                    ),
                ),
                prints="Prints the targets the backup was queued for, a line each; "
                "it does not wait for the backup.",
                output=(
                    Field("queued", "list", "the targets the backup was queued for"),
                ),
                methods=("chat.backup",),
                see=("chat show",),
                run=_backup,
            ),
            Command(
                "harness",
                "read harness sessions and continue one in a chat",
                says="A harness session is a conversation a harness such as Claude"
                " Code or Codex had on its own in a folder, outside hmz. "
                "These commands list, read, and continue them.",
                commands=_HARNESS_COMMANDS,
            ),
        ),
    ),
)
