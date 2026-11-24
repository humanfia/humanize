"""`hmz hosts`: the hosts a daemon holds epics and chats in, listed and closed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.cli.commands.epic import placed
from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call

__all__ = ["COMMANDS"]


def _list(call: Call) -> None:
    hosts = call.client.hosts
    going = {(one.workspace, one.slot): one for one in hosts.running()}
    listed = [
        {
            "workspace": one.workspace,
            "slot": one.slot,
            "pid": one.pid,
            "started": one.started,
            "state": doing.state if doing else "idle",
            "kind": doing.kind if doing else "",
            "flow": doing.flow if doing else "",
            "epic": doing.epic if doing else "",
            "chat": doing.chat if doing else "",
            "task": doing.task if doing else "",
            "asking": list(doing.asking) if doing else [],
        }
        for one in hosts.list()
        for doing in [going.get((one.workspace, one.slot))]
        if doing or not call.running
    ]
    call.answers(
        {"hosts": listed},
        table(
            [
                [
                    str(one[key])
                    for key in ("workspace", "slot", "state", "flow", "task")
                ]
                for one in listed
            ]
        ),
    )


def _stop(call: Call) -> None:
    workspace = placed(call)
    call.client.hosts.stop(workspace, call.slot)
    call.answers({"workspace": workspace, "slot": call.slot}, [t("Host closed.")])


COMMANDS = (
    Command(
        "hosts",
        "list and close the hosts this daemon holds epics and chats in",
        says="A host is the process the daemon holds one workspace's epic, or one "
        "chat, in. It is named by its workspace and its slot: empty for the "
        "workspace's own host, `exec:<id>` for an epic beside it, `chat:<id>` for a "
        "chat.",
        commands=(
            Command(
                "list",
                "list the hosts and what each is running",
                args=(
                    Arg(
                        ("--running",),
                        "list only hosts whose epic or chat is running or stopping",
                    ),
                ),
                examples=(
                    Example("hmz hosts list", "list every host of this daemon"),
                    Example(
                        "hmz hosts list --running --json | jq -r '.hosts[] | "
                        "select(.asking != []) | .workspace'",
                        "print the workspaces whose epics wait on an answer",
                    ),
                ),
                prints="One line per host: workspace, slot, state, flow and task.",
                output=(
                    Field("hosts", "list", "the hosts, in the order they started"),
                    Field("hosts[].workspace", "string", "the host's workspace"),
                    Field(
                        "hosts[].slot",
                        "string",
                        "the host's slot, empty for the workspace's own host",
                    ),
                    Field("hosts[].pid", "integer", "the host's process id"),
                    Field(
                        "hosts[].started", "string", "when the host started, ISO 8601"
                    ),
                    Field("hosts[].state", "string", "`running`, `stopping` or `idle`"),
                    Field(
                        "hosts[].kind",
                        "string",
                        "`flow` for an epic, `chat` for a chat, empty when idle",
                    ),
                    Field("hosts[].flow", "string", "the flow of the epic going"),
                    Field(
                        "hosts[].epic",
                        "string",
                        "the name the epic going is recorded under",
                    ),
                    Field("hosts[].chat", "string", "the name of the chat going"),
                    Field(
                        "hosts[].task",
                        "string",
                        "the epic's task, or the chat's first message",
                    ),
                    Field(
                        "hosts[].asking",
                        "list",
                        "the questions it waits on, each `<run>:<question>`",
                    ),
                ),
                methods=("hosts.list", "hosts.running"),
                see=("epic status", "hosts stop"),
                run=_list,
            ),
            Command(
                "stop",
                "close a host, stopping what it runs",
                says="Closes the host of a workspace and slot. An epic or chat it is "
                "running is stopped first. To stop an epic and keep its host, use "
                "`hmz epic stop`.",
                args=(
                    Arg(
                        ("-w", "--workspace"),
                        "the host's workspace, a directory of the daemon's machine, "
                        "or the current directory",
                        metavar="DIR",
                    ),
                    Arg(
                        ("--slot",),
                        "the host's slot, as `hmz hosts list` prints it, or the "
                        "workspace's own host",
                        metavar="SLOT",
                        default="",
                    ),
                ),
                examples=(
                    Example("hmz hosts stop", "close the host of this directory"),
                    Example(
                        "hmz hosts stop -w ~/work/app --slot exec:1f2e",
                        "close the host of one epic of another workspace",
                    ),
                ),
                prints="One line once the daemon has taken the request.",
                output=(
                    Field("workspace", "string", "the workspace of the host closed"),
                    Field("slot", "string", "the slot of the host closed"),
                ),
                methods=("hosts.stop",),
                see=("hosts list", "epic stop"),
                run=_stop,
            ),
        ),
    ),
)
