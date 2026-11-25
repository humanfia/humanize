"""`hmz flows`: the flows on offer in a workspace, what one declares, and an epic of one checked."""

from __future__ import annotations

import json
import re
import shlex
import sys
from typing import TYPE_CHECKING, Any

from hmz.cli.tree import (
    WORKSPACE,
    Arg,
    Command,
    Example,
    Field,
    Unread,
    table,
    whole,
    workspace,
)
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.cli.tree import Call
    from hmz.sdk.families.flows import Declared

__all__ = ["COMMANDS"]

#: Where one item of an `-a` or an `-e` ends and the next begins, as `hmz exec` splits them
#: (Section 7.2.1 of cli.md): a comma followed by a role and `=`.
_ITEMS = re.compile(r",\s*(?=[A-Za-z_][\w-]*=)")

#: The limits of a budget, as `-p budget.<limit>=` names each.
_LIMITS = ("duration", "cost", "output_tokens")


def _named(flow: str) -> str:
    """A flow as the daemon is told it: a path written from here, whole; a name as it is."""
    return whole(flow) if flow.startswith(("./", "../")) else flow


def _roles(given: Sequence[str] | None, flag: str) -> dict[str, str] | None:
    """What each role is given by every `-a`, or every `-e`: by role, as written after `=`.

    Raises:
      Unread: For an item that is not `<role>=<value>`, and for a role given twice.
    """
    if not given:
        return None
    said: dict[str, str] = {}
    for value in given:
        for item in _ITEMS.split(value):
            role, written, rest = item.strip().partition("=")
            role, rest = role.strip(), rest.strip()
            if not written or not role or not rest:
                raise Unread(
                    t(
                        "{flag} {item}: expected `ROLE=VALUE`",
                        flag=flag,
                        item=item.strip(),
                    )
                )
            if role in said:
                raise Unread(
                    t("{flag}: the role {role} is given twice", flag=flag, role=role)
                )
            said[role] = rest
    return said


def _set_up(call: Call) -> dict[str, Any]:
    """What a line sets an epic up with, as `flows.check` and `flows.setup` take it.

    Raises:
      Unread: For an `-a`, `-e`, `-p` or `--backup` that cannot be read.
    """
    from hmz.runtime.flowing.specs import SpecError, parse_budget, parse_params

    params: tuple[str, ...] = tuple(call.params or ())
    try:
        budget = parse_budget(params)
        read = parse_params(params)
    except SpecError as bad:
        raise Unread(str(bad)) from bad
    backup: list[str] | None = call.backup
    if backup is not None and "none" in backup:
        if set(backup) != {"none"}:
            raise Unread(
                t("`--backup none` cannot be given with another backup target")
            )
        backup = []
    return {
        "agents": _roles(call.agents, "-a"),
        "envs": _roles(call.envs, "-e"),
        "params": read or None,
        "budget": None if budget is None else json.loads(budget.model_dump_json()),
        "profile_flow": call.profile_flow or None,
        "profile_environment": call.profile_environment or None,
        "backup": backup,
    }


def _kinds(one: Mapping[str, Any]) -> set[str]:
    """The JSON types a param's schema lets it be."""
    kind = one.get("type")
    kinds: set[str] = {kind} if isinstance(kind, str) else set(kind or ())
    for each in one.get("anyOf") or ():
        kinds |= _kinds(each)
    return kinds


def _valued(text: str, kinds: set[str]) -> Any:
    """A param written on a line as the flow's schema types it, or as text where it is not one.

    What a set-up keeps is what the page's form keeps: a number as a number and a switch as
    one, so that whichever of them opens the flow next reads the same value.
    """
    if "boolean" in kinds and text.lower() in ("true", "false"):
        return text.lower() == "true"
    for kind, reads in (("integer", int), ("number", float)):
        if kind in kinds:
            try:
                return reads(text)
            except ValueError:
                continue
    return text


