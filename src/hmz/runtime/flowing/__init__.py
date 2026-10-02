"""Everything humanize does to a flow: finding one, loading one, running one, and the drivers.

A flow is content -- somebody else's repository, forked and edited -- and the whole of what it
imports is :mod:`hmz.flows`: the protocols its agents and environments answer to, the
decorator that makes it a flow, and the exceptions it can catch. This is the other side of
that line.

What a driver and the engine promise each other is [spi.py](spi.py); what `-a`, `-e`, `-p` and
`-b` say is [specs.py](specs.py); the engine that defines, loads and runs flows is
[engine.py](engine.py), with what a flow declares read in [declaring.py](declaring.py), what it
is handed in [viewing.py](viewing.py), what a resumable run writes down in
[journaling.py](journaling.py) and what a ref names in [loading.py](loading.py); the drivers
over coding agent CLIs and over machines are [harnesses.py](harnesses.py) and
[environments.py](environments.py); and in-memory stand-ins for all of them, to test a flow
with, are [fakes.py](fakes.py). Where flows come from and what each is called is
[verses.py](verses.py) and [finding.py](finding.py); the skills a flow named that live
somewhere else are fetched by [skills.py](skills.py).

The arrow points one way. Everything here may name the flow API, and it names nothing here at
the top of its files -- what a flow legitimately needs from this layer, which is defining a
flow, loading another and making an outworlder, is reached from there when the flow asks for
it. So a module that moves here moves without a flow anywhere noticing, which is the point of
the line being where it is.

Nothing here drives a coding agent either. That is :mod:`hmz.coganchor`, which the harness
drivers are written against and which names nothing here.

Everything is fetched when it is named, for the reason the layer above does it: a command line
that only lists the places flows come from must not pay for the engine, and neither must a
menu of flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .declaring import AgentRole, Declaration, EnvRole, Grant
    from .engine import (
        Call,
        FlowImpl,
        LiveCall,
        Recorder,
        current,
        define_flow,
        full_view,
        load_flow,
        new_outworlder,
        run_flow,
        running,
    )
    from .environments import local_env, open_env, probe
    from .fakes import (
        FakeAgentDriver,
        FakeEnvDriver,
        FakeOutworlder,
        FakeSession,
        run_fake,
    )
    from .finding import (
        BUILTIN_AT,
        ENTRY,
        Offer,
        about,
        at,
        builtin,
        entry,
        find,
        fork,
        found,
        inside,
        offered,
        offers,
        resolved,
        within,
    )
    from .harnesses import open_agent, open_outworlder
    from .journaling import FlowStateImpl, Journal
    from .loading import FlowModule, Remote, forget
    from .skills import brought
    from .specs import (
        AgentSpec,
        AgentSpecError,
        BudgetSpecError,
        EnvSpec,
        EnvSpecError,
        ParamSpecError,
        SpecError,
        parse_agents,
        parse_budget,
        parse_duration,
        parse_envs,
        parse_params,
    )
    from .spi import (
        AGENT_CAPABILITIES,
        ENV_CAPABILITIES,
        HARNESS_CAPABILITIES,
        AgentDriver,
        BoundHook,
        EnvDriver,
        HookBridge,
        HookTable,
        Limits,
        OutworlderDriver,
        Placement,
        SessionHandle,
        Skill,
        TurnRequest,
        UsageSink,
        capabilities_of,
        default_result,
    )
    from .verses import (
        FLOWS,
        LOCAL,
        MINE,
        OFFICIAL,
        USER,
        Flowverse,
        flowverses,
        holds,
        nearest,
    )
    from .viewing import AgentView, EnvView, OutworlderView, SessionView

__all__ = [
    "AGENT_CAPABILITIES",
    "BUILTIN_AT",
    "ENTRY",
    "ENV_CAPABILITIES",
    "FLOWS",
    "HARNESS_CAPABILITIES",
    "LOCAL",
    "MINE",
    "OFFICIAL",
    "USER",
    "AgentDriver",
    "AgentRole",
    "AgentSpec",
    "AgentSpecError",
    "AgentView",
    "BoundHook",
    "BudgetSpecError",
    "Call",
    "Declaration",
    "EnvDriver",
    "EnvRole",
    "EnvSpec",
    "EnvSpecError",
    "EnvView",
    "FakeAgentDriver",
    "FakeEnvDriver",
    "FakeOutworlder",
    "FakeSession",
    "FlowImpl",
    "FlowModule",
    "FlowStateImpl",
    "Flowverse",
    "Grant",
    "HookBridge",
    "HookTable",
    "Journal",
    "Limits",
    "LiveCall",
    "Offer",
    "OutworlderDriver",
    "OutworlderView",
    "ParamSpecError",
    "Placement",
    "Recorder",
    "Remote",
    "SessionHandle",
    "SessionView",
    "Skill",
    "SpecError",
    "TurnRequest",
    "UsageSink",
    "about",
    "at",
    "brought",
    "builtin",
    "capabilities_of",
    "current",
    "default_result",
    "define_flow",
    "entry",
    "find",
    "flowverses",
    "forget",
    "fork",
    "found",
    "full_view",
    "holds",
    "inside",
    "load_flow",
    "local_env",
    "nearest",
    "new_outworlder",
    "offered",
    "offers",
    "open_agent",
    "open_env",
    "open_outworlder",
    "parse_agents",
    "parse_budget",
    "parse_duration",
    "parse_envs",
    "parse_params",
    "probe",
    "resolved",
    "run_fake",
    "run_flow",
    "running",
    "within",
]

#: Which module each of them is written in. One entry per name this package offers, so that
#: `from hmz.runtime.flowing import find` costs the module `find` is in rather than all of
#: them: the engine and every coding agent driver there is are behind some of these, and a
#: menu of flows must pay for none of it.
_WRITTEN = {
    "AGENT_CAPABILITIES": "hmz.runtime.flowing.spi",
    "AgentDriver": "hmz.runtime.flowing.spi",
    "AgentRole": "hmz.runtime.flowing.declaring",
    "AgentSpec": "hmz.runtime.flowing.specs",
    "AgentSpecError": "hmz.runtime.flowing.specs",
    "AgentView": "hmz.runtime.flowing.viewing",
    "BUILTIN_AT": "hmz.runtime.flowing.finding",
    "BoundHook": "hmz.runtime.flowing.spi",
    "BudgetSpecError": "hmz.runtime.flowing.specs",
    "Call": "hmz.runtime.flowing.engine",
    "Declaration": "hmz.runtime.flowing.declaring",
    "ENTRY": "hmz.runtime.flowing.finding",
    "ENV_CAPABILITIES": "hmz.runtime.flowing.spi",
    "EnvDriver": "hmz.runtime.flowing.spi",
    "EnvRole": "hmz.runtime.flowing.declaring",
    "EnvSpec": "hmz.runtime.flowing.specs",
    "EnvSpecError": "hmz.runtime.flowing.specs",
    "EnvView": "hmz.runtime.flowing.viewing",
    "FLOWS": "hmz.runtime.flowing.verses",
    "FakeAgentDriver": "hmz.runtime.flowing.fakes",
    "FakeEnvDriver": "hmz.runtime.flowing.fakes",
    "FakeOutworlder": "hmz.runtime.flowing.fakes",
    "FakeSession": "hmz.runtime.flowing.fakes",
    "FlowImpl": "hmz.runtime.flowing.engine",
    "FlowModule": "hmz.runtime.flowing.loading",
    "FlowStateImpl": "hmz.runtime.flowing.journaling",
    "Flowverse": "hmz.runtime.flowing.verses",
    "Grant": "hmz.runtime.flowing.declaring",
    "HARNESS_CAPABILITIES": "hmz.runtime.flowing.spi",
    "HookBridge": "hmz.runtime.flowing.spi",
    "HookTable": "hmz.runtime.flowing.spi",
    "Journal": "hmz.runtime.flowing.journaling",
    "LOCAL": "hmz.runtime.flowing.verses",
    "Limits": "hmz.runtime.flowing.spi",
    "LiveCall": "hmz.runtime.flowing.engine",
    "MINE": "hmz.runtime.flowing.verses",
    "OFFICIAL": "hmz.runtime.flowing.verses",
    "Offer": "hmz.runtime.flowing.finding",
    "OutworlderDriver": "hmz.runtime.flowing.spi",
    "OutworlderView": "hmz.runtime.flowing.viewing",
    "ParamSpecError": "hmz.runtime.flowing.specs",
    "Placement": "hmz.runtime.flowing.spi",
    "Recorder": "hmz.runtime.flowing.engine",
    "Remote": "hmz.runtime.flowing.loading",
    "SessionHandle": "hmz.runtime.flowing.spi",
    "SessionView": "hmz.runtime.flowing.viewing",
    "Skill": "hmz.runtime.flowing.spi",
    "SpecError": "hmz.runtime.flowing.specs",
    "TurnRequest": "hmz.runtime.flowing.spi",
    "USER": "hmz.runtime.flowing.verses",
    "UsageSink": "hmz.runtime.flowing.spi",
    "about": "hmz.runtime.flowing.finding",
    "at": "hmz.runtime.flowing.finding",
    "brought": "hmz.runtime.flowing.skills",
    "builtin": "hmz.runtime.flowing.finding",
    "capabilities_of": "hmz.runtime.flowing.spi",
    "current": "hmz.runtime.flowing.engine",
    "default_result": "hmz.runtime.flowing.spi",
    "define_flow": "hmz.runtime.flowing.engine",
    "entry": "hmz.runtime.flowing.finding",
    "find": "hmz.runtime.flowing.finding",
    "flowverses": "hmz.runtime.flowing.verses",
    "forget": "hmz.runtime.flowing.loading",
    "fork": "hmz.runtime.flowing.finding",
    "found": "hmz.runtime.flowing.finding",
    "full_view": "hmz.runtime.flowing.engine",
    "holds": "hmz.runtime.flowing.verses",
    "inside": "hmz.runtime.flowing.finding",
    "load_flow": "hmz.runtime.flowing.engine",
    "local_env": "hmz.runtime.flowing.environments",
    "nearest": "hmz.runtime.flowing.verses",
    "new_outworlder": "hmz.runtime.flowing.engine",
    "offered": "hmz.runtime.flowing.finding",
    "offers": "hmz.runtime.flowing.finding",
    "open_agent": "hmz.runtime.flowing.harnesses",
    "open_env": "hmz.runtime.flowing.environments",
    "open_outworlder": "hmz.runtime.flowing.harnesses",
    "parse_agents": "hmz.runtime.flowing.specs",
    "parse_budget": "hmz.runtime.flowing.specs",
    "parse_duration": "hmz.runtime.flowing.specs",
    "parse_envs": "hmz.runtime.flowing.specs",
    "parse_params": "hmz.runtime.flowing.specs",
    "probe": "hmz.runtime.flowing.environments",
    "resolved": "hmz.runtime.flowing.finding",
    "run_fake": "hmz.runtime.flowing.fakes",
    "run_flow": "hmz.runtime.flowing.engine",
    "running": "hmz.runtime.flowing.engine",
    "within": "hmz.runtime.flowing.finding",
}


def __getattr__(name: str) -> object:
    """Hands through what this package offers, out of the module it is written in.

    Args:
      name: What was asked for.

    Returns:
      The same object that module holds, so that there is one of each however it was reached.

    Raises:
      AttributeError: If nothing here is called that, as for any other module. It is also
        what sends Python looking for a module of that name beside this one, which is how
        `from hmz.runtime.flowing import engine` goes on being the module rather than this.
    """
    from importlib import import_module

    where_ = _WRITTEN.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)
