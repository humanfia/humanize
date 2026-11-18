<script setup>
import GrantScopes from '../.vitepress/theme/components/user-permissions/GrantScopes.vue'
</script>

# Permissions

What an agent may touch is decided by the flow, one role at a time. You choose the CLI and the
model that fill a role; what that role may touch comes with the flow, and neither `-a` nor the
agent sheet has a setting for it. Use this page to find out what a flow's agents may change
before you run it, to see the limit hold, and to change it in a copy of the flow.

::: danger Nothing is put to anybody for approval
Every agent of every flow runs with approvals bypassed. No command or edit waits for a yes,
from you or from the model. What limits an agent is the grant on this page. Read
[Security](/user/security) before you run a flow you did not write.
:::

## Try it

Ask an agent to write one file in its workdir and one outside it:

```sh
mkdir -p /tmp/perm-demo && cd /tmp/perm-demo
hmz chat -a claude/claude-haiku-4-5-20251001:low \
    "Use the Bash tool to run exactly these two commands, one call each, then report each one's result in one line: 1) echo hi > inside.txt   2) echo hi > ~/outside.txt"
```

```text
● 1. `echo hi > inside.txt` — Success: created inside.txt in the current directory (/tmp/perm-demo)
  2. `echo hi > ~/outside.txt` — Failed: permission denied writing to ~/outside.txt
```

`inside.txt` is there afterwards. `~/outside.txt` is not: the agent was never able to write
it, however it tried.

## Before you start

