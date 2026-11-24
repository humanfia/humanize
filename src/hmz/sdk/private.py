"""The private daemon a program runs an epic of driver objects through (Section 4.19).

Driver objects are the program's own -- a scripted agent, a dictionary filesystem -- and no
daemon of this machine can be handed one. So the SDK starts a daemon of the program's own, in
its own process, and reaches it over a socket pair as any client reaches a daemon: each driver
is named to it as `fake:<key>`, and its hosts, held in this process, take each such name back
as the object it stands for. It keeps a temporary home and machine directory, made as it
starts with a copy of the settings file, and removed with everything written there -- the
epic included -- as it is torn down; private daemons going at once in one process share them,
since a process has one environment to say where they are.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.runtime import Flows, Holding

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hmz.daemon.private import Private
    from hmz.flows import Budget, FlowParams
    from hmz.runtime import Run
    from hmz.runtime.flowing import (
        AgentDriver,
        Declaration,
        EnvDriver,
        OutworlderDriver,
    )
    from hmz.runtime.flowing.specs import AgentSpec, EnvSpec
    from hmz.runtime.runner import Runner
    from hmz.sdk.client import Client

__all__ = ["FAKE", "Fakes"]

#: What a driver object is named by to the private daemon holding it.
FAKE = "fake:"

#: The kinds of directory the private daemon's home is, each in the place made for it.
_HOMES = ("config", "data", "state", "cache")


class Fakes:
    """The driver objects of one epic, and the private daemon they are handed to.

    Attributes:
      local: What fills every `LocalEnv` role, or None for the workspace.
      journal: Where a resumable flow's journal is kept and whether to pick it up, or None for
        its epic's.
      ran: Each run its hosts made, in order: what the flow returned or raised is read back
        off the last.
    """

    def __init__(self) -> None:
        self._kept: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._daemon: Private | None = None
        self._made = False
        self.local: EnvDriver | None = None
        self.journal: tuple[Path, bool] | None = None
        self.ran: list[Run] = []

    def __bool__(self) -> bool:
        """Whether any object is held, and so whether a private daemon is wanted."""
        return bool(self._kept) or self.local is not None or self.journal is not None

    def keep(self, one: object) -> str:
        """Names one object to the private daemon.

        Returns:
          `fake:<key>`, `<key>` a text of the SDK's own.
        """
        name = f"{FAKE}{secrets.token_hex(8)}"
        self._kept[name] = one
        return name

    def given(self, one: Any) -> Any:
        """What a name given to the private daemon stands for: the object, or itself."""
        return self._kept.get(one, one) if isinstance(one, str) else one

    def every(self, given: Any) -> Any:
        """What each role's name stands for, of a mapping of them; anything else as it is."""
        if not isinstance(given, Mapping):
            return given
        roles: Mapping[str, Any] = given  # pyright: ignore[reportUnknownVariableType]
        return {role: self.given(one) for role, one in roles.items()}

    def client(self) -> Client:
        """A session with the private daemon, which is started the first time one is asked.

        Raises:
          OSError: If it could not be started.
        """
        from hmz.sdk.client import Client

        with self._lock:
            if self._daemon is None:
                self._daemon = self._starts()
            daemon = self._daemon
        return Client.over(daemon.paired())

    def _starts(self) -> Private:
        """Makes the private daemon, in the home and machine directory private daemons share."""
        import socket

        from hmz.daemon import where
        from hmz.daemon.private import Private

        _PLACE.takes()
        self._made = True
        # Never bound: it takes sessions only as they are handed to it over a socket pair.
        return Private(
            where.at(),
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
            lambda workspace: _Faked(workspace, self),
        )

    def close(self) -> None:
        """Tears the private daemon down: its hosts, its sessions, its home, its epics."""
        with self._lock:
            daemon, self._daemon = self._daemon, None
            made, self._made = self._made, False
        if daemon is not None:
            daemon.close()
        if made:
            _PLACE.leaves()


