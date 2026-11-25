"""The flows a daemon can run, and what runs them (`flows.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "Account",
    "AgentRole",
    "Backends",
    "Checked",
    "Declared",
    "EnvRole",
    "Flow",
    "Flows",
    "Forked",
    "Model",
    "Offered",
    "Running",
]


@dataclass(frozen=True)
class Flow:
    """One flow on offer."""

    whose: str
    """Where it came from: a project's (`local`), the user's, or a flowverse's."""
    name: str
    """What it is started by."""
    about: str
    """What it says of itself, in a line."""


@dataclass(frozen=True)
class Running:
    """One flow an epic is in the middle of."""

    ref: str
    name: str
    depth: int
    """How many flows called it: 0 for the one the epic was started with."""
    since: str
    """When it began, as an ISO 8601 time."""
    task: str


@dataclass(frozen=True)
class Offered:
    """What a workspace has to run."""

    flows: tuple[Flow, ...]
    """Every flow on offer there, in the daemon's order."""
    flow: str
    """The flow last set up there, "" where none was."""
    running: tuple[Running, ...]
    """The flows running there now."""
    answer: dict[str, Any]
    """Everything the daemon answered."""


@dataclass(frozen=True)
class AgentRole:
    """One agent a flow asks for."""

    name: str
    required: bool
    auto: bool
    """Whether it fills itself -- a person, answering -- and so is given no agent."""
    harness: str
    """The only harness that may fill it, "" for any."""
    permission: dict[str, Any]
    """What it may touch: `preset`, `network` and `granular`, each a `path` and its `access`."""
    skills: tuple[str, ...]
    clis: tuple[str, ...]
    """The harnesses installed on the daemon's machine that can fill it."""


@dataclass(frozen=True)
class EnvRole:
    """One environment a flow asks for."""

    name: str
    required: bool
    auto: bool
    """Whether it fills itself: the folder the epic runs in."""
    cpu: Any
    memory: Any
    gpu: Any
    image: Any


@dataclass(frozen=True)
class Declared:
    """What a flow declares, and what a workspace last ran it with."""

    name: str
    ref: str
    description: str
    resumable: bool
    resumes: bool
    """Whether an epic of it there is to be picked up now."""
    agents: tuple[AgentRole, ...]
    envs: tuple[EnvRole, ...]
    params: dict[str, Any]
    """Its params, as a JSON schema."""
    remembered: dict[str, Any]
    """What the workspace last set it up with: `agents`, `envs`, `params`, `budget`,
    `profile_flow`, `profile_environment` and `backup`."""
    answer: dict[str, Any]
    """Everything the daemon answered."""


@dataclass(frozen=True)
class Checked:
    """An epic that would be started, checked and not started."""

    flow: str
    """The flow, as it was named."""
    ref: str
    declared: Declared
    names: dict[str, str]
    """The agent filling each agent role, by role."""
    budget: dict[str, Any] | None
    backup: tuple[str, ...]
    """The backup targets it would go to."""
    unreadable: str
    """Every limit of the budget nothing it drives can enforce, in words, or ""."""
    answer: dict[str, Any]
    """Everything the daemon answered."""


@dataclass(frozen=True)
class Model:
    """One model a harness runs."""

    name: str
    efforts: tuple[str, ...]


@dataclass(frozen=True)
class Account:
    """One account a harness runs as, and the models it runs as it."""

    name: str
    """Its name; "" for the machine's own sign-in."""
    models: tuple[Model, ...]
    asked: str
    """When the harness was last asked what it runs, "" for never."""


@dataclass(frozen=True)
class Backends:
    """What can fill a flow's roles on a daemon's machine."""

    clis: dict[str, tuple[Account, ...]]
    """Each harness installed, and its accounts, the machine's own sign-in first."""
    installable: dict[str, tuple[Model, ...]]
    """Each harness that could be installed, and what it runs."""
    envs: tuple[str, ...]
    """Every backend an environment can be put on, as `-e` spells each."""
    answer: dict[str, Any]
    """Everything the daemon answered."""


@dataclass(frozen=True)
class Forked:
    """A flow copied into a workspace."""

    said: str
    """What was done, in the daemon's words."""
    at: str
    """Where the copy is."""


def _models(said: Sequence[Mapping[str, Any]]) -> tuple[Model, ...]:
    return tuple(Model(one["name"], tuple(one.get("efforts") or ())) for one in said)


def _declared(said: Mapping[str, Any]) -> Declared:
    return Declared(
        name=said["name"],
        ref=said["ref"],
        description=said["description"],
        resumable=bool(said["resumable"]),
        resumes=bool(said["resumes"]),
        agents=tuple(
            AgentRole(
                one["name"],
                bool(one["required"]),
                bool(one["auto"]),
                one.get("harness") or "",
                dict(one.get("permission") or {}),
                tuple(one.get("skills") or ()),
                tuple(one.get("clis") or ()),
            )
            for one in said["agents"]
        ),
        envs=tuple(
            EnvRole(
                one["name"],
                bool(one["required"]),
                bool(one["auto"]),
                one.get("cpu"),
                one.get("memory"),
                one.get("gpu"),
                one.get("image"),
            )
            for one in said["envs"]
        ),
        params=dict(said["params"]),
        remembered=dict(said["remembered"]),
        answer=dict(said),
    )


