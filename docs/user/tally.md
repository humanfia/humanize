<script setup>
import CostReadout from '../.vitepress/theme/components/user-agents/CostReadout.vue'
</script>

# Cost and rate

While a flow runs, a readout above the prompt says what it has spent so far, in tokens and in
dollars, and how fast it is spending. Glance at it to see what a run is costing before it ends.

## Try it

Run any flow. In `hmz`, once anything has been spent, the readout sits under the agent lines,
above the editor. Under `hmz exec`, each turn ends with a line of what that turn cost:

::: code-group

```text{3-4} [hmz]
                builder · claude/claude-opus-5:high · ● 1 · reading
                   reviewer · codex/gpt-5.6-sol:high · ○ 1 · unread
  input 12.4k · output 2.2k · cache_read 1.02M · cache_write 38.9k+
                                                   $1.34 · 91 out/s
```

```text{2} [hmz exec]
● Fixed the retry path in src/pay.py; the tests pass.
✻ input 1.2k · output 980 · cache_read 46.0k · cache_write 9.1k · $0.21 · claude-opus-5 · builder
```

:::

| Part | What it says |
| --- | --- |
| `input 12.4k` and the rest | tokens spent in the whole run, by kind. Each kind has its own price, so they are never added into one total |
| `+` after a figure | at least this much: some agent of the run does not report that kind |
| `$1.34` | what those tokens come to at list price, in US dollars |
| `91 out/s` | output tokens a second, over the last five minutes |

Press <kbd>esc</kbd> for [`/monitor`](/user/monitor), which splits the same figures by model.

## The `+`, and a missing `$`

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
nothing you type waits for it. Until the first fetch lands, the readout shows tokens only.

A model the list does not have shows its tokens and no money: a blank, never `$0.00`. Behind a
gateway, most models are like that.

Read the figure as what the work is worth at list price, not as your bill:

| | |
| --- | --- |
| **List price** | not what a subscription or a negotiated rate charges |
| **Standard tier** | a very long turn priced higher past some context length cost more than this says |
| **A floor** | a kind of token the list has no price for adds nothing |

`HUMANIZE_PRICES` changes where the list comes from. A list of your own must be in
OpenLLMPrices' format:

```sh
HUMANIZE_PRICES=off hmz                           # never fetch
HUMANIZE_PRICES=https://example.com/prices.json hmz   # fetch from here instead
HUMANIZE_PRICES=/srv/prices.json hmz                  # or read a file
```

## When it moves

The readout is worked out again every five seconds, and whenever an agent does anything. How
often new tokens reach it depends on the CLI:

| Backend | Tokens arrive |
| --- | --- |
| `claude`, `codex`, `dsh`, `kimi`, `zcode` | <Badge type="tip" text="during the turn" /> as each request to the model comes back |
| `agy`, `cursor-agent`, `grok`, `mimo`, `opencode`, `pi`, `qwen`, added CLIs | <Badge type="info" text="when the turn ends" /> all at once |

The rate counts seconds on the clock, so the time a flow spends between turns counts too: a
run that has stopped working reads as slowing down.

::: details Which kinds each backend reports

| Backend | Kinds |
| --- | --- |
| `claude`, `cursor-agent`, `dsh`, `grok`, `kimi`, `pi`, `qwen` | `input`, `output`, `cache_read`, `cache_write` |
| `mimo`, `opencode` | those four, and `reasoning` |
| `agy` | `input`, `output`, `cache_read`, `reasoning` |
| `codex` | `input`, `output`, and `cache_read` when it runs on this machine |
| `zcode` | `input`, `output` |

`reasoning` is listed only where a CLI counts it apart from the output. Everywhere else it is
inside `output`, and priced as output.

:::

## See also

- [Watching a run](/user/monitor): the same figures by model, beside the handover graph
- [Every run has a budget](/features/allowances): the same spending, as a cap on the whole run
- [A turn can be cut off](/features/budgets): the same spending, as a cap on one turn
- [Efforts](/user/efforts): a harder effort writes more output
- [Agents › What it has cost, and how fast](/reference/agents#what-it-has-cost-and-how-fast)
