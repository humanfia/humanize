<script setup>
import CostReadout from '../.vitepress/theme/components/user-agents/CostReadout.vue'
</script>

# Cost and rate

While a flow runs, humanize counts what it has spent, in tokens and in dollars, and how fast it
is spending. Use this page to read those figures: to see what a run is costing before it ends,
to compare two agents or two efforts, and to know when a figure is short of the whole truth.

## Try it

Run any flow for one turn:

```sh
hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:low \
    "Name the three primary colours, one line."
```

The turn ends with a line of what it cost:

```text
✻ input 10 · output 136 · cache_read 13.9k · cache_write 6.9k · $0.01 · claude-haiku-4-5-20251001 · assistant
```

## Before you start

- humanize is [installed](/user/installation) and a coding agent CLI is signed in.
- For money as well as tokens, open `hmz` once on this machine: the interface is what fetches
  the price list. Until it has, every figure is tokens only.

## What is counted

Every turn an agent takes spends tokens of up to five **kinds**, and each kind has its own
price, so humanize keeps them apart rather than adding them into one total:

| Kind | Is |
| --- | --- |
| `input` | what the agent was sent, fresh |
| `output` | what the model wrote, reasoning included unless the CLI counts it apart |
| `cache_read` | input the provider had cached from an earlier request, usually the bulk of a long turn and the cheapest |
| `cache_write` | input written into that cache, priced a little above `input` |
| `reasoning` | thinking, where a CLI counts it apart from the output. Priced as output |

The money is those tokens at list price, in US dollars, from a public price list. The rate is
output tokens a second over the last five minutes. You see all three in two places: a line per
turn under `hmz exec`, and a running readout above the prompt in `hmz`.

## Example: read a turn's line under `hmz exec`

```text
✻ input 10 · output 136 · cache_read 13.9k · cache_write 6.9k · $0.01 · claude-haiku-4-5-20251001 · assistant
  ①          ②            ③                  ④                  ⑤       ⑥                           ⑦
```

### What each part means

1. **`input 10`**: fresh input for this turn. Small, because almost all of what an agent is
   sent is its system prompt and history, which the provider caches.
2. **`output 136`**: what the model wrote. This is the figure a harder
   [effort](/user/efforts) makes grow, and the one `-b output_tokens=` caps.
3. **`cache_read 13.9k`**: cached input read back. Large but cheap: at Claude Haiku's list
   price it is a tenth of `input`.
4. **`cache_write 6.9k`**: input the provider cached this turn, to read back on the next one.
5. **`$0.01`**: what the turn's tokens come to at list price. Under a cent it shows four
   places, as in `$0.0062`, so a turn that cost something never reads `$0.00`.
6. **The model** that took the turn, as the CLI named it.
7. **The role** it filled. In a flow with several agents, this is how you tell their lines
   apart.

A flow with two roles prints one such line per turn, per role. This is a real
[`rlar`](/flows/rlar) run of two turns each, with the reviewer checking the actor's fix:

```text
✻ input 26 · output 376 · cache_read 55.6k · cache_write 7.3k · $0.02 · claude-haiku-4-5-20251001 · actor
✻ input 100 · output 2.7k · cache_read 248.4k · cache_write 25.1k · $0.07 · claude-haiku-4-5-20251001 · reviewer
✻ input 10 · output 298 · cache_read 21.2k · cache_write 327 · $0.0040 · claude-haiku-4-5-20251001 · actor
✻ input 114 · output 2.6k · cache_read 322.6k · cache_write 6.1k · $0.05 · claude-haiku-4-5-20251001 · reviewer
```

The reviewer read several times what the actor did, and cost several times as much: it is the
role to give a cheaper model or a lower effort, not the actor.

## Example: watch the readout in `hmz`

In the interface, once anything has been spent, the readout sits under the agent lines, above
the editor. This one is a single [`chat`](/flows/chat) agent a minute in:

```text
                     assistant · claude/claude-haiku-4-5-20251001:low · ● 1   ①
                                                human · outworlder · asking
               input 20 · output 532 · cache_read 27.7k · cache_write 13.8k   ②
                                                           $0.02 · 15 out/s   ③
```

### What each part means

1. **The agent lines**: each role, what fills it, and its sessions. The readout below them is
   for the whole run, every agent together.