class _Place:
    """The temporary home and machine directory of this process's private daemons.

    Where Humanize keeps its home and its machine's directory is the process's -- its home
    told to `hmz` alone (:data:`hmz._INSTEAD`), since the bases it is in are every program's,
    and its machine's directory its `TMPDIR` -- which every thread shares: the private daemons
    going at once share one place, made as the first comes up -- with a copy of the settings
    file -- and removed, epics and all, as the last goes, the process's own place put back.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._holding = 0
        self._made: Path | None = None
        self._was: str | None = None
        self._tempdir: str | None = None

    def takes(self) -> None:
        """Holds the place for one more private daemon, making it for the first.

        The home made holds a copy of the settings file, and the user's own flows where they
        are: a link, which a flow named `@user/...` is found through as it is outside.
        """
        import hmz

        with self._lock:
            self._holding += 1
            if self._holding > 1:
                return
            made = Path(tempfile.mkdtemp(prefix="hmz-private-"))
            flows = hmz.data() / "flows"
            for kind in _HOMES:
                (made / kind).mkdir()
            (made / "tmp").mkdir()
            # The YAML one too, where it is not converted yet: the private home converts it.
            for name in ("settings.toml", "settings.yaml"):
                if (hmz.config() / name).is_file():
                    shutil.copyfile(hmz.config() / name, made / "config" / name)
            if flows.is_dir():
                (made / "data" / "flows").symlink_to(flows)
            self._made = made
            self._was = os.environ.get("TMPDIR")
            self._tempdir = tempfile.tempdir
            hmz._INSTEAD |= {kind: made / kind for kind in _HOMES}  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            os.environ["TMPDIR"] = str(made / "tmp")
            tempfile.tempdir = str(made / "tmp")

    def leaves(self) -> None:
        """Lets go of the place for one private daemon, removing it after the last."""
        import hmz

        with self._lock:
            self._holding -= 1
            if self._holding or self._made is None:
                return
            made, self._made = self._made, None
            if self._was is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = self._was
            hmz._INSTEAD.clear()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            tempfile.tempdir = self._tempdir
        with contextlib.suppress(OSError):
            shutil.rmtree(made, ignore_errors=True)


_PLACE = _Place()


class _Flows(Flows):
    """The flows of a workspace the private daemon holds, a flow it was handed among them."""

    def __init__(self, workspace: str, fakes: Fakes) -> None:
        super().__init__(workspace)
        self._fakes = fakes

    def declared(self, named: str | os.PathLike[str]) -> Declaration:
        """What a flow declares: one handed over as an object, as that object declares it."""
        one = self._fakes.given(named)
        return super().declared(named) if one is named else one.describe()


class _Faked(Holding):
    """A workspace held by the private daemon: each `fake:<key>` taken back as its object."""

    def __init__(self, workspace: str, fakes: Fakes) -> None:
        super().__init__(workspace)
        self._fakes = fakes
        self._flowing = _Flows(workspace, fakes)

    @property
    def flows(self) -> Flows:
        """The flows there are, a flow handed over as an object among them."""
        return self._flowing

    def runner(
        self,
        flow: str | os.PathLike[str],
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        profile_flow: bool = False,
        profile_environment: bool = False,
        resume: bool | str | os.PathLike[str] = False,
        backup: Iterable[str] | None = None,
    ) -> Runner:
        """The flow, loaded in the private daemon, with every object it was given."""
        from hmz import working_in
        from hmz.runtime.runner import Runner

        fakes = self._fakes
        with working_in(self.workspace):
            return Runner(
                fakes.given(flow),
                agents=fakes.every(agents),
                envs=fakes.every(envs),
                params=params,
                budget=budget,
                profile_flow=profile_flow,
                profile_environment=profile_environment,
                resume=resume,
                workspace=self.workspace,
                backup=backup,
                local=fakes.local,
                journal=fakes.journal,
            )

    def run(
        self,
        flow: str | os.PathLike[str],
        task: str,
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        profile_flow: bool = False,
        profile_environment: bool = False,
        resume: bool | str | os.PathLike[str] = False,
        outworlder: OutworlderDriver | None = None,
        backup: Iterable[str] | None = None,
    ) -> Run:
        """The run, kept for what the flow returned or raised to be read back off it."""
        made = super().run(
            flow,
            task,
            agents=agents,
            envs=envs,
            params=params,
            budget=budget,
            profile_flow=profile_flow,
            profile_environment=profile_environment,
            resume=resume,
            outworlder=outworlder,
            backup=backup,
        )
        self._fakes.ran.append(made)
        return made
