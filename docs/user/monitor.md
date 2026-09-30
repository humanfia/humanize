<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const switched = (listed) =>
  listed ? '  [m] graph [/] [sel b B] list [/]' : '  [sel b B] graph [/] [m] list [/]'

const under = [
  '',
  '[m]Flow:             [/]rlar[m]   431s[/]',
  '',
  '[m]Tokens:           [/]claude-opus-5                1.84M     $4.12   [m]38 out/s[/]',
  '[m]                  [/]gpt-5.6-sol                 402.1k     $0.61   [m]0 out/s[/]',
  '[m]Kinds:            [/]input                        61.3k',
  '[m]                  [/]output                       22.8k',
  '[m]                  [/]cache_read                   2.14M+',
  '[m]                  + is a minimum: not all agents report this kind[/]',
  { rule: true },
  { prompt: '' },
  { rule: true },
]

const status = (listed, keys) => ({
  l: `[c]▣[/] monitor[m] · ${listed ? 'list' : 'graph'}[/]`,
  keys,
})

const graph = (top, actor, reviewer, keys) => [
  switched(false),
  top,
  ...actor,
  '   [m]  ├╴[/][m]◇[/] [m]read the failing tests[/]',
  '   [m]  └╴[/][c]◆[/] [m]find where charge() retries[/]',
  '   [c]│   ↓ 5 · ↑ 5[/]',
  ...reviewer,
  ...under,
  status(false, keys),
]

const edge = (here) => (here ? '[b]' : '[m]')
const box = (here, name, clock, runs, tail) => [
  `   ${edge(here)}┌──────────────────────────────────────────────────────────────────────┐[/]`,
  `${here ? ' [b]❯[/]' : '   '} ${edge(here)}│[/] ${name}${clock} ${edge(here)}│[/]`,
  `   ${edge(here)}│[/] [m]${runs}[/]${tail} ${edge(here)}│[/]`,
  `   ${edge(here)}│[/] [m]▤ repo local                                                        [/] ${edge(here)}│[/]`,
  `   ${edge(here)}└──────────────────────────────────────────────────────────────────────┘[/]`,
]

const actor = (here) =>
  box(
    here,
    '[c]▸ ● actor[/]',
    '                                                        [c]43s[/]',
    'claude/claude-opus-5:high · 6 turns · 1.84M tokens',
    '                  ',
  )
const reviewer = (here, open) =>
  box(
    here,
    `${open ? '▾' : '▸'} ○ reviewer`,
    '                                              [m]idle 1m04s[/]',
    'codex/gpt-5.6-sol:high · 5 turns · 2 sessions · 402.1k tokens',
    ' [c]unread[/]',
  )
const sessions = [
  '   [m]  ├╴[/]○ session 1 · 3 turns · 250.0k tokens                   [m]idle 6m40s[/]',
  '   [m]  │   ▤[/] [m]repo · local · /home/you/shop[/]',
  '   [m]  └╴[/]○ session 2 · 2 turns · 152.1k tokens          [c]unread[/][m] · idle 1m04s[/]',
  '   [m]      ▤[/] [m]repo · local · /home/you/shop[/]',
]

const all = (here) =>
  `${here ? ' [b]❯[/]' : '   '} [c]▣[/] all agents[m] · 1 of 2 working · 11 turns · 7m11s[/][b] · reading[/]`

const keys = '↑↓ node · enter open · → back · ctrl+t list · / commands'
const folds = '↑↓ node · space sessions · enter open · → back · ctrl+t list · / commands'
const shuts = '↑↓ node · space shut · enter open · → back · ctrl+t list · / commands'

