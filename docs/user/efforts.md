<script setup>
import EffortLadder from '../.vitepress/theme/components/user-agents/EffortLadder.vue'
</script>

# Efforts

An agent is a CLI, a model and an **effort**: how hard the model thinks. Raise it for a task
that needs more thought, and lower it to spend less.

## Try it

The effort is the word after the last colon of an agent:

```sh
hmz exec -f ralph_loop -b cost=5 \
    -a agent=claude/claude-opus-5:high "fix the build"
#                                 ^^^^ the effort
```

At the prompt, open `/flow`, then the flow, then the agent's role. The `effort` row is marked
`↔`: <kbd>←</kbd> and <kbd>→</kbd> step it, and <kbd>space</kbd> takes the next one round.

```text{6}
  Set up agent

    1. cli          claude ▸                   which coding agent takes its turns
    2. provider     as local ▸                 the account those turns run as
    3. model        claude-opus-5 ▸            which of that CLI's models it runs
  ❯ 4. effort       high ↔                     how hard it thinks

       save                                    this agent

  ←/→ or space change · shift+enter/ctrl+j save · esc close
```

Choosing another model keeps the effort if that model takes it, and otherwise starts at the
hardest one it does.

## Every backend's ladder

Each CLI has its own words, so the ladder depends on the backend. Pick one, then click a rung
or type any word to see what `-a` makes of it:

<EffortLadder />

A word that is not on the backend's ladder is refused before anything runs, and `hmz exec`
exits with status 2. On Codex, Cursor Agent and ZCode each model takes only some of the rungs,
and the agent sheet offers each model its own.

::: details The same ladders, as a table

| Backend | Efforts, hardest first |
| --- | --- |
| `claude` | `ultracode` <Badge type="info" text="not listed by Claude Code" />, `max`, `xhigh`, `high`, `medium`, `low` |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` <Badge type="warning" text="subset per model" /> |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none` <Badge type="warning" text="subset per model" /> |
| `dsh` | `max`, `high`, `low`, `off` |
| `grok` | `xhigh`, `high`, `medium`, `low` |
| `kimi` | `max`, `high`, `medium`, `low` <Badge type="tip" text="each also as swarm…" /> |
| `mimo`, `opencode` | `xhigh`, `high`, `medium`, `low`, `minimal`: the model's variant |
| `pi` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` |
| `zcode` | `max`, `xhigh`, `high`, `medium`, `low`, `enabled`, `nothink`, `disabled` <Badge type="warning" text="subset per model" /> |
| `agy` | `high`, `medium`, `low` |
| a CLI added at `/providers` | any word <Badge type="info" text="not sent" /> |
| every backend | `auto` |

:::

## `auto`: no effort at all

`auto` tells the CLI nothing about how hard to think, so the model runs at its own default.
Every backend takes it. Use it for a model that has no rungs, such as Cursor's `composer-2.5`
or many models behind a gateway:

```sh
hmz exec -f ralph_loop -b cost=5 \
    -a agent=cursor-agent/composer-2.5:auto "fix the build"
```

`auto` is not the bottom rung. pi's `off`, DeepSeek Harness's `off` and Qwen Code's `none` ask
the model not to think at all; `auto` asks nothing.

## Kimi's swarm mode

On Kimi Code, the effort also says how wide a turn runs. `swarm` in front of a rung runs the
same thinking as a fleet of subagents, so `swarmmax` is `max`, run wide:

```sh
hmz exec -f ralph_loop -b cost=5 \
    -a agent=kimi/kimi-code/k3:swarmmax "fix the build"
```

On the agent sheet it is a row of its own, `swarm`, shown for a model that has it.

## For the whole run

An agent runs at the effort you gave it for the whole run. The flow can read the effort, but it
cannot move it, so a flow never makes an agent think harder than you asked.

## See also

- [Cost and rate](/user/tally): what a harder effort costs
- [Providers](/user/providers): the account a model runs as
- [Agents › Efforts](/reference/agents#efforts): the whole reference
