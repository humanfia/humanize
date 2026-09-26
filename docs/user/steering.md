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
  { r: '[m]actor · claude/claude-opus-5:high · ● 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 1[/]' },
  { r: '[m]input 41.2k · output 18.9k · cache_read 1.71M+ · cache_write 72.4k+[/]' },
]
const spent = '[m]$4.12 · 38 out/s[/]'
const status = '[c]·|·[/] actor… [m](43s · ctrl+c twice to stop)[/]'
const keys = 'tab agent · / commands · shift+enter newline · esc monitor · ctrl+c stop'

const steer = [
  {
    label: '1 · type',
    lines: [
      ...working,
      '',
      ...agents,
      { r: spent },
      { rule: true },
      { prompt: 'and fix the tests too' },
      { rule: true },
      {
        l: status,
        keys: 'enter say · tab agent · / commands · shift+enter newline · esc monitor · ctrl+c clear',
      },
    ],
    caption:
      'The actor is in the middle of a turn. Type as you would to start one.',
  },
  {
    label: '2 · pinned',
    lines: [
      ...working,
      '',
      ...agents,
      { l: '[m]❯ and fix the tests too · with actor[/]', r: spent, hl: true },
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
      { t: '[dim]❯[/] and fix the tests too', hl: true },
      '',
      '[g]●[/] Will do. Two of the tests still assert three retries; updating them too.',
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
      '[r]hmz: CursorSession cannot be talked to mid-turn[/]',
      '',
      { r: '[m]actor · cursor-agent/composer-2.5:auto · ● 1[/]' },
      { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 1[/]' },
      { r: '[m]input 22.8k · output 6.3k · cache_read 402.1k+ · cache_write 18.0k+[/]' },
      { l: '[m]❯ and fix the tests too[/]', r: '[m]$0.91 · 52 out/s[/]', hl: true },
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

## Try it

Say something to the [`rlar`](/flows/rlar) actor four minutes into its turn. Step through what
the screen does:

<TermScreen title="hmz · rlar" :frames="steer" />

You do not need to wait for a turn to end, and a line typed between turns is never dropped. It
stays on the pin and goes into the next turn to start.

## Where your line goes

To the agent you are reading. <kbd>tab</kbd> changes which one that is; see
[Many conversations at once](/user/conversations).

| You are reading | Your line goes |
| --- | --- |
| an agent with a turn open | into that turn |
| every agent, which is where the screen opens | into whichever turn is open |
| an agent between turns, or nothing is working | onto the pin, then into the next turn to start |

Lines go **one at a time, in order**. The next one goes only after the agent has taken the one
before it, so three lines typed in a row are three things said, each answered in turn.

## Which agents take a line mid-turn

| Your line goes into | Backends |
| --- | --- |
| <Badge type="tip" text="this turn" /> | Claude Code, Codex, Kimi Code, pi |
| <Badge type="warning" text="next turn" /> | Antigravity, Cursor, DeepSeek Harness, Grok Build, MiMo Code, opencode, Qwen Code, ZCode, and any CLI you add at `/providers` |

The backends in the second row cannot be talked to while they work. Your line is refused with a
red `hmz:` line and goes back on the pin, where the next turn to start takes it:

<TermScreen title="hmz · rlar" :frames="refused" />

An agent working on [another machine](/user/remote-execution) takes a line during a turn the
same way it would locally. Between its turns, your line waits on the pin like any other.

::: details If a turn ends before it takes your line
The screen says `put to actor, which ended its turn without saying it had it`, and your line
goes into the transcript. It may or may not have reached the agent, so say it again if it
matters.

If the flow ends first, pinned lines go into the transcript too. A line still waiting is marked
`never sent`. A line an agent had but never confirmed is marked
`put to the agent, never taken back`: it may have reached the agent.
:::

## When a line is not enough

- To ask how the run is going without steering it, use [`/btw`](/user/btw).
- To end the run, type `/stop` or press <kbd>ctrl+c</kbd> twice. See
  [Stopping](/user/stopping).

A flow can put words into its own agents' turns as well. See
[Writing a flow](/weaver/writing-a-flow).

## See also

- [A line typed mid-turn](/features/steering), which shows how it works
- [Many conversations at once](/user/conversations)
- [Questions](/user/questions), for when the agent asks you instead
