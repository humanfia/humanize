<script setup>
import EffortLadder from '../.vitepress/theme/components/user-agents/EffortLadder.vue'
</script>

# Efforts

An agent is a CLI, a model and an **effort**: how hard the model thinks before it answers. Use
this page to choose one, when a task needs more thought than you are getting or a loop is
spending more than the work is worth. By the end you will set an effort on the command line and
at the prompt, and know which words each backend takes.

## Try it

The effort is the word after the last colon of an agent:

```sh
hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:low \
    "Name the three primary colours, one line."
```

```text
● Red, yellow, and blue are the three traditional primary colors.
✻ input 10 · output 136 · cache_read 13.9k · cache_write 6.9k · $0.01 · claude-haiku-4-5-20251001 · assistant
```

## Before you start

- humanize is [installed](/user/installation), with at least one coding agent CLI signed in.
- You know which CLI and model you want. The effort is the last thing you choose, because
  which efforts there are depends on both.

## What an effort is

Each coding agent CLI has its own words for how long a model reasons: Claude Code says
`ultracode` to `low`, Codex says `ultra` to `low`, pi goes down to `off`. humanize takes the
CLI's own word and passes it on, so an effort always means what that CLI means by it. It does
not translate one backend's `high` into another's.

- **A harder effort** reasons longer. It writes more output tokens, so it costs more and takes
  longer, and it is what a hard bug or a large refactor wants.
- **An easier effort** answers sooner and cheaper. It suits a loop that repeats a mechanical
  step many times.
- **`auto`** says nothing about effort at all, and the model runs at the CLI's own default.

An agent keeps the effort you gave it for the whole run. A flow can read the effort, but it
cannot change it, so a flow never makes an agent think harder than you asked.

## Example: pick an effort, and have a wrong one refused

You want Claude Code's cheapest model to answer quickly. First, try a word Claude Code does not
have:

```sh
hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:turbo "hi"   # ①
echo $?                                                                    # ②
```

```text
hmz exec: error: assistant=claude/claude-haiku-4-5-20251001:turbo: claude cannot be asked to think at 'turbo'; expected one of ultracode, max, xhigh, high, medium, low
2
```

Then use one from the list it gave you:

```sh
hmz exec -f chat \
    -a assistant=claude/claude-haiku-4-5-20251001:low \
    "Name the three primary colours, one line."                            # ③
```

```text
● assistant is working
● Red, yellow, and blue are the three traditional primary colors.
✻ input 10 · output 136 · cache_read 13.9k · cache_write 6.9k · $0.01 · claude-haiku-4-5-20251001 · assistant   ④
Red, yellow, and blue are the three traditional primary colors.
✻ Worked for 3s · assistant
```

### What each part means

1. **`:turbo`** is read as the effort because it comes after the *last* colon. The CLI is read
   up to the first `/`, so a model with slashes or colons in its name needs no quoting.
2. **Exit status `2`** means the line was refused before anything ran: no agent started, and
   nothing was spent. The message names the CLI and lists its whole ladder, hardest first.
3. **`:low`** is the bottom of Claude Code's ladder. For a one-line answer, it is plenty.
4. **The `✻` line** is what the turn cost. `output 136` is the tokens the model wrote,
   reasoning included. Run the same line at `:high` and that figure is the one that grows.
   See [Cost and rate](/user/tally).

## Example: set it at the prompt

In `hmz`, open `/flow`, choose the flow, then the agent's role. The agent sheet has one row
per choice, and the effort is the last of them:

```text
  hmz › /flow › Installed › chat › Set up assistant
  Configure this agent: select its CLI, account, model, and reasoning effort.

  ╭──────────────────────────────────────────────────────────────────────────╮
  │ cli                                                             claude ▸ │
  │   coding agent CLI to use                                                │
  │──────────────────────────────────────────────────────────────────────────│
  │ account                                                       as local ▸ │  ①
  │   account to run as                                                      │
  │──────────────────────────────────────────────────────────────────────────│
  │ model                                        claude-haiku-4-5-20251001 ▸ │  ②
  │   model to use                                                           │
  │──────────────────────────────────────────────────────────────────────────│
  │ effort                                                             low ▾ │  ③
  │   reasoning effort                             ╭─ effort ─────────────╮  │
  │                                                │ ultracode            │  │
  │                                                │ max                  │  │
  │                                                │ xhigh                │  │
  │                                                │ high                 │  │  ④
  │                                                │ medium               │  │
  │                                                │ low ✔                │  │
  │                                                ╰──────────────────────╯  │
  ╰──────────────────────────────────────────────────────────────────────────╯

                                                                          Save

  enter choose   esc close
```

### What each part means