def _limits(budget: Mapping[str, Any] | None) -> list[str]:
    """A budget as the `-p` options that write it."""
    if not budget:
        return []
    said = [
        f"-p budget.{limit}={budget[limit]}"
        for limit in _LIMITS
        if budget.get(limit) is not None
    ]
    graceful = budget.get("graceful")
    if graceful is False:
        said.append("-p budget.graceful=false")
    elif isinstance(graceful, dict):
        said.extend(
            f"-p budget.graceful.{limit}=false"
            for limit in _LIMITS
            if graceful.get(limit) is False  # pyright: ignore[reportUnknownMemberType]
        )
    return said


def _options(remembered: Mapping[str, Any]) -> list[str]:
    """What a workspace last set a flow up with, as the options that say it again."""

    def pairs(flag: str, held: object) -> list[str]:
        if not isinstance(held, dict):
            return []
        return [
            f"{flag} "
            + shlex.quote(
                f"{key}={value if isinstance(value, str) else json.dumps(value)}"
            )
            for key, value in held.items()  # pyright: ignore[reportUnknownVariableType]
            # One kept as nothing is one left out: no line writes a param that is none.
            if value is not None
        ]

    said = [
        *pairs("-a", remembered.get("agents")),
        *pairs("-e", remembered.get("envs")),
        *pairs("-p", remembered.get("params")),
        *_limits(remembered.get("budget")),
    ]
    if remembered.get("profile_flow"):
        said.append("--profile-flow")
    if remembered.get("profile_environment"):
        said.append("--profile-environment")
    backup = remembered.get("backup")
    if isinstance(backup, list):
        targets: list[str] = backup or ["none"]  # pyright: ignore[reportUnknownVariableType]
        said.extend(f"--backup {shlex.quote(one)}" for one in targets)
    return said


def _touches(access: str, path: str) -> str:
    """What one rule of a permission lets an agent do to a path, in the page's words."""
    if access == "write":
        return t("writes {path}", path=path)
    if access == "read":
        return t("reads {path}", path=path)
    return t("keeps out of {path}", path=path)


def _permitted(permission: Mapping[str, Any]) -> str:
    """What a role's agent may touch, in the page's words."""
    presets = {
        "read-only": t("read-only@@preset"),
        "workspace-write": t("workspace-write@@preset"),
        "danger-full-access": t("danger-full-access@@preset"),
    }
    preset = str(permission.get("preset", ""))
    rules: list[dict[str, Any]] = permission.get("granular") or []
    return " · ".join(
        [
            presets.get(preset, preset),
            *(
                _touches(str(rule.get("access")), str(rule.get("path")))
                for rule in rules
            ),
            t("goes online") if permission.get("network") else t("stays offline"),
        ]
    )


def _typed(one: Mapping[str, Any]) -> str:
    """What a param takes, as its schema says it."""
    if "type" in one:
        kind = one["type"]
        return kind if isinstance(kind, str) else "|".join(map(str, kind))
    if "enum" in one:
        return "|".join(json.dumps(each) for each in one["enum"])
    if "anyOf" in one:
        return "|".join(_typed(each) for each in one["anyOf"])
    return str(one.get("$ref", "")).rpartition("/")[2]


def _under(rows: Sequence[Sequence[str]]) -> list[str]:
    """Rows under a heading: in columns, indented, each as long as the longest.

    A row of one cell is a line of its own, which no column is widened for.
    """
    columned = [row for row in rows if len(row) > 1]
    width = max((len(row) for row in columned), default=0)
    lines = iter(table([[*row, *[""] * (width - len(row))] for row in columned]))
    return [f"  {next(lines) if len(row) > 1 else row[0]}" for row in rows]


