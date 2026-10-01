<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

// A box is 70 columns inside its edges, as the interface draws it: a space, 68, a space. The page's own callouts go
// outside the right edge, so they never push the edge out of line.
const W = 68
const shown = (said) => said.replace(/\[[^\]]*\]/g, '')
const fill = (said) => said + ' '.repeat(Math.max(0, W - shown(said).length))
const apart = (left, right) =>
  left + ' '.repeat(Math.max(1, W - shown(left).length - shown(right).length)) + right

const switched = (listed) =>
  listed ? '  [m] graph [/] [sel b B] list [/]' : '  [sel b B] graph [/] [m] list [/]'

const under = (n) => [
  '',
  `[m]Flow:             [/]rlar[m]   431s[/]${n ? '[n]7[/]' : ''}`,
  '',
  '[m]Tokens:           [/]claude-opus-5-5                1.84M     $4.12   [m]38 out/s[/]',
  '[m]                  [/]gpt-5.6-sol                 402.1k     $0.61   [m]0 out/s[/]',
  '[m]Kinds:            [/]input                        61.3k',
  '[m]                  [/]output                       22.8k',
  '[m]                  [/]cache_read                   2.14M',
  { rule: true },
  { prompt: '' },
  { rule: true },
]

const status = (listed, keys) => ({
  l: `[c]▣[/] monitor[m] · ${listed ? 'list' : 'graph'}[/]`,
  keys,
})

const edge = (here) => (here ? '[b]' : '[m]')
const box = (here, top, second, third, mark = ['', '', '']) => [
  `   ${edge(here)}┌${'─'.repeat(W + 2)}┐[/]`,
  `${here ? ' [b]❯[/] ' : '   '}${edge(here)}│[/] ${fill(top)} ${edge(here)}│[/]${mark[0]}`,
  `   ${edge(here)}│[/] ${fill(second)} ${edge(here)}│[/]${mark[1]}`,
  `   ${edge(here)}│[/] ${fill(third)} ${edge(here)}│[/]${mark[2]}`,
  `   ${edge(here)}└${'─'.repeat(W + 2)}┘[/]`,
]

const actor = (here, marks) =>
  box(
    here,
    apart('[c]▸ ● actor[/]', '[c]43s[/]'),
    '[m]claude/claude-opus-5-5:high · 6 turns · 1.84M tokens[/]',
    '[m]▤ workspace local[/]',
    marks,
  )
const reviewer = (here, open) =>
  box(
    here,
    apart(`${open ? '▾' : '▸'} ○ reviewer`, '[m]idle 1m04s[/]'),
    '[m]codex/gpt-5.6-sol:high · 5 turns · 2 sessions · 402.1k tokens[/] [c]unread[/]',
    '[m]▤ workspace local[/]',
  )
const subagents = (n) => [
  `   [m]  ├╴[/][m]◇[/] [m]read the failing tests[/]${n ? '[n]5[/]' : ''}`,
  '   [m]  └╴[/][c]◆[/] [m]find where charge() retries[/]',
  `   [c]│   ↓ 5 · ↑ 5[/]${n ? '[n]6[/]' : ''}`,
]
const sessions = [
  '   [m]  ├╴[/]○ session 1 · 3 turns · 250.0k tokens                   [m]idle 6m40s[/][n]1[/]',
  '   [m]  │   ▤[/] [m]workspace · local · /home/you/shop[/][n]2[/]',
  '   [m]  └╴[/]○ session 2 · 2 turns · 152.1k tokens          [c]unread[/][m] · idle 1m04s[/]',
  '   [m]      ▤[/] [m]workspace · local · /home/you/shop[/]',
]

const all = (here, n) =>
  `${here ? ' [b]❯[/] ' : '   '}[c]▣[/] all agents[m] · 1 of 2 working · 11 turns · 7m11s[/][b] · reading[/]${n ? '[n]2[/]' : ''}`

const keys = '↑↓ node · enter open · → back · ctrl+t list · / commands'
const folds = '↑↓ node · space sessions · enter open · → back · ctrl+t list · / commands'
const shuts = '↑↓ node · space shut · enter open · → back · ctrl+t list · / commands'

