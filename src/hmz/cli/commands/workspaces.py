"""`hmz workspaces`: the folders a daemon knows as workspaces, and its machine's folders to pick."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call

__all__ = ["COMMANDS"]


def _at(said: str) -> str:
    """A folder as the daemon is told it: whole, one written from here taken from here."""
    return said if said.startswith(("/", "~")) else str(Path(said).absolute())


def _list(call: Call) -> None:
    known = call.client.workspaces.list(str(Path.cwd()))
    rows = [
        [
            one.path,
            str(one.epics),
            str(one.chats),
            one.last or "-",
            ", ".join(
                said
                for said, so in (
                    (t("running"), one.running),
                    (t("missing"), not one.there),
                )
                if so
            ),
        ]
        for one in known.workspaces
    ]
    call.answers(known.answer, table(rows))
    if not rows and not call.json:
        print(t("No folders"), file=sys.stderr)


def _add(call: Call) -> None:
    known = call.client.workspaces.add(_at(call.folder), str(Path.cwd()))
    call.answers(known.answer, [known.kept])


def _forget(call: Call) -> None:
    known = call.client.workspaces.forget(_at(call.folder), str(Path.cwd()))
    call.answers(known.answer, [t("Forgotten")])


def _browse(call: Call) -> None:
    # A directory of a runtime's machine is that machine's to read, as it was written.
    found = call.client.paths.list(
        call.directory if call.env else _at(call.directory),
        files=call.files or None,
        hidden=call.hidden or None,
        env=call.env,
    )
    under = found.whole.rstrip("/")
    call.answers(
        found.answer,
        [f"{under}/{one.name}{'/' if one.dir else ''}" for one in found.entries],
    )
    if found.more and not call.json:
        print(t("{n} more", n=found.more), file=sys.stderr)


def _complete(call: Call) -> None:
    # What is typed from here is completed from here, not from where the daemon stands.
    typed: str = call.typed
    if not typed.startswith(("/", "~")):
        typed = f"{Path.cwd()}/{typed}"
    paths = call.client.paths.complete(typed)
    call.answers({"paths": paths}, paths)


#: What `workspaces.list` answers, which `add` and `forget` answer too.
_KNOWN = (
    Field(
        "here", "string", "the absolute path of the directory the command was run in"
    ),
    Field("workspaces", "list", "the workspaces"),
    Field("workspaces[].path", "string", "the absolute path of the folder"),
    Field("workspaces[].name", "string", "the name of the folder"),
    Field("workspaces[].epics", "integer", "how many epics ran there"),
    Field("workspaces[].chats", "integer", "how many chats it has"),
    Field(
        "workspaces[].last",
        "string",
        "when its latest epic or chat began, ISO 8601, or empty",
    ),
    Field(
        "workspaces[].running", "boolean", "whether an epic or chat is running there"
    ),
    Field(
        "workspaces[].here",
        "boolean",
        "whether it is the directory the command was run in",
    ),
    Field("workspaces[].there", "boolean", "whether the folder still exists"),
)

COMMANDS = (
    Command(
        "workspaces",
        "list, add and forget workspaces, and browse the daemon's folders",
        says="A workspace is a folder on the daemon's machine that epics "
        "run in and chats belong to. These commands list the "
        "workspaces, add a folder as one, forget one, and browse or "
        "complete folder paths on the daemon's machine to choose one.",
        commands=(
            Command(
                "list",
                "list the workspaces",
                examples=(
                    Example("hmz workspaces list", "list the workspaces"),
                    Example(
                        "hmz workspaces list --json "
                        "| jq -r '.workspaces[] | select(.running) | .path'",
                        "print the paths of the workspaces with an epic running, "
                        "with jq",
                    ),
                ),
                prints="One line per workspace: its path, how many epics and how "
                "many chats it has, when the latest began, and whether it is "
                "running or its folder is missing; the current directory "
                "comes first, then the running ones, then the most recent.",
                output=_KNOWN,
                methods=("workspaces.list",),
                see=("workspaces add", "workspaces forget"),
                run=_list,
            ),
            Command(
                "add",
                "add a folder on the daemon's machine as a workspace",
                args=(
                    Arg(
                        ("folder",),
                        "the folder, which must exist on the daemon's machine; a "
                        "relative path is taken from the current directory",
                        metavar="PATH",
                    ),
                ),
                examples=(
                    Example(
                        "hmz workspaces add .",
                        "add the current directory as a workspace",
                    ),
                    Example(
                        "hmz workspaces add ~/code/app --json | jq -r .kept",
                        "add the folder ~/code/app as a workspace and print its "
                        "absolute path as JSON",
                    ),
                ),
                prints="The absolute path of the workspace added.",
                output=(
                    Field("kept", "string", "the absolute path of the workspace added"),
                    *_KNOWN,
                ),
                methods=("workspaces.add",),
                see=("workspaces browse", "workspaces list"),
                run=_add,
            ),
            Command(
                "forget",
                "forget what a workspace was set up with",
                says="Forgets the settings kept for a workspace, the set-up of "
                "each flow included. A workspace nothing ran in leaves the "
                "list; its folder, epics and chats are not touched.",
                args=(
                    Arg(
                        ("folder",),
                        "the workspace, as `hmz workspaces list` prints it; the "
                        "folder need not exist any more",
                        metavar="PATH",
                    ),
                ),
                examples=(
                    Example(
                        "hmz workspaces forget ~/code/old",
                        "forget the workspace ~/code/old",
                    ),
                    Example(
                        "hmz workspaces forget . --json",
                        "forget the current directory's set-up and print the "
                        "workspaces left as JSON",
                    ),
                ),
                prints="One word saying it was forgotten.",
                output=_KNOWN,
                methods=("workspaces.forget",),
                see=("workspaces list", "flows setup"),
                run=_forget,
            ),
            Command(
                "browse",
                "list the folders in a directory of the daemon's machine",
                says="Lists one directory of the machine the daemon runs on, to "
                "find the folder to give `hmz workspaces add` or `-w`. With "
                "`--env`, lists a directory of the machine a runtime is on.",
                args=(
                    Arg(
                        ("directory",),
                        "the directory to list, `~` being the home directory there; "
                        "the home directory when not given",
                        metavar="PATH",
                        default="~",
                    ),
                    Arg(("--files",), "list files as well as folders"),
                    Arg(("--hidden",), "list names that start with a dot as well"),
                    Arg(
                        ("--env",),
                        "list the directory on the machine of a runtime, written as "
                        "`-e` writes one with no directory, for example `ssh@NAME`",
                        metavar="ENV",
                    ),
                ),
                examples=(
                    Example(
                        "hmz workspaces browse",
                        "list the folders in the home directory of the daemon's "
                        "machine",
                    ),
                    Example(
                        "hmz workspaces browse ~/code --files --hidden",
                        "list the folders and files in ~/code, hidden ones included",
                    ),
                    Example(
                        "hmz workspaces browse /srv --env ssh@box",
                        "list the folders in /srv on the machine of the ssh runtime "
                        "`box`",
                    ),
                ),
                prints="One absolute path per line, folders first and ending in "
                "`/`; at most 500, and how many were left out on standard "
                "error.",
                output=(
                    Field(
                        "at",
                        "string",
                        "the folder listed, written from `~` where it is under the "
                        "home directory",
                    ),
                    Field("whole", "string", "its absolute path"),
                    Field("up", "string", "its parent folder, or empty at the root"),
                    Field(
                        "entries", "list", "what is in it, folders first, at most 500"
                    ),
                    Field("entries[].name", "string", "the name of the entry"),
                    Field("entries[].dir", "boolean", "whether the entry is a folder"),
                    Field("more", "integer", "how many entries were left out"),
                ),
                methods=("paths.list",),
                see=("workspaces complete", "workspaces add"),
                run=_browse,
            ),
            Command(
                "complete",
                "complete a partly typed folder path on the daemon's machine",
                args=(
                    Arg(
                        ("typed",),
                        "the start of a path, as far as it has been typed, such as "
                        "`~/co`",
                    ),
                ),
                examples=(
                    Example(
                        "hmz workspaces complete '~/co'",
                        "list the folders whose path starts with `~/co`",
                    ),
                    Example(
                        "hmz workspaces complete /srv/ --json",
                        "print the completions of `/srv/` as a JSON list",
                    ),
                ),
                prints="Prints one folder per line that the typed text could "
                "become, written as it was typed and ending in `/`, at most "
                "50.",
                output=(
                    Field(
                        "paths",
                        "list",
                        "the folders the typed text could become, sorted, at most 50",
                    ),
                ),
                methods=("paths.complete",),
                see=("workspaces browse", "workspaces add"),
                run=_complete,
            ),
        ),
    ),
)
