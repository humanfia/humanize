<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const working = [
  '[dim]── actor[/]',
  '',
  '[dim]● actor is working[/]',
  '',
  "[g]●[/] Starting with the retry in charge(), then I'll run the suite.",
]
const agents = [
  { r: '[m]actor · claude/claude-opus-5-5:high · ● 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 1[/]' },
  { r: '[m]input 41.2k · output 18.9k · cache_read 1.71M · cache_write 72.4k[/]' },
]
const spent = '[m]$4.12 · 38 out/s[/]'
const status = '[c]·|·[/] actor… [m](43s · ctrl+c twice to stop)[/]'
const keys = 'shift+tab switch view · / commands · shift+enter newline · ← monitor · ctrl+c stop'

const steer = [
  {
    label: '1 · type',
    lines: [
      ...working,
      '',
      { r: '[m]actor · claude/claude-opus-5-5:high · ● 1[/][n]1[/]' },
      agents[1],
      agents[2],
      { r: spent },
      { rule: true },
      { prompt: 'and fix the tests too[n]2[/]' },
      { rule: true },
      {
        l: status,
        keys: 'enter send · shift+tab switch view · / commands · shift+enter newline · ← monitor · ctrl+c clear',
      },
    ],
    caption:
      'The actor is in the middle of a turn. You type as you would to start one; the status line offers <kbd>enter</kbd> send.',
  },
  {
    label: '2 · pinned',
    lines: [
      ...working,
      '',
      ...agents,
      { l: '[m]❯ and fix the tests too · with actor[/][n]3[/]', r: spent, hl: true },
      { rule: true },
      { prompt: '' },
      { rule: true },
      { l: status, keys },
    ],
    caption:
      'Sent. The line is pinned above the editor, saying which agent has it, until that agent says the words are in front of it.',
  },
  {
    label: '3 · taken',
    lines: [
      ...working,
      '',
      { t: '[dim]❯[/] and fix the tests too[n]4[/]', hl: true },
      '',
      '[g]●[/] Will do. Two of the tests still assert three retries; updating them too.[n]5[/]',
      '',
      ...agents,
      { r: spent },
      { rule: true },
      { prompt: '' },
      { rule: true },
      { l: status, keys },
    ],
    caption:
      'Taken. The line moves into the transcript, and the same turn carries on with it in mind.',
  },
]