def _shown(flow: Declared) -> list[str]:
    """One flow as text: what it declares, what was last set up, and a line that starts it."""
    needs = t("required")
    lines = [flow.name]
    if flow.description:
        lines.append(flow.description)
    lines.extend(
        table(
            [
                [t("ref"), flow.ref],
                [t("resumable"), t("yes") if flow.resumable else t("no")],
            ]
        )
    )
    start = ["hmz", "exec", "-f", shlex.quote(flow.name)]
    lines.append(t("agents"))
    agents: list[list[str]] = []
    for role in flow.agents:
        if role.auto:
            agents.append([role.name + t(" (a person, answering here)")])
            continue
        agents.append(
            [
                role.name,
                needs if role.required else t("optional"),
                ", ".join(role.clis) or t("No harness installed here can fill it."),
                _permitted(role.permission),
                t("skills: {names}", names=", ".join(role.skills))
                if role.skills
                else "",
            ]
        )
        if role.required:
            start.append(f"-a {role.name}=HARNESS/MODEL")
    lines.extend(_under(agents) if agents else [f"  {t('none')}"])
    lines.append(t("environments"))
    envs: list[list[str]] = []
    for role in flow.envs:
        if role.auto:
            envs.append([role.name + t(" (the folder the epic runs in)")])
            continue
        asks = {
            "cpu": role.cpu,
            "memory": role.memory,
            "gpu": role.gpu,
            "image": role.image,
        }
        envs.append(
            [
                role.name,
                needs if role.required else t("optional"),
                " ".join(f"{name}={value}" for name, value in asks.items() if value),
            ]
        )
        if role.required:
            start.append(f"-e {role.name}=ENV")
    lines.extend(_under(envs) if envs else [f"  {t('none')}"])
    lines.append(t("params"))
    params: list[list[str]] = []
    must: list[str] = flow.params.get("required") or []
    properties: dict[str, dict[str, Any]] = flow.params.get("properties") or {}
    for key, one in properties.items():
        default = json.dumps(one["default"]) if "default" in one else ""
        params.append(
            [
                key,
                _typed(one),
                needs if key in must else default,
                " — ".join(
                    str(one[part]) for part in ("title", "description") if one.get(part)
                ),
            ]
        )
        if key in must:
            start.append(f"-p {key}=VALUE")
    lines.extend(_under(params) if params else [f"  {t('none')}"])
    if options := _options(flow.remembered):
        lines.extend(
            [t("What this folder was last set up with"), f"  {' '.join(options)}"]
        )
    start.extend(["-p budget.cost=USD", "TASK"])
    lines.extend([t("Start the flow"), f"  {' '.join(start)}"])
    return lines


def _list(call: Call) -> None:
    offered = call.client.flows.list(workspace(call))
    call.answers(
        offered.answer,
        table([[one.name, one.whose, one.about] for one in offered.flows]),
    )
    if not offered.flows and not call.json:
        said = t("No flows installed yet.") + t(
            " A flow is what an epic runs. Install one from a flowverse."
        )
        print(said, file=sys.stderr)


def _show(call: Call) -> None:
    flow = call.client.flows.get(call.name, workspace(call))
    call.answers(flow.answer, _shown(flow))


def _backends(call: Call) -> None:
    backends = call.client.flows.backends()
    installed: list[list[str]] = []
    for cli, accounts in backends.clis.items():
        for account in accounts:
            runs = f"{cli}@{account.name}" if account.name else cli
            installed.extend(
                [f"{runs}/{model.name}", ", ".join(model.efforts)]
                for model in account.models
            )
            if not account.models:
                installed.append([runs, t("No models listed")])
    lines = [t("Installed")]
    if installed:
        lines.extend(_under(installed))
    else:
        lines.append(f"  {t('No harness is installed on this daemon.')}")
    if backends.installable:
        lines.append(t("Not installed"))
        lines.extend(
            _under(
                [
                    row
                    for cli, models in backends.installable.items()
                    for row in (
                        [
                            [f"{cli}/{one.name}", ", ".join(one.efforts)]
                            for one in models
                        ]
                        or [[cli]]
                    )
                ]
            )
        )
    lines.append(t("environments"))
    lines.extend(f"  {one}" for one in backends.envs)
    call.answers(backends.answer, lines)


