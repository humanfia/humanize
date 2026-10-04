<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const agent = 'agent · claude/claude-haiku-4-5-20251001:low'
const keys = '/ commands · shift+enter newline · ← monitor · ctrl+c stop'
const running = [
  {
    label: 'round 1',
    lines: [
      '[dim]❯[/] Fix the bug in calc.py.',
      '',
      '[dim]── agent[/][n]1[/]',
      '',
      '[dim]● agent is working[/]',
      '',
      "[g]●[/] I'll read the file to identify the bug.",
      '',
      '[g]●[/] Found the bug: the `add` function is subtracting instead of adding. Let me fix it.',
      '',
      '[g]●[/] Done. The `add` function was returning `a - b` instead of `a + b`—now it correctly adds the two numbers.',
      '',
      '[dim]✻ Worked for 7s · agent[/][n]2[/]',
      '',
      { t: '[dim]● agent is working · conversation 2 of 2[/][n]3[/]', hl: true },
      '',
      { r: `[m]${agent} · ● 2[/][n]4[/]` },
      { r: '[m]input 70 · output 1.1k · cache_read 146.5k · cache_write 22.2k[/][n]5[/]' },
      { r: '[m]$0.05 · 73 out/s[/]' },
      { rule: true },
      { prompt: '' },
      { rule: true },
      { l: '[c]·|·[/] agent… [m](3s · ctrl+c twice to stop)[/][n]6[/]', keys },
    ],
    caption:
      'A real run, with Claude Haiku at effort <code>low</code>. The first round fixed the bug in seven seconds; the second has just started, in a fresh conversation.',
  },
  {
    label: 'stopped',
    lines: [
      '[dim]● agent is working · conversation 2 of 2[/]',
      '',
      '[g]●[/] Let me check the git log to see what was supposed to be in this calculator.',
      '',
      '[dim]— press ctrl+c again to stop the flow —[/]',
      '[dim]— stopping the flow —[/]',
      '[y]●[/] [dim]cutting the turn off: interrupted[/]',
      '[y]●[/] [dim]turn cut off: interrupted[/]',
      '',
      '[dim]✻ Worked for 7s · agent[/]',
      '',
      { r: `[m]${agent} · ○ 2[/]` },
      { r: '[m]input 130 · output 2.2k · cache_read 286.7k · cache_write 29.9k[/]' },
      { r: '[m]$0.08 · 114 out/s[/]' },
      { rule: true },
      { prompt: '' },
      { rule: true },
      {
        l: '[c]◉[/] ralph_loop[m] · ~/tmp/humanize-demo[/][n]7[/]',
        keys: '/ commands · shift+enter newline · ← monitor · ctrl+c exit',
        hl: true,
      },
    ],
    caption:
      'Two presses of <kbd>ctrl+c</kbd>. The turn in progress is cut off, and the status line is back to the flow at rest.',
  },
]
</script>

# Your first run

You set up `ralph_loop` in a scratch repository, start it on a small bug, watch it work, and
stop it once the bug is fixed. At the end, that directory remembers the setup, so the next run
there is one line.

::: info At a glance
- **You will** choose a flow, give its role an agent and the run a budget, start it with a
  task, watch it, and stop it.
- **Use it when** you have just installed humanize, or want to see how any flow is set up at
  the prompt.
- **You need** humanize and one signed-in coding agent CLI
  ([Installation](/user/installation)), git, and about ten minutes. The run itself costs a few
  cents.
:::

::: warning Use a scratch repository
A flow's agents run with approvals bypassed: they edit files and run commands without asking
you. Start somewhere you can throw away, and read [Security](/user/security) before you point a
flow at work you care about.
:::

<HmzCast name="first-run" alt="The flow menu: a project flow is chosen, its one agent is set to another model and effort, a budget of 20 minutes is set, and the menu is saved. The task is then typed at the prompt." />

<p class="u7-caption">The same steps, recorded with stand-in CLIs on a project's own flow,
<code>@local/twice</code>.</p>

