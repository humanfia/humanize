# Permissions

What an agent may touch is decided by the flow, one role at a time. You choose the CLI and the
model that fill a role; what that role may touch comes with the flow, and neither `-a` nor the
agent sheet has a setting for it.

::: danger Nothing is put to anybody for approval
Every agent of every flow runs with approvals bypassed. No command or edit waits for a yes,
from you or from the model. What limits an agent is the grant on this page. Read
[Security](/user/security) before you run a flow you did not write.
:::

## What a role gets

A grant has four scopes, each `NONE`, `READ` or `ALL` (read and write). Here is what a role
gets when its flow says nothing:

<div class="perm-scopes" role="img" aria-label="The default grant: local ALL inside user READ inside system READ, and online NONE beside them">
  <div class="perm-box perm-system">
    <p><code>system</code> <b class="perm-read">READ</b><span>everything else on the machine</span></p>
    <div class="perm-box perm-user">
      <p><code>user</code> <b class="perm-read">READ</b><span>the rest of your home directory</span></p>
      <div class="perm-box perm-local">
        <p><code>local</code> <b class="perm-all">ALL</b><span>the workdir the session runs in</span></p>
      </div>
    </div>
  </div>
  <div class="perm-box perm-online">
    <p><code>online</code> <b class="perm-none">NONE</b><span>web search and fetching</span></p>
  </div>
</div>

So by default an agent changes its workdir, reads around it, and does not search the web. An
outer scope never gets more than the one inside it, and `online` is either `NONE` or `ALL`.

## What the official flows declare

Most roles run at that default. These are the ones that do not:

| Flow | Role | Grant |
| --- | --- | --- |
| [`chat`](/flows/chat) | `assistant` | the default, with `online=ALL` |
| [`aot`](/flows/aot) | `critic` | `local=READ`: it reads the draft and never writes |
| [`parallel_flame_chase`](/flows/parallel-flame-chase) | every agent | `ALL` in every scope, `online` included |
| [`parallel_flame_chase_git_pr`](/flows/parallel-flame-chase-git-pr) | the lane agents | the default, with `user=ALL` |
| [`recursive_lean_prover`](/flows/recursive-lean-prover) | `worker`, `reviewer` | `local=ALL`, `user=ALL`, `system=READ`, `online=ALL` |

A flow's own page says what its roles are granted.

## How each CLI holds to it

A grant is carried out by the CLI that fills the role, and not every CLI can be held to every
part of it:

| Backend | `local` of `READ` or `NONE` | `online` of `NONE` |
| --- | --- | --- |
| `claude`, `codex`, `grok`, `kimi`, `mimo`, `opencode`, `qwen`, `zcode` | <Badge type="tip" text="read-only" /> | <Badge type="tip" text="web tools off" /> |
| `agy`, `cursor-agent`, `pi` | <Badge type="tip" text="read-only" /> | <Badge type="warning" text="as the CLI has it" /> |
| `dsh` | <Badge type="danger" text="full access" /> | <Badge type="tip" text="web tools off" /> |
| a CLI added at `/providers` | <Badge type="danger" text="full access" /> | <Badge type="warning" text="as the CLI has it" /> |

A read-only agent can still read outside its workdir, and `local=NONE` runs the same as `READ`.

::: warning Two things no CLI fences
- **`user` and `system` are not enforced.** An agent that may write its workdir may write
  anywhere your user can, whatever those two scopes say.
- **`online` only switches the CLI's own web tools.** A shell command the agent runs reaches
  the network either way.

For a real fence, run the flow in a [container](/user/containers).
:::

## Roles that check each tool

Some roles let the flow look at each tool call and refuse the ones it does not want: the
builder of [`humanize1:rlcr`](/flows/humanize1) and the worker of
[`recursive_lean_prover`](/flows/recursive-lean-prover) are two. Only these CLIs can fill such
a role:

| `claude` | `codex` | `kimi` | `zcode` | every other |
| --- | --- | --- | --- | --- |
| <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="danger" text="refused" /> |

The agent sheet does not offer the others, and `hmz exec` refuses them before anything runs:

```
hmz exec: error: humanize1:rlcr: 'builder' needs PermissionRequestHookAgentMixin, which grok does not do
```

## On a machine somebody else manages

**Codex, where the organisation or the platform forbids full access.** The agent runs one step
down, and says so once:

```
codex: this machine will not run an agent at bypass, so it runs at auto
```

It keeps the same freedom: Codex asks before it reaches past the workspace, and humanize says
yes. See [Troubleshooting](/user/troubleshooting).

**Claude Code, on an account whose managed settings turn off bypass mode.** Agents run as
usual. humanize approves each request itself, and the organisation's own `deny` rules still
apply.

## Changing what a role may touch

Copy the flow into your project: press <kbd>f</kbd> on it in `/flow`. Then change the role's
grant in the copy, as [Writing a flow](/weaver/writing-a-flow) shows.

## See also

- [Security](/user/security)
- [Skills](/user/skills): the other thing a role brings with it
- [Agents › What an agent may do](/reference/agents#what-an-agent-may-do): the whole reference

<style>
.perm-scopes {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(9rem, 12rem);
  gap: 12px;
  margin: 20px 0 24px;
}

.perm-box {
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  padding: 10px 12px 12px;
  background: var(--hmz-panel-bg);
}

.perm-box p {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 8px;
  margin: 0 0 10px;
  line-height: 1.4;
}

.perm-box p span {
  flex-basis: 100%;
  font-size: 12.5px;
  color: var(--vp-c-text-2);
}

.perm-user {
  background: var(--vp-c-bg);
}

.perm-local {
  border-color: var(--hmz-accent);
  background: var(--vp-c-bg-soft);
}

.perm-local p,
.perm-online p {
  margin-bottom: 0;
}

.perm-online {
  align-self: start;
  border-style: dashed;
}

.perm-scopes b {
  padding: 0 7px;
  border-radius: 6px;
  font-size: 11.5px;
  letter-spacing: 0.04em;
}

.perm-all {
  background: var(--vp-c-tip-soft);
  color: var(--vp-c-tip-1);
}

.perm-read {
  background: var(--vp-c-warning-soft);
  color: var(--vp-c-warning-1);
}

.perm-none {
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-2);
}

@media (max-width: 560px) {
  .perm-scopes {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
