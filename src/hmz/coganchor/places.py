"""The words for where an agent's turns land and how its commands are reached there.

One half of the capability vocabulary, kept here rather than beside the other half in
:mod:`hmz.runtime.flowing.checking` -- and the reason is the layering. A capability name is
two things at once: a fact somebody declares, and an ask a flow writes. The ask belongs above,
where flows are read and refused; the fact belongs wherever the thing it is about is written
down,
and every one of these is about a machine or about the road to one. `remote`, `isolated`,
`managed` and the platforms are what :attr:`~hmz.coganchor.machines.MachineConfig.capabilities`
answers with; `anchor:native-cli` and `anchor:supervised` are what
:attr:`~hmz.coganchor.anchor.AnchorConfig.capabilities` answers with. Each of those was
spelling its own words out, and the catalogue above was spelling them out a second time to
describe them -- one word in two places, right in whichever was read last.

So the words live here, where every one of their producers can reach them and where nothing
has to reach up into `hmz.runtime.flowing` to say what it serves. What stays above is the
prose: what the ask looks like, what a flow writes beside a place to reach for one, which is
a question about flows and no business of a layer that drives agents.

`anchor:hooked` and `anchor:preloaded` are here for the company they keep and not because a
machine ever declares them. They are the two roads humanize reaches a turn down from *inside*
the process it started, so they are facts about the CLI --
:meth:`hmz.coganchor.backends.Profile.tags` is what answers with them -- and they are asked of
the agent rather than of where it works.
:data:`INSIDE` is what says so, and what takes them away again from an agent whose turns land
on another machine. They are spelled out there rather than imported from here, because
`backends.py` may name nothing but the standard library; `tests/unit/backends/test_catalogue.py`
is what holds the two spellings together.
"""

from __future__ import annotations

from .proto import PLATFORMS

__all__ = [
    "HOOKED",
    "INSIDE",
    "ISOLATED",
    "MANAGED",
    "NATIVE_CLI",
    "PLACES",
    "PRELOADED",
    "REMOTE",
    "ROADS",
    "SUPERVISED",
]

#: An agent whose turns land on another machine. Said by every machine there is, a machine
#: being the thing an agent is pointed at: an agent pointed at none works here.
REMOTE = "remote"

#: An agent working in a container of its own, where the tools and the libraries a command
#: finds are the image's rather than this machine's.
ISOLATED = "isolated"

#: A machine brought up for the agent and taken down after it, as against one that was
#: already running -- which is never stopped here, a machine nobody here started being
#: nobody here's to end.
MANAGED = "managed"

#: Where an agent's turns may land, which is the whole of what a place may be asked to come
#: to. The platforms are the wire's own list rather than a second copy of it: which platforms
#: humanize has a word for is settled by what a target can say at the handshake, and a name
#: here that `hello` could never answer with would be one a machine is refused for lacking.
PLACES = frozenset({REMOTE, ISOLATED, MANAGED}) | PLATFORMS

#: An anchored turn taken as the CLI already installed on the target, read off its own three
#: streams, with nothing traced and nothing mirrored.
NATIVE_CLI = "anchor:native-cli"

#: An anchored turn whose commands are reached by tracing the process it runs them in, which
#: is how the work of a turn taken here lands on the machine the flow chose.
SUPERVISED = "anchor:supervised"

#: The two roads a *machine* declares, being the two ways an anchor reaches one. Asked for
#: under `where=`, where the machine that was pointed down one is what answers -- and so
#: answered by no place at all where an agent was pointed nowhere.
#:
#: Which is not a gap. A turn on this machine is a CLI humanize spawned here and traced here,
#: so both roads are travelled; but a road is how an anchor reaches a *machine*, there is no
#: machine, and nothing declares it. That is the same answer `remote` gives a local place and
#: for the same reason: what a place comes to is read off the settings of where its work
#: lands, and work that lands here lands under no settings. A flow asking for one of these is
#: asking about somewhere else, which is the only place the question has two answers.
ROADS = (NATIVE_CLI, SUPERVISED)

#: A turn reached through the CLI's own hooks, written for this run and read by no other.
HOOKED = "anchor:hooked"

#: A turn reached from inside the process, by what its runtime is told to load before it
#: starts.
PRELOADED = "anchor:preloaded"

#: The roads humanize can only take where the turn runs on this machine, and so the two
#: `anchor:` names that are asked of the *agent* rather than of where it works. Each of them
#: is humanize putting something inside the process it started -- a hook table written for one
#: run, a variable the runtime reads before it starts -- and a turn whose process is somewhere
#: else is a process none of that reached. The drivers each switch themselves off under an
#: anchor for exactly that reason, so a place that asked for one is refused where its agent is
#: filled rather than quietly given the weaker thing: a flow that believes it is gating tools
#: and is only watching them is the failure asking beforehand exists to prevent.
INSIDE = frozenset({HOOKED, PRELOADED})
