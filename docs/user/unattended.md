<script setup>
import SpecReader from '../.vitepress/theme/components/user-after/SpecReader.vue'
</script>

# Run it unattended

`hmz exec` runs a flow with nobody at the prompt: from a script, a cron entry or a CI job. One
line names everything the run needs, and the line answers the same questions the `/flow` sheet
asks at the prompt.

## Try it

```sh
hmz exec -f ralph_loop \
    -a agent=claude/claude-opus-5:high \
    -b duration=2h,cost=10 \
    "$(cat TASK.md)"
```

| Part | What it says |
| --- | --- |
| `-f ralph_loop` | The flow, by the name `/flow` offers it under, or a path. |
| `-a agent=claude/claude-opus-5:high` | An agent for each role the flow declares. [Ralph loop](/flows/ralph-loop) has one, `agent`. |
| `-b duration=2h,cost=10` | What the run may spend. Whichever limit is reached first stops it. |
| `"$(cat TASK.md)"` | The task, as text. |

`ralph_loop` comes from the official flowverse, which `hmz` fetches each time it starts. On a
machine that has never run `hmz`, name the flow by its repository instead, as
[in CI](/user/ci#name-the-flow-by-its-repository).

The run is drawn in your terminal as it happens, and the command returns when the flow does.

::: warning Nobody approves anything
A flow's agents run with approvals bypassed: nothing asks before an agent edits a file or runs
a command. What each agent may touch is set by the flow. See [Permissions](/user/permissions).
:::

## Name an agent for each role

```
<role>=<cli>[@<account>]/<model>:<effort>
```

- **role** is the name the flow gives the agent: `agent` for [ralph_loop](/flows/ralph-loop),
  `actor` and `reviewer` for [rlar](/flows/rlar). Each flow's page lists its roles.
- **cli** is one of `agy`, `claude`, `codex`, `cursor-agent`, `dsh`, `grok`, `kimi`, `mimo`,
  `opencode`, `pi`, `qwen`, `zcode`, or a CLI you added at [`/providers`](/user/providers).
- **@account** runs the turns as an [account](/user/providers) you made. Leave it off to run
  the CLI as this machine is signed in.
- **model** goes to the CLI as written. humanize does not check it against a list.
- **effort** must be on that CLI's [ladder](/user/efforts); a CLI you added takes any word.
  `auto` asks for none.

The CLI is read up to the first `/` and the effort after the last `:`, so a model with slashes
in it needs no quoting. Several agents go in one `-a`, comma-separated, or in one `-a` each.
Type one below, or pick an example:

<SpecReader />

You never name the person or the working directory. humanize fills those roles itself.

## Set the budget {#say-what-the-run-may-spend}

A loop runs until something stops it, so every flow but `chat` needs a `-b`:

| Key | Written as |
| --- | --- |
| `duration` | wall clock: `90s`, `1h30m`, `2d`, or ISO `PT6H` |
| `cost` | US dollars: `50` or `$50` |
| `output_tokens` | tokens the agents may write: `200k`, `10m` |
| `graceful` | `false` cuts off the turn under way when a limit is reached. By default it finishes. |

Give at least one limit. When one is reached, the run stops, `hmz exec: stopped -- …` names the
limit on stderr, and the exit status is still 0: for a loop, that is the ordinary way to end.
A flow that calls another shares the budget with it. See [Every run has a
budget](/features/allowances).

::: tip A cost limit needs a priced model
`cost` can only stop a model humanize has a price for. For any other, `hmz exec` says so before
the first turn, `hmz exec: nobody lists a price for <model>, so cost=10 cannot stop what it
spends`, and runs anyway. Add a `duration` or `output_tokens` limit.
:::

## Watch it

At a terminal, each agent's work is drawn as it happens, with a clock at the foot while a turn
thinks:

```console
$ hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 "$(cat TASK.md)"
round 1
● agent is working
● Bash(pytest -q tests/)
● I fixed add() and the tests pass.
✻ input 40.0k · output 1.2k · $0.61 · claude-opus-5 · agent
✻ Worked for 74s · agent
round 2
● agent is working
⠹ agent is working · 12s
```

Redirect it and the same lines come out plain. The run goes to **stderr**. What each turn
answered, and whatever the flow prints, goes to **stdout**, so a script can take one without
the other:

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high \
    "summarise CHANGELOG.md" > summary.txt
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 \
    "$(cat TASK.md)" 2> run.log
```

`NO_COLOR` turns colour off. `FORCE_COLOR=1` turns it on for a log viewer that renders it.

## Check the line before you schedule it

`hmz exec` checks everything it can before the first turn: a line it can't read, a missing
role or budget, an effort off the CLI's ladder, a flow that isn't there. Each is refused in a
second, with exit status 2, before any agent starts. So try the line by hand once:

![hmz exec refusing a run with no budget, a flow whose role was left unfilled, and a flow
that is not there](/demo/checks.gif)

## Script on the exit status

| Status | Means |
| --- | --- |
| `0` | The flow returned, or its budget stopped it. |
| `1` | The run failed: the flow raised an error it did not handle. The traceback on stderr says which. |
| `2` | Refused before any agent started. The line after `hmz exec: error:` says why. |
| `130` | Interrupted with <kbd>ctrl+c</kbd>. |

```sh
if ! hmz exec -f goal -a worker=claude/claude-opus-5:max -b duration=4h "$(cat TASK.md)"; then
    echo "the loop did not finish" >&2
    exit 1
fi
```

## When nobody answers

With nobody at a prompt, the run behaves as if you were [away](/user/afk) the whole time:

- A flow that talks to you is answered with nothing, so `chat` does the one thing it was given
  and returns.
- An agent that stops to ask a question is told nobody answered, and carries on.
- A flow that needs an answer it has no default for fails, and says so.

## Stop it, and pick it up again

<kbd>ctrl+c</kbd> stops the run: the turn under way ends, its work stays where it got to, and
the command exits `130`. [`/epics`](/user/tracing#what-a-run-writes-down) lists the run as
stopped.

A flow that can be [picked up](/user/resuming), such as `ralph_loop`, carries on from there
when you run the same line with `--resume`:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b duration=2h \
    --resume "$(cat TASK.md)"
```

## Pass params and environments

A flow with [params of its own](/weaver/flow-settings) takes each one you want to change with
`-p`. The flow checks the whole set before the first turn:

```sh
hmz exec -f humanize1:rlcr -p max=9,plan_file=docs/plan.md \
    -a builder=claude/claude-opus-5:max \
    -a reviewer=codex/gpt-5.6-sol:xhigh \
    -b duration=12h,cost=100 "add undo"
```

A flow that works on another machine takes it with `-e`, as `role=local@/abs/path` or
`role=ssh@[user@]host[:port]/path`. Most flows have no such role. See [Remote
execution](/user/remote-execution).

## Read it with a program

`--json` writes the run to stdout as [NDJSON](https://github.com/ndjson/ndjson-spec): one
object per thing an agent says, flushed as it is said. Nothing else reaches stdout, so the
stream always parses:

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high --json "say hello" \
    | jq -c 'select(.kind == "result")'
```

Each object is one line in the stream, spread out here:

```json
{
  "at": 1789026740.6,
  "agent": "assistant",
  "cli": "claude",
  "model": "claude-opus-5",
  "session": "1d1ff959",
  "kind": "result",
  "text": "Hello.",
  "whose": "",
  "tokens": {"claude-opus-5": 2080},
  "spent": {"input": 2000, "output": 80}
}
```

Every object carries every key. `kind` is one of:

| `kind` | The agent… |
| --- | --- |
| `begins`, `ends` | starts and finishes a turn |
| `text`, `reasoning` | says something, or thinks aloud |
| `tool` | uses a tool |
| `subagent`, `subagent-ends` | starts an agent of its own, which later finishes |
| `asks` | stops to ask a question |
| `took` | has a line steered into the turn in front of it, and says which |
| `notice` | is waiting out a rate limit, moved to another account, or cut off (humanize says this, not the agent) |
| `failed` | failed the turn |
| `result` | gives the answer the turn ends on. Only this one carries `tokens` (by model) and `spent` (by kind of token). |

The full list of keys is in the [CLI reference](/reference/cli).

::: details A task that starts with a dash
Put `--` before it, so it is read as the task rather than a flag:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 \
    -- "--force is not a flag here"
```
:::

## See also

- [humanize in CI](/user/ci): the same line in a scheduled job
- [Picking a run up](/user/resuming)
- [Tracing a run](/user/tracing): what the run did, as a timeline
- [CLI reference](/reference/cli): every flag of `hmz exec`
