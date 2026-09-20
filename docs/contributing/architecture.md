# Architecture

How the package is laid out, what each layer is for, and the rules that keep it that way. For
contributors; nothing here is needed to *use* humanize.

## The tree

```
src/hmz/
├── __init__.py       home() — where humanize keeps what outlives one run
├── __main__.py       python -m hmz
├── coganchor/        everything humanize knows about driving a coding agent CLI
├── flows/            the whole of what a flow imports, and nothing else
├── runtime/          what a run is: driving one, writing it down, reading it back —
│                     flowing/, which is everything humanize does to a flow, and
│                     doing/, which is the whole of that as one object
├── daemon/           a run held where a terminal closing cannot end it
├── sdk/              how a tool that is not humanize reaches humanize
├── tui/              the terminal interface
└── cli/              the command line: one module per command that has a parser, and
                      output.py, which answers whether a person or a program is reading
```

Nothing sits at the top but `__init__.py` and `__main__.py`. A module belongs inside the
directory whose question it answers, because a top level that is a list of files is one where
nothing says which of them go together.

`coganchor/` is the whole of the agent-CLI capability, so that everything above it schedules
flows and drives nothing itself. Every name says what it holds, except that one — it is named
for the anchor inside it, a program that ships to a target and could be lifted out whole.

## The layers

| Layer | Is | Entry points |
| --- | --- | --- |
| `coganchor/backends.py` | Names, aliases, efforts, home directories, log globs, credential paths, ways in and skill directories for all twelve backends. Facts, not code — standard library only, and no model id anywhere in it. | `PROFILES`, `named()`, `profiles()`, `read()`, `remember()` |
| `coganchor/providers/` | Which account an agent runs as, kept apart from which CLI it is: what one is, where its state lives, and the interception a turn is run under. | `Provider`, `add`, `remove`, `find`, `providers`, `chain`, `points`, `ready`, `filled`, `alone`, `copies`, `serves`, `ways`, `where`, `environ`, `env_of`, `ENV`, `LOCAL` |
| `coganchor/models.py` | What each backend runs, asked of that backend the way it offers being asked, and kept per account. Nothing here is a list: a CLI ships models without asking anybody. | `ask`, `offered`, `asked`, `where` |
| `coganchor/agents/` | The drivers: one per backend, plus the vocabulary a turn is described in (`Event`, `Question`, `Moment`). `AgentBase` and `SessionBase` answer to the interface `flows/` declares, structurally — this layer never names a flow. | everything in `__init__` |
| `coganchor/machines/` | The setting that says which machine, and the machine it brings up. | `MachineConfig`, `MachineBase`, `AnchoredConfig`, `DockerConfig` |
| `coganchor/` (the anchor in it) | Syscall interposition: a seccomp-filtered ptrace supervisor here, a replaying server there, a wire protocol between. The half that ships to a target — and the only half that does. Where the supervisor itself runs is `elsewhere.py`, and the introduction two machines that cannot dial each other need is `rendezvous.py`; both ship to a target too, since under those arrangements the target is the one running them. | `AnchorConfig`, `connect`, `check` |
| `flows/` | The whole of what a flow imports and nothing besides: the interfaces it drives, the mark, the marks an atlas is written with, and the vocabulary a turn is described in handed through from the layer it is written in. `builtin/` beside it is the one flow humanize keeps in the package. | `Agent`, `Session`, `Person`, `flow`, `atlas`, `mind`, `logic`, `sub`, `load` |
| `runtime/flowing/` | Everything humanize does to a flow, and none of it a thing a flow names: where flows come from, finding one by name, running its file to read it, what it says it drives, the two readings that refuse one before it can cost anything, compiling an atlas and walking the prophecy, and fetching the skills it named. | `found`, `find`, `held`, `fork`, `flowverses`, `drives`, `wanted`, `load`, `checked`, `proved`, `prophesied`, `walking`, `brought` |
| `coganchor/fallbacks.py` | The layer between an agent and its accounts: where a turn goes when the place taking it cannot take it at all, and how many times over it is taken again first. A step is written between two places — `CLI[@ACCOUNT]/MODEL` — rather than on the account, which `providers` already answers for. Names `backends` and nothing else. | `Falls`, `falls`, `points`, `retrying`, `tried`, `clear`, `chain`, `spec`, `reads`, `waits`, `POLICIES` |
| `runtime/epic.py` | One run of one flow as a directory: the journal, the links to each session's log, and what a flow that can be picked up left behind. Written by `runner`, read by `tracing`, `cli` and `tui`. | `Epic`, `epics`, `read`, `opened`, `state`, `resumed` |
| `runtime/runner.py` | Handing a flow the agents it declared, naming them, and running it under an epic. Also reads the `hmz exec` line, which the interface starts a flow from too. What the flow says it drives is `flows/`'s to answer. | `Runner`, `flow_and_agents`, `read_agent`, `set_up_from` |
| `runtime/tracing/` | Reading the backends' logs back — and, for a profiled run, sampling the programs its agents start — and rendering both as one Chrome trace. | `collect`, `profile.Profiler` |
| `runtime/doing/` | humanize as one object, and the front door `hmz.runtime` hands through. A workspace, what is remembered about it, the flows there are, the agents and accounts they run as, the runs already made and the run being made now. It composes the layers and restates none of them, and it reaches each of them from inside the call that needs it — which is what lets a caller name it without paying for the tracer. | `Hmz`, `Run` |
| `tui/` | The terminal interface. It reaches the runtime through the daemon holding the run it is drawing. | `Humanize` |
| `daemon/` | A run held where a terminal closing cannot end it, and the terminals that come and go from it. How a run is opened is still none of its business — it is handed a callable — but it is the process a run happens in, so it is where the runtime is reached from and what is running there is a question it answers itself. | `Daemon`, `Held`, `Session`, `Hmz`, `running`, `daemons`, `start` |
| `sdk/` | How a tool that is not humanize reaches humanize: the runtime straight at it, and a run held apart from a terminal reached over its socket. It composes nothing and is named by no layer. | `Hmz`, `Daemons`, `Run`, `Session` |
| `cli/` | The one command line, over layers that have none of their own. | `main`, `COMMANDS` |

