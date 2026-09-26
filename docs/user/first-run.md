# Your first run

You set up `ralph_loop` in a scratch repository, start it on a small bug, watch it work, and
stop it once the bug is fixed. At the end, that directory remembers the setup, so the next run
there is one line.

You need humanize and one signed-in coding agent CLI. See [Installation](/user/installation).

::: warning Use a scratch repository
A flow's agents run with approvals bypassed: they edit files and run commands without asking
you. Start somewhere you can throw away, and read [Security](/user/security) before you point a
flow at work you care about.
:::

![The flow menu: a project flow is chosen, its one agent is set to another model and effort,
a budget of 20 minutes is set, and the menu is saved. The task is then typed at the
prompt.](/demo/first-run.gif)

<p class="u7-caption">The same steps, recorded with stand-in CLIs on a project's own flow,
<code>local/twice</code>.</p>

## 1. Make something to fix

`calc.py` subtracts where it should add:

```sh
mkdir -p ~/tmp/humanize-demo && cd ~/tmp/humanize-demo && git init -q
printf 'def add(a, b):\n    return a - b\n' > calc.py
git add -A && git commit -qm "a calculator with a bug in it"
git tag start
```

The tag marks where you started, so you can see everything the agent changed later, whether it
commits its work or not.

## 2. Open the interface

```sh
hmz
```

The first time, humanize asks whether to report what goes wrong to its developers. The question
says what a report carries; answer either way, and `/settings` changes it later
([Reporting](/user/reporting)).

The interface opens on `chat`: one agent that answers you, a turn at a time. For work that
runs on its own you choose a **flow**, the loop that tells agents what to do and when to stop.

## 3. Choose a flow

Type `/flow` and press <kbd>enter</kbd>. The flows are listed by where they come from.
`official` is humanize's own; <kbd>←</kbd> and <kbd>→</kbd> step to your project's flows
(`local`) and your own (`user`) once you have some.

Press <kbd>s</kbd>, type `ralph`, and press <kbd>enter</kbd> on `ralph_loop`. It gives one
agent the same task again and again, in a fresh conversation each round, until its budget runs
out or you stop it. See [ralph_loop](/flows/ralph-loop).

::: details `official` lists only `chat`
The rest of humanize's flows are in a git repository, the official
[flowverse](/weaver/flowverses). `hmz` fetches it in the background every time it opens, and
`/flow` fetches it if that has not happened yet. If the fetch fails, `/flow` says why under the
list. Press <kbd>v</kbd> for the flowverses, where <kbd>r</kbd> fetches one again.
:::

## 4. Give the role an agent

The flow opens on its **roles**: a row for each agent it drives, then `budget` and `save`.
`ralph_loop` has one role, `agent`. humanize fills it with the first CLI it found, so the row
may already name one.

Press <kbd>enter</kbd> on `agent`. An agent is four rows:

::: code-group

```text [The roles]
ralph_loop
What each of its roles is given: an agent -- the CLI that
takes its turns, the account they run as, and the model at
an effort -- or where an environment is.

❯ 1. agent     claude/claude-opus-4-8:high

     budget    none yet; a run is given one

     save      the flow and its roles

enter open · shift+enter/ctrl+j save · esc back to the flows
```

```text [One agent]
Set up agent
What this one agent is: the CLI that takes its turns, the
account they run as, and the model at an effort.

  1. cli          claude ▸
  2. provider     as local ▸
  3. model        claude-opus-4-8 ▸
❯ 4. effort       high ↔

     save         this agent

←/→ or space change · shift+enter/ctrl+j save · esc close
```

```text [The budget]
What a run of ralph_loop may spend
A run stops at whichever limit it reaches first; at least
one is set. Empty or 0 is no limit on that one.

❯ 1. duration        20m
  2. cost            0.0 ↔
  3. output_tokens   0 ↔
  4. graceful        on ↔

type set · backspace rub out · enter accept · esc back
```

:::

| Row | What you choose | How |
| --- | --- | --- |
| `cli` | The coding agent CLI that takes its turns. Only CLIs that can fill this role are listed. | <kbd>enter</kbd>, then pick |
| `provider` | The account. `as local` is the CLI as you signed it in. | <kbd>enter</kbd>, then pick, or <kbd>a</kbd> to add one |
| `model` | One of the models that CLI said it runs. | <kbd>enter</kbd>, then pick; <kbd>r</kbd> asks the CLI again |
| `effort` | How hard it thinks, from the model's own list. | <kbd>←</kbd> <kbd>→</kbd> or <kbd>space</kbd> |

