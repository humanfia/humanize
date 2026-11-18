"""``hmz fence`` -- what this machine can hold, and what a role's fence says of a path.

- `check [-f FLOW] [-a ROLE=SPEC] [--json]`: report what this machine can enforce, and with a
  flow the fence its role resolves to.
- `explain PATH [-f FLOW] [-a ROLE=SPEC] [--json]`: say whether a path is readable, writable
  or denied under that fence, and what holds it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hmz.coganchor.backends import Profile
    from hmz.coganchor.fence import Fence
    from hmz.runtime.flowing import Declaration
    from hmz.runtime.flowing.specs import AgentSpec

__all__ = ["fence"]

#: Landlock's first ABI with TCP rules; ABI 6 adds socket scoping.
_NETWORK_ABI = 4
#: The value of `ptrace_scope` at and above which a supervisor is refused.
_PTRACE_SCOPE_RESTRICTED = 2


def fence(argv: list[str]) -> int:
    """Checks what this machine can fence, or explains one path under a role's fence.

    Args:
      argv: What followed the command name.

    Returns:
      Zero where the fence the role asks for can be put up and any asked path was explained;
      one where it cannot be put up, or the machine could not be asked; two for a usage
      error or a flow that does not load.
    """
    parser = argparse.ArgumentParser(
        prog="hmz fence",
        description="Check what this machine can fence, and explain a path under a flow's role.",
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    check = commands.add_parser(
        "check",
        help="report what this machine can hold, and the fence a role resolves to",
    )
    _options(check, flow_required=False)
    check.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="write one object to stdout, for a program to read",
    )
    explain = commands.add_parser(
        "explain", help="say whether a path is readable, writable or denied"
    )
    _options(explain, flow_required=True)
    explain.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="write one object to stdout, for a program to read",
    )
    explain.add_argument(
        "path", metavar="PATH", help="the path to explain, as it is written"
    )
    args = parser.parse_args(argv)

    from .output import Out

    with Out(as_json=args.as_json) as out:
        if args.command == "explain":
            return _explain(parser, args, out)
        return _check(parser, args, out)


def _options(parser: argparse.ArgumentParser, *, flow_required: bool) -> None:
    """Adds the flow and role selectors both subcommands take."""
    parser.add_argument(
        "-f",
        "--flow",
        required=flow_required,
        metavar="FLOW",
        help="the flow whose role's fence is asked about",
    )
    parser.add_argument(
        "-a",
        "--agents",
        action="append",
        default=[],
        metavar="ROLE=SPEC",
        help="the role to ask about: ROLE=CLI[@PROVIDER]/MODEL[:EFFORT], as `hmz exec` takes it",
    )


def _resolved(parser: argparse.ArgumentParser, name: str) -> Declaration:
    """The declaration of the flow `-f` names, or a usage error."""
    from hmz.flows import FlowException
    from hmz.runtime.flowing import resolved

    try:
        return resolved(name).describe()
    except FlowException as why:
        parser.error(str(why))
        raise AssertionError("parser.error returned") from why


def _role(
    parser: argparse.ArgumentParser,
    declaration: Declaration,
    said: Sequence[str],
) -> tuple[Any, AgentSpec | None]:
    """The one agent role asked about, and the `-a` that named it, or a usage error."""
    from hmz.runtime.flowing.specs import SpecError, parse_agents

    try:
        specs = parse_agents(list(said))
    except SpecError as why:
        parser.error(str(why))
        raise AssertionError("parser.error returned") from why
    if len(specs) > 1:
        parser.error("fence asks about one role: give one -a")
    roles = [one for one in declaration.agents if not one.auto]
    if specs:
        spec = specs[0]
        role = declaration.agent(spec.role)
        if role is None or role.auto:
            parser.error(f"{spec.role}: the flow declares no such agent role")
        return role, spec
    if len(roles) != 1:
        names = ", ".join(one.name for one in roles) or "no agent role"
        parser.error(f"the flow declares {names}: name one with -a ROLE=CLI/MODEL")
    return roles[0], None


def _profile(role: Any, spec: AgentSpec | None) -> Profile | None:
    """What coganchor knows of the CLI the role runs, where it knows one."""
    from hmz.coganchor import backends

    cli = (
        spec.cli
        if spec is not None
        else (role.harness.value if role.harness is not None else "")
    )
    return backends.named(cli) if cli else None


def _fence(role: Any, spec: AgentSpec | None) -> Fence:
    """The fence a role runs under, as a turn of it would be drawn."""
    from hmz.runtime.flowing.harnessing import fenced

    return fenced(
        role.permission,
        workdir=str(Path.cwd()),
        home=str(Path.home()),
        profile=_profile(role, spec),
        environ=os.environ,
    )


def _facts() -> dict[str, Any]:
    """What `coganchor internal able` says of this machine, with its chosen backend."""
    from hmz.coganchor import fence as held

    return held.facts(held.chosen())


def _check(parser: argparse.ArgumentParser, args: argparse.Namespace, out: Any) -> int:
    """Reports the machine's probes, and the fence a role resolves to where a flow is given."""
    from hmz.coganchor import fence as held

    try:
        told = _facts()
    except OSError as why:
        print(f"hmz fence: {why}", file=sys.stderr)
        return 1
    told.pop("unheld", None)
    role = spec = fence = why = None
    if args.flow:
        declaration = _resolved(parser, args.flow)
        role, spec = _role(parser, declaration, args.agents)
        fence = _fence(role, spec)
        why = held.unheld(fence)
    needed = "net" if role is not None and role.permission.network else "fs"
    holds = told.get(needed) is True and why is None
    if args.as_json:
        out.record(
            **told,
            sandbox=held.chosen(),
            fence=None
            if fence is None
            else {
                "read": list(fence.read),
                "write": list(fence.write),
                "keep": list(fence.keep),
                "deny": list(fence.deny),
                "hosts": list(fence.hosts),
                "tmp": fence.tmp,
                "listen": list(fence.listen),
            },
            unheld=why,
        )
    else:
        for line in _lines(told, held.chosen(), fence, why, needed if role else ""):
            out.printed(line)
    return 0 if holds else 1