const listed = [
  switched(true),
  all(false),
  '       [m]node                    runs · where                        turns        time    tokens[/][n]1[/]',
  '   [m]▸[/] [c]●[/] [c]actor[/]                   [m]claude/claude-opus-5-5:high       6 turns[/][c]         43s[/][m]     1.84M[/][n]2[/]',
  ' [b]❯[/] [m]▾[/] ○ reviewer [c]unread[/]         [m]codex/gpt-5.6-sol:high            5 turns  idle 1m04s    402.1k[/]',
  '     ○ reviewer · session 1    [m]codex/gpt-5.6-sol:high            3 turns  idle 6m40s    250.0k[/]',
  '     ○ reviewer · sess… [c]unread[/] [m]codex/gpt-5.6-sol:high            2 turns  idle 1m04s    152.1k[/]',
  '     [c]▤[/] [c]workspace[/]               [m]local · /home/you/shop         3 sessions[/][n]3[/]',
  ...under(false),
  status(true, shuts.replace('ctrl+t list', 'ctrl+t graph')),
]

const place = [
  '   [b]workspace[/]',
  '   [m]An environment of the run: where its sessions work.[/]',
  '',
  '     [m]kind              [/]LOCAL[n]1[/]',
  '     [m]target            [/]this machine',
  '     [m]workdir           [/]/home/you/shop',
  '     [m]grants            [/]nothing beyond running in it[n]2[/]',
  '     [m]harness           [/]adaptive → local: on this machine, in this workdir[n]3[/]',
  '     [m]status            [/]1 of 3 sessions working',
  '     [b]Sessions[/][n]4[/]',
  ' [b]❯[/]   [c]● actor · session 1 · claude/claude-opus-5-5:high[/]',
  '     [m]○ reviewer · session 1 · codex/gpt-5.6-sol:high[/]',
  '     [m]○ reviewer · session 2 · codex/gpt-5.6-sol:high[/]',
  '',
  '   [m]enter read session · esc back[/]',
]

const read = [
  '[dim]─ reading reviewer · 2 conversations ─[/]',
  '',
  '[dim]● reviewer is working · conversation 2 of 2[/]',
  '',
  '[g]●[/] {"done": false, "notes": "charge() still retries outside the lock. Move the retry into the locked block and add a test that charges twice at once."}',
  '',
  '[dim]✻ Worked for 38s · reviewer[/]',
  '',
  { r: '[m]actor · claude/claude-opus-5-5:high · ● 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high · ○ 2 · reading[/]', hl: true },
  { r: '[m]input 61.3k · output 22.8k · cache_read 2.14M · cache_write 88.0k[/]' },
  { r: '[m]$4.73 · 38 out/s[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: '[c]·|·[/] actor… [m](43s · ctrl+c twice to stop)[/]',
    keys: 'shift+tab switch view · / commands · shift+enter newline · ← monitor · ctrl+c stop',
  },
]

const graph = (top, a, r, keys, n) => [
  `${switched(false)}${n ? '[n]1[/]' : ''}`,
  top,
  ...a,
  ...subagents(n),
  ...r,
  ...under(n),
  status(false, keys),
]

const monitor = [
  {
    label: '1 · ←',
    lines: graph(all(true, true), actor(false, ['[n]3[/]', '', '[n]4[/]']), reviewer(false, false), keys, true),
    caption:
      'The monitor opens on <code>all agents</code>: <kbd>enter</kbd> here reads every agent at once.',
  },
  {
    label: '2 · ↓ ↓',
    lines: graph(all(false), actor(false), reviewer(true, false), folds),
    caption:
      'The cursor is on the reviewer, which has stopped and has something you have not read. The keys offer <kbd>space</kbd> sessions.',
  },
  {
    label: '3 · space',
    lines: [
      switched(false),
      all(false),
      ...actor(false),
      ...subagents(false),
      ...reviewer(true, true),
      ...sessions,
      ...under(false),
      status(false, shuts),
    ],
    caption:
      'Space opens it out: a row per session, and under each the environment it works in. The arrows walk onto them.',
  },
  {
    label: '4 · ctrl+t',
    lines: listed,
    caption:
      'The list: no arrows, whatever is working at the top, and every environment a row of its own. <kbd>ctrl+t</kbd> again, or a click on <code>graph</code>, goes back.',
  },
  {
    label: '5 · enter on ▤',
    lines: place,
    caption:
      'Enter on an environment opens its page. It stays live; <kbd>enter</kbd> on a session reads it, <kbd>esc</kbd> goes back.',
  },
  {
    label: '6 · enter on reviewer',
    lines: read,
    art: false,
    caption:
      'Enter on the reviewer reads it, even though it is not working. <kbd>shift+tab</kbd> would not have stopped on it. <kbd>←</kbd> goes back up.',
  },
]
</script>

# Watching a run — the monitor

