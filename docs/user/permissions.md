# Permissions

**This page is the weaver's** — whoever wrote the flow. What an agent may touch is declared
where the flow declares the agent, and nobody running the flow is asked about it: a reviewer
that may not write is a reviewer whichever CLI fills the role, so it is a thing about the work.

A flow declares a `Permission` on a role: four scopes, each saying how much of it the agent may
touch.

| Scope | What it is | May be |
| --- | --- | --- |
| `local` | the environment's workdir the session runs in | `NONE`, `READ`, `ALL` |
| `user` | the rest of the home directory of the user the agent runs as | `NONE`, `READ`, `ALL` |
| `system` | everything else on the machine | `NONE`, `READ`, `ALL` |
| `online` | the network: web search and fetching | `NONE` or `ALL` |

The scopes nest — `local >= user >= system` — and a wider scope may never be granted more than
a narrower one inside it. `Permission()` with nothing said is `local=ALL, user=READ,
system=READ, online=NONE`: an agent that may change its workdir, read around it, and not search
the web.

**Nothing is ever put to anybody for approval**, whatever the flow declares. Every session runs
at its CLI's nothing-asked mode — or, where a managed policy refuses that, at the most
permissive mode short of the model reviewing itself, with every request approved. A flow is
meant to run with nobody watching; what limits its agent is its `Permission`, and whatever
[hooks](/weaver/hooks) the flow hangs on it.

## Declaring one

Subclass the agent type the role is declared as, and set `_permission` on it:

```python
from hmz.flows import Agent, AgentCollection, Permission, PermissionKind


class Reviewer(Agent):
    _permission = Permission(local=PermissionKind.READ)


class Agents(AgentCollection):
    builder: Agent
    reviewer: Reviewer
```

A permission that does not nest, or an `online` of `READ`, is refused where it is written —
`Permission(...)` raises `ValueError`. Run it with the ordinary line — a CLI, a model and an
effort for each role:

```sh
hmz exec -f ./review -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:high \
    -b cost=20 "$(cat TASK.md)"
```

## A line cannot say it

`permission=` is not a setting of `-a`, and a line that writes one is refused before anything
runs, naming the flow as the place to say it. There is no row for it on the sheet an agent is
set up on, either. An agent is a CLI, an account and a model at an effort; what that agent is
allowed to do belongs to the flow driving it.

## A flow may only narrow

A flow can narrow an agent it holds — `derive` — and never widen it:

```python
careful = agents["builder"].derive(
    permission=Permission(user=PermissionKind.NONE, system=PermissionKind.NONE)
)
```

`careful` is the same agent with sessions that run under the narrower grant; asking for more
than the role was granted raises `CapabilityNotGranted`. A flow calling another hands on the
agents it holds, and each must hold **at least** what the called flow's role declares — an
agent held at `local=READ` handed to a role that needs `local=ALL` is refused with
`PermissionTooNarrow` before the called flow runs — and the called flow is then held to exactly
what it declared. So calling a flow you did not write is never how your reviewer comes to write.

## What each backend actually does

Every backend has a ladder of its own — coganchor names four rungs, `read-only`,
`workspace-write`, `auto` and `bypass`, in the words these CLIs use — and a flow's `Permission`
is read onto it:

| `local` | every backend but dsh and ACP CLIs | dsh, ACP CLIs |
| --- | --- | --- |
| `READ` or `NONE` | `read-only` | `bypass` |
| `ALL` | `bypass` | `bypass` |

- **`bypass` is each CLI's nothing-asked mode**: `danger-full-access` with approvals `never` on
  Codex, `yolo` on ZCode, and on Claude Code — whose `--dangerously-skip-permissions` a managed
  policy may turn off — `manual` mode with humanize answering every request yes.
- **`read-only` is the CLI's own read-only rung**: Claude Code's `plan`, Codex's read-only
  sandbox, a tool list with nothing that writes on the rest. It reads outside the workdir too.