def _check(call: Call) -> int | None:
    set_up = _set_up(call)
    checked = call.client.flows.check(
        workspace(call), _named(call.flow), resume=call.resume or None, **set_up
    )
    lines = [
        t("An epic set up like this can start."),
        *table(
            [
                [t("ref"), checked.ref],
                [
                    t("agents"),
                    ", ".join(f"{role}={name}" for role, name in checked.names.items())
                    or t("none"),
                ],
                [t("budget"), " ".join(_limits(checked.budget)) or t("none")],
                [t("Backup"), ", ".join(checked.backup) or t("none")],
            ]
        ),
    ]
    if checked.unreadable:
        lines.append(checked.unreadable)
    call.answers(checked.answer, lines)
    return None


def _setup(call: Call) -> int | None:
    set_up = _set_up(call)
    at = workspace(call)
    flows = call.client.flows
    # The line is the whole set-up: a role, a param or a profile it does not say is one the
    # workspace no longer keeps, as the page's form saves all of it at once.
    properties: Mapping[str, Mapping[str, Any]] = (
        flows.get(call.flow, at).params.get("properties") or {}
    )
    written: dict[str, str] = set_up["params"] or {}
    set_up |= {
        "agents": set_up["agents"] or {},
        "envs": set_up["envs"] or {},
        "params": {
            key: _valued(text, _kinds(properties.get(key) or {}))
            for key, text in written.items()
        },
        "profile_flow": bool(call.profile_flow),
        "profile_environment": bool(call.profile_environment),
    }
    flow = flows.setup(at, call.flow, **set_up)
    call.answers(
        flow.answer,
        [
            t(
                "The set-up of the flow {flow} was saved for the folder {folder}.",
                flow=flow.name,
                folder=at,
            )
        ],
    )
    return None


def _fork(call: Call) -> None:
    forked = call.client.flows.fork(workspace(call), call.flow)
    call.answers({"said": forked.said, "at": forked.at}, [forked.said])


#: What `check` and `setup` take to say what an epic is set up with, as `hmz exec` spells it.
_SET_UP = (
    Arg(
        ("-a", "--agents"),
        "the agent for one agent role, as "
        "`HARNESS[@ACCOUNT]/MODEL[:EFFORT]` or the name of a nous",
        metavar="ROLE=AGENT",
        many=True,
    ),
    Arg(
        ("-e", "--envs"),
        "the environment for one environment role, as `hmz exec -e` "
        "writes one, for example `local` or `ssh@NAME/DIRECTORY`",
        metavar="ROLE=ENV",
        many=True,
    ),
    Arg(
        ("-p", "--params"),
        "one param of the flow, or one limit of the budget as "
        "`budget.cost=5`, `budget.duration=1h` or "
        "`budget.output_tokens=200k`",
        metavar="KEY=VALUE",
        many=True,
    ),
    Arg(("--profile-flow",), "profile the flow's own Python code during the epic"),
    Arg(("--profile-environment",), "profile the programs the epic's agents start"),
    Arg(
        ("--backup",),
        "a backup target the epic is backed up to; `none` for no "
        "backup; the default targets when not given",
        metavar="NAME",
        many=True,
    ),
)

