<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const heading = '   [b]Board[/] · [m]shared by you and the flow[/][n]1[/]'
const todo = ' [b]❯[/] [c]◈[/] todo                      [m]write the parser[/][n]2[/]'
const doing = "   [m]◈[/] doing                     [m]tokenizer[/] · [m]flow's[/][n]3[/]"
const add = ['   [m]+[/] [m]add entry[/][n]4[/]']
// What sits between is the rest of the monitor -- the flow, what it has cost -- left out here.
const gap = ['', '   [m]⋮[/]', '']
const said = (words, mark = '') => [
  ...gap,
  ...(words ? [`[m]${words}[/]${mark}`] : []),
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: '[c]▣[/] monitor[m] · graph[/]',
    keys: '↑↓ node · enter open · → back · ctrl+t list · / commands',
  },
]

const board = [
  {
    label: '1 · the board',
    lines: [heading, todo, doing, ...add, ...said('')],
    caption: "A line marked <code>flow's</code> is not yours to change.",
  },
  {
    label: '2 · enter, then empty it',
    lines: [
      heading.replace('[n]1[/]', ''),
      doing.replace('[n]3[/]', ''),
      '   [m]+[/] [m]add entry[/]',
      ...said('todo removed from the board', '[n]5[/]'),
    ],
    caption:
      '<kbd>enter</kbd> opens the line on a sheet of its own, <code>monitor › todo</code>; delete what it says and <kbd>enter</kbd> again (or <strong>Save</strong>) takes it off at once. Nothing else waits to be saved.',
  },
]
</script>

# The mission board

The board is a handful of named lines kept beside a run, that you and the run both write and
neither waits on. It belongs to the person agent in humanize's lower
[agent layer](/reference/agents), and a run that holds one shows it on
[the monitor](/user/monitor), under the drawing.

::: warning A run of a flow never has a board
A flow has no way to read or write one, so no run started with `/flow`, `$name` or `hmz exec`
shows it. This page is for programs built on the agent layer that hold a person agent.
:::

::: info At a glance
- **You will** read, add, change and remove the lines of a run's board.
- **Use it when** a program on the agent layer keeps its work list there, and you want to add
  to it or correct it without stopping anything.
- **You need** a run that holds a board. Where there is none, nothing is drawn.
:::

## Try it

Where a run has a board, press <kbd>←</kbd> with nothing typed to go up to the monitor. The
board is under the drawing: walk to `+ add entry` and press <kbd>enter</kbd>.

## How it works

A question [stops the turn](/user/questions) until somebody answers. The board is the other
shape: lines anybody can change at any time, where nothing waits. A line is a **name** and what
it **says**, and it says whose it is to change:

| Line | Who may change it |
| --- | --- |
| ordinary | you or the run |
| marked `flow's` | the run alone |

What the lines mean is up to whoever reads them. `todo`, `doing` and `done` holding a few words
each make a work list, but nothing here is that list: it is only lines.

## Example: take a finished item off

The board holds `todo`, which is yours, and `doing`, which is the run's. You have written the
parser yourself, so `todo` should go:

<TermScreen title="hmz · the monitor, cropped to the board" :frames="board" art />

What to look at, by number:

1. **`Board · shared by you and the flow`.** The heading. The board sits under the drawing,
   below the boxes.
2. **A line you may change**, `◈` in colour, its name and then what it says. The cursor walks
   onto it as onto a box.
3. **`· flow's`.** A line the run keeps for itself. <kbd>enter</kbd> on it says
   `doing can only be changed by the flow`.
4. **`+ add entry`**, always last: <kbd>enter</kbd> on it puts a new line up.
5. **`todo removed from the board`.** Saved empty, a line is taken off at once.

### Check it worked

The line under the drawing says what happened to the board: `<name> saved to the board`,
`<name> removed from the board`, or `nothing was entered, so nothing was saved`. The board
itself changes at the same moment, in every interface reading the run.

## The keys

| Key | Does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move between the lines, as between the boxes above them. |
| <kbd>enter</kbd> on `+ add entry` | Put up a line, on a sheet over the monitor, `monitor › Board entry`: type its name, <kbd>enter</kbd> (or **Next**), then what it says, <kbd>enter</kbd> (or **Save**). |
| <kbd>enter</kbd> on a line | Change what it says, on the sheet `monitor › <name>`, then <kbd>enter</kbd> (or **Save**). Saved empty, the line is taken off. |
| <kbd>esc</kbd> | While writing a line: back, changing nothing. |
| <kbd>→</kbd> | Back to the log. |

On the sheet, typing writes and <kbd>backspace</kbd> deletes; <kbd>tab</kbd> reaches its one
button, **Next** while it asks the name and **Save** once it asks what the line says. Its last
line says the keys: `type write   backspace delete   enter continue to value   tab actions   esc back`
while it asks the name.

A board line never stops the run, and nothing waits for it. To give a running flow more work,
edit the file it reads each round instead; see [Loops](/weaver/loops).

## Troubleshooting

### There is no board under the drawing

The run holds none, which is every run of a flow. See the warning at the top of this page.

### `a board entry needs a name`

You pressed <kbd>enter</kbd> on an empty name. Type one, or <kbd>esc</kbd> to leave.

### `<name> can only be changed by the flow`

That line is marked `flow's`. Put up a line of your own under another name instead.

## Next steps

- [Watching a run](/user/monitor): the rest of the screen the board sits on.
- [Questions](/user/questions): for an answer a run is waiting on.
- [Agents reference](/reference/agents): the layer a board belongs to.
