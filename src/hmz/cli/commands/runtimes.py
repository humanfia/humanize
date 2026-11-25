"""`hmz runtimes`: the machines environments are made on, listed, written, asked and removed."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

from hmz.cli.tree import Arg, Command, Example, Exit, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.cli.tree import Call
    from hmz.sdk.families.runtimes import Listed, Runtime

__all__ = ["COMMANDS"]

#: The status `hmz runtimes check` ends with where the runtime did not answer.
UNANSWERED = 4


def _pair(said: str) -> tuple[str, str]:
    """One `--set`, as the field it names and the value it gives it."""
    name, equals, value = said.partition("=")
    if not name or not equals:
        raise argparse.ArgumentTypeError(t("{value} is not FIELD=VALUE.", value=said))
    return name, value


def _one(runtime: Runtime) -> dict[str, Any]:
    return {
        "backend": runtime.backend,
        "name": runtime.name,
        "made": runtime.made,
        "fields": runtime.fields,
    }


def _all(listed: Listed) -> dict[str, Any]:
    return {"runtimes": [_one(one) for one in listed.runtimes]}


def _shown(value: object) -> str:
    """A field's value as a line says it: text as it is, anything else as JSON."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _list(call: Call) -> None:
    listed = call.client.runtimes.list()
    call.answers(
        {"local": listed.local, **_all(listed), "blanks": listed.blanks},
        table(
            [
                ["local", str(listed.local.get("host", "")), ""],
                *([one.backend, one.name, one.made] for one in listed.runtimes),
            ]
        ),
    )


def _found(listed: Listed, backend: str, name: str) -> Runtime | None:
    return next(
        (one for one in listed.runtimes if (one.backend, one.name) == (backend, name)),
        None,
    )


def _show(call: Call) -> None:
    from hmz.sdk import Refused

    listed = call.client.runtimes.list()
    if call.backend not in listed.blanks:
        raise Refused(
            t(
                "{backend} is not a runtime backend; the backends are {backends}.",
                backend=call.backend,
                backends=", ".join(listed.blanks),
            ),
            code=400,
        )
    blank = listed.blanks[call.backend]
    if not call.name:
        said: dict[str, Any] = {
            "backend": call.backend,
            "name": None,
            "made": None,
            "fields": blank,
        }
    else:
        found = _found(listed, call.backend, call.name)
        if found is None:
            raise Refused(
                t(
                    "There is no {backend} runtime called {name}.",
                    backend=call.backend,
                    name=call.name,
                ),
                code=404,
            )
        said = _one(found) | {"fields": blank | found.fields}
    call.answers(
        said, [f"{name}={_shown(value)}" for name, value in said["fields"].items()]
    )


def _given(
    blank: Mapping[str, Any], fields: dict[str, Any], name: str, value: str
) -> None:
    """Puts one `--set` among a runtime's fields, read as the field's blank holds its value."""
    kind: object = blank.get(name, "")
    if isinstance(kind, (dict, list)):
        whole: object = None
        if value[:1] in ("{", "["):
            try:
                whole = json.loads(value)
            except ValueError:
                whole = None
        if isinstance(kind, dict):
            if not value or isinstance(whole, dict):
                fields[name] = whole or {}
            else:
                key, _, held = value.partition("=")
                fields[name] = {**_started(fields, name, {}), key: held}
        elif not value or isinstance(whole, list):
            fields[name] = whole or []
        else:
            fields[name] = [*_started(fields, name, []), value]
        return
    if isinstance(kind, (int, float)) and not isinstance(kind, bool):
        for number in (int, float):
            try:
                fields[name] = number(value)
            except ValueError:
                continue
            return
    # Text, or what the daemon is left to refuse in its own words.
    fields[name] = value


def _started(fields: Mapping[str, Any], name: str, empty: Any) -> Any:
    """What a field of many values holds so far on this line, which the next is added to."""
    held: object = fields.get(name)
    return held if isinstance(held, type(empty)) else empty


