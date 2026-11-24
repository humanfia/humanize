"""One session of `protocol/wire.md` with one daemon, as a program of the SDK holds it.

The client is the runtime's own (:class:`hmz.runtime.doing.daemons.Client`, what the registry
of other machines' daemons hands out too): this adds only reaching this machine's daemon,
which starting it where none runs is the daemon layer's to do (Section 4.21.1 of python.md),
and the families of :mod:`hmz.sdk.families`, each the typed calls of one group of methods.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from hmz.runtime.doing.daemons import Client as Session

if TYPE_CHECKING:
    from hmz.rpc import Kind

    from .families.accounts import Accounts
    from .families.aichan import AiChan
    from .families.backups import Backups
    from .families.btw import SideQuestions
    from .families.chats import Chats
    from .families.devices import Devices
    from .families.easytier import EasyTier
    from .families.envs import Envs
    from .families.epics import Epics
    from .families.files import Files
    from .families.flows import Flows
    from .families.flowverses import Flowverses
    from .families.hosts import Hosts
    from .families.notices import Notices
    from .families.nous import Nous
    from .families.paths import Paths
    from .families.runs import Runs
    from .families.runtimes import Runtimes
    from .families.settings import Settings
    from .families.workspaces import Workspaces

__all__ = ["Client"]

#: How long this machine's daemon is given to take the session.
_PATIENCE = 10.0


class Client(Session):
    """One session with one daemon; a context manager, closed to end it."""

    @classmethod
    def local(cls, *, name: str = "", kind: Kind = "sdk") -> Client:
        """A session with this machine's daemon over `unix:`, started where none runs.

        Ai-chan (`kind` `ai-chan`) reaches it over the scoped link `HUMANIZE_AICHAN_LINK`
        names instead, and starts no daemon (Section 4.21.8 of python.md).

        Args:
          name: What this client is called, "" for this machine's host name.
          kind: What it is: `sdk`, `cli`, `tui`, `ai-chan`.

        Raises:
          OSError: If the daemon cannot be reached or started, or speaks another protocol --
            `EADDRINUSE`, saying so -- and, for `ai-chan`, where no scoped link is named.
        """
        from hmz.reach.pipes import SocketPipe

        if kind == "ai-chan":
            from hmz.runtime.doing.aichan import linked

            one = linked()
        else:
            from hmz import daemon
            from hmz.daemon import where

            daemon.start()
            one = where.connects(where.at(), _PATIENCE)
        one.settimeout(None)
        return cls.over(SocketPipe(one, trusted=True), name=name, kind=kind)

    @functools.cached_property
    def devices(self) -> Devices:
        """The devices paired with the daemon, and pairing one (`pair.*`, `devices.*`)."""
        from .families.devices import Devices

        return Devices(self)

    @functools.cached_property
    def chats(self) -> Chats:
        """Chats and harness sessions (`chat.*`)."""
        from .families.chats import Chats

        return Chats(self)

    @functools.cached_property
    def epics(self) -> Epics:
        """An epic of a host, as a frontend of it (`epic.*`)."""
        from .families.epics import Epics

        return Epics(self)

    @functools.cached_property
    def hosts(self) -> Hosts:
        """The hosts epics and chats are held in (`hosts.*`)."""
        from .families.hosts import Hosts

        return Hosts(self)

    @functools.cached_property
    def runs(self) -> Runs:
        """Recorded epics (`runs.*`)."""
        from .families.runs import Runs

        return Runs(self)

    @functools.cached_property
    def backups(self) -> Backups:
        """Backup targets (`backups.*`)."""
        from .families.backups import Backups

        return Backups(self)

    @functools.cached_property
    def files(self) -> Files:
        """File handles (`files.*`)."""
        from .families.files import Files

        return Files(self)

    @functools.cached_property
    def envs(self) -> Envs:
        """A host's environments (`env.*`, `hosts.env.*`)."""
        from .families.envs import Envs

        return Envs(self)

    @functools.cached_property
    def flows(self) -> Flows:
        """Flows (`flows.*`)."""
        from .families.flows import Flows

        return Flows(self)

    @functools.cached_property
    def flowverses(self) -> Flowverses:
        """Flowverses (`flowverses.*`)."""
        from .families.flowverses import Flowverses

        return Flowverses(self)

    @functools.cached_property
    def workspaces(self) -> Workspaces:
        """Workspaces (`workspaces.*`)."""
        from .families.workspaces import Workspaces

        return Workspaces(self)

    @functools.cached_property
    def paths(self) -> Paths:
        """The daemon machine's directories (`paths.*`)."""
        from .families.paths import Paths

        return Paths(self)

    @functools.cached_property
    def settings(self) -> Settings:
        """Settings (`settings.*`)."""
        from .families.settings import Settings

        return Settings(self)

    @functools.cached_property
    def accounts(self) -> Accounts:
        """Accounts (`accounts.*`)."""
        from .families.accounts import Accounts

        return Accounts(self)

    @functools.cached_property
    def nous(self) -> Nous:
        """Nous (`nous.*`)."""
        from .families.nous import Nous

        return Nous(self)

    @functools.cached_property
    def runtimes(self) -> Runtimes:
        """Runtimes (`runtimes.*`)."""
        from .families.runtimes import Runtimes

        return Runtimes(self)

    @functools.cached_property
    def easytier(self) -> EasyTier:
        """EasyTier networks (`easytier.*`)."""
        from .families.easytier import EasyTier

        return EasyTier(self)

    @functools.cached_property
    def btw(self) -> SideQuestions:
        """Side questions (`btw.*`)."""
        from .families.btw import SideQuestions

        return SideQuestions(self)

    @functools.cached_property
    def aichan(self) -> AiChan:
        """Ai-chan's conversations (`aichan.*`)."""
        from .families.aichan import AiChan

        return AiChan(self)

    @functools.cached_property
    def notices(self) -> Notices:
        """Notices (`notices.*`)."""
        from .families.notices import Notices

        return Notices(self)
