"""`hmz easytier`: the EasyTier networks a daemon's machine joins, and the shared nodes."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hmz.cli.tree import Call
    from hmz.sdk.families.easytier import Network

__all__ = ["COMMANDS"]


def _all(networks: Sequence[Network]) -> dict[str, Any]:
    return {
        "networks": [
            {"name": one.name, "nodes": list(one.nodes), "keyed": one.keyed}
            for one in networks
        ]
    }


def _list(call: Call) -> None:
    networks = call.client.easytier.list()
    call.answers(
        _all(networks),
        table(
            [
                [one.name, str(one.keyed).lower(), " ".join(one.nodes)]
                for one in networks
            ]
        ),
    )


def _secret(call: Call) -> str | None:
    """The secret a line gives, read from where it says: never from the line itself.

    Raises:
      hmz.sdk.Refused: For both places at once, or a variable that is not set.
    """
    from hmz.sdk import Refused

    if call.secret_stdin and call.secret_env:
        raise Refused(t("Give `--secret-stdin` or `--secret-env`, not both."), code=400)
    if call.secret_stdin:
        return sys.stdin.read().rstrip("\r\n")
    if call.secret_env:
        if call.secret_env not in os.environ:
            raise Refused(
                t("The environment variable {name} is not set.", name=call.secret_env),
                code=400,
            )
        return os.environ[call.secret_env]
    return None


def _set(call: Call) -> None:
    # Read before any daemon is asked anything: a line refused here calls nothing.
    secret = _secret(call)
    easytier = call.client.easytier
    nodes: Sequence[str] = call.node or ()
    if not nodes:
        # Written again with its secret alone: the nodes it has stay.
        nodes = next(
            (one.nodes for one in easytier.list() if one.name == call.name), ()
        )
    call.answers(_all(easytier.set(call.name, nodes, secret=secret)), [t("Saved")])


def _remove(call: Call) -> None:
    call.answers(_all(call.client.easytier.remove(call.name)), [t("Removed")])


def _nodes(call: Call) -> None:
    nodes = call.client.easytier.nodes()
    call.answers(
        {
            "nodes": [
                {
                    "url": one.url,
                    "name": one.name,
                    "version": one.version,
                    "up": one.up,
                    "uptime": one.uptime,
                }
                for one in nodes
            ]
        },
        table(
            [
                [
                    one.url,
                    "" if one.up is None else t("up@@node") if one.up else t("down"),
                    ""
                    if one.uptime is None
                    else t("{uptime} up in 24h", uptime=f"{one.uptime:.0%}"),
                    one.version,
                    one.name,
                ]
                for one in nodes
            ]
        ),
    )


_NAME = Arg(
    ("name",),
    "the name of the EasyTier entry, which a route or a "
    "listener names as `easytier:<name>`: letters, digits, .,"
    " _ and -",
)

#: The fields of the document every command that lists or writes an entry answers.
_NETWORKS = (
    Field("networks", "list", "every EasyTier entry after this command"),
    Field("networks[].name", "string", "the name of the EasyTier entry"),
    Field(
        "networks[].nodes",
        "list",
        "the shared nodes the network meets through, each a URL "
        "such as tcp://host:port",
    ),
    Field(
        "networks[].keyed",
        "boolean",
        "whether a secret is written for the entry; the secret itself is never printed",
    ),
)

COMMANDS = (
    Command(
        "easytier",
        "list, write and remove this machine's EasyTier networks",
        says="An EasyTier entry names one private network: a secret "
        "and the shared nodes machines meet through. Machines "
        "sharing a secret and a node reach each other without "
        "open ports.",
        commands=(
            Command(
                "list",
                "list the EasyTier entries, without their secrets",
                examples=(
                    Example("hmz easytier list", "list the EasyTier entries"),
                    Example(
                        "hmz easytier list --json | jq -r '.networks[].name'",
                        "print the names of the EasyTier entries",
                    ),
                ),
                prints="One line per entry: its name, `true` or `false` for "
                "whether a secret is written, and its nodes.",
                output=_NETWORKS,
                methods=("easytier.list",),
                see=("easytier set", "easytier nodes"),
                run=_list,
            ),
            Command(
                "set",
                "add an EasyTier entry, or change its nodes or secret",
                says="Writes an EasyTier entry. A new entry needs a node and a"
                " secret of at least 16 bytes; written again, it keeps "
                "any secret and nodes not given here.",
                args=(
                    _NAME,
                    Arg(
                        ("--node",),
                        "a shared node the network meets through, as "
                        "`tcp://host:port` (or udp, ws, wss, quic or wg); `hmz "
                        "easytier nodes` lists ones to use",
                        metavar="URL",
                        many=True,
                    ),
                    Arg(
                        ("--secret-stdin",),
                        "read the secret from standard input; a secret is never "
                        "taken from the command line and never printed",
                    ),
                    Arg(
                        ("--secret-env",),
                        "read the secret from the environment variable VAR",
                        metavar="VAR",
                    ),
                ),
                examples=(
                    Example(
                        "openssl rand -hex 24 | hmz easytier set lab "
                        "--node tcp://public.easytier.top:11010 --secret-stdin",
                        "add the entry `lab` with a new random secret read from "
                        "standard input",
                    ),
                    Example(
                        "hmz easytier set lab --node tcp://public.easytier.top:11010 "
                        "--secret-env LAB_SECRET",
                        "add the entry `lab` with the secret in the environment "
                        "variable `LAB_SECRET`",
                    ),
                    Example(
                        "hmz easytier set lab --node tcp://a.example:11010 "
                        "--node udp://b.example:11010",
                        "change the nodes of `lab`, keeping its secret",
                    ),
                ),
                prints="The one word `Saved`.",
                output=_NETWORKS,
                methods=("easytier.list", "easytier.set"),
                see=("easytier nodes", "easytier list", "daemons add"),
                run=_set,
            ),
            Command(
                "remove",
                "remove an EasyTier entry the daemon does not listen on",
                args=(_NAME,),
                examples=(
                    Example(
                        "hmz easytier remove lab", "remove the EasyTier entry `lab`"
                    ),
                ),
                prints="The one word `Removed`.",
                output=_NETWORKS,
                methods=("easytier.remove",),
                see=("easytier list",),
                run=_remove,
            ),
            Command(
                "nodes",
                "list the shared EasyTier nodes to choose from",
                examples=(
                    Example(
                        "hmz easytier nodes",
                        "list the shared nodes and how each has stood",
                    ),
                    Example(
                        "hmz easytier nodes --json | "
                        "jq -r '.nodes[] | select(.up) | .url'",
                        "print the URLs of the shared nodes that are up",
                    ),
                ),
                prints="One line per node: its URL, whether it is up, its uptime"
                " over 24 hours, its EasyTier version, and its name.",
                output=(
                    Field("nodes", "list", "the shared EasyTier nodes on offer"),
                    Field("nodes[].url", "string", "the URL to give `--node`"),
                    Field(
                        "nodes[].name",
                        "string",
                        "what the node's monitor calls it: where it is and who runs it",
                    ),
                    Field(
                        "nodes[].version",
                        "string",
                        "the EasyTier version it runs, or empty where unknown",
                    ),
                    Field(
                        "nodes[].up",
                        "boolean|null",
                        "whether it answered last, or null where unknown",
                    ),
                    Field(
                        "nodes[].uptime",
                        "number|null",
                        "the share of the last 24 hours it was up, from 0 to 1, "
                        "or null where unknown",
                    ),
                ),
                methods=("easytier.nodes",),
                see=("easytier set",),
                run=_nodes,
            ),
        ),
    ),
)