The monitor is the run drawn across the whole screen: a box for each agent that has worked, what
each one is doing now, its sessions and the environments they work in, and arrows for the work
passing between agents. It shows at a glance whether the run has the shape you expected, and
which agent to read next.

::: info At a glance
- **You will** see every agent of a run at once, open one out to its sessions and
  environments, and pick the transcript to read.
- **Use it when** a flow drives several agents or many sessions, when a run seems stuck, or
  when you want to read an agent that is not working right now.
- **You need** a run in `hmz`, running or just ended. [Your first run](/user/first-run) starts
  one.
:::

## Try it

During a run, press <kbd>←</kbd> with nothing typed. Press <kbd>→</kbd> to go back to the
transcript you were reading.

## How it works

The interface has two screens. The **log** is where you read transcripts. The **monitor** is
its parent: you pick a log to read from it, and you come back up to it. Both keep the same
prompt at the bottom, so every command works on either.

The monitor draws the run as **nodes**:

- `▣ all agents`, always first: the log every agent's work appears on.
- `◉` an **outworlder**, where the flow talks to you (for example `◉ human · outworlder:
  messages from the flow to you`).
- a **box per agent** that has taken a turn, in the order the flow declares them. An agent is
  one box however many sessions it opens.
- under an agent opened out, a row per **session**, and under each session the **environment**
  it works in, `▤`.

It draws them two ways: as a **graph**, with arrows for the handovers between agents, or as a
**list**, a table with the working rows at the top. The drawing stays live either way.

## Example: find out why an `rlar` run has stalled

An [`rlar`](/flows/rlar) run has an actor and a reviewer. The actor has been working a while
and you want to see what the reviewer last said. Press the frames in order:

<TermScreen title="hmz · rlar" :frames="monitor" art />

What to look at in frame 1, by number:

1. **The switch, `graph` `list`.** Which of the two views you are looking at. A click on the
   other half turns to it, as <kbd>ctrl+t</kbd> does.
2. **`▣ all agents`.** Where the cursor starts: how many boxes are working, the run's turns,
   and how long it has run. `· reading` says its log is the one you came from.
3. **The actor's box.** The top line says what it is doing now: `▸` (it can be opened out),
   `●` working, and `43s`, how long this turn has been going. The second line says what it
   runs, `cli/model:effort`, its turns and tokens.
4. **`▤ workspace local`.** The environments its sessions work in.
5. **`◇` and `◆` under a box.** Subagents the agent started on its own: `◆` still going, `◇`
   finished. You cannot read or talk to them.
6. **`↓ 5 · ↑ 5` between boxes.** Handovers each way: the actor has handed to the reviewer
   five times, and back. The pair the run moved between last is lit.