def _table(value: object) -> dict[str, Any]:
    """One of the objects `coganchor internal able` nests, or nothing."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _lines(
    told: dict[str, Any],
    sandbox: str,
    fence: Fence | None,
    why: str | None,
    needed: str,
) -> list[str]:
    """The lines a person reads, one row per fact."""
    backends = _table(told.get("backend"))
    chosen = backends.get(needed) if needed else backends.get("fs")
    lines = [f"sandbox        {sandbox} -> {chosen or 'none'}"]
    landlock = _table(told.get("landlock"))
    if landlock:
        abi = landlock.get("abi")
        if not isinstance(abi, int) or abi == 0:
            lines.append(
                "landlock       missing: no Landlock (paths need ABI 1, the network 4)"
            )
        else:
            missing: list[str] = []
            if abi < _NETWORK_ABI:
                missing.append("network cut unavailable (needs ABI 4)")
            if not landlock.get("scope"):
                missing.append("socket scoping unavailable (needs ABI 6)")
            lines.append(
                f"landlock       ABI {abi}; "
                + ("; ".join(missing) if missing else "paths and TCP")
            )
    seccomp = _table(told.get("seccomp"))
    if seccomp:
        lines.append(
            "seccomp        user notification "
            + (
                "available"
                if seccomp.get("notify")
                else "missing (the network cut needs it)"
            )
        )
    loopback = _table(told.get("loopback"))
    if loopback:
        scope = loopback.get("ptrace_scope")
        if scope is None:
            scope_said = "unreadable"
        elif scope >= _PTRACE_SCOPE_RESTRICTED:
            scope_said = f"{scope} (restricted: a supervisor needs it below 2)"
        else:
            scope_said = str(scope)
        lines.append(
            "loopback       pidfd_getfd "
            f"{'available' if loopback.get('pidfd_getfd') else 'missing'}; "
            f"ptrace_scope {scope_said}"
        )
    bwrap = _table(told.get("bubblewrap"))
    if bwrap:
        lines.append(
            "bubblewrap     fs "
            f"{'yes' if bwrap.get('fs') else 'no'}, net "
            f"{'yes' if bwrap.get('net') else 'no'}"
        )
    seatbelt = _table(told.get("seatbelt"))
    if seatbelt:
        lines.append(
            "seatbelt       fs "
            f"{'yes' if seatbelt.get('fs') else 'no'}, net "
            f"{'yes' if seatbelt.get('net') else 'no'}"
        )
    if fence is not None:
        lines.append(
            f"fence          write {len(fence.write)}, read {len(fence.read)}, "
            f"keep {len(fence.keep)}, deny {len(fence.deny)}, "
            f"hosts {len(fence.hosts)}, listen {len(fence.listen)}"
        )
        lines.append(f"carve-outs     {why or 'none unheld'}")
    return lines


def _explain(
    parser: argparse.ArgumentParser, args: argparse.Namespace, out: Any
) -> int:
    """Says how much of one path the role's fence grants, and what holds it."""
    declaration = _resolved(parser, args.flow)
    role, spec = _role(parser, declaration, args.agents)
    fence = _fence(role, spec)
    path = str(Path(args.path).expanduser().absolute())
    level, why = fence.explain(path)
    if args.as_json:
        out.record(path=path, level=level, why=why)
    else:
        out.printed(f"{path}: {level} ({why})")
    return 0
