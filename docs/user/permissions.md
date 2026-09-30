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

<div class="perm-scopes" role="img" aria-label="The default grant: local ALL inside user READ inside system READ, and online ALL beside them">
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
    <p><code>online</code> <b class="perm-all">ALL</b><span>web search and fetching</span></p>
  </div>
</div>

So by default an agent changes its workdir, reads around it, and searches the web, and
cannot change anything else of yours. An
outer scope never gets more than the one inside it, and `online` is either `NONE` or `ALL`.

## What the official flows declare

Most roles run at that default. These are the ones that do not:

| Flow | Role | Grant |
| --- | --- | --- |
| [`aot`](/flows/aot) | `critic` | `local=READ`, `online=NONE`: it reads the draft and never writes |
| [`parallel_flame_chase`](/flows/parallel-flame-chase) | every agent | `ALL` in every scope, `online` included |
| [`parallel_flame_chase_git_pr`](/flows/parallel-flame-chase-git-pr) | the lane agents | the default, with `user=ALL` |
| [`recursive_lean_prover`](/flows/recursive-lean-prover) | `worker`, `reviewer` | `local=ALL`, `user=ALL`, `system=READ`, `online=ALL` |

A flow's own page says what its roles are granted.

## How each CLI holds to it

Every grant below everything is enforced on the agent's process and on every command it runs.
Where a CLI can hold part of a grant itself, it is told to. humanize holds the rest from
outside:

- **`local`, `user` and `system`** are held by Landlock, a Linux kernel feature. An agent
  cannot write outside what its grant lets it write, or read outside what it lets it read.
  Every agent can still read what any program needs to run (the system's programs,
  libraries and certificates), and write its own settings and login, its sessions, and a
  temporary directory of its own.
- **`online` of `NONE`** cuts the network. The agent can still reach the hosts its model and
  its login are at, and nothing else: no web search, no package index, no host a command
  names. Nothing from outside reaches it either: a program it runs may serve on this
  machine's loopback address and on no other.

So the default grant is a real limit: an agent changes its workdir and nothing else of yours.

| Backend | `local`, `user`, `system` | `online` of `NONE` |
| --- | --- | --- |
| every CLI | <Badge type="tip" text="held by Landlock" /> | <Badge type="tip" text="cut but for its model" /> |
| `cursor-agent`, `mcode` | <Badge type="tip" text="held by Landlock" /> | <Badge type="danger" text="refused" /> |
| a CLI added over ACP | <Badge type="tip" text="held by Landlock" /> | <Badge type="warning" text="cut but for the hosts declared for it" /> |

A role whose `local` is `READ` or `NONE` also runs in its CLI's read-only mode, where the CLI
has one (every CLI but `dsh`, `mcode` and CLIs added over the Agent Client Protocol: those run
with no rung of their own, and a grant that writes nothing is what keeps them from writing). Where a CLI can
be told, `online` of `NONE` also switches its web tools off. Cursor's web search and fetch
cannot be switched off and run on Cursor's own servers, which it reaches for its model, so a
cut network would not stop them: a `cursor-agent` role with `online` of `NONE` is refused, and
needs `online` of `ALL`. MiniMax Code's web search runs on MiniMax's own service in the same
way, so an `mcode` role with `online` of `NONE` is refused too.

humanize knows nothing of a CLI you added over the Agent Client Protocol: not the hosts its
model is at, and not where it keeps its state. Declare both where it was added, or a role that
grants it `online` of `NONE` is refused (see [A CLI of your own](/reference/agents#a-cli-of-your-own)).

::: warning Where a grant cannot be held, the role does not start
humanize never runs an agent with more than its grant. A role is refused before it starts
(`HarnessSandboxed`) when:

- **this machine has no Landlock:** macOS, or a Linux kernel older than 5.13 or booted
  without it. A kernel older than 6.7 cannot cut the network, so `online` of `NONE` is
  refused there. So is a machine where humanize may not look into the programs it starts
  (inside a container with its default seccomp profile, or with Yama's `ptrace_scope` at 2
  or 3): it could not keep what they listen on to this machine.
- **the CLI would reach the web around the cut:** `cursor-agent` or `mcode` with `online` of
  `NONE`.
- **the work lands on another machine that has no Landlock:** a [container](/user/containers)
  or an ssh host whose kernel is too old, or a container whose seccomp profile refuses
  Landlock. Docker's own default profile allows it.

A container or an ssh host is held to the same grant as this machine. The agent's CLI still
runs here, fenced here. Every command it runs lands on the other machine and is fenced there,
around that machine's own workdir and `$HOME`. With `online` of `NONE`, those commands reach
no host at all, and a container under docker's default seccomp profile refuses such a role
for the reason above.

Only a grant of `ALL` everywhere is enforced by nothing, because there is nothing to hold.
:::

## Roles that check each tool

Some roles let the flow look at each tool call and refuse the ones it does not want: the
builder of [`humanize1:rlcr`](/flows/humanize1) and the worker of
[`recursive_lean_prover`](/flows/recursive-lean-prover) are two. Only these CLIs can fill such
a role:

| `claude` | `codex` | `kimi` | every other |
| --- | --- | --- | --- |
| <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="danger" text="refused" /> |

The agent sheet does not offer the others, and `hmz exec` refuses them before anything runs:

```
hmz exec: error: humanize1:rlcr: 'builder' needs PermissionRequestHookAgentMixin, which grok does not support
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

Copy the flow into your project: in `/flow`, walk to it and choose `copy <flow> here` below the flows. Then change the role's
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

@media (max-width: 560px) {
  .perm-scopes {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
