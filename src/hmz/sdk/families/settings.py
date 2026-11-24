"""A daemon's settings, and a workspace's (`settings.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["Backup", "Kept", "Settings", "Target"]


@dataclass(frozen=True)
class Target:
    """One git repository epics are backed up to."""

    name: str
    """What it is called, which an epic backed up to it names."""
    url: str
    """Where it is, with nothing signed into it: sent back as it is, it is kept as written."""
    branch: str
    """The branch pushed to."""
    policies: tuple[str, ...]
    """When an epic goes to it unasked: any of `session`, `interval` and `end`; none, by hand."""
    every: int
    """How many minutes apart, under `interval`."""

    def sent(self) -> dict[str, Any]:
        """It, as `settings.set` takes one."""
        return {
            "name": self.name,
            "url": self.url,
            "branch": self.branch,
            "policies": list(self.policies),
            "every": self.every,
        }


@dataclass(frozen=True)
class Backup:
    """Every backup target, and the ones an epic goes to unless it is told otherwise."""

    targets: tuple[Target, ...] = ()
    defaults: tuple[str, ...] = ()
    """The names of the targets a new epic is backed up to."""

    def sent(self) -> dict[str, Any]:
        """It, as `settings.set` takes it: every target, and the defaults."""
        return {
            "targets": [one.sent() for one in self.targets],
            "defaults": list(self.defaults),
        }


@dataclass(frozen=True)
class Kept:
    """What a daemon keeps of its machine's settings, and of one workspace's."""

    workspace: str
    """The workspace these are of: the user's home where none was named."""
    flow: str
    """The flow the workspace was last set up to run, or `""`."""
    chat: str
    """The chat agent remembered there, as `-a` spells one, or `""`."""
    prefer: str
    """What `$<name>` in a chat means where it names both a native skill and a flow, for
    every chat of the machine that does not say otherwise: `native` or `flow`."""
    ai_chan: str
    """The nous the last Ai-chan conversation was made with, or `""`."""
    details: bool
    """Whether a turn's tool calls and thinking are shown."""
    harness_sessions: bool
    """Whether the sessions each harness had of its own are listed."""
    reports: bool | None
    """Whether Humanize reports its own failures; None where that was never answered."""
    flows: tuple[str, ...]
    """The flows set up in the workspace."""
    backup: Backup
    listen: tuple[str, ...]
    """The listener specs the daemon opens."""
    ice_servers: tuple[dict[str, Any], ...]
    """The STUN and TURN servers, each `urls`, `username` and `credential` -- which is `True`
    where one is written, never its value."""
    forgot: bool | None
    """Whether `forget` found anything to forget; None from any other call."""
    said: dict[str, Any]
    """Everything the daemon answered."""


def _kept(said: Mapping[str, Any]) -> Kept:
    backup: Mapping[str, Any] = said.get("backup") or {}
    return Kept(
        workspace=str(said["workspace"]),
        flow=str(said.get("flow") or ""),
        chat=str(said.get("chat") or ""),
        prefer=str(said.get("prefer") or "native"),
        ai_chan=str(said.get("ai_chan") or ""),
        details=bool(said.get("details")),
        harness_sessions=bool(said.get("harness_sessions")),
        reports=said.get("reports"),
        flows=tuple(said.get("flows") or ()),
        backup=Backup(
            tuple(
                Target(
                    str(one["name"]),
                    str(one.get("url", "")),
                    str(one.get("branch", "")),
                    tuple(one.get("policies") or ()),
                    int(one.get("every") or 0),
                )
                for one in backup.get("targets") or ()
            ),
            tuple(backup.get("defaults") or ()),
        ),
        listen=tuple(said.get("listen") or ()),
        ice_servers=tuple(dict(one) for one in said.get("ice_servers") or ()),
        forgot=said.get("forgot"),
        said=dict(said),
    )


class Settings(Family):
    """A daemon's settings, and a workspace's."""

    METHODS: ClassVar = ("settings.get", "settings.set", "settings.forget")

    def get(self, workspace: str | None = None) -> Kept:
        """The settings of the daemon's machine, and of one workspace.

        Args:
          workspace: The workspace, as a whole path of the daemon's machine (`~` is its
            user's home), which need not exist; None for the user's home.
        """
        return _kept(self._call("settings.get", workspace=workspace))

    def set(
        self,
        *,
        workspace: str | None = None,
        chat: str | None = None,
        prefer: str | None = None,
        details: bool | None = None,
        harness_sessions: bool | None = None,
        reports: bool | None = None,
        backup: Backup | Mapping[str, Any] | None = None,
        listen: Sequence[str] | None = None,
        ice_servers: Sequence[Mapping[str, Any]] | None = None,
        idem: str | None = None,
    ) -> Kept:
        """Writes the settings given, all of them or, where any is refused, none.

        Args:
          workspace: The workspace `chat` is written for, which must exist; None for the
            user's home.
          chat: The chat agent remembered there, as `-a` spells one.
          prefer: What `$<name>` in a chat means where it names both a native skill and a
            flow: `native` or `flow`.
          details: Whether a turn's tool calls and thinking are shown.
          harness_sessions: Whether the sessions each harness had of its own are listed.
          reports: Whether Humanize reports its own failures.
          backup: Every backup target and the defaults, whole. A target whose `url` is the
            one `get` answered keeps the URL written, credentials and all.
          listen: Every listener spec the daemon opens; the listeners change at once.
          ice_servers: Every STUN and TURN server, each `urls`, `username` and `credential`;
            a `credential` of `True` keeps the one written.
          idem: The key this is done once under.

        Returns:
          The settings as they are afterwards.

        Raises:
          hmz.sdk.Refused: If a value is not one the setting takes, with nothing written.
        """
        return _kept(
            self._call(
                "settings.set",
                workspace=workspace,
                chat=chat,
                prefer=prefer,
                details=details,
                harness_sessions=harness_sessions,
                reports=reports,
                backup=backup.sent() if isinstance(backup, Backup) else backup,
                listen=None if listen is None else list(listen),
                ice_servers=(
                    None if ice_servers is None else [dict(one) for one in ice_servers]
                ),
                idem=idem,
            )
        )

    def forget(self, workspace: str, *, idem: str | None = None) -> Kept:
        """Forgets what a workspace was set up with.

        Args:
          workspace: The workspace, which need not exist.
          idem: The key this is done once under.

        Returns:
          The settings as they are afterwards, `forgot` saying whether there was anything.
        """
        return _kept(self._call("settings.forget", workspace=workspace, idem=idem))
