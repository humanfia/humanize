<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const b = 'builder · claude/claude-opus-5-5:high · ● 1'
const t = 'tester · codex/gpt-5.6-sol:high · ● 1'
const below = [
  { r: '[m]input 58.3k · output 12.9k · cache_read 1.20M · cache_write 51.7k[/]' },
  { r: '[m]$3.02 · 64 out/s[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: '[c]·|·[/] builder, tester… [m](72s · ctrl+c twice to stop)[/]',
    keys: 'shift+tab switch view · / commands · shift+enter newline · ← monitor · ctrl+c stop',
  },
]
const said = {
  builder: [
    '',
    '[dim]● builder is working[/]',
    '',
    '[g]●[/] The parser takes nested lists now. Running the fixtures next.',
  ],
  tester: [
    '',
    '[dim]● tester is working[/]',
    '',
    '[g]●[/] Two new cases for empty input; both fail on main, as expected.',
  ],
}

const reading = [
  {
    label: 'reading builder',
    lines: [
      { t: '[dim]─ reading builder ─[/][n]1[/]', hl: true },
      '',
      '[dim]❯[/] take nested lists in the parser',
      ...said.builder,
      '',
      { r: `[m]${b} · reading[/][n]2[/]`, hl: true },
      { r: `[m]${t} · unread[/][n]3[/]` },
      ...below,
    ],
    caption:
      "Where a run lands: the agent of the first conversation it opens, drawn from the top. <code>unread</code> marks the other agent: it has said something you have not seen.",
  },
  {
    label: 'reading tester · conversation 1',
    lines: [
      { t: '[dim]─ reading tester · conversation 1 ─[/][n]4[/]', hl: true },
      ...said.tester,
      '',
      { r: `[m]${b}[/]` },
      { r: `[m]${t} · reading[/]`, hl: true },
      ...below,
    ],
    caption: 'The next conversation that is running, its own transcript.',
  },
  {
    label: 'reading builder · conversation 1',
    lines: [
      { t: '[dim]─ reading builder · conversation 1 ─[/]', hl: true },
      '',
      '[dim]❯[/] take nested lists in the parser',
      ...said.builder,
      '',
      { r: `[m]${b} · reading[/]`, hl: true },
      { r: `[m]${t}[/]` },
      ...below,
    ],
    caption:
      "One more <kbd>shift+tab</kbd> goes round to the builder's conversation. No transcript holds every agent at once: the monitor is where the whole run is watched.",
  },
]
</script>

# Many conversations at once

When a flow drives several agents, each conversation they hold gets a transcript of its own,
and each [outworlder](/user/questions) gets one of what it asks you. No transcript holds every
agent's lines at once. A run lands on the agent of the first conversation it opens; press
<kbd>shift+tab</kbd> to read the others one at a time, and <kbd>←</kbd> for [the
monitor](/user/monitor), where the whole run is watched.

::: info At a glance
- **You will** switch between the transcripts of the agents and conversations of a run, and
  read the marks that say who is working and who has news.