class Flows(Family):
    """The flows a daemon can run, and what runs them."""

    METHODS: ClassVar = (
        "flows.list",
        "flows.get",
        "flows.backends",
        "flows.setup",
        "flows.check",
        "flows.fork",
    )

    def list(self, workspace: str | None = None) -> Offered:
        """The flows on offer, with those of a workspace where one is named.

        Args:
          workspace: The workspace, an absolute path of the daemon's machine, which need not
            exist; None for the flows that are no project's.
        """
        said = self._call("flows.list", workspace=workspace)
        return Offered(
            tuple(
                Flow(one["whose"], one["name"], one["about"]) for one in said["flows"]
            ),
            said["flow"],
            tuple(
                Running(
                    one["ref"], one["name"], one["depth"], one["since"], one["task"]
                )
                for one in said["running"]
            ),
            dict(said),
        )

    def get(self, name: str, workspace: str | None = None) -> Declared:
        """What a flow declares, and what the workspace last ran it with.

        Args:
          name: The flow, as `list` names it.
          workspace: The workspace, as `list` takes it.

        Raises:
          hmz.sdk.Refused: 404, if it is not a flow on offer there, or will not load.
        """
        return _declared(self._call("flows.get", workspace=workspace, name=name))

    def backends(self) -> Backends:
        """The harnesses installed, their accounts and models, and what an env can be on."""
        said = self._call("flows.backends")
        return Backends(
            {
                cli: tuple(
                    Account(one["name"], _models(one["models"]), one.get("asked") or "")
                    for one in held["accounts"]
                )
                for cli, held in said["clis"].items()
            },
            {cli: _models(found) for cli, found in said["installable"].items()},
            tuple(said["envs"]),
            dict(said),
        )

    def setup(
        self,
        workspace: str,
        flow: str,
        *,
        agents: Mapping[str, str] | None = None,
        envs: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        profile_flow: bool | None = None,
        profile_environment: bool | None = None,
        backup: Sequence[str] | None = None,
        idem: str | None = None,
    ) -> Declared:
        """Writes what a workspace runs a flow with, which a new epic of it there opens on.

        Args:
          workspace: The workspace.
          flow: The flow, as `list` names it.
          agents: What each agent role runs, by role, as `-a` writes one after `<role>=`.
          envs: What each environment role is, likewise with `-e`.
          params: The flow's params, None for its defaults.
          budget: What an epic of it may spend, as a `Budget` is as JSON: at least one limit.
          profile_flow: Whether the flow's own Python is profiled.
          profile_environment: Whether the programs its agents start are.
          backup: The backup targets its epics go to, by name, None for the defaults.
          idem: The key this is done once under.

        Returns:
          The flow, as `get` answers it once written.

        Raises:
          hmz.sdk.Refused: 404 for a flow not on offer or that will not load; 400 for an
            agent that is not one, a role left without one, no budget, or an unknown target.
        """
        return _declared(
            self._call(
                "flows.setup",
                idem=idem,
                workspace=workspace,
                flow=flow,
                agents=None if agents is None else dict(agents),
                envs=None if envs is None else dict(envs),
                params=None if params is None else dict(params),
                budget=None if budget is None else dict(budget),
                profile_flow=profile_flow,
                profile_environment=profile_environment,
                backup=None if backup is None else list(backup),
            )
        )

    def check(
        self,
        workspace: str,
        flow: str,
        *,
        agents: Mapping[str, str] | None = None,
        envs: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        profile_flow: bool | None = None,
        profile_environment: bool | None = None,
        resume: bool | str | None = None,
        backup: Sequence[str] | None = None,
    ) -> Checked:
        """Checks the epic a flow and its set-up make, as `hmz exec` does, starting nothing.

        Args:
          workspace: The workspace.
          flow: The flow: a name, a path or a ref, as `hmz exec -f` takes one.
          agents: What each agent role runs, as `setup` takes it.
          envs: What each environment role is.
          params: The flow's params, None for its defaults.
          budget: What the epic may spend.
          profile_flow: Whether the flow's own Python is profiled.
          profile_environment: Whether the programs its agents start are.
          resume: Whether the newest epic of it there is picked up, or the epic to pick up.
          backup: The backup targets it goes to, None for the defaults.

        Raises:
          hmz.sdk.Refused: 400, with what `hmz exec` prints after `hmz exec: error: `.
        """
        said = self._call(
            "flows.check",
            workspace=workspace,
            flow=flow,
            agents=None if agents is None else dict(agents),
            envs=None if envs is None else dict(envs),
            params=None if params is None else dict(params),
            budget=None if budget is None else dict(budget),
            profile_flow=profile_flow,
            profile_environment=profile_environment,
            resume=resume,
            backup=None if backup is None else list(backup),
        )
        return Checked(
            said["flow"],
            said["ref"],
            _declared(said["declared"]),
            dict(said["names"]),
            said["budget"],
            tuple(said["backup"]),
            said["unreadable"],
            dict(said),
        )

    def fork(self, workspace: str, flow: str, *, idem: str | None = None) -> Forked:
        """Copies a flow into a workspace, to be changed there.

        Args:
          workspace: The workspace.
          flow: The flow, as `list` names it.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 400, with why it was not copied.
        """
        said = self._call("flows.fork", idem=idem, workspace=workspace, flow=flow)
        return Forked(said["said"], said["at"])
