"""The flows there are to run here, what each declares, and the agents that can fill them.

What a page needs to start a run: the flows on offer and where each came from, one flow's
roles, params and budget as it declares them and as this workspace last set them up, and the
backends installed here with the accounts each runs as and the models each says it runs
as which.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, cast

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "declared", "remembered"]


def declared(hmz: Any, name: str) -> dict[str, Any]:
    """One flow, as a page sets a run of it up: what it declares, and what was set last.

    Args:
      hmz: Humanize, for the workspace.
      name: The flow, as it is offered.

    Returns:
      Its agent and environment roles, its params as a JSON schema, whether a run of it can be
      picked up, and what this workspace last ran it with.

    Raises:
      Refusal: If there is no such flow, or it will not load.
    """
    from hmz.runtime.kept import written

    try:
        flow = hmz.flows.declared(name)
    except Exception as why:
        raise Refusal(f"{name} cannot be set up: {why}", 404) from why
    from hmz import daemon

    # Afresh, as what a workspace remembers is written by its runs as well as by this.
    settings = daemon.Hmz(hmz.workspace).settings
    installed = sorted(hmz.installed())
    return {
        "name": name,
        "ref": flow.ref,
        "description": flow.description or "",
        "resumable": flow.resumable,
        "resumes": flow.resumable and hmz.epics.resumed(name) is not None,
        "agents": [
            {
                "name": role.name,
                "required": role.required,
                "auto": role.auto,
                "harness": str(role.harness or ""),
                "permission": asdict(role.permission),
                "skills": list(role.skills),
                # The backends installed here that could fill it, in the order offered.
                "clis": [cli for cli in installed if hmz.serves(cli, role)],
            }
            for role in flow.agents
        ],
        "envs": [
            {
                "name": role.name,
                "required": role.required,
                "auto": role.auto,
                "cpu": role.cpu_count,
                "memory": role.memory,
                "gpu": role.gpu_count,
                "image": role.image,
            }
            for role in flow.envs
        ],
        "params": flow.params.model_json_schema(),
        "remembered": {
            "agents": {
                role: written(runs) for role, runs in settings.agents(name).items()
            },
            "envs": settings.envs(name),
            "params": settings.params(name),
            "budget": settings.budget(name),
            "profile_flow": settings.profile_flow(name),
            "profile_environment": settings.profile_environment(name),
            "backup": settings.backup(name),
        },
    }


def remembered(hmz: Any, said: dict[str, Any]) -> None:
    """Writes down what a workspace is set up to run a flow with, as `/flow` saves it.

    What a new epic there opens on from then on: its agents, environments, params, budget,
    what of it is profiled and the backup targets it goes to. Refused, as the terminal
    interface refuses to save it, where a role names no agent or -- for every flow but chat
    -- nothing says what it may spend.

    Args:
      hmz: Humanize, for the workspace.
      said: The flow and what it is set up with, as a page sends a start.

    Raises:
      Refusal: If the flow is not on offer there, an agent is not one, or it is not set up
        enough to run.
    """
    from hmz.runtime.kept import read_back

    flow = said.get("flow")
    if not isinstance(flow, str) or flow not in {one.name for one in hmz.flows.all()}:
        raise Refusal(f"{flow} is not a flow on offer here.", 404)
    given: object = said.get("agents") or {}
    if not isinstance(given, dict):
        raise Refusal("agents is an object of agents as -a spells them.")
    agents: dict[str, Any] = {}
    for role, spec in cast("dict[str, object]", given).items():
        runs = read_back(spec) if isinstance(spec, str) else None
        if runs is None:
            raise Refusal(f"{role} is not given an agent as -a spells one: {spec}.")
        agents[str(role)] = runs
    try:
        roles = hmz.flows.declared(flow).agents
    except Exception as why:
        raise Refusal(f"{flow} cannot be set up: {why}", 404) from why
    if missing := [
        one.name
        for one in roles
        if one.required and not one.auto and one.name not in agents
    ]:
        raise Refusal(f"{flow} needs an agent for {', '.join(missing)}.")
    budget: object = said.get("budget")
    if flow != "chat" and not budget:
        raise Refusal(f"{flow} needs at least one limit on what it may spend.")
    envs: object = said.get("envs")
    params: object = said.get("params")
    backup: object = said.get("backup")
    if backup is not None and not (
        isinstance(backup, list)
        and all(isinstance(one, str) for one in cast("list[object]", backup))
    ):
        raise Refusal("backup is a list of backup target names.")
    chosen = cast("list[str]", backup or [])
    known = {one.name for one in hmz.backups.targets()}
    if missing := [one for one in chosen if one not in known]:
        raise Refusal(f"There is no backup target named {', '.join(missing)}.")
    daemon_settings(hmz).remember(
        flow,
        agents,
        cast("dict[str, str]", envs) if isinstance(envs, dict) else None,
        cast("dict[str, Any]", params) if isinstance(params, dict) else None,
        cast("dict[str, Any]", budget) if isinstance(budget, dict) else {},
        profile_flow=said.get("profile_flow") is True,
        profile_environment=said.get("profile_environment") is True,
        backup=cast("list[str] | None", backup),
    )


def daemon_settings(hmz: Any) -> Any:
    """A workspace's settings read afresh: its runs write them as well as this does."""
    from hmz import daemon

    return daemon.Hmz(hmz.workspace).settings