### Inside the bigger ones

```
coganchor/
├── backends.py   every fact about a coding agent CLI that is not code
├── models.py     what each backend runs, asked of it and kept per account
├── fallbacks.py  where a turn goes when the place taking it cannot take it at all
├── prices.py     what a token costs, off a list somebody else keeps
├── agents/       event.py hooks.py config.py base.py, and one driver per backend
├── providers/    which account an agent runs as, and the interception it runs under
├── machines/     where an agent's turns land
├── anchor.py argv.py proto.py transport.py remote.py supervisor.py handlers.py
│   policy.py shadow.py standin.py execproxy.py netproxy.py statepaths.py
│   elsewhere.py  where the harness runs, for the two arrangements it is not here
│   rendezvous.py the meeting two halves on two machines are introduced at
├── linux/        ptrace, seccomp, procfs, syscall numbers (x86-64, aarch64)
└── serve/        the target half — imports nothing but proto

runtime/
├── runner.py     finding a flow, checking it, driving it, reading the `hmz exec` line
├── epic.py       what one run of one flow was, written down as it happens
├── exporting.py  one whole run packaged up to send somewhere
├── settings.py   what each workspace was set up to run
├── kept.py       what an agent is, written down: a shape and the two ways it goes
├── telemetry.py  what humanize reports about itself, and whether it does at all
├── doing/        core.py, and one module per store: the whole of the above as one
│                 object, which is what `from hmz.runtime import Hmz` hands back
└── tracing/      collector.py session.py chrome.py profile.py, and readers/ per format

flows/
├── agent.py      Agent, Session, Person — what a flow drives, as interfaces and nothing else
├── atlas.py      atlas, mind, logic, sub — the marks an atlas declares its graph with
├── __init__.py   the mark, and the one import a flow writes
└── builtin/      chat, the one flow humanize keeps in the package

runtime/flowing/
├── checking.py     the reading that runs nothing, over every file the flow holds
├── driving.py      what a flow says it drives, read off its own entry point, and load()
├── finding.py      a flow by name, and what running its file leaves behind
├── prophecy.py     what an atlas compiles to, and the file a flowverse ships it in
├── prophesying.py  the compiling: a body held to the narrower Python and read into a graph
├── proving.py      the second reading: the flow driven by stubs against a clock
├── skills.py       the skills a flow brings, its own and the ones it named
├── stepping.py     walking a prophecy, and picking a stopped run up where it left off
└── verses.py       where flows come from when they come from somewhere else
```

The line between those two is the point of them. A flow is somebody else's repository, so
`flows/` is held to what a flow actually writes — the interfaces, the marks, the vocabulary a
turn is described in — and everything humanize does *to* a flow lives in `runtime/flowing/`,
where it can be renamed, split or rewritten without a flow anywhere noticing.

