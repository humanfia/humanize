"""`hmz hosts`: the hosts a daemon holds epics and chats in, listed and closed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.cli.tree import WORKSPACE, Arg, Command, Example, Field, table, workspace
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


def _open(call: Call) -> None:
    host = call.client.hosts.open(workspace(call), call.slot)
    said = {key: host.get(key) for key in _OPENED}
    call.answers(
        said, table([[str(said[key]) for key in ("pid", "workspace", "slot")]])
    )


def _detach(call: Call) -> None:
    at = workspace(call)
    let_go = call.client.hosts.detach(at, call.slot)
    call.answers(
        {"workspace": at, "slot": call.slot, "let_go": let_go},
        [t("{n} frontends let go.", n=let_go)],
    )


def _stop(call: Call) -> None:
    at = workspace(call)
    call.client.hosts.stop(at, call.slot)
    call.answers({"workspace": at, "slot": call.slot}, [t("Host closed.")])


#: What `hosts.open` answers of a host, as `hmz hosts open --json` writes it.
_OPENED = ("pid", "workspace", "started", "kind", "protocol", "slot")

_SLOT = Arg(
    ("--slot",),
    "the host's slot, as `hmz hosts list` prints it, or the workspace's own host",
    metavar="SLOT",
    default="",
)


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
                "open",
                "start the host of a workspace without attaching to it",
                says="Starts the host of a workspace and slot where the daemon holds "
                "none, and attaches nothing to it; a host already held is answered as "
                "it is. `--slot exec:` or `--slot chat:` alone makes a new slot of "
                "that kind and prints the slot made. An epic is then started on it "
                "with `hmz epic start`.",
                args=(
                    WORKSPACE,
                    Arg(
                        ("--slot",),
                        "the slot to open, as `hmz hosts list` prints it; `exec:` or "
                        "`chat:` alone for a new slot of that kind; when not given, "
                        "the workspace's own host",
                        metavar="SLOT",
                        default="",
                    ),
                ),
                examples=(
                    Example("hmz hosts open", "start the host of this folder"),
                    Example(
                        "hmz hosts open --slot exec: --json | jq -r .slot",
                        "make a new exec slot in this folder and print its name",
                    ),
                ),
                prints="Prints one line with the host's process id, workspace and slot.",
                output=(
                    Field("pid", "integer", "the host's process id"),
                    Field("workspace", "string", "the host's workspace"),
                    Field("started", "string", "when the host started, ISO 8601"),
                    Field("kind", "string", "what the process is, always `host`"),
                    Field(
                        "protocol",
                        "string",
                        "the version of the protocol the host speaks",
                    ),
                    Field("slot", "string", "the host's slot"),
                ),
                methods=("hosts.open",),
                see=("epic start", "hosts list", "hosts stop"),
                run=_open,
            ),
            Command(
                "detach",
                "let every frontend of a host go, leaving its epic running",
                says="Lets go every frontend attached to the host of a workspace and "
                "slot -- every web page, terminal interface and command following it "
                "-- and leaves its epic or chat running. Roles the frontends had "
                "claimed are released. A frontend may attach again.",
                args=(WORKSPACE, _SLOT),
                examples=(
                    Example(
                        "hmz hosts detach",
                        "let go every frontend of the host of this folder",
                    ),
                    Example(
                        "hmz hosts detach --json | jq .let_go",
                        "print how many frontends were let go",
                    ),
                ),
                prints="Prints one line saying how many frontends were let go.",
                output=(
                    Field("workspace", "string", "the workspace of the host"),
                    Field("slot", "string", "the slot of the host"),
                    Field("let_go", "integer", "how many frontends were let go"),
                ),
                methods=("hosts.detach",),
                see=("hosts list", "epic attach", "hosts stop"),
                run=_detach,
            ),
            Command(
                "stop",
                "close a host, stopping what it runs",
                says="Closes the host of a workspace and slot. An epic or chat it is "
                "running is stopped first. To stop an epic and keep its host, use "
                "`hmz epic stop`.",
                args=(WORKSPACE, _SLOT),
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
