# Run it unattended

`hmz exec` runs a flow with nobody at a prompt — which is what a script, a cron entry or a CI
job wants. Reach for it once a run is the same run every time.

## The shape of the line

```sh
hmz exec -f <flow> -a <role>=<agent>[,...] [-e <role>=<env>] [-p <key>=<value>] \
    -b <budget> [--resume] [--json] "<task>"
```

| | |
| --- | --- |
| `-f` | the flow, by name or by path |
| `-a` | an agent for each agent role the flow declares, by the role's name |
| `-e` | an environment for each environment role the flow declares that humanize does not fill itself — usually none |
| `-p` | the flow's params, one field apiece — only where you want other than its defaults |
| `-b` | what the run may spend. **Required**, for every flow but `chat` |
| the last argument | the task, as the text itself |

Every flag but `-f` repeats and takes a comma-separated list, so a flow of four agents is one
`-a` or four, whichever reads better in the line you are writing.

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b output_tokens=10m "$(cat TASK.md)"
```

## Write an agent

An agent is a CLI, an account, a model and an effort, and there is one way to write one:

```
<role>=<cli>[@<provider>]/<model>:<effort>
```

```
agent=claude/claude-opus-5:high
actor=claude@deepseek/claude-opus-5:high
reviewer=codex/gpt-5.6-sol:max
```

The role in front says **which of the flow's agents this one is**, by the name the flow declares
it under — `actor` and `reviewer` for [rlar](/flows/rlar), `agent` for
[ralph_loop](/flows/ralph-loop). `@` names the [account](/user/providers) the turns run as — the
account, not the model.

```console
$ hmz exec -f rlar -a actor=claude/claude-opus-5:max -b cost=20 "fix the build"
hmz exec: error: rlar:rlar: no agent was given for 'reviewer'
```

Read an agent from both ends: the CLI comes first, and the effort comes after the **last**
colon. That is why a model with slashes in it works:

```sh
hmz exec -f ralph_loop -a agent=kimi/kimi-code/k3:swarmmax -b cost=5 "$(cat TASK.md)"
hmz exec -f ralph_loop -a agent=pi/openai-codex/gpt-5.5:high -b cost=5 "$(cat TASK.md)"
hmz exec -f ralph_loop -a agent=opencode/opencode/big-pickle:high -b cost=5 "$(cat TASK.md)"
hmz exec -f ralph_loop -a agent=zcode/zai/glm-5.3:high -b cost=5 "$(cat TASK.md)"
```

`<model>` and `<effort>` are whatever the CLI is asked for. humanize does **not** check them
against a list, so a model your account has still works even when this documentation does not
mention it.

**You never write the person or the directory.** A role the flow types as an `Outworlder` is
whoever is outside the run — nobody, here — and a role typed as a `LocalEnv` is the directory
you ran `hmz exec` in. Both are filled by humanize, and naming either on the line is refused.

## Say what the run may spend

A loop runs until something stops it, so `hmz exec` will not start one without a `-b`:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b duration=6h,cost=50 "$(cat TASK.md)"
```

| | |
| --- | --- |
| `duration` | wall clock: `90s`, `1h30m`, `2d`, or ISO `PT6H` |
| `cost` | USD: `50`, `$50` |
| `output_tokens` | what the agents may write: `200k`, `10m` |
| `graceful` | `false` cuts the turn under way off the moment a limit is reached; the default lets it finish |

At least one limit, and whichever is reached first stops the run. A flow calling another shares
it: what the callee spends counts against the caller too. See [Every run has an
allowance](/features/allowances).

## Narrow what an agent may do

The flow says it, on the role's type — not the line that runs it:

```python
from hmz.flows import Agent, Permission, PermissionKind

class Reviewer(Agent):
    _permission = Permission(local=PermissionKind.READ)
```

```sh
hmz exec -f ./review -a reviewer=codex/gpt-5.6-sol:high -b cost=5 \
    "review this repository and write the findings to REVIEW.md"
```

Nothing a flow's agent does is ever put to anybody for approval, so a flow runs with nobody
watching whatever it declares: a role that may write its directory runs at its CLI's
nothing-asked mode, and one that may only read runs at its CLI's read-only one. See
[Permissions](/user/permissions).

## Run with nobody at a prompt

Nobody at a prompt has one consequence: **nobody answers**. There is nothing to switch. It is
[`/afk`](/user/afk) always.

- A flow that talks to [the person](/weaver/human-agent) — such as `chat` — is answered with
  nothing: `""`, or the answer a shape's defaults make. `chat` does the one thing it was given,
  once.
- A flow that asks the person for [an answer in a shape](/weaver/shapes) with a field that has
  no default gets `OutworlderAway` raised, and the weaver who wrote it had better have handled
  that.
- An agent that stops mid-turn to ask a question is told nobody answered and carries on, unless
  the flow answers it itself.

## Watch it while it runs

