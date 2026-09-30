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
    label: 'reading every agent',
    lines: [
      '[dim]── builder[/][n]1[/]',
      ...said.builder.slice(0, 2),
      '',
      '[dim]── tester[/]',
      ...said.tester.slice(0, 2),
      '',
      '[dim]── builder[/]',
      ...said.builder.slice(2),
      '',
      '[dim]── tester[/]',
      ...said.tester.slice(2),
      '',
      { r: `[m]${b}[/][n]2[/]` },
      { r: `[m]${t}[/]` },
      ...below,
    ],
    caption:
      "Where the screen opens: every agent's work in the order it happens, with a <code>── name</code> line wherever the speaker changes.",
  },
  {
    label: 'reading builder · conversation 1',
    lines: [
      { t: '[dim]─ reading builder · conversation 1 ─[/][n]3[/]', hl: true },
      ...said.builder,
      '',
      { r: `[m]${b} · reading[/][n]4[/]`, hl: true },
      { r: `[m]${t} · unread[/][n]5[/]` },
      ...below,
    ],
    caption:
      "One conversation's own transcript, drawn from the top. <code>unread</code> marks the other agent: it has said something you have not seen.",
  },
  {
    label: 'reading tester · conversation 1',
    lines: [
      { t: '[dim]─ reading tester · conversation 1 ─[/]', hl: true },
      ...said.tester,
      '',
      { r: `[m]${b}[/]` },
      { r: `[m]${t} · reading[/]`, hl: true },
      ...below,
    ],
    caption:
      'The next conversation that is running. One more <kbd>shift+tab</kbd> goes back to every agent.',
  },
]
</script>

# Many conversations at once

When a flow drives several agents, each conversation they hold gets a transcript of its own,
each [outworlder](/user/questions) gets one of what it asks you, and there is one more where
all of it appears together. The screen opens on that one, and goes back to it when a flow
starts. Press <kbd>shift+tab</kbd> to read one at a time.

::: info At a glance
- **You will** switch between the transcript of every agent and the transcript of one
  conversation, and read the marks that say who is working and who has news.
- **Use it when** a flow drives two or more agents, or one agent opens many conversations, and
  the combined transcript is hard to follow.
- **You need** a flow running in `hmz`. A flow with two agents, such as [`rlar`](/flows/rlar),
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

On top of those is the transcript of **every agent**: everything anybody says, in the order it
happens. It is where the screen opens and where a run is usually watched from.

What you are reading decides more than what is on the screen:

- **The transcript**, drawn from the top with a line saying whose it is.
- **Where a line you type goes.** See [Talking to a running turn](/user/steering).
- **Who answers [`/btw`](/user/btw)**: a side copy of that conversation, or the btw agent
  while you read every agent.
- **What `/clear` clears**: only that transcript.

## Example: follow a builder and a tester

A project flow runs a `builder` and a `tester` side by side. Press the keys to step through the
transcripts, as <kbd>shift+tab</kbd> does:

<TermScreen title="hmz · local/pair" :frames="reading" :keys="['shift+tab', 'tab']" />

What to look at, by number:

1. **`── builder`.** On the transcript of every agent, a line with the agent's name marks each
   place the speaker changes. Without it, two agents' lines would read as one voice.
2. **One line per agent above the editor.** The name the flow gives it, what it runs as
   `cli/model:effort`, and `●` while it has a turn open. These stay whatever you read.
3. **`─ reading builder · conversation 1 ─`.** You are on one conversation's own transcript,
   drawn from the top, so it reads as a whole.
4. **`· reading`** marks the agent whose transcript is on the screen.
5. **`· unread`** marks an agent that has said something since you last read it: the tester
   has been working while you read the builder.

### Check it worked

- The line at the top of the transcript names the conversation you meant to read.
- The agent you are reading carries `· reading` above the editor.
- A line you type now goes to that conversation. On every agent's transcript it goes to
  whichever turn is open.

## The keys

| Key | Reads |
| --- | --- |
| <kbd>shift+tab</kbd> | The next conversation that is running, then each outworlder of the flow, then round to every agent again. |
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

Nothing is marked `unread` while you read every agent, since everything is on that screen.

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
conversation. Press <kbd>shift+tab</kbd> to go on to the one that is running, or go back to
every agent.

### A line I typed is still on the pin

A line typed on one conversation's transcript waits for that conversation's next turn, which a
loop that starts fresh every round never takes. Go to every agent's transcript and type it
again. See [Talking to a running turn](/user/steering#my-line-stays-on-the-pin-and-never-goes).

## Next steps

- [Watching a run](/user/monitor): every agent and conversation on one screen, to pick from.
- [Talking to a running turn](/user/steering): what a line typed here does.
- [Exporting a run](/user/export): package every conversation a run opened.
