# Concepts

Eleven words carry the whole of humanize. They are defined here once, in the order they build
on each other, so nothing else has to redefine them.

## The one-sentence version

A **flow** — written by a **weaver**, shipped with humanize or held in a **flowverse** — drives
**agents**, each of which holds **sessions** with a coding-agent **backend**; a session is made
of **turns**; one run of a flow is an **epic**; a session works in an **environment**, a
directory on a machine, and its turns may run as a **provider**; and what the whole thing did is
read back as a **trace**.

## Backend

**A coding agent CLI installed on this machine that humanize knows how to drive.** There are
twelve: Antigravity CLI (`agy`), Claude Code (`claude`), Codex (`codex`), Cursor Agent
(`cursor-agent`), DeepSeek Harness (`dsh`), Grok Build (`grok`), Kimi Code (`kimi`), mimocode
(`mimo`), opencode (`opencode`), pi (`pi`), Qwen Code (`qwen`) and ZCode (`zcode`) — the short
name in brackets is what you write in an agent. Any CLI of your own that speaks the
[Agent Client Protocol](/reference/agents#a-cli-of-your-own) can be added at `/providers`.

humanize never talks to a model provider. It drives the CLI you already have, logged in the way
you already log in, so your credentials never pass through it. One it cannot find is not
offered: it looks on your `PATH`, then where an installer would have put one.

Which of a backend's own interfaces it is driven through — its command line, or the app server
it serves its own client from — is humanize's business, not yours. The consequences that do
reach you are in [Agents](/reference/agents#what-each-backend-can-do).

## Agent

**A backend, a model, and an effort — plus, optionally, the account it runs as.** That is the
whole definition, and it is what an `-a` says, after the role the agent fills:

```
reviewer = claude / claude-opus-5 : high
   │         │           │           └── effort: how hard to think
   │         │           └── model
   │         └── backend
   └── the role it fills in the flow
```

An agent holds no conversation. It is *structure*: the settings that every conversation it
opens will run at. Two consequences surprise people.

- **Two agents at the same model and effort are two agents.** An actor and the reviewer that
  reads its work are not one thing because they are configured alike. A [flow](#flow) that
  drives both drives two.
- **An agent has a role.** A flow declares its agents by role — `actor`, `reviewer` — and
  names each one it is handed by the role it fills. That is what a [trace](#trace) groups its
  sessions under, and what the interface asks you about.

**Effort** is the backend's own word, not humanize's, so the values differ. See
[Agents](/reference/agents#efforts).

| Backend | What its effort says |
| --- | --- |
| Claude Code | `low`, `medium`, `high`, `xhigh`, `max` — and `ultracode` |
| Codex | each model takes its own subset |
| Kimi Code | how hard *and* how wide: `swarmmax` is `max` thinking at the width of a fleet |
| pi | a thinking level, down to `off` |
| opencode, mimocode | the variant of the model |
| ZCode | two vocabularies, because its models are two kinds: `max`/`high`/`low`/`nothink` where a thinking budget is taken, `enabled`/`disabled` where only thinking-or-not is |

## Session

**One conversation with one agent, kept alive across turns.**

The first turn opens the session with the backend; every later turn resumes it, so the agent
still has the earlier turns in context. Discarding the session is how a flow forgets: a new
session starts from nothing. This is the single most important choice a flow makes.

```python
session = await agent.spawn(env=workspace)
await agent.run("do the task", session=session)   # opens it
await agent.run("keep going", session=session)    # resumes it, the first turn still in context
```

A session is **opened in an [environment](#environment)** — `spawn(env=…)` — and every turn of
it happens there: that is what a conversation is to these backends, one rooted at a directory.
So one agent can work in several places at once — one session per worktree, their turns going
together. See [Worktrees, copies and scratch](/weaver/worktrees).

A session can also be **branched**, `agent.fork(session, env=…)`: a second conversation carrying
this one's history and going its own way from there, made of the CLI's own fork. That is how a
flow tries two ways out of an expensive conversation without paying for it twice. See
[Branching a conversation](/weaver/branching).

Every session the backend opened is written down under an id, which is how its transcript is
found again later — a forked one under an id of its own, beside the one it was cut from.

## Turn

**One exchange with the model.** You say something. The agent thinks, uses tools and answers. A
turn can run for minutes and do a great deal.

A turn is the unit that:

- **can be watched** — everything the agent says arrives as it says it, not at the end;
- **can be talked to** — a line you say while a turn is running goes *into* that turn rather
  than starting another;
- **can be hooked** — it passes through named moments; a flow may hang an async function on
  one with its agent's `on_*` methods, and take it down again while the flow is running. See
  [Hooks](/weaver/hooks);
- **can fail** — a failed turn raises, and what it raises says why: an account refused, a model
  not served, a CLI that died. See [Flows › When something goes
  wrong](/reference/flows#when-something-goes-wrong).

## Flow

**An async function marked `@flow`, in a directory beside the skills it brings, that declares
the agents it drives, the environments they work in and the params it takes.** It is the loop:
what each agent is asked, in what order, and when to stop.

```python
@flow(agents=Agents, envs=Envs, params=FlowParams)
async def ralph_loop(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    agent, workspace = agents["agent"], envs["workspace"]
    while True:
        session = await agent.spawn(env=workspace)
        await agent.run(task, session=session)
```

What it declares is load-bearing. Each agent and each environment is a **role**, by name, and
the type of each role says what it has to be able to do — a goal, being steered, a hook only
some backends reach, a shell, a git worktree — and nothing more. humanize checks what it is
given against that before the first turn rather than hours into a loop, and then hands the flow
exactly what it declared: a flow whose reviewer was not declared able to be steered cannot steer
it, whichever backend is underneath.

| | |
| --- | --- |
| the agents, `AgentCollection` | a role apiece: what each agent is *for*, what it must be able to do, and what it may touch |
| the environments, `EnvCollection` | a role apiece: where the work happens, and what may be done there |
| the params, `FlowParams` | what it can be set up with, one field apiece |

A flow is ordinary Python and may branch any way it likes. Nothing asks it what it is doing;
what a run looks like is read off the turns going past. It drives
[many turns at once](/reference/flows#a-flow-that-waits-for-more-than-one-thing) by awaiting
several, and it may [call another flow](/reference/flows#a-flow-that-calls-another-flow) by its
ref and hand it the agents it already has. Starting one is the same either way.

One module may hold several: the flow named after its directory is the one a bare name runs,
and each other is run as `<flow>:<name>`. Three phases of one thing are then one thing to write
and three to run. Each asks only for the roles it drives.

At the prompt a flow is named by that same name, and a `$` in front of it
[starts one outright](/reference/tui#starting-a-flow-outright): `$ralph_loop fix the failing
test` is that flow, run on that line — the menu only opens if that flow is not set up in this
directory.

See [Flows](/reference/flows).

## Weaver

**Whoever writes a flow.** A user runs one; a weaver writes the Python it is.

It is a hat rather than a job — the same person usually wears both, often on the same
afternoon, because a loop that keeps stopping in the same place is a flow to edit rather than a
run to babysit. The word is here because the documentation splits on it: the [User
Guide](/user/) never asks for Python, and the [Weaver Guide](/weaver/) assumes you have run a
flow before writing one.

## Flowverse

**A git repository with a `flows/` directory in it.** One directory per flow holds an
`__init__.py`, what it imports and the `skills/` it brings; a flow that needs neither is a
single `.py`. The repository is cloned into `~/.humanize/flowverses/<name>/` and offered as
`<name>/<flow>`.

One is always there: `official`, which holds `chat` from the package and, once fetched, the
rest of the flows humanize offers. `official` is listed whether or not it has been fetched,
because what there is to run is not the same question as what has been downloaded. Add as many
more as you like; `/flowverses` is where they are added, fetched and taken away, and `/flow`'s
arrows step between them, because that is which list of flows is being read.

See [Flows › Flowverses](/reference/flows#flowverses).

## Epic

**One run of one flow, written down as it happens — and one directory.**

It opens when the flow starts and closes when the flow stops, finished, failed or interrupted,
and is never reopened. Its `epic.jsonl` records the flow, the agents and the backend's id for
every session each of them opened. Beside it are a record apiece for the flows this one
[called](/reference/flows#a-flow-that-calls-another-flow), a link per file each session was
logged to, the journal a flow that [can be picked up](/user/resuming) keeps, the programs a
[profiled](/user/tracing#profiling-a-run) run started, and the traces gathered of it
afterwards.

It does *not* record what the sessions said — the backend's own log is the turn-by-turn record,
and an epic is not a second copy of it. It exists because the backends log a session under an
id and never say whose it was: without the epic, two agents at one configuration are
indistinguishable afterwards, and with it a [trace](#trace) can say `builder` and `reviewer`.

Epics live under `~/.humanize/epics/<workspace>/`, one directory apiece. See
[Tracing](/reference/tracing#epics).

## Environment

**A directory on a machine, where a session's turns land and a flow's commands run.** A flow
declares the environments it works in, one role apiece, and opens each session in one of them.

| | |
| --- | --- |
| **This directory** | a role typed `LocalEnv`: the directory the run was started in, which humanize fills itself. Most flows work in nothing else. |
| **Another directory here** | `-e repo=local@/srv/project` |
| **A directory on another machine** | `-e repo=ssh@gpu-box/home/me/repo`. The agent process stays here — keeping its credentials and its link to its model provider — and everything it *does* happens there. |

An environment may be given more than its role asks for and never less: a role declared with a
shell may run commands, one declared with git worktrees may check out more of them, one declared
with eight GPUs is refused a machine with four. See
[Flows › Where each agent works](/reference/flows#where-each-agent-works) and
[Machines](/reference/machines).

## Provider

**One named set of credentials for one backend** — a subscription signed into, a key, or an
endpoint of somebody else's. It is kept apart from the CLI's own under
`~/.humanize/providers/<cli>/<name>/`.

An agent configured with one runs its turns as that account: with the provider's variables, and
reading its credentials from the provider's directory rather than the CLI's. Only the
credential files move; the sessions, the settings and the skills are the CLI's own.

It is a setting of the agent because it is the agent that signs in. That is what lets one flow
drive two agents of one CLI as two different accounts at once, each refreshing its own token
and neither able to read the other's. See [Providers](/reference/providers).

## Trace

**Everything a run left behind, as one timeline.**

Gathering one reads the backends' own transcripts and names each session by the agent that
opened it, using the epic. It writes a Chrome JSON trace into the epic of the run it is a trace
of; load it in [ui.perfetto.dev](https://ui.perfetto.dev). Each agent is a process, each row of
that agent's sessions is a track, and each slice is one thing the agent did. A run is gathered
from [`/epics`](/reference/tui#the-runs-that-have-already-happened) — **enter** goes into the
run, and *export it* gathers the trace and packs it with the run — and from Python as
`Hmz().epics.traced(epic)`.

It works on sessions no flow ever drove, too: a trace of yesterday's Claude Code session is
`Hmz().epics.trace()` away. See [Tracing](/reference/tracing).

## How they fit

```
epic ──── one run of one flow, written down
  │
flow ──── the loop, a directory of Python
  │
  ├── agent "builder"  ── backend + model + effort + account
  │     ├── session in env "workspace" ── turn, turn, turn …  ─┐
  │     └── session in env "workspace" ── turn                 │  every session's transcript
  │                                                            ├─ is written by the backend,
  └── agent "reviewer" ── backend + model …                    │  and read back as a trace
        └── session in env "workspace" ── turn                ─┘
```

## Two distinctions worth getting right

**Agent vs. session — what is remembered.** The agent is settings; the session is memory. A
flow that opens a session per turn is a Ralph loop: the agent starts from the task and the
repository every time. A flow that holds one session across turns is a conversation. Same
agent, opposite behaviour. The flow decides, not the agent.

**Turn failing vs. run stopping — what a loop should do.** A turn that failed raises a
`HarnessError` saying why, and a loop that wants to go round again catches it — the leaf it can
do something about, or `HarnessError` whole. A run that has been *told to stop* (ctrl+c twice or
`/stop` in the interface) or has spent its budget raises something else — a cancellation, or
`BudgetExceeded` — which a loop catching `HarnessError` does not catch, because a loop that
carried on past it would never end. Catch `HarnessUnrecoverable` only knowingly: a turn that
failed for a reason no other try could come out differently on is one the next round would meet
again.

---

Next: [Writing a flow](/weaver/writing-a-flow) to write one, [Agents](/reference/agents) for
the Python API, [TUI](/reference/tui) or [CLI](/reference/cli) to look something up.
