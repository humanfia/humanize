"""`hmz epic`: an epic held by a daemon, started, followed and steered as one of its frontends.

Each command attaches to the host of a workspace and slot (`epic.attach`), asks its one thing
of the subscription that opens, and lets go again; `attach`, `claim` and `start --follow` stay
attached and write what the host tells them. `status` alone attaches to nothing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from hmz.cli.tree import (
    DONE,
    REFUSED,
    UNREAD,
    Arg,
    Command,
    Example,
    Exit,
    Field,
    table,
)
from hmz.words import t

if TYPE_CHECKING:
    import queue
    from collections.abc import Callable, Sequence

    from hmz.cli.output import Out, Shown
    from hmz.cli.tree import Call
    from hmz.sdk.families.epics import Attached

__all__ = ["COMMANDS"]

#: What a command interrupted while it follows an epic exits with.
INTERRUPTED: Final = 130

#: How an epic ends that did not do what it was started for.
_FAILED: Final = ("failed", "crashed", "refused")

#: The code an answer that does not fit its question is refused with.
_MISFIT: Final = 400

#: How long an answer typed for a claimed role is given to be taken.
_ANSWERING: Final = 30.0

#: How long a frontend answering for a role waits for a message before it looks at what
#: was typed.
_TICK: Final = 0.2

#: Where one `-a` or `-e` item ends and the next begins: a comma before a role and `=`.
_ITEMS: Final = re.compile(r",(?=\s*[^\W\d][\w-]*=)")

#: The keys of a host's status, as `hmz epic status --json` writes them.
_STATUS: Final = (
    "workspace",
    "slot",
    "pid",
    "started",
    "state",
    "run",
    "epic_kind",
    "flow",
    "epic",
    "chat",
    "task",
    "pending",
    "ended",
    "attached",
    "clients",
    "budget",
    "usage",
    "flows",
    "calls",
)


def placed(call: Call) -> str:
    """The workspace a line names, as the daemon knows one: a whole path, its links followed.

    The directory the line was typed in where it names none.
    """
    return str(Path(call.workspace or Path.cwd()).expanduser().resolve())


def _attaches(call: Call, *, replay: bool = False) -> Attached:
    """Attaches to the host a line names, as one more frontend of it.

    Raises:
      hmz.sdk.Refused: With code 404 where no host is held there: attaching would start one,
        which only starting an epic is a reason to do.
    """
    where = placed(call)
    call.client.hosts.status(where, call.slot)
    return call.client.epics.attach(where, slot=call.slot, replay=replay)


def _live(attached: Attached) -> list[dict[str, Any]]:
    """Everything a host tells a frontend as it attaches, up to `live`.

    Raises:
      hmz.sdk.Refused: If the host let go, or the session ended, before that.
    """
    from hmz.sdk import Refused

    told: list[dict[str, Any]] = []
    for message in attached:
        told.append(message)
        if message.get("type") == "live":
            return told
    raise Refused(t("This host cannot be reached."), code=503)


def _interruptible(run: Callable[[Call], int | None]) -> Callable[[Call], int | None]:
    """A command that exits with 130 where it is interrupted, whatever it was waiting on."""

    def runs(call: Call) -> int | None:
        try:
            return run(call)
        except KeyboardInterrupt:
            return INTERRUPTED

    return runs


def _unread(call: Call, message: str) -> int:
    """Says a line could not be read, as the tree says it of one it could not parse."""
    line = " ".join(["hmz", *call.path])
    if call.json:
        print(json.dumps({"error": {"code": 400, "message": message}}))
    else:
        print(f"{line}: {message}", file=sys.stderr)
        print(t("Run `{line}` for help.", line=f"{line} --help"), file=sys.stderr)
    return UNREAD


def _roles(items: Sequence[str] | None) -> dict[str, str] | None:
    """What each role is given, by role, of every `-a` or `-e` of a line.

    Raises:
      ValueError: For an item that is not `<role>=<spec>`, and a role given twice.
    """
    if not items:
        return None
    given: dict[str, str] = {}
    for item in (one.strip() for value in items for one in _ITEMS.split(value)):
        role, written, spec = item.partition("=")
        if not (role and written and spec):
            raise ValueError(t("`{item}` is not written as `ROLE=SPEC`.", item=item))
        if role in given:
            raise ValueError(t("`{role}` is given twice.", role=role))
        given[role] = spec
    return given


def _start(call: Call) -> int | None:
    from hmz.runtime.flowing.specs import parse_budget, parse_params

    try:
        agents, envs = _roles(call.agents), _roles(call.envs)
        params = parse_params(call.params or [])
        budget = parse_budget(call.params or [])
    except ValueError as why:
        return _unread(call, str(why))
    attached = call.client.epics.attach(
        None if call.scratch else placed(call),
        slot=call.slot,
        replay=False,
        scratch=call.scratch or None,
    )
    with attached:
        # Away is set before the start, so that not even its first question waits -- and set
        # back where the start is refused, unless every role was away already.
        told = _live(attached) if call.away else []
        sets = call.away and not any(
            one.get("type") == "away" and one.get("all") for one in told
        )
        if sets:
            attached.afk(on=True)
        try:
            started = attached.start(
                call.flow,
                call.task,
                agents=agents,
                envs=envs,
                params=params or None,
                budget=None if budget is None else json.loads(budget.model_dump_json()),
                profile_flow=call.profile_flow or None,
                profile_environment=call.profile_environment or None,
                resume=call.resume_from or call.resume or None,
                backup=[] if call.no_backup else call.backup,
                remember=call.remember or None,
            )
        except BaseException:
            if sets:
                attached.afk(on=False)
            raise
        document = {
            "run": started.run,
            "slot": started.slot,
            "workspace": started.workspace,
        }
        said = (
            t("Epic {run} started in {workspace}, slot {slot}.", **document)
            if started.slot
            else t("Epic {run} started in {workspace}.", **document)
        )
        if not call.follow:
            call.answers(document, [said])
            return None
        return _follows(call, attached, awaited=True, first=(document, said), told=told)


def _attach(call: Call) -> int:
    with _attaches(call, replay=not call.no_replay) as attached:
        return _follows(call, attached)


def _claim(call: Call) -> int:
    with _attaches(call, replay=not call.no_replay) as attached:
        for role in call.role:
            attached.claim(role, take=call.take or None)
        if not call.json:
            print(t("Claimed."), file=sys.stderr)
        return _follows(call, attached, roles=call.role, awaited=True)


def _typed() -> queue.SimpleQueue[str]:
    """Every line typed on standard input, as it is typed."""
    import queue
    import threading

    lines: queue.SimpleQueue[str] = queue.SimpleQueue()

    def reads() -> None:
        for line in sys.stdin:
            if line.strip():
                lines.put(line.rstrip("\n"))

    threading.Thread(target=reads, daemon=True, name="hmz-typed").start()
    return lines


def _follows(
    call: Call,
    attached: Attached,
    *,
    roles: Sequence[str] = (),
    awaited: bool = False,
    first: tuple[dict[str, Any], str] | None = None,
    told: Sequence[dict[str, Any]] = (),
) -> int:
    """Writes what a host tells a frontend until its epic ends, and says how it ended.

    Args:
      call: The command.
      attached: The frontend.
      roles: The roles it claims, whose questions are answered with what is typed.
      awaited: Whether an epic is waited for where none is going.
      first: What is written before anything the host says: as JSON, and as text.
      told: What the host has told the frontend already, written before what it tells next.

    Returns:
      Zero where the epic was done, was stopped or spent its budget, and where none was
      going; one where it failed, or the host let go first; 130 where it was interrupted.
    """
    from hmz.cli.output import Out, Shown
    from hmz.sdk import Refused

    lines = _typed() if roles else None
    waiting: list[str] = []
    answered: set[str] = set()
    live = going = False
    before = list(told)
    with Out(as_json=call.json) as out, Shown(out) as shown:
        if first is not None:
            if call.json:
                out.record(**first[0])
            else:
                out.aside(first[1])
        try:
            while before or not attached.over:
                message = (
                    before.pop(0) if before else attached.next(_TICK if roles else None)
                )
                if message is not None:
                    kind = message.get("type")
                    if call.json:
                        out.record(**message)
                    else:
                        _shows(out, shown, message)
                    if kind == "run":
                        going = message.get("state") in ("running", "stopping")
                    elif kind == "started":
                        # Another epic, which numbers its questions from one again.
                        answered.clear()
                    elif kind == "pending":
                        waiting = [
                            str(one["question"])
                            for one in message.get("pending") or ()
                            if one.get("role") in roles
                            and one["question"] not in answered
                        ]
                    elif kind == "live":
                        live = True
                        if not (going or awaited):
                            if not call.json:
                                out.aside(t("No epic is going here."))
                            return DONE
                    elif kind == "ended" and live:
                        return REFUSED if message.get("how") in _FAILED else DONE
                    elif kind == "gone":
                        return REFUSED
                while lines is not None and waiting and not lines.empty():
                    # The oldest question, answered once, whatever a `pending` on its way says.
                    question = waiting.pop(0)
                    answered.add(question)
                    try:
                        attached.answer(question, lines.get(), wait=_ANSWERING)
                    except (Refused, TimeoutError) as why:
                        if not call.json:
                            out.aside(str(why))
                        # Not taken: the next `pending` says whether it still waits.
                        answered.discard(question)
                        if getattr(why, "code", 0) == _MISFIT:
                            # It does, and the next line typed is tried on it.
                            waiting.insert(0, question)
        except KeyboardInterrupt:
            return INTERRUPTED
    # The session ended with nothing said of why.
    return REFUSED


def _shows(out: Out, shown: Shown, message: dict[str, Any]) -> None:
    """Writes one message of a host for a person: what its agents did, and what was asked."""
    from hmz.sdk.running import Opened

    def said(key: str) -> str:
        return str(message.get(key) or "")

    kind = message.get("type")
    if kind == "event":
        shown.heard(said("agent"), message.get("session") or None, message)
    elif kind == "opened":
        opened = Opened(
            key=said("key"),
            role=said("role"),
            agent=said("agent"),
            cli=said("cli"),
            model=said("model"),
            person=bool(message.get("person")),
            env=message.get("env"),
            harness=said("harness"),
        )
        shown.opened(opened.role, opened)
    elif kind == "printed":
        out.printed(said("text"))
    elif kind in ("notice", "gone"):
        out.aside(said("text") or said("why"))
    elif kind == "started":
        out.aside(
            t(
                "{who} started {flow}: {task}",
                who=said("by"),
                flow=said("flow"),
                task=said("task"),
            )
        )
    elif kind == "asked":
        out.aside(
            t(
                "{role} asks ({question}): {text}",
                role=said("role"),
                question=said("question"),
                text=said("text"),
            )
        )
        for at, option in enumerate(message.get("options") or (), 1):
            out.aside(f"  {at}. {option}")
        if message.get("schema") is not None:
            out.aside(f"  {json.dumps(message['schema'], ensure_ascii=False)}")
    elif kind == "answered":
        out.aside(t("{who} answered: {said}", who=said("by"), said=said("text")))
    elif kind == "said":
        out.aside(t("{who} said: {text}", who=said("by"), text=said("text")))
    elif kind == "withdrawn":
        out.aside(
            t(
                "Question {question} was withdrawn ({why}).",
                question=said("question"),
                why=said("why"),
            )
        )
    elif kind == "stopping":
        out.aside(t("{who} is stopping the epic.", who=said("by")))
    elif kind == "ended":
        out.aside(t("The epic ended: {how}.", how=said("how")))
        if said("why"):
            out.aside(said("why"))


def _say(call: Call) -> None:
    with _attaches(call) as attached:
        attached.say(call.text, to=call.to or None)
    call.answers({"text": call.text, "to": call.to or ""}, [t("Sent.")])


def _answer(call: Call) -> int | None:
    from hmz.sdk import Refused

    value = None
    if call.value is not None:
        try:
            value = json.loads(call.value)
        except ValueError:
            return _unread(call, t("`--value` takes JSON."))
    with _attaches(call) as attached:
        question = call.question
        if not question:
            pending = [str(one["question"]) for one in attached.status()["pending"]]
            if not pending:
                raise Refused(t("No question is waiting."), code=409)
            if len(pending) > 1:
                raise Refused(
                    t(
                        "{n} questions are waiting: name one with `--question` ({ids}).",
                        n=len(pending),
                        ids=", ".join(pending),
                    ),
                    code=409,
                )
            question = pending[0]
        attached.answer(question, call.text or None, value=value)
    call.answers({"question": question}, [t("Answered")])
    return None


def _stop(call: Call) -> None:
    with _attaches(call) as attached:
        if call.force:
            closed = attached.force()
            call.answers(
                {"forced": True, "closed": closed},
                [t("Force stopped ({n} sessions closed).", n=closed)],
            )
        else:
            attached.stop()
            call.answers({"forced": False, "closed": 0}, [t("Stopping…")])


def _board(call: Call) -> int | None:
    if call.remove and not call.key:
        return _unread(call, t("`--remove` takes the key of a line."))
    with _attaches(call) as attached:
        if call.key and (call.value or call.remove):
            attached.board(call.key, "" if call.remove else call.value)
            call.answers(
                {"key": call.key, "value": "" if call.remove else call.value},
                [
                    t("Removed {key} from the board.", key=call.key)
                    if call.remove
                    else t("Wrote {key} on the board.", key=call.key)
                ],
            )
            return None
        items: list[dict[str, Any]] | None = next(
            (one.get("items") for one in _live(attached) if one.get("type") == "board"),
            None,
        )
    if items is not None and call.key:
        items = [one for one in items if one.get("key") == call.key]
    call.answers(
        {"items": items},
        table(
            [
                [str(one.get(key) or "") for key in ("key", "value", "whose", "by")]
                for one in items or ()
            ]
        )
        or [t("Nothing is on the board yet.")],
    )
    return None


def _release(call: Call) -> None:
    with _attaches(call) as attached:
        # Taken first: a role is released only by the frontend that claims it.
        attached.claim(call.role, take=True)
        attached.release(call.role)
    call.answers({"role": call.role}, [t("Released {role}.", role=call.role)])


def _afk(call: Call) -> None:
    with _attaches(call) as attached:
        attached.afk(on=not call.back, role=call.role or None)
    call.answers(
        {"away": not call.back, "role": call.role or ""},
        [t("Back@@present") if call.back else t("Away")],
    )


def _status(call: Call) -> None:
    status = call.client.hosts.status(placed(call), call.slot)
    pending: list[dict[str, Any]] = status.get("pending") or []
    call.answers(
        {key: status.get(key) for key in _STATUS},
        [
            *table(
                [
                    [
                        str(status.get(key) or "")
                        for key in ("state", "flow", "epic", "task")
                    ]
                ]
            ),
            *table(
                [
                    [str(one.get(key) or "") for key in ("question", "role", "text")]
                    for one in pending
                ]
            ),
        ],
    )


_HOST: Final = (
    Arg(
        ("-w", "--workspace"),
        "the workspace of the epic, a directory of the daemon's machine, or the "
        "current directory",
        metavar="DIR",
    ),
    Arg(
        ("--slot",),
        "the slot of the host that holds the epic, as `hmz hosts list` prints it, or "
        "the workspace's own host",
        metavar="SLOT",
        default="",
    ),
)

_REPLAY: Final = Arg(
    ("--no-replay",), "write only what happens from now on, not what the epic has done"
)

_FOLLOWED: Final = (Exit(INTERRUPTED, "interrupted while following; the epic goes on"),)

COMMANDS = (
    Command(
        "epic",
        "start, follow and steer an epic held by this daemon",
        says="An epic is one run of a flow, held by the daemon on a host of its "
        "workspace. These commands start one, follow it, say lines to its agents, "
        "answer its questions and stop it. Each names the epic by `--workspace` and "
        "`--slot`; without them, the epic of the current directory's own host.",
        commands=(
            Command(
                "start",
                "start an epic on the daemon and return at once",
                says="Starts a flow as a new epic held by the daemon, and returns as "
                "soon as it has started; the epic runs on without this command. Roles, "
                "environments, params and the budget are written as `hmz exec` takes "
                "them. Questions the epic asks wait for `hmz epic answer`, unless "
                "`--away` is given. `--slot exec:` gives it a host of its own, beside "
                "any other epic of the workspace. `--follow` stays and writes the epic "
                "as `hmz epic attach` does, and exits with status 1 where the epic "
                "failed.",
                args=(
                    Arg(
                        ("flow",),
                        "the flow to run: an installed flow's name, a path or a ref",
                    ),
                    Arg(("task",), "what the epic is to do", default=""),
                    Arg(
                        ("-a", "--agents"),
                        "what an agent role runs, as `<harness>[@<account>]/<model>"
                        "[:<effort>]` or a nous name",
                        metavar="ROLE=SPEC",
                        many=True,
                    ),
                    Arg(
                        ("-e", "--envs"),
                        "where an environment role is, as `<backend>[@<runtime>]"
                        "[/<directory>]`",
                        metavar="ROLE=SPEC",
                        many=True,
                    ),
                    Arg(
                        ("-p", "--params"),
                        "a param of the flow, or a limit of the budget as "
                        "`budget.cost=5`, `budget.duration=30m` or "
                        "`budget.output_tokens=200k`",
                        metavar="KEY=VALUE",
                        many=True,
                    ),
                    Arg(
                        ("--resume",),
                        "pick up the newest epic of this flow in the workspace",
                    ),
                    Arg(
                        ("--resume-from",),
                        "pick up this epic, named as `hmz runs list` prints it",
                        metavar="EPIC",
                    ),
                    Arg(
                        ("--backup",),
                        "a backup target the epic goes to, in place of the defaults",
                        metavar="NAME",
                        many=True,
                    ),
                    Arg(("--no-backup",), "back the epic up to no target"),
                    Arg(("--profile-flow",), "sample the flow's own Python as it runs"),
                    Arg(
                        ("--profile-environment",),
                        "profile the programs the agents start",
                    ),
                    Arg(
                        ("--remember",),
                        "keep these roles, params and budget as the workspace's "
                        "set-up of the flow",
                    ),
                    Arg(
                        ("--scratch",),
                        "run in a new folderless workspace instead of `--workspace`",
                    ),
                    Arg(
                        ("--away",),
                        "set every role away first, so that no question waits on a "
                        "person",
                    ),
                    Arg(
                        ("--follow",),
                        "stay attached and write the epic until it ends",
                    ),
                    *_HOST,
                ),
                examples=(
                    Example(
                        "hmz epic start goal 'fix the failing test' -a "
                        "worker=claude/claude-haiku-4-5:low -p budget.cost=2",
                        "start the flow `goal` in the current directory and return",
                    ),
                    Example(
                        "hmz epic start goal 'fix it' -p budget.cost=2 --slot exec: "
                        "--away --follow --json",
                        "start it on a new slot beside other epics, with nobody to "
                        "ask, and write its messages as JSON lines until it ends",
                    ),
                    Example(
                        "hmz epic start goal --resume -p budget.duration=1h",
                        "pick up the newest epic of `goal` here with an hour more",
                    ),
                ),
                prints="One line naming the epic's number, workspace and slot. With "
                "`--follow`, that line and then what `hmz epic attach` prints.",
                output=(
                    Field("run", "integer", "the epic's number on its host"),
                    Field(
                        "slot",
                        "string",
                        "the slot of the host that holds it, to pass as `--slot`",
                    ),
                    Field(
                        "workspace",
                        "string",
                        "the workspace it runs in, to pass as `--workspace`",
                    ),
                ),
                exits=_FOLLOWED,
                methods=("epic.attach", "epic.afk", "epic.start", "epic.detach"),
                see=("epic attach", "epic answer", "epic stop", "hosts list"),
                run=_interruptible(_start),
            ),
            Command(
                "attach",
                "follow an epic as it runs",
                says="Writes what the epic has done so far and then what it does, "
                "until it ends. Leaving with Ctrl-C does not stop the epic. Exits with "
                "status 1 where the epic failed. With "
                "`--json`, writes one JSON object a line, each a message of the host "
                "told apart by its `type`.",
                args=(_REPLAY, *_HOST),
                examples=(
                    Example("hmz epic attach", "follow the epic of this directory"),
                    Example(
                        "hmz epic attach --slot exec:1f2e --no-replay --json | jq -c "
                        "'select(.type == \"asked\")'",
                        "print each question an epic on another slot asks from now on",
                    ),
                ),
                prints="What each agent does on standard error and each answer on "
                "standard output, as `hmz exec` prints them, with the questions asked "
                "and how the epic ended.",
                output=(
                    Field(
                        "type",
                        "string",
                        "what the message is: `welcome`, `live`, `gone`, a history "
                        "record such as `started`, `event`, `asked`, `answered` or "
                        "`ended`, or a snapshot such as `run`, `pending` or `board`",
                    ),
                    Field(
                        "seq",
                        "integer",
                        "of a history record, its place in the host's history",
                    ),
                    Field("run", "integer", "of a history record, the epic's number"),
                    Field(
                        "question",
                        "string",
                        "of `asked`, the id to answer it by with `hmz epic answer`",
                    ),
                    Field(
                        "how",
                        "string",
                        "of `ended`: `done`, `stopped`, `budget`, `refused`, `failed` "
                        "or `crashed`",
                    ),
                ),
                exits=_FOLLOWED,
                methods=("hosts.status", "epic.attach", "epic.detach"),
                see=("epic status", "epic answer", "epic say"),
                run=_interruptible(_attach),
            ),
            Command(
                "say",
                "say a line to an agent of the epic",
                says="Says a line to the epic that is going. Without `--to` it "
                "answers a question that is listening, or else goes to the first "
                "agent with a turn open; a line that cannot go in yet waits for the "
                "agent's next turn.",
                args=(
                    Arg(("text",), "the line to say"),
                    Arg(
                        ("--to",),
                        "who the line is for: an agent's name, a session as "
                        "`<agent>/<n>`, or `outworlder:<role>`",
                        metavar="WHO",
                    ),
                    *_HOST,
                ),
                examples=(
                    Example(
                        "hmz epic say 'use the staging database'",
                        "say a line to the agent working now",
                    ),
                    Example(
                        "hmz epic say --to NeiKos 'skip the migration'",
                        "say a line to the agent named NeiKos",
                    ),
                ),
                prints="One line once the daemon has taken it.",
                output=(
                    Field("text", "string", "the line said"),
                    Field("to", "string", "who it was said to, or empty"),
                ),
                methods=("hosts.status", "epic.attach", "epic.say", "epic.detach"),
                see=("epic attach", "epic answer"),
                run=_say,
            ),
            Command(
                "answer",
                "answer a question the epic is waiting on",
                says="Answers a question the epic asked a person. Without "
                "`--question` it answers the only one waiting. The answer is text, "
                "the number of an offered option, or for a question with a schema a "
                "JSON value given as `--value`; one that does not fit is refused and "
                "the question stays.",
                args=(
                    Arg(("text",), "the answer in words", default=""),
                    Arg(
                        ("-q", "--question"),
                        "the id of the question, as `hmz epic status` prints it",
                        metavar="ID",
                    ),
                    Arg(
                        ("--value",),
                        "the answer as a JSON value of the question's schema, in "
                        "place of the text",
                        metavar="JSON",
                    ),
                    *_HOST,
                ),
                examples=(
                    Example("hmz epic answer yes", "answer the only question waiting"),
                    Example(
                        'hmz epic answer -q q3 --value \'{"verdict": "approve"}\'',
                        "answer question q3 with a value of its schema",
                    ),
                ),
                prints="One line once the answer is taken.",
                output=(
                    Field("question", "string", "the id of the question answered"),
                ),
                methods=(
                    "hosts.status",
                    "epic.attach",
                    "epic.status",
                    "epic.answer",
                    "epic.detach",
                ),
                see=("epic status", "epic claim", "epic afk"),
                run=_answer,
            ),
            Command(
                "stop",
                "stop the epic",
                says="Stops the epic: the turn under way is interrupted and the flow "
                "unwinds. `--force` also closes every session still in a turn, for an "
                "epic that does not stop.",
                args=(
                    Arg(
                        ("--force",),
                        "stop it and close every session that has a turn open",
                    ),
                    *_HOST,
                ),
                examples=(
                    Example("hmz epic stop", "stop the epic of this folder"),
                    Example(
                        "hmz epic stop --force --slot exec:1f2e",
                        "force an epic on another slot that is still stopping",
                    ),
                ),
                prints="One line; with `--force`, how many sessions were closed.",
                output=(
                    Field("forced", "boolean", "whether `--force` was given"),
                    Field("closed", "integer", "how many sessions `--force` closed"),
                ),
                methods=(
                    "hosts.status",
                    "epic.attach",
                    "epic.stop",
                    "epic.force",
                    "epic.detach",
                ),
                see=("epic status", "hosts stop"),
                run=_stop,
            ),
            Command(
                "board",
                "read the epic's board, or write a line of it",
                says="The board is the lines an epic keeps for its agents and its "
                "person. With no argument this prints it; with a key, that line; with "
                "a key and a value it writes the line as the person; `--remove` "
                "removes it.",
                args=(
                    Arg(("key",), "the key of one line", default=""),
                    Arg(("value",), "what to write on that line", default=""),
                    Arg(("--remove",), "remove the line instead of writing it"),
                    *_HOST,
                ),
                examples=(
                    Example("hmz epic board", "print the board"),
                    Example(
                        "hmz epic board deadline 'ship by Friday'",
                        "write the line `deadline`",
                    ),
                    Example("hmz epic board deadline --remove", "remove that line"),
                ),
                prints="One line per board line: key, value, whose it is and who "
                "wrote it. After writing or removing, one line saying so.",
                output=(
                    Field(
                        "items",
                        "list|null",
                        "when reading: the board's lines, or null where the epic has "
                        "no board",
                    ),
                    Field("items[].key", "string", "the key of the line"),
                    Field("items[].value", "string", "what the line says"),
                    Field("items[].about", "string", "what the line is about"),
                    Field(
                        "items[].whose",
                        "string",
                        "whose line it is: the person's or the flow's",
                    ),
                    Field("items[].by", "string", "who last wrote it"),
                    Field(
                        "items[].at",
                        "number",
                        "when it was last written, seconds since the Unix epoch",
                    ),
                    Field("key", "string", "when writing: the key of the line"),
                    Field(
                        "value",
                        "string",
                        "when writing: what was written, empty where removed",
                    ),
                ),
                methods=("hosts.status", "epic.attach", "epic.board", "epic.detach"),
                see=("epic status", "epic attach"),
                run=_board,
            ),
            Command(
                "claim",
                "claim roles and answer their questions from standard input",
                says="Claims one or more roles for as long as this command runs, so "
                "that no other frontend answers for them, and follows the epic as "
                "`hmz epic attach` does. Each line typed on standard input answers "
                "the oldest question waiting on those roles. The roles are released "
                "when the command ends.",
                args=(
                    Arg(("role",), "a role to claim", many=True),
                    Arg(
                        ("--take",),
                        "take a role from the frontend that claims it now",
                    ),
                    _REPLAY,
                    *_HOST,
                ),
                examples=(
                    Example(
                        "hmz epic claim reviewer",
                        "answer for `reviewer` from this terminal until the epic ends",
                    ),
                    Example(
                        "printf 'approve\\n' | hmz epic claim reviewer --take --json",
                        "take `reviewer`, answer its next question with `approve`, "
                        "and write the epic's messages as JSON lines",
                    ),
                ),
                prints="What `hmz epic attach` prints.",
                output=(
                    Field(
                        "type",
                        "string",
                        "what the message is, as `hmz epic attach --json` writes it",
                    ),
                ),
                exits=_FOLLOWED,
                methods=(
                    "hosts.status",
                    "epic.attach",
                    "epic.claim",
                    "epic.answer",
                    "epic.detach",
                ),
                see=("epic attach", "epic release", "epic answer"),
                run=_interruptible(_claim),
            ),
            Command(
                "release",
                "release a role another frontend claims",
                says="Takes a role from whichever frontend claims it and releases "
                "it, so that any frontend may answer its questions again.",
                args=(Arg(("role",), "the role to release"), *_HOST),
                examples=(
                    Example(
                        "hmz epic release reviewer",
                        "free `reviewer` from a window that was left open",
                    ),
                ),
                prints="One line naming the role released.",
                output=(Field("role", "string", "the role released"),),
                methods=(
                    "hosts.status",
                    "epic.attach",
                    "epic.claim",
                    "epic.release",
                    "epic.detach",
                ),
                see=("epic claim", "epic afk"),
                run=_release,
            ),
            Command(
                "afk",
                "set a role, or every role, away or back",
                says="A role that is away is not asked: its questions are answered "
                "with nothing at once, so the epic does not wait on a person. Away "
                "stays set after this command ends, until `--back`.",
                args=(
                    Arg(("role",), "the role, or every role", default=""),
                    Arg(("--back",), "set it back instead of away"),
                    *_HOST,
                ),
                examples=(
                    Example("hmz epic afk", "set every role away"),
                    Example("hmz epic afk reviewer --back", "set `reviewer` back"),
                ),
                prints="One line: away or back.",
                output=(
                    Field("away", "boolean", "whether it was set away"),
                    Field("role", "string", "the role, or empty for every role"),
                ),
                methods=("hosts.status", "epic.attach", "epic.afk", "epic.detach"),
                see=("epic answer", "epic claim"),
                run=_afk,
            ),
            Command(
                "status",
                "show what the epic's host is doing and which questions wait",
                says="Reads the status of the host without attaching to it: whether "
                "an epic is running, stopping or idle, which flow and task, and every "
                "question waiting on a person.",
                args=_HOST,
                examples=(
                    Example("hmz epic status", "show the epic of this folder"),
                    Example(
                        "hmz epic status --json | jq -r '.pending[].question'",
                        "print the ids of the questions waiting",
                    ),
                ),
                prints="One line with the state, flow, epic and task, then one line "
                "per waiting question: its id, role and text.",
                output=(
                    Field("workspace", "string", "the host's workspace"),
                    Field("slot", "string", "the host's slot"),
                    Field("pid", "integer", "the host's process id"),
                    Field("started", "string", "when the host started, ISO 8601"),
                    Field("state", "string", "`running`, `stopping` or `idle`"),
                    Field(
                        "run",
                        "integer",
                        "the number of the epic going, else of the last, or 0",
                    ),
                    Field(
                        "epic_kind",
                        "string",
                        "`flow` for an epic, `chat` for a chat, or empty for none",
                    ),
                    Field("flow", "string", "the epic's flow, as it was named"),
                    Field("epic", "string", "the name the epic is recorded under"),
                    Field("chat", "string", "the chat's name, on a chat's host"),
                    Field("task", "string", "the epic's task"),
                    Field("pending", "list", "the questions waiting on a person"),
                    Field("pending[].question", "string", "the question's id"),
                    Field("pending[].role", "string", "the role it is asked of"),
                    Field("pending[].text", "string", "what is asked"),
                    Field(
                        "pending[].mode",
                        "string",
                        "`ask` for a question, `listen` for one any line answers",
                    ),
                    Field(
                        "ended",
                        "object|null",
                        "how the last epic on this host ended, with `how` and `why`, "
                        "or null",
                    ),
                    Field("attached", "integer", "how many frontends are attached"),
                    Field(
                        "clients",
                        "list",
                        "the frontends attached, each with `client`, `name` and `kind`",
                    ),
                    Field(
                        "budget",
                        "object|null",
                        "the budget of the epic going, or null",
                    ),
                    Field(
                        "usage",
                        "object|null",
                        "what the epic going has spent, or null",
                    ),
                    Field("flows", "list", "the refs of the flow calls in progress"),
                    Field(
                        "calls",
                        "list",
                        "the flow calls in progress, oldest first",
                    ),
                ),
                methods=("hosts.status",),
                see=("epic attach", "hosts list"),
                run=_status,
            ),
        ),
    ),
)
