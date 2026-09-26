# Flows

A flow is a **directory**: an `__init__.py` holding one or more `async` functions decorated with
`@flow`, whatever that imports beside it, and a `skills/` of the skills its agents work by. It
is the loop: which agent is asked what, in which environment, in what order, and when to stop.

```
my_loop/
├── __init__.py          the flow
├── _prompts.py          whatever it imports, which travels with it
└── skills/              what its agents are given, mounted onto every session they open
    └── review-notes/
        └── SKILL.md
```

Everything a flow needs lives in that directory, which is what makes a flow a thing you can
copy, fork and edit whole — `f` on one in `/flow` writes a copy into `.humanize/flows/`.

**A single `.py` file is a flow too.** A flow is a module, and that is the other shape one
has: `.humanize/flows/twice.py` is `-f twice`, exactly as a directory of that name would be.
It brings no skills — what is beside it is the other flows, and none of it came with that one
— so a flow that grows a `skills/` is a flow that becomes a directory. Where both exist under
one name, the directory wins.

It is ordinary Python. There is no DSL, no graph to declare, no state machine — a flow may
branch, sleep, read files, run commands, gather, and give up, because it is just an `async`
function.

## What a flow drives

**`hmz.flows` is the only import a flow needs.** The types a flow declares its agents,
environments and params with, the moments a hook hangs on, what a turn may spend, every
exception a flow can catch, and the three things that run — `flow`, `load` and
`Outworlder.new` — all come from that one name:

```python
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow, load
```

