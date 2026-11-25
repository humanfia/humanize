"""`hmz ai`: the conversations with Ai-chan, made, talked in, listed, renamed and deleted."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.cli.tree import YES, Arg, Command, Example, Field, sure, table, workspace
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call
    from hmz.sdk.families.aichan import Reply

__all__ = ["COMMANDS"]

_ID = Arg(("id",), "the conversation's number, as `hmz ai list` prints it", kind=int)
_TIMEOUT = Arg(
    ("--timeout",),
    "how many seconds to wait for Ai-chan's answer before giving up",
    metavar="SECONDS",
    kind=float,
    default=600,
)
_NUMBER = Field("id", "integer", "the conversation's number")


def _heard(reply: Reply | None) -> dict[str, Any]:
    """What she said, as a document says it; nothing of either where she was not waited for."""
    if reply is None:
        return {"answer": None, "mode": None}
    return {"answer": reply.text, "mode": reply.mode}


def _new(call: Call) -> None:
    given: str | None = call.workspace
    scope: str = call.scope or (
        "epic" if call.epic else "workspace" if given else "daemon"
    )
    # A daemon scope is of no workspace, so the folder this is typed in is not one either.
    at = workspace(call) if given or scope in ("workspace", "epic") else None
    made = call.client.aichan.create(
        call.task,
        scope=scope,
        workspace=at,
        epic=call.epic,
        nous=call.nous,
        preset=call.preset,
    )
    if not call.json:
        # Before she is waited for: a conversation made is named, however the wait ends.
        print(made.id, flush=True)
    reply = call.client.aichan.heard(made.id, wait=call.timeout) if call.wait else None
    call.answers(
        {
            "id": made.id,
            "workspace": made.workspace,
            "slot": made.slot,
            **_heard(reply),
        },
        [] if reply is None else [reply.text],
    )


def _list(call: Call) -> None:
    conversations = call.client.aichan.list()
    call.answers(
        {
            "conversations": [
                {
                    "id": one.id,
                    "title": one.title,
                    "scope": one.scope,
                    "workspace": one.workspace,
                    "epic": one.epic,
                    "nous": one.nous,
                    "preset": one.preset,
                    "slot": one.slot,
                    "state": one.state,
                    "created": one.created,
                    "latest": one.latest,
                    "updated": one.updated,
                }
                for one in conversations
            ]
        },
        table(
            [
                [str(one.id), one.state, one.scope, one.preset, one.nous, one.title]
                for one in conversations
            ]
        ),
    )


def _rename(call: Call) -> None:
    call.client.aichan.rename(call.id, call.title)
    call.answers({"id": call.id, "title": call.title}, [t("Renamed")])


def _forget(call: Call) -> None:
    if not call.yes:
        # Read before anything is asked: one that is not there is refused as that.
        one = call.client.aichan.get(call.id)
        sure(
            call,
            t(
                "Delete conversation {id} ({title}) with Ai-chan? "
                "It cannot be brought back.",
                id=one.id,
                title=one.title,
            ),
        )
    call.client.aichan.forget(call.id)
    call.answers({"id": call.id}, [t("Deleted")])


def _say(call: Call) -> None:
    reply = call.client.aichan.say(
        call.id, call.text, hear=not call.no_wait, wait=call.timeout
    )
    call.answers(
        {"id": call.id, **_heard(reply)}, [] if reply is None else [reply.text]
    )


def _wait(call: Call) -> None:
    reply = call.client.aichan.heard(call.id, wait=call.timeout)
    call.answers({"id": call.id, **_heard(reply)}, [reply.text])


def _stop(call: Call) -> None:
    call.client.aichan.stop(call.id)
    call.answers({"id": call.id}, [t("Stopped")])


COMMANDS = (
    Command(
        "ai",
        "talk to Ai-chan, who operates hmz for you",
        says="Ai-chan is an agent that operates hmz for you within a scope: this daemon, "
        "one workspace or one epic. Each conversation with her has a number. These "
        "commands start a conversation, say the next line in one, and list, rename and "
        "delete conversations.",
        commands=(
            Command(
                "new",
                "start a conversation with Ai-chan",
                says="Starts a conversation whose first message is TASK and prints its "
                "number. Without `--scope`, the scope is the epic where `--epic` is "
                "given, else the workspace where `--workspace` is given, else the daemon. "
                "With `--wait` it also waits for Ai-chan's answer and prints it.",
                args=(
                    Arg(
                        ("task",),
                        "the first thing to tell Ai-chan; its first line becomes the "
                        "conversation's title",
                    ),
                    Arg(
                        ("--scope",),
                        "what Ai-chan reaches: every workspace and epic of this daemon, "
                        "one workspace, or one epic",
                        choices=("daemon", "workspace", "epic"),
                    ),
                    Arg(
                        ("-w", "--workspace"),
                        "the workspace of a workspace or epic scope, as an absolute "
                        "path; when not given, the folder the command runs in",
                        metavar="PATH",
                    ),
                    Arg(
                        ("--epic",),
                        "the epic of an epic scope, by its name",
                        metavar="NAME",
                    ),
                    Arg(
                        ("--nous",),
                        "the nous Ai-chan thinks with; when not given, the one the last "
                        "conversation was started with",
                        metavar="NOUS",
                    ),
                    Arg(
                        ("--preset",),
                        "what Ai-chan may do: read-only reads and changes nothing, "
                        "danger-full-access changes what her scope reaches; read-only "
                        "when not given",
                        choices=("read-only", "danger-full-access"),
                    ),
                    Arg(("--wait",), "also wait for Ai-chan's answer and print it"),
                    _TIMEOUT,
                ),
                examples=(
                    Example(
                        'hmz ai new "Which epics failed today?" --wait',
                        "starts a conversation scoped to this daemon and prints "
                        "Ai-chan's answer",
                    ),
                    Example(
                        'hmz ai new "Summarise this epic" '
                        "--epic 20261117T100000.000Z-ab12cd "
                        "--nous claude/claude-sonnet-4-5",
                        "starts a conversation scoped to one epic of this folder, with "
                        "the nous named",
                    ),
                    Example(
                        'id=$(hmz ai new "Tidy the worktrees" -w ~/project '
                        "--preset danger-full-access --json | jq .id)",
                        "starts a conversation that may change the workspace ~/project "
                        "and keeps its number in a shell variable",
                    ),
                ),
                prints="Prints the conversation's number on the first line; with "
                "`--wait`, Ai-chan's answer after it.",
                output=(
                    _NUMBER,
                    Field(
                        "workspace",
                        "string",
                        "the workspace of the conversation's host",
                    ),
                    Field("slot", "string", "the slot of the conversation's host"),
                    Field(
                        "answer",
                        "string|null",
                        "what Ai-chan said, with `--wait`; null without it",
                    ),
                    Field(
                        "mode",
                        "string|null",
                        "with `--wait`, `listen` when her turn is over, anything else "
                        "when she asks a question mid-turn; null without `--wait`",
                    ),
                ),
                methods=(
                    "aichan.create",
                    "aichan.list",
                    "epic.attach",
                    "epic.status",
                    "epic.detach",
                ),
                see=("ai say", "ai wait", "ai list"),
                run=_new,
            ),
            Command(
                "list",
                "list the conversations with Ai-chan, newest first",
                examples=(
                    Example("hmz ai list", "lists the conversations with Ai-chan"),
                    Example(
                        "hmz ai list --json | jq '.conversations[] "
                        '| select(.state == "running") | .id\'',
                        "prints the numbers of the conversations Ai-chan is answering in",
                    ),
                ),
                prints="Prints one line per conversation, newest first: its number, "
                "state, scope, preset, nous and title.",
                output=(
                    Field("conversations", "list", "the conversations, newest first"),
                    Field("conversations[].id", "integer", "the conversation's number"),
                    Field("conversations[].title", "string", "its title"),
                    Field(
                        "conversations[].scope",
                        "string",
                        "what Ai-chan reaches in it: `daemon`, `workspace` or `epic`",
                    ),
                    Field(
                        "conversations[].workspace",
                        "string",
                        "the workspace of its host",
                    ),
                    Field(
                        "conversations[].epic",
                        "string",
                        "the epic of an epic scope, else empty",
                    ),
                    Field(
                        "conversations[].nous",
                        "string",
                        "the nous Ai-chan thinks with in it",
                    ),
                    Field(
                        "conversations[].preset",
                        "string",
                        "what she may do: `read-only` or `danger-full-access`",
                    ),
                    Field(
                        "conversations[].slot",
                        "string",
                        "the slot of the conversation's host",
                    ),
                    Field(
                        "conversations[].state",
                        "string",
                        "`running` while Ai-chan answers, `waiting` between turns, "
                        "`folded` when no host holds it",
                    ),
                    Field(
                        "conversations[].created",
                        "string",
                        "when it was started, ISO 8601 in UTC",
                    ),
                    Field(
                        "conversations[].latest",
                        "string",
                        "the start of what was last said in it",
                    ),
                    Field(
                        "conversations[].updated",
                        "string",
                        "when that was said, ISO 8601 in UTC",
                    ),
                ),
                methods=("aichan.list",),
                see=("ai new", "ai say", "ai rename", "ai forget"),
                run=_list,
            ),
            Command(
                "rename",
                "change the title of a conversation with Ai-chan",
                args=(_ID, Arg(("title",), "the new title, 1 to 240 characters")),
                examples=(
                    Example(
                        'hmz ai rename 3 "Failed epics, Tuesday"',
                        "gives conversation 3 a new title",
                    ),
                ),
                prints="Prints that the conversation was renamed.",
                output=(_NUMBER, Field("title", "string", "the title given")),
                methods=("aichan.rename",),
                see=("ai list",),
                run=_rename,
            ),
            Command(
                "forget",
                "delete a conversation with Ai-chan for good",
                says="Deletes the conversation and closes its host; it cannot be brought "
                "back. Asks first on standard error unless `--yes` is given; where nobody "
                "is at a terminal, or with `--json`, `--yes` is needed.",
                args=(_ID, YES),
                examples=(
                    Example("hmz ai forget 3", "asks, then deletes conversation 3"),
                    Example(
                        "hmz ai forget 3 --yes", "deletes conversation 3 without asking"
                    ),
                ),
                prints="Prints that the conversation was deleted.",
                output=(_NUMBER,),
                methods=("aichan.list", "aichan.forget"),
                see=("ai list",),
                run=_forget,
            ),
            Command(
                "say",
                "say the next line to Ai-chan and print her answer",
                says="The line answers what Ai-chan waits on, or is said into her turn "
                "while she is answering; a conversation that was folded away is carried "
                "on first. Waits for her answer and prints it, unless `--no-wait` is "
                "given.",
                args=(
                    _ID,
                    Arg(("text",), "the line to say to Ai-chan"),
                    Arg(
                        ("--no-wait",),
                        "return once the line is taken, without waiting for Ai-chan's "
                        "answer",
                    ),
                    _TIMEOUT,
                ),
                examples=(
                    Example(
                        'hmz ai say 3 "And yesterday?"',
                        "says the next line in conversation 3 and prints Ai-chan's "
                        "answer",
                    ),
                    Example(
                        'hmz ai say 3 "Stop the oldest one" --no-wait '
                        "&& hmz ai wait 3 --json",
                        "says a line without waiting, then waits for the answer as JSON",
                    ),
                ),
                prints="Prints what Ai-chan said, or nothing with `--no-wait`.",
                output=(
                    _NUMBER,
                    Field(
                        "answer",
                        "string|null",
                        "what Ai-chan said, or null with `--no-wait`",
                    ),
                    Field(
                        "mode",
                        "string|null",
                        "`listen` when her turn is over, anything else when she asks a "
                        "question mid-turn, or null with `--no-wait`",
                    ),
                ),
                methods=(
                    "aichan.list",
                    "epic.attach",
                    "epic.status",
                    "epic.answer",
                    "epic.say",
                    "epic.detach",
                ),
                see=("ai wait", "ai stop", "ai list"),
                run=_say,
            ),
            Command(
                "wait",
                "wait until Ai-chan waits on you, and print what she said",
                says="Waits while Ai-chan's turn is open, then prints what she waits on "
                "you with: her last answer, or a question she asks mid-turn. A "
                "conversation that was folded away is carried on first.",
                args=(_ID, _TIMEOUT),
                examples=(
                    Example(
                        "hmz ai wait 3",
                        "waits for Ai-chan's answer in conversation 3 and prints it",
                    ),
                    Example(
                        "hmz ai wait 3 --timeout 60 --json",
                        "waits at most a minute, and prints the answer as JSON",
                    ),
                ),
                prints="Prints what Ai-chan said.",
                output=(
                    _NUMBER,
                    Field("answer", "string", "what Ai-chan said"),
                    Field(
                        "mode",
                        "string",
                        "`listen` when her turn is over, anything else when she asks a "
                        "question mid-turn",
                    ),
                ),
                methods=("aichan.list", "epic.attach", "epic.status", "epic.detach"),
                see=("ai say", "ai stop"),
                run=_wait,
            ),
            Command(
                "stop",
                "stop Ai-chan's open turn, leaving the conversation between turns",
                args=(_ID,),
                examples=(
                    Example(
                        "hmz ai stop 3", "stops what Ai-chan is doing in conversation 3"
                    ),
                ),
                prints="Prints that it was stopped.",
                output=(_NUMBER,),
                methods=("aichan.list", "epic.attach", "epic.stop", "epic.detach"),
                see=("ai say", "ai list"),
                run=_stop,
            ),
        ),
    ),
)
