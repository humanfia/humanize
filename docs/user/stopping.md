<script setup>
import CtrlC from '../.vitepress/theme/components/user-prompt/CtrlC.vue'
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Stopping

Press <kbd>ctrl+c</kbd> twice, or send `/stop`. The whole flow stops, not just the turn it is
in. Most flows are loops that never end on their own, so this, or a budget, is how they end.

<CtrlC />

## The ways to stop

| | Where | How |
| --- | --- | --- |
| <kbd>ctrl+c</kbd> <kbd>ctrl+c</kbd> | at the prompt | Two presses within 3 seconds. The first only warns. |
| `/stop` | at the prompt | Sent once. You typed it out on purpose, so it is not asked twice. |
| <kbd>ctrl+c</kbd> | on an `hmz exec` line | One press. |
| a budget | `-b` on `hmz exec`, or what a run may spend in `/flow` | Nothing to press: the run stops itself when the budget is spent. See [Allowances](/features/allowances). |

## What the next <kbd>ctrl+c</kbd> does

The key does the nearest thing there is to take back, and the last entry on the status line
under the prompt always says what that is:

| The status line ends with | The next press |
| --- | --- |
| `ctrl+c clear` | Clears what you have typed. Nothing else happens. |
| `ctrl+c stop` | Warns: `— press ctrl+c again to stop the flow —` |
| `ctrl+c again to stop` | Stops the flow. |
| `ctrl+c close them` | Closes the agents still in a turn, without waiting for the flow to wind down. |
| `ctrl+c exit` | Warns: `— press ctrl+c again to leave —` |
| `ctrl+c again to exit` | Quits `hmz`. |

A press more than 3 seconds after the last one starts over from the top, and so does a press
after a `/stop`.

<kbd>esc</kbd> never stops anything. It opens [`/monitor`](/user/monitor).

## What a stop does

- **The turn is cut off where it is.** The agent's CLI stops, along with anything it had
  started. A file the agent was halfway through writing stays halfway written.
- **The flow winds down in its own time.** A loop finishes its round and what it opened is
  closed. Until it is done, the status line ends with `ctrl+c close them`, and one more press
  closes the agents without waiting.
- **The run is recorded as stopped**, not as finished. [`/epics`](/user/tracing) lists it that
  way.

## Leaving `hmz`

`/exit`, or <kbd>ctrl+q</kbd>, leaves. With nothing running, it just closes. With a flow
running, it asks first:

<Term title="/exit">

<pre><span class="p b">A flow is running.</span>

<span class="p">❯</span> <span class="d">1.</span> <span class="p">stop it, then leave</span>
  <span class="d">2.</span> <span class="p">leave it running</span>          <span class="m">`hmz` opens it again</span>

<span class="d">enter choose · esc stay</span></pre>

</Term>

**leave it running** lets the flow carry on without your terminal. Run `hmz` again in the same
directory to get back to it. When humanize cannot hold the run apart from the terminal
(input or output is not a terminal, or `HUMANIZE_DAEMON=off` is set), the second answer is
**stay here** instead.

## After a stop

**Pick the run up** with `/resume`, or with the same `hmz exec` line plus `--resume`. This
works for a flow that says it can be picked up. It carries on with the same flow, agents and
task, from where the stop left it. See [Picking a run up](/user/resuming).

**Wait for the flow to finish stopping first.** Until then, `/resume` answers:

```
hmz: no picking a run up while the flow is still stopping: it is closing out the turn it was in
```

A third <kbd>ctrl+c</kbd> ends the wait.

**Choose another flow once this one has stopped.** While a flow runs, `/flow <name>` and a
`$name` line are refused with `hmz: a flow is running; no choosing a flow`. `/flow` on its own
opens the agents of the running flow instead. What you save there is what the next run
starts with; the running one keeps what it started with.

## What does not stop a flow

| | What it does instead |
| --- | --- |
| <kbd>esc</kbd> | Opens [`/monitor`](/user/monitor). |
| `/clear` | Clears the transcript you are reading. The flow keeps running. |
| a question the flow asked you | Ends with the flow when it stops. It never holds a stop up. |
| a second `/stop` | Says `hmz: the flow is already stopping: …`. A <kbd>ctrl+c</kbd> is what hurries it. |

::: details If you write flows
A stop reaches your flow as a cancellation, not as a failed turn. Code that catches failed
turns does not catch it, and it should not be caught: let it through, so the run is recorded
as stopped. To cap one turn rather than the whole run, give that turn a
[budget of its own](/features/budgets). [Loops](/weaver/loops) shows a loop written this way.
:::

## See also

- [Picking a run up](/user/resuming): carrying on from where a stop left it
- [Talking to a running turn](/user/steering): when a word in its ear is enough
- [Being away](/user/afk)
- [TUI reference](/reference/tui): every key and command

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