- **Linux with Landlock or bubblewrap, or macOS**: on Linux, a kernel of 5.13 or newer,
  booted with Landlock, and 6.7 or newer for a role that may not reach the network; or,
  where the kernel is older, [bubblewrap](https://github.com/containers/bubblewrap) (`bwrap`,
  the `bubblewrap` package) and a kernel that lets an ordinary user make a namespace. On
  macOS, any version: Humanize uses the Seatbelt sandbox built into it. See
  [Pitfalls](#pitfalls) for where a role is refused.
- The flow's page, which says what its roles are granted. Most say nothing, and run at the
  default below.

## What a role gets

A **grant** is three settings:

| Setting | What it is | A role that says nothing gets |
| --- | --- | --- |
| `preset` | where the agent may read and write: `read-only`, `workspace-write` or `danger-full-access` | `workspace-write` |
| `network` | whether it may reach the web: `True` or `False` | `True` |
| `granular` | rules of your own, one path each, laid over the preset | none |

Each preset is a short list of rules, and a rule gives one path, and everything beneath it, one
of three kinds of access: **write** (read and change), **read**, or **none**.

| Preset | Its rules | What the agent may do |
| --- | --- | --- |
| `read-only` | `read_only("/")` | read anything, change nothing |
| `workspace-write` | `read_only("/")`, `allow(".")` | read anything, change only its workdir |
| `danger-full-access` | `allow("/")` | read and change whatever your account may |

So by default an agent changes its workdir, reads around it, and searches the web, and cannot
change anything else of yours. A path starts with one of three anchors:

- **`.`** is the workdir the session runs in (and the directory a turn starts in, where that
  is elsewhere), and `./src` a path inside it.
- **`~`** is the home directory of the user the agent runs as, and `~/.ssh` a path inside it.
- **`/`** is the whole machine, and `/srv/data` a path on it.

Each is read when the session opens, on the machine it opens on. A path that starts any other
way, or holds a glob such as `*.env`, is refused when the flow is loaded. The rules are
`allow(path)` (write), `read_only(path)` (read) and `deny(path)` (none), all from `hmz.flows`.

Whenever the rules let the agent write its workdir `.` (`workspace-write`,
`danger-full-access`, or `read-only` with `allow(".")`), it also writes the temporary
directories every user shares, `/tmp` and `/var/tmp`, and the one `$TMPDIR` names, as Codex's
`workspace-write` does. They are held like the agent's own paths below: where one of them and a
rule's path nest, the deeper one decides, and at the same path the more permissive wins. So
`deny("/tmp")` does not take `/tmp` away, but `deny("/tmp/x")` does keep the agent out of
`/tmp/x`. A rule holds however the directory is spelled: on a Mac `/tmp` is a link to
`/private/tmp`, and `deny("/private/tmp/x")` keeps the agent out as well.
A rule that lets the agent write `~` writes whatever your user account may change, wherever it
is: a disk of yours mounted outside your home, a device your groups may use. The file
permissions are what hold it. Run as root, it is your home, those temporary directories and
`/run/user/0`.

`network` stands apart from the rules: `danger-full-access` with `network=False` changes
anything on the machine and reaches nothing on the web.

<GrantScopes />

### The last rule that matches wins

The rules are read in order: the preset's first, then the role's `granular` ones. For any path,
the last rule whose path is that path or holds it decides. A rule can so take something back
from a wider one before it, and give it back again:

```python
Permission(granular=(deny("~/.ssh"),))
```

reads everything and writes the workdir, as the preset says, and keeps out of `~/.ssh`
altogether, because `deny("~/.ssh")` comes last. The order matters:

```python
Permission(granular=(deny("./.env"), allow(".")))
```

does **not** keep the agent out of `.env`. `allow(".")` comes after `deny("./.env")` and holds
it, so it wins, and `.env` is writable again. Put the narrower rule last.

Every agent can still read what any program needs to run (the system's programs, libraries and
certificates), and write its own settings and login, its sessions, a temporary directory of
its own, the devices (the GPUs among them), and on Linux `/proc`, which CUDA writes to as it
starts. No rule reaches those. Everything else is held to the grant, for the agent and for
every command it runs.

## What the official flows declare

Most roles run at that default. These are the ones that do not:

| Flow | Role | Grant |
| --- | --- | --- |
| [`aot`](https://humanfia.ai/flows/aot) | `critic` | `preset="read-only"`, `network=False`: it reads the draft and never writes |
| [`flame_chasoid:parallel`](https://humanfia.ai/flows/parallel-flame-chase) | every agent | `preset="danger-full-access"` |
| [`flame_chasoid:parallel_git_pr`](https://humanfia.ai/flows/parallel-flame-chase-git-pr) | the lane agents | the default, with `allow("~")` |
| [`recursive_lean_prover`](https://humanfia.ai/flows/recursive-lean-prover) | `worker`, `reviewer` | the default, with `allow("~")` |

A flow's own page says what its roles are granted.

## Example: watch the default grant hold

This is the run from [Try it](#try-it), in full. A [chat](/user/chat) declares nothing, so its
one agent runs at the default, `workspace-write`, unless you pick [another preset for
it](/user/chat#permission): `.` is the directory you started in, the one
place it writes, and your home directory beyond it is only read.

```sh
mkdir -p /tmp/perm-demo && cd /tmp/perm-demo                 # ①
hmz chat -a claude/claude-haiku-4-5-20251001:low \
    "Use the Bash tool to run exactly these two commands, one call each, then report each one's result in one line: 1) echo hi > inside.txt   2) echo hi > ~/outside.txt"
```

```text
● assistant is working
● Bash(echo hi > inside.txt)                                              ②
● Bash(echo hi > ~/outside.txt)                                           ③
● 1. `echo hi > inside.txt` — Success: created inside.txt in the current directory (/tmp/perm-demo)
  2. `echo hi > ~/outside.txt` — Failed: permission denied writing to ~/outside.txt
✻ input 18 · output 413 · cache_read 34.7k · cache_write 7.3k · $0.01 · claude-haiku-4-5-20251001 · assistant
✻ Worked for 6s · assistant
```

```sh
ls inside.txt ~/outside.txt                                  # ④
```

```text
ls: cannot access '/home/you/outside.txt': No such file or directory
inside.txt
```

### What each part means

1. **The directory you start in** is the role's `.`, the only place the default grant lets it
   write. Start a flow in the project you want changed, never in your home directory.
2. **The write inside the workdir** runs, with no question asked of anybody.
3. **The write outside it** is refused by the kernel as `permission denied`. The CLI's own
   approval setting is bypassed; this is Humanize's limit, held around the agent and every
   program it starts, so a script the agent writes cannot get round it either.
4. **Checking the result yourself** is the way to be sure: only the file inside the workdir
   exists.

## Example: a role that checks each tool

Some roles let the flow look at each tool call and refuse the ones it does not want: the
builder of [`humanize1:rlcr`](https://humanfia.ai/flows/humanize1) and the worker of
[`recursive_lean_prover`](https://humanfia.ai/flows/recursive-lean-prover) are two. Only some CLIs can fill such a
role, and `hmz exec` checks before anything runs:

```sh
hmz exec -f humanize1:rlcr -p budget.cost=1 -a reviewer=codex/gpt-5.5:high \
    -a builder=grok/grok-4:high "add undo"                        # ①
echo $?
```

```text
hmz exec: error: humanize1:rlcr: 'builder' needs PermissionRequestHookAgentMixin, which grok does not support   ②
2                                                                                                             ③
```

### What each part means

1. **`builder=grok/…`** asks Grok Build to fill a role whose flow checks each of its tool
   calls.
2. **`needs PermissionRequestHookAgentMixin`** names what the role asks of its CLI: that it
   stop before each tool call for the flow to decide. Grok Build cannot.
3. **Exit status `2`**: refused before any agent started. Give the role one of the CLIs below.

| `claude` | `codex` | `kimi` | every other |
| --- | --- | --- | --- |
| <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="danger" text="refused" /> |

At the prompt, the agent sheet does not offer the others for such a role.

## Check that it worked

- A role that is refused says so before its first turn, as `hmz exec: error: …` or in red at
  the prompt. A run that starts is a run whose every grant is held.
- To see a limit yourself, ask an agent to write where its grant does not reach, as in the
  first example, and look for the file.

## How each CLI holds to it

Every grant below everything is enforced on the agent's process and on every command it runs.
Where a CLI can hold part of a grant itself, it is told to. Humanize holds the rest from
outside:

- **The preset and the rules** are held by Landlock, a Linux kernel feature, or where
  Landlock cannot hold them by bubblewrap, which gives the agent a filesystem made of what it
  is granted; on macOS by Seatbelt, the sandbox macOS is built with. An agent cannot write
  outside what its grant lets it write, or read outside what it lets it read. A rule that
  takes something back from a wider one (`deny("~/.ssh")` under `read_only("/")`) is held
  too: Seatbelt is told so in as many words, bubblewrap mounts an empty directory over it,
  and Landlock, which can only grant, is given everything beside it instead.
- **`network=False`** cuts the network. The agent can still reach the hosts its model and
  its login are at, and nothing else: no web search, no package index, no host a command
  names. On Linux nothing from outside reaches it either: a program it runs may serve on this
  machine's loopback address and on no other -- under bubblewrap, on a loopback of its own. Seatbelt cannot tell one address from another
  when a program starts to serve, so on macOS a program it runs may serve on any address,
  while it still reaches nothing but its model. A machine that reaches the network through a
  proxy of its own (`HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY`) still reaches the model through
  it.

| Backend | `preset` and `granular` | `network=False` |
| --- | --- | --- |
| every CLI | <Badge type="tip" text="held by Landlock, bubblewrap or Seatbelt" /> | <Badge type="tip" text="cut but for its model" /> |
| `cursor-agent`, `mcode` | <Badge type="tip" text="held by Landlock, bubblewrap or Seatbelt" /> | <Badge type="danger" text="refused" /> |
| a CLI added over ACP | <Badge type="tip" text="held by Landlock, bubblewrap or Seatbelt" /> | <Badge type="warning" text="cut but for the hosts declared for it" /> |

A role whose rules let it write nothing is also told so by its CLI's own controls: its
file-writing tools are withheld and its shell is kept, so it can still run a build or a test,
and the fence refuses any write the shell attempts. No CLI is put in a plan or asking mode for
it. Where a CLI cannot withhold its tools (`cursor-agent`, `mcode`, `omp`, `dsh` and CLIs added
over the Agent Client Protocol), it runs unattended and the fence alone keeps it from writing.
The list per CLI is in [Agents](/reference/agents#what-an-agent-may-do).
Where a CLI can be told, `network=False` also switches its web tools off.

Cursor's web search and fetch cannot be switched off and run on Cursor's own servers, which it
reaches for its model, so a cut network would not stop them: a `cursor-agent` role with
`network=False` is refused, and needs `network=True`. MiniMax Code's web search runs on
MiniMax's own service in the same way, so an `mcode` role with `network=False` is refused
too. The `aot` critic is such a role: give it another CLI.

Humanize knows nothing of a CLI you added over the Agent Client Protocol: not the hosts its
model is at, and not where it keeps its state. Declare both where it was added, or a role that
grants it `network=False` is refused (see
[A CLI of your own](/reference/agents#a-cli-of-your-own)).

## Variations

### Change what a role may touch

Copy the flow into your project: in `/flow`, put the cursor on it and press **Copy here** under
the list. Then change the role's grant in the copy, as [Writing a flow](/weaver/writing-a-flow)
shows. The copy runs as `@local/<flow>`.

### On a machine somebody else manages

**Codex, where the organisation or the platform forbids full access.** An agent whose grant
writes somewhere runs in Codex's `workspace-write` sandbox instead, and says so once:

```text
codex: this machine will not run an agent at danger-full-access, so it runs at workspace-write, where what it asks for is granted
```

It keeps the same freedom: Codex asks before it reaches past the workspace, and Humanize says
yes. The fence still holds where its writes land.

**Claude Code, on an account whose managed settings turn off bypass mode, or as root.** The
agent runs at `acceptEdits` instead, and says so once:

```text
claude: this account will not run an agent at bypassPermissions, so it runs at acceptEdits, where what it asks for is granted
```

It keeps the same freedom: Claude asks before what `acceptEdits` does not cover, and Humanize
says yes. The organisation's own `deny` rules still apply.

### Choose how this machine holds a grant

On Linux Humanize uses Landlock where it can hold the grant and bubblewrap otherwise. To pin one
of them, or to let Codex's own sandbox hold its grant, set `sandbox` in
[`settings.yaml`](/reference/settings#machine-settings) by hand:

```yaml
sandbox:
  backend: bwrap      # auto (the default), landlock or bwrap; read on Linux only
  native: [codex]     # CLIs whose own sandbox holds the grant instead
```

A pinned backend that cannot start here refuses the role rather than fall back to the other.

`native` is a trade, never a default. Codex's sandbox holds the commands the agent runs: what
they may write and whether they reach the network. It holds nothing of Codex itself, the MCP
servers and hooks it starts, or what anything reads -- Codex reads everything. Codex is the one
CLI it applies to; another named there is fenced as before. Codex still falls back to the fence
where its sandbox cannot say the grant (a rule that takes something back from a wider one),
where its sandbox will not start here, or where its work lands on another machine. Where it does
hold the grant, the agent says so once:

```text
codex: held to its permission by Codex's own sandbox, as sandbox.native asks: that holds the commands the agent runs, reading everything, and not Codex itself, its MCP servers or its hooks
```

### On another machine

A [container](/user/containers) or an [ssh host](/user/remote-execution) is held to the same
grant as this machine. Every command the agent runs lands on the other machine and is fenced
there, around that machine's own workdir and `$HOME`. Claude Code, Codex, Grok Build, Qwen
Code and pi are started in a home of their own where they run: here, or on that machine where its own CLI is driven, so
neither writes the settings of the machine it runs on
([Security](/user/security#what-a-flow-lets-its-agents-touch)). With `network=False`, those commands
reach no host at all. The agent's temporary directory is kept on the other machine at the path
it has here, so a command that names it, as Claude Code's every shell command does, finds it
there and ends with its own exit status.

## Pitfalls

::: warning Where a grant cannot be held, the role does not start
Humanize never runs an agent with more than its grant. A role is refused before it starts
(`HarnessSandboxed`) when:

- **this machine cannot fence:** a Linux kernel older than 5.13 or booted without Landlock
  that has no bubblewrap that starts either (no `bwrap`, or no namespace an ordinary user may
  make), or a Mac where Humanize itself runs inside another sandbox, which cannot start one
  of its own. A kernel older than 6.7 cannot cut the network with Landlock, so without
  bubblewrap `network=False` is refused there. So is a Linux machine where Humanize may not
  look into the programs it starts (inside a container with its default seccomp profile, or
  with Yama's `ptrace_scope` at 2 or 3) and bubblewrap cannot start: it could not keep what
  they listen on to this machine. A machine whose `sandbox.backend` pins a backend is refused
  where that backend cannot start.
- **a rule cannot be held here:** a rule that takes back part of a tree its preset grants,
  where this machine's sandbox cannot draw that line -- under bubblewrap, a rule for a path
  that is not there yet. Humanize refuses rather than run the
  agent without it.
- **the CLI would reach the web around the cut:** `cursor-agent` or `mcode` with
  `network=False`.
- **the work lands on another machine that cannot fence:** a [container](/user/containers)
  or an ssh host whose kernel is too old, or a container whose seccomp profile refuses
  Landlock. Docker's own default profile allows it. An ssh host that is a Mac fences with
  Seatbelt.

Only a grant that writes everything and reaches the network (`danger-full-access`, with no
rule that takes anything back) is enforced by nothing, because there is nothing to hold.
:::

- **An agent says `permission denied` and gives up.** That is the grant working. If the flow
  truly needs to write there, copy it and widen the role's grant, or start it in a directory
  that holds what it must change.
- **A `deny` that does nothing.** A rule after it that holds the same path wins. Put the
  narrowest rules last: `allow(".")` after `deny("./.env")` opens `.env` again.
- **A flow you did not write.** Its grants are its author's choice. Read its page, and its
  code in `/flow`, before you run it.

## Next steps

- [Security](/user/security): what the default grant protects, and what it does not
- [Skills](/user/skills): the other thing a role brings with it
- [Writing a flow](/weaver/writing-a-flow): declaring a grant of your own
- [Agents › What an agent may do](/reference/agents#what-an-agent-may-do): the whole reference
