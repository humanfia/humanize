<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const heading = '   [b]Board[/] · [m]what you and the flow both write on[/]'
const todo = ' [b]❯[/] [c]◈[/] todo                      [m]write the parser[/]'
const doing = "   [m]◈[/] doing                     [m]tokenizer[/] · [m]flow's[/]"
const add = ['   [m]+[/] [m]a new line[/]']
// What sits between is the rest of the monitor -- the flow, what it has cost -- left out here.
const gap = ['', '   [m]⋮[/]', '']
const said = (words) => [...gap, ...(words ? [`[m]${words}[/]`] : []), { rule: true }, { prompt: '' }, { rule: true }, {
  l: '[c]▣[/] monitor[m] · a node per agent[/]',
  keys: '↑↓ node · enter read · → back · ctrl+t by session · / commands',
}]

const board = [
  {
    label: 'the board',
    lines: [heading, todo, doing, ...add, ...said('')],
    caption: "A line marked <code>flow's</code> is not yours to change.",
  },
  {
    label: 'enter, then empty it',
    lines: [heading, doing, ...add, ...said('todo is off the board')],
    caption: '<kbd>enter</kbd> opens the line; rub out what it says and <kbd>enter</kbd> again takes it off at once. There is nothing to save.',
  },
]
</script>

# The mission board

A run of a flow never has a board: a flow has no way to read or write one. The board belongs to
the person agent in humanize's lower [agent layer](/reference/agents), and a run that holds one
shows it on [the monitor](/user/monitor), under the drawing.

## Try it

Where a run has a board, <kbd>←</kbd> on an empty prompt goes up to the monitor, and the board
is under the drawing. Press the keys to see what they do:

<TermScreen title="hmz · the monitor, cropped to the board" :frames="board" art />

## The keys

| Key | Does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move between the lines, as between the boxes above them. |
| <kbd>enter</kbd> on `+ a new line` | Put up a line: type its name, <kbd>enter</kbd>, then what it says, <kbd>enter</kbd>. |
| <kbd>enter</kbd> on a line | Change what it says, then <kbd>enter</kbd>. Saved empty, the line is taken off. |
| <kbd>esc</kbd> | While writing a line: back, changing nothing. |
| <kbd>→</kbd> | Back to the log. |

A board line never stops the run, and nothing waits for it. To give a running loop more work,
edit the file it reads each round instead; see [Loops](/weaver/loops).

## See also

- [Watching a run](/user/monitor)
- [Questions](/user/questions), for an answer a run is waiting on
