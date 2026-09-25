"""Everything humanize does to a flow: finding one, reading one, driving one, compiling one.

A flow is content -- somebody else's repository, forked and edited -- and the whole of what it
imports is :mod:`hmz.flows`: the protocols its agents and environments answer to, the
decorator that makes it a flow, and the exceptions it can catch. This is the other side of
that line, and for now it holds two flow APIs.

The new one is written against :mod:`hmz.flows`. What a driver and the engine promise each
other is [spi.py](spi.py); what `-a`, `-e`, `-p` and `-b` say is [specs.py](specs.py); the
engine that defines, loads and runs flows is [engine.py](engine.py), with what a flow declares
read in [declaring.py](declaring.py), what it is handed in [viewing.py](viewing.py), what a
resumable run writes down in [journaling.py](journaling.py) and what a ref names in
[loading.py](loading.py); the drivers over coding agent CLIs and over machines are
[harnesses.py](harnesses.py) and [environments.py](environments.py); and in-memory stand-ins
for all of them, to test a flow with, are [fakes.py](fakes.py).

The old one is written against :mod:`hmz._legacy_flows`, and goes when every way in has moved
over. Where flows come from and what each is called is [verses.py](verses.py) and
[finding.py](finding.py); what a flow says it drives, and what it takes for one flow to run
another, is [driving.py](driving.py); the two readings of a flow that refuse one before it can
cost anything are [checking.py](checking.py) and [proving.py](proving.py); an atlas is
compiled by [prophesying.py](prophesying.py) into the graph [prophecy.py](prophecy.py)
describes, and a run of one is walked by [stepping.py](stepping.py); the skills a flow named
that live somewhere else are fetched by [skills.py](skills.py).

The arrow points one way. Everything here may name either flow API, and neither names
anything here at the top of its file -- what a flow legitimately needs from this layer, which
is defining a flow, loading another and making an outworlder, is reached from there when the
flow asks for it. So a module that moves here moves without a flow anywhere noticing, which is
the point of the line being where it is.

Nothing here drives a coding agent either. That is :mod:`hmz.coganchor`, which this is written
against and which names nothing here.

Everything is fetched when it is named, for the reason the layer above does it: a command line
that only lists the places flows come from must not pay for the `ast` of two readings, and
neither must a menu of flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .checking import Capability, Finding, briefed, catalogue, checked
    from .declaring import AgentRole, Declaration, EnvRole, Grant
    from .driving import (
        Entry,
        NotAFlow,
        Place,
        Running,
        carries,
        configures,
        container,
        declared,
        drives,
        load,
        resumes,
        running,
        set_up,
        wanted,
    )
    from .engine import (
        Call,
        FlowImpl,
        LiveCall,
        Recorder,
        define_flow,
        full_view,
        load_flow,
        new_outworlder,
        run_flow,
    )
    from .environments import local_env, open_env
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
        PROPHECY,
        Offer,
        about,
        at,
        entry,
        find,
        foretold,
        fork,
        found,
        held,
        inside,
        loaded,
        offered,
        offers,
        reading,
        within,
    )
    from .harnesses import open_agent
    from .journaling import FlowStateImpl, Journal
    from .loading import FlowModule, Remote
    from .prophecy import (
        Edge,
        Node,
        Prophecy,
        Shape,
        Shipped,
        canonical,
        digest,
        kept,
        told,
    )
    from .prophecy import shipped as foreshipped
    from .prophesying import Prophesied, is_atlas, prophesied
    from .proving import (
        ALWAYS_DONE,
        NEVER_DONE,
        SILENT,
        Outcome,
        Proof,
        Scenario,
        proved,
    )
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
    from .stepping import walking
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
    "ALWAYS_DONE",
    "BUILTIN_AT",
    "ENTRY",
    "ENV_CAPABILITIES",
    "FLOWS",
    "HARNESS_CAPABILITIES",
    "LOCAL",
    "MINE",
    "NEVER_DONE",
    "OFFICIAL",
    "PROPHECY",
    "SILENT",
    "USER",
    "AgentDriver",
    "AgentRole",
    "AgentSpec",
    "AgentSpecError",
    "AgentView",
    "BoundHook",
    "BudgetSpecError",
    "Call",
    "Capability",
    "Declaration",
    "Edge",
    "Entry",
    "EnvDriver",
    "EnvRole",
    "EnvSpec",
    "EnvSpecError",
    "EnvView",
    "FakeAgentDriver",
    "FakeEnvDriver",
    "FakeOutworlder",
    "FakeSession",
    "Finding",
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
    "Node",
    "NotAFlow",
    "Offer",
    "Outcome",
    "OutworlderDriver",
    "OutworlderView",
    "ParamSpecError",
    "Place",
    "Placement",
    "Proof",
    "Prophecy",
    "Prophesied",
    "Recorder",
    "Remote",
    "Running",
    "Scenario",
    "SessionHandle",
    "SessionView",
    "Shape",
    "Shipped",
    "Skill",
    "SpecError",
    "TurnRequest",
    "UsageSink",
    "about",
    "at",
    "briefed",
    "brought",
    "canonical",
    "capabilities_of",
    "carries",
    "catalogue",
    "checked",
    "configures",
    "container",
    "declared",
    "default_result",
    "define_flow",
    "digest",
    "drives",
    "entry",
    "find",
    "flowverses",
    "foreshipped",
    "foretold",
    "fork",
    "found",
    "full_view",
    "held",
    "holds",
    "inside",
    "is_atlas",
    "kept",
    "load",
    "load_flow",
    "loaded",
    "local_env",
    "nearest",
    "new_outworlder",
    "offered",
    "offers",
    "open_agent",
    "open_env",
    "parse_agents",
    "parse_budget",
    "parse_duration",
    "parse_envs",
    "parse_params",
    "prophesied",
    "proved",
    "reading",
    "resumes",
    "run_fake",
    "run_flow",
    "running",
    "set_up",
    "told",
    "walking",
    "wanted",
    "within",
]

#: Which module each of them is written in. One entry per name this package offers, so that
#: `from hmz.runtime.flowing import find` costs the module `find` is in rather than all of
#: them: the `ast` of two readings and every coding agent driver there is are behind some of
#: these, and a menu of flows must pay for none of it.
_WRITTEN = {
    "AGENT_CAPABILITIES": "hmz.runtime.flowing.spi",
    "ALWAYS_DONE": "hmz.runtime.flowing.proving",
    "AgentDriver": "hmz.runtime.flowing.spi",
    "AgentRole": "hmz.runtime.flowing.declaring",
    "AgentSpec": "hmz.runtime.flowing.specs",
    "AgentSpecError": "hmz.runtime.flowing.specs",
    "AgentView": "hmz.runtime.flowing.viewing",
    "BUILTIN_AT": "hmz.runtime.flowing.finding",
    "BoundHook": "hmz.runtime.flowing.spi",
    "BudgetSpecError": "hmz.runtime.flowing.specs",
    "Call": "hmz.runtime.flowing.engine",
    "Capability": "hmz.runtime.flowing.checking",
    "Declaration": "hmz.runtime.flowing.declaring",
    "ENTRY": "hmz.runtime.flowing.finding",
    "ENV_CAPABILITIES": "hmz.runtime.flowing.spi",
    "Edge": "hmz.runtime.flowing.prophecy",
    "Entry": "hmz.runtime.flowing.driving",
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
    "Finding": "hmz.runtime.flowing.checking",
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
    "NEVER_DONE": "hmz.runtime.flowing.proving",
    "Node": "hmz.runtime.flowing.prophecy",
    "NotAFlow": "hmz.runtime.flowing.driving",
    "OFFICIAL": "hmz.runtime.flowing.verses",
    "Offer": "hmz.runtime.flowing.finding",
    "Outcome": "hmz.runtime.flowing.proving",
    "OutworlderDriver": "hmz.runtime.flowing.spi",
    "OutworlderView": "hmz.runtime.flowing.viewing",
    "PROPHECY": "hmz.runtime.flowing.finding",
    "ParamSpecError": "hmz.runtime.flowing.specs",
    "Place": "hmz.runtime.flowing.driving",
    "Placement": "hmz.runtime.flowing.spi",
    "Proof": "hmz.runtime.flowing.proving",
    "Prophecy": "hmz.runtime.flowing.prophecy",
    "Prophesied": "hmz.runtime.flowing.prophesying",
    "Recorder": "hmz.runtime.flowing.engine",
    "Remote": "hmz.runtime.flowing.loading",
    "Running": "hmz.runtime.flowing.driving",
    "SILENT": "hmz.runtime.flowing.proving",
    "Scenario": "hmz.runtime.flowing.proving",
    "SessionHandle": "hmz.runtime.flowing.spi",
    "SessionView": "hmz.runtime.flowing.viewing",
    "Shape": "hmz.runtime.flowing.prophecy",
    "Shipped": "hmz.runtime.flowing.prophecy",
    "Skill": "hmz.runtime.flowing.spi",
    "SpecError": "hmz.runtime.flowing.specs",
    "TurnRequest": "hmz.runtime.flowing.spi",
    "USER": "hmz.runtime.flowing.verses",
    "UsageSink": "hmz.runtime.flowing.spi",
    "about": "hmz.runtime.flowing.finding",
    "at": "hmz.runtime.flowing.finding",
    "briefed": "hmz.runtime.flowing.checking",
    "brought": "hmz.runtime.flowing.skills",
    "canonical": "hmz.runtime.flowing.prophecy",
    "capabilities_of": "hmz.runtime.flowing.spi",
    "carries": "hmz.runtime.flowing.driving",
    "catalogue": "hmz.runtime.flowing.checking",
    "checked": "hmz.runtime.flowing.checking",
    "configures": "hmz.runtime.flowing.driving",
    "container": "hmz.runtime.flowing.driving",
    "declared": "hmz.runtime.flowing.driving",
    "default_result": "hmz.runtime.flowing.spi",
    "define_flow": "hmz.runtime.flowing.engine",
    "digest": "hmz.runtime.flowing.prophecy",
    "drives": "hmz.runtime.flowing.driving",
    "entry": "hmz.runtime.flowing.finding",
    "find": "hmz.runtime.flowing.finding",
    "flowverses": "hmz.runtime.flowing.verses",
    "foretold": "hmz.runtime.flowing.finding",
    "fork": "hmz.runtime.flowing.finding",
    "found": "hmz.runtime.flowing.finding",
    "full_view": "hmz.runtime.flowing.engine",
    "held": "hmz.runtime.flowing.finding",
    "holds": "hmz.runtime.flowing.verses",
    "inside": "hmz.runtime.flowing.finding",
    "is_atlas": "hmz.runtime.flowing.prophesying",
    "kept": "hmz.runtime.flowing.prophecy",
    "load": "hmz.runtime.flowing.driving",
    "load_flow": "hmz.runtime.flowing.engine",
    "loaded": "hmz.runtime.flowing.finding",
    "local_env": "hmz.runtime.flowing.environments",
    "nearest": "hmz.runtime.flowing.verses",
    "new_outworlder": "hmz.runtime.flowing.engine",
    "offered": "hmz.runtime.flowing.finding",
    "offers": "hmz.runtime.flowing.finding",
    "open_agent": "hmz.runtime.flowing.harnesses",
    "open_env": "hmz.runtime.flowing.environments",
    "parse_agents": "hmz.runtime.flowing.specs",
    "parse_budget": "hmz.runtime.flowing.specs",
    "parse_duration": "hmz.runtime.flowing.specs",
    "parse_envs": "hmz.runtime.flowing.specs",
    "parse_params": "hmz.runtime.flowing.specs",
    "prophesied": "hmz.runtime.flowing.prophesying",
    "proved": "hmz.runtime.flowing.proving",
    "reading": "hmz.runtime.flowing.finding",
    "resumes": "hmz.runtime.flowing.driving",
    "run_fake": "hmz.runtime.flowing.fakes",
    "run_flow": "hmz.runtime.flowing.engine",
    "running": "hmz.runtime.flowing.driving",
    "set_up": "hmz.runtime.flowing.driving",
    "told": "hmz.runtime.flowing.prophecy",
    "walking": "hmz.runtime.flowing.stepping",
    "wanted": "hmz.runtime.flowing.driving",
    "within": "hmz.runtime.flowing.finding",
}

#: The one name this package offers under something other than its own. `shipped` is what a
#: flow's directory ships a compiled prophecy as; `shipped` is also what a session carries of
#: the skills a flow brought. Two of one word in one namespace is a reader having to be told
#: which is meant, so the prophecy's is offered here as `foreshipped` and is `shipped` in the
#: module it is written in, where there is only ever one of it.
_AS = {"foreshipped": "shipped"}


def __getattr__(name: str) -> object:
    """Hands through what this package offers, out of the module it is written in.

    Args:
      name: What was asked for.

    Returns:
      The same object that module holds, so that there is one of each however it was reached.

    Raises:
      AttributeError: If nothing here is called that, as for any other module. It is also
        what sends Python looking for a module of that name beside this one, which is how
        `from hmz.runtime.flowing import checking` goes on being the reading rather than this.
    """
    from importlib import import_module

    where_ = _WRITTEN.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), _AS.get(name, name))
