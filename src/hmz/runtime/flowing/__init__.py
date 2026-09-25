"""Everything humanize does to a flow: finding one, reading one, driving one, compiling one.

A flow is content -- somebody else's repository, forked and edited -- and the whole of what it
imports is :mod:`hmz._legacy_flows`: the interfaces it drives, the mark that makes it a flow,
and the
vocabulary a turn is described in. This is the other side of that line. Where flows come from
and what each is called is [verses.py](verses.py) and [finding.py](finding.py); what a flow
says it drives, and what it takes for one flow to run another, is [driving.py](driving.py);
the two readings of a flow that refuse one before it can cost anything are
[checking.py](checking.py) and [proving.py](proving.py); an atlas is compiled by
[prophesying.py](prophesying.py) into the graph [prophecy.py](prophecy.py) describes, and a
run of one is walked by [stepping.py](stepping.py); the skills a flow named that live
somewhere else are fetched by [skills.py](skills.py).

The arrow points one way. Everything here may name :mod:`hmz._legacy_flows`, and nothing in
:mod:`hmz._legacy_flows` names anything here at the top of its file -- what a flow legitimately
needs
from this layer, which is `load` and the little that goes with it, is handed through from
there when the flow asks for it. So a module that moves here moves without a flow anywhere
noticing, which is the point of the line being where it is.

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

__all__ = [
    "ALWAYS_DONE",
    "BUILTIN_AT",
    "ENTRY",
    "FLOWS",
    "LOCAL",
    "MINE",
    "NEVER_DONE",
    "OFFICIAL",
    "PROPHECY",
    "SILENT",
    "USER",
    "Capability",
    "Edge",
    "Entry",
    "Finding",
    "Flowverse",
    "Node",
    "NotAFlow",
    "Offer",
    "Outcome",
    "Place",
    "Proof",
    "Prophecy",
    "Prophesied",
    "Running",
    "Scenario",
    "Shape",
    "Shipped",
    "about",
    "at",
    "briefed",
    "brought",
    "canonical",
    "carries",
    "catalogue",
    "checked",
    "configures",
    "container",
    "declared",
    "digest",
    "drives",
    "entry",
    "find",
    "flowverses",
    "foreshipped",
    "foretold",
    "fork",
    "found",
    "held",
    "holds",
    "inside",
    "is_atlas",
    "kept",
    "load",
    "loaded",
    "nearest",
    "offered",
    "offers",
    "prophesied",
    "proved",
    "reading",
    "resumes",
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
    "ALWAYS_DONE": "hmz.runtime.flowing.proving",
    "BUILTIN_AT": "hmz.runtime.flowing.finding",
    "Capability": "hmz.runtime.flowing.checking",
    "ENTRY": "hmz.runtime.flowing.finding",
    "Edge": "hmz.runtime.flowing.prophecy",
    "Entry": "hmz.runtime.flowing.driving",
    "FLOWS": "hmz.runtime.flowing.verses",
    "Finding": "hmz.runtime.flowing.checking",
    "Flowverse": "hmz.runtime.flowing.verses",
    "LOCAL": "hmz.runtime.flowing.verses",
    "MINE": "hmz.runtime.flowing.verses",
    "NEVER_DONE": "hmz.runtime.flowing.proving",
    "Node": "hmz.runtime.flowing.prophecy",
    "NotAFlow": "hmz.runtime.flowing.driving",
    "OFFICIAL": "hmz.runtime.flowing.verses",
    "Offer": "hmz.runtime.flowing.finding",
    "Outcome": "hmz.runtime.flowing.proving",
    "PROPHECY": "hmz.runtime.flowing.finding",
    "Place": "hmz.runtime.flowing.driving",
    "Proof": "hmz.runtime.flowing.proving",
    "Prophecy": "hmz.runtime.flowing.prophecy",
    "Prophesied": "hmz.runtime.flowing.prophesying",
    "Running": "hmz.runtime.flowing.driving",
    "SILENT": "hmz.runtime.flowing.proving",
    "Scenario": "hmz.runtime.flowing.proving",
    "Shape": "hmz.runtime.flowing.prophecy",
    "Shipped": "hmz.runtime.flowing.prophecy",
    "USER": "hmz.runtime.flowing.verses",
    "about": "hmz.runtime.flowing.finding",
    "at": "hmz.runtime.flowing.finding",
    "briefed": "hmz.runtime.flowing.checking",
    "brought": "hmz.runtime.flowing.skills",
    "canonical": "hmz.runtime.flowing.prophecy",
    "carries": "hmz.runtime.flowing.driving",
    "catalogue": "hmz.runtime.flowing.checking",
    "checked": "hmz.runtime.flowing.checking",
    "configures": "hmz.runtime.flowing.driving",
    "container": "hmz.runtime.flowing.driving",
    "declared": "hmz.runtime.flowing.driving",
    "digest": "hmz.runtime.flowing.prophecy",
    "drives": "hmz.runtime.flowing.driving",
    "entry": "hmz.runtime.flowing.finding",
    "find": "hmz.runtime.flowing.finding",
    "flowverses": "hmz.runtime.flowing.verses",
    "fork": "hmz.runtime.flowing.finding",
    "found": "hmz.runtime.flowing.finding",
    "foretold": "hmz.runtime.flowing.finding",
    "held": "hmz.runtime.flowing.finding",
    "holds": "hmz.runtime.flowing.verses",
    "inside": "hmz.runtime.flowing.finding",
    "is_atlas": "hmz.runtime.flowing.prophesying",
    "kept": "hmz.runtime.flowing.prophecy",
    "load": "hmz.runtime.flowing.driving",
    "loaded": "hmz.runtime.flowing.finding",
    "nearest": "hmz.runtime.flowing.verses",
    "offered": "hmz.runtime.flowing.finding",
    "offers": "hmz.runtime.flowing.finding",
    "prophesied": "hmz.runtime.flowing.prophesying",
    "proved": "hmz.runtime.flowing.proving",
    "reading": "hmz.runtime.flowing.finding",
    "resumes": "hmz.runtime.flowing.driving",
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
