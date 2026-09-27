<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const graph = (top, actor, reviewer) => [
  top,
  ...actor,
  '   [m]  ├╴[/][m]◇[/] [m]read the failing tests[/]',
  '   [m]  └╴[/][c]◆[/] [m]find where charge() retries[/]',
  '   [c]│   ↓ 5 · ↑ 5[/]',
  ...reviewer,
  '',
  '[m]Flow:             [/]rlar[m]   431s[/]',
  '',
  '[m]Tokens:           [/]claude-opus-5                1.84M     $4.12   [m]38 out/s[/]',
  '[m]                  [/]gpt-5.6-sol                 402.1k     $0.61   [m]0 out/s[/]',
  '[m]Kinds:            [/]input                        61.3k',
  '[m]                  [/]output                       22.8k',
  '[m]                  [/]cache_read                   2.14M+',
  '[m]                  + a floor: not every agent here reports that kind[/]',
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: '[c]▣[/] monitor[m] · a node per agent[/]',
    keys: '↑↓ node · enter read · → back · ctrl+t by session · / commands',
  },
]

const box = (here, name, clock, runs, tail) => [
  `   ${here ? '[b]' : '[m]'}┌──────────────────────────────────────────────────────┐[/]`,
  `${here ? ' [b]❯[/]' : '   '} ${here ? '[b]' : '[m]'}│[/] ${name}${clock} ${here ? '[b]' : '[m]'}│[/]`,
  `   ${here ? '[b]' : '[m]'}│[/] [m]${runs}[/]${tail} ${here ? '[b]' : '[m]'}│[/]`,
  `   ${here ? '[b]' : '[m]'}└──────────────────────────────────────────────────────┘[/]`,
]

const actor = (here) =>
  box(
    here,
    '[c]● actor[/]',
    '                                          [c]43s[/]',
    'claude/claude-opus-5:high · 6 turns',
    '                  ',
  )
const reviewer = (here) =>
  box(
    here,
    '○ reviewer',
    '                                [m]idle 1m04s[/]',
    'codex/gpt-5.6-sol:high · 5 turns',
    '              [c]unread[/]',
  )

const all = (here) =>
  `${here ? ' [b]❯[/]' : '   '} [c]▣[/] all agents[m] · 1 of 2 working · 11 turns · 7m11s[/][b] · reading[/]`

const read = [
  '[dim]● reviewer is working[/]',
  '',
  '[g]●[/] {"done": false, "notes": "charge() still retries outside the lock. Move the retry into the locked block and add a test that charges twice at once."}',
  '',
  '[dim]✻ Worked for 38s · reviewer[/]',
  '',
  { r: '[m]actor · claude/claude-opus-5:high · ● 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 1 · reading[/]', hl: true },
  { r: '[m]input 61.3k · output 22.8k · cache_read 2.14M+ · cache_write 88.0k+[/]' },
  { r: '[m]$4.73 · 38 out/s[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: '[c]·|·[/] actor… [m](43s · ctrl+c twice to stop)[/]',
    keys: 'tab agent · / commands · shift+enter newline · ← monitor · ctrl+c stop',
  },
]

const monitor = [
  {
    label: '←',
    lines: graph(all(true), actor(false), reviewer(false)),
    caption:
      'The monitor opens on <code>all agents</code>: <kbd>enter</kbd> here reads every agent at once.',
  },
  {
    label: '↓ ↓',
    lines: graph(all(false), actor(false), reviewer(true)),
    caption:
      'The cursor is on the reviewer, which has stopped and has something you have not read.',
  },
  {
    label: 'enter',
    lines: read,
    art: false,
    caption:
      'Enter on its box reads the reviewer, even though it is not working. <kbd>tab</kbd> would not have stopped on it. <kbd>←</kbd> goes back up.',
  },
]
</script>

# Watching a run — the monitor

The monitor is the run drawn across the whole screen: a box for each agent that has worked, what
each one is doing now, and arrows for the work passing between them. It shows at a glance whether
the run has the shape you expected, and which agent to read next.

It is one of the interface's two screens. The other is the log, where you read transcripts. The
monitor is the parent: you pick a log to read from it, and you come back up to it.

