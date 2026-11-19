"""`flows.*`: the flows to run in a workspace, what each declares, and the agents to fill them.

What a client needs to start an epic: the flows on offer and where each came from, one flow's
roles, params and budget as it declares them and as the workspace last set them up, the CLIs
installed here with the accounts each runs as and the models each says it runs as which --
and, before anything starts, whether an epic set up so would be refused.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, cast

from pydantic.json_schema import GenerateJsonSchema

from hmz.rpc import Code, RpcError

from .workspaces import place

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hmz.rpc import Call, Handler

__all__ = [
    "METHODS",
    "backends",
    "checked",
    "declared",
    "forked",
    "listed",
    "offered",
    "remembers",
]


class _Authored(GenerateJsonSchema):
    """A params schema whose fields carry a title only where the flow wrote one.

    Pydantic titles every field after its name otherwise, and a client shows a field by its
    title before its name: one it made up would hide the name the flow is set up by.
    """

    def field_title_should_be_set(self, schema: Any) -> bool:  # noqa: ARG002
        return False


def listed(hmz: Any) -> dict[str, Any]:
    """The flows on offer in a workspace, the one last set up there, and the flows running."""
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


def offered(hmz: Any, name: str) -> dict[str, Any]:
    """One flow on offer in a workspace, as :func:`declared` answers it.

    Setting a flow up loads it, which runs it: only a flow already on offer, never a path or a
    repository a client names.

    Raises:
      RpcError: 404, if it is not on offer there or will not load.
    """
    if name not in {one.name for one in hmz.flows.all()}:
        raise RpcError(Code.NOT_FOUND, f"{name} is not a flow on offer here.")
    return declared(hmz, name)


def declared(hmz: Any, name: str) -> dict[str, Any]:
    """One flow, as a client sets an epic of it up: what it declares, and what was set last.

    Args:
      hmz: Humanize, for the workspace.
      name: The flow, as it is offered.

    Returns:
      Its agent and environment roles, its params as a JSON schema (a field titled only where
      the flow titled it), whether an epic of it can be picked up, and what this workspace
      last ran it with.

    Raises:
      RpcError: 404, if there is no such flow, or it will not load.
    """
    from hmz.runtime.kept import written

    try:
        flow = hmz.flows.declared(name)
    except Exception as why:
        raise RpcError(Code.NOT_FOUND, f"{name} cannot be set up: {why}") from why
    settings = _settings(hmz)
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
                # The CLIs installed here that could fill it, in the order offered.
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
        "params": flow.params.model_json_schema(schema_generator=_Authored),
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


def remembers(hmz: Any, said: Mapping[str, Any]) -> Callable[[], None]:
    """Checks what a workspace is to be set up to run a flow with, as `/flow` saves it.

    What a new epic there opens on from then on: its agents, environments, params, budget,
    what of it is profiled and the backup targets it goes to. Refused, as the terminal
    interface refuses to save it, where a role names no agent or nothing says what it may
    spend. Written down only once what is answered is called:
    `epic.start` writes it once the host has taken the start, so that a start refused
    leaves the set-up there was.

    Args:
      hmz: Humanize, for the workspace.
      said: The flow and what it is set up with, as `epic.start` takes them.

    Returns:
      What writes it down.

    Raises:
      RpcError: 404 for a flow not on offer there or that will not load; 400 for an agent
        that is not one, a role left without one, no budget, or an unknown backup target.
    """
    from hmz.runtime.kept import read_back

    flow = said.get("flow")
    if not isinstance(flow, str) or flow not in {one.name for one in hmz.flows.all()}:
        raise RpcError(Code.NOT_FOUND, f"{flow} is not a flow on offer here.")
    given: object = said.get("agents") or {}
    if not isinstance(given, dict):
        raise _refused("agents is an object of agents as -a spells them.")
    agents: dict[str, Any] = {}
    for role, spec in cast("dict[str, object]", given).items():
        runs = read_back(spec) if isinstance(spec, str) else None
        if runs is not None and "/" not in runs.spec:
            # A name is an agent only where a virtual nous is written under it.
            try:
                hmz.nous.entry(runs.spec)
            except ValueError:
                runs = None
        if runs is None:
            raise _refused(f"{role} is not given an agent as -a spells one: {spec}.")
        agents[str(role)] = runs
    try:
        roles = hmz.flows.declared(flow).agents
    except Exception as why:
        raise RpcError(Code.NOT_FOUND, f"{flow} cannot be set up: {why}") from why
    if missing := [
        one.name
        for one in roles
        if one.required and not one.auto and one.name not in agents
    ]:
        raise _refused(f"{flow} needs an agent for {', '.join(missing)}.")
    budget: object = said.get("budget")
    if not budget:
        raise _refused(f"{flow} needs at least one limit on what it may spend.")
    envs: object = said.get("envs")
    params: object = said.get("params")
    backup = _targets(said.get("backup"))
    known = {one.name for one in hmz.backups.targets()}
    if missing := [one for one in backup or [] if one not in known]:
        raise _refused(f"There is no backup target named {', '.join(missing)}.")
    saved = _saved(budget)

    def writes() -> None:
        _settings(hmz).remember(
            flow,
            agents,
            cast("dict[str, str]", envs) if isinstance(envs, dict) else None,
            cast("dict[str, Any]", params) if isinstance(params, dict) else None,
            saved,
            profile_flow=said.get("profile_flow") is True,
            profile_environment=said.get("profile_environment") is True,
            backup=backup,
        )

    return writes


def backends(hmz: Any) -> dict[str, Any]:
    """The CLIs installed here, each account they run as and its models, and those to install."""
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


def forked(hmz: Any, flow: str) -> dict[str, Any]:
    """Copies a flow into the workspace, as `Flows.fork` does.

    Raises:
      RpcError: 400, with what refused it.
    """
    try:
        at = hmz.flows.fork(flow)
    except (ValueError, OSError) as why:
        raise _refused(str(why)) from why
    return {"said": f"copied {flow} to {at}", "at": str(at)}


def checked(hmz: Any, said: Mapping[str, Any]) -> dict[str, Any]:
    """Checks the epic a flow and its set-up make, as `hmz exec` does, without starting it.

    Every check `hmz exec` makes before an epic starts is made: the flow is found and loaded,
    every role and what fills it, the params, the budget, the epic to pick up and the backup
    targets -- the checks :class:`hmz.runtime.runner.Runner` makes as it is made -- and the
    price list as it is kept. Whether an env can be reached, and so where each harness goes
    on it, is not: that is asked of the env's machine.

    Args:
      hmz: Humanize, for the workspace.
      said: The flow and what it is set up with, as `epic.start` takes them.

    Returns:
      The flow as named, its ref, what it declares as :func:`declared` answers it, the name
      of the agent filling each agent role, the budget, the backup targets and every limit
      of the budget nothing it drives can enforce, in words.

    Raises:
      RpcError: 400 with the sentence `hmz exec` prints after `hmz exec: error: `.
    """
    from hmz import working_in
    from hmz.runtime import Refused

    flow: str = said["flow"]
    if flow.startswith("git+"):
        # Loaded only once fetched, and a check reaches no other machine.
        raise _refused(
            f"{flow} is fetched from another machine; check it once fetched."
        )
    agents, envs = _specs(said, "agents"), _specs(said, "envs")
    resume: bool | str = said.get("resume") or False
    backup = _targets(said.get("backup"))
    try:
        with working_in(hmz.workspace):
            runner = hmz.runner(
                flow,
                agents=agents,
                envs=envs,
                params=said.get("params"),
                budget=said.get("budget"),
                profile_flow=said.get("profile_flow", False),
                profile_environment=said.get("profile_environment", False),
                resume=resume,
                backup=backup,
            )
            try:
                unreadable = runner.unreadable(fetch=False)
            finally:
                # A driver starts nothing as it is made; what it holds goes all the same.
                asyncio.run(runner.aclose())
    except Refused as why:
        raise _refused(str(why)) from why
    return {
        "flow": flow,
        "ref": runner.impl.ref,
        "declared": declared(hmz, flow),
        "names": {role: one.name for role, one in runner.agents.items()},
        "budget": json.loads(runner.budget.model_dump_json()),
        "backup": list(runner.backup),
        "unreadable": unreadable,
    }


def _refused(why: str) -> RpcError:
    return RpcError(Code.REFUSED, why)


def _specs(said: Mapping[str, Any], name: str) -> dict[str, str]:
    """What each role is given, as `-a` or `-e` spells it after `<role>=`.

    Raises:
      RpcError: 400, for one that is not text.
    """
    given = cast("dict[str, object]", said.get(name) or {})
    if not all(isinstance(one, str) for one in given.values()):
        raise _refused(f"{name} is each role's spec, as text.")
    return cast("dict[str, str]", given)


def _targets(backup: object) -> list[str] | None:
    """The backup targets named, or None for the defaults.

    Raises:
      RpcError: 400, for anything but a list of names.
    """
    if backup is not None and not (
        isinstance(backup, list)
        and all(isinstance(one, str) for one in cast("list[object]", backup))
    ):
        raise _refused("backup is a list of backup target names.")
    return cast("list[str] | None", backup)


def _saved(budget: object) -> dict[str, Any]:
    """A budget a client sent, as settings writes one: every limit, the duration in ISO 8601.

    Args:
      budget: The budget, its duration in seconds as a client says one.

    Returns:
      The budget, and nothing at all for none, which erases the one kept. One whose duration
      is not one is left as it was said, for a start with it to be refused by its host.
    """
    if not isinstance(budget, dict) or not budget:
        return {}
    import datetime

    import pydantic

    said = cast("dict[str, Any]", budget)
    durations: pydantic.TypeAdapter[datetime.timedelta | None] = pydantic.TypeAdapter(
        datetime.timedelta | None
    )
    try:
        duration = durations.validate_python(said.get("duration"))
    except pydantic.ValidationError:
        return said
    unset: dict[str, Any] = {"cost": None, "output_tokens": None, "graceful": True}
    return unset | said | {"duration": durations.dump_python(duration, mode="json")}


def _settings(hmz: Any) -> Any:
    """A workspace's settings read afresh: its epics write them as well as this does."""
    from hmz.runtime import Hmz

    return Hmz(hmz.workspace).settings


def _hmz(call: Call) -> Any:
    """Humanize, for the workspace a call names."""
    from hmz.runtime import Hmz

    return Hmz(place(call.params["workspace"]))


def _holding(call: Call) -> Any:
    """Humanize, for the workspace a call names, checking an epic in this process."""
    from hmz.runtime import Holding

    return Holding(place(call.params["workspace"]))


def _setup(call: Call) -> dict[str, Any]:
    hmz = _hmz(call)
    remembers(hmz, call.params)()
    return declared(hmz, call.params["flow"])


def _backends(_: Call) -> dict[str, Any]:
    from pathlib import Path

    from hmz.runtime import Hmz

    return backends(Hmz(Path.home()))


#: Each method of the family, by name.
METHODS: Mapping[str, Handler] = {
    "flows.list": lambda call: listed(_hmz(call)),
    "flows.get": lambda call: offered(_hmz(call), call.params["name"]),
    "flows.backends": _backends,
    "flows.setup": _setup,
    "flows.fork": lambda call: forked(_hmz(call), call.params["flow"]),
    "flows.check": lambda call: checked(_holding(call), call.params),
}
