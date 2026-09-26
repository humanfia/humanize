<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const question = 'what is the reviewer waiting for?'
const before = [
  '[dim]── actor[/]',
  '',
  '[dim]● actor is working[/]',
  '',
  '[dim]❯[/] /btw ' + question,
]
const below = [
  '',
  { r: '[m]actor · claude/claude-opus-5:high · ● 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 1[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: '[c]·|·[/] actor… [m](51s · ctrl+c twice to stop)[/]',
    keys: 'tab agent · / commands · shift+enter newline · esc monitor · ctrl+c stop',
  },
]

const asking = [
  {
    label: 'asked',
    lines: [
      ...before,
      { t: '[dim]btw: checking the flow for ' + question + '…[/]', hl: true },
      ...below,
    ],
    caption: 'The run carries on. The actor never sees the question.',
  },
  {
    label: 'answered',
    lines: [
      ...before,
      '[dim]btw: checking the flow for ' + question + '…[/]',
      '',
      {
        t:
          '[c]●[/] [dim]btw · ' +
          question +
          "[/] The actor's next turn. The reviewer has taken 5 turns and reads the repository each time the actor finishes; the actor has been on the retry in charge() for 51s.",
        hl: true,
      },
      ...below,
    ],
    caption:
      'The answer lands in the transcript you are reading, behind a cyan <code>●</code> and <code>btw ·</code>.',
  },
]
</script>

# Side questions — `/btw`

Ask about a running flow without interrupting it. `/btw` answers from what the run has done so
far, and the flow's own agents never see the question.

## Try it

While a flow is running, type:

```
/btw what is the reviewer waiting for?
```

<TermScreen title="hmz · rlar" :frames="asking" />

Ask as many as you like. Up to four can be in progress at once.

## What answers it

A read-only copy of one of the run's agents, the one you are reading if you are reading one. It
answers from a snapshot of the run:

- the flow, its task, and how long it has been going;
- each agent's model, how many turns it has taken, and whether it is working;
- the handovers between agents, and what the run has spent;
- the latest things the agents said and did, and what the flow printed.

It can read the workspace, but it cannot change anything and it cannot steer the flow. It is a
real turn, though, and it counts against the run's [budget](/features/allowances). It does not
appear on [`/monitor`](/user/monitor) or in the run's [trace](/user/tracing).

To tell the agent something rather than ask about it, type the line without `/btw`. See
[Talking to a running turn](/user/steering).

## When it says no

| You see | Because |
| --- | --- |
| `hmz: /btw needs a flow that is running` | Nothing is running. Start a flow first. |
| `hmz: /btw needs a coding agent that supports read-only turns` | The run has no coding agent to copy. |
| `hmz: /btw already has 4 questions in progress` | Wait for one of the four to answer. |
| `hmz: usage: /btw <question>` | There was no question after `/btw`. |
| `hmz: /btw: …` | The side question failed. The flow is not affected. |

## See also

- [Watching a run](/user/monitor)
- [Talking to a running turn](/user/steering)
