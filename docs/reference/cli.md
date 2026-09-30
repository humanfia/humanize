---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# CLI reference

Every command, flag, environment variable, file and exit status. For a walk-through rather than
a lookup, start at the [quickstart](/#run-a-flow).

| Line | What it does |
| --- | --- |
| [`hmz`](#hmz) | Opens the [terminal interface](/reference/tui) in this directory. |
| [`hmz exec …`](#hmz-exec) | Runs one flow here, to its end, with no interface. |
| [`hmz --version`](#hmz) | Prints `hmz <version>`. |
| [`hmz --help`](#hmz) | Lists the commands. `hmz <command> --help` lists what one takes. |
| [`hmz internal …`](#hmz-internal) <Badge type="warning" text="not typed by hand" /> | The processes humanize spawns for itself. |

Everything after a command's name reaches that command untouched, `--help` included. A command
that does not exist (`hmz bogus`) prints the usage line and exits 2. `python -m hmz` is the
same command line.

## Who is reading

Every command writes for whoever is on the other end of its streams.

| Reader | What it gets |
| --- | --- |
| **A terminal** | Colour and layout. `hmz exec` draws the run as it happens, with a clock at the foot of the screen while a turn thinks. |
| **A pipe or a file** | The same lines, with no escape sequences. What each turn answered goes to **stdout** and the run itself to **stderr**, so `hmz exec … > answer.txt` keeps the answer. |
| **A program** | `hmz exec --json`: one JSON object per line on stdout, and nothing else there. See [Watching a run](#watching-a-run). |

`NO_COLOR`, `TERM=dumb` and `FORCE_COLOR` decide colour, in that order. See
[Environment variables](#output).

## `hmz`

```sh
hmz                  # opens the terminal interface
hmz --version        # hmz 0.1.0
hmz --help           # the commands
```

`hmz` takes no arguments. It opens on whatever this workspace was
[last set up to run](/reference/tui#what-it-remembers), and starts nothing: the first line you
send starts the flow.

The runs are held by a [process of their own](/reference/daemon), one per directory, so
closing the terminal does not end a run. `hmz` opens the interface in this process as one
[frontend](/reference/daemon#hosting) of the runs held in this directory, starting a host where
none is; every `hmz` there is a whole interface of its own on the same runs. The interface
holds the runs in this process instead when:

| Case | What is said |
| --- | --- |
| stdin or stdout is not a terminal | nothing |
| `HUMANIZE_DAEMON` is `off`, `0` or `no` | nothing |
| the runs cannot be held (no fork, no writable home, no socket) | `hmz: runs cannot be detached from the terminal (…), so they will run in this process instead` |

Runs held here by a daemon of an older humanize are not opened on: `hmz` says
`hmz: the runs in <dir> are held by an older humanize (pid <n>); stop it with that version` and
exits 1. It exits 1 too where the host lets go of the interface, saying why.

## `hmz exec`

Runs a [flow](/reference/flows) in the current directory, on the agents and environments it is
given, under a budget. Nobody is at a prompt: see [Nobody is at the
prompt](#nobody-is-at-the-prompt).

```
hmz exec -f|--flow <ref>
         [-a|--agents <role>=<cli>[@<provider>]/<model>:<effort>[,...]] [-a ...]
         [-e|--envs <role>=<backend>@<provider>[/<workdir>][,...]] [-e ...]
         [-p|--params <key>=<value>[,...]] [-p ...]
         -b|--budget <key>=<value>[,...] [-b ...]
         [-H|--harness adaptive|local|env|standalone:<env>]
         [--resume] [--json] [--] <task>
```

| Argument | |
| --- | --- |
| <span id="exec-flow"></span>`-f`, `--flow <ref>` | **Required.** The flow. See [Naming a flow](#naming-a-flow). |
| <span id="exec-agents"></span>`-a`, `--agents <spec>` | One agent per agent role the flow declares. See [Writing an agent](#writing-an-agent). |
| <span id="exec-envs"></span>`-e`, `--envs <spec>` | One environment per environment role. See [Writing an environment](#writing-an-environment). |
| <span id="exec-params"></span>`-p`, `--params <key>=<value>` | The flow's [params](/reference/flows#settings-of-the-flow-s-own). See [Writing params](#writing-params). |
| <span id="exec-budget"></span>`-b`, `--budget <key>=<value>` | **Required**, except for `chat`. What the run may spend. See [Writing a budget](#writing-a-budget). |
| <span id="exec-harness"></span>`-H`, `--harness <where>` | Where each agent's harness runs; `adaptive` if not given. Said once. See [Choosing where the harness runs](#choosing-where-the-harness-runs). |
| <span id="exec-resume"></span>`--resume` | Pick up the newest run of this flow here instead of starting afresh. See [Picking a run up](#picking-a-run-up). |
| <span id="exec-json"></span>`--json` | Write the run as NDJSON on stdout. See [Watching a run](#watching-a-run). |
| <span id="exec-task"></span>`<task>` | **Required.** What the flow is to do, as the text itself. Put `--` before it if it starts with a dash. |

Every flag but `-f` repeats, and each takes a comma-separated list: `-a actor=…,reviewer=…` and
`-a actor=… -a reviewer=…` are the same line. A comma splits two items only where a `key=`
follows it, so `-p tags=a,b,c` is one param.

### Examples

::: code-group

```sh [one agent]
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b output_tokens=10m "$(cat TASK.md)"
hmz exec -f chat -a assistant=claude/claude-opus-5:high "summarise CHANGELOG.md" > summary.txt
hmz exec -f ralph_loop -a agent=pi/openai-codex/gpt-5.5:high -b cost=5 "$(cat TASK.md)"
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 -- "--force is not a flag here"
```

```sh [two agents]
hmz exec -f rlar -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -b cost=20 "$(cat TASK.md)"
hmz exec -f flame_chase -a first_chaser=claude/claude-opus-5:max,second_chaser=codex/gpt-5.6-sol:max \
    -b duration=6h,cost=50 "fix the build"
```

```sh [accounts]
hmz exec -f flame_chase -a first_chaser=claude@anthropic/claude-opus-5:max \
    -a second_chaser=claude@deepseek/deepseek-chat:high -b cost=20 "fix the build"
```

```sh [params]
hmz exec -f humanize1:rlcr -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:xhigh \
    -p max=20 -b duration=12h,cost=100 "add undo"
```

```sh [your own flow]
hmz exec -f ./flows/mine -a coder=kimi/kimi-code/k3:swarmmax -b duration=2h "port this to asyncio"
hmz exec -f local/mine -a coder=claude/claude-opus-5:high -b cost=5 "port this to asyncio"
hmz exec -f 'git+https://github.com/humanfia/flowverse@main#rlar' \
    -a actor=claude/claude-opus-5:high,reviewer=codex/gpt-5.6-sol:high -b cost=20 "fix the build"
```

```sh [elsewhere]
hmz exec -f mine -a coder=claude/claude-opus-5:high -e trainer=ssh@gpu-box/home/me/repo \
    -b duration=1d "train it"
```

```sh [resume]
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b output_tokens=10m --resume "$(cat TASK.md)"
```

:::

### Naming a flow

| `-f` | Is |
| --- | --- |
| `<flow>` | A flow by the name it is offered under: humanize's own (`chat`) and the official flowverse's are bare. The flow named after its directory, else the only visible flow its module holds; otherwise an error listing the ones it does hold. |
| `<flow>:<sub>` | One of the [several flows a module holds](/reference/flows#several-flows-in-one-file), as `humanize1:rlcr`. |
| `<flowverse>/<flow>` | A flow pinned to the [flowverse](/reference/flows#flowverses) it came from. `local/<flow>` is this project's `.humanize/flows/`, `user/<flow>` is `~/.humanize/flows/`. |
| a path | A directory or file, taken outright: `./flows/mine`. |
| `git+https://…[@<rev>]#<flow>[:<sub>]` | A flow of a repository nobody has added, [pinned](/reference/flows#refs) at that revision. |

See [where flows live](/reference/flows#where-flows-live).

### Writing an agent

```
actor=claude/claude-opus-5:high
reviewer=claude@deepseek/claude-opus-5:high
coder=kimi/kimi-code/k3:swarmmax
assistant=cursor-agent/composer-2.5:auto
```

`<role>=<cli>[@<provider>]/<model>:<effort>`, one per agent role. The role is the name the flow
[declares the agent under](/reference/flows#how-many-agents-and-what-they-are-for); the order
roles are written in means nothing.

| Part | |
| --- | --- |
| `<cli>` | One of the twelve below, or a CLI of your own [added on the Accounts page of `/settings`](/reference/agents#a-cli-of-your-own), by the name it was added under. |
| `@<provider>` | The [account](/reference/providers) its turns run as: `claude@deepseek`. Left off, the CLI runs as you already run it. A CLI name never holds an `@`. |
| `<model>` | Whatever that CLI is asked for. Not checked against a list. It may hold slashes of its own (`kimi-code/k3`; pi, opencode, mimocode and MiniMax Code write `provider/id`), so the CLI is read from the front and the effort from after the last colon. |
| `<effort>` | A rung on that CLI's ladder, or `auto` for none: the CLI's own default. Any other word is refused before anything runs. The ladders are in the [Agents reference](/reference/agents). A CLI of your own has no ladder and takes any word. On Kimi Code, `swarm` in front (`swarmmax`) runs the turn as a fleet. |

| CLI | Also answers to | Needs |
| --- | --- | --- |
| `agy` | `antigravity` | |
| `claude` | `claude-code` | |
| `codex` | | |
| `cursor-agent` | `cursor-cli` | |
| `dsh` | `deepseek-harness` | `hmz[dsh]` |
| `grok` | `grok-build`, `grokbuild` | |
| `kimi` | `kimi-code` | `hmz[kimi]` |
| `mcode` | `minimax`, `minimax-code` | |
| `mimo` | `mimocode`, `mimo-code` | |
| `opencode` | | |
| `pi` | | |
| `qwen` | `qwen-code` | |

Refused before anything runs: a role given twice, a role the flow does not declare, a line with
no role, and a role the runtime fills. A role typed as an `Outworlder` is whoever is outside
the run, and is never given with `-a`.

What an agent may do is not part of `-a`. Its
[permission](/reference/flows#what-each-agent-may-do), its skills and what it must be able to
do are declared by the flow on the role's type, and a CLI that cannot serve them is refused
before anything runs.

### Writing an environment

```
repo=ssh@gpu-box/home/me/repo
repo=ssh@me@gpu-box:2222/~/repo
repo=ssh@gpu
data=local@/srv/data
box=docker@gpubox/srv/repo
box=docker@local/tmp/x
box=docker@gpubox
```

`<role>=<backend>@<provider>[/<workdir>]`, one per environment role the flow declares.

| Part | |
| --- | --- |
| `<backend>` | `local` (this machine), `ssh` (a host reached with ssh) or `docker` (a [container of its own](/reference/machines#docker-environments) on a docker daemon). |
| `<provider>` | For `ssh`, the name of an [environment provider](/reference/machines#environment-providers) you saved, reached with everything it says (login, port, key, jump host, options). Any other name is the destination as `ssh` takes it: `host`, `user@host`, `host:port` or an alias from your ssh config. For `docker`, the name of a docker provider you saved, or `local` for docker's default here with none saved; any other name is refused. Empty for `local`: `local@/path`. |
| `<workdir>` | Everything from the first `/` after the `@`. Absolute; `ssh@host/~/repo` is `repo` under the ssh login's home. For `docker`, a directory of the daemon's host, which the container is given at the same path; `~/` only where that daemon is this machine's. Left off, as in `ssh@gpu` or `docker@gpubox`, it is the workdir that provider was saved with; a provider saved without one, or a plain host, needs it. |

A role typed as a `LocalEnv` is the directory `hmz exec` was started in, and is never given
with `-e`. Most flows declare nothing else, so most lines have no `-e`. Every environment given
is probed before the flow is called: one that cannot be reached, or whose machine is smaller
than the role declares (fewer CPUs or GPUs, less memory), is refused. A `docker` one has its
container started then, sized by what the role declares, and is refused where its provider has
not that much left to hand out.

### Writing params

```
-p rounds=3
-p rounds=3,strict=false -p tags=a,b,c
-p 'limits={"cost": 5, "turns": 9}'
```

`<key>=<value>`, one field of the flow's `FlowParams` apiece. A value is read as the field's
type (`3` for an `int`, `false` for a `bool`) and otherwise as JSON. A field left out keeps its
default. A key the flow does not declare, a key given twice and a value the field refuses are
refused before anything runs, naming the field.

### Writing a budget

```
-b cost=20
-b duration=6h,output_tokens=10m
-b duration=1h30m -b cost=$5,graceful=false
```

At least one of the three limits, each key at most once across every `-b`. Whichever limit is
reached first stops the run. See [Every run has a budget](/features/allowances).

| Key | Written as |
| --- | --- |
| `duration` | Seconds (`90`, `1.5`); units of `w`, `d`, `h`, `m`, `s`, each at most once (`1h30m`, `2d`); ISO 8601 (`PT1H30M`); or `HH:MM:SS`. |
| `cost` | USD, with or without a `$`. `inf` is no limit. |
| `output_tokens` | A whole number (`200000`, `200_000`), or `k` and `m` (`200k`, `1.5m`). |
| `graceful` | `true`/`false`, `yes`/`no`, `1`/`0`, `on`/`off`. Whether the turn under way when a limit is reached is let finish (the default) or cut off. |

A line with no `-b` is refused, except for `chat`, which runs with no limit. A flow declares no
budget of its own.

A `cost` limit over a model nobody prices cannot stop anything. The run starts anyway, and says
so first: `hmz exec: nobody lists a price for <model>, so cost=5 cannot stop what it spends`.

### Choosing where the harness runs

```
-H adaptive
-H env
-H standalone:ssh@gpu-box
-H standalone:docker@local/srv/scratch
```

The **harness** is an agent's CLI and whatever supervises it. For work on this machine it is
here whatever `-H` says, except `standalone`. For work in an `ssh` or `docker` environment:

| `-H` | The harness runs |
| --- | --- |
| `adaptive` *(default)* | On the environment's machine where the agent's CLI is installed there (and can be fenced to the role's permission), and here otherwise -- here too for a role with a hook hung that gates its tools, which a CLI on another machine can only watch. Decided once per role and machine. |
| `local` | Here, supervised, reaching the environment through the anchor. |
| `env` | On the environment's machine, as the CLI installed there. Refused, naming the machine and the line that installs the CLI, where it is not. |
| `standalone:<env>` | On a machine of its own, reaching the environment through the anchor. `<env>` is spelled as `-e` spells one after `<role>=` (`ssh@HOST[/DIR]`, `docker@PROVIDER[/DIR]`), or is a saved environment provider's name. The CLI must be installed there. |

A machine left without a directory, and saved with none, is worked in at the login's home over
ssh, and at `~/.humanize/harness` on docker's default here (`docker@local`); any other daemon
needs one said. A docker one is a container of its own,
started from the provider's image and taken down with the run. See
[Remote execution › Where the harness runs](/reference/remote-execution#where-the-harness-runs).

Where each session's harness went is written into the run's epic beside the session, as
`local`, `env` or `standalone:<target>`.

### Watching a run

At a terminal:

```console
$ hmz exec -f rlar -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high -b cost=20 "fix the build"
● actor is working
● Bash(pytest -q tests/)
● I fixed add() and the tests pass.
✻ input 40.0k · output 1.2k · $0.61 · claude-opus-5 · actor
✻ Worked for 74s · actor
```

The `✻` line under a turn is what it cost: tokens by kind, the money where the model is
[priced](/user/tally), then the model and the agent. An unpriced model shows no money rather
than `$0.00`. An agent holding several conversations says which one a turn is in:
`● actor is working · conversation 2 of 3`. The clock at the foot of the screen is drawn only
where escapes are wanted; `NO_COLOR` and `TERM=dumb` mean no clock.

With `--json`, one object per line, flushed as each is written. Anything the flow prints goes
to stderr for the duration, so nothing else reaches stdout:

```console
$ hmz exec -f chat -a assistant=claude/claude-opus-5:high --json "say hello" | jq -c 'select(.kind == "result")'
{"at":1789026740.6,"agent":"assistant","cli":"claude","model":"claude-opus-5","session":"1d1ff959","kind":"result","text":"Hello.","whose":"","tokens":{"claude-opus-5":2080},"spent":{"input":2000,"output":80}}
```

Every object carries every key:

| Key | |
| --- | --- |
| `at` | When it was said, as a Unix timestamp. |
| `agent` | Which agent, by the role the flow declared it under. |
| `cli`, `model` | The backend and model it was said on. |
| `session` | The backend's id for the conversation, or `""` before it has named one. |
| `kind` | What it is. See the table below. |
| `text` | The words. |
| `whose` | For `subagent` and `subagent-ends`, the backend's id for that sub-agent; `""` otherwise. |
| `tokens` | On a `result`, what the turn cost per model, from a backend that says. `{}` otherwise. |
| `spent` | The same cost by kind of token: `input`, `output`, `cache_read`, `cache_write`, `reasoning`, as far as the backend reports them. |

| `kind` | Means |
| --- | --- |
| `begins`, `ends` | A turn starts, a turn is over. |
| `text` | The agent talking. |
| `reasoning` | The agent thinking aloud. |
| `tool` | The agent using a tool. |
| `subagent`, `subagent-ends` | An agent this one started of its own, and its end. |
| `asks` | The agent stopping to ask its user something. Under `hmz exec` nobody answers. |
| `took` | A line put into the running turn is now in front of the model. `text` is that line. |
| `notice` | humanize, not the agent: a rate limit being waited out, another account taking over, a turn cut off or ended for saying nothing. |
| `failed` | The turn failed. `text` is why. |
| `result` | The answer the turn ends on. Carries `tokens` and `spent`. |

### Nobody is at the prompt

A run of `hmz exec` has its [outworlder](/reference/flows#the-person-at-the-prompt) away the
whole time. A flow that asks the person something gets `""`, or the answer a schema's defaults
make, or `OutworlderAway` where a field has no default. An agent that stops to ask is told
nobody answered and carries on.

### What is refused before anything runs

Everything that can be checked before the first turn is. Each refusal is one line on stderr and
exit status 2, with nothing started:

| Refused | Says |
| --- | --- |
| no such flow | `nosuch: no flow is called 'nosuch', and it is not a path` |
| a role the flow does not declare | `chat has no agent role 'helper'; available roles are 'assistant'` |
| a required role left out | `rlar needs an agent for 'reviewer'; specify each with -a ROLE=CLI/MODEL:EFFORT` |
| a role the runtime fills | `<flow>: '<role>' is assigned automatically by the runtime and cannot be set with -a` |
| a CLI that cannot do what the role needs | `<flow>: '<role>' needs SteeringAgentMixin, which grok does not support` |
| a role typed as another CLI's own | `<flow>: '<role>' requires codex, but got claude` |
| an effort off the ladder | `assistant=claude/claude-opus-5:turbo: claude cannot be asked to think at 'turbo'; expected one of ultracode, max, xhigh, high, medium, low` |
| no `-b` | `rlar requires a budget: specify with -b duration=...,cost=...,output_tokens=...` |
| an `-H` that is none of the four | `-H 'somewhere': expected adaptive, local, env or standalone:<backend>@<provider>[/<workdir>]` |
| params the flow refuses | the flow's own validation error, naming the field |
| an environment short of its role, or unreachable | why, naming the role |
| a skill a role names that cannot be found or fetched | why, naming the skill |
| `--resume` with nothing to pick up | [see below](#picking-a-run-up) |

Each is prefixed `hmz exec: error: `. A line argparse cannot read (an unknown flag, no `-f` or
task, an `-a`, `-e`, `-p` or `-b` that is not one) prints the usage line first:

```console
$ hmz exec -f rlar -a actor=opus -b cost=20 "fix the build"
usage: hmz exec [-h] -f FLOW [-a ROLE=SPEC[,...]] [-e ROLE=SPEC[,...]]
                [-p KEY=VALUE[,...]] [-b KEY=VALUE[,...]] [-H WHERE]
                [--resume] [--json]
                task
hmz exec: error: -a 'actor=opus': expected [NAME=]CLI[@PROVIDER]/MODEL:EFFORT
```

Whatever a flow does as it is imported is the flow's own, and fails as it would anywhere.

### Picking a run up

`--resume` carries on the newest run of the same flow in this workspace that [can be picked
up](/reference/flows#a-flow-that-can-be-picked-up) and got as far as writing its journal
(`resume.jsonl`, inside the run's [epic](/reference/tracing#epics)). The flow at the top picks
up what it kept, and each flow it calls picks up where it is called again with the same task,
agents, environments and params. The line still gives `-a`, `-e`, `-p` and a fresh `-b`, so an
agent that changed is a flow called afresh from there down. The new run is an epic of its own
and records which epic it `picked_up` from.

| Refused | Says |
| --- | --- |
| the flow is not resumable | `chat does not support resuming, so there is no run to resume` |
| no run of it here left a journal | `<flow> has no run to resume here: none saved any progress` |

Without `--resume` every run starts afresh.

A run its budget stops lets the turn under way finish (unless `graceful=false`), prints
`hmz exec: stopped -- …` naming the limit, and exits 0. A resumable one carries on from there
with `--resume` and a fresh `-b`.

## `hmz internal` <Badge type="warning" text="not typed by hand" /> {#hmz-internal}

```
hmz internal COMMAND [ARGS...]
```

The command lines humanize starts its own processes with. You meet them in `ps`, in a CLI's
hook or MCP configuration, or in an error; you do not type them. Each still runs when typed,
which is what `hmz internal anchor --check` is for.

| Command | |
| --- | --- |
| [`hmz internal anchor`](#hmz-internal-anchor) | A turn whose work lands on another machine; under `serve`, the half that lands it. |
| [`hmz internal cred`](#hmz-internal-cred) | A program run with its credential files answered from an account's own directory, and its sessions from where humanize keeps them. |
| [`hmz internal fence`](#hmz-internal-fence) | A program walled in to the paths and hosts its flow's permission grants. |
| [`hmz internal hook`](#hmz-internal-hook) | One moment of a coding agent's hook table, carried to the flow it belongs to. |
| [`hmz internal tools`](#hmz-internal-tools) | A coding agent's tool calls, carried to the process whose callbacks they are. |

`hmz internal --help` lists these five. With no command, or one it does not know, it prints its
usage and exits 2.

### `hmz internal anchor`

Runs a coding agent on this machine whose work lands on another. humanize spawns it for every
such turn. See [Remote execution](/reference/remote-execution).

```
hmz internal anchor [options] AGENT [ARGS...]
```

Everything after the agent's name is the agent's own.

| Flag | Default | |
| --- | --- | --- |
| `--target URL` | `$HUMANIZE_TARGET`, else `local` | `ssh://HOST`, `docker://CONTAINER[@ENDPOINT]`, `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT`, or `local[:DIR]`. |
| `--harness WHERE` | `$HUMANIZE_HARNESS`, else `local` | Where the agent process and the supervisor tracing it run: `local`, `same` (wherever `--target` is), or a target of their own. See [where the harness runs](/reference/remote-execution#where-the-harness-runs). |
| `--broker HOST` | `$HUMANIZE_RENDEZVOUS`, else this machine's outward address | Where the two halves dial to be introduced, when `--harness` and `--target` name different machines. |
| `--workspace PATH` | this directory | The project directory as it exists on the target. |
| `--chdir PATH` | `--workspace` | Where inside the workspace the agent starts, as the target names it. |
| `--remote-path PATH` | `--workspace` | Where the workspace really lives on the target, if not at the same path. |
| `--shadow PATH` | `$HUMANIZE_SHADOW`, else `--workspace` | The mirror directory, on whichever machine the harness runs. A harness elsewhere given none gets one under that machine's cache, kept between turns. |
| `--local-path PATH` | — | Keep this path on this machine even inside the workspace. Repeatable. |
| `--local-exec PATH` | — | Run programs under this path here rather than on the target. Repeatable. |
| `--redirect FROM=TO` | — | Answer this path (a file, or everything under a directory) with that one, kept local. What a turn under a [provider](/reference/providers) is given. Repeatable. |
| `--private NAME` | — | Keep this variable out of what the agent's commands run with on the target. Repeatable. |
| `--net {local,remote}` | `local` | Where the agent's own TCP connections go. Commands it spawns always use the target's network. |
| `--net-allow HOST[:PORT]` | — | With `--net remote`, keep connections to this host local. Repeatable. |
| `--token TOKEN` | `$HUMANIZE_TOKEN` | Shared secret a `tcp://` target expects. |
| `--force` | off | Use the mirror directory even if it already holds unrelated files. |
| `--native` | off | Run the CLI installed **on the target** instead of supervising one here: no mirror, nothing traced. The mirror flags above do nothing under it. |
| `--hush NAME` | — | With `--native`, run the CLI on the target without this variable, whoever set it there. Repeatable. |
| `--project NAME=DIR` | — | With `--native`, put this directory of credentials on the target for the turn and set `NAME` to where it landed. Readable only by the target's user; removed after. Repeatable. |
| `--carry DIR=PATH` | — | With `--native`, put this directory into the target's workspace at `PATH` for the turn. How a flow's own [skills](/reference/flows#the-skills-a-flow-brings) get there. Nothing already at `PATH` is overwritten. Repeatable. |
| `--installs LINE` | — | With `--native`, the line that installs this CLI, said where the target has none. |
| `--fence JSON` | — | Hold the agent to this [fence](/reference/agents#the-fence), on both machines: the agent process here by this machine's Landlock, and every command it runs by the target's, drawn again from the fence's levels around the target's own workdir and home. A fence built path by path, or one with a harness elsewhere, exits 2. A target that cannot hold it refuses the session. |
| `--check` | off | Connect, report what was found, and exit without running anything. |
| `--log-level {debug,info,warning,error}` | `$HUMANIZE_LOG`, else `warning` | Logging to stderr. |

Settings no session could run under (an unreadable target, a `--net` that is neither, a
credential bound for something that is not a variable) exit 2. A `--native` session whose CLI
the target lacks exits **127**. Otherwise it exits with the agent's own status.

```sh
hmz internal anchor --target ssh://build-box claude
hmz internal anchor --target ssh://gpu-01 codex exec "run the test suite"
hmz internal anchor --target docker://build-container --workspace /srv/project claude
hmz internal anchor --native --target docker://build-container --remote-path /srv/project claude
hmz internal anchor --harness same --target ssh://build-box --workspace /srv/project claude
hmz internal anchor --harness ssh://runner --target ssh://build-box --workspace /srv/project claude
hmz internal anchor --check --target ssh://build-box
```

### `hmz internal anchor serve`

The other half of a session: replays on this machine what an `hmz internal anchor` elsewhere
asks of it. Needs only a POSIX system and a recent `python3`: no root, no compiler.

```
hmz internal anchor serve --export VIRTUAL[:REAL] (--stdio | --listen [HOST:]PORT | --peer TICKET@HOST:PORT) [--token TOKEN]
```

| Flag | |
| --- | --- |
| `--export VIRTUAL[:REAL]` | **Required, repeatable.** Expose a directory: `VIRTUAL` is the path seen by the agent, `REAL` where it is here. |
| `--stdio` | Serve one session over stdin/stdout. What a bootstrapped target runs. |
| `--listen [HOST:]PORT` | Serve TCP connections. A bare port listens on `127.0.0.1`. |
| `--peer TICKET@HOST:PORT` | Serve one session through the rendezvous server using this ticket. humanize writes this one. |
| `--token TOKEN` | Shared secret required from clients. Defaults to `$HUMANIZE_TOKEN`. |
| `--log-level` | As for `hmz internal anchor`. |

One of `--stdio`, `--listen` and `--peer` is required, and only one.

A command sent with a fence runs under this machine's own `hmz internal fence`, drawn around
the exported directories, this user's `$HOME` and this machine's minimum. On a machine that has
no Landlock, the command is refused and never runs. The machine says whether it can fence when
a client connects.

::: danger
Listening on anything but loopback without `--token` is refused. An open port is a shell on
that machine. Read [Security](/user/security).
:::

```sh
hmz internal anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

### `hmz internal anchor rendezvous`

Where the two halves of a session are introduced when neither can dial the other. humanize
holds one inside itself for the sessions it starts; this runs one on its own, on a machine both
halves can reach.

```
hmz internal anchor rendezvous [--listen [HOST:]PORT] [--punching SECONDS]
```

| Flag | |
| --- | --- |
| `--listen [HOST:]PORT` | The address to listen on. Defaults to every interface, any free port. |
| `--punching SECONDS` | How long two halves get to reach each other before the broker carries the bytes itself. Defaults to 4. |
| `--log-level` | As for `hmz internal anchor`. |

The address it landed on is printed on stderr. Pairing is by ticket, a 128-bit secret, so there
is no token.

```sh
hmz internal anchor rendezvous --listen 0.0.0.0:9001
```

### `hmz internal cred`

```
hmz internal cred (--map | --keep) FROM=TO [...] -- COMMAND [ARGS...]
```

Runs a program with some of its paths answered by others, and exits with its status. What a
turn or a login under a [provider](/reference/providers) is spawned as, and every turn whose
sessions humanize [keeps](/reference/providers#where-sessions-are-kept): the program
runs here, on this terminal, and the syscalls that name one of its credential files are handed
a path inside that account's directory instead, and those naming its sessions one inside the
directory they are kept in.

| Flag | |
| --- | --- |
| `--map FROM=TO` | **Repeatable.** Answer this path (a file, or everything under a directory) with that one, a read with a copy held in memory. |
| `--keep FROM=TO` | **Repeatable.** The same, never with a copy, making where it goes as the program writes. `FROM` may hold a glob in any of its names. |
| `--` | Ends the flags. Everything after it is the program and its arguments. |

A line with nothing to map or keep, or nothing to run, is a usage error. A program that could not be
supervised exits 1 rather than running unsupervised as whoever is at this machine.

### `hmz internal fence`

```
hmz internal fence --policy=JSON -- COMMAND [ARGS...]
```

Runs a program inside a [fence](/reference/agents#the-fence), and exits with its status. What
every turn of an agent held to a permission it does not grant in full is spawned as, outermost
of whatever else wraps the turn: the program runs here, on this terminal, walled in by Landlock.
Where the fence cuts the network, a seccomp filter refuses every socket but TCP and Unix ones,
and the program is handed a proxy on loopback (`HTTPS_PROXY` and the rest, with `NO_PROXY`
emptied) that passes only the fence's hosts. Its `TMPDIR` is the fence's scratch directory.

| Flag | |
| --- | --- |
| `--policy JSON` | **Required.** The fence, as JSON, or `@PATH` for a file holding it. |
| `--` | Ends the flags. Everything after it is the program and its arguments. |

A line with nothing to run is a usage error. A fence this machine cannot put up (no Landlock, or
a kernel that cannot cut TCP where the network is cut) exits 126 without running the program,
rather than running it unfenced.

### `hmz internal hook`

```
hmz internal hook --at <socket>
```

Carries one call of a coding agent's [hook table](/reference/agents#hooks) to the flow whose
moment it is, and the verdict back: reads the call on stdin, sends it to the flow's socket,
writes the answer to stdout. humanize writes this line into the CLI's hook table and the CLI
spawns it once per moment.

| Flag | |
| --- | --- |
| `--at PATH` | **Required.** The unix socket the flow is listening on. |

It exits 0 whatever the flow said, and never with the status a CLI reads as the hook refusing.
A socket that is not there lets the tool through and says so on stderr.

### `hmz internal tools`

```
hmz internal tools --at <socket>
```

Carries the tool protocol between a coding agent and the process whose callbacks were offered
to it as tools (coganchor's `session.offers([...])`): stdin to that process's socket, the
answers back to stdout. The flow API offers no callbacks as tools, so a flow never has one
spawned; a flow reaches its own code from inside a turn [through hooks](/weaver/tools).

| Flag | |
| --- | --- |
| `--at PATH` | **Required.** The unix socket the toolbox is served on. |

A socket that is not there exits 1, which the CLI reads as tools being unavailable.

## Environment variables

### humanize's own

| Variable | |
| --- | --- |
| `HUMANIZE_HOME` | Where humanize keeps what outlives a run. Defaults to `~/.humanize`. Every path under [Files](#files) moves with it. |
| `HUMANIZE_DAEMON` | `off`, `0` or `no`: the interface holds its runs in its own process rather than [apart from the terminal](/reference/daemon). Anything else, empty included, holds them apart. |
| `HUMANIZE_NAME` | What a frontend of a [host](/reference/daemon#hosting) is called, ahead of `@tui` or `@sdk`. Defaults to your login. |
| `HUMANIZE_SENTRY` | `on` or `off`: answers the [reporting](/user/reporting) question for this process without writing anything down. |
| `HUMANIZE_WATCHDOG` | Seconds a turn may say nothing before [the watchdog looks at it](/reference/agents#when-a-cli-stops-answering), overriding every backend's own. `0` or less turns it off. |
| `HUMANIZE_SESSIONS` | `off`, `0` or `no`: every CLI keeps its sessions in its own home, and a turn is supervised only for an [account](/reference/providers). Anything else keeps them in the run, or in `~/.humanize/sessions/` for an agent driven by hand. |
| `HUMANIZE_PRICES` | Where model prices come from: a URL or a path to read instead of [OpenLLMPrices](https://openllmprices.com/). `off`, `0`, `no`, `none` or empty: fetch nothing and use what is kept. |
| `HUMANIZE_SHADOWS` | Where the mirrors coganchor has made are recorded. Defaults to `~/.cache/humanize/shadows`. |
| `HUMANIZE_SSH_REUSE` | `0`, `no`, `false` or empty: open a fresh `ssh` per command instead of sharing one connection per host. Set it for a host whose sshd refuses multiplexing. The shared sockets live under `$XDG_RUNTIME_DIR`, else the temporary directory. |
| `HUMANIZE_RENDEZVOUS_PORT` | The port humanize's own broker listens on, for a firewall that needs one in advance. Any free port by default. |

### For `hmz internal anchor`

| Variable | Default for |
| --- | --- |
| `HUMANIZE_TARGET` | `--target` |
| `HUMANIZE_HARNESS` | `--harness` |
| `HUMANIZE_SHADOW` | `--shadow`: how a harness on another machine is told which directory to mirror into. |
| `HUMANIZE_RENDEZVOUS` | `--broker` |
| `HUMANIZE_TOKEN` | `--token`, for `anchor` and `anchor serve` |
| `HUMANIZE_LOG` | `--log-level`, for `anchor` and `anchor serve` |

Set **inside** an anchored agent, so that it and what it spawns can tell:

| Variable | |
| --- | --- |
| `HUMANIZE` | The version of the half that launched it. |
| `HUMANIZE_TARGET` | The target its work lands on. |
| `HUMANIZE_WORKSPACE` | The workspace as the target has it. |

### Backend homes

Where each CLI keeps its settings, skills, credentials and -- for a session humanize did not
run -- its sessions. humanize reads them wherever it reads a CLI's own files: the skills an
agent is listed with, the log a failed turn is explained from, and the sessions a trace gathers
beside the ones its [epics](/reference/tracing#epics) keep. A home that does not exist is
skipped. The sessions a turn opens are kept by humanize instead, laid out the same way, under
the path the variable moves them to.

| Variable | CLI | Default |
| --- | --- | --- |
| `CLAUDE_CONFIG_DIR` | Claude Code | `~/.claude` |
| `CODEX_HOME` | Codex | `~/.codex` |
| `CURSOR_CONFIG_DIR` | Cursor Agent | `~/.cursor` |
| `DSH_HOME` | DeepSeek Harness | `~/.dsh` |
| `GROK_HOME` | Grok Build | `~/.grok` |
| `KIMI_CODE_HOME` | Kimi Code | `~/.kimi-code` |
| `MINIMAX_DATA_DIR` | MiniMax Code | `~/.minimax` |
| `PI_CODING_AGENT_DIR` | pi | `~/.pi/agent` |
| `QWEN_HOME` | Qwen Code | `~/.qwen` |
| `XDG_DATA_HOME` | opencode, mimocode | `~/.local/share`, under which `opencode/` and `mimocode/` |
| `XDG_CONFIG_HOME` | opencode, mimocode, Cursor Agent: their skills | `~/.config` |

Antigravity CLI reads no variable: its state is always `~/.gemini/antigravity-cli`.

### Output

| Variable | |
| --- | --- |
| `NO_COLOR` | Anything non-empty: no escape sequences anywhere, the interface included. Wins over `FORCE_COLOR`. |
| `TERM` | `dumb`: treated as `NO_COLOR`. |
| `FORCE_COLOR` | Anything but `0`: write colour into a pipe or file, as a CI log wants. The layout stays the piped one. |
| `TEXTUAL_THEME` | A Textual theme for the interface instead of your terminal's sixteen colours. An unknown name is ignored. |

## Files

`~/.humanize` below is `$HUMANIZE_HOME` where that is set. Directories are made by whatever
writes into them.

### Runs

A run is one directory, its [epic](/reference/tracing#epics):
`~/.humanize/epics/<workspace>/<datetime>-<hex>/`, where `<workspace>` is the workspace's path
with everything but letters and digits turned into `-`.

| In the epic | Written by | |
| --- | --- | --- |
| `epic.jsonl` | every run | What the run was: the flow, the agents, every session opened and as which account, how it ended. |
| `epic.<flow>_<hex>.jsonl` | each flow the run [called](/reference/flows#a-flow-that-calls-another-flow) | The same, for that call. The run's own record names which file each call is in. |
| `resume.jsonl` | a run of a flow that [can be picked up](/reference/flows#a-flow-that-can-be-picked-up) | The journal `--resume` and `/resume` carry on from. |
| `profile.jsonl` | a run of a workspace that is [profiled](/reference/tracing#profiling-a-run) | The programs the run started, sampled as it ran. |
| `sessions/<cli>/` | every turn of the run | Its sessions, laid out as that CLI's home is, and the only copy: the CLI writes and resumes them here. |
| `traces/export.trace.json` | exporting on `/epics` | The trace of that run. One gathered by hand is named for the moment instead. |

| Elsewhere | Written by | |
| --- | --- | --- |
| `.humanize/<run>.epic.tar.gz` | **export run**, on a run in `/epics` | One whole run to send: its records, its session logs in full, a manifest. `0600`. |
| `~/.humanize/sessions/<cli>/` | a turn of an agent no run drives, from Python | Its sessions, as an epic's `sessions/` keeps a run's. |

### Flows

| Path | Written by | |
| --- | --- | --- |
| `.humanize/flows/*/` | you | This project's flows, offered as `local/<flow>`. |
| `~/.humanize/flows/*/` | you | Your flows in every project, offered as `user/<flow>`. |
| `~/.humanize/flowverses/<name>/` | `add a flowverse` on `/settings flowverses`, and every start | A [flowverse](/weaver/flowverses), cloned. Its flows are offered as `<name>/<flow>`. |
| `~/.humanize/flowverses/.pinned/<digest>/<commit>/` | a run of a `git+…#<flow>` ref | The repository a flow was [named by URL](/reference/flows#refs) in, at that commit. |
| `~/.humanize/skills/<owner>-<repo>-<digest>/` | a flow that names skills | A repository of [skills a flow brings](/reference/flows#the-skills-a-flow-brings), cloned; fetched again when a run next asks. |
| `~/.humanize/envs/<name>-<digest>/` | a flow that derives an environment | What a flow [derives from a workdir](/reference/flows#worktrees-copies-and-scratch-directories): `clones/`, `scratch/`, `worktrees/`. On an ssh host, the same under `${HUMANIZE_HOME:-~/.humanize}` there. Removed as the flow ends, unless its run can be picked up. |

### Accounts and models

| Path | Written by | |
| --- | --- | --- |
| `~/.humanize/providers/<cli>/<name>/provider.json` | `add an account` on `/settings accounts` | How a [provider](/reference/providers) was made and what its turns run with. `0600`, in a `0700` directory. |
| `~/.humanize/providers/<cli>/<name>/{home,user}/…` | the CLI's own login | That account's credentials, at the names the CLI keeps its own under. |
| `~/.humanize/providers/<cli>/<name>/models.json` | `add an account` on `/settings accounts`; **check again** on a model list | What that account may name. Never the credential it was asked with. |
| `~/.humanize/local/<cli>.json` | **fails over to** on "as local", on `/settings accounts` | What the account this machine is signed into fails over to. |
| `~/.humanize/models/<cli>.json` | the interface; **check again** on a model list | What the CLI as you run it may name. |
| `~/.humanize/fallbacks.json` | `/settings fallback` | Where a turn goes when its place cannot take it, and how often it is tried again first. |
| `~/.humanize/acp.json` | `add a custom CLI` on `/settings accounts` | Your [ACP CLIs](/reference/agents#a-cli-of-your-own), as `{name: [argv…]}`. |
| `~/.humanize/prices.json` | the interface, as it opens | Model prices from `HUMANIZE_PRICES`, refreshed when older than a day. `hmz exec` reads what is kept. |

### The interface and the daemon

| Path | Written by | |
| --- | --- | --- |
| `~/.humanize/settings.yaml` | the interface | Per workspace: what each flow was last set up with, [by the name it is offered under](/reference/tui#what-it-remembers), and whether runs are profiled. Beside them, `enable_sentry`. |
| `~/.humanize/history.jsonl` | the interface | What was typed at the prompt, and where. |
| `~/.humanize/daemons/<project>-<digest>/daemon.sock` | `hmz` | The socket a frontend reaches the [held runs](/reference/daemon) through. `0600`. |
| `~/.humanize/daemons/<project>-<digest>/daemon.json` | `hmz` | The process holding them, the workspace, when, and the [host's](/reference/daemon#hosting) `kind` and `protocol`. |
| `~/.humanize/daemons/<project>-<digest>/daemon.lock` | `hmz` | Held by the daemon while it runs. The kernel drops it when the process goes. |
| `~/.humanize/daemons/<project>-<digest>/daemon.log` | `hmz` | What could not be said to a frontend about those runs. |

### Caches

| Path | Written by | |
| --- | --- | --- |
| `~/.humanize/compiled/{pi,qwen}/` | a pi or Qwen Code session | Node's compile cache for that CLI. |
| `~/.cache/humanize/shadows/` | an anchored session | Which mirrors coganchor has made. Moved by `HUMANIZE_SHADOWS`. |

What an anchor keeps on a target is in [Remote execution](/reference/remote-execution).

## Exit statuses

| Status | |
| --- | --- |
| `0` | It did what it was asked, a run its budget stopped included. |
| `1` | It could not: a flow that raised, a target that could not be reached, a listener that could not start, a turn that could not be supervised. |
| `2` | The line was wrong: argparse's own rejections, and everything [refused before anything runs](#what-is-refused-before-anything-runs), a malformed listen address and a non-loopback listener with no token among them. |
| `126` | `hmz internal fence`: the fence could not be put up, and the program never ran. |
| `127` | `hmz internal anchor --native`: the target has no such CLI. |
| `130` | Interrupted. |
| `143`, `129` | `hmz exec` terminated (`SIGTERM`) or hung up on (`SIGHUP`). The run is stopped as an interrupt stops it, and exits only once it has let go of everything it made: its sessions closed, its containers removed. A second signal while it does is ignored. |
| *the program's own* | `hmz internal anchor` exits with the agent's status, `hmz internal cred` and `hmz internal fence` with the program's. |

## Python entry points

Every way in is a shell around [`Hmz`](/reference/sdk), the object the command line itself
holds:

```python
from hmz.sdk import Hmz

hmz = Hmz()
hmz.exec(["-f", "ralph_loop", "-a", "agent=claude/claude-opus-5:high", "-b", "cost=5", "fix the build"])
hmz.epics.trace(output="run.trace.json")
hmz.accounts.all("claude")
hmz.verses.add("humanfia/flowverse")
```

| Call | Reference |
| --- | --- |
| `hmz.exec(argv)` | [Flows](/reference/flows#running-one) |
| `hmz.epics.trace(...)` | [Tracing](/reference/tracing) |
| `hmz.accounts` | [Providers](/reference/providers) |
| `hmz.verses` | [Flowverses](/weaver/flowverses) |

The layers under it are reachable directly. `Hmz` composes them and restates none of them. The
layer each lives in is named in [Architecture](/contributing/architecture).

```python
from hmz.runtime.flowing import run_flow       # a flow, over drivers
from hmz.runtime.flowing import open_agent, open_env, parse_agents, parse_budget  # -a, -e, -b
from hmz.runtime.tracing import collect        # the trace /epics gathers
from hmz.coganchor import connect, check       # hmz internal anchor, and its --check
from hmz.daemon import running, host           # the runs hmz holds apart from the terminal
```

| Call | Reference |
| --- | --- |
| `await run_flow(flow, task, agents=…, envs=…, params=…, budget=…)` | [Flows](/reference/flows#running-one) |
| `collect(workspace, *, sessions=…, agents=…, output=…, start=…, end=…, profile=…)` | [Tracing](/reference/tracing) |
| `connect(command, config)`, `check(config)` | [Remote execution](/reference/remote-execution) |
| `running(workspace)`, `host(workspace)` | [Daemon](/reference/daemon) |
