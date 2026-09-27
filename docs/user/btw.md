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
    l: '[c]btw · btw agent[/] · [c]·|·[/] actor… [m](51s · ctrl+c twice to stop)[/]',
    keys: 'tab agent · / commands · shift+enter newline · esc monitor · ctrl+c stop',
  },
]

const asking = [
  {
    label: 'asked',
    lines: [
      ...before,
      { t: '[c]btw · btw agent[/] [dim]each line is a question; /btw or esc leaves[/]', hl: true },
      ...below,
    ],
    caption: 'The run carries on. The actor never sees the question, and the status line says you are in btw mode.',
  },
  {
    label: 'answered',
    lines: [
      ...before,
      '[c]btw · btw agent[/] [dim]each line is a question; /btw or esc leaves[/]',
      '',
      {
        t:
          '[c]●[/] [dim]btw · ' +
          question +
          "[/] [c]The actor's next turn. The reviewer has taken 5 turns and reads the repository each time the actor finishes; the actor has been on the retry in charge() for 51s.[/]",
        hl: true,
      },
      ...below,
    ],
    caption:
      'The answer lands in cyan in the transcript you are reading. Type the next question as a plain line.',
  },
]
</script>

# Side questions — `/btw`

Ask about a flow without interrupting it. `/btw` opens a side conversation beside the run. The
flow's own agents never see what you ask there.

## Try it

While a flow is running, or after it has ended, type:

```
/btw what is the reviewer waiting for?
```

<TermScreen title="hmz · rlar" :frames="asking" />

This puts you in btw mode. The status line starts with `btw · <who>`. Every line you type is
now one more question in the same side conversation, so follow-ups can say "and then?". `/btw`
on its own does the same without a first question.

To leave, type `/btw` again or press <kbd>esc</kbd>. Leaving closes the side conversation.
Starting a new flow or closing `hmz` also leaves btw mode.

## Who answers

It depends on the view you are in when you type `/btw`.

**In one session's view**, a side copy of that session answers:

- If its CLI can fork a conversation (Claude, Codex, Kimi, OpenCode, Pi), the side copy is a
  fork of the session. It knows everything the session knew.
- Otherwise, or if the fork fails, it is a fresh session of the same agent. It is given a
  snapshot of the run and what that role has done lately.

This also works for a session that has ended, even with no flow running. Pick it on the
[monitor](/user/monitor) and type `/btw`.

**In the view of every agent, or on the monitor**, the **btw agent** answers. By default it is
the flow's first agent. You can choose another in [`/settings`](/reference/tui#what-humanize-remembers)
(the **btw agent** row, which takes effect the next time you enter btw mode). It is given a
snapshot of the run and the list of its sessions. It can ask any session's side copy a
question of its own, up to 4 per question you ask. Each one it asks is shown as a dim
`btw · asking <session>: …` line.

The snapshot holds:

- the flow, its task, and how long it has been going;
- each agent's model, how many turns it has taken, and whether it is working;
- the handovers between agents, and what the run has spent;
- the latest things the agents said and did, and what the flow printed.

Every side conversation runs read-only, with no skills, no goals and none of the flow's tools.
It can read the workspace, but it cannot change anything and it cannot steer the flow. Its
turns are real turns, though, and they count against the run's
[budget](/features/allowances). They do not appear on the monitor or in the run's
[trace](/user/tracing).

To tell the agent something rather than ask about it, leave btw mode and type the line. See
[Talking to a running turn](/user/steering).

## When it says no

| You see | Because |
| --- | --- |
| `hmz: /btw needs a coding agent to ask` | No btw agent is set, and no flow is set up to copy one from. |
| `hmz: /btw: <session> has no conversation to ask` | That session is gone. |
| `hmz: btw is still answering the last question` | Wait for the answer, then ask again. |
| `hmz: /btw: …` | The side question failed. The flow is not affected. |

## See also

- [Watching a run](/user/monitor)
- [Talking to a running turn](/user/steering)