#: What a flow declares, as `show` and `setup` answer it and `check` answers it under `declared`.
_DECLARED = (
    Field("name", "string", "the name of the flow"),
    Field("ref", "string", "where the flow is loaded from"),
    Field("description", "string", "what the flow says it does"),
    Field("resumable", "boolean", "whether an epic of the flow can be resumed"),
    Field(
        "resumes",
        "boolean",
        "whether the workspace has an epic of the flow to resume now",
    ),
    Field("agents", "list", "the agent roles the flow declares"),
    Field("agents[].name", "string", "the role, as `-a ROLE=` names it"),
    Field("agents[].required", "boolean", "whether the role must be given an agent"),
    Field(
        "agents[].auto",
        "boolean",
        "whether the role is a person answering, which takes no agent",
    ),
    Field(
        "agents[].harness",
        "string",
        "the only harness that can fill the role, or empty for any",
    ),
    Field(
        "agents[].permission",
        "object",
        "what the role's agent may touch: `preset`, `network`, and "
        "`granular` as a list of `path` and `access`",
    ),
    Field("agents[].skills", "list", "the skills the role's agent is given"),
    Field(
        "agents[].clis",
        "list",
        "the harnesses installed on the daemon's machine that can fill the role",
    ),
    Field("envs", "list", "the environment roles the flow declares"),
    Field("envs[].name", "string", "the role, as `-e ROLE=` names it"),
    Field(
        "envs[].required", "boolean", "whether the role must be given an environment"
    ),
    Field(
        "envs[].auto",
        "boolean",
        "whether the role is the folder the epic runs in, which takes no environment",
    ),
    Field("envs[].cpu", "number|null", "how many CPUs the role asks for, or null"),
    Field("envs[].memory", "string|null", "how much memory the role asks for, or null"),
    Field("envs[].gpu", "number|null", "how many GPUs the role asks for, or null"),
    Field("envs[].image", "string|null", "the image the role asks for, or null"),
    Field(
        "params",
        "object",
        "the flow's params as a JSON schema; each key of "
        "`properties` is a `-p KEY=VALUE`",
    ),
    Field(
        "remembered",
        "object",
        "what the workspace last set the flow up with: `agents`, "
        "`envs`, `params`, `budget`, `profile_flow`, "
        "`profile_environment`, `backup`",
    ),
)