## Try it

During an [`rlar`](/flows/rlar) run, press <kbd>←</kbd> with nothing typed. Then walk to a box and
press <kbd>enter</kbd>:

<TermScreen title="hmz · rlar" :frames="monitor" art />

The drawing stays live. <kbd>→</kbd> with nothing typed goes back to the log you were reading.

## The first node

`▣ all agents` is always first, and the cursor starts on it. <kbd>enter</kbd> on it reads the log
every agent's work appears on, which is where a run is watched from. Its row also says how many
boxes are working, the run's turns, and how long it has run.

Under it, a run that talks to you has a `◉` node for each outworlder: the role that is you. Enter
on it reads what the flow says to you.

## Reading a box

The left of a box says what the agent is: the name the flow gives it, what it runs as
`cli/model:effort`, and how many turns it has taken. The right says what it is doing now:

| Right side | Means |
| --- | --- |
| `●` and `43s` | Working. The clock is how long this turn has been going. |
| `○` and `idle 1m04s` | Stopped. The clock is how long since its last turn ended. |
| `reading` | Its log is the one you were reading. |
| `unread` | It has said something since you last read it. |

An agent that has been thinking for eleven minutes and one that stopped eleven minutes ago look
nothing alike here. The second is usually where a run has gone wrong.

**Under a box** hang the subagents that agent started on its own. `◆` is one still going and
`◇` one that has finished. You cannot read or talk to them.

**Between two boxes**, `↓ 5 · ↑ 5` counts the handovers each way. The pair the run moved
between most recently is lit. Handovers between boxes that are not next to each other are
listed under the drawing as `Also`.

A box appears when its agent takes its first turn, and stays until the next run, working or not.
A flow may declare ten agents and use three, and you see the three. Before any turn, the monitor
lists the agents that are set up instead.

## A box per session

<kbd>ctrl+t</kbd> draws a box per session instead of per agent, and back again. A loop that
opens a new session each round is one agent and many sessions: `actor · session 1`,
`actor · session 2`, with the handovers between them. A session that has ended stays, and can
still be read. The status line says which you are looking at: `a node per agent` or
`a node per session`, and the monitor opens again the way you left it.

## Under the drawing

| Row | Shows |
| --- | --- |
| `Flow` | The flow running, and any flow it called, innermost last, each with how long it has run. |
| `Set` | The flow's settings that differ from its defaults. |
| `Also` | Handovers the arrows could not show. |
| `Tokens` | Tokens and money per model, and the output tokens a second each is producing. |
| `Kinds` | Tokens by kind for the whole run. A `+` marks a floor, because some agent's CLI does not report that kind. See [Cost and rate](/user/tally). |

## The prompt

The prompt under the drawing is the same one as the log's. Every command works here, and a line
you type goes where it would have gone from the log. What a command answers appears under the
drawing, above the prompt.

## The keys

| Key | Does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | With nothing typed: move between the nodes. |
| <kbd>enter</kbd>, or a click | With nothing typed: read that node's log. On a line of the board, change it. |
| <kbd>→</kbd> | With nothing typed: back to the log you were reading. |
| <kbd>ctrl+t</kbd> | A box per agent, or per session. |
| <kbd>←</kbd> | On the log, with nothing typed: up to the monitor. |

Once you type, the arrows and <kbd>enter</kbd> are the prompt's again. <kbd>esc</kbd> does not
open the monitor, and there is no command for it.

The monitor can also draw a [board](/user/board), but a run of a flow never has one.

## Without opening it

Much of this is on the log too:

- **Above the editor**, one line per agent: what it runs, and `●` or `○` for whether it is
  working. See [Many conversations at once](/user/conversations).
- **Under those**, what the run has cost and how fast it is spending. See
  [Cost and rate](/user/tally).
- **On the status line**, whose turn it is and how long it has been going.

After the run, its [trace](/user/tracing) shows the same shape in far more detail.

## See also

- [Side questions (`/btw`)](/user/btw), to ask about the run in words
- [Many conversations at once](/user/conversations)
- [Tracing](/user/tracing)
