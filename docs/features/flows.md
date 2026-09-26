---
pageClass: hmz-feature
---

# A flow is Python

A flow is a directory holding Python — an `async` function that takes a task and the agents,
environments and params it declared — and whoever writes one is a **weaver**. A loop, a command
run between two turns, a file read, a condition on what the last answer said: it is a function,
so it may do whatever a function does.

What makes it more than a function is what it **declares**. Every agent it drives is a role with
a name and a type, and the type says what the flow will ask of it; every environment its agents
work in is a role the same way; the settings it takes are a pydantic model. What the flow is
handed is exactly that, and nothing more.

<HmzLoops />

## What a flow declares

One decorator, and three types it names:

```python
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import GoalCommandAgentMixin, LocalEnv, ShellEnvMixin, flow


class Worker(Agent, GoalCommandAgentMixin): ...


class Workspace(LocalEnv, ShellEnvMixin): ...


class Agents(AgentCollection):
    worker: Worker


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def pursue(task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext):
    ...
```

What it carries is what a command line cannot otherwise know:

- **Which agents it drives, and what it calls each.** A role is a key of the collection, so a
  flow says `actor` and `reviewer` rather than "the first one" — and `-a actor=…` is how a run
  fills it, and the name a [trace](/features/tracing) groups that agent's sessions under. A role
  left out of a run is refused before the first turn rather than partway through a loop.
- **What it needs of each.** A role's type is `Agent` with the mixins it asks for — a
  [goal](/features/goals), [steering](/features/steering), a [hook](/features/hooks) only some
  harnesses reach — and a harness that cannot serve one is refused before anything starts. See
  [the capability map](/features/capabilities).
- **What each may touch.** A `Permission` on the role — its workdir, the rest of the user's
  home, the machine, the network — which every session of that agent runs under.
- **Where each works.** An environment role: the directory the run was started in (a
  `LocalEnv`, which nobody names), or one on another machine that `-e` points at, with what the
  flow may do there — run programs, run scripts, read and write files, add worktrees, make
  throwaway copies.
- **Settings of its own**, as a `FlowParams` model: `-p rounds=5` on a command line, a form in
  the interface, an instance from a calling flow.
- **Whether it can be [picked up](/features/resuming)** where its last run left off.
- **One file, several flows.** Three phases of one thing are one thing to write and three to
  run, each asking only for the roles it drives and only for the params it takes.

## What it is handed is exactly what it declared

The types a flow imports from `hmz.flows` are protocols: they describe, and they run nothing.
What the flow is handed at run time is the runtime's own object for each role — a *view* of the
real agent or machine, holding what that role was granted. A harness that could run a `/goal`
does not let a flow run one through a role that did not ask for it; a machine that could run a
bash script does not let a flow run one in an environment declared to run programs only. Either
raises `CapabilityNotGranted`, so what a flow declares is the whole of what it can do — which is
what makes a declaration something to read rather than something to hope.

## Flows are loaded as code

A flow rewritten between two runs — by hand, or by an agent that flow is itself driving — runs
as it is *now*: the next run that nobody else is running it in imports it afresh. Within one run a flow's module is imported once
and kept, so two calls of one flow in one run are the same code.

Its own directory is importable while it runs, so what it keeps beside its entry point imports
by a plain name. All of which is why a flowverse is trusted the way a repository of code is
trusted rather than read as data, and why [Security](/user/security) is a page rather than a
paragraph.

## The shapes a loop takes

The diagram above is the whole vocabulary, and each shape is a few lines:

- **A conversation.** The flow waits for the next thing to say, says it, and waits again.
  Between two turns it is a coroutine sitting on an `await` that has not returned.
- **Ralph.** A session of its own each round: the agent starts from the task and the repository
  with nothing of the last round in context. The repository is the memory.
- **Stateful ralph.** One session, spawned once and held, re-sent the task every round. The
  conversation is what the flow is — and is the one thing a run picked up again cannot have
  back.
- **An actor and a reviewer.** One works; the other is asked, in a session of its own, for an
  [answer in a shape](/features/shapes), so the loop reads a field rather than a paragraph.
- **A fan-out.** One agent, a session per file, [all of them going at
  once](/features/concurrency).

## A flow that calls a flow

A loop worth having is a loop another loop can reach for. A flow asks for another by a ref —
`:review` beside it, `humanize1:gen-plan` in the same flowverse,
`git+https://github.com/humanfia/flowverse@main#rlar` in somebody else's — and calls what it is
given with agents and environments it already holds, awaiting whatever it answers with.

What it passes must carry at least what the called flow declares — its mixins, its permission,
its resources, its harness where it names one — or the call is refused before the called flow
runs. The called flow then sees exactly what *it* declared, however much more the caller had.
Its budget is the tighter of its own and what remains of the caller's, what it spends counts
against every flow above it, and whatever it raises reaches the caller as it was raised. A run
is a tree of these calls, sixty-four deep at most.

## Everything a flow needs lives inside it

So that it can be copied, forked and edited whole: a flow whose parts are elsewhere has a hole
in it wherever it lands.

- **Its own skills are the `skills/` directory inside it**, named by a role's `_skills`, and
  given to every session of that agent.
- **A skill maintained elsewhere is named as a git URL** with `#<skill>`, cloned under
  humanize's own home and fetched again the next time a run asks for it — so it keeps up, and
  goes on working when the network is down.
- **A skill that is not there stops the call that needs it** before any turn of it, not at the
  first turn. A flow that works by a skill it has not got is not one to start and find out about
  an hour in.

## Where flows come from

A flowverse is a git repository with a `flows/` directory in it, offered under its own name,
and **only that directory is read** — a repository is a README, a pyproject and a test suite as
well, and reading a flow means running it.

Nearest wins: this project's flows, then yours, then whatever there is to run, so a project may
mean its own `chat` by `chat`. A name qualified by a flowverse is that flowverse's and is never
stood in for.

One is always listed — `official`, the package's own `chat` plus humanize's repository of the
rest, listed whether or not it has been fetched. A list that only mentioned it once somebody had
thought to add it would be a list that hid what there is to run.

## Where the detail is

- [Writing a flow](/weaver/writing-a-flow) · [Loops](/weaver/loops) · [Testing a
  flow](/weaver/testing-flows)
- [Params of its own](/weaver/flow-settings) · [A flow that calls a
  flow](/weaver/calling-flows) · [Flowverses](/weaver/flowverses)
- [Flows reference](/reference/flows) — the contract, in full