COMMANDS = (
    Command(
        "flows",
        "list flows, show what one declares, check and set up an epic",
        says="A flow is what an epic runs. These commands list the flows "
        "on offer in a workspace, show what one declares, list the "
        "harnesses that can fill its roles, check an epic before it "
        "starts, save a workspace's set-up of a flow, and copy a "
        "flow into a workspace to change it. Flows are installed "
        "with `hmz flowverses`.",
        commands=(
            Command(
                "list",
                "list the flows on offer in a workspace",
                args=(WORKSPACE,),
                examples=(
                    Example(
                        "hmz flows list",
                        "list the flows on offer in the current directory",
                    ),
                    Example(
                        "hmz flows list -w ~/code/app --json | jq -r '.flows[].name'",
                        "print the names of the flows on offer in the folder "
                        "~/code/app, with jq",
                    ),
                ),
                prints="One line per flow: its name, where it came from, and what "
                "it does.",
                output=(
                    Field("flows", "list", "the flows on offer"),
                    Field("flows[].name", "string", "the name the flow is started by"),
                    Field(
                        "flows[].whose",
                        "string",
                        "where the flow came from: `local` for the workspace's own, "
                        "`user` for yours, or the name of a flowverse",
                    ),
                    Field("flows[].about", "string", "what the flow does, in one line"),
                    Field(
                        "flow",
                        "string",
                        "the flow last set up in the workspace, or empty",
                    ),
                    Field("running", "list", "the flows running in the workspace now"),
                    Field("running[].ref", "string", "the ref of the running flow"),
                    Field("running[].name", "string", "the name of the running flow"),
                    Field(
                        "running[].depth",
                        "integer",
                        "how many flows called it; 0 for the flow the epic started "
                        "with",
                    ),
                    Field("running[].since", "string", "when it began, ISO 8601"),
                    Field("running[].task", "string", "the task it was given"),
                ),
                methods=("flows.list",),
                see=("flows show", "flowverses install"),
                run=_list,
            ),
            Command(
                "show",
                "show what one flow declares: its roles, params and last set-up",
                says="Prints what is needed to start an epic of the flow. Each "
                "agent role takes `-a ROLE=HARNESS/MODEL`, each environment "
                "role `-e ROLE=ENV`, each param `-p KEY=VALUE`, and the "
                "budget at least one of `-p budget.cost=USD`, `-p "
                "budget.duration=TIME` and `-p budget.output_tokens=N`. `hmz "
                "flows backends` lists the harnesses and models.",
                args=(
                    Arg(
                        ("name",), "the name of the flow, as `hmz flows list` prints it"
                    ),
                    WORKSPACE,
                ),
                examples=(
                    Example(
                        "hmz flows show ralph_loop",
                        "show what the flow `ralph_loop` declares",
                    ),
                    Example(
                        "hmz flows show ralph_loop --json | jq -r "
                        "'.agents[] | select(.required and (.auto | not)) | .name'",
                        "print the names of the agent roles of `ralph_loop` that "
                        "need an agent, with jq",
                    ),
                ),
                prints="The flow's name and description, its ref, whether it is "
                "resumable, each agent role with the harnesses installed "
                "that can fill it and what it may touch, each environment "
                "role, each param with its type, default and description, "
                "the options this folder last set it up with, and an `hmz "
                "exec` line to fill in.",
                output=_DECLARED,
                methods=("flows.get",),
                see=("flows backends", "flows check", "flows list"),
                run=_show,
            ),
            Command(
                "backends",
                "list the installed harnesses with their accounts and models",
                says="Lists what can fill an agent role on the daemon's machine, "
                "each written as `-a ROLE=` takes it: `HARNESS/MODEL` for "
                "this machine's own sign-in, `HARNESS@ACCOUNT/MODEL` for an "
                "account; an effort goes after the model as `:EFFORT`. Also "
                "lists the harnesses not installed and the backends an "
                "environment can be put on.",
                examples=(
                    Example(
                        "hmz flows backends",
                        "list every harness, account and model that can fill an "
                        "agent role",
                    ),
                    Example(
                        "hmz flows backends --json | jq -r '.clis | keys[]'",
                        "print the names of the installed harnesses, with jq",
                    ),
                ),
                prints="Under Installed, one line per harness, account and model, "
                "written as `-a` takes it, then the efforts the model takes; "
                "under Not installed, the same for harnesses that can be "
                "installed; under environments, the backends `-e` takes.",
                output=(
                    Field("clis", "object", "the installed harnesses, by name"),
                    Field(
                        "clis.<harness>.accounts",
                        "list",
                        "the accounts the harness runs as, this machine's own "
                        "sign-in first",
                    ),
                    Field(
                        "clis.<harness>.accounts[].name",
                        "string",
                        "the account's name; empty for this machine's own sign-in",
                    ),
                    Field(
                        "clis.<harness>.accounts[].models",
                        "list",
                        "the models the harness runs as that account, each `name` "
                        "and `efforts`",
                    ),
                    Field(
                        "clis.<harness>.accounts[].asked",
                        "string",
                        "when the harness was last asked for its models, or empty if "
                        "never",
                    ),
                    Field(
                        "installable",
                        "object",
                        "the harnesses that can be installed, by name, each a list "
                        "of models with `name` and `efforts`",
                    ),
                    Field(
                        "envs",
                        "list",
                        "the backends an environment can be put on, as `-e` writes "
                        "each",
                    ),
                ),
                methods=("flows.backends",),
                see=("flows show", "flows check"),
                run=_backends,
            ),
            Command(
                "check",
                "check that an epic of a flow would start, without starting it",
                says="Takes the options `hmz exec` takes and checks everything "
                "`hmz exec` checks before an epic starts: the flow, each "
                "role and what fills it, the params, the budget, the epic to "
                "resume and the backup targets. Starts no agent and no "
                "environment, and does not check whether an environment can "
                "be reached.",
                args=(
                    Arg(
                        ("flow",),
                        "the flow: a name `hmz flows list` prints, or a path or ref "
                        "as `hmz exec -f` takes one",
                    ),
                    *_SET_UP,
                    Arg(
                        ("--resume",),
                        "check resuming the newest epic of this flow in the "
                        "workspace instead of starting a new one",
                    ),
                    WORKSPACE,
                ),
                examples=(
                    Example(
                        "hmz flows check ralph_loop -a coder=claude/claude-opus-5:high "
                        "-p budget.cost=5",
                        "check an epic of `ralph_loop` with one agent and a cost "
                        "limit of five dollars",
                    ),
                    Example(
                        "hmz flows check ralph_loop --resume -p budget.cost=5 --json "
                        "| jq .names",
                        "check resuming the newest epic of `ralph_loop` and print "
                        "the agent filling each role as JSON",
                    ),
                ),
                prints="A line saying the epic can start, then the flow's ref, the "
                "agent filling each role, the budget and the backup targets, "
                "and any limit of the budget that cannot be enforced.",
                output=(
                    Field("flow", "string", "the flow, as it was named"),
                    Field("ref", "string", "where the flow is loaded from"),
                    Field(
                        "declared",
                        "object",
                        "what the flow declares, with the fields `hmz flows show "
                        "--json` prints",
                    ),
                    Field(
                        "names",
                        "object",
                        "the name of the agent filling each agent role, by role",
                    ),
                    Field(
                        "budget",
                        "object|null",
                        "the budget the epic would run under: `duration`, `cost`, "
                        "`output_tokens` and `graceful`",
                    ),
                    Field("backup", "list", "the backup targets the epic would go to"),
                    Field(
                        "unreadable",
                        "string",
                        "every limit of the budget that nothing the epic runs can "
                        "enforce, in words, or empty",
                    ),
                ),
                methods=("flows.check",),
                see=("flows show", "flows backends", "flows setup"),
                run=_check,
            ),
            Command(
                "setup",
                "save what a workspace starts a flow with",
                says="Saves the agents, environments, params, budget, profiling "
                "and backup targets a workspace runs a flow with. A new epic "
                "of that flow in the workspace opens with them filled in, on "
                "the web page and in the terminal interface. Every required "
                "agent role needs an agent and the budget needs at least one "
                "limit.",
                args=(
                    Arg(
                        ("flow",), "the name of the flow, as `hmz flows list` prints it"
                    ),
                    *_SET_UP,
                    WORKSPACE,
                ),
                examples=(
                    Example(
                        "hmz flows setup ralph_loop -a coder=claude/claude-opus-5:high "
                        "-p budget.cost=5",
                        "save that `ralph_loop` runs in this folder with one agent "
                        "and a cost limit of five dollars",
                    ),
                    Example(
                        "hmz flows setup ralph_loop -w ~/code/app -a coder=codex/gpt-5 "
                        "-p budget.duration=2h --backup none",
                        "save the set-up of `ralph_loop` for the folder ~/code/app, "
                        "with a time limit and no backup",
                    ),
                ),
                prints="One line saying the set-up was saved.",
                output=_DECLARED,
                methods=("flows.get", "flows.setup"),
                see=("flows show", "flows check", "workspaces forget"),
                run=_setup,
            ),
            Command(
                "fork",
                "copy a flow into a workspace to change it there",
                says="Copies a flow into the workspace's own flows, where it can "
                "be edited. The copy is offered in that workspace as a "
                "`local` flow under the same name.",
                args=(
                    Arg(
                        ("flow",),
                        "the name of the flow to copy, as `hmz flows list` prints it",
                    ),
                    WORKSPACE,
                ),
                examples=(
                    Example(
                        "hmz flows fork ralph_loop",
                        "copy the flow `ralph_loop` into the current directory",
                    ),
                    Example(
                        "hmz flows fork ralph_loop -w ~/code/app --json | jq -r .at",
                        "copy `ralph_loop` into the folder ~/code/app and print "
                        "where the copy is, with jq",
                    ),
                ),
                prints="What was copied and where to.",
                output=(
                    Field("said", "string", "what was done, in words"),
                    Field("at", "string", "the path of the copy"),
                ),
                methods=("flows.fork",),
                see=("flows list", "flows show"),
                run=_fork,
            ),
        ),
    ),
)
