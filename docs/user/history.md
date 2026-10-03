<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const status = '[c]◉[/] chat[m] · ~/tmp/humanize-demo[/]'
const at = (label, line, n, caption) => ({
  label,
  lines: [
    '[dim]❯[/] /afk on',
    '[dim]away: agents that ask are told nobody is here[/]',
    '[dim]❯[/] /afk off',
    '[dim]here: an agent may stop and ask you[/]',
    '[dim]❯[/] /clear',
    '',
    { rule: true },
    { prompt: n ? `${line}[n]${n}[/]` : line },
    { rule: true },
    { l: status, keys: 'enter start · / commands · shift+enter newline · ctrl+c clear' },
  ],
  caption,
})

const walk = [
  at('typed', 'fix the flaky', 1, 'Half a line typed, and three lines sent before it.'),
  at('↑', '/clear', 2, 'The newest line you sent. What you had typed is kept aside.'),
  at('↑ ↑', '/afk off', 0, 'One further back.'),
  at('↑ ↑ ↑', '/afk on', 3, 'The oldest. Another <kbd>↑</kbd> stays here: there is nothing older.'),
  at('↓ ↓ ↓', 'fix the flaky', 4, 'Down past the newest, and your own half-typed line is back.'),
]
</script>

# History

Press <kbd>↑</kbd> at the prompt to bring back the last line you sent. Keep pressing to go
further back, and <kbd>↓</kbd> to come forward again. Whatever you were typing is kept: step
past the newest line and it comes back.

::: info At a glance
- **You will** send a line again, or a changed copy of it, without typing it out.
- **Use it when** you give the same task or the same steer more than once, or want to fix a
  typo in a long line you just sent.
- **You need** `hmz` open, and at least one line sent before. Anywhere counts.
:::

## Try it

At an empty prompt, press <kbd>↑</kbd>. Edit what comes back if you like, and press
<kbd>enter</kbd>.

<HmzCast name="history" alt="hmz: three commands sent; then, with &quot;fix the flaky&quot; half typed, up brings back /afk off, /clear and /afk on in turn, and down walks forward again until &quot;fix the flaky&quot; is back at the prompt" />

## How it works

Every line you send at the prompt is written down, with the directory you sent it in. The
arrows walk that list, newest first, and put each line in the editor as if you had typed it.
Nothing is sent until you press <kbd>enter</kbd>, so a line brought back is yours to change.

The walk has a draft: whatever was in the editor when you pressed the first <kbd>↑</kbd>. It is
kept aside, not lost, and <kbd>↓</kbd> past the newest line gives it back. A key pressed by
mistake cannot take a half-written prompt with it.

## Example: walk back three lines and return

You have sent `/afk on`, `/afk off` and `/clear` here, and have now typed `fix the flaky`.
Step through the presses:

<TermScreen title="hmz · chat" :frames="walk" />

What to look at, by number:

1. **Your draft.** Half a line, not sent. The first <kbd>↑</kbd> sets it aside.
2. **The newest line first.** `/clear` was the last thing you sent, so it comes back first.
3. **The far end.** `/afk on` is the oldest line here. Pressing <kbd>↑</kbd> again leaves it
   where it is.
4. **The draft, back.** <kbd>↓</kbd> walks forward through the same lines, and one step past
   the newest returns what you were typing.

The same walk as a table:

| You press | The prompt shows |
| --- | --- |
| (nothing yet) | `fix the flaky` |
| <kbd>↑</kbd> | `/clear` |
| <kbd>↑</kbd> | `/afk off` |
| <kbd>↑</kbd> | `/afk on` |
| <kbd>↑</kbd> | `/afk on` (nothing older, so it stays) |
| <kbd>↓</kbd> | `/afk off` |
| <kbd>↓</kbd> | `/clear` |
| <kbd>↓</kbd> | `fix the flaky`, your own line back |

### Check it worked

- The line in the editor is the one you wanted, and the status line offers `enter start` (or
  `enter send`, with a flow running).
- A line brought back opens no [completion](/user/completion) list, so the arrows keep walking.

## What goes in

Every line you send: a task that starts a flow, a word to one [already
running](/user/steering), an answer to a question, a command. A line the same as the one
before it is kept once. What agents say is never in it, and neither is a task you gave
`hmz exec`: your shell's history keeps that.

## Which lines you walk

The lines you sent **in this directory**. A directory where you have sent nothing yet walks
everything you have sent anywhere, so a new project still has something to go back through.
Which of the two applies is settled when `hmz` starts, so send one line in a new project and
it has its own history from the next start.

## Variations

- **Several lines in the editor.** In a prompt of several lines, <kbd>↑</kbd> walks back only
  from the first line and <kbd>↓</kbd> only from the last; anywhere else they move the cursor,
  as usual.
- **With a completion list open**, the arrows move through the list instead. Press
  <kbd>esc</kbd> to put it away, then walk.
- **Send a task to another flow.** Bring back a `$ralph_loop …` line and change the flow name:
  the task comes along.

## Troubleshooting

### <kbd>↑</kbd> moves the cursor instead of walking

The cursor is not on the first line of a prompt of several lines, or a completion list is open.
Move to the first line, or press <kbd>esc</kbd>.

### A new project walks lines from other projects

Nothing has been sent in this directory yet, so the walk falls back to everything. Send one
line here, and from the next `hmz` start it walks this directory's lines only.

### A line I sent is missing

A line the same as the one before it is kept once. A task given to `hmz exec` is not kept:
look in your shell's history.

::: details Clearing it
History is one file, `~/.hmz/history.jsonl` (under `$HUMANIZE_HOME` if you set that).
Delete it to forget every line you have sent, everywhere. Nothing else is lost.
:::

## Next steps

- [Completion](/user/completion): finish a word instead of typing it.
- [Settings](/user/settings): the other thing kept between starts.
- [Exporting a run](/user/export): for what actually happened in a run, not what you typed.
