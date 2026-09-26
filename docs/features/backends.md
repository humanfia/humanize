---
pageClass: hmz-feature
---

# Many backends, one agent

humanize drives twelve coding agent CLIs, and any other CLI that speaks the Agent Client
Protocol. Each one runs under a login you already have, so most need no API key. A flow names
its **roles**, and you pick the backend that plays each one. If the backend cannot do what the
role needs, the run is refused before it starts, not an hour in.

<HmzBackends />

Two of them need an extra when you install humanize: DeepSeek Harness (`dsh`) and Kimi Code
(`kimi`). See [Installation](/user/installation).

## An agent is four things

<div class="anatomy" role="img" aria-label="claude@work/claude-opus-5:high: the backend claude, the account work, the model claude-opus-5, the effort high">
  <span class="part cli"><code>claude</code><em>backend</em></span>
  <span class="part acct"><code>@work</code><em>account</em></span>
  <span class="part model"><code>/claude-opus-5</code><em>model</em></span>
  <span class="part effort"><code>:high</code><em>effort</em></span>
</div>

- The **backend** is the CLI.
- The **account** is who its turns run as. Leave it out, and the agent runs as whoever the CLI
  is signed in as on this machine. See [Two accounts of one CLI](/features/accounts).
- The **model** is any model that account can run.
- The **effort** is a rung of that backend's ladder.

Two agents spelled the same are still two agents. A flow's actor and its reviewer can share one
spelling and still keep separate conversations.

## The models on offer are the account's {#what-it-runs-is-discovered-for-the-account}

Which models you can run depends on the subscription, key or gateway, so humanize asks rather
than guesses:

- **It asks as the account.** Two accounts of one CLI can offer two different lists.
- **An account on a gateway is asked the gateway.** Its list is what that endpoint serves,
  under the ids it serves them by. pi, opencode, mimocode and Cursor Agent are asked
  themselves.
- **It asks once, when you make the account,** and keeps the answer with the account. Opening
  a menu never starts a CLI or reaches the network. The list is refreshed when you ask it
  again, on [Providers](/user/providers).

DeepSeek Harness and Qwen Code cannot list their models. Until an endpoint of theirs is asked,
you are offered the short list each one ships pointed at.

## Efforts are the backend's own words {#the-efforts-are-a-vocabulary-so-they-are-written-down}

Each backend has a ladder, hardest first, and each model offers only the rungs it takes. Pick a
backend above to see its ladder.

| You write | What happens |
| --- | --- |
| a rung on the ladder | The model thinks that hard. |
| `auto` | humanize says nothing about effort, and the model runs at its CLI's default. |
| a rung that is not on the ladder | The agent is refused before the run starts. A CLI of your own is the exception: it takes any word, and runs as you configured it. |

Two of them are worth knowing by name. Claude Code's `ultracode` is `xhigh` with the turn
orchestrating a fleet of its own. Kimi Code's `swarm` prefix, as in `swarmmax`, runs the same
thinking across a fleet of agents instead of one. See [Efforts](/user/efforts) for choosing
one.

## Your skills, and a flow's

The skills you installed are read where each CLI reads them. humanize never rewrites or
switches off any of them.

A flow can bring skills of its own. They are put where the backend reads them for the length
of a session, then taken away. pi, DeepSeek Harness and a CLI of your own take none of a flow's
skills; their turns run without them. See [Skills](/user/skills).

## Adding a CLI of your own {#adding-a-cli-of-your-own}

Anything that speaks the Agent Client Protocol becomes a backend the moment you add it. It is
named by the command that starts it. Its model and effort are whatever you configured it with,
so humanize offers one rung, `as configured`, and sends nothing.

From then on it is a backend like any other. A role can name it, and a [fallback](/user/fallback)
step can point to it or away from it.

## Where the detail is

- [Efforts](/user/efforts) · [Permissions](/user/permissions) · [Skills](/user/skills) ·
  [Providers](/user/providers)
- [Providers reference](/reference/providers): every way into each backend, and adding a CLI
- [Agents reference](/reference/agents): what each backend does, exactly

<style>
.anatomy {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 18px 0 20px;
  font-size: 15px;
}

.anatomy .part {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.anatomy .part code {
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 15px;
  color: var(--vp-c-text-1);
}

.anatomy .part em {
  font-style: normal;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.anatomy .cli code {
  background: color-mix(in srgb, var(--hmz-lane-1) 20%, transparent);
}

.anatomy .acct code {
  background: color-mix(in srgb, var(--hmz-lane-2) 20%, transparent);
}

.anatomy .model code {
  background: color-mix(in srgb, var(--hmz-lane-3) 20%, transparent);
}

.anatomy .effort code {
  background: color-mix(in srgb, var(--hmz-lane-4) 22%, transparent);
}
</style>
