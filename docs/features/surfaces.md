---
pageClass: hmz-feature
---

# One system, four ways in

humanize has a Python SDK, a command line, a terminal interface and a daemon, and none of them
is a second orchestration engine. They reach the same workspace stores, flow loader and runner.
What changes is how the question is asked and how long the caller stays attached.

The route starts before a run does: find the nearest flow, fork it when it should become yours,
let what it declares — its roles, its environments, its params model — describe its setup, then
enter through whichever surface fits the job.

<HmzSurfaces />

## A flow starts near you

A flowverse is one place flows come from: a Git repository whose flows directory is the only
part offered to humanize. `chat` is read from the package instead, and the project flow
directory and the one in your home are places too — called local and user, even though nothing
fetches either of them.

That gives a name two different orders:

| | |
| --- | --- |
| **The catalogue** | humanize's own flows, then added flowverses, and finally the local places, wherever either has something to show |
| **An unqualified name** | this project first, then your home, then everywhere else — what is nearest wins |
| **A qualified name** | its flowverse outright, bypassing that precedence |

Which is why the catalogue can show the original and a local variant beside each other while an
unqualified name quietly picks the one meant for this project.

Discovery is also a trust boundary. Listing files is cheap, but finding the flows a module
defines and the lines they say about themselves means loading their entry points — so trust a flowverse the
way you trust a package that will run on this machine. Only the flows directory is considered,
and what is in it is still Python.

## Forking changes ownership, not ancestry

Forking copies a flow into this project's local flow directory. A directory flow arrives whole
— its entry point, the modules it imports beside itself and every skill it brings — and a
single-file flow remains a single file. The fetched source stays untouched, so refreshing its
flowverse later cannot erase the local edits.

The copy is staged beside its destination and then moved into place: if copying fails, no
half-flow is left under the name, and if a local file or directory already owns that name,
forking refuses to write over it. Once the copy lands, the unqualified name means the local
copy, while the qualified source name still reaches the original.

This is a source decision, not a runtime capability switch. Forking does not add a goal feature
to a backend, make an unsupported hook available or change where an agent can work; the flow's
declared requirements are checked separately against the agents chosen for the run.

## The declaration is the setup surface

What a run needs is what the flow declares: a role per agent, each asking for a CLI, an account,
a model and an effort; a role per environment the runtime does not fill itself, each asking for a
machine and a directory; its params; and a budget. The roles are named, so each is asked about by
the name the flow calls it.

A flow that takes params declares them as a `FlowParams` subclass — a pydantic model. That model
is the complete vocabulary of the params: field names, annotations, defaults, descriptions,
bounds and validators. Optional section metadata lets a large model group related fields without
teaching the terminal interface what any of them mean.

The interface reads those declarations directly, and the description appears beside the field.

| In the model | In the interface |
| --- | --- |
| a boolean | a switch |
| a fixed set of literal values | a list to step through |
| a number | moves one at a time, or accepts what is typed |
| anything else | written |

When the reader accepts the sheet, the model validates the whole set, including relationships
between fields, and returns its own refusal when the combination cannot run.

The command line and Python do not get a weaker contract: `-p key=value` and values handed to
the SDK go through the same model, each read as the field's type or as JSON. The earlier model
class is not trusted as the current one — what was remembered is read back through the class the
flow declares now. A remembered setup that no longer fits starts over, and a bad setup presented
to a run is refused before any agent starts.

## Shared core does not mean identical interfaces

The runtime's workspace object — `Hmz`, which the SDK hands out under its own name — is the
composition point. It reaches the same settings, flows, agents, accounts and epics that the
other surfaces show, and loads each only when it is asked for. Adding a flowverse through one
surface and seeing it in another is not a sync operation — both are reading the same store.

| | | |
| --- | --- | --- |
| **Python** | composable | Holds the Run — a loaded runner plus its task — with one lifecycle for running here, starting in the background, waiting, stopping and closing the agent conversations. It is offered both ways: straight at the runtime, or held apart from any terminal by a daemon |
| **The command line** | scriptable | The same Run, on the blocking path, reaching the runtime by name |
| **The terminal interface** | conversational | Keeps that workspace object and runner in hand — reached through the daemon holding its run — so it can configure the flow, watch several conversations, accept questions and steer a turn while the run is live |
| **The daemon** | continuity | Opens no flow itself: it is handed something that opens one. It holds that same interface in a detached process, carries its screen through a pseudoterminal, and answers what is running there out of the runtime |

What the interface sees of being held is the Session boundary — how many terminals are reading,
and how to detach them without stopping the run — which keeps the pseudoterminal and the socket
out of it while a closed terminal leaves the work going on the same host.

So unified means common state, validation and runtime semantics where the surfaces overlap,
rather than feature parity. Each stays small because none has to redefine what a flow, setup,
run or session means.

## Where the detail is

- [Flowverses and forking](/weaver/flowverses) · [Params of its own](/weaver/flow-settings)
- [Python SDK](/reference/sdk) · [CLI](/reference/cli) · [TUI](/reference/tui) ·
  [Daemon](/reference/daemon)
