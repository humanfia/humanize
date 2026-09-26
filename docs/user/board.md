<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const heading = '   [b]Board[/] · [m]what you and the flow both write on[/]'
const todo = ' [b]❯[/] [c]◈[/] todo                      [m]write the parser[/]'
const doing = "   [m]◈[/] doing                     [m]tokenizer[/] · [m]flow's[/]"
const add = ['', '        [b]add[/]                       [m]a line[/]']
const keys = '   [m]↑↓ move · enter read or change · a add · d twice takes one away · esc close[/]'
// What sits between is the rest of the sheet -- the flow, what it has cost -- left out here.
const gap = ['', '   [m]⋮[/]', '']
const said = (words) => (words ? [...gap, `   [m]${words}[/]`, '', keys] : [...gap, keys])

const board = [
  {
    label: 'the board',
    lines: [heading, todo, doing, ...add, ...said('')],
    caption: "A line marked <code>flow's</code> is not yours to change.",
  },
  {
    label: 'd',
    lines: [heading, todo, doing, ...add, ...said('press d again to take todo off the board')],
    caption: 'The first <kbd>d</kbd> only asks. Moving the cursor cancels it.',
  },
  {
    label: 'd again',
    lines: [heading, doing, ...add, ...said('todo is off the board')],
    caption: 'The second <kbd>d</kbd> takes the line off at once. There is nothing to save.',
  },
]
</script>

# The mission board

A run of a flow never has a board: a flow has no way to read or write one. The board belongs to
the person agent in humanize's lower [agent layer](/reference/agents), and a run that holds one
shows it on [`/monitor`](/user/monitor), under the drawing.

## Try it

Where a run has a board, <kbd>esc</kbd> opens it on `/monitor`. Press the keys to see what
they do:

<TermScreen title="hmz · /monitor, cropped to the board" :frames="board" art />

## The keys

| Key | Does |
| --- | --- |
| <kbd>a</kbd>, or <kbd>enter</kbd> on `add` | Put up a line: type its name, <kbd>enter</kbd>, then what it says, <kbd>enter</kbd>. |
| <kbd>enter</kbd> on a line | Change what it says. |
| <kbd>d</kbd> twice | Take the line off. |
| <kbd>esc</kbd> | Close `/monitor`. |

A board line never stops the run, and nothing waits for it. To give a running loop more work,
edit the file it reads each round instead; see [Loops](/weaver/loops).

## See also

- [Watching a run](/user/monitor)
- [Questions](/user/questions), for an answer a run is waiting on