At a terminal, the run is drawn as it happens — which agent is working, what it says, the
tools it runs, and what each turn cost when it lands. A turn thinks for minutes and says
nothing for most of them, so a clock sits at the foot of the screen while it does:

```console
$ hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 "$(cat TASK.md)"
● agent is working
● Bash(pytest -q tests/)
● I fixed add() and the tests pass.
✻ input 40.0k · output 1.2k · $0.61 · claude-opus-5 · agent
✻ Worked for 74s · agent
```

Redirect it and the escape sequences go: the same lines, plain. What each turn **answered**
goes to stdout and the run itself to stderr, so a script reads one without the other:

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high "summarise CHANGELOG.md" > summary.txt
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 "$(cat TASK.md)" 2> run.log
```

`NO_COLOR` turns colour off outright; `FORCE_COLOR` turns it on for a log that renders it.

## Read it with a program

`--json` writes the run as [NDJSON](https://github.com/ndjson/ndjson-spec) — one object per
thing an agent says, on stdout, flushed as it is said:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 --json "$(cat TASK.md)" \
    | jq -c 'select(.kind == "result")'
```

Every object carries the agent, the backend and model, the conversation, the kind of thing it
was, the words, what the turn cost and when — the keys are in the
[CLI reference](/reference/cli#watching-a-run). While `--json` is on, nothing else reaches
stdout: whatever the flow prints goes to stderr, so one stray line cannot break the stream.

## See what is checked first

Run these on purpose. Each is refused before a single turn:

```console
$ hmz exec -f rlar -a actor=claude/claude-opus-5:max -b cost=20 "fix the build"
hmz exec: error: rlar:rlar: no agent was given for 'reviewer'

$ hmz exec -f ralph_loop -a claude/claude-opus-5:high -b cost=5 "fix the build"
hmz exec: error: -a 'claude/claude-opus-5:high': expected <role>=<harness>[@<provider>]/<model>:<effort>

$ hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high "fix the build"
hmz exec: error: ralph_loop needs a budget: -b duration=…,cost=…,output_tokens=…
```

Everything that can be known before the first turn is checked before the first turn: a missing
role, an agent whose CLI cannot do what its role declares, params the flow's model refuses, a
budget that limits nothing. An hour into a loop is the wrong place to find out you miscounted.

![hmz exec refusing a malformed agent, a missing role, and a flow that is not
there](/demo/checks.gif)

## Pass a task that starts with a dash

`--` ends the flags, so a task that starts with a dash is read as the task:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 -- "--force is not a flag here"
```

## Run a flow with params

For a flow that [takes params of its own](/weaver/flow-settings), write each one you want other
than its default with `-p`:

```sh
hmz exec -f humanize1:rlcr -p max=9,plan_file=docs/plan.md \
    -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:xhigh \
    -b duration=12h,cost=100 "add undo"
```

Each value is read as its field's type — and as JSON where that is what reads it, for a list or
a mapping — and the flow's own model checks the lot **before the first turn**, so a combination
the flow will not run is refused where you wrote it.

## Read the exit status

| | |
| --- | --- |
| `0` | it did what it was asked |
| `1` | it could not — no such provider, target unreachable, a turn that could not be supervised |
| `2` | the command line was wrong |
| `130` | interrupted |

You can script on these statuses:

```sh
hmz exec -f goal -a worker=claude/claude-opus-5:max -b duration=4h "$(cat TASK.md)" || {
    echo "the loop did not finish" >&2
    exit 1
}
```

## Stop a run

Stop it with **ctrl+c**. The interrupt reaches the whole process group, so the agent's own
process takes it too. The turn under way dies with it, what it was doing is left where it got
to, and the command exits `130`.

The [epic](/user/tracing#what-a-run-writes-down) records that run as **`failed`**. `stopped`
is for a run [told to stop by hand](/user/stopping), with ctrl+c twice or `/stop` in the
interface. Nothing on a command line tells the two apart.

Either way, a flow that says it [can be picked up](/user/resuming) carries on from what that
run left behind: the same line with `--resume` picks up the newest run of that flow here, or
type `/resume` in the interface.

## Checking a line before it goes into cron

There is no line that opens the interface on a setup: `hmz` with no command opens on whatever
that directory was [last set up to run](/reference/tui#what-it-remembers), and the flow, its
roles, its params and its budget are chosen at the prompt. So a line bound for cron is checked
by running it — everything knowable before the first turn is refused before the first turn,
which is why the refusals above cost two seconds rather than forty minutes.

For a run that is always the same run, set it up once at the prompt and leave it: `hmz` in that
directory opens on it every morning, and the line stays in cron for the nights nobody is there.

## See also

- [Permissions](/user/permissions)
- [Params of its own](/weaver/flow-settings)
- [Tracing](/user/tracing) — what a run writes down, and reading it back
- [Stopping](/user/stopping)
- [Picking a run up](/user/resuming) — carrying a stopped loop on where it left off
- [humanize in CI](/user/ci)