def _setup(asked: Asked) -> dict[str, Any]:
    hmz = _place(asked).hmz
    remembered(hmz, asked.body)
    return declared(hmz, asked.text("flow"))


def _place(asked: Asked) -> Any:
    """The workspace a write names, or where the interface started."""
    said = asked.body.get("workspace", "")
    return asked.site.places.of(said if isinstance(said, str) else "")


def _hmz(asked: Asked) -> Any:
    """Humanize, for the workspace a request names, or where the interface started."""
    return asked.site.places.of(asked.query.get("workspace", "")).hmz


def _flows(asked: Asked) -> dict[str, Any]:
    hmz = _hmz(asked)
    return {
        "flows": [
            {"whose": one.whose, "name": one.name, "about": one.about}
            for one in hmz.flows.all()
        ],
        "flow": hmz.settings.flow,
        "running": [
            {
                "ref": one.ref,
                "name": one.name,
                "depth": one.depth,
                "since": one.since,
                "task": one.task,
            }
            for one in hmz.flows.running()
        ],
    }


def _flow(asked: Asked) -> dict[str, Any]:
    hmz = _hmz(asked)
    name = asked.query.get("name", "")
    if not name:
        raise Refusal("Say which flow, as name.")
    # Setting a flow up loads it, which runs it: only a flow already on offer here, never a
    # path or a repository a page names.
    if name not in {one.name for one in hmz.flows.all()}:
        raise Refusal(f"{name} is not a flow on offer here.", 404)
    return declared(hmz, name)


def _backends(asked: Asked) -> dict[str, Any]:
    hmz = _hmz(asked)
    accounts = hmz.accounts

    def models(cli: str, name: str) -> list[dict[str, Any]]:
        return [
            {"name": one.name, "efforts": list(one.efforts)}
            for one in accounts.models(cli, name)
        ]

    def held(cli: str) -> dict[str, Any]:
        # This machine's own sign-in first, as `as local`, then every account made for it.
        names = ["", *(one.name for one in accounts.all(cli))]
        return {
            "accounts": [
                {
                    "name": name,
                    "models": models(cli, name),
                    "asked": accounts.asked(cli, name),
                }
                for name in names
            ]
        }

    return {
        "clis": {cli: held(cli) for cli in hmz.installed()},
        "installable": {
            cli: [{"name": one.name, "efforts": list(one.efforts)} for one in found]
            for cli, found in hmz.installable().items()
        },
        "envs": hmz.runtimes.kinds(),
    }


#: What a page reads of the flows here and the agents that can run them.
ROUTES = routes(
    ("GET", "/api/flows", _flows),
    ("GET", "/api/flow", _flow),
    ("GET", "/api/backends", _backends),
    ("POST", "/api/flows/setup", _setup),
)
