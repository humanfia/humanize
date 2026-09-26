# CLI reference

Every command, flag, environment variable, exit status and file. For a walk through rather than
a lookup, start at the [quickstart](/#run-a-flow).

```
hmz [<command> [<args>...]]
```

A line naming no command opens the [terminal interface](/reference/tui). A line naming something that
is not a command is a usage error listing the commands there are. Everything after the command
name reaches that command untouched — `--help` included — so each answers for its own
arguments.

There are two commands. `hmz exec` runs a flow, and is the one anybody types.
[`hmz internal`](#hmz-internal) is the door onto the four lines humanize spawns for itself —
listed rather than hidden, because a command nobody can discover is a command nobody can
debug, and these are exactly what turns up in a process table when a run has gone wrong.

`python -m hmz` is the same command line, which is how a turn spawns itself under an
[anchor](/reference/remote-execution).

## Who is reading

Every command is written twice over: for somebody at a terminal, and for a program.

- **A terminal** gets colour and layout. `hmz exec` draws the run as it happens — which agent
  is working and in which conversation, what it says, the tools it runs, the sub-agents it
  starts, a clock at the foot while it thinks, and what the turn cost when it lands.
- **A pipe or a file** gets exactly the same lines with no escape sequences in them. What each
  turn answered still goes to stdout and the run itself to stderr, so `hmz exec … > answer.txt`
  and `hmz exec … 2>/dev/null` mean what they always did.
- **A program** gets `--json`: one JSON object per line, flushed as it is written, and nothing
  else on stdout at all — anything the flow prints is put on stderr for the duration, so a
  stray line cannot break the stream.

`NO_COLOR`, `FORCE_COLOR` and `TERM=dumb` are honoured, in that order of authority. See
[environment variables](#environment-variables).

## `hmz`

```
hmz                  # opens the terminal interface
hmz --version        # prints the installed version
hmz --help           # lists the commands
```

There is no command that opens the interface. Naming nothing at all is how it opens.

It opens on a run [held apart from this terminal](/reference/daemon), so that closing the
terminal is not what ends a day's work: a line naming no command reads whichever run is already
being held in this directory and starts one where none is. It opens it in this
process instead, which is also what happens with no terminal to hand over to — output going to
a file, a suite driving the interface itself — and what happens if a run cannot be held at all,
which is said on stderr and then done without.

It opens on whatever this workspace was [last set up to run](/reference/tui#what-it-remembers).
The line says nothing about that: which flow, what drives it and what it is set up with are
[chosen at the prompt](/reference/tui#setting-a-flow-up), and what was chosen there is what the
next `hmz` here opens on — so a run that is always the same run is set up once rather than
spelled out again by every line that reads it.

Nothing is started either: the interface opens ready, and the first thing you say is still what
starts it.

## `hmz exec`

Runs a [flow](/reference/flows) in the current directory, on the agents and environments it is
given, under a budget.

```
hmz exec -f|--flow <ref>
         [-a|--agents <role>=<harness>[@<provider>]/<model>:<effort>[,...]] [-a ...]
         [-e|--envs <role>=<backend>@<provider>/<workdir>[,...]] [-e ...]
         [-p|--params <key>=<value>[,...]] [-p ...]
         -b|--budget duration=<duration>,cost=<usd>,output_tokens=<count>[,graceful=<bool>] [-b ...]
         [--resume] [--json] <task>
```

| Argument | |
| --- | --- |
| `-f`, `--flow <ref>` | **Required.** The flow to run. A bare `<flow>` is the flow named after its directory, else the only visible flow its module holds, and otherwise an error listing the ones it does hold; `<flow>:<sub>` is one of the [several flows a module holds](/reference/flows#several-flows-in-one-file); `<flowverse>/<flow>` pins a flow to the [flowverse](/reference/flows#flowverses) it came from — `local` and `user` for your own; a path is taken outright; and `git+https://…[@<rev>]#<flow>[:<sub>]` is a flow of a repository nobody has added. See [where flows live](/reference/flows#where-flows-live). |
| `-a`, `--agents <spec>[,<spec>...]` | One agent per **role** the flow declares, by the role's name. See [Writing an agent](#writing-an-agent). |
| `-e`, `--envs <spec>[,<spec>...]` | One environment per environment role, by the role's name. See [Writing an environment](#writing-an-environment). |
| `-p`, `--params <key>=<value>[,...]` | The flow's [params](/reference/flows#settings-of-the-flow-s-own), one field apiece. See [Writing params](#writing-params). |
| `-b`, `--budget <key>=<value>[,...]` | **Required**, for every flow but `chat`. What the run may spend. See [Writing a budget](#writing-a-budget). |
| `--resume` | Pick up the newest run of this flow in this workspace that [can be picked up](/reference/flows#a-flow-that-can-be-picked-up), rather than starting afresh. |
| `--json` | Write the run for a program: one JSON object on stdout per thing an agent says, as it says it. See [Watching a run](#watching-a-run). |
| `<task>` | **Required.** What the flow is to have the agents do, as the text itself. Put `--` before it if it starts with a dash. |

Every flag but `-f` repeats, and every one of them takes a comma-separated list, so
`-a actor=…,reviewer=…` and `-a actor=… -a reviewer=…` are the same line. A comma separates two
items only where what follows it is a key and `=`, so a value may hold commas of its own:
`-p tags=a,b,c` is one param.

**Nobody is at a prompt.** A run of `hmz exec` has its [outworlder](/reference/flows#the-person-at-the-prompt)
away the whole time: a flow that asks the person something is answered with nothing — `""`, or
the answer a schema's defaults make, and `OutworlderAway` where the schema has a field with no
default — and an agent that stops to ask is told nobody answered and carries on.

### Watching a run

At a terminal, the run is drawn as it happens:

```console
$ hmz exec -f rlar -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high -b cost=20 "fix the build"
● actor is working
● Bash(pytest -q tests/)
● I fixed add() and the tests pass.
✻ input 40.0k · output 1.2k · $0.61 · claude-opus-5 · actor
✻ Worked for 74s · actor
```

The star under a turn says what it cost: the tokens by kind, then what those came to in money
where the model is one [somebody lists](/user/tally#the-money), then which model and which
agent. A model nobody lists shows the tokens and no figure at all — `$0.00` beside a turn that
cost something would be a claim about a bill, and a wrong one.

While a turn is thinking — which is most of a turn — a clock sits at the foot of the screen
saying which agent is working and for how long, or how many turns are open where there are
several. It is drawn only where a terminal is reading **and** escapes are wanted — a clock is
written in them, cursor and all, so `NO_COLOR` and `TERM=dumb` mean no clock — and it is gone
when the run is.

Piped or redirected, the same lines are written with no escape sequences in them. The run goes
to **stderr** and what each turn answered to **stdout**, which is where every script written
against `hmz exec` reads it:

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high "summarise CHANGELOG.md" > summary.txt
```

`--json` writes the run for a program instead — [NDJSON](https://github.com/ndjson/ndjson-spec),
one object a line, flushed as each is written:

```console
$ hmz exec -f chat -a assistant=claude/claude-opus-5:high --json "say hello" | jq -c 'select(.kind == "result")'
{"at":1789026740.6,"agent":"assistant","cli":"claude","model":"claude-opus-5","session":"1d1ff959","kind":"result","text":"Hello.","whose":"","tokens":{"claude-opus-5":2080},"spent":{"input":2000,"output":80}}
```

| Key | |
| --- | --- |
| `at` | When it was said, as a Unix timestamp. |
| `agent` | Which agent said it, by the role the flow declared it under. |
| `cli`, `model` | Which backend and model it was said on. |
| `session` | The backend's own id for the conversation, or `""` before the backend has named one. |
| `kind` | `begins` and `ends` bracket a turn; `text` is the agent talking, `reasoning` it thinking aloud, `tool` it using one, `subagent`/`subagent-ends` an agent it started of its own, `asks` it stopping to ask, `failed` a turn that went wrong, `result` the answer it ends on. |
| `text` | The words themselves. |
| `whose` | Which of a turn's several things it is about — the backend's id for a sub-agent — and `""` for everything else. |
| `tokens` | What the turn cost, per model. Only a `result` carries it, and only from a backend that says. |
| `spent` | The same cost by the kind of token it went on. |

Every object carries every key, whether or not it has anything to put in it. While `--json` is
on, **nothing else reaches stdout**: whatever the flow prints goes to stderr instead, so one
stray line cannot break the stream.

### Writing an agent

```
actor=claude/claude-opus-5:high
reviewer=claude@deepseek/claude-opus-5:high
actor=claude/claude-opus-5:high,reviewer=codex/gpt-5.6-sol:max
```

`<role>=<harness>[@<provider>]/<model>:<effort>`, one role apiece. The role is the key the flow
[declares the agent under](/reference/flows#how-many-agents-and-what-they-are-for) — the
`reviewer` of `class Agents(AgentCollection): reviewer: Agent` — so a line says which agent is
which, and the order roles are written in means nothing.

- `<harness>` is `agy`, `claude`, `codex`, `cursor-agent`, `dsh`, `grok`, `kimi`, `mimo`,
  `opencode`, `pi`, `qwen` or `zcode` — or any CLI of your own
  [added at `/providers`](/reference/agents#a-cli-of-your-own), by the name it was added under.
  Each is the command that CLI is installed as. Several also answer to the longer name they
  are installed under: `antigravity`, `claude-code`, `cursor-cli`, `deepseek-harness`,
  `grok-build`, `kimi-code`, `qwen-code`, `mimocode`, `mimo-code` and `zcode-cli`.
- `<model>` and `<effort>` are whatever that CLI is asked for — humanize does not check them
  against a list, so a model your account has and this documentation does not still works.
- A model may hold slashes of its own — Kimi Code's are `kimi-code/k3`, and pi, opencode,
  mimocode and ZCode name every model as `provider/id` — so the harness is read from the front
  and the effort from after the last colon.
- An `@` after the harness names the [provider](/reference/providers) that agent's turns run
  as — the account, not the model: `claude@deepseek`. A harness is never spelled with an `@` in
  it, so the two are told apart wherever an agent is written. An agent that names none runs its
  CLI as you already run it.
- A role given twice, a role the flow does not declare, and a line with no role at all are each
  refused before anything runs.
- **A role the runtime fills is not yours to fill.** A role typed as an `Outworlder` is whoever
  is outside the run — nobody, under `hmz exec` — and naming it with `-a` is a usage error.
- **What an agent may do is not a setting of `-a`.** Its [permission](/reference/flows#what-each-agent-may-do),
  the skills it carries and what it must be able to do — a goal, steering, a hook only some
  harnesses reach — are the flow's, declared on the role's type, and a harness that cannot
  serve what a role declares is refused before anything runs.

### Writing an environment

```
repo=ssh@gpu-box/home/me/repo
repo=ssh@me@gpu-box:2222/~/repo
data=local@/srv/data
```

`<role>=<backend>@<provider>/<workdir>`, for each environment role the flow declares. The
workdir is everything from the first `/` after the `@`, so it is absolute; `ssh@host/~/repo` is
`repo` under the home directory of whoever ssh logs in as.

- `<backend>` is `local`, this machine, or `ssh`, a host reached with ssh.
- `<provider>` is the ssh destination — `host`, `user@host`, `host:port` or an alias of your ssh
  config — and is empty for `local`, whose spec is `local@/path`.
- A role the runtime fills is not yours to fill. A role typed as a `LocalEnv` is the directory
  `hmz exec` was started in, and naming it with `-e` is a usage error. Most flows work in
  nothing else, so most lines have no `-e` at all.
- An environment whose machine is smaller than the role declares — fewer CPUs or GPUs, less
  memory — is refused before anything runs, as is one that cannot serve a mixin the role
  declares.

### Writing params

```
-p rounds=3
-p rounds=3,strict=false -p tags=a,b,c
-p 'limits={"cost": 5, "turns": 9}'
```

`<key>=<value>`, one field of the flow's `FlowParams` apiece. Each value is read as the field's
own type — `3` for an `int`, `false` for a `bool` — and, where that does not read it, as JSON,
so a list or a model is written the way JSON writes one. A key the flow does not declare, a key
given twice and a value the field refuses are each refused before anything runs, naming the
field. A field left out keeps its default.

### Writing a budget

```
-b cost=20
-b duration=6h,output_tokens=10m
-b duration=1h30m -b cost=$5,graceful=false
```

At least one of the three limits, and each key at most once across every `-b` on the line:

| Key | Written as |
| --- | --- |
| `duration` | Seconds (`90`, `1.5`); units of weeks, days, hours, minutes and seconds, each at most once (`1h30m`, `2d`, `90s`); ISO 8601 (`PT1H30M`); or `HH:MM:SS`. |
| `cost` | USD, with or without a `$`. `inf` is no limit. |
| `output_tokens` | A whole number (`200000`, `200_000`), or thousands and millions (`200k`, `1.5m`). |
| `graceful` | `true` or `false` (`yes`/`no`, `1`/`0`, `on`/`off`). Whether the turn under way when a limit is reached is let finish before the run stops — the default — or is cut off at once. |

**A line with no `-b` is refused**, before any agent starts: a flow is a loop, and a loop with
nothing to stop it is a bill nobody agreed to. The one exception is `chat`, which ends when you
stop talking to it and runs with no limit at all. A flow no longer declares a budget of its own
for a run to fall back on. See [What a run may spend](/reference/flows#what-a-run-may-spend).

### What is refused before anything runs

Everything that can be known before the first turn is checked before the first turn, and is a
usage error — reported with nothing started, rather than an hour into a loop with a turn's work
already behind it:

- a ref that is no ref, or names no flow — a bare one that is ambiguous lists the flows there are;
- a `-a`, `-e`, `-p` or `-b` that cannot be read;
- no `-b`, for any flow but `chat`;
- a role named twice, a role the flow does not declare, a role the runtime fills, and a
  required role left unfilled — a role the flow declares `NotRequired` may be left out;
- an agent whose harness cannot serve what its role declares, or a role typed as one harness's
  own protocol given another harness;
- an environment short of what its role declares, or one that cannot be reached — every
  environment the line gives is probed before the flow is called;
- params the flow's model refuses;
- a skill a role names that cannot be found or fetched.

Each is one line on stderr, `hmz exec: error: …`, and exit status 2. A line argparse itself
cannot read — an unknown flag, no `-f` or task, an `-a`, `-e`, `-p` or `-b` that is not one —
prints argparse's usage line first:

```console
$ hmz exec -f rlar -a actor=claude/claude-opus-5:high -b cost=20 "fix the build"
hmz exec: error: rlar needs an agent for 'reviewer'; give each with -a ROLE=CLI/MODEL:EFFORT
$ hmz exec -f rlar -a actor=opus -b cost=20 "fix the build"
usage: hmz exec [-h] -f FLOW [-a ROLE=SPEC[,...]] [-e ROLE=SPEC[,...]]
                [-p KEY=VALUE[,...]] [-b KEY=VALUE[,...]] [--resume] [--json]
                task
hmz exec: error: -a 'actor=opus': expected [NAME=]CLI[@PROVIDER]/MODEL:EFFORT
```

Whatever else a flow does as it is imported is the flow's own, and fails as it would anywhere.

### Picking a run up

A flow that says it [can be picked up](/reference/flows#a-flow-that-can-be-picked-up) keeps a
journal of what it did while it runs: `resume.jsonl`, inside the run's
[epic](/user/tracing#what-a-run-writes-down), each state write a `{"t":"set",…}` line of it. `--resume` carries on the
newest run of the same flow in this workspace that got as far as writing one: the flow at the
top picks up what it kept, and each flow it calls picks up where it is called again with the
same task, agents, environments and params. The line still says what to run it on — its own
`-a`, `-e`, `-p` and a fresh `-b` — so an agent that changed is a flow called afresh from there
down. The run picking one up is an epic of its own, handed a copy of that journal, and says
which epic it `picked_up` from.

A flow that is not resumable, or one with no such run here, is refused with `--resume`. Without
it every run starts afresh, whatever an earlier one left behind.

A loop that only its budget ends ends that way: the turn it was in is let finish (unless the
budget said `graceful=false`), the run stops, `hmz exec: stopped -- …` says which limit it
reached, and the exit status is 0. A resumable one carries on from there with `--resume` and a
fresh `-b`.

### Examples

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b output_tokens=10m "$(cat TASK.md)"
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b output_tokens=10m --resume "$(cat TASK.md)"
hmz exec -f flame_chase -a first_chaser=claude/claude-opus-5:max,second_chaser=codex/gpt-5.6-sol:max \
    -b duration=6h,cost=50 "fix the build"
hmz exec -f rlar -a actor=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -b cost=20 "$(cat TASK.md)"
hmz exec -f flame_chase -a first_chaser=claude@anthropic/claude-opus-5:max \
    -a second_chaser=claude@deepseek/deepseek-chat:high -b cost=20 "fix the build"
hmz exec -f ./flows/mine -a coder=kimi/kimi-code/k3:swarmmax -b duration=2h "port this to asyncio"
hmz exec -f mine -a coder=claude/claude-opus-5:high -e trainer=ssh@gpu-box/home/me/repo \
    -b duration=1d "train it"
hmz exec -f ralph_loop -a agent=pi/openai-codex/gpt-5.5:high -b cost=5 "$(cat TASK.md)"
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 -- "--force is not a flag here"
hmz exec -f humanize1:rlcr -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:xhigh \
    -p max=20 -b duration=12h,cost=100 "add undo"
hmz exec -f 'git+https://github.com/humanfia/flowverse@main#rlar' \
    -a actor=claude/claude-opus-5:high,reviewer=codex/gpt-5.6-sol:high -b cost=20 "fix the build"
hmz exec -f chat -a assistant=claude/claude-opus-5:high "summarise CHANGELOG.md"
```

## `hmz internal`

```
hmz internal COMMAND [ARGS...]
```

The four lines humanize starts processes with, under one name. Nobody types one of these: each
exists because starting a process needs a command line, and each takes arguments humanize
renders for it.

They are listed and documented rather than hidden behind an undocumented name, because every
one of them is what a person *finds* rather than what they run — the process under a turn in
`ps`, the line in a backend's MCP configuration, the program a hook's error came from. A door
marked `internal` tells you both what is there and that it is not for you; a listing that left
them out would simply be untrue about what humanize runs.

| Command | |
| --- | --- |
| [`hmz internal anchor`](#hmz-internal-anchor) | A turn whose work lands on another machine, and — under `serve` — the half that lands it. |
| [`hmz internal cred`](#hmz-internal-cred) | A program run with its credentials answered out of an account's own directory. |
| [`hmz internal hook`](#hmz-internal-hook) | One moment of a coding agent's hook table, carried to the flow whose moment it is. |
| [`hmz internal tools`](#hmz-internal-tools) | A coding agent's tool calls, carried to the process whose callbacks they are. |

## `hmz internal anchor`

Runs a coding agent on this machine whose work lands on another one. See
[Remote execution](/reference/remote-execution).

**Not a command anybody types.** humanize spawns it for every turn whose work lands on another
machine, and the zipapp bootstrapped onto a target runs `hmz internal anchor serve` to answer
one — the same reason `hmz internal tools` is a command line. It still runs when it is typed,
which is what `--check` is for.

```
hmz internal anchor [options] AGENT [ARGS...]
```

Everything after the agent's name is the agent's own.

| Flag | Default | |
| --- | --- | --- |
| `--target URL` | `$HUMANIZE_TARGET`, else `local` | `ssh://HOST`, `docker://CONTAINER`, `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT`, or `local[:DIR]`. |
| `--harness WHERE` | `$HUMANIZE_HARNESS`, else `local` | Where the agent process and the supervisor tracing it run: `local`, `same` (wherever `--target` is), or a target spelling of their own. See [where the harness runs](/reference/remote-execution#where-the-harness-runs). |
| `--broker HOST` | `$HUMANIZE_RENDEZVOUS`, else this machine's outward address | Where the two halves dial to be introduced, when `--harness` and `--target` name different machines. |
| `--workspace PATH` | this directory | The project directory as it exists on the target. |
| `--chdir PATH` | `--workspace` | Where inside that workspace the agent starts, as the target names it. What a [session opened at a directory](/reference/agents#the-directory-a-session-works-in) comes to: the agent is put in this machine's mirror of it. |
| `--remote-path PATH` | `--workspace` | Where that workspace really lives on the target, if not at the same path. |
| `--shadow PATH` | `$HUMANIZE_SHADOW`, else `--workspace` | The mirror directory, on whichever machine the harness runs on. Defaulting to the workspace path is what makes the paths the agent sees the target's own. A harness elsewhere that was given none is put in one under that machine's own cache, named for what it mirrors and kept between turns. |
| `--local-path PATH` | — | Keep this path on this machine even when it is inside the workspace. Repeatable. |
| `--local-exec PATH` | — | Run programs under this path here rather than on the target. Repeatable. |
| `--redirect FROM=TO` | — | Answer this path with that one — the file it names, or everything under the directory it names — and keep what it is answered with local. What a turn under a [provider](/reference/providers) is given. Repeatable. |
| `--private NAME` | — | Keep this variable out of what the agent's commands are run with on the target: a credential it was given to reach its model provider is its own. Repeatable. |
| `--net {local,remote}` | `local` | Where the agent's *own* TCP connections go. Local keeps its model provider reachable. Commands it spawns always use the target's network. |
| `--net-allow HOST[:PORT]` | — | With `--net remote`, keep connections to this host local. Repeatable. |
| `--token TOKEN` | `$HUMANIZE_TOKEN` | Shared secret a `tcp://` target expects. |
| `--force` | off | Use the mirror directory even if it already holds unrelated files. |
| `--native` | off | Run the CLI already installed **on the target** instead of supervising one here. No mirror, nothing traced: this process starts it there and carries its three streams, its signals and its exit status. The flags above that describe a mirror say nothing under it. |
| `--hush NAME` | — | With `--native`, run the CLI on the target without this variable, whoever left it there. The other half of `--private`: a key in the target's own shell profile outranks the account the turn was given, and merely not sending one does not remove it. Repeatable. |
| `--project NAME=DIR` | — | With `--native`, put this directory of credentials on the target for the length of the turn and set `NAME` to where it landed. Written where only the target's user may read it, and removed when the turn is over. Repeatable. |
| `--carry DIR=PATH` | — | With `--native`, put this directory into the target's copy of the workspace at `PATH` for the length of the turn — which is how a flow's own [skills](/reference/flows#the-skills-a-flow-brings) get there. Nothing already at `PATH` is written over. Repeatable. |
| `--installs LINE` | — | With `--native`, the line that installs this CLI, said where the target has nothing to run. |
| `--check` | off | Connect, report what was found, and exit without running anything. |
| `--log-level {debug,info,warning,error}` | `$HUMANIZE_LOG`, else `warning` | Logging verbosity. The log goes to stderr. |

Settings no session could run under — a target nobody can read, a `--net` that is neither, a
credential bound for something that is not a variable — exit 2 the way argparse's own
rejections do. A `--native` session whose CLI the target has not got exits **127**, the status
every shell uses for a command it could not find, so that whatever spawned it reads it as a CLI
that is not installed.

```sh
hmz internal anchor --target ssh://build-box claude
hmz internal anchor --target ssh://gpu-01 codex exec "run the test suite"
hmz internal anchor --target docker://build-container --workspace /srv/project claude
hmz internal anchor --native --target docker://build-container --remote-path /srv/project claude
hmz internal anchor --harness same --target ssh://build-box --workspace /srv/project claude
hmz internal anchor --harness ssh://runner --target ssh://build-box --workspace /srv/project claude
hmz internal anchor --check --target ssh://build-box
```

## `hmz internal anchor serve`

The other half of a session: replays on this machine what an `hmz internal anchor` elsewhere
asks of it. Needs only a POSIX system and a recent `python3` — no root, no compiler, nothing
installed.

```
hmz internal anchor serve --export VIRTUAL[:REAL] (--stdio | --listen [HOST:]PORT | --peer TICKET@HOST:PORT) [--token TOKEN]
```

| Flag | |
| --- | --- |
| `--export VIRTUAL[:REAL]` | **Required, repeatable.** Expose a directory. `VIRTUAL` is the path the agent believes it is using; `REAL` is where it is here. |
| `--stdio` | Serve one session over stdin/stdout. This is what a bootstrapped target runs. |
| `--listen [HOST:]PORT` | Serve TCP connections on this address. A bare port listens on `127.0.0.1`. |
| `--peer TICKET@HOST:PORT` | Serve one session to whoever presents this ticket at that rendezvous — which is how the other half reaches this machine when it cannot dial it. humanize writes this one; it is not a line to type. |
| `--token TOKEN` | Shared secret required from clients. Defaults to `$HUMANIZE_TOKEN`. |
| `--log-level` | As for `hmz internal anchor`. |

`--stdio`, `--listen` and `--peer` are mutually exclusive, and one is required.

**Listening on anything but loopback without `--token` is refused.** An open port is equivalent
to a shell on that machine — read [Security](/user/security).

```sh
hmz internal anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

## `hmz internal anchor rendezvous`

The meeting place two halves of a session are introduced at, for the arrangement where the
harness is on one machine and its work on another and neither can dial the other. humanize
holds one of these inside itself for the sessions it starts; this is the same thing run on its
own, for a machine both halves can reach that is not the one driving them.

```
hmz internal anchor rendezvous [--listen [HOST:]PORT] [--punching SECONDS]
```

| Flag | |
| --- | --- |
| `--listen [HOST:]PORT` | The address to hold meetings on. Defaults to every interface on any free port, which is the point of it. |
| `--punching SECONDS` | How long two halves are given to reach each other before the broker carries the bytes itself. Defaults to 4. |
| `--log-level` | As for `hmz internal anchor`. |

The address it landed on is announced on stderr, so a port of `0` is usable from a script.
Pairing is by ticket and a ticket is a 128-bit secret, so there is no token: the only session a
stranger can join is one they were told the name of.

```sh
hmz internal anchor rendezvous --listen 0.0.0.0:9001
```

## `hmz internal cred`

```sh
hmz internal cred --map FROM=TO [--map ...] -- COMMAND [ARGS...]
```

Runs a program with some of its paths answered by others, and exits with its status. What a
turn under a [provider](/reference/providers) is spawned as, and what a login run for one is
spawned as: the program runs here, unchanged and on this terminal, and the handful of syscalls
that name one of its credential files are handed a path inside that account's directory
instead.

**Not a command anybody types.** It is a command of its own rather than something the driver
does in this process because the supervisor forks the program and takes the process's signal
handling with it, which a flow pumping turns from threads of its own has none to lend.

| Flag | |
| --- | --- |
| `--map FROM=TO` | **Required, repeatable.** Answer this path — the file it names, or everything under the directory it names — with that one. |
| `--` | Ends the flags. Everything after it is the program and its own arguments. |

A line with nothing to answer, or nothing to run, is a usage error. A run that could not be
supervised exits 1 rather than running the program unsupervised: that would be a turn taken as
whoever is at this machine, which is the wrong account rather than a failed turn.

## `hmz internal hook`

```sh
hmz internal hook --at <socket>
```

Carries one call of a coding agent's own [hook table](/reference/agents#hooks) to the flow
whose moment it is, and the verdict back again: it reads the call on its stdin, sends it to the
flow's socket and writes the answer back out. It is what makes a refusal at `PreToolUse` stop
the tool rather than describe one that has already run.

**Not a command anybody types.** A CLI takes a hook by starting a program and waiting for what
it says, so there is a program — humanize writes this line into the CLI's own hook table and
spawns it once per moment.

| Flag | |
| --- | --- |
| `--at PATH` | **Required.** The unix socket the flow is serving its moments on. |

It exits 0 whatever the flow said, and never with the status these CLIs read as the hook
itself having refused: a relay that could not reach anybody would otherwise be refusing on a
flow's behalf without having asked it. A socket that is not there lets the tool through and
says so on stderr, where the CLI shows it and carries on.

## `hmz internal tools`

```sh
hmz internal tools --at <socket>
```

Carries the tool protocol between a coding agent and the process whose callbacks were put in
front of it as tools — coganchor's `session.offers([...])`: it reads its stdin into that
process's socket and the answers back out to its stdout, and does nothing else. The flow API
has no way to offer a callback as a tool, so a flow never has one spawned for it; a flow
reaches back into its own code from inside a turn [through hooks](/weaver/tools) instead.

**Not a command anybody types.** A CLI takes a tool by starting a program, so there is a
program — the same reason `hmz internal cred` exists. humanize spawns it and tells the backend
to run it; a socket that is not there exits 1, which the CLI reads as tools being unavailable
rather than as a turn that failed.

| Flag | |
| --- | --- |
| `--at PATH` | **Required.** The unix socket the toolbox is served on. |

## Environment variables

| Variable | Read by | |
| --- | --- | --- |
| `HUMANIZE_HOME` | everything | Where humanize keeps what outlives one run. Defaults to `~/.humanize`. |
| `HUMANIZE_TARGET` | `hmz internal anchor` | Default for `--target`. |
| `HUMANIZE_HARNESS` | `hmz internal anchor` | Default for `--harness`. |
| `HUMANIZE_SHADOW` | `hmz internal anchor` | Default for `--shadow`. How a harness put on another machine is told which directory to mirror into, that machine's home being one this one cannot spell. |
| `HUMANIZE_RENDEZVOUS` | `hmz internal anchor` | Default for `--broker`: where two halves on two machines dial to be introduced. |
| `HUMANIZE_RENDEZVOUS_PORT` | humanize | The port humanize's own broker listens on, for a firewall that has to be told one in advance. Any free port by default. |
| `HUMANIZE_SSH_REUSE` | `hmz internal anchor` | Set to `0` on a host whose sshd refuses connection multiplexing. One `ssh` to a host otherwise serves every command after it. |
| `HUMANIZE_TOKEN` | `hmz internal anchor`, `hmz internal anchor serve` | Default for `--token`. |
| `HUMANIZE_LOG` | `hmz internal anchor`, `hmz internal anchor serve` | Default for `--log-level`. |
| `HUMANIZE_DAEMON` | `hmz` with no command | `off`, `0` or `no` opens the interface in this terminal rather than [holding the run apart from it](/reference/daemon). Anything else — including empty — is silence, and silence holds the run. |
| `HUMANIZE_SENTRY` | everything | `on` or `off`, answering the [reporting](/user/reporting) question for one process without writing anything down. Nothing else is looked at while it is set. |
| `HUMANIZE_WATCHDOG` | everything that runs a turn | How long a turn may say nothing before [the watchdog looks at it](/reference/agents#when-a-cli-stops-answering), in seconds, overriding each backend's own. `0` turns it off. |
| `HUMANIZE_SHADOWS` | `hmz internal anchor`, a container or a machine an agent works on | Where the mirrors coganchor has been pointed at are recorded. Defaults to `~/.cache/humanize/shadows`. |
| `CLAUDE_CONFIG_DIR` | the traces `/epics` gathers, the TUI's cost readout | Claude Code's home. Defaults to `~/.claude`. |
| `CODEX_HOME` | same | Codex's home. Defaults to `~/.codex`. |
| `DSH_HOME` | same | DeepSeek Harness's home. Defaults to `~/.dsh`. |
| `GROK_HOME` | the model list, the cost readout | Grok Build's home. Defaults to `~/.grok`. |
| `KIMI_CODE_HOME` | same | Kimi Code's home. Defaults to `~/.kimi-code`. |
| `PI_CODING_AGENT_DIR` | same | pi's home. Defaults to `~/.pi/agent`. |
| `QWEN_HOME` | same | Qwen Code's home. Defaults to `~/.qwen`. |
| `XDG_DATA_HOME` | the model list | Where opencode and mimocode keep their data. Defaults to `~/.local/share`. |
| `NO_COLOR` | every command, the TUI | Honoured. Set to anything non-empty, nothing writes an escape sequence — and it wins over `FORCE_COLOR`. |
| `FORCE_COLOR` | every command | Set to anything but `0`, a command writes colour into something that is not a terminal — which is what a CI log wants. It does not make a run believe somebody is watching it: a piped run is still written plainly in shape, just in colour. |
| `TERM` | every command | `dumb` is a terminal saying it could not read escapes, and is honoured as `NO_COLOR` is. |
| `TEXTUAL_THEME` | the TUI | Names a Textual theme to use instead of humanize's own, which is your terminal's sixteen colours. A name no theme answers to is ignored. |

Antigravity CLI and ZCode are the two backends whose homes cannot be moved: neither reads a
variable of its own, so their state is always `~/.gemini/antigravity-cli` and `~/.zcode`.

A backend home that does not exist is skipped rather than being an error.

**Set inside an anchored agent**, so that it and the commands it spawns can tell:

| Variable | |
| --- | --- |
| `HUMANIZE` | The version of the half that launched it. |
| `HUMANIZE_TARGET` | The target its work is landing on. |
| `HUMANIZE_WORKSPACE` | The workspace as the target has it. |

## Files

| Path | Written by | |
| --- | --- | --- |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/epic.jsonl` | every run of a flow | What the run was: the flow, the agents, every session opened and as which account, how it ended. See [Epics](/reference/tracing#epics). |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/epic.<flow>_<hex>.jsonl` | the same, per flow that run [called](/reference/flows#a-flow-that-calls-another-flow) | What that call was, written the same way: a called flow opens sessions and calls flows of its own. The run's own record says which file each call is in. |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/sessions/<session>/` | the same | A link per file each session was logged to, for reading a run back. humanize reads and writes the logs where the backend keeps them. |
| the run's journal, beside its epic | a run of a flow that [can be picked up](/reference/flows#a-flow-that-can-be-picked-up) | One JSON line per thing the run did that a run picking it up needs: each flow call and how it ended, each write to a flow's state, each session opened, each temporary copy and scratch directory kept. What `--resume` carries on from. |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/profile.jsonl` | a run of a workspace that asked to be profiled | The programs the run started, sampled while it ran. |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/traces/export.trace.json` | exporting on `/epics` | The trace of that run, gathered as it was exported. One gathered by hand is named for the moment instead. |
| `~/.humanize/providers/<cli>/<name>/provider.json` | **a** in `/providers` | What a [provider](/reference/providers) was made by, and what a turn under it runs with. `0600`, in a directory at `0700`. |
| `~/.humanize/providers/<cli>/<name>/{home,user}/...` | the CLI's own login | That provider's credentials, at the names the CLI keeps its own under. |
| `~/.humanize/providers/<cli>/<name>/models.json` | **a** in `/providers`, **r** | What that account may name: what its endpoint serves where it has one, and what the CLI said where it has not. Never the credential either was asked under. Goes when the account does. |
| `~/.humanize/local/<cli>.json` | what enter opens in `/providers` | What the account this machine is signed into does when it fails: where it falls back to, and how a turn under it is tried again. |
| `~/.humanize/acp.json` | a CLI of your own, added where `/providers` asks which CLI | The CLIs of your own that speak the [Agent Client Protocol](/reference/agents#a-cli-of-your-own), as `{name: [argv…]}`. A backend from the moment it is written. |
| `~/.humanize/models/<cli>.json` | the TUI, **r** | The same, for the CLI as you already run it. |
| `~/.humanize/settings.yaml` | the TUI | What each workspace was last set up to run and whether its runs are profiled, and the settings that are not a workspace's — `enable_sentry`, the answer to the [reporting](/user/reporting) question. |
| `~/.humanize/history.jsonl` | the TUI | What has been typed at the prompt before, and where. |
| `~/.humanize/daemons/<project>-<digest>/daemon.sock` | `hmz` with no command | The socket a terminal reaches a [held run](/reference/daemon) through. `0600`. |
| `~/.humanize/daemons/<project>-<digest>/daemon.json` | the same | Which process is holding it, which workspace, and since when. |
| `~/.humanize/daemons/<project>-<digest>/daemon.log` | the same | Whatever could not be said through a terminal about that run — what the daemon itself could not say, and what went wrong in a process reaching for its socket. |
| `.humanize/<run>.epic.tar.gz` | **export it**, on a run of `/epics` | One whole run, packaged up to send: its records, its session logs in full, and a manifest. `0600`. |
| `~/.humanize/flowverses/<name>/` | **a** in `/flowverses` | A [flowverse](/weaver/flowverses), cloned. Every flow in it is offered as `<name>/<flow>`. |
| `~/.humanize/flowverses/.pinned/<digest>/<commit>/` | a run of a `git+…#<flow>` ref | A repository a flow was [named by URL](/reference/flows#refs) in, checked out at the commit its ref stood at. One clone per commit. |
| `~/.humanize/envs/<name>-<digest>/` | a flow that derived an environment | What a flow [derives from a workdir](/reference/flows#worktrees-copies-and-scratch-directories) on this machine: `clones/`, `scratch/`, and `worktrees/` added with no directory of their own. On an ssh host, the same under `${HUMANIZE_HOME:-~/.humanize}` there. Removed as the flow that made them ends, unless its run can be picked up. |
| `~/.humanize/skills/<owner>-<repo>-<digest>/` | a flow that named one | A repository of [skills a flow brings](/reference/flows#the-skills-a-flow-brings), cloned. The digest is of the URL, so two repositories of one name on two hosts are two directories. Fetched again the next time a run asks for it. |
| `.humanize/flows/*/` | you | This project's own flows, offered as `local/<flow>`. |
| `~/.humanize/flows/*/` | you | Your flows in every project, offered as `user/<flow>`. |

`~/.humanize` is `$HUMANIZE_HOME` where that is set. The directories are made by whatever writes
into them.

## Exit statuses

| | |
| --- | --- |
| `0` | It did what it was asked — a run its budget stopped included. |
| `1` | It could not: the target could not be reached, the listener could not be started, a turn could not be supervised. |
| `2` | The command line was wrong — argparse's own rejections, a flow that is not there, a `-a`, `-e`, `-p` or `-b` that cannot be read or does not meet what the flow declares, no `-b` for a flow that is not `chat`, an environment that cannot be reached, `--resume` with nothing to pick up, a malformed listen address, a non-loopback listener with no token. |
| `130` | Interrupted. |
| *the agent's own* | `hmz internal anchor` exits with the status of the program it ran, and `hmz internal cred` with that of the program it supervised. |

## Python entry points

Every way in — the command, and every sheet of the interface — is a shell around a call you
can make yourself. The layer each lives in is named in
[Architecture](/contributing/architecture).

Every one of them is [`Hmz`](/reference/sdk) — the object the command line itself holds, which
it reaches as `from hmz.runtime import Hmz` and which `hmz.sdk` hands out to whoever is calling
humanize from outside:

```python
from hmz.sdk import Hmz

hmz = Hmz()
hmz.exec(["-f", "ralph_loop", "-a", "agent=claude/claude-opus-5:high", "-b", "cost=5", "fix the build"])
hmz.epics.trace(output="run.trace.json")
hmz.accounts.all("claude")
hmz.verses.add("humanfia/flowverse")
```

- `hmz.exec(argv)` — [Flows](/reference/flows#running-one)
- `hmz.epics.trace(...)` — [Tracing](/reference/tracing)
- `hmz.accounts` — [Providers](/reference/providers)
- `hmz.verses` — [Flowverses](/weaver/flowverses)

The layers under it are reachable directly where that is what you want — `Hmz` composes them
and restates none of them:

```python
from hmz.runtime.flowing import run_flow       # a flow, over drivers
from hmz.runtime.flowing import open_agent, open_env, parse_agents, parse_budget  # -a, -e, -b
from hmz.runtime.tracing import collect        # the trace /epics gathers
from hmz.coganchor import connect      # hmz internal anchor
from hmz.coganchor import check        # hmz internal anchor --check
from hmz.daemon import running, start  # the run hmz holds apart from the terminal
```

- `await run_flow(flow, task, agents=…, envs=…, params=…, budget=…)` — [Flows](/reference/flows#running-one)
- `collect(workspace, *, sessions=…, agents=…, output=…, start=…, end=…, profile=…)` — [Tracing](/reference/tracing)
- `connect(command, config)` / `check(config)` — [Remote execution](/reference/remote-execution)
- `running(workspace)` / `start(opens)` — [Daemon](/reference/daemon)
