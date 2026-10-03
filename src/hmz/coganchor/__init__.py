"""coganchor -- everything humanize knows about driving a coding agent CLI.

The whole of the capability, so that the layers above it only ever schedule flows. What each
CLI *is* -- its name, its efforts, where it keeps its logs and its credentials, what it runs
-- is :mod:`hmz.coganchor.backends` and :mod:`hmz.coganchor.models`; driving one is
:mod:`hmz.coganchor.agents`; which account it runs as is :mod:`hmz.coganchor.providers`;
where its turns land is :mod:`hmz.coganchor.machines`; where a turn goes when the place
taking it cannot is :mod:`hmz.coganchor.fallbacks`; and what its tokens cost is
:mod:`hmz.coganchor.prices`.

And the anchor this package is named for: running an agent on one machine and having it act
on another. Two arrangements, and a session says which it is. Under :func:`connect` the agent
process stays local, keeping its credentials, its state directory and its link to its model
provider: a seccomp-filtered ptrace supervisor intercepts the cold syscalls that name a path,
spawn a process or open a socket, and the serving half replays them on the target machine.
Under :func:`drive` nothing stays local at all -- the CLI already installed on the target is
the one that runs, and this side is a pipe carrying its streams.

What the front door offers is fetched when it is named. The facts about a CLI are a leaf and
are read where a figure is drawn: naming this package to reach one must not cost the ptrace
layer, the register map and the wire the anchor is made of.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.coganchor.anchor import AnchorConfig, check, connect, drive

    #: humanize's version: the one `pyproject.toml` says, as the installed `hmz` carries it.
    __version__: str

__all__ = ["AnchorConfig", "__version__", "check", "connect", "drive"]

#: Which module each of them is written in. One entry per name this package offers, so that
#: `from hmz.coganchor import backends` costs the facts about the CLIs and none of the anchor.
_WRITTEN = {
    "AnchorConfig": "hmz.coganchor.anchor",
    "check": "hmz.coganchor.anchor",
    "connect": "hmz.coganchor.anchor",
    "drive": "hmz.coganchor.anchor",
}


def __getattr__(name: str) -> object:
    """Hands through what this package offers, out of the module it is written in.

    And the version, out of the installed package's metadata -- which is where the one copy of
    it, in `pyproject.toml`, ends up -- kept here once it is read. The archive a target runs
    carries a copy of that metadata, so that the same question has the same answer there.

    Args:
      name: What was asked for.

    Returns:
      The same object that module holds, so that there is one of each however it was reached.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    if name == "__version__":
        # Asked for rather than read at import: reaching the metadata costs more than the rest
        # of this front door, and only a turn being started, or the archive it ships, asks.
        from importlib.metadata import PackageNotFoundError, version

        try:
            found = version("hmz")
        except PackageNotFoundError:
            # A source tree run without being installed, which has a version nowhere to read.
            found = "unknown"
        globals()[name] = found
        return found
    from importlib import import_module

    where_ = _WRITTEN.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)
