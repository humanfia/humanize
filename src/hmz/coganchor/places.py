"""The words for where an agent's turns land and how its commands are reached there.

The machine half of coganchor's capability vocabulary, and the reason it is here is the
layering: a capability name is a fact somebody declares, and the fact belongs wherever the
thing it is about is written down -- every one of these is about a machine or about the road
to one. `remote`, `isolated`, `managed` and the platforms are what
:attr:`~hmz.coganchor.machines.MachineConfig.capabilities` answers with; `anchor:native-cli`
and `anchor:supervised` are what :attr:`~hmz.coganchor.anchor.AnchorConfig.capabilities`
answers with. Each of those spelling its own words out would be one word in several places,
right in whichever was read last.

So the words live here, where every one of their producers can reach them and where nothing
has to reach up into `hmz.runtime` to say what it serves.

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
    "AFAR",
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

#: An anchored turn whose harness -- the agent process and the supervisor tracing it -- runs
#: on a machine that is not this one. The third arrangement anchoring has, and the one that
#: says a turn costs this machine nothing per file the agent opens: under
#: :data:`SUPERVISED` alone the harness is here and every path the agent names is a round
#: trip, while a harness put beside its work reads that machine's disk at that machine's
#: speed. Said by an anchor rather than by a machine, like the two above it, because where
#: the harness runs is a fact about how the turn is reached and not about where it lands --
#: and a flow that must not send the agent's own process elsewhere is one that has to be able
#: to ask.
AFAR = "anchor:afar"

#: The roads a *machine* declares, being the ways an anchor reaches one. Asked for
#: under `where=`, where the machine that was pointed down one is what answers -- and so
#: answered by no place at all where an agent was pointed nowhere.
#:
#: Which is not a gap. A turn on this machine is a CLI humanize spawned here and traced here,
#: so both roads are travelled; but a road is how an anchor reaches a *machine*, there is no
#: machine, and nothing declares it. That is the same answer `remote` gives a local place and
#: for the same reason: what a place comes to is read off the settings of where its work
#: lands, and work that lands here lands under no settings. A flow asking for one of these is
#: asking about somewhere else, which is the only place the question has two answers.
ROADS = (NATIVE_CLI, SUPERVISED, AFAR)

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
