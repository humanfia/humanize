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
    keys: 'tab agent · / commands · shift+enter newline · esc monitor · ctrl+c stop',
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
    label: 'reading builder',
    lines: [
      { t: '[dim]─ reading builder ─[/]', hl: true },
      ...said.builder,
      '',
      { r: `[m]${b} · reading[/]`, hl: true },
      { r: `[m]${t} · unread[/]` },
      ...below,
    ],
    caption:
      'One agent\'s own transcript, drawn from the top. <code>unread</code> marks the other agent: it has said something you have not seen.',
  },
  {
    label: 'reading tester',
    lines: [
      { t: '[dim]─ reading tester ─[/]', hl: true },
      ...said.tester,
      '',
      { r: `[m]${b}[/]` },
      { r: `[m]${t} · reading[/]`, hl: true },
      ...below,
    ],
    caption: 'The next agent that is working. One more <kbd>tab</kbd> goes back to every agent.',
  },
]
</script>

# Many conversations at once

When a flow drives several agents, each one gets a transcript of its own, and there is one
more where all their work appears together. The screen opens on that one. Press
<kbd>tab</kbd> to read one agent at a time.

## Try it

A project flow runs a `builder` and a `tester` side by side. Press the keys to step through
the transcripts, as <kbd>tab</kbd> does:

<TermScreen title="hmz · local/pair" :frames="reading" :keys="['shift+tab', 'tab']" />

## The keys

| Key | Reads |
| --- | --- |
| <kbd>tab</kbd> | The next agent that is working, then round to every agent again. |
| <kbd>shift+tab</kbd> | The one before. |
| <kbd>esc</kbd>, then <kbd>enter</kbd> on a box | Any agent, working or not, picked on [`/monitor`](/user/monitor). |

<kbd>tab</kbd> steps only between agents that are working, so with ten agents it skips the ones
that are idle. Once you are reading an agent, you stay on it after its turn ends, until you
press a key. To reach one that has stopped, or has not started yet, use `/monitor`.

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
- **Which agent answers [`/btw`](/user/btw).**
- **What `/clear` clears**: only that transcript.

## One agent, many conversations

An agent can hold many conversations. A Ralph loop opens a fresh one every round, and a
fan-out holds several at once. They all run down that agent's one transcript, and the screen
is never wiped when a new one opens. When an agent holds more than one, each turn says which:

```
● worker is working · conversation 2 of 3
```

::: details How much the screen keeps
The last 16 transcripts, and the last 2,000 lines of each. Anything older is gone from the
screen but not from the run's [trace](/user/tracing).
:::

How many conversations each agent holds is up to the flow. See
[Many turns at once](/weaver/async-flows) and [Branching a conversation](/weaver/branching).

## See also

- [Watching a run](/user/monitor)
- [Talking to a running turn](/user/steering)
- [Exporting a run](/user/export), which packages every conversation a run opened
