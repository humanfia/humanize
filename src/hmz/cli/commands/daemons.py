"""`hmz daemons`: the daemons of other machines this machine keeps, which `--daemon` names.

The one group of commands that asks no daemon anything to do its work: what it lists and
writes is the registry of Section 4.14 of python.md, kept on this machine by whoever reaches
other daemons from it -- this command line, the terminal interface, the SDK -- and not by any
daemon (Section 4.20.2 of daemon.md). `show --connect` and `pair` reach the daemon they name
over its routes, as `--daemon` does.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.cli.tree import Call
    from hmz.runtime.doing.daemons import Daemons

__all__ = ["COMMANDS"]

#: This machine's daemon, as the registry names it: always there, never written down.
_LOCAL: Mapping[str, Any] = {"name": "local", "id": "", "routes": ["unix:"]}


def _registry() -> Daemons:
    from hmz.runtime.doing.daemons import Daemons

    return Daemons()


def _row(one: Mapping[str, Any]) -> list[str]:
    return [str(one["name"]), str(one["id"]), " ".join(one["routes"])]


def _kept(name: str) -> dict[str, Any]:
    """The daemon kept under a name.

    Raises:
      hmz.sdk.Refused: If none is.
    """
    from hmz.sdk import Refused

    found = dict(_LOCAL) if name == _LOCAL["name"] else _registry().find(name)
    if found is None:
        raise Refused(t("There is no daemon {name}.", name=name), code=404)
    return found


def _free(name: str) -> None:
    """Refuses a name a daemon is kept under already."""
    from hmz.sdk import Refused

    if name == _LOCAL["name"] or _registry().find(name) is not None:
        raise Refused(t("There is already a daemon {name}.", name=name), code=409)


def _list(call: Call) -> None:
    daemons = [dict(_LOCAL), *_registry().all()]
    call.answers({"daemons": daemons}, table([_row(one) for one in daemons]))


def _add(call: Call) -> None:
    from hmz.sdk import Refused

    if not call.route:
        raise Refused(t("A daemon needs at least one route."), code=400)
    try:
        written = _registry().write(
            call.name,
            {"id": call.id, "routes": list(call.route)},
            replace=call.replace,
        )
    except FileExistsError as why:
        # Refused where it is written, under the lock: two adding one name keep the first.
        raise Refused(
            t("There is already a daemon {name}.", name=call.name), code=409
        ) from why
    except ValueError as why:
        raise Refused(str(why), code=400) from why
    except OSError as why:
        raise Refused(str(why), code=500) from why
    call.answers(written, [t("Saved") if call.replace else t("Added")])


def _remove(call: Call) -> None:
    from hmz.sdk import Refused

    _kept(call.name)
    try:
        _registry().remove(call.name)
    except LookupError as why:
        raise Refused(
            t("There is no daemon {name}.", name=call.name), code=404
        ) from why
    except ValueError as why:
        raise Refused(str(why), code=400) from why
    except OSError as why:
        raise Refused(str(why), code=500) from why
    call.answers({"name": call.name}, [t("Removed")])


def _show(call: Call) -> None:
    said: dict[str, Any] = _kept(call.name) | {"state": None, "version": None}
    if call.connect:
        from hmz.cli.tree import reach

        # Reached as `--daemon` reaches it: a daemon that cannot be is this command's failure.
        with reach(call.name) as client:
            said["state"], said["version"] = "up", client.version
            # The id it answered is pinned now, where none was.
            said["id"] = _kept(call.name)["id"] or client.daemon_id
    call.answers(
        said,
        table(
            [
                [name, value if isinstance(value, str) else " ".join(value)]
                for name, value in said.items()
                if value is not None
            ]
        ),
    )


def _pair(call: Call) -> None:
    from hmz.runtime.doing.daemons import Unreached
    from hmz.sdk import Refused

    if not call.replace:
        _free(call.name)
    code = sys.stdin.read().strip() if call.code == "-" else call.code
    remotes = _registry().remotes(kind="cli")
    try:
        written = remotes.pair(call.name, code, device=call.device)
    except ValueError as why:
        raise Refused(str(why), code=400) from why
    except Unreached as why:
        if why.status == _UNREACHED:
            raise ConnectionError(str(why)) from why
        raise Refused(str(why), code=why.status) from why
    except OSError as why:
        # Claimed, and then not written down: not a daemon that could not be reached.
        raise Refused(str(why), code=500) from why
    finally:
        remotes.close()
    call.answers(written, [t("Added")])


#: The status of a daemon no route opened to, as `Unreached` says it.
_UNREACHED = 503

_NAME = Arg(
    ("name",),
    "the name the daemon is kept under: letters, digits, ., _"
    " and -; it is what `--daemon` takes",
)

#: The fields of one daemon as it is kept.
_DAEMON = (
    Field("name", "string", "the name the daemon is kept under"),
    Field(
        "id",
        "string",
        "the daemon id pinned for it, or empty until it is first "
        "reached over a trusted route",
    ),
    Field("routes", "list", "its routes, in the order they are tried"),
)

COMMANDS = (
    Command(
        "daemons",
        "list, add, pair and remove the daemons of other machines",
        says="The daemons of other machines this machine can reach, "
        "each kept under a name with its routes. Give a name to "
        "`--daemon` on any command to ask that daemon.",
        commands=(
            Command(
                "list",
                "list this machine's daemon and the daemons of other machines",
                examples=(
                    Example("hmz daemons list", "list the daemons"),
                    Example(
                        "hmz daemons list --json | jq -r '.daemons[].name'",
                        "print the names `--daemon` takes",
                    ),
                ),
                prints="One line per daemon: its name, its daemon id where one "
                "is pinned, and its routes.",
                output=(
                    Field(
                        "daemons",
                        "list",
                        "this machine's daemon as `local` first, then every "
                        "daemon kept, in order",
                    ),
                    Field(
                        "daemons[].name", "string", "the name the daemon is kept under"
                    ),
                    Field(
                        "daemons[].id",
                        "string",
                        "the daemon id pinned for it, or empty until it is first "
                        "reached over a trusted route",
                    ),
                    Field(
                        "daemons[].routes",
                        "list",
                        "its routes, in the order they are tried",
                    ),
                ),
                see=("daemons add", "daemons pair", "daemons show"),
                run=_list,
            ),
            Command(
                "add",
                "add a daemon by its routes",
                says="Keeps a daemon under a name with its routes. A first "
                "route that is not ssh needs `--id`; a pairing code "
                "carries both, see `hmz daemons pair`.",
                args=(
                    _NAME,
                    Arg(
                        ("route",),
                        "a route, tried in the order given: "
                        "`stdio:ssh://[user@]host[:port]`, `tcp://host:port`, "
                        "`ws://…`, `wss://…`, `relay:wss://…`, `webrtc:wss://…` "
                        "or `easytier:<entry>`",
                        many=True,
                    ),
                    Arg(
                        ("--id",),
                        "the daemon id to pin, 52 characters, as the other "
                        "machine's daemon reports it; needed unless the first "
                        "route is ssh",
                        metavar="ID",
                        default="",
                    ),
                    Arg(
                        ("--replace",),
                        "write over the daemon already kept under this name",
                    ),
                ),
                examples=(
                    Example(
                        "hmz daemons add gpu stdio:ssh://gpu-box",
                        "add the host `gpu-box` of your SSH config as the daemon `gpu`",
                    ),
                    Example(
                        "hmz daemons add gpu stdio:ssh://me@10.0.0.7:2222 "
                        "tcp://10.0.0.7:41817",
                        "add a daemon reached over ssh first, then over a TCP port",
                    ),
                    Example(
                        "hmz daemons add lab easytier:lab --id "
                        "abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrst",
                        "add a daemon reached over the EasyTier entry `lab`, "
                        "pinning its daemon id",
                    ),
                    Example(
                        "hmz daemons add far relay:wss://relay.example/hmz "
                        "ws://far.example:8443 --id "
                        "abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrst",
                        "add a daemon reached through a relay, then over a "
                        "WebSocket, pinning its daemon id",
                    ),
                ),
                prints="The one word `Added`, or `Saved` with `--replace`.",
                output=_DAEMON,
                see=("daemons pair", "daemons show", "easytier set"),
                run=_add,
            ),
            Command(
                "remove",
                "forget how to reach one daemon",
                args=(_NAME,),
                examples=(
                    Example(
                        "hmz daemons remove gpu",
                        "remove the daemon `gpu` from the list; nothing on its "
                        "machine changes",
                    ),
                ),
                prints="The one word `Removed`.",
                output=(
                    Field("name", "string", "the name of the daemon that was removed"),
                ),
                see=("daemons list",),
                run=_remove,
            ),
            Command(
                "show",
                "print one daemon's id and routes, and with `--connect` reach it",
                args=(
                    _NAME,
                    Arg(
                        ("--connect",),
                        "reach the daemon over its routes and print its state and"
                        " hmz version; exits with status 3 where it cannot be "
                        "reached",
                    ),
                ),
                examples=(
                    Example(
                        "hmz daemons show gpu",
                        "print the routes kept for the daemon `gpu`",
                    ),
                    Example(
                        "hmz daemons show gpu --connect",
                        "check that the daemon `gpu` can be reached, and print "
                        "its version",
                    ),
                ),
                prints="One line per field: the field's name, then its value.",
                output=(
                    *_DAEMON,
                    Field(
                        "state",
                        "string|null",
                        "`up` once reached with `--connect`; null where it was "
                        "not asked",
                    ),
                    Field(
                        "version",
                        "string|null",
                        "the hmz version the daemon runs, where it was reached "
                        "with `--connect`; null otherwise",
                    ),
                ),
                see=("daemons list", "devices list"),
                run=_show,
            ),
            Command(
                "pair",
                "add a daemon from a pairing code made on its machine",
                says="Claims a pairing code `hmz devices pair` printed on the "
                "other machine: pairs this machine as a device of that "
                "daemon, and keeps the daemon under NAME.",
                args=(
                    _NAME,
                    Arg(
                        ("code",),
                        "the pairing code, which starts with `hmz-pair:`; or `-` "
                        "to read it from standard input",
                    ),
                    Arg(
                        ("--device",),
                        "the name this machine is paired as on that daemon; this "
                        "machine's host name where not given",
                        metavar="NAME",
                    ),
                    Arg(
                        ("--replace",),
                        "write over the daemon already kept under this name",
                    ),
                ),
                examples=(
                    Example(
                        "hmz daemons pair gpu hmz-pair:eyJ2IjoxLC…",
                        "claim a pairing code and keep its daemon as `gpu`",
                    ),
                    Example(
                        "ssh gpu-box hmz devices pair | hmz daemons pair gpu - "
                        "--device laptop",
                        "make a pairing code on `gpu-box` over ssh and claim it "
                        "here, pairing this machine as `laptop`",
                    ),
                ),
                prints="The one word `Added`.",
                output=_DAEMON,
                methods=("pair.claim",),
                see=("devices pair", "daemons list", "daemons show"),
                run=_pair,
            ),
        ),
    ),
)
