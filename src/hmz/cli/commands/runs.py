"""`hmz runs`: the epics a daemon wrote down, listed, read back, exported, imported and totalled.

What the web page's search, its Exomyth view, its Export and Import and its usage settings
read, for a line: each command is one method of `runs.*`, or two where a file crosses the
session (`files.*`), and prints what the daemon answered. What a field is called is the
daemon's name for it, in text as in JSON, so that what a person reads off a terminal is what a
program asks `jq` for.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import TYPE_CHECKING, Any, Final

from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence

    from hmz.cli.tree import Call

__all__ = ["COMMANDS", "fields", "folder", "local"]

#: How an epic went, as `runs.list` finds epics by it.
_STATUSES: Final = ("running", "done", "failed", "stopped", "unfinished")

#: What a timeline counts time in, to the second.
_MICRO: Final = 1e6


def folder(said: str | None) -> str | None:
    """A workspace as a line named it, as the daemon is told it: its folder's whole path."""
    return None if said is None else os.path.abspath(os.path.expanduser(said))  # noqa: PTH100, PTH111 -- no link followed: the daemon reads it


@contextlib.contextmanager
def local() -> Generator[None]:
    """A block that reads or writes a file of this machine, refused where it cannot.

    A file that is not there is no daemon that cannot be reached, which is what an `OSError`
    out of a command is taken for.

    Raises:
      hmz.sdk.Refused: With what the system said of the file.
    """
    from hmz.sdk import Refused

    try:
        yield
    except TimeoutError:
        raise
    except OSError as why:
        raise Refused(str(why)) from why