## The dependency graph

```
                coganchor   ← everything about driving a coding agent CLI
                  ↑    ↓
                  │  telemetry → settings → kept
                  │
    flows ────────┤   ← the whole of what a flow imports
      ↑           │
    flowing ──────┤   ← and everything humanize does to one
      ↑           │
    runner ── epic ── tracing ── exporting
      ↑
    doing   ← the whole of the runtime as one object: hmz.runtime.Hmz
      ↑
    daemon  ← a run held where a terminal closing cannot end it
      ↑
     tui
      ↑
     cli   ← may name anything; it is what joins them

    sdk → doing, daemon   ← the way in from outside. Nothing below names it.
```

<HmzStack />

It is a DAG with one exception, and the exception is checked rather than trusted. `flowing`
names `flows`, because reading a flow means reading the mark and the interfaces it declared its
agents with; `flows` names `flowing` back for one thing only — `load`, which is a flow running
another flow, and so a run — and it names it for a type checker and never at import. Writing
`@flow` therefore costs nothing of the runtime, and `hmz exec` reading a line that names no
flow costs nothing of it either. Everything else points one way. The diagram above is the same
table drawn: hover a layer and it lights up exactly what that layer is allowed to name.

The column in the middle is the one thing worth reading twice. `cli` names the runtime by its
own name; `tui` names it through the `daemon` holding the run it is drawing, because a run of a
workspace lives in a process of its own and the interface is what draws inside that process —
so what holds the run is what the interface asks, and asking it is a name rather than a message
on the socket. The socket carries the terminals outside; the interface is already in here.

`sdk` sits off to the side because it is not a layer humanize is built out of. It is how a tool
that is not humanize reaches humanize — the runtime straight at it, a held run over its
socket — and it composes nothing, restates nothing, and is named by nothing below it. It used
to be both that and the seam every way in had to pass through, which are two different jobs: a
rule about how humanize is built wins every argument with a promise made to somebody else, so
the promise was the one going unkept.

Four edges are worth explaining:

- **`coganchor → telemetry`**, which is the one thing the bottom layer names. A skill a flow
  brought that a session will not read is noticed there and nowhere else, and the reporter
  names nothing above itself — so this widens the graph without bending it. It is also why
  `runtime/` is drawn open rather than closed: had `telemetry` been inside one box with
  `runner`, that box and `coganchor` would point both ways.
- **`epic → tracing`**, because a profiled run samples the programs its agents start. `tracing`
  itself knows how to *drive* nothing; it needs the home directories and log globs, and
  nothing else.
- **`cli` reaches `coganchor` directly**, for `hmz internal anchor`. That command is the only
  line the target half is ever started by, and it must cost nothing else of humanize on the
  way.
- **`daemon → doing`**, which is the one edge out of what used to be a leaf. A daemon still
  knows nothing about how a run is *opened* — it is handed a callable, which is what makes the
  interface under one identical to the interface under none — but it is the process the run
  happens in, so what is running there is a question it answers out of the runtime rather than
  one it is handed the answer to by whatever it is holding.

And one edge deliberately absent: **`coganchor` does not name `epic`.** A run is written out
of the agents it drove, so naming the run from an agent would be a circle. What an agent needs
of one — somewhere to write down a session it opened — is a `Journal` protocol declared in
`coganchor/agents/base.py`, which `Epic` happens to satisfy.

Inside `coganchor` the arrows are no longer in the table, because it is one layer: the drivers
name the facts, the accounts and the machines freely, exactly as the insides of `flows/` and
`tui/` do. The one line held inside it is `coganchor/serve/`, which may name the wire and
nothing else — see below.

## Rules that are checked

`tests/integration/layering/test_layering.py` holds the table and five tests. It is the
only place these can be checked at all.

1. **Every layer imports only what it may.** The table lists what each may name besides its own
   subtree and `hmz` itself. A package a submodule was taken out of does not count as named —
   `from hmz.runtime import telemetry` names the reporter, not everything beside it — or one
   entry would silently say a whole directory the import never touched. Relative spellings are
   resolved, so
   `from ..supervisor import Supervisor` counts exactly as the absolute form would.
2. **No two layers name each other.** A pair that points both ways is two things put in one
   place, not one above another.
3. **Every top-level module is in the table.** One left out is unchecked, and reads exactly like
   one deliberately exempt. `cli` is the only exemption, and it is checked differently:
4. **Serving loads only what it may** — against a real target half, not statically. The bundle
   is built, `hmz internal anchor serve` is run out of it with an empty `PYTHONPATH`, and what
   it loaded is compared with the table.

That last one is why `coganchor/serve/` may import nothing but `proto` — not even the package it sits in, whose name would be leave to name every driver in it. It is also why the bundle carries the anchor half alone: `DRIVING` in `coganchor/transport.py` names what a target has no use for, and `test_the_bundle_carries_nothing_that_drives_an_agent` is what notices a new one. The serving half runs on
the target, which may be any architecture, while `coganchor/linux/` picks a register map at
import time and refuses any architecture it has not got one for — which is x86-64 and aarch64,
and nothing else.

The same discipline is why **every command imports what it needs when it is the one asked for,
and no earlier** — `hmz exec` must not pay for a date parser it will not use. Ruff's
`PLC0415` is off for exactly this reason.

## Two design decisions worth knowing

**An agent and its session are two halves of one object, declared in one file.** They are
mutually recursive by nature — a session registers itself with its agent, and an agent's turns
run through its sessions — so splitting them would create a two-way dependency and spread the
`SLF001` exemption across two files. `agents/base.py` is long on purpose.

**The setting and the machine are two classes.** `MachineConfig.create()` builds a
`MachineBase`. One config drives as many agents as it is given to, and each gets a machine of
its own — two agents sharing a `DockerConfig` get a container each, which is what you want and
what a single class could not express.

## Naming

Module names come from the product's own vocabulary — the same words `hmz` and this site use.
[Agents](/reference/agents) documents `coganchor/agents/`, [Tracing](/reference/tracing)
documents `runtime/tracing/`, and so on.

A name of its own is for something that could be its own repository: its own SPEC, its own wire
protocol, its own architecture requirement, shippable on its own. Exactly one thing qualifies,
and it is `coganchor` — an abbreviation, and an easter egg.

## SPECs

Under `specs/`, and normative. Where this documentation says what humanize *does*, a SPEC says
what it *must* do, in MUST/MUST NOT terms, for whoever is changing it.

The tree under `specs/` mirrors the tree under `src/hmz/`: a package with a contract of its
own has a file named for it at the path it is written at, so `specs/coganchor/agents.md` is
the contract for `coganchor/agents/`, and a package with subpackages of its own has a
directory with a `SPEC.md` in it. A package no file is named for is bound by the nearest one
above it that has a file, and `specs/SPEC.md` is the one for the tree itself.
Together rather than beside the code, because a contract is read as a set — what one package may
demand of another is a question about several of them at once — and because a file under `src/`
is a file the wheel ships: a SPEC is for whoever changes humanize, not for whoever installs it.

| | |
| --- | --- |
| `specs/SPEC.md` | The tree, what each layer is, and how they may name one another |
| `specs/cli.md` | Every command line |
| `specs/coganchor/SPEC.md` | Driving a coding agent CLI, and what an anchor entitles you to |
| `specs/coganchor/agents.md` | The agent and session contract every backend keeps |
| `specs/coganchor/linux.md` | What the anchor intercepts on the target |
| `specs/coganchor/machines.md` | What a machine is |
| `specs/coganchor/providers.md` | Which account an agent runs as, and how a turn is run under it |
| `specs/coganchor/serve.md` | The half that ships to a target |
| `specs/flows.md` | The whole of what a flow imports: what it drives, the mark, the atlas marks |
| `specs/runtime/SPEC.md` | What a run is, and what humanize remembers of one |
| `specs/runtime/doing.md` | humanize as one object: a workspace and everything doable in it |
| `specs/runtime/flowing.md` | What humanize does to a flow: finding, reading, checking, driving, compiling |
| `specs/runtime/tracing.md` | The collect API and what a trace must hold |
| `specs/daemon.md` | Holding a run apart from a terminal, and the terminals that read one |
| `specs/sdk.md` | How a tool that is not humanize reaches humanize |
| `specs/tui.md` | Every behaviour the interface must have |

`AGENTS.md` says not to modify a SPEC unless you were told to. Change the code to match the
SPEC; propose the SPEC change separately.

## Adding things

**A backend.** A `Profile` in `coganchor/backends.py`, a driver in `coganchor/agents/`, an
entry in the `DRIVEN` table in `coganchor/agents/__init__.py`, which `runtime/runner.py` and
the interface both read, a way of asking it what it runs in `coganchor/models.py`'s `_READING`
table, and its state paths in `coganchor/statepaths.py`. Subclass `CommandSessionBase` if a turn is one run of a command
line, or `StreamSessionBase` if it is one long-lived process spoken to a line at a time —
`specs/coganchor/agents.md` says which and why.