- **`user` and `system` are not fenced — a known widening.** A session that may write its
  workdir may write anywhere its user can, whatever `user` and `system` say. Two of these CLIs
  have a sandbox that could fence it, and neither is used: both are bubblewrap, which cannot
  start on a machine that gives it no user namespace, and a fence here would be a flow that
  loses its shell wherever it runs in a container.
- **dsh and ACP CLIs can be held to nothing but `bypass`**, which is wider than asked for any
  permission below `ALL`.
- **`online`** switches the CLI's own web tools: on for `ALL`, off for `NONE` where the CLI can
  be told, and left as the CLI has it where it cannot — cursor-agent, pi, agy and ACP CLIs. A
  shell command the agent runs reaches the network whatever this says.

The whole table, backend by backend, is in
[Agents › The flow API's permission on each CLI](/reference/agents#the-flow-api-s-permission-on-each-cli).

**A Codex whose rules were set by somebody else runs a rung down rather than not at all.** Some
installations arrive with requirements — an enterprise policy on the account, a
`requirements.toml` on a machine whose platform packages Codex — and one that forbids
`danger-full-access` refuses every call asking for it. humanize asks again at `auto` instead:
the same freedom, with Codex asking before it reaches past the workspace and humanize granting
what it asks. It is found out once per agent. See
[Troubleshooting](/user/troubleshooting#codex-this-machine-will-not-run-an-agent-at-bypass-so-it-runs-at-auto).

**Claude Code's `bypass` runs the same on an account somebody else set up.** The flag that
skips the asking is one managed settings can turn off, and an account carrying
`disableBypassPermissionsMode` starts the turn at a mode where every edit is declined and it
ends successfully with the work not done. So humanize does not skip the asking: it runs the
agent at Claude's `manual` mode and answers each request itself, yes to whatever the account
leaves decidable, with the organisation's own hard `deny` list still enforced by Claude before
it asks.

## A worked pair

A reviewer that cannot touch the change it is reading, said once in the flow:

```python
class Reviewer(Agent):
    _permission = Permission(local=PermissionKind.READ)


class Agents(AgentCollection):
    actor: Agent
    reviewer: Reviewer
```

The actor runs at the default — its workdir to change, the rest to read — and does the work.
The reviewer can only look: the one thing this flow insists on, and the same whoever runs it,
on whichever CLI they have.

## What it does not bound

A permission bounds the **tools the agent reaches for**. It does not confine the process: an
agent that may write its workdir and runs a command which itself writes elsewhere has written
elsewhere. Read [Security](/user/security).

## Where a hook gets a say

A [hook](/weaver/hooks) on a permission request can refuse a tool and have the agent hear it —
which is how a flow narrows one thing rather than a whole scope. The role declares
`PermissionRequestHookAgentMixin` and the flow hangs the hook with `on_permission_request`:

```python
from hmz.flows import (
    Agent,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookParams,
    PermissionRequestHookResult,
)


class Builder(Agent, PermissionRequestHookAgentMixin): ...


async def no_force_push(params: PermissionRequestHookParams) -> PermissionRequestHookResult:
    pushing = "push --force" in str(params.input.get("command", ""))
    return PermissionRequestHookResult(allow=not pushing, reason="not on this branch")


agents["builder"].on_permission_request(no_force_push)
```

Its answer overrides the nothing-asked mode the agent runs at. Claude Code, Codex, Kimi Code
and ZCode serve the moment, and a role that declares it is refused any other CLI before
anything runs. While such a hook is hung, the CLI is started so that it asks: Codex keeps its
sandbox and runs with approvals `untrusted`, so every command but a known-safe read is put to
the hook; Kimi Code and ZCode run at their ask-and-approve mode, which asks about what the CLI
deems risky; Claude Code's `manual` mode asks already. Whatever the hook does not refuse is
granted.

## See also

- [Hooks](/weaver/hooks) — refusing one thing rather than a whole scope
- [Security](/user/security)
