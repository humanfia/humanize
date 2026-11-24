"""`hmz backup`: an epic backed up to git repositories now, and one brought back down.

What the web page's Upload and its Download do, for a line, and each through the daemon: the
upload is the daemon's (`runs.backup`), which queues it and says at once which targets it goes
to, and how each went is read back off the epic, where the daemon writes it; what a target
holds is asked of the daemon (`backups.epics`), which fetches the repository; and one of those
is downloaded onto the daemon's machine (`backups.pull`), as an import would land it.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from typing import TYPE_CHECKING, Final

from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call

__all__ = ["COMMANDS"]

#: How much of a task a listing shows, on its one line.
_TASK: Final = 60


def _run(call: Call) -> None:
    from hmz.sdk import Refused

    # Nothing to wait is not waiting: the daemon is asked once either way.
    waits = not call.no_wait and call.timeout > 0
    try:
        went = call.client.runs.backup(
            call.epic, to=call.to, wait=call.timeout if waits else 0
        )
    except TimeoutError:
        said = t(
            "The backup of {name} did not finish within {seconds} seconds, and carries on in "
            "the daemon.",
            name=call.epic,
            seconds=call.timeout,
        )
        raise TimeoutError(said) from None
    if not waits:
        call.answers(
            {"queued": list(went), "backed": {}},
            [t("Uploading to {targets}", targets=", ".join(went))],
        )
        return
    took = [
        t("{name}: uploaded {when}", name=name, when=one["at"])
        for name, one in went.items()
        if one["ok"]
    ]
    failed = [
        t(
            "{name}: failed, {error} {when}",
            name=name,
            error=one["error"],
            when=one["at"],
        )
        for name, one in went.items()
        if not one["ok"]
    ]
    if failed:
        # One document under `--json`, and that one the error; the targets that took it are
        # still said to somebody reading.
        if not call.json:
            for line in took:
                print(line)
        raise Refused(" · ".join(failed))
    call.answers({"queued": list(went), "backed": went}, took)


def _list(call: Call) -> None:
    if call.target is None:
        targets = call.client.backups.targets()
        call.answers(
            {
                "targets": [
                    {
                        "name": one.name,
                        "url": one.url,
                        "branch": one.branch,
                        "policies": list(one.policies),
                        "every": one.every,
                    }
                    for one in targets
                ],
                "defaults": [one.name for one in targets if one.default],
            },
            table(
                [
                    [
                        one.name,
                        one.url,
                        one.branch,
                        ",".join(one.policies),
                        "default" if one.default else "",
                    ]
                    for one in targets
                ]
            ),
        )
        if not targets and not call.json:
            print(t("No backup target."), file=sys.stderr)
        return
    held = call.client.backups.epics(call.target)
    rows: list[list[str]] = []
    for one in held:
        task = " ".join(one.task.split())
        rows.append(
            [
                one.key,
                one.how or t("unfinished"),
                t("chat") if one.chat else one.flow,
                "here" if one.here else "",
                task if len(task) <= _TASK else f"{task[: _TASK - 1]}…",
            ]
        )
    call.answers({"epics": [asdict(one) for one in held]}, table(rows))


def _pull(call: Call) -> None:
    from hmz.sdk import Refused

    client = call.client
    key: str = call.key
    if "/" not in key:
        # A name alone: whichever one the target holds of it, where it holds only one.
        found = [
            one.key for one in client.backups.epics(call.target) if one.epic == key
        ]
        if not found:
            raise Refused(
                t(
                    "{target} holds no epic or chat {name}.",
                    target=call.target,
                    name=key,
                )
            )
        if len(found) > 1:
            said = t(
                "{target} holds {name} from more than one machine, name one of: {keys}.",
                target=call.target,
                name=key,
                keys=", ".join(found),
            )
            raise Refused(said)
        key = found[0]
    name = client.backups.pull(call.target, key)
    call.answers({"name": name}, [name])


COMMANDS = (
    Command(
        "backup",
        "back epics up to git repositories, and download them again",
        says="A backup target is a git repository set in Settings > Backup. These commands "
        "upload an epic to targets, list targets and what one holds, and download from one.",
        commands=(
            Command(
                "run",
                "back one epic up to backup targets now",
                says="Uploads the epic to the targets it was started with, else the default "
                "targets, and waits to say how each went. Interrupting this command does not "
                "stop the upload.",
                args=(
                    Arg(("epic",), "the epic's name, as `hmz runs list` prints it"),
                    Arg(
                        ("--to",),
                        "a backup target to upload to, as `hmz backup list` prints it; when not "
                        "given, the targets the epic was started with, else the default targets",
                        metavar="NAME",
                        many=True,
                    ),
                    Arg(
                        ("--no-wait",),
                        "return once the daemon has queued the uploads, without waiting to hear "
                        "how they went",
                    ),
                    Arg(
                        ("--timeout",),
                        "how many seconds to wait for the uploads to finish",
                        metavar="SECONDS",
                        kind=int,
                        default=600,
                    ),
                ),
                examples=(
                    Example(
                        "hmz backup run 20261012T091500.123Z-1a2b3c",
                        "uploads the epic to its own targets, or the default ones, and waits "
                        "for the result",
                    ),
                    Example(
                        "hmz backup run NAME --to lab --to home",
                        "uploads the epic to the targets `lab` and `home`",
                    ),
                    Example(
                        "hmz backup run NAME --no-wait --json",
                        "queues the uploads and prints the targets queued, as JSON",
                    ),
                ),
                prints="Prints one line per target that took the epic. A target that did not is "
                "reported as the command's error, and the command exits `1`.",
                output=(
                    Field(
                        "queued",
                        "list",
                        "names of the targets the upload was queued for",
                    ),
                    Field(
                        "backed",
                        "object",
                        "how each upload went, by target name, with `at`, `ok`, `error` and "
                        "`why`; empty with `--no-wait`",
                    ),
                ),
                methods=("runs.backup", "runs.get"),
                see=("backup list", "runs show"),
                run=_run,
            ),
            Command(
                "list",
                "list the backup targets, or the epics and chats one target holds",
                says="Without `--target` it lists the backup targets set up on this daemon. "
                "With `--target` it fetches that repository and lists every epic and chat it "
                "holds, from every machine.",
                args=(
                    Arg(
                        ("--target",),
                        "the backup target whose epics and chats to list; the targets "
                        "themselves are listed when not given",
                        metavar="NAME",
                    ),
                ),
                examples=(
                    Example("hmz backup list", "lists the backup targets"),
                    Example(
                        "hmz backup list --target lab",
                        "lists the epics and chats the target lab holds",
                    ),
                    Example(
                        "hmz backup list --target lab --json | jq -r "
                        "'.epics[] | select(.here | not) | .key'",
                        "prints the key of every epic lab holds that this machine does not",
                    ),
                ),
                prints="Line per target: name, URL, branch, policies, `default` where it is "
                "one. With `--target`, line per epic or chat: key, status, flow or `chat`, "
                "`here` if held here, task.",
                output=(
                    Field(
                        "targets",
                        "list",
                        "without `--target`: the backup targets, each with `name`, `url`, "
                        "`branch`, `policies` and `every`",
                    ),
                    Field(
                        "defaults",
                        "list",
                        "without `--target`: names of the targets an epic is backed up to when "
                        "it names none",
                    ),
                    Field(
                        "epics",
                        "list",
                        "with `--target`: the epics and chats the target holds, newest first",
                    ),
                    Field(
                        "epics[].key",
                        "string",
                        "what `hmz backup pull` takes: `<machine>/<workspace>/<epic>`",
                    ),
                    Field("epics[].machine", "string", "the machine the epic ran on"),
                    Field(
                        "epics[].workspace", "string", "the workspace the epic ran in"
                    ),
                    Field("epics[].epic", "string", "the epic's name, or the chat's"),
                    Field(
                        "epics[].flow",
                        "string",
                        "the flow the epic ran, or an empty string for a chat",
                    ),
                    Field(
                        "epics[].task",
                        "string",
                        "the epic's task, or the chat's first message",
                    ),
                    Field("epics[].began", "string", "when it began, ISO 8601"),
                    Field(
                        "epics[].ended",
                        "string",
                        "when it ended, ISO 8601, or an empty string",
                    ),
                    Field(
                        "epics[].how",
                        "string",
                        "how it ended, or an empty string where it had not when backed up",
                    ),
                    Field(
                        "epics[].head",
                        "string",
                        "the commit of the target that holds it",
                    ),
                    Field(
                        "epics[].chat",
                        "boolean",
                        "whether it is a chat rather than an epic",
                    ),
                    Field(
                        "epics[].here",
                        "boolean",
                        "whether this machine already holds it",
                    ),
                ),
                methods=("settings.get", "backups.epics"),
                see=("backup pull", "backup run"),
                run=_list,
            ),
            Command(
                "pull",
                "download one epic or chat from a backup target",
                says="Fetches the target and writes the epic down on this daemon as an import "
                "does; a chat goes among the chats. One this machine already holds is refused.",
                args=(
                    Arg(
                        ("key",),
                        "the epic or chat, as `<machine>/<workspace>/<epic>` or, where only one "
                        "in the target has it, its name alone; `hmz backup list --target` "
                        "prints both",
                    ),
                    Arg(
                        ("--target",),
                        "the backup target to download from, as `hmz backup list` prints it",
                        metavar="NAME",
                        required=True,
                    ),
                ),
                examples=(
                    Example(
                        "hmz backup pull laptop/project/20261012T091500.123Z-1a2b3c "
                        "--target lab",
                        "downloads that epic of the machine laptop from the target lab",
                    ),
                    Example(
                        "hmz backup pull 20261012T091500.123Z-1a2b3c --target lab --json",
                        "downloads the one epic of that name lab holds and prints its name as JSON",
                    ),
                ),
                prints="The name of the epic or chat downloaded.",
                output=(
                    Field("name", "string", "name of the epic or chat downloaded"),
                ),
                methods=("backups.epics", "backups.pull"),
                see=("backup list", "runs import"),
                run=_pull,
            ),
        ),
    ),
)
