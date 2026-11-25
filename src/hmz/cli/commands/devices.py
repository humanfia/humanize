"""`hmz devices`: the devices paired with a daemon, and the codes they are paired by."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call

__all__ = ["COMMANDS"]


def _list(call: Call) -> None:
    devices = call.client.devices.list()
    call.answers(
        {
            "devices": [
                {
                    "name": one.name,
                    "fingerprint": one.fingerprint,
                    "added": one.added,
                    "seen": one.seen,
                }
                for one in devices
            ]
        },
        table(
            [[one.name, one.fingerprint, one.added, one.seen or ""] for one in devices]
        ),
    )


def _revoke(call: Call) -> None:
    dropped = call.client.devices.revoke(call.name)
    call.answers(
        {"dropped": dropped},
        [t("Device revoked ({n} sessions closed).", n=dropped)],
    )


def _pair(call: Call) -> None:
    import datetime

    code = call.client.devices.pair(routes=call.route, seconds=call.seconds)
    call.answers({"code": code.code, "expires": code.expires}, [code.code])
    if not call.json:
        until = datetime.datetime.fromtimestamp(code.expires).astimezone()
        said = t(
            "Claim this code on the device before {time}.",
            time=f"{until:%Y-%m-%d %H:%M:%S %Z}",
        )
        print(said, file=sys.stderr)


COMMANDS = (
    Command(
        "devices",
        "list and revoke the devices paired with this daemon",
        says="A paired device is a phone, browser or other machine let in to this daemon by "
        "claiming a pairing code. These commands list them and revoke one.",
        commands=(
            Command(
                "list",
                "list the paired devices",
                examples=(
                    Example("hmz devices list", "list the paired devices"),
                    Example(
                        "hmz devices list --json | jq -r '.devices[].name'",
                        "list the paired devices as JSON and print their names with jq",
                    ),
                ),
                prints="One line per device: name, fingerprint, when it was paired, when it "
                "was last seen.",
                output=(
                    Field("devices", "list", "the paired devices"),
                    Field(
                        "devices[].name", "string", "the name the device was paired as"
                    ),
                    Field(
                        "devices[].fingerprint",
                        "string",
                        "fingerprint of the device's certificate",
                    ),
                    Field("devices[].added", "string", "when it was paired, ISO 8601"),
                    Field(
                        "devices[].seen",
                        "string|null",
                        "when it last opened a session, ISO 8601, or null if never",
                    ),
                ),
                methods=("devices.list",),
                see=("devices revoke", "devices pair"),
                run=_list,
            ),
            Command(
                "revoke",
                "revoke one paired device and close its open sessions",
                args=(
                    Arg(
                        ("name",),
                        "the name the device was paired as, as `hmz devices list` prints it",
                    ),
                ),
                examples=(
                    Example(
                        "hmz devices revoke phone",
                        "revoke the device paired as `phone`",
                    ),
                ),
                prints="How many sessions were closed.",
                output=(
                    Field(
                        "dropped",
                        "integer",
                        "how many of the device's open sessions were closed",
                    ),
                ),
                methods=("devices.revoke",),
                see=("devices list",),
                run=_revoke,
            ),
            Command(
                "pair",
                "make a pairing code for one device to claim",
                says="Prints a one-time pairing code. Enter it on the device (in Settings > "
                "Daemons, or the desktop app) before it expires.",
                args=(
                    Arg(
                        ("--route",),
                        "a route the code carries to reach this daemon, or those it listens on",
                        metavar="ROUTE",
                        many=True,
                    ),
                    Arg(
                        ("--seconds",),
                        "how long the code can be claimed for, in seconds",
                        metavar="N",
                        kind=int,
                    ),
                ),
                examples=(
                    Example(
                        "hmz devices pair --seconds 600",
                        "make a pairing code that can be claimed for ten minutes",
                    ),
                ),
                prints="The code alone on standard output, and when it expires on standard "
                "error.",
                output=(
                    Field("code", "string", "the pairing code"),
                    Field(
                        "expires",
                        "integer",
                        "when the code stops being claimable, seconds since the Unix epoch",
                    ),
                ),
                methods=("pair.create",),
                see=("devices list",),
                run=_pair,
            ),
        ),
    ),
)