7. **Under the drawing.** The flow and how long it has run, then tokens and money per model.
   See [Under the drawing](#under-the-drawing).

The frames after it walk the rest: <kbd>↓</kbd> to the reviewer, <kbd>space</kbd> to open it
out, <kbd>ctrl+t</kbd> to the list, <kbd>enter</kbd> on the environment for its page, and
<kbd>enter</kbd> on the reviewer to read it. In frame 3, the numbers mark **(1)** a session
row, with its own turns, tokens and clock, and **(2)** the environment that session works in,
with the directory. In frame 4, **(1)** the list's columns, **(2)** a working row moved to the
top, and **(3)** the environment as a row of its own. Frame 5 is explained under
[Environments](#environments).

### Check it worked

- The status line reads `▣ monitor · graph` or `▣ monitor · list`.
- <kbd>enter</kbd> on a box reads that agent's log, with `· reading` beside it above the
  editor.
- <kbd>→</kbd> with nothing typed puts you back on the log you left.

## Graph or list

The switch above the drawing says which of the two you are looking at, and a click on the other
half turns to it. So does <kbd>ctrl+t</kbd>, which works even with something typed. The status
line says `graph` or `list`, and the monitor opens again the way you left it.

- **The graph** draws a box per agent in the order the flow declares them, with the handovers
  between them as arrows.
- **The list** is the same nodes as rows, and says nothing about who handed to whom. Whatever is
  working is at the top, and everything else keeps its place, so a row moves only when what it
  is about starts or stops. Its columns are `node`, `runs · where` (what each runs, or where an
  environment is), `turns`, `time` (how long it has been at what it is doing) and `tokens`.
  Every environment of the run is a row of its own.

| Reach for | When |
| --- | --- |
| the graph | the flow passes work between agents, and you want to see who is waiting on whom |
| the list | many agents or sessions, and you want the busy ones at the top |

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
its turns, its tokens and its own clock. From a real `ralph_loop` run:

```text
  ❯ │ ▾ ○ agent                                                    idle 0s │
    │ claude/claude-haiku-4-5-20251001:medium · 2 turns · 2 sessions · 21… │
    │ ▤ workspace local                                                    │
    └──────────────────────────────────────────────────────────────────────┘
      ├╴○ session 1 · 1 turn · 63.9k tokens                       idle 21s
      │   ▤ workspace · local · /tmp/g1/demo
      └╴○ session 2 · 1 turn · 152.8k tokens                       idle 0s
          ▤ workspace · local · /tmp/g1/demo
```

The subagents a session started hang under that session. A session that has ended stays, and
can still be read: <kbd>enter</kbd> on it reads its own log. <kbd>space</kbd> again, on the
agent or on any row under it, shuts it.

With the mouse, a click on the left edge of a box, where its `▸` is, opens it out or shuts it,
and so does a click on the agent the cursor is already on. A click anywhere else on an agent
only moves the cursor there, and a double click reads it.

## Environments

Under each session is the environment it works in: `▤`, the environment role the flow gave it,
and where it is -- the kind of machine, which one, and the directory on it. A session in a
worktree derived from an environment works somewhere else, and is drawn so.

<kbd>enter</kbd> or a click on one opens its page. In frame 5 of the example, **(1)** is the
kind of machine, **(2)** what the flow lets the role do there, **(3)** where the agents working
in it run, and **(4)** every session working in it, to read. A row with nothing to say is left
out:

| Row | Shows |
| --- | --- |
| `kind` | `LOCAL`, `SSH` or `DOCKER`. |
| `target` | The ssh host or the docker provider, or `this machine`. |
| `workdir` | The directory its sessions work in. |
| `set up as` | What it was given with `-e` or on `/flow`, where it was set up here. |
| `image` | What a container for it is started from, where the flow names one. |
| `grants` | The capabilities the flow declared for the role: `Shell`, `Files`, `GitWorktree`, … or `nothing beyond running in it`. |
| `needs` | What the flow asks of the machine: CPUs, memory, GPUs. |
| `harness` | Where the run put the harnesses of the agents working in it: what `-H` was, then what that came to for its sessions, such as `adaptive → env: on this environment's machine, with the CLI installed there` or `local → local: on this machine; what it runs lands here`. Where sessions went different ways, each is named: `adaptive → env for builder/1 · local for reviewer/1`. See [Remote execution](/user/remote-execution). |
| `status` | How many of its sessions are working now, such as `1 of 3 sessions working`. |
| `Sessions` | Each session working in it. <kbd>enter</kbd> or a click on one reads it. |

The page stays live. <kbd>esc</kbd> goes back to the monitor.

## Under the drawing

| Row | Shows |
| --- | --- |
| `Flow` | The flow running, and any flow it called, innermost last, each with how long it has run. |
| `Agents` | Before any turn: the agents that are set up. |
| `Set` | The flow's settings that differ from its defaults. |
| `Also` | On the graph, handovers the arrows could not show. |
| `Reading` | Where more than one interface or program reads the run: each by name, yours marked `you`. |
| `Tokens` | Tokens and money per model, and the output tokens a second each is producing. A row per model, in the order each was first spent on: rows do not swap as one model overtakes another. |
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

The status line offers only the keys that do something on the node under the cursor:
`space sessions` on an agent that can be opened out, `space shut` once it is.

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

## Troubleshooting

### <kbd>←</kbd> moves the cursor instead of opening the monitor

Something is typed at the prompt, so the arrows are the prompt's. Clear it with
<kbd>ctrl+c</kbd>, then press <kbd>←</kbd>.

### An agent the flow declares has no box

It has not taken a turn yet. A box appears with its agent's first turn. Before any turn at all,
the `Agents` row under the drawing lists what is set up.

### The list rows keep moving

A row moves to the top when what it is about starts working, and back when it stops. Use the
graph for a picture that holds still.

### I cannot reach a subagent's log

Subagents (`◆`, `◇`) are the agent's own. humanize shows that they ran, but has no transcript
of theirs to read. Read the agent that started them.

## Next steps

- [Side questions (`/btw`)](/user/btw): ask about the run in words.
- [Many conversations at once](/user/conversations): step between logs without the monitor.
- [Tracing](/user/tracing): the whole run on one timeline, after it ends.
- [TUI reference](/reference/tui): every key and command.