const listed = [
  switched(true),
  all(false),
  '       [m]node                    runs · where                        turns        time    tokens[/]',
  '   [m]▸[/] [c]●[/] [c]actor[/]                   [m]claude/claude-opus-5:high         6 turns[/][c]         43s[/][m]     1.84M[/]',
  '     [c]▤[/] [c]repo[/]                    [m]local · /home/you/shop         3 sessions[/]',
  ' [b]❯[/] [m]▾[/] ○ reviewer [c]unread[/]         [m]codex/gpt-5.6-sol:high            5 turns  idle 1m04s    402.1k[/]',
  '     ○ reviewer · session 1    [m]codex/gpt-5.6-sol:high            3 turns  idle 6m40s    250.0k[/]',
  '     ○ reviewer · sess… [c]unread[/] [m]codex/gpt-5.6-sol:high            2 turns  idle 1m04s    152.1k[/]',
  ...under,
  status(true, shuts.replace('ctrl+t list', 'ctrl+t graph')),
]

const read = [
  '[dim]● reviewer is working[/]',
  '',
  '[g]●[/] {"done": false, "notes": "charge() still retries outside the lock. Move the retry into the locked block and add a test that charges twice at once."}',
  '',
  '[dim]✻ Worked for 38s · reviewer[/]',
  '',
  { r: '[m]actor · claude/claude-opus-5:high · ● 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 2 · reading[/]', hl: true },
  { r: '[m]input 61.3k · output 22.8k · cache_read 2.14M+ · cache_write 88.0k+[/]' },
  { r: '[m]$4.73 · 38 out/s[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: '[c]·|·[/] actor… [m](43s · ctrl+c twice to stop)[/]',
    keys: 'shift+tab switch view · / commands · shift+enter newline · ← monitor · ctrl+c stop',
  },
]

const monitor = [
  {
    label: '←',
    lines: graph(all(true), actor(false), reviewer(false, false), keys),
    caption:
      'The monitor opens on <code>all agents</code>: <kbd>enter</kbd> here reads every agent at once.',
  },
  {
    label: '↓ ↓',
    lines: graph(all(false), actor(false), reviewer(true, false), folds),
    caption:
      'The cursor is on the reviewer, which has stopped and has something you have not read.',
  },
  {
    label: 'space',
    lines: [
      ...graph(all(false), actor(false), reviewer(true, true), shuts).slice(0, -1 - under.length),
      ...sessions,
      ...under,
      status(false, shuts),
    ],
    caption:
      'Space opens it out: a row per session, and under each the environment it works in. The arrows walk onto them.',
  },
  {
    label: 'ctrl+t',
    lines: listed,
    caption:
      'The list: no arrows, and whatever is working at the top. <kbd>ctrl+t</kbd> again, or a click on <code>graph</code>, goes back.',
  },
  {
    label: 'enter',
    lines: read,
    art: false,
    caption:
      'Enter on the reviewer reads it, even though it is not working. <kbd>tab</kbd> would not have stopped on it. <kbd>←</kbd> goes back up.',
  },
]
</script>

# Watching a run — the monitor

The monitor is the run drawn across the whole screen: a box for each agent that has worked, what
each one is doing now, its sessions and the environments they work in, and arrows for the work
passing between agents. It shows at a glance whether the run has the shape you expected, and
which agent to read next.

It is one of the interface's two screens. The other is the log, where you read transcripts. The
monitor is the parent: you pick a log to read from it, and you come back up to it.

## Try it

During an [`rlar`](/flows/rlar) run, press <kbd>←</kbd> with nothing typed. Then walk to a box,
open it out, turn to the list, and read it:

<TermScreen title="hmz · rlar" :frames="monitor" art />

The drawing stays live. <kbd>→</kbd> with nothing typed goes back to the log you were reading.

## Graph or list

The switch above the drawing says which of the two you are looking at, and a click on the other
half turns to it. So does <kbd>ctrl+t</kbd>, which works even with something typed. The status
line says `graph` or `list`, and the monitor opens again the way you left it.

- **The graph** draws a box per agent in the order the flow declares them, with the handovers
  between them as arrows.
- **The list** is the same nodes as rows, and says nothing about who handed to whom. Whatever is
  working is at the top, and everything else keeps its place, so a row moves only when what it
  is about starts or stops. Its columns are what each runs (or where an environment is), its
  turns, how long it has been at what it is doing, and the tokens it has spent. Every
  environment of the run is a row of its own.