Choosing another CLI clears the account and the model, since both belong to a CLI. Press
<kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd> to save the agent. [Providers](/user/providers)
and [Efforts](/user/efforts) say more about accounts and efforts.

A flow that has settings of its own asks for them before its roles. `ralph_loop` has none.

## 5. Set a budget

Press <kbd>enter</kbd> on `budget`. The run stops at whichever limit it reaches first:

- `duration`: how long it may take, such as `20m` or `1h30m`;
- `cost`: how many US dollars it may spend;
- `output_tokens`: how much the models may write.

Type `20m` into `duration` and press <kbd>enter</kbd>. The row now reads `stops at 20m00s`.
If your account is billed by the token, set a `cost` as well. `graceful` on lets the turn that
is running finish; off cuts it off. Every flow except `chat` needs a budget. See
[Every run has a budget](/features/allowances).

## 6. Save

Press <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd>, from anywhere on the menu. The status line
now reads `◉ ralph_loop`, and humanize says `say what to do, and the flow starts on it`.

Nothing is applied before you save. <kbd>esc</kbd> steps back, and leaving a menu with changes
in it asks `Save?`. If a role has no agent or the flow has no budget yet, saving says which
instead.

## 7. Say what to do

```text
❯ Fix the bug in calc.py.
```

Press <kbd>enter</kbd> and the flow starts. What each agent says streams into the transcript as
it says it, and the status line shows who is working and for how long:

```text
                agent · claude/claude-opus-4-8:high · ● 3
             input 18.2k · output 1.4k · cache_read 41.0k
                                         $0.41 · 38 out/s
─────────────────────────────────────────────────────────
❯
─────────────────────────────────────────────────────────
 ·/· agent… (42s · ctrl+c twice to stop)  esc monitor · ctrl+c stop
```

While it runs:

| To | Do | More |
| --- | --- | --- |
| tell the agent something | type a line and press <kbd>enter</kbd>; it goes into the turn that is running | [Talking to a running turn](/user/steering) |
| see who is working, and who handed to whom | <kbd>esc</kbd>, or `/monitor` | [Watching a run](/user/monitor) |
| stop the flow | <kbd>ctrl+c</kbd> twice, or `/stop` | [Stopping](/user/stopping) |
| walk away and keep it going | close the terminal, or `/exit` | [Leaving it running](/user/leaving) |

A Ralph loop keeps going round until its budget is spent. Once `calc.py` is fixed, press
<kbd>ctrl+c</kbd> twice to stop it, and look at what it did:

```sh
git diff start
```

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

## Next time: one line

humanize remembers the setup for this directory, so the next `hmz` here opens on
`ralph_loop` with the same agent and budget. Type the task and press <kbd>enter</kbd>.

What this directory remembers:

- the flow you last saved, which `hmz` opens on;
- for every flow you have set up here: each role's agent (CLI, account, model and effort), the
  flow's own settings, and its budget.

To run another flow without opening the menu, put its name after a `$` at the start of the
line:

```text
❯ $ralph_loop Fix the bug in calc.py.
```

| The flow is | Name it |
| --- | --- |
| humanize's own | `$ralph_loop` |
| in this project's `.humanize/flows/` | `$local/twice` |
| in your `~/.humanize/flows/` | `$user/twice` |
| in a flowverse you added | `$<flowverse>/<flow>` |

A flow that is set up here starts at once. One that is not opens the menu on its roles, holding
your line, and saving starts it. `$ralph_loop` with nothing after it only chooses the flow.
While a flow is running, a `$` line is refused with `a flow is running; no choosing a flow`.

[What a project remembers](/user/settings) shows how to change or forget this.

## Next

- [Security](/user/security): what to check before you point a flow at real work.
- The tutorials take a real piece of work start to finish:
  [Beat a benchmark](/user/tutorials/take-home),
  [Port a project](/user/tutorials/port-a-project) and
  [Build a coding agent](/user/tutorials/build-an-agent).
- [Flows](/flows/) lists every flow humanize and its official flowverse offer.

<style scoped>
.u7-caption {
  margin-top: -8px;
  font-size: 0.85em;
  color: var(--vp-c-text-2);
}
kbd {
  display: inline-block;
  padding: 0 6px;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-mono);
  font-size: 0.85em;
  line-height: 1.6;
  white-space: nowrap;
}
</style>