## Try it

In a git repository you can throw away:

```text
hmz
/flow                        choose ralph_loop, set its agent and budget, then save
❯ Fix the bug in calc.py.    the task; the flow starts
ctrl+c ctrl+c                stop it once the bug is fixed
```

The steps below take each of those in turn.

## How it works

Three words cover what you set up:

- A **flow** is the loop: which agent is asked what, in what order, and when to stop.
  [`ralph_loop`](/flows/ralph-loop), used here, gives one agent the same task again and again,
  in a fresh conversation each round, until its budget runs out or you stop it.
- A **role** is a slot the flow declares, such as `agent`, `builder` or `reviewer`. You fill
  each role with an **agent**: a CLI, the account it runs as, a model, and an effort.
- A **budget** is what a run may spend: time, dollars or output tokens. Every flow except
  `chat` needs one, because most flows are loops that never end on their own.

You set all three in the `/flow` menu, save, and then type the task. Nothing runs until you
send that first line.

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
runs on its own you choose a **flow**.

## 3. Choose a flow

Type `/flow` and press <kbd>enter</kbd>. It opens on **Installed**: every flow ready to run
here, the ones built into humanize first. Press <kbd>/</kbd>, type `ralph`, press
<kbd>enter</kbd> to go back to the list, and <kbd>enter</kbd> on `ralph_loop`:

<Term title="hmz · /flow">

<pre>  <span class="m">hmz › /flow ›</span> <span class="p b">Installed</span>
  <span class="m">Flows ready to run here: pick one to set it up and run it, or install more</span>
  <span class="m">from a flowverse.</span>

  <span class="p">╭────────────────────────────────────────────────────────────────────────╮</span>
  <span class="p">│</span>  ralph                                                                 <span class="p">│</span> <span class="n">1</span>
  <span class="p">╰────────────────────────────────────────────────────────────────────────╯</span>
  <span class="p">╭────────────────────────────────────────────────────────────────────────╮</span>
   <span class="p">built in</span> <span class="n">2</span>
  <span class="sel"> <b>ralph_loop</b>                                                     built in </span>
     <span class="m">The task again and again, a fresh session every round.</span>

   <b>stateful_ralph</b>                                                 <span class="m">built in</span>
     <span class="m">The task again and again, in one session that remembers.</span>
  <span class="p">╰────────────────────────────────────────────────────────────────────────╯</span>

    Install more…   Update   Uninstall   Copy here <span class="n">3</span>   Search…       Save

  <b>enter</b> set up   <b>/</b> search   <b>tab</b> actions   <b>esc</b> back</pre>

</Term>

1. **The search box.** It keeps the flows whose names hold the letters you typed, in that
   order. <kbd>esc</kbd> clears it, then steps out of the menu.