## The first node

`▣ all agents` is always first, and the cursor starts on it. <kbd>enter</kbd> on it reads the log
every agent's work appears on, which is where a run is watched from. Its row also says how many
boxes are working, the run's turns, and how long it has run.

Under it, a run that talks to you has a `◉` node for each outworlder: the role that is you. Enter
on it reads what the flow says to you. Where another interface reads the same run, the node says
whose the role is to answer -- `yours`, or `bob@tui's` -- once somebody has
[claimed](/reference/tui#several-people-on-one-run) it.

## Reading a box

The left of a box says what the agent is: `▸`, the name the flow gives it, what it runs as
`cli/model:effort`, how many turns it has taken, how many sessions where it has more than one,
and the tokens it has spent. A third line names the environments its sessions work in. The right
says what it is doing now:

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

## Sessions

An agent is one box however many sessions it opens: a loop that opens a new session each round
is one agent and many sessions. <kbd>space</kbd> opens the agent under the cursor out, its `▸`
turning to `▾`, with a row per session hanging under it -- `session 1`, `session 2` -- each with
its turns, its tokens and its own clock. The subagents a session started hang under that
session. A session that has ended stays, and can still be read: <kbd>enter</kbd> on it reads its
own log. <kbd>space</kbd> again, on the agent or on any row under it, shuts it.

With the mouse, a click on the left edge of a box, where its `▸` is, opens it out or shuts it,
and so does a click on the agent the cursor is already on. A click anywhere else on an agent
only moves the cursor there, and a double click reads it.

## Environments

Under each session is the environment it works in: `▤`, the environment role the flow gave it,
and where it is -- the kind of machine, which one, and the directory on it. A session in a
worktree derived from an environment works somewhere else, and is drawn so.

<kbd>enter</kbd> or a click on one opens its page:

| Row | Shows |
| --- | --- |
| `kind` | `LOCAL`, `SSH` or `DOCKER`. |
| `target` | The ssh host or the docker provider, or `this machine`. |
| `workdir` | The directory its sessions work in. |
| `set up as` | What it was given with `-e` or on `/flow`, where it was set up here. |
| `image` | What a container for it is started from, where the flow names one. |
| `grants` | The capabilities the flow declared for the role: `Shell`, `Files`, `GitWorktree`, … |
| `needs` | What the flow asks of the machine: CPUs, memory, GPUs. |
| `harness` | Where the agents working in it run. An ssh or docker environment is anchored: the agent runs on this machine and what it runs lands there. |
| `status` | How many of its sessions are working now. |
| `Sessions` | Each session working in it. <kbd>enter</kbd> or a click on one reads it. |

The page stays live. <kbd>esc</kbd> goes back to the monitor.

## Under the drawing

| Row | Shows |
| --- | --- |
| `Flow` | The flow running, and any flow it called, innermost last, each with how long it has run. |
| `Set` | The flow's settings that differ from its defaults. |
| `Also` | On the graph, handovers the arrows could not show. |
| `Reading` | Where more than one interface or program reads the run: each by name, yours marked `you`. |
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
| <kbd>space</kbd> | With nothing typed: open the agent under the cursor out to its sessions, or shut it. |
| <kbd>enter</kbd> | With nothing typed: read that node's log. On an environment, open its page. On a line of the board, change it. |
| a click | What <kbd>enter</kbd> does. On an agent: on its `▸`, or on the one already picked, open it out or shut it; elsewhere, pick it; twice, read it. |
| <kbd>→</kbd> | With nothing typed: back to the log you were reading. |
| <kbd>ctrl+t</kbd> | The graph, or the list. |
| <kbd>←</kbd> | On the log, with nothing typed: up to the monitor. |

Once you type, the arrows, <kbd>space</kbd> and <kbd>enter</kbd> are the prompt's again.
<kbd>esc</kbd> does not open the monitor, and there is no command for it.

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
