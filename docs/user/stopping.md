<script setup>
import CtrlC from '../.vitepress/theme/components/user-prompt/CtrlC.vue'
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const said = [
  '[dim]❯[/] Run the test suite until it is green. Do not commit.',
  '[dim]── agent[/]',
  '[dim]● agent is working[/]',
]
const agent = (mark) => ({ r: `[m]agent · claude/claude-haiku-4-5-20251001:high · ${mark} 1[/]` })
const spent = { r: '[m]$0.02 · 28 out/s[/]' }
const running = '[c]·|·[/] agent… [m](23s · ctrl+c twice to stop)[/]'
const keys = '/ commands · shift+enter newline · ← monitor · '
const below = (mark, status, last) => [
  '',
  agent(mark),
  spent,
  { rule: true },
  { prompt: '' },
  { rule: true },
  { l: status, keys: keys + last },
]

const stop = [
  {
    label: '1 · running',
    lines: [...said, ...below('●', running, 'ctrl+c stop[n]1[/]')],
    caption: 'A turn is open. The last key on the status line says what the next press does.',
  },
  {
    label: '2 · first press',
    lines: [
      ...said,
      { t: '[dim]— press ctrl+c again to stop the flow —[/][n]2[/]', hl: true },
      ...below('●', running, 'ctrl+c again to stop'),
    ],
    caption: 'The first press only warns. You have three seconds for the second.',
  },
  {
    label: '3 · second press',
    lines: [
      ...said,
      '[dim]— press ctrl+c again to stop the flow —[/]',
      { t: '[dim]— stopping the flow —[/][n]3[/]', hl: true },
      { t: '[y]●[/] [dim]cutting the turn off: interrupted[/][n]4[/]', hl: true },
      ...below('●', running, 'ctrl+c force stop[n]5[/]'),
    ],
    caption: 'The flow is told to stop and winds down. A third press would not wait for it.',
  },
  {
    label: '4 · stopped',
    lines: [
      ...said,
      '[dim]— press ctrl+c again to stop the flow —[/]',
      '[dim]— stopping the flow —[/]',
      '[y]●[/] [dim]cutting the turn off: interrupted[/]',
      '[y]●[/] [dim]turn cut off: interrupted[/]',
      '[dim]✻ Worked for 24s · agent[/]',
      ...below('○', '[c]◉[/] ralph_loop[m] · ~/tmp/humanize-demo[/][n]6[/]', 'ctrl+c exit'),
    ],
    caption: 'Stopped. The status line is back to the flow and the directory, ready for the next task.',
  },
]
</script>

# Stopping

Press <kbd>ctrl+c</kbd> twice, or send `/stop`. The whole flow stops, not just the turn it is
in. Most flows are loops that never end on their own, so this, or a budget, is how they end.

::: info At a glance
- **You will** end a run by hand, and know what state it leaves your files and the run in.
- **Use it when** the work is done, the run has gone the wrong way, or it is spending more
  than it is worth.
- **You need** a flow running in `hmz`. [Your first run](/user/first-run) starts one.
:::

## Try it

With nothing typed at the prompt, press <kbd>ctrl+c</kbd>, then <kbd>ctrl+c</kbd> again within
3 seconds. Or type:

```text
❯ /stop
```

<CtrlC />

## How it works

<kbd>ctrl+c</kbd> always does the nearest thing there is to take back, and the last entry on
the status line under the prompt says what that is. While you are typing, it clears your line.
While a flow runs, it stops the flow, but only on the second press, so a key pressed by
accident costs nothing. With nothing running, it leaves `hmz`, also on the second press.

A stop is not an undo. It ends the run where it is:

- **The turn is cut off where it is.** The agent's CLI stops, along with anything it had
  started. A file the agent was halfway through writing stays halfway written.
- **The flow winds down in its own time.** A loop finishes its round and what it opened is
  closed. Until it is done, the status line ends with `ctrl+c force stop`, and one more press
  closes the agents without waiting.
- **The run is recorded as stopped**, not as finished. [`/epics`](/user/tracing) lists it that
  way, and a flow that can be picked up is marked `resumable`.

