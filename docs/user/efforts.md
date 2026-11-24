---
title: Effort and swarm mode
description: Choose how hard an agent's model thinks, on every interface, and run a turn as a fleet of subagents where the harness can.
---

# Effort and swarm mode

Effort sets how hard a model thinks before it answers. It is the last part of an agent, after the harness, account, and model. Swarm mode runs a turn as a fleet of subagents instead of one agent.

![The chip of a new chat in Humanize Desktop is opened, its Effort level is opened, and Low is picked](/shots/user-efforts-chip.svg)

## How effort works

Each harness uses its own words for effort. Humanize passes your chosen word directly to the harness without translating it.

Harder efforts think longer, use more output tokens, and cost more. Easier efforts answer sooner and cost less. Set `auto`, or omit the effort, to send nothing and run at the harness's default. Every harness accepts `auto`, which the app calls **Default**.

A model may support only a subset of its harness's efforts. Humanize queries the harness and offers only the supported values.

## Efforts by harness

Efforts are listed from hardest to easiest.

| Harness | Efforts |
| --- | --- |
| `claude` | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none` |
| `pi`, `omp` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` |
| `mcode` | `max`, `xhigh`, `high`, `medium`, `low` |
| `opencode`, `mimo` | `xhigh`, `high`, `medium`, `low`, `minimal` |
| `grok` | `xhigh`, `high`, `medium`, `low` |
| `kimi` | `max`, `high`, `medium`, `low`, and each with `swarm` in front |
| `dsh` | `max`, `high`, `low`, `off` |
| `agy` | `high`, `medium`, `low` |
| `litellm` | `high`, `medium`, `low`, `minimal`, `none` |
| a CLI you added over ACP | `as configured`: any word is accepted, none is sent |

`off` and `none` tell the model not to think at all.

On `claude`, `ultracode` runs at `xhigh` and tells Claude Code to orchestrate its own fleet of subagents.

## In the app

1. Click the agent chip under the message box of a new chat, on a role of the **New epic** page, or wherever you choose a nous.
2. Click **Effort**, then select an effort from the list of **Default** and the model's supported values. Models that take no effort hide the **Effort** level.

![The Effort level of the chip: Default, Ultracode, High, Medium, Low](/shots/user-efforts-levels.svg)

The app displays effort names in plain words: `xhigh` and `extra-high` become **Extra high**, `max` becomes **Max**, `none` becomes **None**, and `as configured` becomes **As configured**.

Once a chat has started, selecting an effort on the chip changes it for the chat's next turn, whether the chat is running or was opened from the list. A harness that cannot go on from an earlier conversation refuses the change with a message; see [Change the model or effort](/user/chat-input#change-the-model-or-effort).

## In the terminal

Open the agent sheet for a flow role with `/flow`, the flow, and the role, or for the workspace chat agent with `/settings workspace` and **Chat agent**.

1. Select the `Effort` row and press <kbd>enter</kbd> to list the model's efforts.
2. Press <kbd>↑</kbd> or <kbd>↓</kbd> to highlight an effort, press <kbd>enter</kbd> to pick it, and select **Save**.

![The agent sheet in the terminal: the effort row is opened, the model's efforts drop under it, and low is picked](/shots/user-efforts-terminal.svg)

With no model chosen yet, pressing <kbd>enter</kbd> on the row answers `pick a model first: the efforts are the model's`. The model list shows each model's supported efforts beside its name. The form that adds a concrete nous on `/settings nous` has an `Effort` row as well.

In an active Claude Code or Codex chat, run `/effort` to change the effort for future turns:

```text
/effort low
```

The new effort takes effect on the next turn and persists for the rest of the chat.

## From the command line

Add the effort after the last colon of the agent spec in `hmz exec` and `hmz chat`:

```sh
hmz exec -f goal -a worker=claude/claude-haiku-4-5:low -p budget.output_tokens=20000 "Add a discount code to checkout"
hmz chat start -a claude/claude-haiku-4-5:low "Add a discount code to checkout"
```

![hmz exec run with an agent at :low, and the answer it printed](/shots/user-efforts-exec.svg)

If you pass an effort the harness does not support, the command exits immediately with status `2`, spends nothing, and lists the valid efforts:

![hmz exec refusing :turbo and listing the efforts claude takes](/shots/user-efforts-refused.svg)

Set a separate effort for each role by specifying each role's agent:

```sh
hmz exec -f rlar -p budget.cost=10 -a actor=claude/claude-haiku-4-5:low -a reviewer=claude/claude-opus-4-1:high "Add a discount code to checkout"
```

## Run a turn in swarm mode

Swarm mode changes the width of the turn, not the thinking depth: `max` and `swarmmax` think at the same effort. Only Kimi Code (`kimi`) supports swarm mode.

![The same effort at two widths: max runs a turn as one agent, swarmmax as a lead agent with subagents](/diagrams/user-efforts-1.svg)

In the terminal, models that support swarming show a `Swarm` row below `Effort` on the agent sheet. Set it to `On` to run as a swarm, or `Off` to run as one agent.

![The agent sheet for a Kimi Code model, with the swarm row opened on its on and off values](/shots/user-efforts-terminal-swarm.svg)

The model list marks capable models with `swarms`:

![The model list for kimi: each model with its efforts and the word swarms](/shots/user-efforts-terminal-models.svg)

On the command line, prefix the effort with `swarm`:

```sh
hmz exec -f goal -a worker=kimi/kimi-code/k3:swarmmax -p budget.cost=5 "Add a discount code to checkout"
```

Harnesses without swarm mode reject the value like any other unknown effort:

![hmz exec refusing :swarmmax on claude](/shots/user-efforts-noswarm.svg)

The app chip has no swarm toggle. Configure swarm mode in the terminal or on the command line; the app displays it with `swarm` at the end, such as **Max swarm**.

## Good to know

- The same effort word does not mean the same strength across harnesses. `high` on one harness is not equal to `high` on another.
- Picking a model in the terminal keeps the effort already set if the model takes it. Otherwise it jumps to the model's hardest effort (such as `ultracode` on Claude Code); lower it before saving if you want less. In the app, the effort falls back to **Default** instead, and the chip remembers the effort you last picked for each harness in this browser.
- A flow can read an agent's effort, but cannot change it.
- On `cursor-agent`, the effort is part of the model ID, so an effort is available only if your account lists that model at that effort.
- On `agy`, a model whose name ends in an effort, such as `gemini-3.7-flash-low`, runs at that effort only. Under a [gateway or LiteLLM account](/user/gateways), `agy` takes no effort for any model, so the **Effort** level is hidden and the model runs at its default.
- See [Coding agents](/user/agents) for the full agent grammar, [Nous: models, retries and fallback](/user/nous) for model retries and fallback, and [Cost and usage](/user/usage) for what harder efforts cost.
