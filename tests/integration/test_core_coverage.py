"""Whatever a daemon does, a program can ask for and a command line can type.

`protocol/openrpc.json` says every method a daemon serves. Each is named by exactly one family
of the SDK, which is what makes it something a program can do with names and types; and each is
called by at least one declared command, which is what makes it something a person, a script
or an agent can do from a shell -- but for the few written down here, each with why no command
is the place for it. And every command there is has its section of the protocol and its line of
the reference.
"""

from __future__ import annotations

import inspect
import json
import pkgutil
import re
from collections import Counter
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import hmz.sdk.families
from hmz import cli
from hmz.cli import tree
from hmz.sdk.families import Family

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.cli.tree import Command

ROOT = Path(__file__).resolve().parents[2]

#: What opens, cancels and describes a session itself: the client's own, under every call.
SESSION = {"session.hello", "session.cancel", "rpc.discover"}

#: The methods no declared command calls, and why none does.
UNTYPED = {
    "epic.aside": (
        "which side conversation a frontend has open is state of a frontend that stays; a "
        "command that ends holds none, and `hmz btw` asks a side question through `btw.ask`"
    ),
    "epic.unaside": (
        "closes a side conversation of the frontend that opened it, which a command that "
        "ends never has open"
    ),
    "hosts.env.read": (
        "`hmz env cat` reads the same file through `env.read`, which also reads it whole "
        "against the etag it was first read with"
    ),
    "hosts.env.write": (
        "`hmz env write` writes the same file through `env.write`, against what was read"
    ),
    "hosts.env.grep": (
        "`hmz env search` searches the same environment through `env.search`"
    ),
}


def _served() -> set[str]:
    """Every method of the wire protocol but the session's own."""
    document = json.loads((ROOT / "protocol" / "openrpc.json").read_text("utf-8"))
    return {method["name"] for method in document["methods"]} - SESSION


def _families() -> Iterator[type[Family]]:
    """Every family there is: each class of a module of the package that names methods."""
    for module in pkgutil.iter_modules(hmz.sdk.families.__path__):
        held = import_module(f"{hmz.sdk.families.__name__}.{module.name}")
        for _, one in inspect.getmembers(held, inspect.isclass):
            if (
                issubclass(one, Family)
                and one.__module__ == held.__name__
                and "METHODS" in vars(one)
            ):
                yield one


def _leaves(path: tuple[str, ...], command: Command) -> Iterator[tuple[str, Command]]:
    if not command.commands:
        yield " ".join(path), command
    for one in command.commands:
        yield from _leaves((*path, one.name), one)


def _typed() -> dict[str, list[str]]:
    """Each method some declared command calls, with the commands that call it."""
    calls: dict[str, list[str]] = {}
    for name, command in tree.commands().items():
        for line, leaf in _leaves((name,), command):
            for method in leaf.methods:
                calls.setdefault(method, []).append(line)
    return calls


def test_every_method_is_named_by_exactly_one_family() -> None:
    named = Counter(method for family in _families() for method in family.METHODS)

    assert not set(named) - _served(), "a family names a method no daemon serves"
    assert not _served() - set(named), "a method no family names"
    twice = {
        method: sorted(
            family.__name__ for family in _families() if method in family.METHODS
        )
        for method, count in named.items()
        if count > 1
    }
    assert not twice, "a method two families name"


def test_every_family_is_one_a_client_has() -> None:
    reached = {
        type(getattr(hmz.sdk.Client, name).func(None)).__name__
        for name, held in vars(hmz.sdk.Client).items()
        if hasattr(held, "func")
    }

    # `Harness` is under `client.chats.harness`, the one family reached through another.
    assert {family.__name__ for family in _families()} - reached == {"Harness"}


def test_every_method_is_called_by_a_declared_command_or_said_why_not() -> None:
    typed = _typed()

    assert not set(typed) - _served() - SESSION, (
        "a command calls a method nobody serves"
    )
    assert _served() - set(typed) == set(UNTYPED), (
        "a method no command calls must be given a command, or a reason in UNTYPED; "
        "and one that is called now must leave UNTYPED"
    )
    assert all(why.strip() for why in UNTYPED.values())


def test_every_command_has_its_section_of_the_protocol() -> None:
    protocol = (ROOT / "protocol" / "cli.md").read_text("utf-8")
    headed = {
        name
        for heading in re.findall(r"^#{2,3} .*$", protocol, re.MULTILINE)
        for name in re.findall(r"`hmz (\S+?)`", heading)
    }

    assert not set(cli.summaries()) - headed


def test_every_command_is_in_the_reference() -> None:
    reference = (ROOT / "docs" / "reference" / "cli.md").read_text("utf-8")

    for name in cli.summaries():
        assert f"| `{name}` |" in reference, name
    for name, command in tree.commands().items():
        assert f"## hmz {name}\n" in reference, name
        for line, _ in _leaves((name,), command):
            if command.commands:
                assert f"### hmz {line}\n" in reference, line