- **Use it when** a flow drives two or more agents, or one agent opens many conversations.
- **You need** a flow running in `hmz`. A flow with two agents, such as [`rlar`](https://humanfia.ai/flows/rlar),
  shows it best.
:::

## Try it

While a flow with several agents runs, press <kbd>shift+tab</kbd> with nothing typed. Press it
again to step on, and <kbd>tab</kbd> to step back.

## How it works

A **conversation** (a session) is one exchange with one agent kept across its turns. A flow
decides how many each agent holds: a reviewer that starts fresh every round opens a new one
each time, and a fan-out holds several at once. Every conversation gets a transcript of its
own, and so does each agent, with all of its conversations running down it.

When a run starts, the screen lands on the agent of the first conversation it opens, with what
you started it on at the top, and follows that agent into its later conversations. Before any
conversation opens, the screen shows only the interface's own lines.

What you are reading decides more than what is on the screen:

- **The transcript**, drawn from the top with a line saying whose it is.
- **Where a line you type goes.** See [Talking to a running turn](/user/steering).
- **Who answers [`/btw`](/user/btw)**: a side copy of that conversation, or the btw agent
  on the monitor.
- **What `/clear` clears**: only that transcript.

## Example: follow a builder and a tester

A project flow runs a `builder` and a `tester` side by side. Press the keys to step through the
transcripts, as <kbd>shift+tab</kbd> does:

<TermScreen title="hmz · @local/pair" :frames="reading" :keys="['shift+tab', 'tab']" />

What to look at, by number:

1. **`─ reading builder ─`.** You are on the builder's transcript, where the run landed,
   drawn from the top so it reads as a whole.
2. **One line per agent above the editor.** The name the flow gives it, what it runs as
   `cli/model:effort`, and `●` while it has a turn open. These stay whatever you read.
   `· reading` marks the agent whose transcript is on the screen.
3. **`· unread`** marks an agent that has said something since you last read it: the tester
   has been working while you read the builder.
4. **`─ reading tester · conversation 1 ─`.** One conversation's own transcript.

### Check it worked

- The line at the top of the transcript names the conversation you meant to read.
- The agent you are reading carries `· reading` above the editor.
- A line you type now goes to that conversation, or to the open turn of the agent you read.

## The keys

| Key | Reads |
| --- | --- |
| <kbd>shift+tab</kbd> | The next conversation that is running, then each outworlder of the flow, then round again. |
| <kbd>tab</kbd> | The one before. |
| <kbd>←</kbd>, then <kbd>enter</kbd> on a node | Any agent or conversation, working or not, picked on [the monitor](/user/monitor). |

<kbd>shift+tab</kbd> steps only between conversations that are running, so with ten agents it
skips the ones that are idle. Once you are reading a conversation, you stay on it after its
turn ends, until you press a key. To reach one that has ended, or an agent that has not
started yet, use the monitor.

An outworlder's transcript holds only what that outworlder puts to you, and a line typed there
answers it. See [Questions](/user/questions).

## What the lines above the editor say

Each line is one agent: the name the flow gives it, what it runs as `cli/model:effort`, and
then what it is holding.

| Mark | Means |
| --- | --- |
| `● 1` | It has a turn open. The number is how many conversations it holds. |
| `○ 2` | It is between turns, and holds two conversations. |
| `reading` | Its transcript is the one on the screen. |
| `unread` | It has said something since you last read it. |

## One agent, many conversations

An agent can hold many conversations. A Ralph loop opens a fresh one every round, and a
fan-out holds several at once. Each has a transcript of its own, numbered in the order the
agent opened them, and they all run down that agent's one transcript too, which is never wiped
when a new one opens. When an agent holds more than one, each turn says which:

```text
● agent is working · conversation 2 of 2
```

How many conversations each agent holds is up to the flow. See
[Many turns at once](/weaver/async-flows) and [Branching a conversation](/weaver/branching).

::: details How much the screen keeps
The last 32 transcripts, a conversation's going before an agent's, and the last 2,000 lines of
each. Anything older is gone from the screen but not from the run's [trace](/user/tracing).
:::

## Troubleshooting

### <kbd>shift+tab</kbd> skips the agent I want

It steps only between conversations with a turn open. Press <kbd>←</kbd> for the monitor,
walk to the agent or session, and press <kbd>enter</kbd>: that reads it whether it is working
or not.

### The transcript I was reading stopped moving

You are still on that conversation, and its turn has ended. A Ralph loop's next round is a new
conversation. Press <kbd>shift+tab</kbd> to go on to the one that is running, or read the
agent itself from the monitor, which follows it into each new conversation.

### A line I typed is still on the pin

A line typed on one conversation's transcript waits for that conversation's next turn, which a
loop that starts fresh every round never takes. Read the agent itself from the monitor,
which says to whichever of its conversations has a turn open, and type it again. See [Talking to a running turn](/user/steering#my-line-stays-on-the-pin-and-never-goes).

## Next steps

- [Watching a run](/user/monitor): every agent and conversation on one screen, to pick from.
- [Talking to a running turn](/user/steering): what a line typed here does.
- [Exporting a run](/user/export): package every conversation a run opened.
