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
  ·|· builder… (73s · ctrl+c twice to stop)      ← monitor · ctrl+c stop
```

| Part | Shows |
| --- | --- |
| **Opening box** | `humanize v<version>` in its top border, the name drawn large (smaller on a narrow terminal), and the package's one-line summary. [`/clear`](#commands) draws it again. |
| **Transcript** | One agent's, one conversation's, one outworlder's, or the one every agent's work appears on, which it opens on. See [Reading one agent](#reading-one-agent). |
| **Above the editor, right** | One line per agent role: `role · cli/model:effort`, the account where it is not this machine's own, then `●` (a turn open) or `○`, how many conversations it holds, and `reading` or `unread`. While a flow runs, one line per outworlder: `human · outworlder`, then who [holds it](#several-people-on-one-run) -- `yours` or `<name>'s` -- where somebody does, `away`, `asking`, and `reading` or `unread`. Under them, [the run's cost](#the-cost-readout). |
| **Above the editor, left** | Lines typed and not yet taken, pinned. See [Talking to a running flow](#talking-to-a-running-flow). |
| **Editor** | Multi-line, up to ten rows, behind `❯`. |
| **Status line, left** | The modes, then what is running. See below. |
| **Status line, right** | The keys that do something right now. See below. |

### The status line

The left side is the first of these that holds:

| State | Left side |
| --- | --- |
| A flow waiting for you to say something | `·\|· waiting for you · ctrl+c twice to stop`, or `waiting for <name>` where the role asking is another frontend's. |
| A turn open | `·\|· builder… (73s · ctrl+c twice to stop)`: who is working, and for how long. |
| A flow between turns | The same, naming the flow and how long the run has gone. A flow that [called another](/reference/flows#a-flow-that-calls-another-flow) names both, innermost last: `chat ▸ rlar`. |
| Nothing running | `◉ <flow> · <directory>`, with your home as `~`. |

In front of it go the modes: `afk` in the warning colour while
[`/afk`](#questions-and-being-away) is on for every outworlder, or `afk <role>, …` naming the
ones it is on for, and `details` while [details](#what-humanize-remembers) is on. After it,
`· copied` for two seconds after a [copy](#selecting-and-copying).

The right side lists only keys that work now, in this order:

| Key hint | Shown when |
| --- | --- |
| `↑↓ move · tab select · esc cancel` | The offers list is open. Nothing else is shown then. |
| `enter run`, `enter ask`, `enter answer`, `enter send`, `enter start` | Something is typed: a `/` command that would run here (nothing, for one that would only be refused), a side question in [btw mode](#btw), an answer to a question up, a line to a running flow, a task with nothing running. |
| `shift+tab switch view` | There is another transcript to step to. |
| `/ commands`, `shift+enter newline` | Always. |
| `← monitor` | Nothing is typed. |
| `ctrl+c clear` · `ctrl+c again to stop` · `ctrl+c again to exit` · `ctrl+c stop` · `ctrl+c force stop` · `ctrl+c exit` | What the next <kbd>ctrl+c</kbd> does: [see below](#ctrl-c). |

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
  :chips="['prompt', 'anywhere', 'every menu', '/flow', '/settings', 'monitor', '/exit']"
>

| Where | Key | Does |
| --- | --- | --- |
| prompt | <span id="key-enter"></span><kbd>enter</kbd> | Sends the line: starts the flow, says it to the agent, or answers a question. Over the offers list, takes the one highlighted. |
| prompt | <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | Breaks the line. |
| prompt | <kbd>↑</kbd> <kbd>↓</kbd> | Walks [history](#history), from the first or last line of what is typed. Over the offers list, moves in it. |
| prompt | <kbd>tab</kbd> | Over the offers list, takes the one highlighted. |
| prompt | <kbd>esc</kbd> | Over the offers list, dismisses it. |
| anywhere | <span id="key-tab"></span><kbd>shift+tab</kbd> <kbd>tab</kbd> | Next or previous [transcript](#reading-one-agent): the one every agent is on, then each conversation with a turn open, then each outworlder of the running flow. Not while a menu is up. |
| prompt | <span id="key-left"></span><kbd>←</kbd> | With nothing typed, on the log: up to [the monitor](#watching-the-run). It stops nothing. |
| anywhere | <span id="key-ctrl-c"></span><kbd>ctrl+c</kbd> | Clears a half-typed line. With nothing typed, stops the flow on the second press, or leaves on the second press with nothing running. See [ctrl+c](#ctrl-c). |
| anywhere | <kbd>ctrl+q</kbd> | Does what [`/exit`](#leaving-and-letting-go) does, asking first if a flow is running. |
| anywhere | drag · double click · triple click | Copies what was dragged across, the word, or the whole line. See [Selecting and copying](#selecting-and-copying). |
| anywhere | <kbd>shift</kbd> + drag | Your terminal's own selection instead. |
| every menu | <span id="key-menus"></span><kbd>↑</kbd> <kbd>↓</kbd> | Moves the cursor, round from the last row to the first. On a form of `/settings`, keeps the row being written first. |
| every menu | <kbd>←</kbd> <kbd>→</kbd> | Turns the pages of a menu that has them, round from the last to the first. While a row is being changed, changes it instead. |
| every menu | <kbd>enter</kbd> | Opens or chooses the row under the cursor, or does what a row below the choices says: `search…`, `add`, `save`, and the rest. On a row marked `↔`, or a field to write, begins changing it; pressed again, keeps the change. |
| every menu | <kbd>esc</kbd> | One step back: puts back a row being changed, then leaves a running search, then leaves. Leaving a menu that holds changes asks: save or discard. |
| every menu | typing · <kbd>backspace</kbd> | Only while a search runs, or a field is being written. On a form of `/settings`, typing on a written row begins writing it. |
| /flow | <kbd>←</kbd> <kbd>→</kbd> | On the flows: the place before or after, wrapping round. |
| /settings accounts | <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | Making an account, while writing `variables`, the one field that takes a list: breaks the line. |
| monitor | <kbd>↑</kbd> <kbd>↓</kbd> | With nothing typed: the node before or after. |
| monitor | <kbd>enter</kbd> · click | With nothing typed: reads that node's log. On an environment, opens its page. On a board line, changes it; saved empty, takes it off. On `+ add entry`, puts one up. A click on an agent picks it out, or on its `▸` or once picked opens it out; a double click reads it. |
| monitor | <kbd>→</kbd> | With nothing typed: back to the log last read. |
| monitor | <kbd>space</kbd> | With nothing typed: opens the agent under the cursor out to its sessions, or shuts it. |
| monitor | <kbd>ctrl+t</kbd> | The graph, or the list. |
| /exit | <kbd>enter</kbd> | Takes the answer under the cursor. |
| /exit | <kbd>esc</kbd> | Stays. |

</RefFilter>

Every menu says its keys on its bottom row, and only there. There are no others: what a
letter used to do is a row below the choices.

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
| Nothing running | **1** says `— press ctrl+c again to exit —`.<br>**2**, within 3 s, leaves. |

The status line always names what the next press does. A press more than three seconds after
the last is a first press again; the third press has no time limit. <kbd>esc</kbd> and
<kbd>←</kbd> never stop anything.

## Slash commands {#commands}

A line starting with `/` is a command, a line starting with `$` [starts a
flow](#starting-a-flow-outright), and any other line is said to the flow. Type `/` to see the
list, with a line about each. It holds only the commands that would do something here and now:
`/stop` appears while a flow runs and goes once it is stopping, `/resume` appears with nothing
running and a run here to carry on. The list and the line beside each command change the moment
the run or the view does, without a key being pressed. A command typed out while it is not
listed does nothing and says why, in red.

<RefFilter label="Filter commands">

| Command | While a flow runs | Does |
| --- | --- | --- |
| <span id="cmd-flow"></span>`/flow [flow]` | <Badge type="warning" text="roles only" /> | [Chooses the flow](#choosing-a-flow) and sets up its roles, params and budget. With a name, opens inside that flow. While a flow runs it reads `Set up the running flow's agents`, and no flow is offered after it. |
| <span id="cmd-btw"></span>`/btw [question]` | <Badge type="tip" text="yes" /> | [Enters or leaves btw mode](#btw): side questions about the flow, answered read-only beside it. Listed only with somebody to ask: the conversation being read, or an agent. |
| <span id="cmd-epics"></span>`/epics` | <Badge type="warning" text="read only" /> | [The runs of this directory](#the-runs-that-have-already-happened): go into one, export it, resume it. |
| <span id="cmd-resume"></span>`/resume` | <Badge type="danger" text="refused" /> | [Picks up the last run here](#carrying-the-last-one-on-outright) of a flow that can be picked up. Listed only with nothing running or stopping and such a run here, which is looked for as the interface opens, as a run ends and as a menu closes; typed anyway, it looks again. |
| <span id="cmd-settings"></span>`/settings [page]` | <Badge type="tip" text="yes" /> | [Everything humanize remembers](#what-humanize-remembers), in six pages: `everywhere`, `directory`, [`accounts`](#the-accounts-themselves), [`environments`](#environments), [`fallback`](#where-a-turn-goes-when-it-cannot-be-taken) and [`flowverses`](#where-flows-come-from). With a page, opens on it. |
| <span id="cmd-clear"></span>`/clear` | <Badge type="tip" text="yes" /> | Clears the transcript being read and draws the opening box again. Nothing else. |
| <span id="cmd-afk"></span>`/afk [on\|off]` | <Badge type="tip" text="yes" /> | [Says you are away](#questions-and-being-away): nothing waits on you. On an outworlder's transcript, as that outworlder alone; not on one agent's. Off at start. |
| <span id="cmd-claim"></span>`/claim [on\|off]` | <Badge type="tip" text="yes" /> | [Holds the outworlder being read](#several-people-on-one-run) for this interface alone; `off` gives it back. Only on an outworlder's transcript, and not on one another frontend holds -- nor is `/afk` there. |
| <span id="cmd-stop"></span>`/stop` | <Badge type="info" text="needs one" /> | [Stops the flow](#stop) for everybody reading it, asked once. Only on the transcript every agent is on and on the monitor, and only while a flow runs and is not already stopping. |
| <span id="cmd-exit"></span>`/exit` | <Badge type="warning" text="asks" /> | [Leaves](#leaving-and-letting-go): this interface, and nobody else's. Asks first if a flow is running, and says so beside it then. Also <kbd>ctrl+q</kbd>. |

</RefFilter>

`/afk` and `/claim` flip when given nothing, and take `on` or `off`. A line that is not a
command is shown in red and nothing happens:

| Typed | Answered |
| --- | --- |
| `/afk maybe` | `hmz: expected 'on' or 'off', not 'maybe'` |
| `/settings nosuch` | `hmz: /settings has no page 'nosuch': choose everywhere, directory, accounts, environments, fallback or flowverses` |
| `/nosuch` | `hmz: no such command: /nosuch` |
| `/stop`, nothing running | `hmz: no flow is running` |
| `/resume`, a flow running | `hmz: cannot resume a run while a flow is running: press ctrl+c twice to stop it first` |
| `/claim`, on an outworlder bob holds | `hmz: human is bob's: cannot claim it` |
| `/resume last` | `hmz: /resume takes no arguments: it resumes the last run here; use /epics to choose another run` |
| `/btw what's left` | `hmz: No closing quotation`: arguments are split like a shell line |

## Starting a flow outright

`$<flow> <task>` runs that flow on that task: `$ralph_loop fix the failing test`.

| The flow is | What happens |
| --- | --- |
| **set up here already** | It runs, now. |
| **never set up here** | [`/flow`](#choosing-a-flow) opens inside it. The task is held and runs the moment the menu is saved. Walk out without saving and `flow not set up; nothing started`. |
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
- Refused while a flow runs: `hmz: cannot choose a flow while one is running`.
- Not read as a flow while a question is up: the next line is the answer, whatever it starts
  with.

## While a flow runs

### Reading one agent

There is one transcript per conversation, one per agent holding all of its conversations, one
per outworlder, and one where every agent's work and everything every outworlder asks appear
together. The interface opens on that one, and goes back to it when a flow starts.

- <kbd>shift+tab</kbd> steps forward round it, the conversations with a turn open and the
  outworlders of the running flow, and <kbd>tab</kbd> steps back, wrapping at either end. A
  conversation that has ended stays on screen once you are on it, but is not stepped onto; it
  can still be read from [the monitor](#watching-the-run).
- Stepping onto another transcript redraws it from the top, under `── reading builder ·
  conversation 2 ──`, `── reading outworlder human ──` or `── reading all agents ──`.
  `/clear` clears only the one you are reading.
- A role's conversations are numbered in the order it opened them, from one, again for each
  run. Where it holds several, each turn says which: `● builder is working · conversation 3 of
  3`.
- On the shared transcript, a line `── builder` marks each change of speaker.
- `unread` marks an agent or an outworlder that has said something since you last read it.
  Nothing is marked while you read the shared transcript.
- Kept: the last 32 transcripts, a conversation's going before an agent's, and the last 2,000
  lines of each. The [trace](/reference/tracing) keeps everything.

### Talking to a running flow

A line typed while a flow runs goes to [the conversation you are reading](#reading-one-agent),
or, reading an agent, into its conversation with a turn open. Reading every agent at once, it
goes to whichever has a turn open. While a [question is up](#questions-and-being-away), a line
typed on the shared transcript or on the asking outworlder's answers it instead.

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
   `sent to <agent>, which ended its turn without acknowledging it`.
5. A flow that ends, however it ends, moves whatever is still pinned into the transcript,
   marked `never sent`.
6. What [another frontend](#several-people-on-one-run) says to the run is pinned and put in the
   transcript the same way, marked `· by <name>`.

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
| **MiniMax Code** | <Badge type="info" text="next turn" /> |
| **opencode** | <Badge type="info" text="next turn" /> |
| **Qwen Code** | <Badge type="info" text="next turn" /> |
| an **ACP CLI** of your own | <Badge type="info" text="next turn" /> |

**next turn**: a red line says why the line cannot be put in, and it waits for the next turn to
start.

Anchoring changes nothing here. An [anchored](/reference/remote-execution) Claude hears a line
during a turn like any other; its process ends between turns, when nothing is sent anyway.

### Side questions (`/btw`) {#btw}

`/btw [question]` enters btw mode, and asks the question if there is one. While it is on, the
status line starts with `btw · <who>`, and every line that is not a command is one more turn of
the same side conversation. `/btw` on its own, or <kbd>esc</kbd>, leaves it and closes every side
session it opened. Starting a flow or closing the interface leaves it too. Answers appear in
cyan as `● btw · <question> <answer>`.

Who answers depends on the view:

| View | Answered by |
| --- | --- |
| one agent or one session | That session's side copy: a fork of it where its CLI forks (`Profile.forks`), else a new session of the same agent given a snapshot of the run and that role's recent activity. Ended sessions too, with no flow running. |
| every agent, an outworlder, or the monitor | The btw agent: the one set on `/settings`, else the flow's first agent. It is given the snapshot and the list of sessions. |

Every side session runs at the read-only rung (a flow's `NONE`), with no skills, no goals, no
allow-listed tools, no MCP approval and none of the flow's callbacks.

The btw agent reaches a session by answering with lines of the form
`@ask <session>: <question>`, where `<session>` is `<role>/<n>`. The interface puts each one to
that session's side copy, opening it the first time, shows `btw · asking <session>: …`, and
hands the answers back as `<answer from="<session>">`. It may ask 4 per question; after that it
is told to answer with what it has. A line works on every CLI at the read-only rung, where a
tool would need one that takes tools.

The question on the `/btw` line is split like a shell line, so an apostrophe there needs quotes.
Lines typed in btw mode are taken as they are.

| Refused | Says |
| --- | --- |
| nothing to make the btw agent from | `hmz: /btw requires a coding agent` |
| the session is gone | `hmz: /btw: no conversation found for <session>` |
| a question while the last is still being answered | `hmz: btw is still answering the last question` |

### Questions, and being away

Two things wait on you. Both are shown on the transcript of the outworlder asking and on the
one every agent is on, and the next line typed on either is the answer rather than a word put
into the turn: the status line says `enter answer`. On the shared transcript it answers the
oldest question up, on an outworlder's the oldest that outworlder asks. On one agent's
transcript a line goes to the agent, as ever. The answers a question offers are numbered, and
a bare number picks one: `2` answers `2. south`.

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

Each outworlder is away or here on its own. `/afk` on an outworlder's transcript sets that one;
on the shared transcript or the monitor it sets every one, clearing what was set apart. It is
not offered on one agent's transcript, which asks you nothing: typed there it says
`hmz: /afk is only available on the monitor, the all-agents transcript and an outworlder's
transcript, not on one agent's transcript`.

Away is held with the runs rather than by this interface: it stays said after you
[leave](#leaving-and-letting-go), until somebody says otherwise. Where [other
frontends](#several-people-on-one-run) hold roles, `/afk` off an outworlder's transcript sets
every role you may answer for and leaves theirs as they are, and on the transcript of a role
somebody else holds it is refused, saying whose it is.

A question still up when the flow ends or is stopped ends with it.

### Stopping {#stop}

`/stop` stops the whole flow, not just the turn: what the second <kbd>ctrl+c</kbd> does, asked
once. The turn under way is interrupted and the flow unwinds from where it stands. There is one
run however many are reading it, so it stops for all of them, and each is told who stopped it:
`— alice@tui is stopping the flow —`.

- Listed only while a flow runs and has not been told to stop. Typed out anyway, it says why.
- With a flow already stopping: `hmz: the flow is already stopping: it is finishing the turn it
  was in`. The next <kbd>ctrl+c</kbd> closes its conversations without waiting.
- With nothing running: `hmz: no flow is running`.
- It resets <kbd>ctrl+c</kbd>'s count, so the press after it is a first press.
- Only on the transcript every agent is on and on the monitor, where the whole run is watched.
  Elsewhere it is not offered, and typed out says `hmz: /stop is only available on the monitor
  and the all-agents transcript, not on …`. <kbd>ctrl+c</kbd> twice stops the flow from anywhere.

See [Stopping](/user/stopping) and [ctrl+c](#ctrl-c).

### Leaving, and letting go

Closing the interface and stopping the run are two things: the runs are
[held by a process of their own](/reference/daemon), and this interface is one reader of them.
With a flow running, `/exit` and <kbd>ctrl+q</kbd> ask:

```text
A flow is running.

❯ 1. stop the flow and exit
  2. detach and exit              run `hmz` here to reattach

enter choose · esc stay
```

**detach and exit** lets go of this interface and nothing else: the flow carries on, anybody
else reading it goes on reading it, any role you [claimed](#several-people-on-one-run) is
anybody's again, and `hmz` in this directory reads the run again from the top. **stop the flow
and exit** stops the run for everybody, closing its conversations under whatever turn is open.
Where the runs are held in this process (output not a terminal, or
[`HUMANIZE_DAEMON`](/reference/cli#environment-variables) off), the second answer is
**cancel** instead. With nothing running, `/exit` leaves without asking.

### Several people on one run

Every `hmz` in a directory is a whole interface of its own -- its own views, monitor and
prompt -- over the same runs, and so is a program on the [SDK](/reference/daemon#link). Each
is named for `HUMANIZE_NAME`, else your login, then what it is: `alice@tui`, `bob@sdk`; a name
already reading gets `#2`.

- **Claims.** `/claim` on an outworlder's transcript makes what it asks yours alone to answer.
  Another interface sees it marked `alice@tui's` above its prompt, on the monitor and under the
  question, and a line it types there is refused, saying whose it is. `/claim off`, or leaving,
  gives it back; a role somebody else holds is refused (`reviewer is bob@tui's`).
- **Unclaimed questions** are everybody's: the first answer wins, and a later one is refused
  with `already answered by …`.
- **Who did what.** An answer, a line said to an agent, or a run started from another frontend
  carries ` · by <name>` in the transcript. The monitor lists who is reading under `Reading`.
- **Arriving late** reads the run from the top: what was said, asked and answered, and how
  things stand now.

## Menus

`/flow`, `/epics` and `/settings` each put up a sheet over the screen. The [keys
table](#keys) lists every key; each sheet's own are on its bottom row.

### Every menu {#the-menus-and-when-what-they-hold-lands}

| Rule | |
| --- | --- |
| **Four keys** | <kbd>↑</kbd> <kbd>↓</kbd> walk the rows, <kbd>←</kbd> <kbd>→</kbd> turn the pages, <kbd>enter</kbd> opens the row under the cursor, <kbd>esc</kbd> steps back. There are no others: what a menu does besides is a row of it. |
| **Nothing lands until you save** | On `/flow`, an agent's sheet, `/settings`, a flow's params and budget, and the forms `/settings` opens. Save with the `save` (or `set`) row below the choices. <kbd>esc</kbd> out of a menu holding changes asks, in a box over it, whether to save or discard; <kbd>esc</kbd> on the box goes back to the menu. A menu you only looked at asks nothing. |
| **Some happen at once** | `/epics` and the Environments and Flowverses pages of `/settings` hold no draft, and have no `save` row: what you ask for happens as you ask. So do making an account and signing one in on its Accounts page. |
| **Rows set apart** | Out of the numbering: `search…`, `add …`, `save`, and what else a menu does -- `check again`, `fetch again`, `copy … here`, `manage flowverses`, `remove …`. On the pages of `/settings` and the lists they open, they are above the list and `save` is last; elsewhere they are below it. |
| **Forms** | Adding or correcting something on `/settings` opens a form: a row per question, then `done`, which says what answering it will do. Typing on a written row writes it; <kbd>enter</kbd> keeps it and moves on to the next row still to be answered, or to `done`. What the form guessed for you is replaced by the first letter typed. |
| **Changing a row** | A row marked `↔`, a switch, or a field to write is changed where it stands: <kbd>enter</kbd> begins, <kbd>←</kbd> <kbd>→</kbd> or typing change it, <kbd>enter</kbd> keeps it, <kbd>esc</kbd> puts it back. Walking past a row never changes it. `▸` opens something. |
| **Search** | <kbd>enter</kbd> on `search…` starts it, letters narrow by name, <kbd>esc</kbd> clears and leaves it. Where the search row is above the list, the cursor goes to the first match. Typing never searches by itself. |
| **Pages** | A menu of several pages shows their titles across the top, and <kbd>←</kbd> <kbd>→</kbd> turn between them. A page that cannot open now is struck through. |
| **Going deeper** | <kbd>enter</kbd> opens what you picked; <kbd>esc</kbd> comes back one step. |

### `/flow` {#choosing-a-flow}

Which flow runs, and inside it, what fills each role. It opens on the flows of one **place** at
a time, with <kbd>←</kbd> <kbd>→</kbd> stepping between places: each
[flowverse](/reference/flows#flowverses) (`official` first: `chat` from the package, plus what
has been fetched), then `local` (`.humanize/flows/` here) and `user` (`~/.humanize/flows/`),
each where there are any.

```text
  Flow

  Choose a flow to run; you will type its task next. To run a flow
  from elsewhere, type its path.

  official · local · user

❯ 1. chat            Chat — one agent, one session, and every line ty…
  2. continue_loop   Continue loop (flowbench: continue_loop) — send …
  3. flame_chase     Flame chase (flowbench: flame_chase) — two agent…

     search…
     copy chat here         so you can edit it
     manage flowverses      the flowverses page of /settings

  enter open · ←/→ place · esc close
```

- It opens on the place the flow in force came from. A place never fetched is fetched as the
  menu opens, in the background; how that went is said under the list. An empty place says so,
  and one never fetched says `not fetched yet; select manage flowverses below to fetch`.
- `search…` searches flow names across every place, and narrows the strip to the places with a
  match. What a flow says about itself is not searched.
- `copy … here` copies the flow the cursor was last on, with what it imports and the skills it
  brings, into `.humanize/flows/`. Your own are looked in first, so the name then means your
  copy.
- `manage flowverses` opens `/settings` on [Flowverses](#where-flows-come-from).
- **While a flow runs**, there are no flows to choose: `/flow` opens inside the running flow's
  roles, and <kbd>esc</kbd> there leaves. What you save is what the next run starts on.
- `/flow <name>` opens already inside that flow; `/flow ./path` opens a flow of your own by
  path. Both are refused while a flow runs: `hmz: cannot choose a flow while one is running`.
- The same places are [`Hmz().verses`](/reference/sdk) from Python.

<kbd>enter</kbd> on a flow asks its [params](#setting-a-flow-up), where it declares any, then
lands on its roles:

| Row | |
| --- | --- |
| one per agent role | What fills it, or `not set`. <kbd>enter</kbd> opens [the agent's sheet](#what-each-agent-is). |
| one per environment role | [Where it is](#where-each-agent-works), or `not set`. |
| `budget` | [What a run may spend](#what-a-run-of-it-may-spend). |
| `save` | Checks every role against what the flow declares, and applies the flow, its roles, its params and its budget together. |

Roles the runtime fills are not rows: an `Outworlder` is you, and a `LocalEnv` is the directory
the interface was started in. <kbd>esc</kbd> goes back to the flows.

#### An agent's sheet {#what-each-agent-is}

An agent is a CLI, an account, a model and an effort: exactly what `-a` says.

```text
  Set up builder

  Configure this agent: select its CLI, account, model, and reasoning
  effort.

  ❯ 1. cli        claude ▸          coding agent CLI to use
    2. account    as local ▸        account to run as
    3. model      claude-opus-5 ▸   model to use
    4. effort     high ↔            reasoning effort

       save                         this agent

  enter open · esc close
```

| Row | |
| --- | --- |
| `cli` | [Which CLI](#which-cli-and-which-account). Changing it lets go of the model. |
| `account` | [Which account](#which-cli-and-which-account) of that CLI. |
| `model` | [Which model](#what-each-agent-runs) that account may name. |
| `effort` | A rung on that model's ladder, changed where it stands: <kbd>enter</kbd>, <kbd>←</kbd> <kbd>→</kbd>, <kbd>enter</kbd>. |
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
  Select the account to run as

  ❯ 1. as local   use the account signed in on this machine
    2. deepseek   gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
    3. work       login

       search…
       add        an account

  enter choose · esc back
```

- `as local`, always first, is the CLI as you already run it, with nothing redirected.
- The `add` row makes an account without leaving, on [the same form](#making-an-account) as the
  Accounts page less its `cli` row, and the CLI's own login where the way has one. It comes back
  with the new account chosen, and the agent's sheet then asks its CLI what it runs, saying so
  under its rows while it does. A CLI with none says `claude has no saved accounts yet`.
- An agent given an account that has since been taken away fails its first turn, naming the
  account. It never runs as yours instead.

#### Which model {#what-each-agent-runs}

```text
  Select a model for claude

  The model claude uses for this agent's turns, and its reasoning
  effort. These are the models last reported for this account.

    1. claude-opus-5     max, high
  ❯ 2. claude-sonnet-5   max, high

       search…
       check again

  enter choose · esc back
```

- The list is what the chosen account may name. Where the account points its CLI at an
  endpoint, the endpoint is asked. It is asked the first time the interface opens, whenever an
  account is made, and on the `check again` row.
- An account never asked says so where the list would be; one nothing answers for says why
  under it.
- Choosing a new model starts its effort at the hardest it takes. Choosing the same one keeps
  the effort.

#### Where each agent works

Each environment role the flow declares is a row under the agents. <kbd>enter</kbd> on it opens
one form, whose rows are the parts of what `-e` takes after `<role>=`:

```text
  Environment for box

    1. backend  ssh ↔                   a machine reached over ssh
    2. host     gpu ▸                   from ~/.ssh/config · working directory: ~/work
    3. workdir  ~/work                  leave blank to use saved default: ~/work
    4. as -e    ssh@gpu                 full -e spec: typing one sets the rows above

  ❯    done                      sets box to ssh@gpu when the flow is saved

  enter done · esc back
```

| Row | |
| --- | --- |
| `backend` ↔ | Every backend `-e` takes. It starts on the first one an [environment provider](#environments) is saved for, else on `local`. Changing it lets go of the host and the workdir. |
| `host` ▸ | Not asked for `local`; `daemon` for a docker backend, once `-e` takes one. Opens the providers of that backend saved on [Environments](#environments), with `add an ssh host` (or `add a docker host`) above them, which saves one on the same form and comes back with it chosen, and, for ssh, `unsaved host`: `host`, `user@host`, `host:port` or an ssh config alias, saved nowhere. |
| `workdir` | The directory there: absolute, or `~/…` under the ssh login's home. It starts from where the provider is saved to work, and while it still says that, `as -e` leaves it out so the role follows the provider; typed over, it is spelled out. Blank is the provider's too. |
| `as -e` | All of it, as `-e` spells it. Typing a whole spec there sets the rows above. |
| `done` | Holds it with the rest of the menu, read the way `-e` reads it: one that does not read is refused under the form, in `-e`'s words. With nothing said, it leaves the role unset. |

| Answer | Where the work goes |
| --- | --- |
| `local@/home/me/repo` | A directory on this machine. |
| `ssh@gpu-box/home/me/repo` | A directory on a host you reach with ssh: a saved provider, `host`, `user@host`, `host:port` or an ssh config alias. |
| `ssh@gpu-box/~/repo` | The same, under the ssh login's home. |
| `ssh@gpu-box` | Where the provider `gpu-box` is saved to work. |

A host that cannot be reached, a missing directory and a machine smaller than the role declares
are red lines when the flow starts, before any turn. An agent spawned in an ssh environment
takes its turns there; its credentials stay here. See
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

  Configure how this flow runs. Options and validation are defined by
  the flow itself.

    1. plan_file       docs/plan.md   --plan-file: the plan to build, …
  ❯ 2. max             20▏ ↔          --max: rounds before the loop st…
    3. codex_timeout   5400 ↔         --codex-timeout: seconds one rev…

       set                            all of the above

  ←/→ change · enter keep · esc undo
```

| Key | |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Between fields, stepping over headings. |
| <kbd>enter</kbd> | On a field, begins changing it; pressed again, keeps the change. On `set`, takes every field. |
| <kbd>←</kbd> <kbd>→</kbd> | While changing a field: a switch flips, a choice steps, a number moves by one. |
| typing · <kbd>backspace</kbd> | While changing a field that is written. A caret marks where. |
| <kbd>esc</kbd> | While changing a field, puts it back. Otherwise back, asking about anything changed. |

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

### `/settings` {#what-humanize-remembers}

Everything humanize remembers, in one menu of six pages. `/settings` opens on the first,
`/settings <page>` on the one named (`everywhere`, `directory`, `accounts`, `environments`,
`fallback`, `flowverses`, offered as you type). <kbd>←</kbd> and <kbd>→</kbd> turn between them;
`manage flowverses` on `/flow` opens it on **Flowverses**.

```text
  Settings

  Everywhere · This directory · Accounts · Environments · Fallback · Flowverses

  ❯ 1. reports   on ↔    send error reports to humanize
    2. sent      ▸       what error reports include and exclude
    3. details   off ↔   show every tool call and all of the thinking

       save              no changes yet

  enter change · ←/→ page · esc close
```

| Page | Row | |
| --- | --- | --- |
| Everywhere | `reports` ↔ | Whether humanize [reports what goes wrong](/user/reporting): `on`, `off`, or `not set`. Where `HUMANIZE_SENTRY` overrides it for this run, the page says so. |
| Everywhere | `sent` ▸ | What a report carries and what it never does. <kbd>enter</kbd> reads it out. |
| Everywhere | `details` ↔ | Shows or hides [the working](/user/settings#details): every tool call, all of the thinking, and what a backend prints on its way past. Off until turned on, and remembered in `~/.humanize/settings.yaml` as `details`, so the next start opens the same way. The status line says `details` while it is on. |
| Everywhere | `btw` ▸ | The [btw agent](#btw). <kbd>enter</kbd> sets it up on the same sheet as a flow's agent; `reset to the flow's first agent`, under it once one is chosen, undoes that. Saved as `btw:` in `settings.yaml`; takes effect the next time btw mode is entered. |
| This directory | `workspace` | The directory these are for. |
| This directory | `flow` | The flow it opens on, and how many agents that flow was set up with. |
| This directory | `profile` ↔ | Whether a run here [profiles](/user/tracing#profiling-a-run) the programs it starts. |
| This directory | `forget` ↔ | Forget everything remembered here, across every flow. Other directories are untouched. |
| Accounts | | [The accounts](#the-accounts-themselves) agents run as. |
| Environments | | [The machines](#environments) a flow's environments go on: add, import, check, edit, remove. |
| Fallback | | [Where a turn goes](#where-a-turn-goes-when-it-cannot-be-taken) when its place cannot take it. |
| Flowverses | | [Where flows come from](#where-flows-come-from): add, fetch again, remove. |

- On the first two pages, <kbd>enter</kbd> begins changing the row under the cursor,
  <kbd>←</kbd> <kbd>→</kbd> step it and <kbd>enter</kbd> keeps it. The last four are lists,
  laid out alike: `add …` and `search…` above the list, the list, then `save` where the page
  holds anything. The cursor opens on the first thing listed, or on `add …` where there is
  nothing yet. What the line under a list last said is still there when you turn back to it.
- What every page holds lands together, on the `save` row; <kbd>esc</kbd> with anything held asks
  whether to save or discard. Making an account, signing one in and everything on
  Environments and Flowverses happen at once instead.
- Once saved, the transcript says what changed, and, for what cannot take hold at once, when it
  will. `reports`, `details` and the fallback steps take hold at once (the next failed turn
  reads the steps). `profile` does from the next flow run. A corrected account, what it fails
  over to, or one taken away, from the next agent session: a session already running keeps the
  account it started with, and the row says `from the next agent session` while such a change
  is held. `forget` from the next launch: the interface open now keeps what it opened with.
- On a first start, a box asks `Report errors to humanize?`; <kbd>esc</kbd> there
  leaves it unanswered, to be asked again next time.

#### Accounts {#the-accounts-themselves}

Every account an agent may run as, under a heading per CLI, with the way it was made and the
variables it sets (names only, never values).

```text
     add an account          a sign-in for one CLI: API key, login, or gateway
     add a custom CLI        supports ACP
     search…

  claude
  ❯ 1. deepseek   gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
    2. work       login
    3. as local   the account signed in on this machine · fails over to
                  work

  codex
    4. personal   key
    5. as local   the account signed in on this machine

     save                    no changes yet
```

![The Accounts page of /settings: the accounts under a heading per CLI, and enter opening what
there is to do with one](/demo/accounts.gif)

| Row | |
| --- | --- |
| `add an account` | Makes one, on [one form](#making-an-account). |
| `add a custom CLI` | Writes down a [CLI of your own](/reference/agents#a-cli-of-your-own) that speaks ACP: the command that starts it, then `done`. |
| an account | What there is to do with it (below). |
| `save` | Saves. <kbd>esc</kbd> closes, asking about anything held. |

![What enter opens on one account: edit settings, sign in again, fails over to, and
remove](/demo/account-does.png)

| On one account | | Lands |
| --- | --- | --- |
| **edit settings** | Its way's questions again, on the account form less its `cli`, `way` and `name`. A secret starts blank and says `leave blank to keep current value`: leave it, or type a new one. Each CLI already holding a copy starts switched on, so a rotated key lands on every copy. | on save |
| **sign in again** | Runs its way in again; a login command owns the terminal until it is done. It asks only what the way still needs. | at once |
| **fails over to** | Which account of the same CLI a turn carries on as when this one fails. `add an account` above the list makes one and chooses it. | on save |
| **remove** | The account and its credentials. Marked, it reads **cancel removal**. | on save |

- The last row under each CLI is `as local`: the CLI as this machine is signed in. It offers
  only **fails over to**, and says why: humanize keeps no credentials for it.
- Nothing here is refused while a flow runs. What lands on save reaches an agent from its next
  session, and the row says `from the next agent session` while it is held: a session already
  running keeps the account it started with.
- How often a failed turn is tried again is
  [Fallback](#where-a-turn-goes-when-it-cannot-be-taken), not here.
- The same accounts are [`Hmz().accounts`](/reference/sdk).

##### Making an account {#making-an-account}

```text
  Add an account

  ❯ 1. cli                claude ↔   installed here
    2. way                key ↔      an Anthropic API key, from the console
    3. name               key        account name
    4. ANTHROPIC_API_KEY  ••••••     the API key
    5. also for pi        on ↔       installed here
    6. also for opencode  on ↔       installed here

       done                          adds claude/key, for pi, opencode too

  type to edit · esc back
```

| Row | |
| --- | --- |
| `cli` ↔ | The CLI it is for: the ones installed here first, then the rest, marked `not installed here yet`. Not asked where the CLI is already known. |
| `way` ↔ | [How it signs in](/reference/providers#the-ways-in), with what that way is beside it. Changing it changes the rows under it. |
| `name` | Written in for you: the way's own name, or `-2`, `-3` after it where an account of any CLI is already called that. The first letter typed replaces it. |
| what the way asks | One row per question, under the variable it becomes. A secret is drawn as bullets. A way that asks nothing in particular (`env`) has one `variables` row, `NAME=VALUE` a line. |
| `also for …` ↔ | One per other CLI the account could run (an Anthropic key in pi, opencode, mimocode), on where that CLI is installed here. Only variables travel: a login has none of these. |
| `done` | Says what it will do, then does it: writes the account, copies it, and hands the terminal to the CLI's own login where the way has one. |

- The cursor opens on `cli`. Keeping `way` moves it to the first question still to be answered;
  keeping an answer moves it to the next, then to `done`.
- Once it lands, the account's CLI is asked what it runs, in the background: the row says
  `checking models…`, and the line under the list says how many models it named or why it
  named none.

#### Environments {#environments}

The machines a flow's environment roles can be put on, saved under a name that `-e` and
`/flow` then name: ssh hosts, and docker daemons with what each may hand out, under a heading
per backend. They are kept in `~/.humanize/env-providers/` (see
[Machines › Environment providers](/reference/machines#environment-providers)).

```text
     add an ssh host           a machine reached over ssh
     add a docker host         a local or remote docker daemon
     import ~/.ssh/config      hosts from this or another config file
     search…

  ssh
  ❯ 1. box                     me@box.example.com:2200 · key ~/.ssh/id_box · working
                               directory: ~/proj
    2. gpu                     from ~/.ssh/config · working directory: ~/work

  docker
    3. local                   local · 16 CPUs, 64G, GPUs 0

  enter open · ←/→ page · esc close
```

![The Environments page of /settings: the ssh hosts and the docker daemons under a heading
each, below the rows that add and import one](/demo/environments.png)

| Row | |
| --- | --- |
| `add an ssh host` | One form: `host` (`user@host:port` is taken apart into `user` and `port`), `name` (written in after the host, never one already saved), `user`, `port`, `identity file` (a path; never read), `proxy jump`, `options` (`KEYWORD=VALUE, …`), `workdir`, then `done`. |
| `add a docker host` | One form: `endpoint` ↔ (`local`, `socket`, `tcp` with a TLS directory, `saved ssh host` ▸, `ssh address`, `context`) and the row that way asks, `name`, `image`, `runtime`, `run args`, `max containers`, `workdir`, then what it may hand out: `cpus`, `memory` (`64G`, in docker's units of 1024) and `gpus` (`0, 1`), each blank to use all the host has. `detect` asks the daemon and writes what it has into those three to be typed over, the cursor on the first. |
| `import ~/.ssh/config` | A form: `from`, the config to read (yours, or a path typed over it), then a switch per host it names, as `ssh -G` resolves it: on, unless it is saved already. The cursor lands on `done`, which saves each host switched on under its `Host`. Nothing is written to the config. |
| a provider | What there is to do with it (below). |

| On one provider | |
| --- | --- |
| **edit** | Its form again, less the name; an imported host has an `alias` row too. |
| **check** | An ssh host is reached as a run reaches it, with nobody there to type a password: its home, CPUs, memory and GPUs. A docker daemon is asked `docker info`, and what it is saved to hand out and has not got is said in yellow. Given 30 seconds, in the background. |
| **remove** | It is saved no more. A docker host that reached its daemon through it is named. |

- Everything here happens at once, so the page has no `save` row. A provider added or corrected
  is checked as it lands, and the line under the list says what it answered or why it could not
  be reached.
- A search narrows by name, backend, and what the row says.
- The same providers are [`Hmz().environments`](/reference/machines#environment-providers).

#### Fallback {#where-a-turn-goes-when-it-cannot-be-taken}

A list of steps between **places**. A place is a CLI, an account and a model: what a turn can
fail for having named (a retired model, a CLI that will not start, a rate limit on the whole
account). The effort and what the agent may reach for carry across a step unchanged.

```text
  Settings

  Everywhere · This directory · Accounts · Environments · Fallback · Flowverses

  Where a turn falls back when an agent fails. An agent is a CLI, an
  account and a model. Saved rules apply from the next failed turn.

       add fallback rule           an agent that fails, and its fallback
       search…

  ❯ 1. claude@work/claude-opus-5   3 retries, exponential · falls back
                                   to codex@key/gpt-5.6-sol
    2. codex@key/gpt-5.6-sol       falls back to dsh/deepseek-v4-flash

       save                        all changes

  enter edit · ←/→ page · esc close
```

- `add fallback rule` opens one form: `fails on` ▸, `falls back to` ▸, then `tries`, `policy`
  and `for` ↔, then `done`. Each place row opens one list of every place (each CLI here, as each
  of its accounts, at each model it runs), searched by any of the three; an account that has not
  said what it runs is a row of its own, and choosing it asks. `falls back to` offers `nowhere`
  first and never the place that fails.
- <kbd>enter</kbd> on a step opens the same form for it, with `remove` above `done`.
- A place cannot fall back to itself; a chain that comes round ends at the second sight of a
  place. A step that falls back nowhere and tries nothing again is refused: `choose a fallback
  agent or set retries`.
- An account failing over to another account of the same CLI is on
  [Accounts](#the-accounts-themselves), not here.
- Held until saved, then read by the next turn that fails. The same steps are
  [`Hmz().fallbacks`](/reference/sdk). What they mean is [Falling back](/user/settings#fallback).

A step's three ways of trying again are changed where they stand:

| Row | Steps through |
| --- | --- |
| `tries` | `none`, 1, 2, 3, 5, 8, 13, 21 retries |
| `policy` | `none`, `constant`, `linear`, `exponential`, `exponential-jitter` (the default), `fibonacci` |
| `for` | `no limit`, `30s`, `1m`, `5m`, `15m`, `60m` |

#### Flowverses {#where-flows-come-from}

Where flows come from: each a git repository with a `flows/` directory, cloned under
`~/.humanize/flowverses/`, plus your own `local` and `user`. `manage flowverses` on `/flow`
opens `/settings` on this page.

![The Flowverses page of /settings: official, which holds `chat` from the package and, at its
GitHub URL, the rest, marked as not fetched yet](/demo/flowverses.png)

| Row | |
| --- | --- |
| `add a flowverse` | Adds one: a URL or `owner/repo`, then a name to keep it under (blank for the repository's own); `done` clones it. |
| a flowverse | What it holds: `fetch again` (or `fetch`) and the row that takes it away, then a row per flow. `official`, `local` and `user` cannot be taken away, and say why; `local` and `user` have nothing to fetch. |

- A place never fetched is listed anyway, with its URL and `not fetched yet`.
- Nothing on this page is held, so it has no `save` row.
- Each happens as you ask: a clone runs in the background, and what came of it is said under
  the list and again in the transcript.
- Every start of the interface fetches every flowverse that has a URL, quietly and one at a
  time, except a clone you have written into. It stops if a flow starts. A fetch that brings
  something down makes any open list of flows read them again.
- `manage flowverses` is refused while `/flow` is still fetching the place it opened on.
- Nothing here is refused while a flow runs.
- The same is [`Hmz().verses`](/reference/sdk): `add`, `fetch`, `remove`, `holds`.

### `/epics` {#the-runs-that-have-already-happened}

Every run of a flow in this directory, newest first.

![The /epics list: two runs, each with when it began, the flow that ran, what it was asked to
do and how many sessions it opened, the newer one marked "resumable"](/demo/epics.png)

- A row is when the run began and the flow; beside it, the task, how many sessions it opened,
  and `resumable` where its flow says it can be picked up and it left a journal. How it ended is
  shown only when it did not finish: stopped, failed, or unfinished.
- `search…` searches the flow, the task and the run's name.
- <kbd>enter</kbd> goes into a run: where it is written down, then what to do with it.

![Inside one run: its directory, how it went and how much it opened, over resume run and
export run](/demo/epic-does.png)

| Row | |
| --- | --- |
| **resume run** | Picks the run up: its own flow, agents, environments, params, budget and task, from where its journal got to. [`/resume`](#carrying-the-last-one-on-outright) with the run named, refused for the same reasons in the same words. Offered only where the flow says **now** that it can be picked up. |
| **export run** | Packs **that run** into `.humanize/<run>.epic.tar.gz`: its records, every session log in full, a manifest, and a [trace](/user/tracing) of its sessions (and programs, for a [profiled](/reference/tracing#profiling-a-run) run), which also lands in the run's own `traces/`. Where it landed and how big are said under the list. See [Exporting a run](/user/export). |

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
| `no run here was of a flow that can be resumed` | Every run was of a flow that neither said nor says so. |
| `<run> cannot be read` | Its record is not one. |
| `<flow> does not support resuming` | Asked of the flow as it is today. A flow that will not load says no. |
| `<run> has no saved state to resume` | Killed before its journal held anything. Say what to do and the flow starts from the top. |
| `cannot resume a run while a flow is running` | [Stop it](#stop) first. |
| `cannot resume a run while the flow is still stopping` | Wait for it to unwind, or [press ctrl+c](#ctrl-c) once more. |

`hmz exec --resume` is the command-line equivalent: see
[Picking a run up](/reference/cli#picking-a-run-up).

### The monitor {#watching-the-run}

The run, drawn across the whole screen, over the log's own prompt. It is the parent of the log:
<kbd>←</kbd> with nothing typed goes up to it, and picking a node reads that node's log. It is
never refused, redraws itself while up, and every command works from its prompt. There is no
command for it, and <kbd>esc</kbd> does not open it.

```text
   graph   list
❯ ▣ all agents · 1 of 2 working · 17 turns · 7m11s · reading
  ┌──────────────────────────────────────────────────────────────────────┐
  │ ▸ ● builder                                                      43s │
  │ claude/claude-opus-5:high · 12 turns · 48.2k tokens                  │
  │ ▤ repo docker                                                        │
  └──────────────────────────────────────────────────────────────────────┘
    ├╴◆ Task read the tests
    └╴◇ Task find the flaky one
  │   ↓ 6 · ↑ 5
  ┌──────────────────────────────────────────────────────────────────────┐
  │ ▾ ○ reviewer                                              idle 1m04s │
  │ codex/gpt-5.6-sol:high · 5 turns · 2 sessions · 9.1k tokens   unread │
  │ ▤ repo docker                                                        │
  └──────────────────────────────────────────────────────────────────────┘
    ├╴○ session 1 · 3 turns · 5.0k tokens                     idle 6m40s
    │   ▤ repo · docker · builders · /work
    └╴○ session 2 · 2 turns · 4.1k tokens            unread · idle 1m04s
        ▤ repo · docker · builders · /work

Flow:             humanize1:rlcr   431s
Set:              max                          20

Tokens:           claude-opus-5        48.2k    $1.34   91 out/s
                  gpt-5.6-sol           9.1k             12 out/s
Kinds:            input                 1.2k
                  output                 980
                  cache_read           46.0k
                  cache_write           9.1k
────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────
  ▣ monitor · graph  ↑↓ node · space sessions · enter open · → back · ctrl+t list
```

| Part | |
| --- | --- |
| `graph` `list` | The switch above the drawing, the way it is drawn now lit. A click on the other half, or <kbd>ctrl+t</kbd>, turns to it; the monitor opens again the way it was left. |
| `▣ all agents` | The first node, where the cursor starts: how many boxes are working, the run's turns and time. <kbd>enter</kbd> reads the shared transcript. |
| `◉ <role> · outworlder` | Under it, a node per outworlder of a run that talks to you, with `yours` or `<name>'s` where somebody [holds it](#several-people-on-one-run). <kbd>enter</kbd> reads what the flow says to you. |
| a box | One per agent that has taken a turn, in the order the flow declares them. Left: `▸` shut or `▾` opened out, `●` working or `○` idle, the name, what it runs, its turns, its sessions where it has more than one, and the tokens its backend reported; a third line names the environments its sessions work in. Right: how long the open turn has run, or `idle` and how long since its last; `reading` or `unread`. <kbd>enter</kbd> reads it, working or ended. |
| `├╴○ session <n>` | Under an agent opened out with <kbd>space</kbd>, a row per session that has taken a turn: its turns, tokens and clock. <kbd>enter</kbd> reads that session's own log. |
| `▤ <role> · <kind> · <target> · <workdir>` | Under each session, the environment it works in. <kbd>enter</kbd> opens [its page](#an-environment-s-page). |
| `├╴◆` `└╴◇` | Sub-agents it started of its own, under the box, or under the session that started them once the box is opened out: `◆` still going, `◇` back. Only from [backends that report them](/reference/agents#not-every-backend-runs-every-moment). A long fleet is cut, with a count. |
| `↓ 6 · ↑ 5` | Handovers between neighbouring boxes, each way; the latest one lit. |
| `Flow` | What is running, nested flows indented under the flow that called them, each with its time. |
| `Set` | The flow's params that are not at their defaults. |
| `Reading` | Where [more than one frontend](#several-people-on-one-run) reads the runs: each by name, yours marked `you`. |
| `Agents` | Before any agent has worked: the agents set up, in place of the boxes. |
| `Also` | On the graph, handovers between boxes that are not neighbours. |
| `Tokens` | One row per model, biggest first: tokens, money (blank where unpriced), output tokens a second. |
| `Kinds` | The run's tokens by kind, over every model. `+` marks a floor. |
| the last line under them | What the last command typed here answered. |
| the status line | `▣ monitor`, `graph` or `list`, and the keys that work now. |

The arrows, <kbd>space</kbd> and <kbd>enter</kbd> are the graph's only while nothing is typed;
once you type, they are the prompt's. <kbd>space</kbd> on a session or an environment shuts the
agent it hangs under.

**With the mouse**, a click does what <kbd>enter</kbd> does, except on an agent: on its left
edge, where `▸` is, or on the agent the cursor is already on, it opens the agent out or shuts
it; anywhere else it moves the cursor there, and a double click reads it.

**The list** (<kbd>ctrl+t</kbd>) is the same nodes as rows, without the handovers: every agent,
the sessions of the ones opened out, and every environment, each with what it runs or where it
is, its turns (an environment's sessions), its clock and its tokens. Whatever is working is at
the top; the rest keep their order, so a row moves only when what it is about starts or stops.

#### An environment's page

Opened with <kbd>enter</kbd> or a click on an environment, and live while it is up:

| Row | |
| --- | --- |
| `kind` | `LOCAL`, `SSH` or `DOCKER`. |
| `target` | The ssh host or docker provider, or `this machine`. |
| `workdir` | Where on it its sessions work. |
| `set up as` | Its `-e` spelling, where it was set up here. |
| `image` | What a container for it starts from, where the flow names one. |
| `grants` | The environment capabilities the flow declared for the role. |
| `needs` | CPUs, memory and GPUs the flow asks of the machine. |
| `harness` | Where its agents run: on this machine, anchored to an ssh or docker environment so that what they run lands there. |
| `status` | How many of its sessions are working. |
| `Sessions` | Each session working in it; <kbd>enter</kbd> or a click reads one. |

<kbd>esc</kbd> goes back to the monitor.

**The board** sits under the diagram where the run keeps one: named lines you and the flow both
write, each a node the arrows reach. <kbd>enter</kbd> on `+ add entry` puts one up (a name,
then its value), <kbd>enter</kbd> on a line changes it, and a line saved empty is taken off at
once. A line the flow wrote is the flow's to change. Where the run keeps no board, none is
drawn. See [The mission board](/user/board).

After a run ends, its boxes stay, with every clock stopped where the run stopped.

## At the prompt

### Completion

A half-typed line is offered what it could become, in a list above the editor:

| Typed | Offered |
| --- | --- |
| `/` | The commands that would do something now, each with what it takes and a line about it. See [Slash commands](#commands). |
| `/flow ` | Every flow: humanize's own, every fetched flowverse's, and your `local/` and `user/` ones. Nothing while a flow runs. |
| `$` | The same flows, while the word after `$` is being typed. What follows is the task, and is not completed. Nothing while a flow runs. |

- A word already written out in full is offered nothing, so <kbd>enter</kbd> sends `/settings`
  as it is.
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
- **Details**, as `details: true` or `false` at the top of the file, for every directory: the
  interface opens showing the working or not, as it was last left.

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
