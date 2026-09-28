<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const b = 'builder · claude/claude-opus-5:high · ● 1'
const t = 'tester · codex/gpt-5.6-sol:high · ● 1'
const below = [
  { r: '[m]input 58.3k · output 12.9k · cache_read 1.20M+ · cache_write 51.7k+[/]' },
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
      '[dim]── builder[/]',
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
      { r: `[m]${b}[/]` },
      { r: `[m]${t}[/]` },
      ...below,
    ],
    caption:
      'Where the screen opens: every agent\'s work in the order it happens, with a <code>── name</code> line wherever the speaker changes.',
  },
  {
    label: 'reading builder · conversation 1',
    lines: [
      { t: '[dim]─ reading builder · conversation 1 ─[/]', hl: true },
      ...said.builder,
      '',
      { r: `[m]${b} · reading[/]`, hl: true },
      { r: `[m]${t} · unread[/]` },
      ...below,
    ],
    caption:
      'One conversation\'s own transcript, drawn from the top. <code>unread</code> marks the other agent: it has said something you have not seen.',
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
    caption: 'The next conversation that is running. One more <kbd>shift+tab</kbd> goes back to every agent.',
  },
]
</script>

# Many conversations at once

When a flow drives several agents, each conversation they hold gets a transcript of its own,
each [outworlder](/user/questions) gets one of what it asks you, and there is one more where
all of it appears together. The screen opens on that one, and goes back to it when a flow
starts. Press <kbd>shift+tab</kbd> to read one at a time.

## Try it

A project flow runs a `builder` and a `tester` side by side. Press the keys to step through
the transcripts, as <kbd>shift+tab</kbd> does:

<TermScreen title="hmz · local/pair" :frames="reading" :keys="['shift+tab', 'tab']" />

## The keys

| Key | Reads |
| --- | --- |
| <kbd>shift+tab</kbd> | The next conversation that is running, then each outworlder of the flow, then round to every agent again. |
| <kbd>tab</kbd> | The one before. |
| <kbd>←</kbd>, then <kbd>enter</kbd> on a box | Any agent or conversation, working or not, picked on [the monitor](/user/monitor). |

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
| `● 1` | It has a turn open, in one conversation. |
| `○ 2` | It is between turns, and holds two conversations. |
| `reading` | Its transcript is the one on the screen. |
| `unread` | It has said something since you last read it. |

Nothing is marked `unread` while you read every agent, since everything is on that screen.

## What "the agent you are reading" decides

- **The transcript**, drawn from the top with a line saying whose it is.
- **Where a line you type goes.** See [Talking to a running turn](/user/steering).
- **Who answers [`/btw`](/user/btw)**: a side copy of that agent's newest session, or the btw agent
  while you read every agent.
- **What `/clear` clears**: only that transcript.

## One agent, many conversations

An agent can hold many conversations. A Ralph loop opens a fresh one every round, and a
fan-out holds several at once. Each has a transcript of its own, numbered in the order the
agent opened them, and they all run down that agent's one transcript too, which is never wiped
when a new one opens. When an agent holds more than one, each turn says which:

```
● worker is working · conversation 2 of 3
```

::: details How much the screen keeps
The last 32 transcripts, a conversation's going before an agent's, and the last 2,000 lines of
each. Anything older is gone from the
screen but not from the run's [trace](/user/tracing).
:::

How many conversations each agent holds is up to the flow. See
[Many turns at once](/weaver/async-flows) and [Branching a conversation](/weaver/branching).

## See also

- [Watching a run](/user/monitor)
- [Talking to a running turn](/user/steering)
- [Exporting a run](/user/export), which packages every conversation a run opened