1. **`account`** is who the turns run as. `as local` is the CLI as this machine is signed in.
   See [Accounts](/user/settings#accounts).
2. **`model`** lists, for each model, the efforts it takes, so you can see a model's ladder
   before you pick it:
   `claude-haiku-4-5-20251001 ultracode, max, xhigh, high, medium, low`.
3. **`▾`** marks a row whose values drop under it. <kbd>enter</kbd> or a click shows the
   model's whole ladder, hardest first, with `✔` on the effort in force.
4. **The list**: <kbd>↑</kbd> <kbd>↓</kbd> and <kbd>enter</kbd>, or a click, pick an effort;
   <kbd>esc</kbd> or a click off the list keeps the one you had.

Press **Save** under the sheet (<kbd>tab</kbd>, <kbd>enter</kbd>), then **save** on the flow. The
line above the prompt then reads
`assistant · claude/claude-haiku-4-5-20251001:low`.

## Check that it worked

- Under `hmz exec`, a line that runs at all was accepted: a refused effort exits `2` before
  anything starts.
- At the prompt, the agent line above the editor ends in the effort, as in `…:low`.
- Compare the `output` figure on the `✻` line of two runs at different efforts. The harder one
  writes more.

## Every backend's ladder

Each CLI has its own words, so the ladder depends on the backend. Pick one, then click a rung
or type any word to see what `-a` makes of it:

<EffortLadder />

A word that is not on the backend's ladder is refused before anything runs. On Codex, Cursor
Agent and MiniMax Code each model takes only some of the rungs, and the agent sheet offers each
model its own.

::: details The same ladders, as a table

| Backend | Efforts, hardest first |
| --- | --- |
| `claude` | `ultracode` <Badge type="info" text="not listed by Claude Code" />, `max`, `xhigh`, `high`, `medium`, `low` |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` <Badge type="warning" text="subset per model" /> |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none` <Badge type="warning" text="subset per model" /> |
| `dsh` | `max`, `high`, `low`, `off` |
| `grok` | `xhigh`, `high`, `medium`, `low` |
| `kimi` | `max`, `high`, `medium`, `low` <Badge type="tip" text="each also as swarm…" /> |
| `mcode` | `max`, `xhigh`, `high`, `medium`, `low` <Badge type="warning" text="only MiniMax-M3.1-Flash-Preview" /> |
| `mimo`, `opencode` | `xhigh`, `high`, `medium`, `low`, `minimal`: the model's variant |
| `pi` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` |
| `agy` | `high`, `medium`, `low` |
| a CLI added on the Accounts page of `/settings` | any word <Badge type="info" text="not sent" /> |
| every backend | `auto` |

:::

## Variations

### `auto`: no effort at all

`auto` tells the CLI nothing about how hard to think, so the model runs at its own default.
Every backend takes it. Use it for a model that has no rungs, such as Cursor's `composer-2.5`
or many models behind a gateway:

```sh
hmz exec -f ralph_loop -p budget.cost=5 \
    -a agent=cursor-agent/composer-2.5:auto "fix the build"
```

`auto` is not the bottom rung. pi's `off`, DeepSeek Harness's `off` and Qwen Code's `none` ask
the model not to think at all; `auto` asks nothing. On the agent sheet, a model with no rungs
shows no effort to pick, and runs as `auto`.

### Kimi's swarm mode

On Kimi Code, the effort also says how wide a turn runs. `swarm` in front of a rung runs the
same thinking as a fleet of subagents, so `swarmmax` is `max`, run wide:

```sh
hmz exec -f ralph_loop -p budget.cost=5 \
    -a agent=kimi/kimi-code/k3:swarmmax "fix the build"
```

On the agent sheet it is a row of its own, `swarm`, shown for a model that has it.

### Two roles, two efforts

Each role has its own agent, so each has its own effort. A cheap maker and a careful checker is
a common split:

```sh
hmz exec -f rlar -p budget.cost=10 \
    -a actor=claude/claude-opus-5:medium \
    -a reviewer=codex/gpt-5.6-sol:xhigh "fix the build"
```

## Pitfalls

- **A new model starts at its hardest rung.** Choosing another model on the sheet keeps the
  effort if that model takes it, and otherwise starts at the hardest one it does, such as
  `ultracode` on Claude Code. Step it down before you save if you did not mean that.
- **`cannot be asked to think at '…'`.** The word is not on that CLI's ladder. Pick one
  from the list in the message, or `auto`. See
  [Troubleshooting](/user/troubleshooting).
- **`cursor-agent lists no … this account runs … as …`.** Cursor writes the effort into the
  model's id, and your account does not offer that model at that effort. Pick an effort the
  message lists.
- **The same word, different cost.** `high` on one backend is not `high` on another.
  Compare the `output` figure on the `✻` line, not the word.

## Next steps

- [Cost and rate](/user/tally): what a harder effort costs
- [Accounts](/user/settings#accounts): the account a model runs as
- [Run it unattended](/user/unattended): the rest of an `-a`
- [Agents › Efforts](/reference/agents#efforts): the whole reference
