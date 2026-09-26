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
"""

from __future__ import annotations

__all__ = [
    "AFAR",
    "ISOLATED",
    "MANAGED",
    "NATIVE_CLI",
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

#: The roads a *machine* declares, being the ways an anchor reaches one. The machine that was
#: pointed down one is what answers -- and so no place at all answers where an agent was
#: pointed nowhere.
#:
#: Which is not a gap. A turn on this machine is a CLI humanize spawned here and traced here,
#: so both roads are travelled; but a road is how an anchor reaches a *machine*, there is no
#: machine, and nothing declares it. That is the same answer `remote` gives a local place and
#: for the same reason: what a place comes to is read off the settings of where its work
#: lands, and work that lands here lands under no settings. A flow asking for one of these is
#: asking about somewhere else, which is the only place the question has two answers.
ROADS = (NATIVE_CLI, SUPERVISED, AFAR)
