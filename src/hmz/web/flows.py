"""The flows there are to run here, what each declares, and the agents that can fill them.

What a page needs to start a run: the flows on offer and where each came from, one flow's
roles, params and budget as it declares them and as this workspace last set them up, and the
backends installed here with the accounts each runs as and the models each says it runs
as which.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from .routing import Refusal, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "declared"]


def declared(hmz: Any, name: str) -> dict[str, Any]:
    """One flow, as a page sets a run of it up: what it declares, and what was set last.

    Args:
      hmz: humanize, for the workspace.
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
    settings = hmz.settings
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
            "profile": settings.profile(name),
        },
    }


def _flows(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
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
    hmz = asked.site.hmz
    name = asked.query.get("name", "")
    if not name:
        raise Refusal("Say which flow, as name.")
    # Setting a flow up loads it, which runs it: only a flow already on offer here, never a
    # path or a repository a page names.
    if name not in {one.name for one in hmz.flows.all()}:
        raise Refusal(f"{name} is not a flow on offer here.", 404)
    return declared(hmz, name)


def _backends(asked: Asked) -> dict[str, Any]:
    hmz = asked.site.hmz
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
)