| Name | Is |
| --- | --- |
| `Agent` | A coding agent: sessions, turns, forks, what it may touch, and the hooks hung on it. What an agent role is typed as, with [mixins](#asking-for-an-agent-that-can-do-something) for anything more. |
| `Session` | One conversation with one agent, in one environment, kept across turns. What `agent.spawn(env=…)` answers. |
| `Env` | A working directory on a machine — this one, or one reached over ssh. What an environment role is typed as, with [mixins](#where-each-agent-works) for what the flow does there. |
| `LocalEnv` | The workspace the run was started in, which the runtime fills itself. |
| `Outworlder` | Whoever is outside the run — the person at the prompt — taking turns as an agent of the flow. The runtime fills it too. See [the person at the prompt](#the-person-at-the-prompt). |
| `AgentCollection`, `EnvCollection` | The `TypedDict`s a flow subclasses to declare its roles, one key apiece. |
| `FlowParams` | The pydantic model a flow subclasses for [settings of its own](#settings-of-the-flow-s-own). |
| `FlowContext`, `FlowState` | What a flow knows of its own call: [its budget, what it has spent](#the-context), and what a [resumable](#a-flow-that-can-be-picked-up) one keeps. |
| `Budget`, `Usage` | [What a run may spend](#what-a-run-may-spend), and what it has. |
| `Flow` | A flow, ready to be called: what `@flow` and `load` answer. |

They are **protocols**, not base classes. What a flow is handed when it runs is the runtime's
own object for each role — a view of the driver underneath, granted exactly what the role
declared and nothing more — and it answers to these structurally. So a role typed `Agent` is
handed an agent that cannot run `/goal`, even on a harness that has a goal feature, and one
typed with `GoalCommandAgentMixin` is handed one that can. What a role's type says is what the
flow will do with it, and the view holds the flow to it: anything else raises
`CapabilityNotGranted`.

Importing `hmz.flows` costs pydantic and nothing of humanize's own. Everything humanize does
*to* a flow — finding one by name, listing them, loading one by its ref, running it over the
drivers of real coding agents and machines, and the in-memory fakes a test runs one on — is
`hmz.runtime.flowing`, which no flow imports.

## The contract

A flow is an `async` function decorated with `@flow`, which says what it needs:

```python
"""Two passes over the same task."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def twice(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Does the work, then reads it back and fixes what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])
    await builder.run(task, session=session)
    await builder.run("Now review what you just did, and fix anything wrong.", session=session)
```

```sh
hmz exec -f twice -a builder=claude/claude-opus-5:high -b cost=5 "fix the build"
```

The rules, each refused with `FlowDefinitionError`:

- **It is an `async def`**, called with the task and four keyword arguments: `agents`, `envs`,
  `params` and `ctx`.
- **`agents=` is an `AgentCollection` subclass and `envs=` an `EnvCollection` subclass**, one
  key per role, each typed as what that role must be — see [how many agents, and what they are
  for](#how-many-agents-and-what-they-are-for) and [where each agent
  works](#where-each-agent-works).
- **`params=` is a `FlowParams` subclass** — `FlowParams` itself for a flow that takes none.

The decorator refuses all of that as it runs, but for what each role is typed as: a value no
agent or environment can be — `builder: int` — is refused the first time the flow is called or
described, since that is when the collections' annotations are read.

What else the decorator takes:

| Argument | What it says |
| --- | --- |
| `name` | What the flow is called in its module, which is what a ref names it by after the colon. The function's name by default. Letters, digits, `_`, `.` and `-`: nothing a ref spells anything else with. |
| `description` | One line saying what it does, where flows are listed. The first line of the function's docstring by default. |
| `hidden` | Leave it out of the lists a person picks a flow from. It can still be run and [loaded](#a-flow-that-calls-another-flow) by its ref. |
| `resumable` | A run of it [can be picked up](#a-flow-that-can-be-picked-up) where it left off, which is what gives it a `ctx.state`. |

The collections' annotations are read the first time the flow is called or described, not when
the decorator runs, against the namespaces it was written in. So `from __future__ import
annotations`, types written as strings, and collections declared inside a function all work,
and importing a module of flows costs nothing but defining them. `NotRequired`, `Required`,
`ReadOnly` and `Annotated` are read through.

What the function returns is what whoever called it gets back — a flow calling this one,
through [`load`](#a-flow-that-calls-another-flow), or a test. Anything else the module does as
it is imported is the flow's own business and fails as it would anywhere.

## How many agents, and what they are for

A flow names every agent it drives, one key of its `AgentCollection` apiece, and types each as
what it must be able to do:

```python
from typing import NotRequired

from hmz.flows import Agent, AgentCollection, Outworlder


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent
    second_opinion: NotRequired[Agent]
    human: Outworlder
```

```python
actor, reviewer = agents["actor"], agents["reviewer"]
if "second_opinion" in agents:
    ...
```

The collection is a `TypedDict`, so the flow reads its agents by key, a type checker knows
what each one is, and `NotRequired` is a role whoever runs the flow may leave out. A required
role left unfilled is refused before anything starts — `MissingRole`, with the role's name.

**The role's name is what everything calls that agent.** It is not only for the flow's own
readability:

- `-a reviewer=codex/gpt-5.6-sol:high` fills it on a command line, and `/flow` asks what *the
  reviewer* runs rather than what agent 2 of 3 runs.
- The line above the prompt says `reviewer · codex/gpt-5.6-sol:high`, a
  [trace](/reference/tracing) groups that agent's sessions under `reviewer`, and
  `agent.role` says it.
- What each role was set to run is [remembered per role](/reference/tui#what-it-remembers), so
  a flow that grows a role in the middle does not hand the reviewer's model to the builder.

A role typed `Outworlder` is not one anybody fills: it is [the person at the
prompt](#the-person-at-the-prompt), and the runtime fills it. `-a` naming one is refused.

## Asking for an agent that can do something

`Agent` is what every harness can do: open a session, take a turn, answer in a shape, fork, be
narrowed, and have the six hooks every harness reaches hung on it. Anything only some harnesses
can do is a **mixin**, and a role that needs it says so by subclassing:

```python
from hmz.flows import Agent, GoalCommandAgentMixin, PermissionRequestHookAgentMixin


class Builder(Agent, GoalCommandAgentMixin, PermissionRequestHookAgentMixin):
    """Pursues the task as its own goal, and has its tool requests put to the flow."""


class Agents(AgentCollection):
    builder: Builder
    reviewer: Agent
```

| Mixin | What it lets the flow do |
| --- | --- |
| `GoalCommandAgentMixin` | Run `/goal <objective>`: the harness's own goal feature keeps the agent going until it decides the objective is met. See [Goals](/weaver/goals). |
| `LoopCommandAgentMixin` | Run `/loop <interval> <task>`, the harness's own recurring task. |
| `SteeringAgentMixin` | `steer` a turn while it runs. See [sessions and turns](#sessions-and-turns). |
| `PermissionRequestHookAgentMixin` | `on_permission_request`: answer the harness asking whether a tool may run. |
| `SubagentStartHookAgentMixin` | `on_subagent_start`: hear of the agent starting subagents of its own. |
| `SubagentStopHookAgentMixin` | `on_subagent_stop`: hear of one finishing. |
| `AskUserHookAgentMixin` | `on_ask_user`: answer the agent stopping mid-turn to ask its user a question. |

It is held to twice:

- **Before the run.** An agent whose harness does not serve what its role declares is refused
  before anything starts — `CapabilityMissing`, naming the mixin and the harness — so a flow
  built on a goal cannot be started on a harness with none and fail an hour in:

  ```console
  $ hmz exec -f pursuing -a worker=pi/gpt-5.5:high -b cost=5 "fix the build"
  hmz exec: error: pursuing:pursuing: 'worker' needs GoalCommandAgentMixin, which pi does not serve
  ```

  `/flow` offers only the harnesses that would do for each role, so it cannot be chosen wrong
  there at all.
- **At every use.** A flow that uses something its role did not declare raises
  `CapabilityNotGranted`, whatever the harness underneath could do: a `/goal` or `/loop`
  prompt without its mixin, `steer`, one of the four hooks above, a script `exec`, files,
  worktrees, copies or scratch directories. A type checker catches most of these before
  anything runs, since the protocol a role is typed as has no such method.

### What each harness serves

Each harness serves exactly this, and has a protocol of its own that declares exactly it:

| Harness (`-a`) | Protocol | Mixins it serves |
| --- | --- | --- |
| `claude` | `ClaudeCodeAgent` | Goal, Loop, Steering, PermissionRequest, SubagentStart, SubagentStop, AskUser |
| `codex` | `CodexAgent` | Goal, Steering, PermissionRequest, SubagentStart, SubagentStop, AskUser |
| `cursor-agent` | `CursorAgent` | SubagentStart, SubagentStop |
| `kimi` | `KimiCodeAgent` | Goal, Steering, PermissionRequest, AskUser |
| `zcode` | `ZCodeAgent` | Goal, PermissionRequest, AskUser |
| `grok` | `GrokBuildAgent` | nothing beyond `Agent` |
| `pi` | `PiAgent` | Steering, AskUser |
| `dsh` | `DeepSeekHarnessAgent` | Goal |
| `opencode`, `mimo`, `qwen`, `agy` | `OpenCodeAgent`, `MiMoCodeAgent`, `QwenCodeAgent`, `AntigravityAgent` | nothing beyond `Agent` |
| a CLI added by hand, over ACP | `Agent` | nothing beyond `Agent` |

A role typed as one of these protocols asks for **that harness**, and everything it serves:

```python
from hmz.flows import ClaudeCodeAgent


class Agents(AgentCollection):
    builder: ClaudeCodeAgent  # Claude Code, and nothing else will do
```

Any other harness given for it is refused before anything starts, with `HarnessMismatch`. Reach
for this only where the flow really is written for one CLI; a role declared by the mixins it
uses is a role more harnesses can fill. `HARNESS_AGENTS` maps each `HarnessKind` to its
protocol.

The one flow granted everything its harness serves whatever it declares is
[`chat`](#the-flow-in-the-package).

## What each agent may do

What an agent may touch is the role's to say, with `_permission`:

```python
from hmz.flows import Agent, Permission, PermissionKind


class Reviewer(Agent):
    _permission = Permission(local=PermissionKind.READ, user=PermissionKind.NONE,
                             system=PermissionKind.NONE)
```

| Scope | What it covers | Default |
| --- | --- | --- |
| `local` | the environment's workdir the session works in | `ALL` |
| `user` | the rest of the home directory of the user the agent runs as | `READ` |
| `system` | everything else on the machine | `READ` |
| `online` | the network: the CLI's own web search and fetching | `NONE` |

Each is `NONE`, `READ` or `ALL`, which order that way. The scopes nest, so a wider one may never
be granted more than a narrower one inside it — `local >= user >= system` — and `online` is all
or nothing. A `Permission` that breaks either is refused where it is made, with `ValueError`.

**Nothing is ever asked.** Every harness runs at its nothing-asked mode — `danger-full-access`
and `never` on Codex; on Claude Code, whose `bypassPermissions` a managed policy may forbid, its
manual mode with humanize answering every request yes — and where a CLI refuses that, in the most
permissive mode short of the model reviewing its own actions, with every request approved by
humanize. No session waits on a person to approve a tool, and no model reviews another's. What limits an agent is this, and whatever [hooks](#hooks-in-a-flow) the
flow hangs on it. How the scopes reach each CLI:

| `local` | Every harness but dsh and ACP | dsh, ACP |
| --- | --- | --- |
| `READ` or `NONE` | the CLI's read-only rung — Claude Code's `plan`, Codex's read-only sandbox, a tool list with nothing that writes | `bypass` |
| `ALL` | `bypass` | `bypass` |

Three things that table does not say:

- **`user` and `system` are not fenced.** A session that may write its workdir may write
  anywhere its user can. Two of these CLIs have a sandbox that could fence it — Codex's
  `workspace-write` and cursor-agent's `--sandbox enabled` — and neither is used: the flow API's
  own word for Codex's bypass is `danger-full-access`, and the sandbox is bubblewrap, which
  cannot start where it is given no user namespace, so a fence would be a flow that loses its
  shell wherever it runs in a container. A known widening, written down rather than hidden.
- **`local` `READ` reads outside the workdir too**, which is wider than a `user` or `system` of
  `NONE`; and dsh and ACP CLIs can be held to nothing but `bypass`.
- **`online`** is the CLI's own web tools: on for `ALL`, off for `NONE` where the CLI can be
  told, and left as the CLI has it where it cannot (cursor-agent, pi, Antigravity, ACP). A shell
  command the agent runs reaches the network whatever this says.

While a hook is hung that only an asking CLI reaches, the CLI is started so that it asks, and
humanize answers every request yes unless the hook says no: Codex runs with approval policy
`untrusted` while an `on_permission_request` hook is hung, and turns its
`default_mode_request_user_input` feature on for an `on_ask_user` one; Kimi Code and ZCode run at
their ask-and-approve rung while either is hung. A permission hook's answer overrides the bypass
it runs under. See [Agents](/reference/agents) for the rungs themselves.

**An agent given for a role holds at least what it declares.** One holding less is refused
before anything runs, with `PermissionTooNarrow`, and the flow's sessions run under exactly the
role's permission, whatever the agent handed in held.

**`derive` narrows.** An agent the flow holds can be narrowed for a stretch of the flow — a
reviewer that may not write, a session given fewer skills — and never widened:

```python
reading = agents["builder"].derive(
    permission=Permission(local=PermissionKind.READ, system=PermissionKind.NONE)
)
```

A wider permission, or a skill the role was not given, raises `CapabilityNotGranted`. The
derived agent shares the original's hooks and its sessions; the original is unchanged.

And `_skills` says which skills the role's sessions carry — see [the skills a flow
brings](#the-skills-a-flow-brings).

## Sessions and turns

A session is one conversation of one agent in one environment. A turn is a prompt and what the
agent answered:

```python
coder, workspace = agents["coder"], envs["workspace"]

session = await coder.spawn(env=workspace)
said = await coder.run(task, session=session)                           # str
verdict = await coder.run("Is it done?", session=session, output_schema=Verdict)  # a Verdict
```

- **`output_schema=`** is a pydantic model, and the turn answers with an instance of it; an
  answer that cannot be read as one raises `OutputSchemaError`. See [Answers in a
  shape](/weaver/shapes).
- **`budget=`** limits that one turn, on top of the flow's own. See [what a run may
  spend](#what-a-run-may-spend).
- **A prompt starting `/goal`** hands the turn to the harness's own goal feature, and one
  starting `/loop` to its recurring task — each only for a role declared with the mixin for it
  (Claude Code, Codex, Kimi Code, ZCode and dsh have a goal; Claude Code alone a `/loop`, which
  goes to the CLI as it is). Every other prompt goes to the agent as it is.
- **A session takes one turn at a time.** A second `run` on a session whose turn is under way
  raises `SessionError`; two sessions of one agent may take turns at once.
- **A session belongs to the agent that opened it.** Handing it to another agent — or to the
  same agent as a called flow holds it — raises `SessionError`.
- **`session.usage`** is what its turns have spent so far, up to date whenever it is read;
  `session.agent` and `session.env` are what it is of.

`steer` puts words into a turn while it runs, for a role declared with `SteeringAgentMixin`
(Claude Code, Codex, Kimi Code, pi):

```python
turn = asyncio.create_task(coder.run(task, session=session))
await asyncio.sleep(600)                                  # ten minutes in
if not turn.done():
    await coder.steer("Wrap up: commit what you have.", session=session)
said = await turn
```

The agent takes a steer when it next looks, and carries on; `queued=False` interrupts the turn
first and goes on from the new prompt, as pressing Esc before typing would. Steering a session
with no turn under way raises `SessionError`.

`fork` opens a second session that carries on from where one is, and leaves the first as it
was:

```python
tried = await coder.fork(session, env=workspace)
```

Claude Code, Codex, Kimi Code and ZCode fork into another environment as well as the one the
session is in; every other harness that forks does so only into the same workdir; cursor-agent,
Antigravity and dsh do not fork, and raise `UnsupportedOperation`. A fork is cut where it takes
its first turn, so it is refused then if the session it came from has taken a turn since. See
[Branching a conversation](/weaver/branching).

**A session is closed when the flow call that opened it ends** — and every call it started has —
**or as soon as nothing holds it any more**, whichever comes first. There is no `close`: a loop
that opens a fresh session a round holds one or two open however many rounds it runs, and a
session kept in a variable, a list or a dict stays open for as long as it is kept. One handed
back to a caller is closed all the same as the call that opened it ends. A fork keeps the
session it was forked from open until its own first turn, which is where it is cut. A turn that
is cancelled — a `TaskGroup` sibling failing, a deadline, ctrl+c — interrupts the CLI rather
than leaving it running.

## Where each agent works

An environment is a working directory on a machine. A flow names every one it works in, one key
of its `EnvCollection` apiece, and types each as what it will do there:

```python
from hmz.flows import BashEnvMixin, Env, EnvCollection, FilesEnvMixin, GPUEnvMixin
from hmz.flows import LocalEnv, ShellEnvMixin


class Workspace(LocalEnv, BashEnvMixin, FilesEnvMixin):
    """The directory the run was started in: scripts run there, and files are read."""


class Trainer(Env, ShellEnvMixin, GPUEnvMixin):
    _gpu_count = 8
    _gpu_memory = 80 * 1024**3


class Envs(EnvCollection):
    workspace: Workspace
    trainer: Trainer
```

```sh
hmz exec -f train -a coder=claude/claude-opus-5:high -e trainer=ssh@gpu-box/home/me/repo \
    -b duration=6h "get the loss under 2.1"
```

A role typed as **`LocalEnv`** — or a subclass of it with mixins — is the workspace the run was
started in, which the runtime fills itself: no `-e` names it, and one that tries is refused.
Every other role is named with `-e <role>=<backend>@<provider>/<workdir>`: `local@/srv/data`
for a directory on this machine, `ssh@gpu-box/home/me/repo` for one on a host `ssh` reaches,
and `ssh@gpu-box/~/repo` for one under the home directory there. An agent spawned in an
environment works in its workdir, on its machine — an ssh environment is where that agent's
turns land.

What every `Env` has: `workdir`, `backend` (`local` or `ssh`), `provider` (the host, or `""`),
`available`, `role`, and `derive_subdir(subdir=…)`, which is an environment at a directory
under this one, made if missing. The rest is mixins:

| Mixin | What it lets the flow do |
| --- | --- |
| `ShellEnvMixin` | `await env.exec(["pytest", "-q"], timeout=600)` — one program with no shell between, run in the workdir: its exit status, stdout and stderr. `timeout` in seconds, `0` for none; past it the program is killed and `EnvCommandTimeout` raised. |
| `BashEnvMixin` | `exec` of a string as well, run as `bash -c` would: `await env.exec("make test 2>&1 \| tail -20")`. |
| `FilesEnvMixin` | `await env.read(path)` → bytes, and `await env.write(path, data)`, relative to the workdir or absolute; a missing file raises `EnvFileNotFound`, which is a `FileNotFoundError`. |
| `GitWorktreeEnvMixin` | `derive_worktree` — see below. |
| `TemporaryClonedDirEnvMixin` | `derive_temp_clone` and `destroy_temp_clone` — see below. |
| `ScratchDirEnvMixin` | `derive_scratch` and `destroy_scratch` — see below. |

And three that are amounts rather than abilities, which the machine given for the role must
have — one that has less is refused before anything runs, with `ResourceUnmet`:

| Mixin | Says |
| --- | --- |
| `CPUEnvMixin` | `_cpu_count`: the fewest logical CPUs |
| `MemoryEnvMixin` | `_memory`: the least memory, in bytes |
| `GPUEnvMixin` | `_gpu_count` and `_gpu_memory`: the fewest GPUs, and the least memory each, in bytes |

### Worktrees, copies and scratch directories

Three ways to derive another environment on the same machine, each granted what the one it came
from was and filling the same role:

```python
tree = await workspace.derive_worktree(ref="main")        # a git worktree, checked out detached
trial = await workspace.derive_temp_clone("attempt-1")    # a throwaway copy of the workdir
notes = await workspace.derive_scratch("notes")           # an empty directory beside it

session = await coder.spawn(env=tree)                     # and an agent working in one
```

- **`derive_worktree(ref=None, dir=None)`** adds a worktree of the repository the workdir is in:
  `ref` checked out detached, or what the workdir has checked out; at `dir`, or a fresh
  directory the runtime picks. A workdir outside a repository, a ref git does not know, or a
  directory that is taken raises `WorktreeError`.
- **`derive_temp_clone(id)`** is a copy of the workdir — a reflink where the filesystem can
  make one. The same id from the same environment is the same copy, made once; asked for by
  another environment while this one holds it, it raises `TempCloneBusy`.
  `destroy_temp_clone(id)` removes it now and frees the id.
- **`derive_scratch(id)`** is an empty directory, the same one for the same id;
  `destroy_scratch(id)` removes it now.

Copies and scratch directories a flow made are **removed when that flow call ends**, after
every call it started has — unless the run is [resumable](#a-flow-that-can-be-picked-up), which
keeps them so that `--resume` finds them where they were. A worktree is left where it is.
Everything derived lives under `envs/` in humanize's home on that machine
(`~/.humanize/envs/<workdir>-<digest>/{clones,scratch,worktrees}/`), named after the workdir
and the id, which is how a resumed run finds the copy it left. See
[Worktrees, copies and scratch](/weaver/worktrees).

## Hooks in a flow

A flow holds its agents, so it can hang a hook on one and take it down again as it goes. A hook
is an `async` function from one moment's params to that moment's result, hung with the `on_*`
method for that moment. This is a Ralph loop that will not let a turn stop while the task file
still has unticked boxes:

```python
from hmz.flows import StopHookParams, StopHookResult


class Workspace(LocalEnv, FilesEnvMixin): ...


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def unfinished(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    agent, workspace = agents["agent"], envs["workspace"]

    async def not_yet(hook: StopHookParams) -> StopHookResult:
        left = "- [ ]" in (await workspace.read("TASK.md")).decode()
        return StopHookResult(block=left and hook.again < 5,
                              reason="TASK.md still has unticked boxes.")

    agent.on_stop(not_yet)
    while "- [ ]" in (await workspace.read("TASK.md")).decode():
        session = await agent.spawn(env=workspace)
        await agent.run(task, session=session)
```

One method per moment. The six every harness reaches are on `Agent`; the rest only on a role
declared with the mixin for them, and `on_outworlder_run` only on an `Outworlder`:

| Method | When | Params, beside `ctx` and `session` | Result |
| --- | --- | --- | --- |
| `on_session_start` | a session is about to take its first turn | — | `context`: text put before the first prompt |
| `on_user_prompt_submit` | a prompt is about to go to the agent | `prompt` | `block`, `reason`; `context` added to the prompt |
| `on_pre_tool_use` | the agent has reached for a tool that has not run | `tool`, `input` | `block`, `reason` told to the agent |
| `on_notification` | the agent stops to tell its user something | `message` | — |
| `on_stop` | a turn is about to end | `said`, `again` | `block`, with `reason` as the next prompt |
| `on_session_end` | a session is being closed | — | — |
| `on_permission_request` · `PermissionRequestHookAgentMixin` | the harness asks whether a tool may run | `tool`, `input` | `allow`, `reason` |
| `on_subagent_start` · `SubagentStartHookAgentMixin` | the agent starts a subagent | `subagent`, `task` | `context` |
| `on_subagent_stop` · `SubagentStopHookAgentMixin` | a subagent is about to finish | `subagent`, `said` | `block`, `reason` |
| `on_ask_user` · `AskUserHookAgentMixin` | the agent stops mid-turn to ask its user | `question`, `options` | `answer`, or `None` to leave it unanswered |
| `on_outworlder_run` · `Outworlder` | an outworlder made with `Outworlder.new()` is asked to take a turn | `prompt`, `output_schema` | `output` |

Each params class is `<Moment>HookParams` and each result `<Moment>HookResult`, all in
`hmz.flows`; `HookKind` names the moments. A result built with no arguments changes nothing, so
a hook that only watches returns one. Hanging a hook replaces the one hung there before, and
`None` takes it down.

- **A hook covers every session of the agent it is hung on** — including the fresh one a Ralph
  loop spawns every round — and of any agent `derive`d from it. It is the flow's own: a called
  flow's hooks are not heard by its caller's sessions, nor the other way round.
- **It runs as the flow the agent belongs to**, with that flow's `ctx`, on the flow's event loop.
  What it raises fails the turn the moment arrived in, and `run` raises it there.
- **What it answers is done where the CLI waits for it.** `on_pre_tool_use` refuses a tool on a
  CLI that gates its tools with a hook table of its own (Claude Code, Qwen Code), and on the
  rest hears of one already reached for. An `on_permission_request` refusal is the tool refused,
  its reason told to the agent — on Codex, whose refusals carry none, as a steer into the turn.
  `on_subagent_start` and `on_subagent_stop` are told: no CLI waits on either, so what they
  answer changes nothing.
- **A hook that keeps a CLI waiting 15 minutes** is answered as if nothing were hung, and the
  turn goes on. `on_ask_user` is the exception: a question waits for its answer.
- **A hook hung mid-turn** reaches that turn's later moments, except the ones that decide how a
  CLI is started — `on_pre_tool_use` on a CLI that gates its tools, and the [asking
  modes](#what-each-agent-may-do) an `on_permission_request` or `on_ask_user` hook starts Codex,
  Kimi Code and ZCode in — which take hold from the next turn.

See [Hooks](/weaver/hooks) for more, and [the agent asking the flow](/weaver/tools) for
`on_ask_user` as the way back from inside a turn to the flow.

## The person at the prompt

A role typed `Outworlder` is whoever is outside the run — you, at the prompt, taking turns as
an agent of the flow rather than typing into one:

```python
class Agents(AgentCollection):
    assistant: Agent
    human: Outworlder


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def talk(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    assistant, human = agents["assistant"], agents["human"]
    talking = await assistant.spawn(env=envs["workspace"])
    listening = await human.spawn(env=envs["workspace"])
    said = task
    while said:
        answered = await assistant.run(said, session=talking)
        said = await human.run(answered, session=listening)
```

Running it is asking what to say next; what it answers is what was typed. Asked for an
`output_schema`, the person is asked a question per field rather than shown a schema, and the
model is built out of what they typed.

**Nobody fills it.** The runtime does — at the top of a run it is the person who started it — so
an outworlder is never one of the agents `-a` names, and naming one is refused.

**It may be away.** `hmz exec` is always away, since nobody is at a prompt; in the interface,
[`/afk`](/user/afk) says you are. While it is away, `run` answers at once: `""` for text, the
schema built from its defaults where every field has one, and `OutworlderAway` otherwise.
`human.away` says which, so a flow can decide not to ask. The loop above ends at once under
`hmz exec`, having done the one thing it was given.

**A calling flow may stand in for it.** A flow that calls another whose role asks for an
outworlder passes its own, or leaves the role out and the callee gets the run's — or makes one
of its own and answers for it:

```python
from hmz.flows import OutworlderRunHookParams, OutworlderRunHookResult


async def approve(asked: OutworlderRunHookParams) -> OutworlderRunHookResult:
    if asked.output_schema is None:
        return OutworlderRunHookResult(output="Yes, go ahead.")
    return OutworlderRunHookResult(output=asked.output_schema())


stand_in = Outworlder.new()
stand_in.on_outworlder_run(approve)
await load(":rlcr")(task, agents={"builder": builder, "reviewer": reviewer, "human": stand_in},
                    envs=envs, params=RlcrParams())
```

An `Outworlder.new()` with no hook on it is away. `on_outworlder_run` is only for one made that
way: hung on the run's own, it raises `CapabilityNotGranted`. An outworlder carries no skills
and cannot be forked. And this is not [steering](/user/steering): steering is you putting a word
into an agent's turn, while an outworlder takes turns of its own.

## Settings of the flow's own

A flow that has settings says so with a `FlowParams` subclass, one field per setting:

```python
from typing import Literal

from pydantic import Field

from hmz.flows import FlowParams


class Params(FlowParams):
    """What this flow takes."""

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")


@flow(agents=Agents, envs=Envs, params=Params)
async def loop(task, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext):
    for _ in range(params.rounds):
        ...
```

```sh
hmz exec -f loop -a agent=claude/claude-opus-5:high -p rounds=5,mode=slow -b cost=10 "…"
```

That is the whole of it. The model is what asks: the fields are the questions, their types say
how each is answered, `description` is the line shown beside each, and whatever the model
refuses is what the flow will not run.

- **`-p key=value`**, as many as there are, or a comma list in one. A value is read as the
  field's type, or as JSON where that is what reads it — `-p tags='["a","b"]'` — and a comma
  splits two settings only where a `key=` follows it, so `-p note=one,two` is one setting.
- **`FlowParams` forbids a key it does not declare**, so a setting mistyped is refused rather
  than ignored. Everything the model refuses is `ParamsError`, before anything starts.
- **Every field has a default or is required.** A field with none must be given with `-p`.
- **The interface asks the same model.** `/flow` puts up a form of these fields between
  choosing the flow and starting it, and what you set is [remembered per
  flow](/reference/tui#what-it-remembers).
- **Combinations the flow cannot run belong in the model** — a `model_validator` — which is
  refused where it was typed rather than an hour into the run.

A flow with none passes `params=FlowParams` to the decorator. A flow calling another passes an
instance of the callee's own model; see [a flow that calls another
flow](#a-flow-that-calls-another-flow).

## The context

`ctx` is what a flow knows of its own call:

| | |
| --- | --- |
| `ctx.flow` | The flow being called. |
| `ctx.budget` | The budget this call runs under: the tighter of its own and what remains of every one above it. |
| `ctx.usage` | What this call, and every call under it, has spent so far. |
| `ctx.state` | What a [resumable](#a-flow-that-can-be-picked-up) flow keeps across runs, or `None` for one that is not. |
| `ctx.resumed` | Whether this call picks up one an earlier run left off. |

Each call has its own: a flow gathering ten calls of another is ten contexts, each counting its
own spending, all of it counted in the caller's too.

## What a run may spend

A loop with nothing to stop it runs until somebody stops it, which is a bill nobody agreed to and
a week of rounds nobody read. So **every run has a budget**, and `hmz exec` will not start a flow
without one:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b duration=6h,cost=50 "$(cat TASK.md)"
```

```python
from datetime import timedelta

from hmz.flows import Budget

Budget(duration=timedelta(hours=6), cost=50.0, output_tokens=25_000_000, graceful=True)
```

| Field | What it limits |
| --- | --- |
| `duration` | How long, from when it started. A deadline. |
| `cost` | What it may cost, in USD. |
| `output_tokens` | How many tokens its agents may write. |
| `graceful` | Whether the turn under way when a limit is reached is let finish (`True`, the default) or cut off at once. |

At least one limit is set; a `Budget` that limits nothing is refused. `-b` writes it as
`duration=6h` (or `1h30m`, `90s`, `PT1H30M`, `HH:MM:SS`), `cost=50` (or `$50`), `output_tokens=25m`
(or `200k`, `200_000`) and `graceful=false`, in one `-b` or several, each at most once. `chat`
alone runs without one — it is a conversation, over when you stop typing — as
`Budget(cost=math.inf)`, which is also what unlimited is written as anywhere else.

**It is held to at every turn, whatever harness is behind it.** A limit reached mid-turn lets
that turn finish where the budget is graceful, and cuts it — the CLI stops spending — where it
is not; either way the next turn under that budget raises the `BudgetExceeded` leaf for it:
`DurationExceeded` (a `TimeoutError` too), `CostExceeded` or `OutputTokensExceeded`. **A spent
budget stays spent**: every later turn under it raises again rather than spending more. Past its
deadline, a call is stopped where it is — after the turns under way under it finish, where it is
graceful — and raises `DurationExceeded` there.

**Budgets nest.** A flow calling another may give the call a budget of its own, and a turn one:

```python
await load(":review")(task, agents=..., envs=..., params=..., budget=Budget(cost=2.0))
await agent.run(prompt, session=session,
                budget=Budget(output_tokens=50_000, graceful=False))
```

Each runs under the tighter of its own and what remains of every budget above it. A turn's own
budget is one turn long, so there is no next turn under it to refuse: a graceful one lets the
turn run to its end and only counts, and one meant to cut a turn short says `graceful=False`. What is spent
anywhere under a flow counts against every flow above it, from whichever thread reports it —
cost and tokens roll up — while `duration` is a deadline each call has of its own rather than a
sum, so ten calls gathered for an hour spend one hour of their caller's, not ten.

`ctx.budget` says what a call runs under, and `ctx.usage` what it has spent — a `Usage`, with
`duration` (the time its agents spent taking turns), `cost` and `output_tokens`. A flow may read
them to decide something: that there is not enough left for another round, say.

What a turn costs is read from what the CLI reports, priced with [humanize's price
table](/user/tally); a model nobody prices costs nothing there, so a cost limit alone does not
stop it — say `duration` or `output_tokens` as well.

## A flow that waits for more than one thing

Every flow is a coroutine, so waiting for several things at once is `asyncio`:

```python
import asyncio


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def both(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    actor, reviewer, workspace = agents["actor"], agents["reviewer"], envs["workspace"]
    acting = await actor.spawn(env=workspace)
    reading = await reviewer.spawn(env=workspace)
    acted, reviewed = await asyncio.gather(
        actor.run(task, session=acting),
        reviewer.run(f"Read the repository and say what is wrong: {task}", session=reading),
    )
```

`asyncio.gather`, `asyncio.TaskGroup`, `asyncio.timeout` and `except*` all work as they do
anywhere: a turn a `TaskGroup` cancels interrupts its CLI, and a subflow's exception reaches
`except*` with the class it was raised with. A fan-out is a session apiece:

```python
async def fix(path: str) -> str:
    session = await coder.spawn(env=workspace)
    return await coder.run(f"Fix the tests in {path}", session=session)

async with asyncio.TaskGroup() as group:
    fixing = [group.create_task(fix(path)) for path in paths]
said = [task.result() for task in fixing]
```

Two rules: turns of *one* session are still a sequence — a conversation is a conversation, and a
second `run` on a session whose turn is under way raises `SessionError` — and a flow that awaits
one thing at a time runs one turn at a time, which is what most of them want. Hooks, subflows and
budgets are the same either way: each call is a context of its own, so a gather of subflow calls
is a tree of them, each counting what it spends.

## A flow that can be picked up

A loop meant to run for a week is a loop that will be stopped and started: a machine goes down,
somebody stops it, a turn takes the process with it. So a flow may say it can be picked up where
the last run of it left off, and one that does has a `ctx.state` to keep what it needs to:

```python
@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def each_file(task, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    """One pass per file, however often it is stopped."""
    agent, workspace, state = agents["agent"], envs["workspace"], ctx.state
    assert state is not None                       # a resumable flow always has one
    if "left" not in state:
        _, out, _ = await workspace.exec(["git", "ls-files", "*.py"])
        state["left"] = out.split()
    while state["left"]:
        session = await agent.spawn(env=workspace)
        await agent.run(f"{task}\n\nThis file: {state['left'][0]}", session=session)
        state["left"] = state["left"][1:]          # writing it is what saves it
```

**`ctx.state` is a mapping of JSON**: `state[key]`, `state[key] = value`, `del state[key]` and
`key in state`. A value JSON cannot hold raises `StateNotSerializable` where it is written, and
what is read back is what JSON gives back — so a fresh run and a resumed one read the same.

**It is saved as it is written**, each write flushed as it is made: a run worth picking up is
one that was stopped or killed rather than one that ended tidily. A change made *inside* a value
it holds — a list appended to — is a change no mapping can see; write the value back, as above.

**It is not a second copy of the transcript.** The harnesses keep that, and the run's
[epic](/reference/tracing#epics) already says which sessions it opened. What belongs here is the
handful of things the loop itself is keeping track of — which round it is on, which files it has
been through, what it has decided — which is the part of a run nothing else knows.

**`--resume` is what picks it up.** `hmz exec -f each_file --resume …` carries on the newest
resumable run of that flow in this workspace; without it every run starts fresh. In the
interface, `/resume` carries on the last run, and `/epics` offers it for the run under the
cursor. A run of a resumable flow keeps a **journal** — one file of JSON lines, appended to as it
goes, of every call, every state write, every session and every copy it made — and a resumed run
reads it back:

- The flow at the top picks up unconditionally, with `ctx.resumed` true and its state as it was.
- **A flow it calls picks up too, where the call is the same one**: the same flow, task, agents
  (harness, account, model, effort, permission, skills), environments (how each was derived from
  what a command line named, never a path) and params. Several identical calls are matched in the
  order they were made. A call that differs starts afresh, with an empty state.
- A flow that is not resumable has no state, and passes resumption through to the flows it
  calls.
- Temporary copies and scratch directories a resumable run made are kept rather than removed,
  so the resumed run finds them where they were.

## Running one

```sh
hmz exec -f <ref> -a <role>=<harness>[@<provider>]/<model>:<effort> [-a …] \
    [-e <role>=<backend>@<provider>/<workdir>] [-p <key>=<value>] \
    -b duration=…,cost=…,output_tokens=…[,graceful=…] [--resume] [--json] <task>
```

One `-a` per agent role and one `-e` per environment role, by name; `-p` for its params; `-b`
for its budget, which is required for every flow but `chat`. Each flag may be given several
times and takes a comma list. Roles the runtime fills — `Outworlder` and `LocalEnv` — are never
named, and a required role left out is refused before any agent starts. Full syntax in the [CLI
reference](/reference/cli#hmz-exec).

In the [interface](/reference/tui), `/flow` picks one by name, then asks for each role's agent,
each environment, its params and its budget.

From Python, a flow is run over drivers by `run_flow`, which is what both of those call:

```python
from hmz.flows import Budget, load
from hmz.runtime.flowing import open_agent, parse_agents, run_flow

said = parse_agents(["actor=claude/claude-opus-5:high", "reviewer=codex/gpt-5.6-sol:high"])
await run_flow(
    load("rlar"),
    "fix the build",
    agents={spec.role: open_agent(spec) for spec in said},
    envs={},
    params={},
    budget=Budget(cost=20),
)
```

`open_env` and `parse_envs` are the same for `-e`; the workspace a `LocalEnv` role is filled with
is the directory the process is in unless `local=` says otherwise, and an `Outworlder` role is
away unless `outworlder=` is given one.

It checks everything before anything starts — every required role filled, each driver serving
its role, the machines large enough, the params valid — then calls the flow with views granted
exactly what each role declared, and closes every session and removes every copy it made before
it returns or raises. To run one on no agent and no machine at all, see [testing a
flow](#testing-a-flow).

## Several flows in one file

Three phases of one thing are one thing to write and three to run. Give each its `name`, and
each is a flow of its own, called `<flow>:<name>`:

```python
"""Three phases of one thing."""

@flow(agents=Drafting, envs=Envs, params=IdeaParams, name="gen-idea")
async def gen_idea(task, *, agents, envs, params, ctx):
    """Opens a loose idea into a repo-grounded draft."""

@flow(agents=Planning, envs=Envs, params=PlanParams, name="gen-plan")
async def gen_plan(task, *, agents, envs, params, ctx):
    """Turns that draft into a plan both sides have converged on."""
```

```sh
hmz exec -f humanize1:gen-idea -a drafter=claude/claude-opus-5:max -b cost=5 "add undo to the editor"
hmz exec -f humanize1:gen-plan -a planner=claude/claude-opus-5:max \
    -a analyst=codex/gpt-5.6-sol:max -b cost=10 ""
```

Each declares its own agents, environments and params, so opening one asks about two agents
rather than five. What passes between them is whatever they write — a file, usually — or what one
returns to another that [calls it](#a-flow-that-calls-another-flow).

**A bare name is the flow named after its directory**: `-f humanize1` is the flow called
`humanize1` in `humanize1/`. Where there is none, it is the one flow of the module that is not
hidden, and where there are several, it is refused with `FlowNotFound` naming them. A module's
flows are only those defined inside its directory — a flow it imports from elsewhere is not one
of them — and two of one name are refused with `FlowDefinitionError`.

`hidden=True` keeps an implementation flow, used only by the flows that load it, out of the
lists and the `/flow` picker without losing its name: it remains callable as `<flow>:<name>`.
The lists show the flow a bare name means under the directory's name, and every other visible
flow of the module as `<flow>:<name>`.

## A flow that calls another flow

A flow is a loop over agents, and a loop worth having is one another loop can reach for. `load`
answers with the flow a ref names, and a flow is called the same way whichever of `@flow` or
`load` it came from:

```python
from hmz.flows import load


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def plan_then_build(task, *, agents: Agents, envs: Envs, params: FlowParams,
                          ctx: FlowContext):
    plan = load("humanize1:gen-plan")
    await plan(f"plan this first: {task}",
               agents={"planner": agents["builder"], "analyst": agents["reviewer"]},
               envs={"workspace": envs["workspace"]},
               params=plan.expected_params())
    ...
```

`await flow(task, *, agents, envs, params, budget=None)` runs it, from inside a run, and answers
with what it returned. `flow.expected_agents`, `expected_envs` and `expected_params` are what it
declares, `description` and `resumable` what it says of itself. A flow called outside every run
raises `FlowRuntimeError`.

### Refs

| Ref | Is |
| --- | --- |
| `:review` | a flow in the same module as the flow asking |
| `humanize1` | a flow in the same flowverse, by the [bare-name rule](#several-flows-in-one-file) |
| `humanize1:gen-plan` | a named flow of a flow in the same flowverse |
| `git+https://github.com/humanfia/flowverse@main#humanize1:gen-plan` | a flow of another flowverse, at a ref |

A relative ref is relative to the flow asking; asked for with no flow asking, it raises
`FlowRefError`, as does anything that is not a ref. A name the flowverse asking does not hold is
looked up [nearest first](#where-flows-live), as `-f` looks one up; one nothing answers to raises
`FlowNotFound`. A VCS ref is any `git+` URL pip would take, `@<rev>` optional and the default
branch without it: it is fetched once per URL and rev per run, on a thread and not until the
flow is first called, pinned to the commit it stands at, and cloned once per commit.

**A run imports a flow's module once**, however often it loads its flows, and nothing a run uses
is taken out of `sys.modules` while it goes. Two checkouts claiming one module name in one run —
two flowverses each with a `humanize1`, say — raise `FlowLoadConflict` rather than one replacing
the other under a flow still using it. A module whose files changed is imported afresh by the
next run nobody else is running it in.

### What the called flow is handed

**Hand it what it declares, no narrower.** Each agent passed must carry at least the mixins its
role in the callee declares, at least its `_permission`, and the harness where the role is typed
as one; each environment at least its mixins and resources. Anything short is refused before the
callee runs — `MissingRole`, `CapabilityMissing`, `PermissionTooNarrow`, `ResourceUnmet`,
`HarnessMismatch`, all `RequirementError` — so nothing of it has run and nothing has been spent.
What is passed must be an agent or environment the run handed out: one of the caller's own, or
one derived from them.

**It is handed exactly what it declared.** The callee gets a view of each granted what its own
role says — a reviewer the caller may steer is a reviewer the callee may not, if it did not ask
to — with the callee's own permission and skills on its sessions. Its hooks are its own and its
sessions are its own: a session opened by the caller is not one the callee can take a turn in.

**Roles the runtime fills may be left out.** An `Outworlder` role left out is the run's own
outworlder, and a `LocalEnv` role left out is the run's workspace; pass
[`Outworlder.new()`](#the-person-at-the-prompt) to answer for the person yourself. `NotRequired`
roles may be left out too.

**Params are its own.** An instance of the callee's `FlowParams` subclass is taken as it is;
another model or a mapping is validated into it, and refused with `ParamsError` where it does not
validate.

**A budget of its own** runs under what remains of the caller's; see [what a run may
spend](#what-a-run-may-spend). **Resuming** reaches it where the call is the same one; see [a flow
that can be picked up](#a-flow-that-can-be-picked-up).

**What it raises reaches the caller as it was raised** — never wrapped — so `except
CostExceeded` and `except* HarnessError` mean the same around a subflow as around a turn.

**Calls may be gathered, and may go as deep as you like** — to a point: flows called **64 deep**
raise `FlowDepthExceeded` at the call that would be the 65th, rather than a `RecursionError`
somewhere inside it. A call costs no filesystem work and no task, so a tree of ten thousand of
them is cheap.

**A call whose caller has ended** — cancelled, or failed, while something it started runs on —
raises `FlowCancelled` at its next operation.

## When something goes wrong

Everything the flow API raises is one tree under `FlowException`, in three branches by whose
fault it was, so a flow can catch one leaf, one branch, or all of it:

```
FlowException
├── FlowRuntimeError                  humanize refused something, or a budget ran out
│   ├── FlowNotFound · FlowRefError (ValueError) · FlowDefinitionError · FlowLoadConflict
│   ├── RequirementError              what was given does not meet the declaration; nothing ran
│   │   └── MissingRole · CapabilityMissing · PermissionTooNarrow · ResourceUnmet · HarnessMismatch
│   ├── CapabilityNotGranted          used what the role did not declare
│   ├── ParamsError (ValueError) · FlowDepthExceeded (RecursionError)
│   ├── BudgetExceeded
│   │   └── DurationExceeded (TimeoutError) · CostExceeded · OutputTokensExceeded
│   └── FlowCancelled · StateNotSerializable (TypeError) · OutworlderAway
├── HarnessError                      a coding agent CLI could not take the turn
│   └── HarnessNotInstalled · HarnessContended · HarnessThrottled · HarnessRefused
│       ModelUnavailable · HarnessMissing · HarnessSandboxed · HarnessKilled · HarnessDropped
│       HarnessUnrecoverable · OutputSchemaError (ValueError) · SessionError · UnsupportedOperation
└── EnvError                          an environment could not do what it was asked
    └── EnvUnavailable · EnvConnectionError (ConnectionError) · EnvCommandTimeout (TimeoutError)
        EnvFileNotFound (FileNotFoundError) · EnvPermissionDenied (PermissionError)
        WorktreeError · TempCloneBusy · ScratchError
```

Where a builtin already names the kind of failure, the leaf is that builtin too: `except
TimeoutError` catches a command that ran out of time and a budget whose duration did, and `except
FileNotFoundError` a file an environment does not have. A bug in the flow's own code is still the
`KeyError` it was.

| Harness leaf | The turn failed because |
| --- | --- |
| `HarnessNotInstalled` | the CLI is not installed where the agent works |
| `HarnessContended` | two turns reached one local store of the CLI at once |
| `HarnessThrottled` | the provider refused for too many requests, or a spent quota |
| `HarnessRefused` | the provider refused the credential |
| `ModelUnavailable` | the model is not served to this account, is retired, or never was |
| `HarnessMissing` | the CLI would not start |
| `HarnessSandboxed` | the CLI could not set up its own sandbox on this machine |
| `HarnessKilled` | the CLI died mid-turn |
| `HarnessDropped` | the connection to the CLI or its provider broke mid-turn |
| `HarnessUnrecoverable` | nothing a retry could change, for a reason none of the others name |

A loop that should carry on past one failed turn says so where the turn is:

```python
try:
    await agent.run(task, session=session)
except (HarnessThrottled, HarnessDropped):
    await asyncio.sleep(60)          # transient: go round again
```

and lets the rest — `HarnessRefused`, `ModelUnavailable`, a spent budget — end it, since a next
attempt at those fails the same way. Every exception here is raised with its message as its only
argument, so each pickles as itself and crosses a process boundary intact.

## Where flows live

`-f` takes a name or a path. A name is looked for nearest first:

| | |
| --- | --- |
| `local` | `.humanize/flows/*` — this project's own |
| `user` | `~/.humanize/flows/*` — yours, in every project |
| — | the ones humanize ships, and every [flowverse](#flowverses) there is |

Nearest wins, so a flow of your own may stand in for one of humanize's by taking its name — a
`.humanize/flows/chat/` is what `-f chat` runs *in that project*. Which is what `f` in the flow
menu is for: it copies the flow under the cursor into `.humanize/flows/`, whole, and from then on
that name means your copy. In Python that is `hmz.runtime.flowing.fork(name, into=None)`, which
copies a directory flow with its `skills/` and a single-file flow as a file, and refuses a name
you already have a copy of — in either shape — rather than writing over it. A copy that fails
partway leaves nothing behind, so the name is free to try again.

What a flow is **called** is another question, and one rule answers it for every place:
humanize's own are called by a bare name, and every other by the place it came from, which is
the one spelling nothing can stand in for. Your own two places are `local` and `user`:

| | |
| --- | --- |
| `chat` · `rlar` | humanize's own, wherever of its two places each is kept |
| `theirs/rlar` | one somebody else's flowverse holds |
| `local/chat` | this project's own |
| `user/chat` | yours, in every project |

So yours is listed beside humanize's rather than instead of it, `-f` takes either, and what each
was [set up to run](/reference/tui#what-it-remembers) is remembered apart — a flow of yours cannot
quietly inherit the agents or the params of the one it shares a name with.

A name no place answers to is taken as a path: a flow's directory, or a `.py` file to run as one
— `-f ./flows/mine`, `-f ./flows/mine.py` and `-f ./flows/mine/` all work. A directory whose name
starts with `_` is not a flow.

**A flow imports what travels with it.** A flow's directory is imported as a module named after
it, with the directory itself on `sys.path`, so `import _prompts` reaches the module beside the
flow's entry point by its plain name. Those names are the flow's for as long as a run uses it.

```sh
mkdir -p .humanize/flows && cp -r my_loop .humanize/flows/
hmz exec -f my_loop -a agent=claude/claude-opus-5:high -b cost=5 "fix the build"
hmz exec -f ./somewhere/else -a agent=claude/claude-opus-5:high -b cost=5 "fix the build"
```

## The skills a flow brings

The `skills/` inside a flow is what that flow works by, laid out the way every one of these CLIs
lays a skill out — a directory apiece, each holding a `SKILL.md`. A role says which of them its
sessions carry, with `_skills`:

```python
class Reviewer(Agent):
    _skills = ("review-notes", "https://github.com/humanfia/flowverse#writing-tests")
```

A name is a skill in the flow's own `skills/`; a git URL anything can clone, with `#<skill>`
after it, is one of that repository's `skills/*` — without the `#`, every skill it holds. Such a
repository is cloned under `~/.humanize/skills/` and fetched again the next time a run asks for
it, and the flow's own wins a name a repository also uses.

They are **mounted** onto every session of that role: copied where that harness reads a
project's own skills for as long as the session lives, and taken away again after. Nothing is
installed, and nothing the person at this machine installed is touched. A harness that reads no
project skills of its own carries none of this.

**A skill that is not there stops the call before its first turn**, with `FlowDefinitionError`
— one the flow's `skills/` does not hold, or a repository that cannot be fetched — rather than a
session an hour in that works without it. One fetched before and unreachable now runs on the copy
already here.

**`derive(skills=…)` gives a stretch of the flow fewer of them**: an agent whose sessions carry
only the ones named, which must be among the role's own. In a directory that holds [several
flows](#several-flows-in-one-file), the `skills/` is all of theirs, and each role names the ones
it carries.

## Flowverses

A flowverse is a git repository with a `flows/` directory in it: one directory per flow, each
holding the `__init__.py` that is the flow, whatever it imports beside it, and the `skills/` it
brings. It is cloned into `~/.humanize/flowverses/<name>/`, and every flow in its `flows/` is
then offered under that name. Nothing outside that directory is read, so the repository is free
to have a README, a pyproject and a test suite of its own without any of it being taken for a
flow. A flow of a flowverse calls its siblings by their bare name, and another flowverse's by a
[`git+` ref](#refs).

Three are always there:

| | |
| --- | --- |
| `official` | humanize's own: [`chat`](#the-flow-in-the-package) in the package, and [humanfia/flowverse](https://github.com/humanfia/flowverse) for everything else, fetched from its default branch |
| `local` | `.humanize/flows` where humanize is being run — this project's own |
| `user` | `~/.humanize/flows` — yours, in every project |

`official` is two places read as one. `chat` is in the package because an interface that has
never reached a network still has to have something to open talking to; everything else is in
the repository, where it can change without a release. Which of the two a flow is kept in is
humanize's business, so both are offered under the one name and every flow of humanize's is run
by a bare one. The qualified spelling — `official/rlar` — still resolves and pins a flow to the
place it came from, but nothing needs it.

`official` is listed before it has been fetched, and none of the three can be taken away. The
last two are places rather than repositories: nothing fetches them, and what is in one is
whatever you put there. They are listed as flowverses all the same, so that one rule says what a
flow is called and one list says where they are. `add`, `fetch` and `remove` all refuse them.

In the [interface](/reference/tui), `/flowverses` is where they live: `a` adds one, `r` fetches
the one under the cursor again, and enter says what one holds — and, past the flows, takes the
whole place away. [`Hmz().verses`](/reference/sdk#flowverses) is the same store, reached without
opening anything: `all`, `holds`, `add`, `fetch`, `remove`.

A flow is Python, and reading one means running it — so listing what a flowverse holds imports
the entry point of every flow in its `flows/`. Adding one is trusting that repository with this
machine, exactly as installing a package is.

Editing a flowverse's own copy does not keep: it is somebody else's repository, and fetching it
again takes what that repository says now. `f` on a flow copies it into `.humanize/flows/`, where
it is yours. See [Flowverses](/weaver/flowverses) for publishing one.

## The flow in the package

One, and it is the one an interface opens on. Everything else humanize offers is in the
flowverse, fetched the first time somebody wants it — a flow is content, and content that can
change without a release is content that keeps up; but a first run that had to clone before it
could say hello would be a first run that fails without a network.

| Flow | Roles | What it does |
| --- | --- | --- |
| [`chat`](/flows/chat) | an agent, and you | One agent, one session, and every line typed between turns is a turn of it. Talking to a coding agent with no loop around it. |

`chat` is special in two ways. It is **granted everything its harness serves**, whatever it
declares — steering, goals, every hook — since it talks to whichever harness it is given and so
cannot declare any one of them; no other flow is. And it **runs with no budget**, as
`Budget(cost=math.inf)`: a conversation ends when you stop typing. It keeps nothing: what was said
is the conversation, and the harness logged it.

## The official flowverse

Everything else humanize offers is in [humanfia/flowverse](https://github.com/humanfia/flowverse),
fetched as `/flow` first opens, or with `r` at `/flowverses`. [Flows](/flows/) is the same list with the
shape of each one drawn.

| Flow | Roles | What it does |
| --- | --- | --- |
| `ralph_loop` | `agent` | A fresh session every round, so nothing carries over but the repository. |
| `stateful_ralph` | `agent` | One session, re-sent the task every round. |
| `continue_loop` | `agent` | Sends the task once, then keeps nudging `continue`. |
| `goal` | `worker` | The task set once as the agent's [own goal](/weaver/goals). |
| `flame_chase` | `first_chaser`, `second_chaser` | Two agents take turns on the same task. Each reads the repository, not a history. |
| `rlar` | `actor`, `reviewer` | The actor works in one session and must remember; a fresh reviewer reads its work and must not. The review *is* the actor's next prompt, and the reviewer is also the one that says the task is finished. |
| `humanize1:gen-idea` | `drafter` | Opens a loose idea into a repo-grounded draft. |
| `humanize1:gen-plan` | `planner`, `analyst` | Turns that draft into a plan both sides have converged on. |
| `humanize1:rlcr` | `builder`, `reviewer`, `human` | Builds the plan under review until nothing is left to say. Run it in a git repository. |
| `parallel_flame_chase` | `coordinator`, `lane_1_actor_a` … `lane_3_actor_b`, `human` | A coordinator plans three isolated lanes; six actors alternate two to a lane and coordinate by durable report. |
| `parallel_flame_chase_git_pr` | `orchestrator`, `lane_1_actor_a` … `lane_3_actor_b`, `human` | The same three lanes, each in a clone of its own, landing work through pull requests that are merged only when an evaluator's receipt says they improve `main`. |
| `ralph_loop_agent_cleanup` | `agent`, `cleaner`, `human` | `ralph_loop`, with a cleaner that distills the workspace every few turns. Every agent role is declared with `SteeringAgentMixin`. |
| `flame_chase_agent_cleanup` | `first_chaser`, `second_chaser`, `cleaner`, `human` | `flame_chase`, with the same cleaner. |
| `recursive_lean_prover` | `worker`, `reviewer` | A Lean theorem proved by recursive decomposition, each node planned and built by `humanize1`'s phases in a worktree of its own. |
| `aot` | `writer`, `critic`, `human` | Writes a flow from a description, and lands it only once it has loaded, run on fakes and been read by a critic. |

A `human` role is [the person at the prompt](#the-person-at-the-prompt) and a `workspace` the
directory the run was started in, both filled by the runtime. None of them declares a budget of
its own: the run's `-b` is what stops the ones that do not stop themselves. Most of them [can be
picked up](#a-flow-that-can-be-picked-up), each keeping the little it honestly can in
`ctx.state` — the round it reached, whose turn is next, the review the actor is owed.

Their source is the best documentation of this API there is —
[humanfia/flowverse](https://github.com/humanfia/flowverse), or
`~/.humanize/flowverses/official/flows/` once it has been fetched. Read [Security](/user/security)
before starting any of them.

## Patterns

### Ralph: forget every turn

```python
while True:
    session = await agent.spawn(env=workspace)
    await agent.run(task, session=session)
```

A session a round, dropped when the round is over. That is the whole of a Ralph loop.

### Stateful: remember everything

```python
session = await agent.spawn(env=workspace)
while True:
    await agent.run(task, session=session)
```

Same agent, opposite behaviour. The flow decides, not the agent.

### Actor and reviewer

The reviewer must arrive fresh, so it gets a new session each round while the actor keeps one:

```python
working = await actor.spawn(env=workspace)
said = await actor.run(task, session=working)
while True:
    reading = await reviewer.spawn(env=workspace)
    review = await reviewer.run(REVIEW_PROMPT + said, session=reading)
    said = await actor.run(review, session=working)
```

Give the two the same model and effort and they are still two roles — which is the point: a
trace reads the actor's session and the reviewer's rounds as two.

### Asking a question rather than setting an agent to work

A loop that has to decide something — is this finished, does this plan belong to this
repository — asks for the [shape of the answer](/weaver/shapes) and reads a field, rather than
looking for a word at the end of a paragraph:

```python
class Review(BaseModel):
    """What one round's review comes to."""

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")


review = await reviewer.run(REVIEW_PROMPT + task, session=reading, output_schema=Review)
if review.done:
    return
```

The same call to [the person](#the-person-at-the-prompt) is a questionnaire: they are asked a
question per field, and the model is built out of what they typed.

### Carrying on past a failed turn

```python
try:
    await agent.run(task, session=session)
except HarnessError:
    session = await agent.spawn(env=workspace)   # a fresh session, and the loop goes round
```

It catches a turn that failed and nothing else — not a spent budget, which is a
`FlowRuntimeError`, and not a flow [being stopped](#stopping).

### Reading the repository between turns

```python
async def head() -> str:
    _, out, _ = await workspace.exec(["git", "rev-parse", "HEAD"])
    return out.strip()

before = await head()
await agent.run(task, session=session)
if await head() == before:
    ...  # the turn changed nothing
```

A workspace declared with `ShellEnvMixin` is all it takes, and the same line works on an
environment over ssh.

## Stopping

A flow ends when it returns — many of humanize's own never do, and are ended from outside:

- **Its budget**, which every run but `chat` has.
- **ctrl+c** twice in the interface, or once on a `hmz exec` command line.

A stop cancels the flow where it is waiting. The turn under way is interrupted — the CLI stops
spending — and the cancellation unwinds through the flow as it would through any coroutine, so a
`finally` runs and a `TaskGroup` cancels its siblings. Every session is closed on the way out,
and every copy and scratch directory is removed — unless the run is one that can be picked up,
which keeps what any of its flows made, and its journal, for `--resume`. What the turn was doing
is left where it got to: a stop that waited for a turn would not read as a stop.

## Testing a flow

A flow is tested the way it is run — through the engine, granted what it declared — with the
drivers underneath swapped for in-memory fakes, `hmz.runtime.flowing.fakes`: no coding agent,
no machine, no tokens, and no time.

```python
import pytest

from hmz.flows import Budget, CostExceeded
from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake


async def test_twice_reads_its_own_work_back():
    builder = FakeAgentDriver(reply="done")
    await run_fake("twice", "fix the build", agents={"builder": builder})
    assert builder.prompts == [
        "fix the build",
        "Now review what you just did, and fix anything wrong.",
    ]


async def test_the_loop_is_held_to_its_budget():
    agent = FakeAgentDriver(cost=1.0)
    with pytest.raises(CostExceeded):
        await run_fake("my_loop", "go", agents={"agent": agent}, budget=Budget(cost=2.5))
    assert len(agent.prompts) == 3        # the third turn finished; the fourth was refused
```

| | |
| --- | --- |
| `FakeAgentDriver(harness="claude", *, reply=…, cost=0, output_tokens=1, seconds=0, …)` | An agent answering every turn from a script: one answer, a list taken in order, or a function of the prompt (given `session=` and `output_schema=`). A mapping or JSON is read into the schema asked for; nothing answers `"ok"`, or the schema's defaults. It serves its harness's mixins, or `capabilities=`. `.prompts` and `.sessions` say what it was asked. |
| `FakeSession` | One of its sessions, handed to a reply function as `session=`, to reach the moments a real agent would: `tool(name, input)` fires `PRE_TOOL_USE` and `PERMISSION_REQUEST`, `ask(question, options)` fires `ASK_USER`, `notify` and `subagent` the rest, and `until_steered()` waits for a `steer`. Every turn fires `SESSION_START`, `USER_PROMPT_SUBMIT` and `STOP`, and a `STOP` hook that blocks keeps the turn going. |
| `FakeEnvDriver(files={…}, *, workdir="/work", run=…, refs=…, repo=True, …)` | A workdir in a dictionary: files, worktrees, copies and scratch directories. `exec` is answered by `run=` — a table of commands or a function — with `true`, `false`, `echo`, `cat`, `ls`, `sleep N` and `git rev-parse --is-inside-work-tree` answered by default, and anything else by exit status 127. `.files`, `.text(path)`, `.commands`, `.clones` and `.scratches` say what happened. |
| `FakeOutworlder(reply, *, away=False)` | The person outside the run, answering from a script, or away. `.asked` is what they were asked. |
| `run_fake(flow_or_ref, task, *, agents=, envs=, params=, budget=, outworlder=, local=, journal=, resume=)` | Runs a flow on fakes, with a fake for every required role nobody gave one for: an agent replying `"ok"`, an empty environment, an away outworlder, an empty workspace for `LocalEnv` roles. A `NotRequired` role nobody gave is left out, as it would be on a command line. A role may be given a driver, or just what its fake replies or holds. Unlimited by default; `journal=` and `resume=True` run it twice to test [picking it up](#a-flow-that-can-be-picked-up). |

A turn costs what the fake is told to, reported as a real one is, so budgets, usage and
sticky exhaustion behave as they would; a loop that never ends on its own is tested by giving it
a budget. `run_fake` loads a ref from where it is called, as `load` does. See [Testing a
flow](/weaver/testing-flows).