def _set(call: Call) -> None:
    runtimes = call.client.runtimes
    listed = runtimes.list()
    fields: dict[str, Any] = {}
    kept = _found(listed, call.backend, call.name) if call.replace else None
    if kept is not None:
        fields.update(kept.fields)
    blank = listed.blanks.get(call.backend, {})
    said: Sequence[tuple[str, str]] = call.set or ()
    # What this line says of a field of many values takes the place of what was written.
    for name in {name for name, _ in said}:
        fields.pop(name, None)
    for name, value in said:
        _given(blank, fields, name, value)
    after = runtimes.set(call.backend, call.name, fields, replace=call.replace)
    call.answers(_all(after), [t("Saved")])


def _remove(call: Call) -> None:
    after = call.client.runtimes.remove(call.backend, call.name)
    call.answers(_all(after), [t("Removed")])


def _check(call: Call) -> int:
    checked = call.client.runtimes.check(call.backend, call.name)
    call.answers(
        checked.said,
        table([[name, _shown(value)] for name, value in checked.said.items()]),
    )
    return 0 if checked.reached else UNANSWERED


def _hosts(call: Call) -> None:
    hosts = call.client.runtimes.hosts()
    call.answers(
        {"hosts": [one.said for one in hosts]},
        table(
            [
                [
                    one.alias,
                    one.host,
                    one.user,
                    str(one.port),
                    t("Saved") if one.saved else "",
                ]
                for one in hosts
            ]
        ),
    )


def _import(call: Call) -> None:
    after = call.client.runtimes.import_(call.host, update=call.update)
    call.answers(_all(after), [t("Imported")])


_BACKEND = Arg(
    ("backend",),
    "what kind of runtime it is: `ssh`, `docker`, `swarm`, "
    "`apple-container` or `slurm`",
)
_NAME = Arg(
    ("name",),
    "the name the runtime is written down under, as `hmz runtimes list` prints it",
)

#: The fields of the document every command that writes a runtime answers.
_RUNTIMES = (
    Field(
        "runtimes",
        "list",
        "every runtime written down after this command, in the daemon's order",
    ),
    Field(
        "runtimes[].backend",
        "string",
        "the runtime's backend: ssh, docker, swarm, apple-container or slurm",
    ),
    Field("runtimes[].name", "string", "the name the runtime is written down under"),
    Field(
        "runtimes[].made",
        "string",
        "how the runtime came to be written down: `typed`, or "
        "`imported` from the SSH config",
    ),
    Field(
        "runtimes[].fields",
        "object",
        "the runtime's other fields by name, as `--set` takes them",
    ),
)

