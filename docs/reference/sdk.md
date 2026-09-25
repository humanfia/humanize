# SDK reference

How a tool that is not humanize reaches humanize. There are two ways to reach a run from
outside, and `hmz.sdk` is where both are offered.

**Straight at the runtime.** `Hmz` is a workspace and everything humanize can be asked to do in
it — the same object the [command line](/reference/cli) holds, and the one the
[terminal interface](/reference/tui) reaches through the [daemon](/reference/daemon) holding
its run. A thing that can be done one way can be done every way, and is refused the same way
whichever way it was asked.

```python
from hmz.sdk import Hmz

hmz = Hmz()
hmz.exec(["-f", "chat", "-a", "assistant=claude/claude-opus-5:high", "say hello"])
```

**Over a daemon.** [`Daemons`](#daemons) is a run held where a terminal closing cannot end it:
a process of its own, one per workspace, reached over the socket beside it. That is what a tool
looking after a run somebody else started asks, and what holds a run of its own past its own
exit.

```python
from hmz.sdk import Daemons

held = Daemons().here()          # the run being held in this directory, or None
if held is not None:
    print(held.status())         # how many terminals are reading, and what is running
    held.detach()                # let go of them; the run goes on
```

Nothing here does any of it. Every answer is written where it is carried out — `hmz.runtime`
for what can be done in a workspace, `hmz.daemon` for a run held apart from a terminal — and
this hands those through under one name, so that a tool and humanize itself are holding one
object rather than two that agree for now. The [layers](/contributing/architecture) are
reachable by their own names too, which is what a tool writing an interface or a command line
of its own does.

## `Hmz`

```python
Hmz(workspace: str | os.PathLike[str] | None = None)
```

| Argument | |
| --- | --- |
| `workspace` | The project directory this is about, or `None` for wherever humanize is being run. Kept exactly as it was given: a workspace nobody named follows a flow that changes directory, and one that was named is the directory it named, spelled the way it was named. |

Nothing is loaded until it is asked for. Holding one costs one import; asking it for the runs of
a workspace is what loads the tracer.

| Attribute | |
| --- | --- |
| `workspace` | The project directory, as a `Path`. |
| `home` | Where humanize keeps what outlives one run — `~/.humanize`, or `$HUMANIZE_HOME`. |
| `settings` | [What humanize remembers](/reference/tui#what-it-remembers) about this workspace, as `hmz.runtime.settings.Settings`. |
| `flows` | [The flows there are](#flows), and the places they come from. |
| `verses` | [Where flows come from](#flowverses) — the same object as `hmz.runtime.flowing.verses`. |
| `accounts` | [The accounts an agent may be run as](#accounts), and what each backend runs as one. |
| `fallbacks` | [Where a turn goes](#fallbacks) when the place taking it cannot take it at all. |
| `epics` | [The runs of this workspace](#epics) that have already happened. |

| Method | |
| --- | --- |
| `backends()` | Every coding agent CLI humanize drives, as `hmz.coganchor.backends.Profile`. |
| `reports()` | Starts [reporting humanize's own failures](/user/reporting) where that has been answered yes. Returns whether anything is being reported. |
| `read(argv)` | Reads an `hmz exec` line into what it says: the flow, an agent and an environment per role, the params, the budget, the task, and whether to pick a run up. Everything [refused before anything runs](/reference/cli#what-is-refused-before-anything-runs) is refused here. |
| `run(...)` | A [`Run`](#run) of a flow over what a line said — the agents and environments by role, the params and the budget — which is what `exec` makes of one. |
| `exec(argv)` | The whole of `hmz exec`: reads the line, loads the flow, runs it to its return. |

## `Run`

One run of one flow. Making one starts nothing — whoever made it says which of the two they are
holding.

| | |
| --- | --- |
| `agents` | Every agent it drives, by role. |
| `running` | Whether the flow is still going. `False` before it is started. |
| `raised` | Whatever the flow raised, for a run started on a thread and now over. |
| `run()` | Runs the flow here, until it returns. |
| `start()` | Runs it on a thread of its own, and returns at once. |
| `wait(timeout=None)` | Waits for it to end. Returns whether it has. |
| `stop()` | Stops the flow: the turn running now is cut off, and every flow call of the run raises `FlowCancelled` at its next step rather than handing on. |
| `close()` | Closes every conversation still open, which is the backend's process going. The last thing there is to do about a run. |

```python
from hmz.sdk import Hmz

hmz = Hmz()
hmz.exec(["-f", "ralph_loop", "-a", "agent=claude/claude-opus-5:high", "-b", "cost=5",
          "fix the build"])
```

A `Run` is what to hold instead where the caller wants the run back while it goes — `start()`,
then `stop()` or `wait()` — made by `run(...)` from what `read(argv)` read off the same line.

## Flows

`hmz.flows` — [what a flow is](/reference/flows) is the layer under this.

| | |
| --- | --- |
| `all()` | Every flow there is to run, by the name `-f` takes. |
| `find(named)` | The file one flow is written in — or `named` itself where nothing answers to it, so whether a flow is there is whether what comes back is a file. |
| `about(named)` | The line a flow says about itself. |
| the roles | What it declares: an agent role and an environment role apiece — which of them the runtime fills, which may be left out, and what each must be able to do — its [params](/reference/flows#settings-of-the-flow-s-own), and whether it [can be picked up](/user/resuming). What `/flow` asks its questions from. |
| `fork(named, into=None)` | Copies it into this project's own flows, whole. |
| `running()` | Every flow call of the run going now, each with its depth and the call it is under. |
| `verses` | [Where flows come from](#flowverses). |

There is no checking a flow without running it any more — no static findings, no atlas and no
prophecy. A flow is tested by running it on the fake kit, `hmz.runtime.flowing.fakes`, which
drives it through the same engine with in-memory agents and environments. See [Testing a
flow](/weaver/testing-flows).

## Flowverses

`hmz.verses` — the same store [`/flowverses`](/reference/tui#where-flows-come-from) walks, and
the one `/flow` steps between with its arrows.

| | |
| --- | --- |
| `all()` | Every place there is, in the order their flows are offered. |
| `nearest()` | The same places, in the order a flow's name is looked up in. |
| `find(name)` | The place of that name, or `None`. |
| `add(url, name="")` | Fetches one and offers its flows under a name. |
| `fetch(name)` | Fetches one again, or for the first time. |
| `remove(name)` | Takes one away, flows and all. |
| `holds(one)` | What it holds, by the name each flow is offered under. **This reads the flows**, which means running them. |
| `edited(one)` | Whether anything has been written into its clone that fetching it again would undo. What anything fetching without being asked to asks first. |
| `standing(one)` | Which commit its clone stands at, and `""` for one that is not a clone. Asked either side of a fetch, by whatever has to know whether anything came down with it. |
| `where(name)` | The directory it is kept in. |
| `plain(url)` | A URL with whatever was signed into it taken out. |
| `whence(one, nowhere="-")` | Where it came from, as it may be shown to somebody — asked of which flowverse it is rather than of whether its URL is empty. |

## Accounts

`hmz.accounts` — [the accounts an agent may be run as](/reference/providers), and what each
backend runs as one of them.

| | |
| --- | --- |
| `all(cli="")` | Every account somebody made, or one backend's. |
| `ways(cli)` | How one backend can be signed into. |
| `way(cli, name)` | The way in it offers under a name. |
| `find(cli, name)` | The account of that backend under that name. |
| `where(cli, name)` | Where it keeps its credentials, whether or not it has been made. |
| `local(cli)` | Where the account this machine is already signed into keeps what is written of it. |
| `write(cli, name, way="", env=None, args=())` | Writes one down as it now stands, without running anything. |
| `make(cli, name, way, answers=None)` | Writes one down out of what its way in was answered with. |
| `sign_in(provider, way, answers=None)` | Runs a backend's own way in, under this account's paths. |
| `asks(way, given)` | What a way in still has to be told. |
| `serves(one)` | The other backends this account's credentials could run. |
| `copies(one, cli, name="")` | Writes the same account down for another backend. |
| `chain(one)` | Every account a turn under this one would carry on under, this one first. |
| `points(cli, name, at)` | Says which account a turn under one carries on under when it fails. |
| `remove(cli, name)` | Takes one away, credentials and all. |
| `env(said)` | Reads `NAME=VALUE` lines into what a turn under an account is run with. |
| `environ(provider)` | What a turn under this account is run with. |
| `models(cli, provider="")` | What one backend last said it runs as one account. |
| `asked(cli, provider="")` | When it was last asked, and `""` for never. |
| `ask(cli, provider="", seconds=None)` | **Starts the backend** to find out, and keeps what it said. |

## Fallbacks

`hmz.coganchor.fallbacks` — [where a turn
goes](/reference/tui#where-a-turn-goes-when-it-cannot-be-taken) when the place taking it cannot take
it at all.

| | |
| --- | --- |
| `default` | How a failed turn waits unless somebody said otherwise. |
| `policies()` | The waits there are. |
| `named(policy)` | The wait one name means, or `None`. |
| `all()` | Every step, in the order they were written down. |
| `reads(said)` | One place as it is written down, and `""` for a spelling no place answers to. |
| `spec(backend, model, provider="")` | One place, out of the three things a place is. |
| `tried(said)` | What is written down against one place. |
| `chain(said)` | The places one turn would walk, the one it starts at first. |
| `points(said, at)` | Says where one place's turns go when it cannot run at all. |
| `retrying(said, tries, policy, timeout)` | Says how a failed turn there is taken again. |
| `clear(said)` | Takes one step away. |

## Epics

`hmz.epics` — [the runs of this workspace](/reference/tracing#epics) that have already
happened.

| | |
| --- | --- |
| `under()` | The directory this workspace's runs are kept in. |
| `all()` | Every run, oldest first. |
| `read(epic)` | What one run was: when, which flow, on what, how it went, what it opened. |
| `sessions(epic)` | Every session it opened. |
| `opened(epic)` | What each agent opened, by the name the run knew that agent as. |
| `resumed(flow)` | The newest run of one flow here that can be picked up — what `--resume` carries on. |
| `traced(epic, *, output=None, start=None, end=None)` | Gathers one run into a [trace](/reference/tracing) of that run — its own sessions, by the ids it wrote down, beside the programs it profiled — and answers with where it went and what is in it. It goes beside the run unless an output is named. |
| `trace(*, sessions=None, agents=None, output=None, start=None, end=None, profile=None)` | The same collector, asked for whatever sessions you name — which is how a session no run ever drove is read back. |
| `bundled(epic, *, output=None, transcript=None)` | Packages one whole run up as one archive to send somewhere — its own records, every session log the backends wrote for it with the links followed, and a manifest — and answers with where it went and what went in. Credentials are struck out of every byte. See [Exporting a run](/user/export). |

## Daemons

`hmz.daemon` — [a run held](/reference/daemon) where a terminal closing cannot end it, as a
tool outside reaches one.

| | |
| --- | --- |
| `here(workspace=None)` | The run being held in one workspace, or `None` where nothing is. |
| `all()` | Every run being held on this machine, oldest first. |
| `hold(opens, workspace=None, *, columns=0, rows=0)` | Puts a run where a terminal closing cannot end it, and comes back once it is listening. `opens` is called in the held process with the run being held, and returns when the run is over — so a tool that wants a flow held runs one there, and one that wants an interface of its own held draws one. |

Each of these hands back a [`Daemon`](/reference/daemon#python), which is what humanize's own
ways in hold: `status()`, `attach()`, `detach()`, `stop()`, `kill()`.

```python
from hmz.sdk import Daemons, Hmz

LINE = ["-f", "ralph_loop", "-a", "agent=claude/claude-opus-5:high", "-b", "cost=5",
        "fix the build"]


def opens(session):
    # Runs in the held process, and returns when the run is over. `session` is what lets go
    # of the terminals reading it; a run nobody is drawing for never needs it.
    Hmz().exec(LINE)


held = Daemons().hold(opens)
held.status()
held.stop()
```

## Session

What is holding a run somewhere a terminal closing cannot reach, as whatever is drawing sees
one — a `Protocol` rather than the thing itself, so that a run held apart from a terminal and a
run in the process somebody typed `hmz` in are one interface: one is handed one of these and
the other is handed none.

| | |
| --- | --- |
| `attached` | How many terminals are reading this run right now. |
| `detach()` | Lets go of every terminal reading it, leaving the run running. Returns how many were let go of. |

`Held` is what implements it, and is what a tool holding a run of its own is handed: it is
[`Session`](#session) plus the hooks the process holding a run registers — `redrawn`,
`stopping`, `says`. Both names are here, so an interface of your own is one import away.
