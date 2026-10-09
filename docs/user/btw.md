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
const below = (status) => [
  '',
  { r: '[m]actor · claude/claude-opus-5-5:high · ● 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 1[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: status,
    keys: 'shift+tab switch view · / commands · shift+enter newline · ← monitor · ctrl+c stop',
  },
]
const inBtw = '[c]btw · btw agent[/][n]3[/] · [c]·|·[/] actor… [m](51s · ctrl+c twice to stop)[/]'

const asking = [
  {
    label: '1 · asked',
    lines: [
      ...before,
      {
        t: '[c]btw · btw agent[/][n]1[/] [dim]each line is a question; /btw or esc to exit[/][n]2[/]',
        hl: true,
      },
      ...below(inBtw),
    ],
    caption:
      'The run carries on. The actor never sees the question, and the status line says you are in btw mode.',
  },
  {
    label: '2 · answered',
    lines: [
      ...before,
      '[c]btw · btw agent[/] [dim]each line is a question; /btw or esc to exit[/]',
      '',
      {
        t:
          '[c]●[/] [dim]btw · ' +
          question +
          "[/][n]4[/] [c]The actor's next turn. The reviewer has taken 5 turns and reads the repository each time the actor finishes; the actor has been on the retry in charge() for 51s.[/]",
        hl: true,
      },
      ...below(inBtw),
    ],
    caption:
      'The answer lands in cyan in the transcript you are reading. Type the next question as a plain line.',
  },
  {
    label: '3 · esc',
    lines: [
      ...before,
      '[c]btw · btw agent[/] [dim]each line is a question; /btw or esc to exit[/]',
      '',
      "[c]●[/] [dim]btw · " + question + "[/] [c]The actor's next turn. …[/]",
      { t: '[dim]btw: exited[/][n]5[/]', hl: true },
      ...below('[c]·|·[/] actor… [m](58s · ctrl+c twice to stop)[/]'),
    ],
    caption: 'Out of btw mode. The side conversation is closed, and a line typed now steers again.',
  },
]
</script>

# Side questions — `/btw`

Ask about a flow without interrupting it. `/btw` opens a side conversation beside the run, with
an agent that can read the run but not change it. The flow's own agents never see what you ask
there.

::: info At a glance
- **You will** ask how a run is going, what an agent is doing, or why it did something, and
  get an answer in words.
- **Use it when** the transcript is too long to read, or you want an explanation rather than a
  change of course.
- **You need** a run in `hmz`, running or ended. [Your first run](/user/first-run) starts one.
:::

## Try it

While a flow is running, or after it has ended, type:

```text
❯ /btw what is the reviewer waiting for?
```

Press <kbd>esc</kbd> when you are done.

## How it works

A line you type into a running flow [steers](/user/steering) it: the agent hears it and acts
on it. A side question must never do that, so `/btw` sends it somewhere else: to a **side
conversation** that runs read-only, next to the run, and is closed when you leave.

`/btw` puts you in **btw mode**. From then on every line you type is one more question in the
same side conversation, so a follow-up can say "and then?". The status line starts with
`btw · <who>` for as long as you are in it.

Who answers depends on what is on the screen when you type `/btw`:

- **One conversation's transcript** (`btw · builder/2`): a side copy of that conversation.
  Where its CLI can fork a conversation (Claude Code, Codex, Grok Build, Kimi Code, MiMo Code,
  Oh My Pi, opencode, pi, Qwen Code, and a CLI you added that speaks ACP), the copy is a fork
  and knows everything the conversation knew. Otherwise, or if the fork fails, it is a fresh
  session of the same agent, given a snapshot of the run and what that role has done lately.
  This works for a conversation that has ended too, with no flow running.
- **Every agent's transcript, or the monitor** (`btw · btw agent`): the **btw agent**. It is
  the flow's first agent unless you chose another on the [General page of
  `/settings`](/user/settings#general). It is given a snapshot of the run and the list of
  its sessions, and it may put a question of its own to any session's side copy, up to 4 per
  question you ask. Each one shows as a dim `btw · asking <session>: …` line.

The snapshot holds:

- the flow, its task, and how long it has been going;
- each agent's model, how many turns it has taken, and whether it is working;
- the handovers between agents, and what the run has spent;
- the latest things the agents said and did, and what the flow printed.

## Example: ask what the reviewer is waiting for

An [`rlar`](https://humanfia.ai/flows/rlar) run has been going a few minutes. The actor is working and the
reviewer is idle, and you want to know why. You are on the transcript of every agent, so the
btw agent answers. Step through it:

<TermScreen title="hmz · rlar" :frames="asking" />

What to look at, by number:

1. **`btw · btw agent`.** Who is answering. On one conversation's transcript this names that
   conversation instead, such as `btw · reviewer/1`.
2. **`each line is a question; /btw or esc to exit`.** You are in btw mode now. A plain line
   typed from here is a question, not a steer.
3. **The status line** starts with `btw · btw agent` until you leave, so you cannot forget you
   are in it.
4. **The answer**, in cyan, behind your question in dim. It lands in the transcript you are
   reading, among the run's own lines, and nothing about the run changed.
5. **`btw: exited`.** <kbd>esc</kbd>, or `/btw` on its own, leaves btw mode and closes the side
   conversation.

### Check it worked

- The actor's `● 1` line is unchanged: it never saw the question.
- The answer is cyan and starts with `btw ·`, which no line of the run's own does.
- Once you leave, the status line no longer starts with `btw`.

## Variations

- **Ask about one conversation.** Press <kbd>←</kbd> for the [monitor](/user/monitor), walk to
  a session and press <kbd>enter</kbd> to read it, then type `/btw`. A fork of that
  conversation answers, so it remembers its own reasoning:

  ```text
  ❯ /btw what did you say, in three words?
  btw · assistant/1 each line is a question; /btw or esc to exit
  ● btw · what did you say, in three words? Build something great.
  ```

- **Enter first, ask after.** `/btw` on its own enters btw mode with no question yet.
- **Choose who answers from every agent's view.** Set **/btw agent** on the General page of
  `/settings`: the flow's first agent, one you chose, or `another…`, which asks for its CLI,
  account, model and effort. It takes effect the next time you enter btw mode.

## What a side conversation may do

Every side conversation runs read-only, with no skills, no goals and none of the flow's tools.
It can read the workspace, but it cannot change anything and it cannot steer the flow. Its
turns are real turns, though: they count against the run's [budget](/features/allowances).
They do not appear on the monitor or in the run's [trace](/user/tracing).

Starting a new flow, or closing `hmz`, also leaves btw mode.

## Troubleshooting

### `hmz: /btw requires a coding agent`

No btw agent is set, and no flow is set up here to borrow one from. Set one up with `/flow`,
or choose one as **/btw agent** in `/settings`.

### `hmz: /btw: no conversation found for <session>`

The conversation on the screen is gone, so there is nothing to copy. Read another one, or go to
every agent's transcript and ask the btw agent.

### `hmz: btw is still answering the last question`

Questions go one at a time. Wait for the answer, then ask again.

### `hmz: /btw: …`

The side question failed, for the reason given. The flow is not affected.

### The agent did what I asked in btw mode

It cannot: nothing in btw mode reaches the flow. If the agent changed course, the line was
typed outside btw mode. Check the status line starts with `btw` before you type.

## Next steps

- [Talking to a running turn](/user/steering): tell the agent something rather than ask.
- [Watching a run](/user/monitor): see the run's shape without asking.
- [Many conversations at once](/user/conversations): choose whose side copy answers.
- [TUI reference](/reference/tui): every command and key.
