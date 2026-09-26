---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
import RefFilter from '../.vitepress/theme/components/ref-cli/RefFilter.vue'
</script>

# TUI reference

`hmz` with no command opens the terminal interface: a transcript, a multi-line editor under it,
and a status line under that, driving a [flow](/user/concepts#flow) rather than one agent.

**Look up:** [keys](#keys) · [slash commands](#commands) · [`$`
lines](#starting-a-flow-outright) · [menus](#menus) · [what it remembers](#what-it-remembers)

## The screen

```text
╭─ humanize v0.1.0 ──────────────────────────────────╮
│                                                    │
│    HUMANIZE, drawn large                           │
│                                                    │
│    Orchestrate, execute, and observe agent flows   │
╰────────────────────────────────────────────────────╯
● builder is working
● Bash(pytest -q tests/)
                 builder · claude/claude-opus-5:high · ● 2 · reading
                    reviewer · codex/gpt-5.6-sol:high · ○ 1 · unread
     input 12.4k · output 2.1k · cache_read 1.02M+ · cache_write 48.2k+
                                                     $1.34 · 91 out/s
────────────────────────────────────────────────────────────────────────
❯ type here
────────────────────────────────────────────────────────────────────────
  ·|· builder… (73s · ctrl+c twice to stop)  esc monitor · ctrl+c stop
```

| Part | Shows |
| --- | --- |
| **Opening box** | `humanize v<version>` in its top border, the name drawn large (smaller on a narrow terminal), and the package's one-line summary. [`/clear`](#commands) draws it again. |
| **Transcript** | One agent's, or the one every agent's work appears on, which it opens on. See [Reading one agent](#reading-one-agent). |
| **Above the editor, right** | One line per agent role: `role · cli/model:effort`, the account where it is not this machine's own, then `●` (a turn open) or `○`, how many conversations it holds, and `reading` or `unread`. Under them, [the run's cost](#the-cost-readout). |
| **Above the editor, left** | Lines typed and not yet taken, pinned. See [Talking to a running flow](#talking-to-a-running-flow). |
| **Editor** | Multi-line, up to ten rows, behind `❯`. |
| **Status line, left** | The modes, then what is running. See below. |
| **Status line, right** | The keys that do something right now. See below. |

### The status line

The left side is the first of these that holds:

| State | Left side |
| --- | --- |
| A flow waiting for you to say something | `·\|· waiting for you · ctrl+c twice to stop` |
| A turn open | `·\|· builder… (73s · ctrl+c twice to stop)`: who is working, and for how long. |
| A flow between turns | The same, naming the flow and how long the run has gone. A flow that [called another](/reference/flows#a-flow-that-calls-another-flow) names both, innermost last: `chat ▸ rlar`. |
| Nothing running | `◉ <flow> · <directory>`, with your home as `~`. |

In front of it go the modes: `afk` in the warning colour while
[`/afk`](#questions-and-being-away) is on, and `details` while [`/details`](#commands) is.
After it, `· copied` for two seconds after a [copy](#selecting-and-copying).

The right side lists only keys that work now, in this order:

| Key hint | Shown when |
| --- | --- |
| `↑↓ move · tab take · esc dismiss` | The offers list is open. Nothing else is shown then. |
| `enter start`, `enter say`, `enter answer` | Something is typed: no flow running, a flow running, a question up. |
| `tab agent` | There is another transcript to step to. |
| `/ commands`, `shift+enter newline`, `esc monitor` | Always. |
| `ctrl+c clear` · `ctrl+c again to stop` · `ctrl+c again to exit` · `ctrl+c stop` · `ctrl+c close them` · `ctrl+c exit` | What the next <kbd>ctrl+c</kbd> does: [see below](#ctrl-c). |

On a terminal too narrow for all of them, hints drop from the front, so the <kbd>ctrl+c</kbd>
one stays.

### The cost readout

Under the agent lines, what the run has spent: one figure per kind of token (`input`, `output`,
`cache_read`, `cache_write`, `reasoning`), then the money and the rate.

- A `+` on a kind marks a floor: some agent of the run drives a CLI that does not report that
  kind.
- The money is per model, from [OpenLLMPrices](https://openllmprices.com/), kept in
  `~/.humanize/prices.json` and fetched again as the interface opens when it is older than a
  day (see [`HUMANIZE_PRICES`](/reference/cli#environment-variables)). A model nobody prices
  adds no money rather than `$0.00`, and a total that mixes priced and unpriced models reads
  `$1.34+`.
- The rate is **output** tokens a second over the last five minutes, so a flow that has stopped
  reads as stopped.
- It is worked out again every five seconds and whenever an agent does anything.

See [Cost and rate](/user/tally).

## Keys

<RefFilter
  label="Filter keys: try esc, save, or a menu"
  :chips="['prompt', 'anywhere', 'every menu', '/flow', '/flowverses', '/providers',
    '/fallback', '/settings', '/monitor', '/exit']"
>

| Where | Key | Does |
| --- | --- | --- |
| prompt | <span id="key-enter"></span><kbd>enter</kbd> | Sends the line: starts the flow, says it to the agent, or answers a question. Over the offers list, takes the one highlighted. |
| prompt | <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | Breaks the line. |
| prompt | <kbd>↑</kbd> <kbd>↓</kbd> | Walks [history](#history), from the first or last line of what is typed. Over the offers list, moves in it. |
| prompt | <kbd>tab</kbd> | Over the offers list, takes the one highlighted. |
| prompt | <kbd>esc</kbd> | Over the offers list, dismisses it. |
| anywhere | <span id="key-tab"></span><kbd>tab</kbd> <kbd>shift+tab</kbd> | Next or previous [transcript](#reading-one-agent): the one every agent is on, then each agent with a turn open. Not while a menu is up. |
| anywhere | <span id="key-esc"></span><kbd>esc</kbd> | Opens [`/monitor`](#watching-the-run). It stops nothing. |
| anywhere | <span id="key-ctrl-c"></span><kbd>ctrl+c</kbd> | Clears a half-typed line. With nothing typed, stops the flow on the second press, or leaves on the second press with nothing running. See [ctrl+c](#ctrl-c). |
| anywhere | <kbd>ctrl+q</kbd> | Does what [`/exit`](#leaving-and-letting-go) does, asking first if a flow is running. |
| anywhere | drag · double click · triple click | Copies what was dragged across, the word, or the whole line. See [Selecting and copying](#selecting-and-copying). |
| anywhere | <kbd>shift</kbd> + drag | Your terminal's own selection instead. |
| every menu | <span id="key-menus"></span><kbd>↑</kbd> <kbd>↓</kbd> | Moves the cursor. |
| every menu | <kbd>enter</kbd> | Opens or chooses the row under the cursor. On an `add` or `save` row, does that. |
| every menu | <kbd>esc</kbd> | One step back. Leaving a menu that holds changes asks: save or discard. Leaves a running search first. |
| every menu | <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | Saves the menu from any row: `/flow`, an agent's sheet, `/providers`, `/fallback`, `/settings`. |
| every menu | <kbd>s</kbd> | Starts a search on a list that has one. Letters narrow it; <kbd>esc</kbd> leaves it. |
| every menu | <kbd>←</kbd> <kbd>→</kbd> <kbd>space</kbd> | Steps a row marked `↔`. Space goes round to the first value after the last. |
| /flow | <kbd>←</kbd> <kbd>→</kbd> | On the flows: the place before or after, wrapping round. |
| /flow | <kbd>f</kbd> | On the flows: copies the one under the cursor into `.humanize/flows/` to change. |
| /flow | <kbd>v</kbd> | On the flows: opens [`/flowverses`](#where-flows-come-from). |
| /flow agent | <kbd>←</kbd> <kbd>→</kbd> | Steps `effort`, and `swarm` where the model has one. |
| /flow agent | <kbd>space</kbd> | The next value of that row, round to the first. |
| /flow accounts | <kbd>a</kbd> | Makes an account for this CLI and chooses it. |
| /flow models | <kbd>r</kbd> | Asks the CLI again what it runs as this account. |
| /flow params | typing · <kbd>backspace</kbd> | Writes a field that is written rather than stepped. |
| /flow params | <kbd>enter</kbd> | Takes every field and goes back. |
| /flowverses | <kbd>a</kbd> | Adds one: a URL or `owner/repo`, then a name. |
| /flowverses | <kbd>r</kbd> | Fetches the one under the cursor again. |
| /providers | <kbd>a</kbd> | Makes an account: which CLI, how to sign in, what that asks. |
| /providers | <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | Making an account, in the one field that takes a list of variables: breaks the line. |
| /providers | <kbd>space</kbd> <kbd>←</kbd> <kbd>→</kbd> | After making an account, on the list of other CLIs to copy it to: turns one on or off. <kbd>enter</kbd> copies to the ones on, <kbd>esc</kbd> to none. |
| /fallback | <kbd>a</kbd> | Adds a step: the place that cannot run, then the place that takes its turns. |
| /fallback retries | <kbd>←</kbd> <kbd>→</kbd> <kbd>space</kbd> | Steps the tries, the policy and the time given. |
| /settings | <kbd>tab</kbd> <kbd>shift+tab</kbd> | Turns between `Everywhere` and `This directory`. |
| /monitor | <kbd>enter</kbd> | On a box, reads that agent. On a board line, changes it. |
| /monitor | <kbd>a</kbd> | Puts a line on the board. |
| /monitor | <kbd>d</kbd> <kbd>d</kbd> | Takes the board line under the cursor off, on the second press. |
| /exit | <kbd>enter</kbd> | Takes the answer under the cursor. |
| /exit | <kbd>esc</kbd> | Stays. |

</RefFilter>

Every menu says its keys on its bottom row, and only there.

<kbd>shift+enter</kbd> reaches a program only from a terminal that speaks a keyboard protocol
able to say so: Ghostty, kitty, WezTerm, Alacritty. Anywhere else it arrives as
<kbd>enter</kbd>. <kbd>ctrl+j</kbd> arrives from every terminal. In **iTerm2** that protocol is
kept off, because iTerm2 loses input-method text with it on, so there <kbd>shift+enter</kbd>
sends the line and <kbd>ctrl+j</kbd> is the one that breaks it. Under tmux, iTerm2 behaves like
the rest.

Focus never leaves the editor. While a menu is up, its keys are the menu's; while the offers
list is open, <kbd>tab</kbd> is the list's.

### ctrl+c {#ctrl-c}

| State | Presses |
| --- | --- |
| Something typed | **1** clears the line. |
| A flow running | **1** says `— press ctrl+c again to stop the flow —`.<br>**2**, within 3 s, stops the flow, as [`/stop`](#stop) does.<br>**3** closes every conversation still open under its turn, without waiting for the flow to unwind. The flow reads that as a failed turn. |
| Nothing running | **1** says `— press ctrl+c again to leave —`.<br>**2**, within 3 s, leaves. |

The status line always names what the next press does. A press more than three seconds after
the last is a first press again; the third press has no time limit. <kbd>esc</kbd> never stops
anything.

## Slash commands {#commands}

A line starting with `/` is a command, a line starting with `$` [starts a
flow](#starting-a-flow-outright), and any other line is said to the flow. Type `/` to see the
list, with a line about each.

<RefFilter label="Filter commands">

| Command | While a flow runs | Does |
| --- | --- | --- |
| <span id="cmd-flow"></span>`/flow [flow]` | <Badge type="warning" text="roles only" /> | [Chooses the flow](#choosing-a-flow) and sets up its roles, params and budget. With a name, opens inside that flow. |
| <span id="cmd-btw"></span>`/btw <question>` | <Badge type="info" text="needs one" /> | [Asks a side question](#btw) about the running flow, answered by a read-only copy of one of its agents. |
| <span id="cmd-flowverses"></span>`/flowverses` | <Badge type="tip" text="yes" /> | [Where flows come from](#where-flows-come-from): add, fetch again, take away. |
| <span id="cmd-providers"></span>`/providers` | <Badge type="tip" text="yes" /> | [The accounts](#the-accounts-themselves) agents run as. |
| <span id="cmd-fallback"></span>`/fallback` | <Badge type="tip" text="yes" /> | [Where a turn goes](#where-a-turn-goes-when-it-cannot-be-taken) when its place cannot take it. |
| <span id="cmd-epics"></span>`/epics` | <Badge type="warning" text="read only" /> | [The runs of this directory](#the-runs-that-have-already-happened): go into one, export it, resume it. |
| <span id="cmd-resume"></span>`/resume` | <Badge type="danger" text="refused" /> | [Picks up the last run here](#carrying-the-last-one-on-outright) of a flow that can be picked up. |
| <span id="cmd-settings"></span>`/settings` | <Badge type="tip" text="yes" /> | [What humanize remembers](#what-humanize-remembers), everywhere and here. |
| <span id="cmd-monitor"></span>`/monitor` | <Badge type="tip" text="yes" /> | [The run, drawn](#watching-the-run), and the board. Also <kbd>esc</kbd>. |
| <span id="cmd-clear"></span>`/clear` | <Badge type="tip" text="yes" /> | Clears the transcript being read and draws the opening box again. Nothing else. |
| <span id="cmd-details"></span>`/details [on\|off]` | <Badge type="tip" text="yes" /> | Shows or hides the working: tool calls, thinking, and what a backend prints on its way past. Off at start. |
| <span id="cmd-afk"></span>`/afk [on\|off]` | <Badge type="tip" text="yes" /> | [Says you are away](#questions-and-being-away): nothing waits on you. Off at start. |
| <span id="cmd-stop"></span>`/stop` | <Badge type="info" text="needs one" /> | [Stops the flow](#stop), asked once. |
| <span id="cmd-exit"></span>`/exit` | <Badge type="warning" text="asks" /> | [Leaves](#leaving-and-letting-go). Asks first if a flow is running. Also <kbd>ctrl+q</kbd>. |

</RefFilter>

`/details` and `/afk` flip when given nothing, and take `on` or `off`. A line that is not a
command is shown in red and nothing happens:

| Typed | Answered |
| --- | --- |
| `/details maybe` | `hmz: say on or off, not 'maybe'` |
| `/nosuch` | `hmz: no such command: /nosuch` |
| `/resume last` | `hmz: /resume takes nothing: it carries the last run here on, and /epics is where another one is named` |
| `/btw what's left` | `hmz: No closing quotation`: arguments are split like a shell line |

## Starting a flow outright

`$<flow> <task>` runs that flow on that task: `$ralph_loop fix the failing test`.

| The flow is | What happens |
| --- | --- |
| **set up here already** | It runs, now. |
| **never set up here** | [`/flow`](#choosing-a-flow) opens inside it. The task is held and runs the moment the menu is saved. Walk out without saving and `nothing was set up, so nothing was started`. |
| **not a flow** | `hmz: no such flow: <name>`. |

`<flow>` is the name the flow is **offered** under, exactly as completion offers it:

| Flow | `$` name |
| --- | --- |
| humanize's own, and the official flowverse's | bare: `$chat`, `$ralph_loop` |
| this project's, under `.humanize/flows/` | `$local/<flow>` |
| yours, under `~/.humanize/flows/` | `$user/<flow>` |
| another flowverse's | `$<flowverse>/<flow>` |
| one of several in one file | `…:<sub>`, as `$humanize1:rlcr` |

**Set up here** means a remembered agent for every agent role the flow declares now, a
remembered environment for every required environment role, params that still read back through
the flow's `FlowParams`, and a budget (`chat` needs none). A flow that has grown, lost or
renamed a role since is asked about again, and so is one whose kept params no longer fit. A
flow you never set params for takes its defaults, as `hmz exec` does with no `-p`.

What counts as a `$` line:

- The name must be followed by whitespace or the end of the line. `$ ls -la`, `$5 says
  otherwise`, `$(pwd)` and a bare `$` are said to the flow like any other line.
- A path is not a name: `/flow ./flows/mine` is how a flow by path is chosen.
- `$ralph_loop` alone chooses that flow and starts nothing.
- A task may start on the next line (<kbd>shift+enter</kbd> after the name).
- Refused while a flow runs: `hmz: a flow is running; no choosing a flow`.
- Not read as a flow while a question is up: the next line is the answer, whatever it starts
  with.

## While a flow runs

### Reading one agent

There is one transcript per agent, and one where every agent's work appears together. The
interface opens on that one.

- <kbd>tab</kbd> and <kbd>shift+tab</kbd> step round it and the agents with a turn open,
  wrapping at either end. An agent between turns stays on screen once you are on it, but is not
  stepped onto. Every agent that has worked can be read from [`/monitor`](#watching-the-run).
- Stepping onto another transcript redraws it from the top, under `── reading builder ──`, or
  `── reading every agent ──`. `/clear` clears only the one you are reading.
- All of one agent's conversations run down its one transcript. Where it holds several, each
  turn says which: `● builder is working · conversation 3 of 3`.
- On the shared transcript, a line `── builder` marks each change of speaker.
- `unread` marks an agent that has said something since you last read it. Nothing is marked
  while you read the shared transcript.
- Kept: the last 16 transcripts, and the last 2,000 lines of each. The
  [trace](/reference/tracing) keeps everything.

### Talking to a running flow

A line typed while a flow runs goes to [the agent you are reading](#reading-one-agent), into
the conversation with a turn open. Reading every agent at once, it goes to whichever has a turn
open.

The line is **pinned** above the editor, dimmed, until something takes it:

```text
                                   assistant · claude/claude-opus-5:high
❯ and fix the tests too · with assistant       input 11.2k · output 1.1k
❯ then push                                             $0.31 · 84 out/s
────────────────────────────────────────────────────────────────────────
❯ █
```

1. Lines queue in the order typed and go **one at a time**: the next goes only once the turn
   says it has the one before.
2. A line put into a turn stays pinned, marked `· with <agent>`, until the agent's own turn
   says the words are in front of the model. Then it moves into the transcript.
3. With no turn open, or on a backend that cannot be steered, the line waits for the next turn
   to start, which takes it into its prompt. A backend that refuses it mid-turn says why in
   red, and the line goes back to the head of the queue.
4. A turn that ends without saying it had the line puts it in the transcript under
   `put to <agent>, which ended its turn without saying it had it`.
5. A flow that ends, however it ends, moves whatever is still pinned into the transcript,
   marked `never sent`.

The pin shows at most five lines, cut at the screen edge, and counts the rest:
`… 3 more waiting`, `… 6 more lines`. What is sent is the whole of what you typed.

| Backend | A line typed mid-turn |
| --- | --- |
| **Claude Code** | <Badge type="tip" text="steered" /> Into the running turn, which ends once the agent has answered everything it was told. |
| **Codex** | <Badge type="tip" text="steered" /> A steer on the running turn. |
| **Kimi Code** | <Badge type="tip" text="steered" /> Queued, then steered into the running turn. |
| **pi** | <Badge type="tip" text="steered" /> A steer on the run it is making. |
| **Antigravity** | <Badge type="info" text="next turn" /> |
| **Cursor Agent** | <Badge type="info" text="next turn" /> |
| **DeepSeek Harness** | <Badge type="info" text="next turn" /> |
| **Grok Build** | <Badge type="info" text="next turn" /> |
| **mimocode** | <Badge type="info" text="next turn" /> |
| **opencode** | <Badge type="info" text="next turn" /> |
| **Qwen Code** | <Badge type="info" text="next turn" /> |
| **ZCode** | <Badge type="info" text="next turn" /> |
| an **ACP CLI** of your own | <Badge type="info" text="next turn" /> |

**next turn**: a red line says why the line cannot be put in, and it waits for the next turn to
start.

Anchoring changes nothing here. An [anchored](/reference/remote-execution) Claude hears a line
during a turn like any other; its process ends between turns, when nothing is sent anyway.

### Side questions (`/btw`) {#btw}

`/btw <question>` asks about the running flow without steering it. The question goes to a copy
of one of the flow's agents, in a session of its own, with read-only permission, no skills and
no goals, given a snapshot of the run: the task, the agents, their turns and handovers, what
has been spent, and the last 32 things the run did. The agent you are reading is tried first,
then the others. The answer appears as `● btw · <question> <answer>`.

The question is split like a shell line and joined again, so an apostrophe needs quotes:
`/btw "what's left?"`.

| Refused | Says |
| --- | --- |
| no question | `hmz: usage: /btw <question>` |
| no flow running | `hmz: /btw needs a flow that is running` |
| no agent that can take a read-only turn | `hmz: /btw needs a coding agent that supports read-only turns` |
| four already running | `hmz: /btw already has 4 questions in progress` |

A side question still running is dropped when the next flow starts or the interface closes.

### Questions, and being away

Two things wait on you, and both are shown where you type. The next line you type is the answer
rather than a word put into the turn, and the status line says `enter answer`.

- **The flow asks.** A flow whose roles include an
  [`Outworlder`](/reference/flows#the-person-at-the-prompt) is asking you when it runs that
  role. Asked for a shape, it is one question per field.
- **An agent asks.** An agent that stops mid-turn to ask its user asks the flow, through the
  hook the flow hung for it; a flow that means you to answer, as `chat` does, puts it to you.
  An agent whose flow hung no hook is told nobody answered, and carries on.

`/afk` says you are away. While it is on, a flow's question is answered at once: `""` for text,
the answer a shape's defaults make, or `OutworlderAway` where a field has none. An agent's
question is told nobody answered. A question already up when `/afk` goes on is answered by
nobody, which the flow hears as `OutworlderAway`. It starts **off**. While on, `afk` leads the
status line.

A question still up when the flow ends or is stopped ends with it.

### Stopping {#stop}

`/stop` stops the whole flow, not just the turn: what the second <kbd>ctrl+c</kbd> does, asked
once. The turn under way is interrupted and the flow unwinds from where it stands.

- With a flow already stopping: `hmz: the flow is already stopping: it is closing out the turn
  it was in`. The next <kbd>ctrl+c</kbd> closes its conversations without waiting.
- With nothing running: `hmz: no flow is running, so there is nothing to stop`.
- It resets <kbd>ctrl+c</kbd>'s count, so the press after it is a first press.

See [Stopping](/user/stopping) and [ctrl+c](#ctrl-c).

### Leaving, and letting go

Closing the interface and stopping the run are two things: the run is
[held in a process of its own](/reference/daemon). With a flow running, `/exit` and
<kbd>ctrl+q</kbd> ask:

```text
A flow is running.

❯ 1. stop it, then leave
  2. leave it running             `hmz` opens it again

enter choose · esc stay
```

**leave it running** lets go of this terminal. The flow carries on, and `hmz` in this directory
opens it again from the top. Where the run is not held (output not a terminal, or
[`HUMANIZE_DAEMON`](/reference/cli#environment-variables) off), the second answer is
**stay here** instead. With nothing running, `/exit` leaves without asking.

## Menus

`/flow`, `/flowverses`, `/providers`, `/fallback`, `/epics`, `/settings` and `/monitor` each
put up a sheet over the screen. The [keys table](#keys) lists every key; each sheet's own are
on its bottom row.

### Every menu {#the-menus-and-when-what-they-hold-lands}

| Rule | |
| --- | --- |
| **Nothing lands until you save** | On `/flow`, an agent's sheet, `/providers`, `/fallback` and `/settings`. Save with the `save` row below the choices or <kbd>shift+enter</kbd>/<kbd>ctrl+j</kbd> from any row. <kbd>esc</kbd> out of a menu holding changes asks, in a box over it, whether to save or discard; <kbd>esc</kbd> on the box goes back to the menu. A menu you only looked at asks nothing. |
| **Some happen at once** | `/flowverses` and `/epics` hold no draft: what you ask for happens as you ask. So do making an account and signing one in on `/providers`. |
| **An `add` row** | A list you can add to has one below the choices, beside the letter key. |
| **Row marks** | `↔` is stepped where it stands (<kbd>←</kbd> <kbd>→</kbd> <kbd>space</kbd>); `▸` opens something. |
| **Search** | <kbd>s</kbd> starts it, letters narrow by name, <kbd>esc</kbd> clears and leaves it. Typing never searches by itself. |
| **Pages** | A menu of several pages shows their titles across the top, and <kbd>tab</kbd>/<kbd>shift+tab</kbd> turn between them. A page that cannot open now is struck through. |
| **Going deeper** | <kbd>enter</kbd> opens what you picked; <kbd>esc</kbd> comes back one step. |

### `/flow` {#choosing-a-flow}

Which flow runs, and inside it, what fills each role. It opens on the flows of one **place** at
a time, with <kbd>←</kbd> <kbd>→</kbd> stepping between places: each
[flowverse](/reference/flows#flowverses) (`official` first: `chat` from the package, plus what
has been fetched), then `local` (`.humanize/flows/` here) and `user` (`~/.humanize/flows/`),
each where there are any.

```text
  Flow

  Which flow drives the agents; what it is to do is the next thing you
  say. A flow anywhere else is a path you type.

  official · local · user   ←/→ switch

❯ 1. chat            Chat — one agent, one session, and every line ty…
  2. continue_loop   Continue loop (flowbench: continue_loop) — send …
  3. flame_chase     Flame chase (flowbench: flame_chase) — two agent…

  enter open · f copy here · v flowverses · shift+enter/ctrl+j save ·
  esc close · s search
```

- It opens on the place the flow in force came from. A place never fetched is fetched as the
  menu opens, in the background; how that went is said under the list. An empty place says so,
  and one never fetched says `not fetched yet; v opens the flowverses, where r fetches it`.
- <kbd>s</kbd> searches flow names across every place, and narrows the strip to the places with
  a match. What a flow says about itself is not searched.
- <kbd>f</kbd> copies the flow under the cursor, with what it imports and the skills it brings,
  into `.humanize/flows/`. Your own are looked in first, so the name then means your copy.
- **While a flow runs**, there are no flows to choose: `/flow` opens inside the running flow's
  roles, and <kbd>esc</kbd> there leaves. What you save is what the next run starts on.
- `/flow <name>` opens already inside that flow; `/flow ./path` opens a flow of your own by
  path. Both are refused while a flow runs: `hmz: a flow is running; no choosing a flow`.
- The same places are [`Hmz().verses`](/reference/sdk) from Python.

<kbd>enter</kbd> on a flow asks its [params](#setting-a-flow-up), where it declares any, then
lands on its roles:

| Row | |
| --- | --- |
| one per agent role | What fills it, or `not chosen yet`. <kbd>enter</kbd> opens [the agent's sheet](#what-each-agent-is). |
| one per environment role | [Where it is](#where-each-agent-works), or `not said yet`. |
| `budget` | [What a run may spend](#what-a-run-of-it-may-spend). |
| `save` | Checks every role against what the flow declares, and applies the flow, its roles, its params and its budget together. |

Roles the runtime fills are not rows: an `Outworlder` is you, and a `LocalEnv` is the directory
the interface was started in. <kbd>esc</kbd> goes back to the flows.

#### An agent's sheet {#what-each-agent-is}

An agent is a CLI, an account, a model and an effort: exactly what `-a` says.

```text
  Set up builder

  What this one agent is: the CLI that takes its turns, the account
  they run as, and the model at an effort.

  ❯ 1. cli        claude ▸          which coding agent takes its turns
    2. provider   as local ▸        the account those turns run as
    3. model      claude-opus-5 ▸   which of that CLI's models it runs
    4. effort     high ↔            how hard it thinks

       save                         this agent

  enter open · shift+enter/ctrl+j save · esc close
```

| Row | |
| --- | --- |
| `cli` | [Which CLI](#which-cli-and-which-account). Changing it lets go of the model. |
| `provider` | [Which account](#which-cli-and-which-account) of that CLI. |
| `model` | [Which model](#what-each-agent-runs) that account may name. |
| `effort` | A rung on that model's ladder, stepped where it stands. |
| `swarm` | `on` or `off`: the turn run as a fleet. Only for a model that runs one (Kimi Code). |
| `save` | Accepts this agent into the flow's draft and returns to the roles. The flow's own `save` writes it down. |

What an agent may touch, its skills and what it must be able to do are the flow's,
[declared on the role's type](/reference/flows#asking-for-an-agent-that-can-do-something), and
are not rows here. Nor are skills a CLI carries of its own: see
[What each agent carries](#what-each-agent-carries).

#### Which CLI, and which account

The CLIs offered are the ones **installed here**, less any that cannot serve what the role
declares, plus the supported ones a `pip install` away, marked as such.

```text
  Select the account its turns run as

  ❯ 1. as local   signed in as you signed it in
    2. deepseek   gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
    3. work       login

       add        an account

  a add · enter choose · esc back · s search
```

- `as local`, always first, is the CLI as you already run it, with nothing redirected.
- <kbd>a</kbd> or the `add` row makes an account without leaving: how to sign in, what that
  asks, and the CLI's own login where the way has one. It comes back with the new account
  chosen. A CLI with none says `claude has no accounts here yet`.
- An agent given an account that has since been taken away fails its first turn, naming the
  account. It never runs as yours instead.

#### Which model {#what-each-agent-runs}

```text
  Select what claude runs

  Which model of claude takes this one's turns, and how hard it may be
  asked to think. These are what it last said it runs as this account.

    1. claude-opus-5     max, high
  ❯ 2. claude-sonnet-5   max, high

  r ask it again · enter choose · esc back · s search
```

- The list is what the chosen account may name. Where the account points its CLI at an
  endpoint, the endpoint is asked. It is asked the first time the interface opens, whenever an
  account is made, and on <kbd>r</kbd>.
- An account never asked says so where the list would be; one nothing answers for says why
  under it.
- Choosing a new model starts its effort at the hardest it takes. Choosing the same one keeps
  the effort.

#### Where each agent works

Each environment role the flow declares is a row under the agents, answered as `-e` spells it
after `<role>=`:

| Answer | Where the work goes |
| --- | --- |
| `local@/home/me/repo` | A directory on this machine. |
| `ssh@gpu-box/home/me/repo` | A directory on a host you reach with ssh (`host`, `user@host`, `host:port` or an ssh config alias). |
| `ssh@gpu-box/~/repo` | The same, under the ssh login's home. |

An answer that does not read is shown in red under the roles; an empty one leaves the role
unanswered. A host that cannot be reached, a missing directory and a machine smaller than the
role declares are red lines when the flow starts, before any turn. An agent spawned in an ssh
environment takes its turns there; its credentials stay here. See
[Remote execution](/reference/remote-execution).

#### What each agent carries

Nothing is set here. The skills an agent carries are its CLI's own, found and switched off
where that CLI does it. A run adds [the skills the flow
brings](/reference/flows#the-skills-a-flow-brings) to every session of the role that names
them, and takes them away after.

#### Params {#setting-a-flow-up}

A flow that [declares a `FlowParams`](/reference/flows#settings-of-the-flow-s-own) is asked it
as you choose the flow: one row per field, with its value and the line the flow declared it
with. Fields in groups get a heading per group.

```text
  Set up humanize1:rlcr

  How this flow runs, which it says for itself. What is refused here
  is the flow's own refusal rather than this list's.

    1. plan_file       docs/plan.md   --plan-file: the plan to build, …
  ❯ 2. max             20▏            --max: rounds before the loop st…
    3. codex_timeout   5400           --codex-timeout: seconds one rev…

  ←/→ or space change · type set · backspace rub out · enter accept ·
  esc back
```

| Key | |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Between fields, stepping over headings. |
| <kbd>←</kbd> <kbd>→</kbd> <kbd>space</kbd> | Steps the field: a switch flips, a choice steps, a number moves by one. |
| typing · <kbd>backspace</kbd> | Writes a field that is written. A caret marks where. |
| <kbd>enter</kbd> | Takes every field. |
| <kbd>esc</kbd> | Back, changing nothing. |

What is refused is the flow's own refusal, in its own words. What you answer is held with the
rest of the menu until it is saved. There is no command for it: choose the flow again to answer
again. On a command line the same fields are [`hmz exec -p`](/reference/cli#writing-params).

#### Budget {#what-a-run-of-it-may-spend}

The `budget` row sits under the roles and says what the run is held to without opening:
`stops at 6h, $50`. <kbd>enter</kbd> opens the same sheet as params, over the four things a
[`Budget`](/reference/flows#what-a-run-may-spend) holds: `duration`, `cost` in USD,
`output_tokens`, and `graceful`. Whichever limit is reached first stops the run.

**Every flow but `chat` needs one.** The menu will not save a flow whose budget sets none of
the three, as `hmz exec` will not run one without a `-b`.

### `/flowverses` {#where-flows-come-from}

Where flows come from: each a git repository with a `flows/` directory, cloned under
`~/.humanize/flowverses/`, plus your own `local` and `user`. <kbd>v</kbd> on `/flow` opens the
same sheet; the command is how you reach it while a flow runs.

![The /flowverses list: official, which holds `chat` from the package and, at its GitHub URL,
the rest, marked as not fetched yet](/demo/flowverses.png)

| Key | |
| --- | --- |
| <kbd>enter</kbd> | What that flowverse holds: a row per flow, then the row that takes the flowverse away. `official`, `local` and `user` cannot be taken away, and say why. |
| <kbd>a</kbd> | Adds one: a URL or `owner/repo`, then a name to keep it under. The `add` row does the same. |
| <kbd>r</kbd> | Fetches the one under the cursor, again or for the first time. `local` and `user` have nothing to fetch. |

- A place never fetched is listed anyway, with its URL and `not fetched yet`.
- Each happens as you ask: a clone runs in the background, and what came of it is said under
  the list and again in the transcript.
- Every start of the interface fetches every flowverse that has a URL, quietly and one at a
  time, except a clone you have written into. It stops if a flow starts. A fetch that brings
  something down makes any open list of flows read them again.
- <kbd>v</kbd> is refused while `/flow` is still fetching the place it opened on.
- Nothing here is refused while a flow runs.
- The same is [`Hmz().verses`](/reference/sdk): `add`, `fetch`, `remove`, `holds`.

### `/providers` {#the-accounts-themselves}

Every account an agent may run as, under a heading per CLI, with the way it was made and the
variables it sets (names only, never values).

```text
  claude
  ❯ 1. deepseek   gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
    2. work       login
    3. as local   the CLI as this machine is already signed in · falls
                  back to work

  codex
    4. personal   key
    5. as local   the CLI as this machine is already signed in
```

![/providers: the accounts under a heading per CLI, enter opening what there is to do with one,
and a asking which backend a new one is for](/demo/accounts.gif)

| Key | |
| --- | --- |
| <kbd>enter</kbd> | What there is to do with the account under the cursor (below). |
| <kbd>a</kbd> | Makes one: which CLI, then how to sign in, then what that way asks. The list of CLIs is also where a [CLI of your own](/reference/agents#a-cli-of-your-own) that speaks ACP is added. |
| <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | Saves. |
| <kbd>esc</kbd> | Closes, asking about anything held. |

![What enter opens on one account: correct what it holds, sign it in again, what it falls back
to, and take it away](/demo/account-does.png)

| On one account | | Lands |
| --- | --- | --- |
| **correct what it holds** | The answers its way in was made with, asked again. Secrets start blank: type one again or leave it. | on save |
| **sign in again** | Runs its way in again; a login command owns the terminal until it is done. | at once |
| **falls back to** | Which account of the same CLI a turn carries on under when this one fails. | on save |
| **take it away** | The account and its credentials. Marked, it reads **keep it after all**. | on save |

- The last row under each CLI is `as local`: the CLI as this machine is signed in. It offers
  only **falls back to**, and says why: humanize keeps no credentials for it.
- Making an account is three questions: the CLI, [its way
  in](/reference/providers#the-ways-in), what that way asks. Secrets are drawn as bullets and
  never shown back.
- A credential other CLIs also read (an Anthropic key held by Claude Code, pi, opencode or
  mimocode) is then offered to them: a list of switches, the installed ones on.
  <kbd>enter</kbd> writes the account down for the ones on as well, <kbd>esc</kbd> for none.
- Nothing here is refused while a flow runs. An agent reads its account once, so a change
  reaches the next run.
- How often a failed turn is tried again is
  [`/fallback`](#where-a-turn-goes-when-it-cannot-be-taken), not here.
- The same accounts are [`Hmz().accounts`](/reference/sdk).

### `/fallback` {#where-a-turn-goes-when-it-cannot-be-taken}

One page of steps between **places**. A place is a CLI, an account and a model: what a turn can
fail for having named (a retired model, a CLI that will not start, a rate limit on the whole
account). The effort and what the agent may reach for carry across a step unchanged.

```text
  Fallback

  Where a turn goes when the place taking it cannot take it at all. A
  place is a CLI, an account and a model.

  ❯ 1. claude@work/claude-opus-5   3 more tries, exponential · falls
                                   back to codex@key/gpt-5.6-sol
    2. codex@key/gpt-5.6-sol       falls back to dsh/deepseek-v4-flash

       add                         a step
       save                        these steps

  enter what happens · a add · shift+enter/ctrl+j save · esc close ·
  s search
```

- <kbd>a</kbd> or `add`: the place that cannot run, then the place that takes its turns, each
  as its CLI, one of its accounts and one of its models.
- <kbd>enter</kbd> on a step: where its turns go, how it is tried again first, or take it away.
- A place cannot fall back to itself; a chain that comes round ends at the second sight of a
  place.
- An account falling back to another account of the same CLI is on
  [`/providers`](#the-accounts-themselves), not here.
- Held until saved. The same steps are [`Hmz().fallbacks`](/reference/sdk). What they mean is
  [Falling back](/user/fallback).

The retry sheet steps three rows where they stand:

| Row | Steps through |
| --- | --- |
| `tries` | `none`, 1, 2, 3, 5, 8, 13, 21 more tries |
| `policy` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter` (the default), `fibonacci` |
| `for` | `as long as it takes`, `30s`, `1m`, `5m`, `15m`, `60m` |

### `/epics` {#the-runs-that-have-already-happened}

Every run of a flow in this directory, newest first.

![The /epics list: two runs, each with when it began, the flow that ran, what it was asked to
do and how many sessions it opened, the newer one marked "can be picked up"](/demo/epics.png)

- A row is when the run began and the flow; beside it, the task, how many sessions it opened,
  and `can be picked up` where its flow says it can be and it left a journal. How it ended is
  shown only when it did not finish: stopped, failed, or unfinished.
- <kbd>s</kbd> searches the flow, the task and the run's name.
- <kbd>enter</kbd> goes into a run: where it is written down, then what to do with it.

![Inside one run: its directory, how it went and how much it opened, over resume this run and
export it](/demo/epic-does.png)

| Row | |
| --- | --- |
| **resume this run** | Picks the run up: its own flow, agents, environments, params, budget and task, from where its journal got to. [`/resume`](#carrying-the-last-one-on-outright) with the run named, refused for the same reasons in the same words. Offered only where the flow says **now** that it can be picked up. |
| **export it** | Packs **that run** into `.humanize/<run>.epic.tar.gz`: its records, every session log in full, a manifest, and a [trace](/user/tracing) of its sessions (and programs, for a [profiled](/reference/tracing#profiling-a-run) run), which also lands in the run's own `traces/`. Where it landed and how big are said under the list. See [Exporting a run](/user/export). |

Reading is not refused while a flow runs; resuming is. The same calls are
[`Hmz().epics.traced(epic)`](/reference/sdk) and `Hmz().epics.bundled(epic)`. A trace of a
directory's sessions regardless of run is `Hmz().epics.trace()`, and is not offered here.

#### `/resume` {#carrying-the-last-one-on-outright}

`/resume` picks up **the last run here of a flow that can be picked up**, without the list: its
flow, agents, environments, params, budget and task come off that run, and the line it starts
on says which run. Runs of flows that cannot be picked up are passed over; nothing further back
is. What the budget spent is counted again from nothing. It takes no arguments; naming an older
run is what `/epics` is for.

| Says | When |
| --- | --- |
| `no flow has been run here` | Nothing has run in this directory. |
| `no run here was of a flow that can be picked up` | Every run was of a flow that neither said nor says so. |
| `<run> cannot be read back` | Its record is not one. |
| `<flow> does not say it can be picked up` | Asked of the flow as it is today. A flow that will not load says no. |
| `<run> left nothing behind` | Killed before its journal held anything. Say what to do and the flow starts from the top. |
| `no picking a run up while a flow is running` | [Stop it](#stop) first. |
| `no picking a run up while the flow is still stopping` | Wait for it to unwind, or [press ctrl+c](#ctrl-c) once more. |

`hmz exec --resume` is the command-line equivalent: see
[Picking a run up](/reference/cli#picking-a-run-up).

### `/settings` {#what-humanize-remembers}

Two pages over `~/.humanize/settings.yaml`.

```text
  Settings

  Everywhere · This directory   tab/shift+tab switch

  ❯ 1. reports   on ↔   report what goes wrong to humanize
    2. sent      ▸      what a report carries, and what it never does

       save             what is set here

  ←/→ or space change · shift+enter/ctrl+j save · esc close
```

| Page | Row | |
| --- | --- | --- |
| Everywhere | `reports` ↔ | Whether humanize [reports what goes wrong](/user/reporting): `on`, `off`, or `not answered yet`. Where `HUMANIZE_SENTRY` overrides it for this run, the page says so. |
| Everywhere | `sent` ▸ | What a report carries and what it never does. |
| This directory | `workspace` | The directory these are for. |
| This directory | `flow` | The flow it opens on, and how many agents that flow was set up with. |
| This directory | `profile` ↔ | Whether a run here [profiles](/user/tracing#profiling-a-run) the programs it starts. |
| This directory | `forget` ↔ | Forget everything remembered here, across every flow. Other directories are untouched. |

Held until saved. On a first start, a box asks `Report what goes wrong to humanize?`;
<kbd>esc</kbd> there leaves it unanswered, to be asked again next time.

### `/monitor` {#watching-the-run}

The run, drawn. <kbd>esc</kbd> opens it; it is never refused, and redraws itself while open.

```text
  ▣ every agent · 1 of 2 working · 17 turns · 7m11s

  ┌──────────────────────────────────────────────────────┐
  │ ● builder                                        43s │
  │ claude/claude-opus-5:high · 12 turns                 │
  └──────────────────────────────────────────────────────┘
    ├╴◆ Task read the tests
    └╴◇ Task find the flaky one
  │   ↓ 6 · ↑ 5
  ┌──────────────────────────────────────────────────────┐
❯ │ ○ reviewer                                idle 1m04s │
  │ codex/gpt-5.6-sol:high · 5 turns              unread │
  └──────────────────────────────────────────────────────┘

  Flow:             humanize1:rlcr   431s
  Set:              max                          20

  Tokens:           claude-opus-5        48.2k    $1.34   91 out/s
                    gpt-5.6-sol           9.1k             12 out/s
  Kinds:            input                 1.2k
                    output                 980
                    cache_read           46.0k
                    cache_write           9.1k

  ↑↓ move · enter read · esc close
```

| Part | |
| --- | --- |
| `▣ every agent` | The first row: how many boxes are working, the run's turns and time. <kbd>enter</kbd> reads the shared transcript. |
| a box | One per agent that has taken a turn, in the order the flow declares them. Left: `●` working or `○` idle, the role, what it runs and its turns. Right: how long the open turn has run, or `idle` and how long since its last; `reading` or `unread`. <kbd>enter</kbd> or a click reads that agent, working or not. |
| `├╴◆` `└╴◇` | Sub-agents it started of its own: `◆` still going, `◇` back. Only from [backends that report them](/reference/agents#not-every-backend-runs-every-moment). A long fleet is cut, with a count. |
| `↓ 6 · ↑ 5` | Handovers between neighbouring boxes, each way; the latest one lit. |
| `Flow` | What is running, nested flows indented under the flow that called them, each with its time. |
| `Set` | The flow's params that are not at their defaults. |
| `Agents` | Before any agent has worked: the agents set up, in place of the boxes. |
| `Also` | Handovers between boxes that are not neighbours. |
| `Tokens` | One row per model, biggest first: tokens, money (blank where unpriced), output tokens a second. |
| `Kinds` | The run's tokens by kind, over every model. `+` marks a floor. |

**The board** sits under the diagram where the run keeps one: named lines you and the flow both
write. <kbd>a</kbd> or the `add` row puts one up (a name, then what it says), <kbd>enter</kbd>
changes the line under the cursor, and <kbd>d</kbd> twice takes it off at once. A line the flow
wrote is the flow's to change. Where the run keeps no board, none is drawn and <kbd>a</kbd>
says `this run keeps no board`. See [The mission board](/user/board).

After a run ends, its boxes stay, with every clock stopped where the run stopped.

## At the prompt

### Completion

A half-typed line is offered what it could become, in a list above the editor:

| Typed | Offered |
| --- | --- |
| `/` | The commands, each with what it takes and a line about it. |
| `/flow ` | Every flow: humanize's own, every fetched flowverse's, and your `local/` and `user/` ones. |
| `$` | The same flows, while the word after `$` is being typed. What follows is the task, and is not completed. |

- A word already written out in full is offered nothing, so <kbd>enter</kbd> sends `/flow`
  rather than taking `/flowverses`.
- Taking an offer replaces the word being typed.
- Offers follow the cursor as well as the text: with the cursor mid-line, nothing is offered.
- Nothing is offered while a question is up against a `$` line, nor on a line reached by
  walking history.
- A flow anywhere else is a path, and is typed.

### History

Every line you send is kept in `~/.humanize/history.jsonl`: tasks, words put into a running
flow, commands. <kbd>↑</kbd> and <kbd>↓</kbd> walk what was typed **in this directory**, or
everything typed anywhere where nothing has been typed here yet. Which of the two is settled as
the interface opens.

### Selecting and copying

Drag across the screen with the mouse, and what you dragged across is on your clipboard when
you let go. The status line says `copied` for two seconds.

| Gesture | Copies |
| --- | --- |
| drag | Everything from press to release, across lines. |
| double click | The word under it, up to the spaces either side, so a path or an id comes whole. |
| triple click | The whole line, however many rows it was drawn over. |
| <kbd>shift</kbd> + drag | Your terminal's own selection, copying the screen as drawn. |

- What comes back is what was written, not what was drawn: a long line wrapped over four rows
  copies as one line, without the padding.
- The opening box copies as drawn, borders and all.
- The editor and a menu's lists select for themselves; a click on a list is still a choice.
- Resizing the terminal drops the selection.
- It reaches the clipboard through OSC 52, so over ssh it lands on the machine you sit at. Some
  terminals need it turned on: `set-clipboard on` in tmux, clipboard write in VTE-based ones.

## What it remembers

Opening the interface again in the same directory finds it as you left it: the flow last set
up, and for each flow this directory has run, what fills each agent role and as which account,
where each environment role is, its params and its budget. It is kept in
`~/.humanize/settings.yaml` (see [Files](/reference/cli#files)).

- **Per flow**, keyed by the name the flow is offered under: `chat`, `local/<flow>`,
  `user/<flow>`, `<flowverse>/<flow>`. A flow of yours never inherits the setup of another
  flow with the same bare name.
- **Per role**, by the name the flow declares it under, so a flow that grows a role is asked
  about again.
- **Params** read back through the flow's own `FlowParams`: a field since dropped or renamed is
  asked again.

## Colours

Drawn in your terminal's own sixteen colours and their reversals, on your terminal's
background. It never asks the terminal what its colours are. `NO_COLOR` is honoured.
`TEXTUAL_THEME` names a Textual theme to use instead; an unknown name is ignored.

## What it will not do

- **Open another way.** `hmz` with no command is the only way in.
- **Run two flows at once.** While one runs, `/flow` opens on its roles and `$` is refused.
- **Close on a bad line.** A line it cannot carry out is shown and the interface stays up. It
  closes on `/exit`, <kbd>ctrl+q</kbd>, or <kbd>ctrl+c</kbd> twice with nothing running; with a
  flow running, the first two ask first and one answer leaves the run going.
- **Ask the flow about itself.** Everything drawn is read off the turns going past; a flow is
  Python that may branch any way it likes.