COMMANDS = (
    Command(
        "runtimes",
        "list, write, check and remove the runtimes environments are put on",
        says="A runtime is a machine an environment runs on, other "
        "than the daemon's own. `-e` of `hmz exec` and `hmz chat`"
        " names it as `<backend>@<name>`.",
        commands=(
            Command(
                "list",
                "list the runtimes, and this machine",
                examples=(
                    Example("hmz runtimes list", "list the runtimes"),
                    Example(
                        "hmz runtimes list --json | jq '.blanks.ssh'",
                        "print every field an ssh runtime has, with its default",
                    ),
                ),
                prints="A first line for the daemon's own machine (`local` and "
                "its host name), then one line per runtime: backend, "
                "name, and how it was made.",
                output=(
                    Field(
                        "local",
                        "object",
                        "the daemon's own machine, where work runs that names no "
                        "runtime: host, system, machine, cpus, and memory in "
                        "bytes",
                    ),
                    *_RUNTIMES,
                    Field(
                        "blanks",
                        "object",
                        "for each backend, every field a runtime of it has, with "
                        "the value the field has when it is not set",
                    ),
                ),
                methods=("runtimes.list",),
                see=("runtimes show", "runtimes set", "runtimes check"),
                run=_list,
            ),
            Command(
                "show",
                "print one runtime's fields, or the fields a backend takes",
                says="Prints one runtime's fields as lines `field=value`, the "
                "form `--set` takes. Without NAME, prints the fields a "
                "new runtime of the backend starts with.",
                args=(
                    _BACKEND,
                    Arg(
                        ("name",),
                        "the runtime to print; left out, the fields a new runtime"
                        " of the backend starts with",
                        default="",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runtimes show ssh gpu-box",
                        "print the fields of the ssh runtime `gpu-box`",
                    ),
                    Example(
                        "hmz runtimes show docker",
                        "print every field a docker runtime takes, with its default",
                    ),
                ),
                prints="One line per field, `field=value`; a list or a mapping "
                "is written as JSON.",
                output=(
                    Field(
                        "backend",
                        "string",
                        "the runtime's backend: ssh, docker, swarm, "
                        "apple-container or slurm",
                    ),
                    Field(
                        "name",
                        "string|null",
                        "the runtime's name, or null where only a backend was named",
                    ),
                    Field(
                        "made",
                        "string|null",
                        "how the runtime was made, `typed` or `imported`, or null"
                        " where only a backend was named",
                    ),
                    Field(
                        "fields",
                        "object",
                        "every field of the runtime by name, the ones it does not"
                        " set at their defaults",
                    ),
                ),
                methods=("runtimes.list",),
                see=("runtimes set", "runtimes list"),
                run=_show,
            ),
            Command(
                "set",
                "add a runtime, or with `--replace` change one",
                says="Writes a runtime down. A name already written is refused"
                " unless `--replace` is given, which changes it and keeps"
                " the fields this line does not set.",
                args=(
                    _BACKEND,
                    _NAME,
                    Arg(
                        ("--set",),
                        "one field of the runtime, as `hmz runtimes show BACKEND`"
                        " lists them; repeat for each list item, and write "
                        "`FIELD=KEY=VALUE` for each pair of a mapping",
                        metavar="FIELD=VALUE",
                        many=True,
                        kind=_pair,
                    ),
                    Arg(
                        ("--replace",),
                        "change the runtime already written under this backend "
                        "and name, keeping the fields this line does not set",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runtimes set ssh gpu-box --set host=10.0.0.7 --set user=me "
                        "--set port=2222",
                        "add the ssh host 10.0.0.7 as the runtime `gpu-box`, "
                        "logging in as `me` on port 2222",
                    ),
                    Example(
                        "hmz runtimes set docker lab --set endpoint=ssh:gpu-box "
                        "--set image=ubuntu:24.04 --set gpus=0 --set gpus=1",
                        "add a docker runtime `lab` on the daemon reached through"
                        " the ssh runtime `gpu-box`, with a default image and "
                        "GPUs 0 and 1",
                    ),
                    Example(
                        "hmz runtimes set ssh gpu-box --replace "
                        "--set options=Compression=yes",
                        "change `gpu-box` to pass ssh the option "
                        "`Compression=yes`, keeping its other fields",
                    ),
                    Example(
                        "hmz runtimes set slurm cluster --set partition=gpu "
                        "--set account=lab --set time=04:00:00",
                        "add a Slurm runtime `cluster` on partition `gpu`, "
                        "account `lab`, with a four-hour time limit",
                    ),
                    Example(
                        "hmz runtimes set docker lab --replace --set gpus= "
                        """--set 'run_args=["--shm-size", "8g"]'""",
                        "change the docker runtime `lab`: clear its GPUs and give"
                        " its run arguments as a JSON array",
                    ),
                ),
                prints="The one word `Saved`.",
                output=_RUNTIMES,
                methods=("runtimes.list", "runtimes.set"),
                see=("runtimes show", "runtimes check", "runtimes remove"),
                run=_set,
            ),
            Command(
                "remove",
                "remove one runtime",
                args=(_BACKEND, _NAME),
                examples=(
                    Example(
                        "hmz runtimes remove ssh gpu-box",
                        "remove the ssh runtime `gpu-box`",
                    ),
                ),
                prints="The one word `Removed`.",
                output=_RUNTIMES,
                methods=("runtimes.remove",),
                see=("runtimes list",),
                run=_remove,
            ),
            Command(
                "check",
                "reach one runtime and print what it has",
                says="Reaches the runtime the way an environment put on it "
                "would, and prints what it has: CPUs, memory, GPUs, "
                "version, and what it is short of.",
                args=(_BACKEND, _NAME),
                examples=(
                    Example(
                        "hmz runtimes check ssh gpu-box",
                        "check that the ssh runtime `gpu-box` answers, and print "
                        "what it has",
                    ),
                    Example(
                        "hmz runtimes check docker lab --json | jq .gpus",
                        "print the GPUs the docker runtime `lab` reports",
                    ),
                ),
                prints="One line per field of the answer: the field's name, then"
                " its value.",
                output=(
                    Field("reached", "boolean", "whether the runtime answered at all"),
                    Field(
                        "said",
                        "string",
                        "why it did not answer, in its own words; empty where it did",
                    ),
                    Field(
                        "home",
                        "string",
                        "the home directory of the login, for an ssh host",
                    ),
                    Field("cpus", "number", "how many CPUs it has"),
                    Field("memory", "integer", "its memory in bytes"),
                    Field("gpus", "list", "its GPUs, by device id"),
                    Field(
                        "usable",
                        "list|null",
                        "the GPUs that answer, for a docker daemon whose host "
                        "could be asked; null where it could not",
                    ),
                    Field(
                        "gpu_memory",
                        "integer",
                        "the memory of its smallest GPU in bytes, or 0 where unknown",
                    ),
                    Field(
                        "runtimes",
                        "list",
                        "the OCI runtimes a docker daemon offers, its default first",
                    ),
                    Field(
                        "version",
                        "string",
                        "the version of the docker daemon, of Apple's container "
                        "system, or of Slurm",
                    ),
                    Field(
                        "short",
                        "list",
                        "what the runtime was written down as handing out that it"
                        " has not got",
                    ),
                    Field(
                        "nodes",
                        "list",
                        "the host names of a swarm's or a Slurm partition's nodes"
                        " that can be given work",
                    ),
                ),
                exits=(
                    Exit(
                        UNANSWERED,
                        "the runtime did not answer; its reason is in `said`",
                    ),
                ),
                methods=("runtimes.check",),
                see=("runtimes list", "runtimes set"),
                run=_check,
            ),
            Command(
                "hosts",
                "list the hosts of the SSH config on the daemon's machine",
                examples=(
                    Example("hmz runtimes hosts", "list the hosts of the SSH config"),
                    Example(
                        "hmz runtimes hosts --json | "
                        "jq -r '.hosts[] | select(.saved | not) | .alias'",
                        "print the hosts of the SSH config not yet saved as runtimes",
                    ),
                ),
                prints="One line per host: its alias, the machine it reaches, "
                "user, port, and `Saved` where an ssh runtime of its name"
                " is written down.",
                output=(
                    Field(
                        "hosts",
                        "list",
                        "every Host of ~/.ssh/config on the daemon's machine, as "
                        "ssh resolves it",
                    ),
                    Field(
                        "hosts[].alias",
                        "string",
                        "the name the SSH config gives the host",
                    ),
                    Field(
                        "hosts[].host", "string", "the machine it reaches (HostName)"
                    ),
                    Field("hosts[].user", "string", "the user it logs in as"),
                    Field("hosts[].port", "integer", "the port it dials"),
                    Field(
                        "hosts[].identity_files",
                        "list",
                        "the key files the SSH config names for it; empty where "
                        "ssh picks its own",
                    ),
                    Field(
                        "hosts[].proxy_jump",
                        "string",
                        "the host it is reached through, or empty",
                    ),
                    Field(
                        "hosts[].saved",
                        "boolean",
                        "whether an ssh runtime of that name is already written down",
                    ),
                ),
                methods=("runtimes.hosts",),
                see=("runtimes import",),
                run=_hosts,
            ),
            Command(
                "import",
                "import hosts from the SSH config as ssh runtimes",
                args=(
                    Arg(
                        ("host",),
                        "the hosts to import, each by its Host in the SSH config,"
                        " as `hmz runtimes hosts` prints it",
                        many=True,
                    ),
                    Arg(
                        ("--update",),
                        "write a runtime imported before again, as its host "
                        "stands in the SSH config now",
                    ),
                ),
                examples=(
                    Example(
                        "hmz runtimes import gpu-box build-box",
                        "import the hosts `gpu-box` and `build-box` of the SSH "
                        "config as ssh runtimes",
                    ),
                    Example(
                        "hmz runtimes import gpu-box --update",
                        "bring the runtime imported from `gpu-box` up to date "
                        "with the SSH config",
                    ),
                ),
                prints="The one word `Imported`.",
                output=_RUNTIMES,
                methods=("runtimes.import",),
                see=("runtimes hosts", "runtimes list"),
                run=_import,
            ),
        ),
    ),
)