def _value(value: object) -> str:
    """One field's value on a line of its own."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return t("yes") if value else t("no")
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def fields(document: Mapping[str, Any], last: str, *, whole: bool = False) -> list[str]:
    """A document a field a line, its name and then its value, and one field last and whole.

    Args:
      document: What the daemon answered.
      last: The field put after the others, under its name, indented.
      whole: Whether that field is written as indented JSON; as the text it is otherwise.
    """
    lines = table(
        [[name, _value(value)] for name, value in document.items() if name != last]
    )
    if last in document:
        said = document[last]
        text = (
            json.dumps(said, ensure_ascii=False, indent=2) if whole else str(said or "")
        )
        lines += [last, *(f"  {line}" for line in text.splitlines())]
    return lines


def _list(call: Call) -> None:
    found = call.client.runs.list(
        workspace=folder(call.workspace),
        status=call.status,
        flow=call.flow,
        query=call.query,
        offset=call.offset,
        limit=call.limit,
    )
    call.answers(
        {
            "runs": found.runs,
            "total": found.total,
            "offset": found.offset,
            "limit": found.limit,
            "counts": found.counts,
            "flows": found.flows,
        },
        table(
            [
                [one["name"], one["how"], one["flow"], one["began"], one["task"]]
                for one in found.runs
            ]
        ),
    )
    shown = found.offset + len(found.runs)
    if not call.json and found.runs and shown < found.total:
        said = t(
            "{shown} of {n} epics listed; pass `--offset {next}` for the next ones.",
            shown=len(found.runs),
            n=found.total,
            next=shown,
        )
        print(said, file=sys.stderr)


def _show(call: Call) -> None:
    one = call.client.runs.get(call.name)
    call.answers(one, fields(one, "task"))


def _trace(call: Call) -> None:
    sessions = call.client.runs.trace(call.name)
    lines: list[str] = []
    for session in sessions:
        lines.append(f"{session['key']}  {session['agent']}".rstrip())
        actions = [
            [
                str(action["at"]),
                f"{action['seconds']:.3f}",
                str(action["category"]),
                str(action["name"]),
            ]
            for action in session["actions"]
        ]
        lines.extend(f"  {line}" for line in table(actions))
    call.answers({"sessions": sessions}, lines)


def _seconds(micros: float) -> str:
    return f"{micros / _MICRO:.3f}"


def _spans(track: Mapping[str, Any], strings: Sequence[str]) -> list[list[str]]:
    """Every span of a track as a row: its id, start, duration, category and name."""
    columns: Mapping[str, Sequence[int]] = track["spans"]
    return [
        [
            str(track["first"] + at),
            _seconds(columns["start"][at]),
            _seconds(columns["dur"][at]),
            strings[columns["cat"][at]],
            strings[columns["name"][at]],
        ]
        for at in range(track["count"])
    ]


def _timeline(call: Call) -> None:
    laid = call.client.runs.timeline(call.name)
    strings: Sequence[str] = laid["strings"]
    tracks: Sequence[Mapping[str, Any]] = laid["tracks"]
    lines: list[str] = []
    processes: Sequence[Mapping[str, Any]] = laid["processes"]
    for process in processes:
        said = [
            str(process["id"]),
            str(process["kind"]),
            strings[int(process["name"])],
            strings[int(process["label"])],
            _seconds(process["start"]),
            _seconds(process["end"]),
        ]
        lines.append("  ".join(one for one in said if one))
        for index in process["tracks"]:
            track = tracks[int(index)]
            count: int = track["count"]
            counted = (
                t("{count} span", count=count)
                if count == 1
                else t("{count} spans", count=count)
            )
            lines.append(f"  {strings[int(track['name'])]}  {counted}".rstrip())
            if call.spans:
                lines.extend(f"    {line}" for line in table(_spans(track, strings)))
    call.answers(laid, lines)


def _span(call: Call) -> None:
    one = call.client.runs.span(call.name, call.id, call.layout)
    call.answers(one, fields(one, "args", whole=True))


def _export(call: Call) -> None:
    client = call.client
    with local():
        out = client.runs.export(call.name, call.output)
    call.answers(
        {"path": str(out.path), "filename": out.filename, "size": out.size},
        [str(out.path)],
    )


def _import(call: Call) -> None:
    client = call.client
    if call.there:
        got = client.runs.imported(path=call.file)
    else:
        with local():
            got = client.runs.import_(call.file)
    lines = [t("Imported {name}", name=got.name)]
    if not got.resumable and got.why:
        lines.append(t("Imported · not resumable here: {why}", why=got.why))
    call.answers(
        {
            "name": got.name,
            "workspace": got.workspace,
            "resumable": got.resumable,
            "why": got.why,
        },
        lines,
    )


def _figures(one: Mapping[str, Any]) -> list[str]:
    return [str(one["runs"]), one["money"], one["tokens"], one["worked"]]


def _usage(call: Call) -> None:
    said = call.client.runs.usage(days=call.days, workspace=folder(call.workspace))
    counted = [t("Epics"), t("Cost"), t("Output tokens"), t("Time working")]
    rows = [[t("Flow"), *counted]]
    rows += [[one["flow"], *_figures(one)] for one in said["flows"]]
    rows += [[t("Day"), *counted]]
    rows += [[one["day"], *_figures(one)] for one in said["days"] if one["runs"]]
    rows += [[t("Total"), *_figures(said["whole"])]]
    call.answers(said, table(rows))


_NAME: Final = Arg(("name",), "the epic's name, as `hmz runs list` prints it")

#: The fields of an epic row, which a listing holds many of and one epic read back is.
_ROW: Final = (
    ("name", "string", "the epic's name"),
    ("workspace", "string", "path of the workspace folder the epic ran in"),
    ("folderless", "boolean", "whether that workspace has no folder of its own"),
    ("kind", "string", "always `flow`"),
    ("flow", "string", "the flow the epic ran"),
    ("task", "string", "the first line of the epic's task, cut at 240 characters"),
    ("began", "string", "when the epic began, ISO 8601"),
    (
        "ended",
        "string",
        "when the epic ended, ISO 8601, or an empty string while it has not",
    ),
    (
        "how",
        "string",
        "its status: `running`, `done`, `failed`, `stopped` or `unfinished`",
    ),
    (
        "agents",
        "list",
        "the epic's agents, each with `name`, `role` and `runs` (what it was started as)",
    ),
    ("sessions", "integer", "how many sessions the epic opened"),
    ("resumable", "boolean", "whether the epic's flow can be resumed"),
    (
        "spent",
        "object|null",
        (
            "what the epic spent (cost, tokens, seconds, and each as text), or null where "
            "nothing was counted"
        ),
    ),
    ("held", "boolean", "whether a host of this daemon is running the epic now"),
    ("slot", "string", "the slot of the host running the epic, or an empty string"),
    (
        "asking",
        "list",
        "the questions the running epic waits on, each as `<run>:<question>`",
    ),
    ("backup", "list", "names of the backup targets the epic was started with"),
    (
        "backed",
        "object",
        "the last backup to each target, by target name, each with `at`, `ok`, `error` and `why`",
    ),
)

#: What one epic read back says of itself that a row of a listing does not, or says otherwise.
_WHOLE: Final = {
    "task": Field("task", "string", "the epic's whole task"),
    "agents": Field(
        "agents",
        "list",
        "the epic's agents, each with `name`, `role`, `runs`, `backend`, `model`, `effort` and "
        "`provider`",
    ),
    "sessions": Field(
        "sessions",
        "list",
        "the sessions the epic opened, each with `agent`, `backend`, `provider`, `ident`, "
        "`name`, `at`, `flow`, `parent` and `harness`",
    ),
}

COMMANDS = (
    Command(
        "runs",
        "list, read back, export and import epics, and total their spend",
        says="A daemon writes down every epic it runs. `hmz runs` lists them, reads one back, "
        "exports or imports `.hmzepic` files, and totals what epics spent.",
        commands=(
            Command(
                "list",
                "list the epics written down, newest first",
                args=(
                    Arg(
                        ("--workspace",),
                        "list only the epics of the workspace at this folder path; every "
                        "workspace when not given",
                        metavar="PATH",
                    ),
                    Arg(
                        ("--status",),
                        "list only the epics with this status",
                        metavar="STATUS",
                        choices=_STATUSES,
                    ),
                    Arg(
                        ("--flow",), "list only the epics of this flow", metavar="NAME"
                    ),
                    Arg(
                        ("-q", "--query"),
                        "list only the epics whose task, flow or name contains this text",
                        metavar="TEXT",
                    ),
                    Arg(
                        ("--offset",),
                        "how many of the newest matching epics to skip",
                        metavar="N",
                        kind=int,
                    ),
                    Arg(
                        ("--limit",),
                        "the most epics to list, from 1 to 200",
                        metavar="N",
                        kind=int,
                        default=50,
                    ),
                ),
                examples=(
                    Example(
                        "hmz runs list", "lists the newest 50 epics of every workspace"
                    ),
                    Example(
                        "hmz runs list --status failed --flow ralph_loop -q parser",
                        "lists the failed epics of the flow ralph_loop whose task mentions parser",
                    ),
                    Example(
                        "hmz runs list --json | jq -r '.runs[].name'",
                        "lists the epics as JSON and prints their names with jq",
                    ),
                ),
                prints="One line per epic, newest first: name, status, flow, when it began, "
                "first line of its task. Where more match than were listed, standard error says "
                "so.",
                output=(
                    Field("runs", "list", "the epics listed, newest first"),
                    *(Field(f"runs[].{name}", kind, says) for name, kind, says in _ROW),
                    Field("total", "integer", "how many epics match the filters"),
                    Field("offset", "integer", "how many matching epics were skipped"),
                    Field("limit", "integer", "the most epics this answer lists"),
                    Field(
                        "counts",
                        "object",
                        "how many epics there are of each status, over every epic, by status",
                    ),
                    Field(
                        "flows", "list", "the name of every flow an epic ran, sorted"
                    ),
                ),
                methods=("runs.list",),
                see=("runs show", "runs usage", "backup list"),
                run=_list,
            ),
            Command(
                "show",
                "read back an epic's task, agents, sessions, spend and backups",
                args=(_NAME,),
                examples=(
                    Example(
                        "hmz runs show 20261012T091500.123Z-1a2b3c",
                        "prints what was written down of that epic",
                    ),
                    Example(
                        "hmz runs show NAME --json | jq .backed",
                        "prints how the last backup of the epic to each target went",
                    ),
                ),
                prints="Prints one line per field, the field's name and then its value, with "
                "the whole task last.",
                output=(
                    *(
                        _WHOLE.get(name, Field(name, kind, says))
                        for name, kind, says in _ROW
                    ),
                    Field(
                        "at",
                        "string",
                        "path of the directory the epic is written down in, on the daemon's "
                        "machine",
                    ),
                    Field("ref", "string", "the ref the epic's flow was started by"),
                    Field("envs", "list", "the environments the epic was started with"),
                    Field("used", "list", "the environments the epic used"),
                    Field("params", "object", "the params the epic was started with"),
                    Field(
                        "budget",
                        "object|null",
                        "the budget the epic was started with, or null for none",
                    ),
                    Field(
                        "picked_up",
                        "string",
                        "name of the epic this one resumed from, or an empty string",
                    ),
                    Field(
                        "profile_flow",
                        "boolean",
                        "whether the flow's own Python was profiled",
                    ),
                    Field(
                        "profile_environment",
                        "boolean",
                        "whether the programs its agents ran were profiled",
                    ),
                    Field(
                        "picks_up",
                        "boolean",
                        "whether a new epic can resume from this one",
                    ),
                    Field(
                        "foreign",
                        "string",
                        "why an imported epic cannot be resumed on this machine, or an empty "
                        "string",
                    ),
                    Field(
                        "calls",
                        "list",
                        "the tree of flows the epic called, each with `flow`, `task`, `began`, "
                        "`ended`, `how` and `calls`",
                    ),
                ),
                methods=("runs.get",),
                see=("runs list", "runs trace", "runs timeline", "backup run"),
                run=_show,
            ),
            Command(
                "trace",
                "print what each session of an epic said and did",
                says="Reads the logs the epic's agents kept and prints every action of every "
                "harness session: turns, model calls, tool calls, what was said. Slow for a "
                "long epic.",
                args=(_NAME,),
                examples=(
                    Example(
                        "hmz runs trace NAME",
                        "prints every session of the epic and its actions in order",
                    ),
                    Example(
                        "hmz runs trace NAME --json | jq -r '.sessions[].actions[] | "
                        'select(.category == "tool") | .name\'',
                        "prints the name of every tool call of the epic",
                    ),
                ),
                prints="One line per harness session with its key and agent, then an indented "
                "line per action: when it started, seconds taken, category, name.",
                output=(
                    Field(
                        "sessions",
                        "list",
                        "the sessions that did anything, in the order they started",
                    ),
                    Field(
                        "sessions[].key",
                        "string",
                        "the session, as `<harness>:<session id>`",
                    ),
                    Field(
                        "sessions[].agent", "string", "the agent the session belongs to"
                    ),
                    Field(
                        "sessions[].actions", "list", "what the session did, in order"
                    ),
                    Field(
                        "sessions[].actions[].category",
                        "string",
                        "the kind of action, such as `turn`, `llm` or `tool`",
                    ),
                    Field(
                        "sessions[].actions[].name",
                        "string",
                        "what the action was: the tool called, the model asked",
                    ),
                    Field(
                        "sessions[].actions[].at",
                        "string",
                        "when the action started, ISO 8601",
                    ),
                    Field(
                        "sessions[].actions[].start",
                        "number",
                        "when the action started, in seconds on the trace's clock",
                    ),
                    Field(
                        "sessions[].actions[].seconds",
                        "number",
                        "how long the action took, in seconds",
                    ),
                    Field(
                        "sessions[].actions[].args",
                        "object",
                        "everything else the action carried, such as its input, its output and "
                        "its tokens",
                    ),
                ),
                methods=("runs.trace",),
                see=("runs timeline", "runs show"),
                run=_trace,
            ),
            Command(
                "timeline",
                "print an epic's Exomyth timeline: processes, tracks and spans",
                says="Lays the epic out as the Exomyth view draws it: a process for the flow, "
                "each harness session and each profiled program, each with tracks of spans.",
                args=(
                    _NAME,
                    Arg(
                        ("--spans",),
                        "also print every span under its track, with its id",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runs timeline NAME",
                        "prints the processes and tracks of the epic's timeline",
                    ),
                    Example(
                        "hmz runs timeline NAME --spans",
                        "also prints every span with the id `hmz runs span` takes",
                    ),
                    Example(
                        "hmz runs timeline NAME --json | jq .summary",
                        "prints the counts and time of the timeline by category",
                    ),
                ),
                prints="`hmz runs timeline` prints a line per process, and under it a line per "
                "track; with `--spans`, it prints each span too.",
                output=(
                    Field(
                        "version", "integer", "the version of the timeline document, 1"
                    ),
                    Field(
                        "layout",
                        "string",
                        "what identifies this laying out; span ids are good only with it",
                    ),
                    Field("epic", "string", "the epic's name"),
                    Field(
                        "origin",
                        "number",
                        "the earliest moment in the timeline, in seconds since the Unix epoch",
                    ),
                    Field("live", "boolean", "whether the epic has not ended yet"),
                    Field(
                        "strings",
                        "list",
                        "every text of the document once; other text fields are indexes into "
                        "this list",
                    ),
                    Field(
                        "processes",
                        "list",
                        "the processes, each with `id`, `kind`, `name`, `label`, `start`, "
                        "`end`, `parent` and `tracks`; times are microseconds from `origin`",
                    ),
                    Field(
                        "tracks",
                        "list",
                        "the tracks, each with `process`, `name`, `first`, `count`, `depths` "
                        "and `spans`, the columns of its spans; a span's id is `first` plus its "
                        "index",
                    ),
                    Field(
                        "spawns",
                        "object",
                        "which span started which process, as two columns `span` and `process`",
                    ),
                    Field(
                        "summary",
                        "object",
                        "start and end, process, track and span counts, and count, time and "
                        "tokens by category",
                    ),
                ),
                methods=("runs.timeline",),
                see=("runs span", "runs trace"),
                run=_timeline,
            ),
            Command(
                "span",
                "print one span of an epic's timeline, with everything it carried",
                says="Prints one span whole: a model call with its prompt and answer, a tool "
                "call with its input and output. Without `--layout`, the timeline is laid out "
                "first.",
                args=(
                    _NAME,
                    Arg(
                        ("id",),
                        "the span's id, as `hmz runs timeline --spans` prints it",
                        kind=int,
                    ),
                    Arg(
                        ("--layout",),
                        "the `layout` of the timeline the id was read from; refused if the epic "
                        "has been laid out again since",
                        metavar="LAYOUT",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runs span NAME 42",
                        "prints span 42 of the epic's timeline as it is laid out now",
                    ),
                    Example(
                        "hmz runs span NAME 42 --layout a1ed23f784909965 --json",
                        "prints span 42 as JSON, only if the timeline is still laid out as when "
                        "the id was read",
                    ),
                ),
                prints="One line per field of the span, the field's name and then its value, "
                "and what it carried as indented JSON.",
                output=(
                    Field("id", "integer", "the span's id"),
                    Field(
                        "process", "integer", "id of the process the span belongs to"
                    ),
                    Field("track", "integer", "index of the track the span is on"),
                    Field(
                        "start",
                        "integer",
                        "when the span started, in microseconds from the timeline's origin",
                    ),
                    Field(
                        "dur", "integer", "how long the span lasted, in microseconds"
                    ),
                    Field(
                        "depth", "integer", "how deeply the span is nested on its track"
                    ),
                    Field(
                        "cat",
                        "string",
                        "the span's category, such as `turn`, `llm` or `tool`",
                    ),
                    Field("name", "string", "the span's name"),
                    Field("at", "string", "when the span started, ISO 8601 UTC"),
                    Field(
                        "args",
                        "object",
                        "everything the span carried, such as its input, its output and its tokens",
                    ),
                ),
                methods=("runs.timeline", "runs.span"),
                see=("runs timeline",),
                run=_span,
            ),
            Command(
                "export",
                "export one epic to a `.hmzepic` file on this machine",
                says="The daemon packs the epic into one `.hmzepic` archive, credentials struck "
                "out, written on the machine this command runs on. `hmz runs import` reads it "
                "back.",
                args=(
                    _NAME,
                    Arg(
                        ("-o", "--output"),
                        "the file to write, or a directory to write it into; `<name>.hmzepic` "
                        "in the current directory when not given; an existing file is replaced",
                        metavar="FILE",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runs export NAME",
                        "writes NAME.hmzepic in the current directory",
                    ),
                    Example(
                        "hmz runs export NAME -o ~/epics/",
                        "writes the archive into the directory ~/epics",
                    ),
                ),
                prints="Prints the path of the file written.",
                output=(
                    Field("path", "string", "absolute path of the file written"),
                    Field(
                        "filename",
                        "string",
                        "the name the daemon gave the archive, `<name>.hmzepic`",
                    ),
                    Field("size", "integer", "the archive's size in bytes"),
                ),
                methods=("runs.bundle", "files.read", "files.close"),
                see=("runs import", "backup run"),
                run=_export,
            ),
            Command(
                "import",
                "import an epic from a `.hmzepic` file",
                says="Sends the file to the daemon, which writes the epic down under the "
                "workspace it ran in. An epic already there is refused.",
                args=(
                    Arg(
                        ("file",),
                        "the `.hmzepic` file to import; with `--there`, its absolute path on "
                        "the daemon's machine",
                    ),
                    Arg(
                        ("--there",),
                        "have the daemon read the file from that path on its own machine rather "
                        "than sending it",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runs import NAME.hmzepic",
                        "sends the file to the daemon and imports the epic",
                    ),
                    Example(
                        "hmz runs import /srv/epics/NAME.hmzepic --there --daemon lab",
                        "has the daemon `lab` import a file already on its own machine",
                    ),
                ),
                prints="Prints the imported epic's name, and why it cannot be resumed here when "
                "it cannot.",
                output=(
                    Field("name", "string", "name of the imported epic"),
                    Field(
                        "workspace",
                        "string",
                        "path of the workspace folder the epic is kept under",
                    ),
                    Field(
                        "resumable",
                        "boolean",
                        "whether the imported epic can be resumed on this daemon",
                    ),
                    Field(
                        "why",
                        "string",
                        "why it cannot be resumed here, or an empty string",
                    ),
                ),
                methods=("files.create", "files.write", "files.close", "runs.import"),
                see=("runs export", "backup pull"),
                run=_import,
            ),
            Command(
                "usage",
                "total what chats and epics spent, by flow and by day",
                args=(
                    Arg(
                        ("--days",),
                        "how many days back to count, today included, from 1 to 365",
                        metavar="N",
                        kind=int,
                        default=30,
                    ),
                    Arg(
                        ("--workspace",),
                        "count only the chats and epics of the workspace at this folder",
                        metavar="PATH",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runs usage",
                        "totals what the last 30 days of chats and epics spent",
                    ),
                    Example(
                        "hmz runs usage --days 7 --workspace . --json | jq .whole.cost",
                        "prints the dollars this workspace spent in the last seven days",
                    ),
                ),
                prints="A table of flows, costliest first, a table of the days something ran, "
                "then the total: epics, cost, output tokens, time working. Chats count as the "
                "flow `chat`.",
                output=(
                    Field("days_back", "integer", "how many days were counted"),
                    Field(
                        "days",
                        "list",
                        "one entry per UTC day, oldest first, each with `day` and the figures "
                        "of `whole`",
                    ),
                    Field(
                        "flows",
                        "list",
                        "one entry per flow, costliest first, each with `flow` and the figures "
                        "of `whole`",
                    ),
                    Field(
                        "ended",
                        "object",
                        "how many chats and epics ended each way, by status",
                    ),
                    Field("whole", "object", "the totals over everything counted"),
                    Field(
                        "whole.runs", "integer", "how many chats and epics were counted"
                    ),
                    Field("whole.cost", "number", "what they cost, in US dollars"),
                    Field(
                        "whole.output_tokens",
                        "integer",
                        "how many output tokens they wrote",
                    ),
                    Field(
                        "whole.seconds",
                        "number",
                        "how many seconds their agents worked",
                    ),
                    Field("whole.money", "string", "the cost as text, such as `$1.25`"),
                    Field(
                        "whole.tokens",
                        "string",
                        "the output tokens as text, such as `12.5k`",
                    ),
                    Field(
                        "whole.worked",
                        "string",
                        "the time working as text, such as `3m 20s`",
                    ),
                ),
                methods=("runs.usage",),
                see=("runs list",),
                run=_usage,
            ),
        ),
    ),
)
