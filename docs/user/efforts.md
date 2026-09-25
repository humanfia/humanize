# Efforts

An agent is a backend, a model and an **[effort](/reference/agents#efforts)**: how hard to
think. Set one when a task needs more or less thought than the agent's default.

```
claude / claude-opus-4-8 : high
  │           │            └── effort
  │           └── model
  └── backend
```

The word belongs to each backend rather than to humanize, so the values differ.

## Try it

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 "fix the build"
```

The `effort` row of the agent's sheet shows `high`, with `↔` beside it for a row that is
adjusted where it stands. Press **←/→** to step it, or **space** to take the next one round;
the `swarm` row turns swarm mode on for a model that has one.

## Set the effort

`backend/model:effort` is how an agent carries one on a command line — the effort last, after
the last colon, however many slashes the model's own name has in it. An agent configured in
Python takes the same word:

::: code-group

```sh [command line]
hmz exec -f ralph_loop -a agent=kimi/kimi-code/k3:swarmmax -b cost=5 "fix the build"
```

```python [Python]
ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
```

:::

## `auto` — no effort at all

Not every model has rungs. Cursor runs `composer-2.5`, `gemini-3.1-pro` and `auto` at one
setting and no other, Antigravity has models with no variants, and a gateway will serve plenty
that reason one way only. An agent is written `backend/model:effort` wherever anything names
one, so a model with no rung had nothing to write after the colon — and could not be named on
a command line at all.

`auto` is that nothing, spelled:

```sh
hmz exec -f ralph_loop -a agent=cursor-agent/composer-2.5:auto -b cost=5 "fix the build"
```

It is not a rung on anybody's ladder. It says humanize tells the CLI nothing about how hard to
think, which leaves the model wherever your account leaves it — so it is also the way to ask
for a backend's own default rather than one of the words below.

## Efforts by backend

humanize does not check an effort against a list: a value your account has but this page does
not still works. These are the backends whose ladders need explaining; the whole set is in
[Agents › Efforts](/reference/agents#efforts).

| Backend | Efforts, hardest first |
| --- | --- |
| Claude Code | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| Codex | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` — each model takes its own subset |
| Kimi Code | `max`, `high`, `medium`, `low`, each also as `swarm…` |
| pi | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| opencode, mimocode | the model variant: `xhigh`, `high`, `medium`, `low`, `minimal` |
| ZCode | `max`, `high`, `low`, `enabled`, `nothink`, `disabled` — two vocabularies, and a model takes one of them |
| *every backend* | `auto` — no effort at all, the model left at its own default |

- **`ultracode`** is Claude Code's `xhigh` thinking with the turn opted into orchestrating a
  fleet of its own, so it sits above `max`. It is real and undocumented, and no listing the CLI
  answers with will ever name it. humanize keeps it anyway.
- **Kimi Code's effort says how wide as well as how hard.** `max` is one agent; `swarmmax` is
  the same thinking at the width of a fleet of subagents. The prefix is exported as
  `hmz.coganchor.agents.SWARM`, and a flow reads an agent's effort as `agent.effort`.
- **pi's `off`** is the model asked not to think at all — the least of the efforts, not the
  absence of a setting.
- **Codex's models differ from each other.** `gpt-5.6-sol` takes `ultra`; `gpt-5.5` does not,
  so the interface offers each model only the efforts it takes.
- **ZCode's ladder is two vocabularies in one.** The models that take a thinking budget answer
  `max`, `high` and `low`, with `nothink` at the bottom; the ones that only take
  thinking-or-not answer `enabled` and `disabled`. Each model is offered the rungs it said it
  takes, and no model takes both halves.

## Change the effort while an agent runs

The rest of this page is for whoever drives agents from Python. A flow's agent runs at the
effort its `-a` said, which the flow reads as `agent.effort` and has no way of moving.

A config is frozen. A session resumes under the settings it opened with, and a config that
changed mid-run would silently split one conversation across two models. The effort is the one
setting that may move as it goes:

```python
builder.effort = "low"              # every session of this agent, from its next turn
session.effort = "max"              # this conversation alone
session.effort = ""                 # and back to whatever the agent runs at
```

A `swarm` prefix moves with it: `agent.effort = "swarmmax"`. Read it back through the same
property:

| | |
| --- | --- |
| `agent.config.effort` | what the agent was **configured** with |
| `agent.effort` | what its turns actually **run at** |

**The change takes hold on the next turn.** The turn already under way keeps the effort it
started at: a model does not think harder halfway through an answer. How it lands is the
backend's own business:

| Backend | How the new effort reaches the model |
| --- | --- |
| Codex, Kimi Code, opencode, mimocode | sent with each turn |
| Claude Code | an argument of the process it is held open as, so that process ends and the conversation resumes in one started at the new effort |
| pi | it has a command for it, and is told |
| ZCode | its app server keeps the level on the session, and is told the new one before the next turn |

## What to steer by

The reading that responds to effort is **`juice()`**: output tokens an average turn *of the
model* came out with. A model asked to think harder writes more in each answer, so that average
is what an effort moves.

```python
agent.juice(over=60)
```

A loop driving an agent from Python can govern on it — moving the effort a rung a round to
hold the agent to a target. A flow cannot: the flow API hands a flow an agent's effort to read,
`agent.effort`, and no way to move it while it runs.

## See also

- [Cost and rate](/user/tally)
- [Permissions](/user/permissions) — what an agent may do, which its flow says
- [Agents › Efforts](/reference/agents#efforts)
