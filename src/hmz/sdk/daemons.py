"""The runs humanize is holding apart from a terminal, as a tool outside reaches them.

A workspace's runs outlive the program that asked for them: they are held in a process of
their own, one per workspace, and are reached over the socket beside it. That is the other way
in -- :class:`hmz.runtime.doing.core.Hmz` runs a flow here, in the process that asked, and
this starts a host somewhere a terminal closing cannot end it and reaches whichever are
already running.

:mod:`hmz.daemon` is where all of it is done; this is the one object it is asked through, so
that a tool holds one thing per way in rather than a module of functions apiece.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os

    from hmz.daemon import Daemon

__all__ = ["Daemons"]


class Daemons:
    """Every workspace's runs being held apart from a terminal, and how they are put there."""

    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None:
        """The run being held in one workspace, if one is.

        Args:
          workspace: The project directory, or None for wherever this is being run.

        Returns:
          It, or None where nothing is being held there -- which is what a directory left
          behind by a daemon whose process has gone reads as, a socket file outliving the
          process that bound it.
        """
        from hmz import daemon

        return daemon.running(workspace)

    def all(self) -> list[Daemon]:
        """Every run being held on this machine, oldest first."""
        from hmz import daemon

        return daemon.daemons()

    def host(self, workspace: str | os.PathLike[str] | None = None) -> Daemon:
        """The daemon hosting a workspace's runs for frontends, started where none is.

        What a tool reaches to be one of a run's frontends: its `link()` is a
        :class:`hmz.daemon.Link`, the same one an interface or `hmz attach` holds.

        Args:
          workspace: The project directory, or None for wherever this is being run.

        Returns:
          The daemon, listening.

        Raises:
          OSError: If a daemon of an older humanize holds it, or no host could be started.
        """
        from hmz import daemon

        return daemon.host(workspace)
