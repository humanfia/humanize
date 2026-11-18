"""The SDK: how a tool that is not Humanize reaches Humanize.

    from hmz.sdk import Hmz

    hmz = Hmz()
    hmz.run(
        "goal", "win", agents={"worker": "claude/claude-haiku-4-5:low"}, budget={"cost": 1}
    ).run()

:class:`Hmz` is a workspace and everything that can be done in it: what was set up to run
there, the accounts, the runtimes, the epics already written. Its epics are run by a daemon
and never in the process that asked: :meth:`Hmz.run` has this machine's daemon check the epic
and hold it on a slot of its own, and :class:`Run` follows it there as one more frontend, so
the epic outlives the program that asked for it. An epic given driver objects -- the scripted
agents and dictionary filesystems of :mod:`fakes` -- is run by a private daemon of the
program's own, in its own process, since nothing else can hold them.

:class:`Client` is one session with a daemon, for a tool that wants the methods themselves;
:class:`Daemons`, :class:`Daemon` and :class:`Link` are a workspace's hosts, reached the way an
interface reaches them, claiming the roles a tool answers for and saying what the others type:

    with (Daemons().here() or Daemons().host()).link(name="ci") as link:
        link.claim("reviewer")
        for said in link:
            ...

An `Outworlder` role is answered by an :class:`hmz.runtime.flowing.OutworlderDriver` given to
:meth:`Hmz.run`, asked each question as one :class:`Ask`: its prompt, the JSON Schema its answer
is a value of, and the context shown with it -- the same question a person is shown.

What runs an epic in a host is internal to Humanize, and is not offered here.

Everything here is fetched when it is named, for the reason a workspace's own layers are: a
tool that only lists the places flows come from must not pay for the runs, the accounts and
the traces to do it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.daemon import Daemon, Link
    from hmz.runtime import (
        Accounts,
        Epics,
        Flows,
        Flowverses,
        NousBook,
        Refused,
        Runtimes,
    )
    from hmz.runtime.flowing.spi import Ask
    from hmz.sdk import faking as fakes
    from hmz.sdk.client import Client
    from hmz.sdk.daemons import Daemons
    from hmz.sdk.running import Hmz, Run

__all__ = [
    "Accounts",
    "Ask",
    "Client",
    "Daemon",
    "Daemons",
    "Epics",
    "Flows",
    "Flowverses",
    "Hmz",
    "Link",
    "NousBook",
    "Refused",
    "Run",
    "Runtimes",
    "fakes",
]

#: Where each of them is written: the runtime's settings of this machine, the daemon's hosts,
#: and the clients of a daemon written here. One entry apiece, so that `from hmz.sdk import
#: Hmz` costs the modules `Hmz` needs rather than every layer Humanize has.
_WRITTEN = {
    "Accounts": "hmz.runtime",
    "Ask": "hmz.runtime.flowing.spi",
    "Client": "hmz.sdk.client",
    "Daemon": "hmz.daemon",
    "Daemons": "hmz.sdk.daemons",
    "Epics": "hmz.runtime",
    "Flows": "hmz.runtime",
    "Flowverses": "hmz.runtime",
    "Hmz": "hmz.sdk.running",
    "Link": "hmz.daemon",
    "NousBook": "hmz.runtime",
    "Refused": "hmz.runtime",
    "Run": "hmz.sdk.running",
    "Runtimes": "hmz.runtime",
}

#: What is offered as a module rather than out of one: the fakes are a kit, used as one.
_MODULES = {"fakes": "hmz.sdk.faking"}


def __getattr__(name: str) -> object:
    """Hands through what this package offers, out of the layer it is written in.

    Args:
      name: What was asked for.

    Returns:
      The same object that layer holds, so that there is one of each however it was reached --
      a tool that named this and Humanize itself are holding one class, not two that agree.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    from importlib import import_module

    if name in _MODULES:
        return import_module(_MODULES[name])
    where_ = _WRITTEN.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)