2. **The token kinds**, summed over the run so far. A `+` after a figure means *at least this
   much*: see [The `+`, and a missing `$`](#the-and-a-missing).
3. **`$0.02`** is the run so far at list price. **`15 out/s`** is output tokens a second over
   the last five minutes, so it falls while the agent waits on you or on a slow tool.

Press <kbd>←</kbd> for [the monitor](/user/monitor), which splits the same figures by model.

## Check that it worked

- Under `hmz exec`, every finished turn has a `✻` line. With `--json`, the turn's `result`
  object carries the same figures as `tokens` (by model) and `spent` (by kind):
  `"spent":{"cache_write":3426.0,"output":400.0,"cache_read":38448.0,"input":18.0}`.
- In `hmz`, the readout appears as soon as the first tokens are reported, and the `$` once the
  price list has been fetched.
- `~/.humanize/prices.json` exists once the list has been fetched.

## The `+`, and a missing `$` {#the-and-a-missing}

Switch agents in and out of the run to see how the readout marks what it cannot count:

<CostReadout />

- **A `+` after a kind** means some agent's CLI does not report that kind, so the figure holds
  only the others'. With one agent there is nothing to be short of, and nothing is marked.
- **A `+` after the money** means some model has no price, so its tokens add nothing to it.
- **No `$` at all** means no model of the run has a price.

A `+` also appears on every kind when a CLI reports some tokens without saying which kind they
were.

## The money

The prices come from [OpenLLMPrices](https://openllmprices.com/) and are kept in
`~/.humanize/prices.json`. `hmz` refreshes the list in the background about once a day, and
nothing you type waits for it. `hmz exec` reads what is kept and never fetches.

A model the list does not have shows its tokens and no money: a blank, never `$0.00`. Behind a
gateway, most models are like that.

Read the figure as what the work is worth at list price, not as your bill:

| | |
| --- | --- |
| **List price** | not what a subscription or a negotiated rate charges |
| **Standard tier** | a very long turn priced higher past some context length cost more than this says |
| **A floor** | a kind of token the list has no price for adds nothing |

## Variations

### Use another price list

`HUMANIZE_PRICES` changes where the list comes from. A list of your own must be in
OpenLLMPrices' format:

```sh
HUMANIZE_PRICES=off hmz                               # never fetch
HUMANIZE_PRICES=https://example.com/prices.json hmz   # fetch from here instead
HUMANIZE_PRICES=/srv/prices.json hmz                  # or read a file
```

### Cap the spending rather than watch it

The same figures are what a budget stops on. `-b cost=5` stops the run at five dollars,
`-b output_tokens=200k` at that many written tokens. See
[Every run has a budget](/features/allowances).

## When it moves

The readout is worked out again every five seconds, and whenever an agent does anything. How
often new tokens reach it depends on the CLI:

| Backend | Tokens arrive |
| --- | --- |
| `claude`, `codex`, `dsh`, `kimi`, `mcode` | <Badge type="tip" text="during the turn" /> as each request to the model comes back |
| `agy`, `cursor-agent`, `grok`, `mimo`, `opencode`, `pi`, `qwen`, added CLIs | <Badge type="info" text="when the turn ends" /> all at once |

What an agent of Claude Code's own (its `Agent` tool) spends is the exception: Claude says it
only when the turn ends, so it arrives then, and a budget that is not graceful cannot stop a
turn while one of those is working.

The rate counts seconds on the clock, so the time a flow spends between turns counts too: a
run that has stopped working reads as slowing down.

::: details Which kinds each backend reports

| Backend | Kinds |
| --- | --- |
| `claude`, `cursor-agent`, `dsh`, `grok`, `kimi`, `mcode`, `pi`, `qwen` | `input`, `output`, `cache_read`, `cache_write` |
| `mimo`, `opencode` | those four, and `reasoning` |
| `agy` | `input`, `output`, `cache_read`, `reasoning` |
| `codex` | `input`, `output`, and `cache_read` when it runs on this machine |

`reasoning` is listed only where a CLI counts it apart from the output. Everywhere else it is
inside `output`, and priced as output.

:::

## Pitfalls

- **No `$` under `hmz exec`.** The price list has never been fetched on this machine. Open
  `hmz` once and leave it a few seconds, or point `HUMANIZE_PRICES` at a copy.
- **`nobody lists a price for <model>, so cost=… cannot stop what it spends`.** A `cost` cap
  cannot stop a model that has no price. Add `duration` or `output_tokens` to the budget.
- **The count sits still, then jumps.** That CLI reports when the turn ends. See the table
  above, and [Troubleshooting](/user/troubleshooting).
- **The rate falls to nothing.** The flow is waiting, on you or between turns. It is a rate
  over the clock, not over work.

## Next steps

- [Watching a run](/user/monitor): the same figures by model, beside the handover graph
- [Every run has a budget](/features/allowances): the same spending, as a cap on the whole run
- [A turn can be cut off](/features/budgets): the same spending, as a cap on one turn
- [Efforts](/user/efforts): a harder effort writes more output
- [Agents › What it has cost, and how fast](/reference/agents#what-it-has-cost-and-how-fast)
