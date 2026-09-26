# History

Press <kbd>↑</kbd> at the prompt to bring back the last line you sent. Keep pressing to go
further back, and <kbd>↓</kbd> to come forward again. Whatever you were typing is kept: step
past the newest line and it comes back.

![hmz: three commands sent; then, with "fix the flaky" half typed, up brings back
/details off, /afk on and /details on in turn, and down walks forward again until "fix the
flaky" is back at the prompt](/demo/history.gif)

## What a walk looks like

Say you have sent two lines here, `/details on` and then `$ralph_loop fix the build`, and have
now typed `and the tests`:

| You press | The prompt shows |
| --- | --- |
| (nothing yet) | `and the tests` |
| <kbd>↑</kbd> | `$ralph_loop fix the build` |
| <kbd>↑</kbd> | `/details on` |
| <kbd>↑</kbd> | `/details on` (nothing older, so it stays) |
| <kbd>↓</kbd> | `$ralph_loop fix the build` |
| <kbd>↓</kbd> | `and the tests`, your own line back |

A line you bring back is yours to edit before sending. It opens no
[completion](/user/completion) list, so the arrows keep walking.

In a prompt of several lines, <kbd>↑</kbd> walks back only from the first line and <kbd>↓</kbd>
only from the last; anywhere else they move the cursor, as usual. With a completion list open,
they move through the list instead.

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

::: details Clearing it
History is one file, `~/.humanize/history.jsonl` (under `$HUMANIZE_HOME` if you set that).
Delete it to forget every line you have sent, everywhere. Nothing else is lost.
:::

## See also

- [Completion](/user/completion): finishing a word instead of typing it
- [What a project remembers](/user/settings): the other thing kept between starts
- [Exporting a run](/user/export): for what actually happened in a run, not what you typed

<style scoped>
kbd {
  display: inline-block;
  min-width: 1.7em;
  padding: 0 0.45em;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-base);
  font-size: 0.85em;
  font-weight: 500;
  line-height: 1.6;
  text-align: center;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}
</style>
