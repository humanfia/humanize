<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const sheet = [
  { rule: 'b' },
  '   [b B]Monitor[/]',
  '   [m]The run as it is going: a box per agent that has worked, marked as it[/]',
  '   [m]works, and whatever it started of its own hanging under it.[/]',
  '',
  '   [c]▣[/] every agent[m] · 1 of 2 working · 11 turns · 7m11s[/][b] · reading[/]',
  '   [m]┌──────────────────────────────────────────────────────┐[/]',
  '   [m]│[/] [c]● actor[/]                                          [c]43s[/] [m]│[/]',
  '   [m]│[/] [m]claude/claude-opus-5:high · 6 turns[/]                  [m]│[/]',
  '   [m]└──────────────────────────────────────────────────────┘[/]',
  '   [m]  ├╴[/][m]◇[/] [m]read the failing tests[/]',
  '   [m]  └╴[/][c]◆[/] [m]find where charge() retries[/]',
  '   [c]│   ↓ 5 · ↑ 5[/]',
  '   [b]┌──────────────────────────────────────────────────────┐[/]',
  ' [b]❯[/] [b]│[/] ○ reviewer                                [m]idle 1m04s[/] [b]│[/]',
  '   [b]│[/] [m]codex/gpt-5.6-sol:high · 5 turns[/]              [c]unread[/] [b]│[/]',
  '   [b]└──────────────────────────────────────────────────────┘[/]',
  '',
  '   [m]Flow:             [/]rlar[m]   431s[/]',
  '',
  '   [m]Tokens:           [/]claude-opus-5                1.84M     $4.12   [m]38 out/s[/]',
  '   [m]                  [/]gpt-5.6-sol                 402.1k     $0.61   [m]0 out/s[/]',
  '   [m]Kinds:            [/]input                        61.3k',
  '   [m]                  [/]output                       22.8k',
  '   [m]                  [/]cache_read                   2.14M+',
  '   [m]                  [/]cache_write                  88.0k+',
  '   [m]                  + a floor: not every agent here reports that kind[/]',
  '',
  '   [m]↑↓ move · enter read · esc close[/]',
]

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
    keys: 'tab agent · / commands · shift+enter newline · esc monitor · ctrl+c stop',
  },
]

const monitor = [
  {
    label: 'esc',
    lines: sheet,
    caption:
      'The cursor is on the reviewer, which has stopped and has something you have not read.',
  },
  {
    label: 'enter',
    lines: read,
    art: false,
    caption:
      'Enter on its box reads the reviewer, even though it is not working: its own transcript, down to its latest turn. <kbd>tab</kbd> would not have stopped on it.',
  },
]
</script>

# Watching a run — `/monitor`

Press <kbd>esc</kbd>, or type `/monitor`, to see the run drawn: a box for each agent that has
worked, what each one is doing now, and arrows for the work passing between them. It shows at
a glance whether the run has the shape you expected, and which agent to read next.

## Try it

Press <kbd>esc</kbd> during an [`rlar`](/flows/rlar) run, then <kbd>enter</kbd> on a box:

<TermScreen title="hmz · rlar" :frames="monitor" art />

The drawing stays live while it is open. <kbd>esc</kbd> closes it again.

## Reading a box

The left of a box says what the agent is: the name the flow gives it, what it runs as
`cli/model:effort`, and how many turns it has taken. The right says what it is doing now:

| Right side | Means |
| --- | --- |
| `●` and `43s` | Working. The clock is how long this turn has been going. |
| `○` and `idle 1m04s` | Stopped. The clock is how long since its last turn ended. |
| `reading` | Its transcript is the one behind the drawing. |
| `unread` | It has said something since you last read it. |

An agent that has been thinking for eleven minutes and one that stopped eleven minutes ago look
nothing alike here. The second is usually where a run has gone wrong.

**Under a box** hang the subagents that agent started on its own. `◆` is one still going and
`◇` one that has finished. You cannot read or talk to them.

**Between two boxes**, `↓ 5 · ↑ 5` counts the handovers each way. The pair the run moved
between most recently is lit. Handovers between boxes that are not next to each other are
listed under the drawing as `Also`.

A box appears when its agent takes its first turn, and stays until the next run. A flow may
declare ten agents and use three, and you see the three. Before any turn, the sheet lists the
agents that are set up instead.

## Under the drawing

| Row | Shows |
| --- | --- |
| `Flow` | The flow running, and any flow it called, innermost last, each with how long it has run. |
| `Set` | The flow's settings that differ from its defaults. |
| `Also` | Handovers the arrows could not show. |
| `Tokens` | Tokens and money per model, and the output tokens a second each is producing. |
| `Kinds` | Tokens by kind for the whole run. A `+` marks a figure that is a floor, because some agent's CLI does not report that kind. See [Cost and rate](/user/tally). |

## The keys

| Key | Does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move between the boxes and the top row. |
| <kbd>enter</kbd>, or a click | Read that agent. The top row reads every agent again. |
| <kbd>esc</kbd> | Close the drawing. |

`/monitor` can also draw a [board](/user/board), but a run of a flow never has one.

## Without opening it

Much of this is on the main screen too:

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