Then whatever its logs allow, and nothing more: a reader in `runtime/tracing/readers/` where a session
of it can be gathered afterwards, and a branch in `tui/tally.py`'s `_spent` where a row of them
says what one request cost, which is what a tally moving during a turn is read out of. A
backend that writes neither gets neither, and says so rather than being left out.

Its usage goes under the names in `coganchor/agents/event.py`'s `KINDS` and no others — the
prices are per kind, so a driver writing its CLI's own spelling down reports a lump nothing can
price — and which of them it reports is declared on the agent class as `counts`, read off the
same table the driver parses with rather than written down twice. A backend that reports
nothing declares nothing; what draws a run then marks its figures as floors rather than leaving
that backend out of them.

And the documentation. Several pages count the backends and several tables name every one of
them, so one added without them is a site that says there are fewer than there are.

**A machine.** Two classes in `coganchor/machines/`, per [Machines](/reference/machines#writing-a-machine-of-your-own).

**A command.** A module under `cli/` if it takes a parser of its own, a thin wrapper in
`cli/__init__.py`, and an entry in `COMMANDS` — or in `INTERNAL`, which is what `hmz internal`
routes, if the line is one humanize renders and spawns rather than one a person types. Both
tables are `name: (what carries it out, the summary the listing shows)`, and everything routed
is listed: there is no third table for things that run but are not shown. Import your layer
*inside* the function, not at the top of the module — `cli/__init__.py` is loaded by every
command including the one the bundled target half runs, so an import at the top is a cost every
other command pays. Write through `cli/output.py` rather than through `print` where the
command has a `--json` of its own: `Out.row` is one call for the line a person reads and the
object a program reads, and holding one open is what keeps a stray print out of the stream.

**A flow.** Just a directory: one in a [flowverse](/reference/flows#flowverses)'s own `flows/`
for one it offers, one in `.humanize/flows/` for one of your own. humanize's own go in
[humanfia/flowverse](https://github.com/humanfia/flowverse) rather than in `flows/builtin/`,
which holds `chat` alone — that is what an interface with no network yet has to open talking to,
and everything else is content that should be able to change without a release. Its `__init__.py` is the flow, whatever it imports
lives beside it, and its `skills/` is what it brings. They are content and import nothing of
humanize but `hmz.flows`, which is where everything a flow is written against is handed
through from.

## The checks

```sh
uv sync
uv run pre-commit install     # then every commit is checked before it is made

uv run pre-commit run --all-files   # format, lint, types
uv run pytest                       # every tier this machine can run -- the gate
uv run pytest --run-agents          # also the system tier: the real CLIs, real tokens
```

Run them through `uv run`, not `uvx`: the lockfile pins the versions the hooks and CI enforce.

A test that needs a model to answer does not reach anybody's gateway: `tests/llm.py` serves an
OpenAI-compatible endpoint on the loopback — `GET /v1/models` for a catalogue and
`POST /v1/chat/completions` for a turn — out of what the test said it serves and says, and
writes down every request it took. The `llm` fixture hands one out, and `Serving.account(cli)`
writes down an account of any backend pointed at it, reading which variable routes that
backend's turns off its own profile.

- **ruff** with `select = ["ALL"]`, less what this codebase has a reason to be without. Every
  exemption in `pyproject.toml` carries the reason it is there.
- **pyright** in strict mode, with `# type: ignore` comments disabled — a suppression names a
  pyright rule or it does not exist.
- Google-style docstrings, and type annotations everywhere.

The tests are in three directories, by what is on the other side of them — and the layering
above is why that line can be drawn at all. `tests/unit/` calls into a package and asserts.
`tests/integration/` reaches a seam, a driver's CLI or an app server or a transport, and finds
this repository's own stand-in on the far side, which is the same move the layers make for
imports: a boundary is a place you can put something else behind. `tests/system/` is the tier
where the far side is real, and it is the one CI does not run.
[Contributing](/contributing/) has the table.

CI runs all of it over every file, and the first two tiers on each Python the package claims,
on both Linux and macOS. It never runs `tests/system/` — `--ignore=tests/system`, so on a
runner that tier is not even collected, since a hosted machine has no signed-in CLI, no ptrace
and no docker to be right or wrong about. The tests that run an agent under an anchor need
Linux on x86-64 or aarch64 and skip aloud anywhere else; the serving half, and everything above
it, is held to both.