## Example: stop a loop with <kbd>ctrl+c</kbd>

A [`ralph_loop`](/flows/ralph-loop) run is working on a test suite, and you have seen enough.
Step through the four moments of stopping it:

<TermScreen title="hmz · ralph_loop" :frames="stop" />

What to look at, by number:

1. **`ctrl+c stop`.** The last key on the status line. It is what the next press does, and it
   changes with what is on the screen: with something typed it reads `ctrl+c clear`.
2. **The warning.** The first press only says what the second will do. Wait more than 3
   seconds and the next press is a first press again.
3. **`— stopping the flow —`.** The second press. The flow has been told to stop, for
   everybody reading the run, not just this terminal.
4. **The yellow `●` line.** humanize saying what it is doing about the turn: cutting it off.
   It shows even with [details](/user/settings#details) off.
5. **`ctrl+c force stop`.** The flow is winding down. A third press closes every agent still in
   a turn without waiting. You rarely need it.
6. **The status line back at rest.** `◉` and the flow's name mean nothing is running, and
   <kbd>enter</kbd> on a task starts the flow again. The last key is `ctrl+c exit` once more.

### Check it worked

- The status line reads `◉ <flow> · <directory>`, with no clock after it.
- Each agent's line above the editor shows `○`: nothing has a turn open.
- `/epics` lists the run at the top, marked `stopped`:

  ```text
  ❯ 1. 2026-09-30 05:36 · ralph_loop Run the test suite … · 4 sessions · stopped · resumable
  ```

- `git diff` shows what the agent changed before it was cut off. Look for half-written files.

## The ways to stop

| | Where | How |
| --- | --- | --- |
| <kbd>ctrl+c</kbd> <kbd>ctrl+c</kbd> | at the prompt | Two presses within 3 seconds. The first only warns. |
| `/stop` | at the prompt, reading every agent, or on the monitor | Sent once. You typed it out on purpose, so it is not asked twice. Offered only while a flow runs and is not already stopping, and not on one conversation's or one outworlder's transcript. Typed there anyway, it says why it did nothing. |
| <kbd>ctrl+c</kbd> | on an `hmz exec` line | One press. |
| a budget | `-b` on `hmz exec`, or what a run may spend in `/flow` | Nothing to press: the run stops itself when the budget is spent. See [Allowances](/features/allowances). |

## What the next <kbd>ctrl+c</kbd> does

| The status line ends with | The next press |
| --- | --- |
| `ctrl+c clear` | Clears what you have typed. Nothing else happens. |
| `ctrl+c stop` | Warns: `— press ctrl+c again to stop the flow —` |
| `ctrl+c again to stop` | Stops the flow. |
| `ctrl+c force stop` | Closes the agents still in a turn, without waiting for the flow to wind down. |
| `ctrl+c exit` | Warns: `— press ctrl+c again to exit —` |
| `ctrl+c again to exit` | Quits `hmz`. |

A press more than 3 seconds after the last one starts over from the top, and so does a press
after a `/stop`.

<kbd>esc</kbd> never stops anything, and neither does <kbd>←</kbd>, which goes up to
[the monitor](/user/monitor).

## Leaving `hmz`

`/exit`, or <kbd>ctrl+q</kbd>, leaves. With nothing running, it just closes. With a flow
running, it asks first:

<Term title="/exit">

<pre><span class="p b">A flow is running.</span><span class="n">1</span>

<span class="p">❯</span> <span class="d">1.</span> <span class="p">stop the flow and exit</span><span class="n">2</span>
  <span class="d">2.</span> <span class="p">detach and exit</span>           <span class="m">run `hmz` here to reattach</span><span class="n">3</span>

<span class="d">enter choose · esc stay</span><span class="n">4</span></pre>

</Term>

1. **The question** only appears while a flow runs. With nothing running, `/exit` closes at
   once.
2. **stop the flow and exit** stops it for everybody, as `/stop` and <kbd>ctrl+c</kbd> twice
   do, then closes this terminal's `hmz`.
3. **detach and exit** lets the flow carry on without your terminal, and without letting go of
   anybody else reading it. Run `hmz` again in the same directory to get back to it. See
   [Leaving it running](/user/leaving).
4. **<kbd>esc</kbd> stays**, with the flow untouched.

When humanize cannot hold the run apart from the terminal (input or output is not a terminal,
or `HUMANIZE_DAEMON=off` is set), the second answer is **cancel** instead.

## After a stop

**Pick the run up** with `/resume`, or with the same `hmz exec` line plus `--resume`. This
works for a flow that says it can be picked up. It carries on with the same flow, agents and
task, from where the stop left it:

```text
❯ /resume
resuming 20260930T054202.927Z-a5d31a: running ralph_loop from saved state
● agent is working
```

See [Picking a run up](/user/resuming).

**Choose another flow once this one has stopped.** While a flow runs, `/flow <name>` and a
`$name` line are refused. `/flow` on its own opens the agents of the running flow instead. What
you save there is what the next run starts with; the running one keeps what it started with.

## What does not stop a flow

| | What it does instead |
| --- | --- |
| <kbd>←</kbd> | With nothing typed, goes up to [the monitor](/user/monitor). |
| <kbd>esc</kbd> | Puts away a list or a menu, or leaves [btw mode](/user/btw). The flow keeps running. |
| `/clear` | Clears the transcript you are reading. The flow keeps running. |
| a line you type | Goes into the running turn. See [Talking to a running turn](/user/steering). |
| a question the flow asked you | Ends with the flow when it stops. It never holds a stop up. |
| a second `/stop` | No longer offered. Typed anyway, says `hmz: the flow is already stopping: …`. A <kbd>ctrl+c</kbd> is what hurries it. |

## Variations

- **Stop at a budget, not by hand.** Give the run a `duration` or `cost` in `/flow`, or `-b` on
  `hmz exec`, and it stops itself. With `graceful` on, the turn that is running finishes first.
  See [Every run has a budget](/features/allowances).
- **Stop from another terminal.** Run `hmz` in the same directory: it opens on the running flow.
  Then stop it there. See [Leaving it running](/user/leaving).
- **Stop an unattended run.** One <kbd>ctrl+c</kbd> on the `hmz exec` line. See
  [Run it unattended](/user/unattended).

## Troubleshooting

### It still says `ctrl+c force stop` long after I stopped it

The flow is winding down: a loop finishing its round, or a backend slow to notice its turn was
cut off. Press <kbd>ctrl+c</kbd> once more to close every agent still in a turn. The line
`— closed 1 conversation(s) mid-turn —` says how many it closed.

### `hmz: cannot resume a run while the flow is still stopping: it is finishing the turn it was in`

A run is picked up from where it wrote down it got to, and it is still writing that. Wait until
the status line reads `◉ <flow>`, or press <kbd>ctrl+c</kbd> to end the wait, then `/resume`
again.

### `hmz: cannot resume a run while a flow is running: press ctrl+c twice to stop it first`

`/resume` picks up a run that has stopped. Stop the one that is running first.

### `hmz: cannot choose a flow while one is running`

`/flow <name>` and `$name` would swap the flow out from under its agents. Stop the run first,
then choose. `/flow` on its own still opens the running flow's agents, for the next run.

### `hmz: no flow is running`

`/stop` was typed with nothing to stop. To leave `hmz`, use `/exit`.

### The first <kbd>ctrl+c</kbd> cleared my line instead of warning

With text in the editor, <kbd>ctrl+c</kbd> clears it and does nothing else; the status line said
`ctrl+c clear`. Press it twice more with the editor empty.

::: details If you write flows
A stop reaches your flow as a cancellation, not as a failed turn. Code that catches failed
turns does not catch it, and it should not be caught: let it through, so the run is recorded
as stopped. To cap one turn rather than the whole run, give that turn a
[budget of its own](/features/budgets). [Loops](/weaver/loops) shows a loop written this way.
:::

## Next steps

- [Picking a run up](/user/resuming): carrying on from where a stop left it.
- [Leaving it running](/user/leaving): walk away without stopping it.
- [Talking to a running turn](/user/steering): when a word in its ear is enough.
- [Being away](/user/afk): keep a run you left from waiting on you.
- [TUI reference](/reference/tui): every key and command.