2. **`built in`** is where these flows come from: they ship with humanize. A flow you install
   from a [flowverse](/user/concepts#flowverse) is listed under that flowverse's name, and this
   project's own under `local`.
3. **Copy here** copies the flow under the cursor into this project, to read or change. You do
   not need it now; [Security](/user/security#listing-a-flow-runs-its-python) says when you
   would.

::: details More flows than these
**Install more…** goes to the flowverses: indexes of flows humanize can install, `official`
first. `hmz` fetches them in the background every time it opens. Open one, then a flow, and
install it; from then on it is listed here, with its version at the end of its row. See
[Flowverses](/weaver/flowverses#managing-flowverses).
:::

## 4. Give the role an agent

The flow opens on its **roles**: a row for each agent it drives, then `budget` and
`profiling`, and a **Save** button under them. `ralph_loop` has one role, `agent`. humanize
fills it with the first CLI it found, so the row already names one.

<Term title="hmz · /flow › ralph_loop">

<pre>  <span class="m">hmz › /flow › Installed ›</span> <span class="p b">ralph_loop</span>                    <span class="y">● unsaved changes</span>
  <span class="m">Configure each role: an agent (CLI, account, model and effort) or an</span>
  <span class="m">environment; then what the flow takes and what a run may spend.</span>

  <span class="p">╭────────────────────────────────────────────────────────────────────────╮</span>
  <span class="sel"> <b>agent</b>                                     claude/claude-opus-5-5:high ▸ </span> <span class="n">1</span>
     <span class="m">agent</span>
   ────────────────────────────────────────────────────────────────────────
   <b>budget</b>                                                           <span class="m">none ▸</span> <span class="n">2</span>
     <span class="m">what a run may spend: none set; a run needs one</span>
   ────────────────────────────────────────────────────────────────────────
   <b>profiling</b>                                                       <span class="m">○ off ▾</span> <span class="n">3</span>
     <span class="m">traced only</span>
  <span class="p">╰────────────────────────────────────────────────────────────────────────╯</span>

                                                                    <span class="btn"> Save </span> <span class="n">4</span>

  <b>enter</b> open   <b>tab</b> actions   <b>esc</b> back</pre>

</Term>

1. **`agent`**, the flow's one role, and the agent filling it as `cli/model:effort`.
2. **`budget`**: none yet. You set it in step 5.
3. **`profiling`** stays off here: it is for when you want the programs a run starts in its
   [trace](/user/tracing#profiling-a-run).
4. **Save**: nothing you change is kept until you press it. `● unsaved changes` says something
   is waiting.

Press <kbd>enter</kbd> on `agent`. An agent is four rows:

<Term title="hmz · /flow › ralph_loop › agent">

<pre>  <span class="m">hmz › /flow › Installed › ralph_loop ›</span> <span class="p b">Set up agent</span>
  <span class="m">Configure this agent: select its CLI, account, model, and reasoning
  effort.</span>

  <span class="p">╭────────────────────────────────────────────────────────────────────────╮</span>
   <b>cli</b>                                                            <span class="a">claude ▸</span> <span class="n">1</span>
     <span class="m">coding agent CLI to use</span>
   ────────────────────────────────────────────────────────────────────────
   <b>account</b>                                                      <span class="a">as local ▸</span> <span class="n">2</span>
     <span class="m">account to run as</span>
   ────────────────────────────────────────────────────────────────────────
   <b>model</b>                                       <span class="a">claude-haiku-4-5-20251001 ▸</span> <span class="n">3</span>
     <span class="m">model to use</span>
   ────────────────────────────────────────────────────────────────────────
  <span class="sel"> <b>effort</b>                                                            low ▾ </span> <span class="n">4</span>
  <span class="sel">   reasoning effort                              </span><span class="p">╭─ effort ─────────────╮</span>
                                                   <span class="p">│</span> ultracode            <span class="p">│</span>
                                                   <span class="p">│</span> max                  <span class="p">│</span>
                                                   <span class="p">│</span> xhigh                <span class="p">│</span>
                                                   <span class="p">│</span> high                 <span class="p">│</span>
                                                   <span class="p">│</span> medium               <span class="p">│</span>
                                                   <span class="p">│</span><span class="sel"> low ✔                </span><span class="p">│</span>
                                                   <span class="p">╰──────────────────────╯</span>
  <span class="p">╰────────────────────────────────────────────────────────────────────────╯</span>

                                                                     <span class="m"> Save </span> <span class="n">5</span>

  <b>enter</b> choose   <b>esc</b> close</pre>

</Term>

1. **`cli`**: the coding agent CLI that takes its turns. Only CLIs that can fill this role are
   listed. Choosing another clears the account and the model, since both belong to a CLI.
2. **`account`**: `as local` is the CLI as you signed it in. **Add an account** under its list
   makes another; see [Accounts](/user/settings#accounts).
3. **`model`**: one of the models that CLI said it runs. The list shows each model's efforts
   beside it, and **Check again** under it asks the CLI again.
4. **`effort`**: how hard it thinks, from the model's own list. `▾` means <kbd>enter</kbd> or a
   click drops every effort the model takes under the row, hardest first, with `✔` on the one
   in force; <kbd>↑</kbd> <kbd>↓</kbd> and <kbd>enter</kbd>, or a click, pick one, and
   <kbd>esc</kbd> picks none. See [Efforts](/user/efforts).
5. **Save** keeps the agent. It cannot be pressed until a row has changed.

A row marked `▸` opens a list: <kbd>enter</kbd> or <kbd>→</kbd>, then pick; each list opens on
the choice in force. For a first run, pick a small model and a low effort, as here. Then
<kbd>tab</kbd> to **Save** and press <kbd>enter</kbd> to save the agent. The line across the top
is the way you came, `hmz › /flow › Installed › ralph_loop › Set up agent`: <kbd>esc</kbd> or a click on
`ralph_loop` goes back there.

A flow that has settings of its own asks for them before its roles. `ralph_loop` has none.

## 5. Set a budget

Press <kbd>enter</kbd> on `budget`:

<Term title="hmz · /flow › ralph_loop › budget">

<pre>  <span class="m">hmz › /flow › Installed › ralph_loop ›</span> <span class="p b">Set budget for ralph_loop</span> <span class="y">● unsaved changes</span>
  <span class="m">A run stops at whichever limit it reaches first; at least one limit is
  required. Leave empty or 0 for no limit.</span>

  <span class="p">╭────────────────────────────────────────────────────────────────────────╮</span>
   <b>duration</b>                                                            <span class="a">20m</span> <span class="n">1</span>
     <span class="m">maximum run duration: 1h30m, 90s, PT2H; empty for no limit</span>
   ────────────────────────────────────────────────────────────────────────
  <span class="sel"> <b>cost</b>                                                                0.5 </span> <span class="n">2</span>
  <span class="sel">   maximum cost in US dollars, 0 for no limit                            </span>
   ────────────────────────────────────────────────────────────────────────
   <b>output_tokens</b>                                                         <span class="a">0</span>
     <span class="m">maximum output tokens, 0 for no limit</span>
   ────────────────────────────────────────────────────────────────────────
   <b>graceful</b>                                                         <span class="g">● on ▾</span> <span class="n">3</span>
     <span class="m">finish the current turn when a limit is reached</span>
  <span class="p">╰────────────────────────────────────────────────────────────────────────╯</span>

                                                                      <span class="btn"> Set </span> <span class="n">4</span>

  <b>enter</b> change   <b>tab</b> actions   <b>esc</b> back</pre>

</Term>

1. **`duration`**: how long the run may take. <kbd>enter</kbd>, type `20m`, <kbd>enter</kbd>.
   `1h30m`, `90s` and `PT2H` are all understood.
2. **`cost`**: how many US dollars it may spend. <kbd>enter</kbd>, type `0.5`, <kbd>enter</kbd>:
   the first key you type replaces the `0.0` that was there. `output_tokens` works the same
   way.
3. **`graceful`**: on lets the turn that is running finish when a limit is reached; off cuts
   it off. <kbd>enter</kbd> or a click drops the two under it, opening on the one it is not.
4. **Set** keeps all four: <kbd>tab</kbd> to it and press <kbd>enter</kbd>. The `budget` row
   then reads `set`, and under it `what a run may spend: stops at 20m, $0.50`.

The run stops at whichever limit it reaches first. If your account is billed by the token, set
a `cost` as well as a `duration`. See [Every run has a budget](/features/allowances).

## 6. Save

Press <kbd>tab</kbd> to reach **Save** under the roles, and <kbd>enter</kbd>. The status line
now reads `◉ ralph_loop`, and humanize says `enter a task to start the flow`.

Nothing is applied before you save. <kbd>esc</kbd> steps back, and leaving `/flow` with changes
in it asks `Save?` in a box, with **Save** and **Discard**. A flow with no budget refuses to save, saying
`this flow requires a budget: set the budget first`.

## 7. Say what to do

```text
❯ Fix the bug in calc.py.
```

Press <kbd>enter</kbd> and the flow starts. What the agent says streams into the transcript as
it says it:

<TermScreen title="hmz · ralph_loop" :frames="running" />

What to look at, by number:

1. **`── agent`** marks whose words follow. With several agents, a new one appears wherever the
   speaker changes.
2. **`✻ Worked for 7s · agent`** closes a turn: the first round is done, and `calc.py` is
   already fixed.
3. **`conversation 2 of 2`**: a Ralph loop starts a fresh conversation every round, so the
   agent comes to the task new each time. It keeps going until the budget is spent.
4. **The agent line**: its role, what it runs, and `●` while a turn is open (`○` between
   turns). The number is how many conversations it holds.
5. **What the run has spent**: tokens by kind, dollars, and how fast the model is writing. See
   [Cost and rate](/user/tally).
6. **The status line**: who is working, for how long, and how to stop. Its right-hand end is
   the keys that work right now; `ctrl+c stop` means <kbd>ctrl+c</kbd> would start a stop.
7. **Stopped**: back to `◉ ralph_loop`, and `ctrl+c exit`, because nothing is running.

While it runs:

| To | Do | More |
| --- | --- | --- |
| tell the agent something | type a line and press <kbd>enter</kbd>; it goes into the turn that is running | [Talking to a running turn](/user/steering) |
| see who is working, and who handed to whom | <kbd>←</kbd> with nothing typed | [Watching a run](/user/monitor) |
| stop the flow | <kbd>ctrl+c</kbd> twice, or `/stop` | [Stopping](/user/stopping) |
| walk away and keep it going | close the terminal, or `/exit` | [Leaving it running](/user/leaving) |

A Ralph loop keeps going round until its budget is spent. Once `calc.py` is fixed, press
<kbd>ctrl+c</kbd> twice to stop it.

### Check it worked

Look at what it did, from the tag you made in step 1:

```sh
git diff start
```

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

`/epics` in `hmz` lists the run you just made, marked `stopped`.

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
| built in, or installed from `official` | `$ralph_loop` |
| in this project's `.hmz/flows/` | `$@local/twice` |
| in your `~/.hmz/flows/` | `$@user/twice` |
| installed from a flowverse you added | `$@<flowverse>/<flow>` |

A flow that is set up here starts at once. One that is not opens the menu on its roles, and
saving starts it. `$ralph_loop` with nothing after it only chooses the flow.

The [Workspace page of `/settings`](/user/settings#workspace) shows what this directory
remembers, and forgets it.

## Troubleshooting

### `this flow requires a budget: set the budget first`

Saving refused, because the budget row still reads `none set; a run needs one`. Set at least
one limit in step 5.

### The cost row reads `0.00.5`

What you type is added to what the row holds. <kbd>enter</kbd> on the row, delete what is
there, and type the amount again.

### `hmz: cannot choose a flow while one is running`

A `$name` line, or `/flow <name>`, was typed while a flow runs. Stop it first
([Stopping](/user/stopping)). `/flow` on its own opens the running flow's agents instead, and
what you save there is what the next run starts with.

### The agent row names a CLI you did not want

humanize fills a role with the first CLI it found. <kbd>enter</kbd> on the role, then on
`cli`, and pick another; then pick its model again.

### A flow from the [Flows](/flows/) pages is not listed

Only the flows built into humanize are there from the start. Install the others from a
flowverse: see the note under [step 3](#_3-choose-a-flow).

## Next steps

- [Security](/user/security): what to check before you point a flow at real work.
- The tutorials take a real piece of work start to finish:
  [Beat a benchmark](/user/tutorials/take-home),
  [Port a project](/user/tutorials/port-a-project) and
  [Build a coding agent](/user/tutorials/build-an-agent).
- [Flows](/flows/) lists every flow humanize and its official flowverse offer.
- [Run it unattended](/user/unattended): the same run as one `hmz exec` line.

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