const refused = [
  {
    label: 'cursor-agent',
    lines: [
      '[dim]── actor[/]',
      '',
      '[dim]● actor is working[/]',
      '[r]hmz: CursorSession cannot be talked to mid-turn[/][n]1[/]',
      '',
      { r: '[m]actor · cursor-agent/composer-2.5:auto · ● 1[/]' },
      { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 1[/]' },
      { r: '[m]input 22.8k · output 6.3k · cache_read 402.1k · cache_write 18.0k[/]' },
      { l: '[m]❯ and fix the tests too[/][n]2[/]', r: '[m]$0.91 · 52 out/s[/]', hl: true },
      { rule: true },
      { prompt: '' },
      { rule: true },
      { l: status, keys },
    ],
  },
]
</script>

# Talking to a running turn

While an agent is working, type a line and press <kbd>enter</kbd>. The line goes into the turn
that is running, and the agent takes it into account without starting over. There is no mode
to switch into and no key to hold.

::: info At a glance
- **You will** add to, correct or redirect what an agent is doing, without stopping the run.
- **Use it when** the agent has gone the wrong way, missed part of the task, or needs a fact
  only you have.
- **You need** a flow running in `hmz`. [Your first run](/user/first-run) starts one.
:::

## Try it

While a turn is running, type at the prompt and press <kbd>enter</kbd>:

```text
❯ and fix the tests too
```

## How it works

A **turn** is one exchange with an agent: it is given something, works with its tools, and
answers. A flow is a loop of turns, and most of the time one of them is open. What you type at
the prompt while it is open is not a new task. It is something said to the agent in the middle
of its work, the way you would lean over and say it to a colleague.

Three things happen to the line, in order:

1. **It is pinned.** It appears above the editor, dim, with the agent that has it. Nothing is
   lost if the agent is busy: the pin is a queue.
2. **It is taken.** Once the agent's CLI confirms the words are in front of the model, the line
   leaves the pin and appears in the transcript, where the agent's own words are.
3. **The turn carries on.** The agent keeps what it has done so far and works your line in. It
   does not start the turn again, and nothing it has already written is undone.

Which turn gets the line depends on the transcript you are reading, and whether the agent's CLI
can take words mid-turn at all. Both are below.

## Example: add to the task four minutes in

An [`rlar`](https://humanfia.ai/flows/rlar) run has an **actor** fixing a flaky payment test and a **reviewer**
that checks each of its turns. Four minutes into the actor's turn, you remember that the tests
assert the old retry count, and want them fixed in the same turn. Step through what the screen
does:

<TermScreen title="hmz · rlar" :frames="steer" />

What to look at, by number:

1. **`● 1` on the actor's line.** `●` means the agent has a turn open, so a line sent now goes
   into that turn. The reviewer's `○` means it is between turns. The number is how many
   conversations the agent holds.
2. **The editor.** You type exactly as you would to start a task. The status line changes its
   last keys to `enter send` and `ctrl+c clear`: <kbd>ctrl+c</kbd> now clears what you typed
   rather than stopping anything.
3. **The pin, `· with actor`.** Sent, but not yet in front of the model. The name says which
   agent holds it; where two agents are working, that is the half worth knowing. A pin with no
   `with` is still waiting for a turn to go into.
4. **The line in the transcript.** The agent's CLI has confirmed it. From here on it is part of
   the conversation, and the [trace](/user/tracing) records it where it landed.
5. **The agent's answer, in the same turn.** No new turn started, and the work it had done on
   `charge()` is kept.

### Check it worked

- The pin above the editor is gone, and your line is in the transcript with a dim `❯` in front.
- The agent's next words respond to it.
- On the [monitor](/user/monitor) the agent's turn count has not gone up: the same turn took
  the line.

## Where your line goes

To the conversation you are reading. <kbd>shift+tab</kbd> changes which one that is; see
[Many conversations at once](/user/conversations).

| You are reading | Your line goes |
| --- | --- |
| a conversation with a turn open | into that turn |
| every agent, which is where the screen opens | into whichever turn is open |
| a conversation between turns, or nothing is working | onto the pin, then into the next turn to start |
| an outworlder, or every agent while a [question](/user/questions) is up | the answer to it |

Lines go **one at a time, in order**. The next one goes only after the agent has taken the one
before it, so three lines typed in a row are three things said, each answered in turn.

A line typed between turns is never dropped. It stays on the pin and goes into the next turn
to start.

Where [somebody else reads the same run](/features/daemon#several-people-on-one-run), their
lines wait on the same pin and land in the same transcripts, marked ` · by <name>`. Anybody may
say anything to any agent.

## Which agents take a line mid-turn

| Your line goes into | Backends |
| --- | --- |
| <Badge type="tip" text="this turn" /> | Claude Code, Codex, Kimi Code, Oh My Pi, pi |
| <Badge type="warning" text="next turn" /> | Antigravity, Cursor, DeepSeek Harness, Grok Build, MiMo Code, MiniMax Code, opencode, Qwen Code, and any CLI you add on the Accounts page of `/settings` |

The backends in the second row cannot be talked to while they work. Your line is refused, and
goes back on the pin, where the next turn to start takes it:

<TermScreen title="hmz · rlar" :frames="refused" />

1. **The red `hmz:` line** names the backend that refused. Nothing is wrong with the run.
2. **The pin keeps your line**, now without `with actor`: it waits for the next turn to start.

An agent working on [another machine](/user/remote-execution) takes a line during a turn the
same way it would locally. Between its turns, your line waits on the pin like any other.

## Variations

- **Ask without steering.** To ask how the run is going without the agent hearing it, use
  [`/btw`](/user/btw).
- **Several lines at once.** <kbd>shift+enter</kbd> starts a new line in the editor, so a
  paragraph goes as one message rather than as several.
- **Steer one agent of several.** Press <kbd>shift+tab</kbd> until that agent's conversation is
  on the screen, then type. On the transcript of every agent, a line goes to whichever turn is
  open.

## Troubleshooting

### My line stays on the pin and never goes

You were reading a conversation that will not take another turn. A line typed on one
conversation's transcript waits for *that* conversation, and a Ralph loop opens a fresh one
every round, so an old round's conversation never starts again. The pin shows no `with`.

Press <kbd>shift+tab</kbd> until the view reads every agent, and type the line again. The one
still pinned goes into the transcript as `never sent` when the flow ends.

### `sent to actor, which ended its turn without acknowledging it`

The turn ended before the CLI confirmed your words were in front of the model. The line goes
into the transcript either way. It may or may not have reached the agent, so say it again if it
matters.

### Lines marked `never sent` or `sent to the agent, not acknowledged`

The flow ended with lines still pinned. `never sent` never left the pin.
`sent to the agent, not acknowledged` was handed to the agent, which never confirmed it: it may
have reached the model.

### I want it to stop, not change course

A line never stops a run. Type `/stop` or press <kbd>ctrl+c</kbd> twice. See
[Stopping](/user/stopping).

## Next steps

- [Side questions (`/btw`)](/user/btw): ask about the run without the agents hearing it.
- [Many conversations at once](/user/conversations): choose which agent you are talking to.
- [Questions](/user/questions): when the agent asks you instead.
- [A line typed mid-turn](/features/steering): how it works, drawn.
- [TUI reference](/reference/tui): every key at the prompt.

A flow can put words into its own agents' turns as well. See
[Writing a flow](/weaver/writing-a-flow).
