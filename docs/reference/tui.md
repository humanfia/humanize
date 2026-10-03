---
pageClass: hmz-ref
outline: [2, 3]
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
import RefFilter from '../.vitepress/theme/components/ref-cli/RefFilter.vue'
</script>

# TUI reference

The terminal interface `hmz` opens with no command: its screens, views, commands, keys, menus,
settings, monitor and messages. Package `hmz.tui`, class `Humanize` (a Textual `App`).
Notation: [Conventions](/reference/#conventions). In this page, `●` is `⏺` on macOS, and
*red*, *yellow*, *cyan* and *dim* are the terminal's own palette entries (see
[Colours](#colours)).

## Launch {#launch}

```python
class Humanize(App[None]):
    def __init__(self, flow: str = "", agents: Mapping[str, Runs] | None = None,
                 params: BaseModel | None = None, link: Link | None = None) -> None
    def action_quit(self) -> None
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `flow` | `""` | The flow to open on. `""`: the flow remembered for this directory, else `chat`. |
| `agents` | `None` | What each agent role runs. `None`: what is remembered for the flow, with unremembered roles [filled by default](#default-fill). |
| `params` | `None` | The flow's params. `None`: remembered, else the flow's defaults. |
| `link` | `None` | The [link](/reference/daemon#link) to a host. `None`: a `Host` in this process, linked as `kind="tui"`. |

`hmz` constructs `Humanize(link=…)` or `Humanize()` as described in
[CLI › Where the runs are held](/reference/cli#where-runs-are-held); `app.return_code or 0` is
the exit status. There is no command palette (`ctrl+p` does nothing).

At mount, in the background, the interface:

| Task | Detail |
| --- | --- |
| Asks installed backends for models | Each installed CLI's own account whose model list was never fetched or is older than 7 days. Failures are logged only. |
| Fetches flowverses | Every flowverse index with a URL (cloning `official` the first time) whose clone holds no local edits, one at a time. Installed flows are not touched. A fetch that brings new commits makes open flow lists re-read. Then, where any installed flow's index lists a newer release, prints once, dim: `updates available: <flow> <v> ↑ <newer>[, …]; update from /flow`. |
| Looks for a run to resume | Decides whether [`/resume`](#resume) is listed. |
| Refreshes prices | `$HUMANIZE_HOME/prices.json` from `HUMANIZE_PRICES` (default `https://openllmprices.com/data/prices.json`) when older than 24 h; at most one attempt an hour, 20 s timeout. |
| Asks the reporting question | Only where unanswered: [First start](#first-start). |

## Screen {#the-screen}

```text
╭─ humanize v0.1.0 ──────────────────────────────────╮
│                                                    │
│    HUMANIZE, drawn large                           │
│                                                    │
│    The agent flow system for token maxxing.        │
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

| Region | Content |
| --- | --- |
| Opening box | Rounded dim border, title `humanize v<version>`; the word `humanize` in blue, figlet font `ansi_shadow` where it fits the width minus 10, else `small`; a blank line; the package summary. Redrawn by [`/clear`](#cmd-clear). |
| Transcript | The [view](#views) being read. Follows the end until scrolled up; follows again once back at the bottom. |
| Offers list | Above the editor, at most 10 rows: [completion](#completion) offers or one hint row. |
| Right of the pin area | [Agent lines](#agent-lines), [outworlder lines](#outworlder-lines), [cost readout](#cost-readout). |
| Pin area (left) | [Lines waiting](#talking-to-a-running-flow) to be taken. |
| Editor | Multi-line, at most 10 rows, prompt `❯`, between full-width `─` rules. Always focused. |
| Status line | [Left: modes and state; right: key hints](#the-status-line). Redrawn every 0.5 s. |

## Views {#views}

<span id="reading-one-agent"></span>

| View | Key | Holds |
| --- | --- | --- |
| all agents (aggregate) | `""` | Every agent's lines and every outworlder's questions and answers. Default view; selected again when a run starts. |
| one agent | `<role>` | Every conversation of that role. |
| one conversation | `<role>/<n>` | One session. `<n>` counts from 1 per role per run, in opening order. |
| one outworlder | `outworlder:<role>` | What the flow asks through that `Outworlder` role, and the answers. |
| monitor | — | A screen of its own: [Monitor](#watching-the-run). |

For command availability the view kinds are `aggregate`, `session` (one agent or one
conversation), `outworlder` and `monitor`.

| Rule | |
| --- | --- |
| Where a line goes | A conversation's line: the aggregate, its role's view, its own. An outworlder's line: its own view and the aggregate. Lines the interface itself shows (`hmz: …`, confirmations): the view being read only, and the monitor's last line. |
| Speaker marker | On the aggregate, a blank line and `── <title>` whenever the speaker changes (`── outworlder <role>` for an outworlder). |
| Switching header | The new view is redrawn from the top under `─ reading <title>[ · <n> conversations] ─`. Titles: `all agents`, `<role>`, `<role> · conversation <n>`, `outworlder <role>`. When a new run starts while another view was read: `─ that flow has gone, now reading all agents ─`. |
| Unread | Set on a view other than the one read when a line is written there; never on or while reading the aggregate. Reading the aggregate clears every unread mark. |
| Retention | At most 32 transcripts of at most 2 000 lines each. Over the limit, the oldest are dropped, conversations before others, never the aggregate, the one being read, or the one just opened. A new run deletes every conversation transcript of the previous run. |
| Round | [`shift+tab`](#key-tab) steps forward, `tab` back, wrapping, through: the aggregate, every conversation with a turn open (in first-seen order), every outworlder of the running flow. A view not in the round starts from the aggregate. An ended conversation stays readable once read, and from the monitor. |

### Turn lines {#turn-lines}

| Line | Style | Shown |
| --- | --- | --- |
| `● <agent> is working[ · conversation <i> of <n>]` | dim | always; the suffix where the role holds ≥ 2 sessions |
| `● <text>`; continuation lines indented 2 | green bullet | always |
| `● <tool>(<args>)` | green bullet | [details](#general-page) on |
| thinking | dim italic | details on |
| `● <name>(<about>) started` / `done` | cyan bullet | details on |
| `  ⎿  <line>` (backend output) | dim | details on |
| `● <notice>` | yellow bullet | always |
| `● <question>` | yellow bullet | always |
| `hmz: <why>` (a failed turn) | red | always |
| `hmz: nobody lists a price for <model>[, …], so cost=<n> cannot stop what it spends` | yellow | always, before the first turn of a run whose `cost` limit no agent's price can enforce |
| `✻ Worked for <s>s · <agent>` | dim | always |
| `❯ <task> · by <name>` | | a run another frontend started |
| `<role>'s harness runs here` / `<role>'s harness runs on its environment's machine` / `<role>'s harness runs on the runtime <backend>:<name>` | dim | once per role per run, where the session reports a harness placement (`opened.harness` not empty) |
| `— stopping the flow —` / `— <name> is stopping the flow —` | | this / another frontend stopped the run |
| `hmz: <why>` / `hmz: stopped -- <why>` / `— the flow is done —` | red / yellow / — | run ended refused-failed-crashed / by its budget / normally |

## Status line {#the-status-line}

### Left side {#status-left}

`[btw · <who> ][afk… ][details ]<state>[ · copied]`

| Part | Text | Condition |
| --- | --- | --- |
| btw | `btw · <target>` or `btw · btw agent`, cyan | [btw mode](#btw) on |
| afk | `afk` | away for every role; |
| | `afk <role>, <role>` | away for some roles; yellow |
| details | `details`, muted | details on |
| copied | ` · copied` | for 2.0 s after a [copy](#selecting-and-copying) |

State: the first row that holds.

| # | Condition | Text |
| --- | --- | --- |
| 1 | A run going, no turn open, a *listen* question pending | `·\|· waiting for <you\|name> · ctrl+c twice to stop` (muted, not animated). `you` where some such question is unowned or owned by this frontend; else the first owner's name. |
| 2 | A turn open, or a run going | `<spinner> <names>… (<s>s · ctrl+c twice to stop)`. Spinner `·\|·` `·/·` `·—·` `·\·`, a frame per 0.5 s, cyan. `<names>`: the working agents, comma-separated; with none, the flows running joined by ` ▸ ` (innermost last), else the flow set up. `<s>`: since the oldest open turn began, else since the run began. |
| 3 | Otherwise | `◉ <flow> · <cwd>`, with `$HOME` as `~`. |

### Right side {#status-right}

Hints joined by ` · `, in this order; each only when its condition holds.

| # | Hint | Condition |
| --- | --- | --- |
| 1 | `↑↓ move`, `tab select`, `esc cancel` | The offers list is open. **Nothing else is shown.** |
| 2 | `enter run` | The line starts with `/` and its first word is a command available in this view and not refused now. |
| 2 | `enter ask` · `enter answer` · `enter send` · `enter start` | Some other text: btw on · a question is answerable here · a run is going · otherwise. |
| 3 | `shift+tab switch view` | The round holds more than one view. |
| 4 | `/ commands` | Always. |
| 5 | `shift+enter newline` | Always. |
| 6 | `← monitor` | The editor is empty. |
| 7 | `ctrl+c clear` · `ctrl+c again to stop` · `ctrl+c again to exit` · `ctrl+c stop` · `ctrl+c force stop` · `ctrl+c exit` | What the next [`ctrl+c`](#ctrl-c) does. |

Where the hints are wider than the width left, hints are dropped **from the front** until they
fit or one remains. The left side is never cut.

## Agent and outworlder lines {#agent-lines}

Right-aligned above the editor.

| Line | Format |
| --- | --- |
| Agent (one per agent role) | `<role> · <cli>/<model>:<effort>[ · <account>][ · ●\|○ <n>][ · reading\|unread]`. `<account>` only where not *as local*. `● <n>`/`○ <n>`: sessions held in this or the last run, `●` where one has a turn open. `reading` wins over `unread`. |
| <span id="outworlder-lines"></span>Outworlder (while a run is going) | `<role> · outworlder[ · yours\|<name>'s][ · away][ · asking][ · reading\|unread]` |
| No agent roles | `no agent available` |

### Cost readout {#cost-readout}

Two lines under the agent lines, shown once the run has spent any tokens.

```text
input 12.4k · output 2.1k · cache_read 1.02M+ · cache_write 48.2k+
$1.34 · 91 out/s
```

| Element | Rule |
| --- | --- |
| Line 1 | `<kind> <count>[+]` per kind, joined by ` · `; `<count> tokens` where no kinds are known. |
| Kinds | `input`, `output`, `cache_read`, `cache_write`, `reasoning`, then others alphabetically; every kind any agent of the run reports. |
| `+` on a kind | A floor: some agent's backend does not report that kind, or some tokens were counted without a kind (then every kind carries `+`). |
| Counts | `< 1000`: integer; `< 1 000 000`: `12.4k`; else `1.02M`. |
| Line 2 | `[<money>[+] · ]<rate> out/s` |
| Money | Per model, from the price list. `$1,234` (≥ $100), `$1.34` (≥ $0.01), `$0.0042` (> 0), `$0.00` (0). Omitted where no model is priced; `+` where some are and some are not. |
| Rate | Output tokens per second over the last 300 s, or the run's age if shorter; an ended run is read at its end. |
| Refresh | On any change of counts, whenever an agent does anything, and at least every 5 s. Backend logs are read every 1 s (claude, dsh, codex, mcode, kimi). |

## Input {#input}

A sent line is stripped, [recorded](#history), and dispatched:

| # | Line | Handling |
| --- | --- | --- |
| 1 | not starting with `/`, while [btw](#btw) is on | A side question (`$` lines included). |
| 2 | `$<name>[ <task>]` matching the [grammar](#starting-a-flow-outright), with no question [answerable here](#questions-and-being-away) | [Starts a flow](#starting-a-flow-outright). |
| 3 | not starting with `/` | [Said](#talking-to-a-running-flow): an answer, a line to the run, or the task of a new run. |
| 4 | starting with `/` | A [command](#commands). |

## Commands {#commands}

<span id="slash-commands"></span>

A `/` line is echoed as `❯ /…` and then, in order:

| # | Step | On failure (red) |
| --- | --- | --- |
| 1 | Split at the first space into name and rest; rest split with `shlex.split`. | `hmz: <shlex error>` (e.g. `hmz: No closing quotation`) |
| 2 | Look the name up (case-sensitive). | `hmz: no such command: /<name>` |
| 3 | Check the [view](#views). | `hmz: /<name> is only available on <views>, not on <view>` |
| 4 | Check the state (`refuses`). | `hmz: <why>`; the `ctrl+c` count is reset. |
| 5 | Run it. | |

View names in messages: `the monitor`, `the all-agents transcript`, `one agent's transcript`,
`an outworlder's transcript`, joined `a, b and c`.

<RefFilter label="Filter commands">

| Command | Args | Views | Refused (and unlisted) when | Also unlisted when |
| --- | --- | --- | --- | --- |
| <span id="cmd-flow"></span>`/flow` | `[flow]` | all | never; `[flow]` itself is refused while a run is going | — |
| <span id="cmd-btw"></span>`/btw` | `[question]` | all | nobody to ask (see [btw](#btw)) | — |
| <span id="cmd-epics"></span>`/epics` | — | all | never | — |
| <span id="cmd-resume"></span>`/resume` | — | all | a run going or stopping | the last background look found nothing |
| <span id="cmd-settings"></span>`/settings` | `[page]` | all | never | — |
| <span id="cmd-clear"></span>`/clear` | — | all | never | — |
| <span id="cmd-afk"></span>`/afk` | `[on\|off]` | all but `session` | on an outworlder another frontend holds | — |
| <span id="cmd-claim"></span>`/claim` | `[on\|off]` | `outworlder` | on an outworlder another frontend holds | — |
| <span id="cmd-stop"></span>`/stop` | — | `monitor`, `aggregate` | no run going, or it is stopping | — |
| <span id="cmd-exit"></span>`/exit` | — | all | never | — |

</RefFilter>

Each command's line in the completion list:

| Command | About | Instead, when |
| --- | --- | --- |
| `/flow` | `Choose, set up and install flows` | `Set up the running flow's agents` — a run is going |
| `/btw` | `Ask side questions; press esc or /btw to stop` | `Ask one more; alone, leave btw mode (esc too)` — btw on |
| `/epics` | `View and manage runs in this directory` | |
| `/resume` | `Resume the last run in this directory` | |
| `/settings` | `Every setting: general, accounts, fallback, runtimes, workspace` | |
| `/clear` | `Clear the screen` | |
| `/afk` | `Toggle whether an agent may ask you` | |
| `/claim` | `Answer for this outworlder exclusively; off releases it` | |
| `/stop` | `Stop the flow without confirmation` | |
| `/exit` | `Exit` | `Exit; a running flow can be left running` (daemon) or `Exit; asks before stopping the running flow` (in process) — a run is going |

The completion list shows the commands that are available in the view, not refused and not
unlisted, alphabetically. Availability and about texts are re-evaluated whenever the view, the
run or the question state changes. Arguments beyond those listed are ignored by `/flow`,
`/settings`, `/epics`, `/clear`, `/stop` and `/exit`.

### Refusal messages {#refusals}

Every message is red and prefixed `hmz: `.

| Command | Condition | Message |
| --- | --- | --- |
| any | wrong view | `/<name> is only available on <views>, not on <view>` |
| `/afk`, `/claim` | outworlder held by another | `<role> is <name>'s: cannot say whether it is away` / `… cannot claim it` |
| `/afk`, `/claim` | argument not `on`/`off` | `expected 'on' or 'off', not '<word>'` |
| `/claim off` | not held by this frontend | `<role> is not yours to release` |
| `/stop` | nothing running | `no flow is running` |
| `/stop` | stopping | `the flow is already stopping: it is finishing the turn it was in` |
| `/resume` | a run going | `cannot resume a run while a flow is running: press ctrl+c twice to stop it first` |
| `/resume` | stopping | `cannot resume a run while the flow is still stopping: it is finishing the turn it was in` |
| `/resume` | any argument | `/resume takes no arguments: it resumes the last run here; use /epics to choose another run` |
| `/flow <name>`, `$<name>` | a run going | `cannot choose a flow while one is running` |
| `/settings <page>` | unknown page | `/settings has no page '<page>': choose general, accounts, fallback, runtimes or workspace` |
| `/settings flowverses` | a run going | `the flowverses are on /flow now, which offers them while no flow runs` |
| `/btw` | no agent to ask | `/btw requires a coding agent` |
| `/btw` | the session is gone | `/btw: no conversation found for <role>/<n>` |
| `/btw <q>` | busy | `btw is still answering the last question` |

### `/flow [flow]` {#flow-command}

Opens the [flow menu](#choosing-a-flow) on Installed. With `[flow]` (a name as offered, or a
path), opens inside that flow's roles. While a run is going, opens on the running flow's roles
and offers nothing else. Saving while a run is going says `the current run keeps its original roles;
changes will apply to the next run`.

### `/btw [question]` {#btw-command}

Enters [btw mode](#btw), asking `[question]` if given. In btw mode, `/btw` alone leaves and
`/btw <q>` asks. The question is the `shlex`-split words joined by one space.

### `/epics` {#epics-command}

Opens [`/epics`](#the-runs-that-have-already-happened).

### `/resume` {#resume}

See [`/resume`](#carrying-the-last-one-on-outright).

### `/settings [page]` {#settings-command}

Opens [`/settings`](#what-humanize-remembers) on its landing screen, or inside `[page]`: one of
`general`, `accounts`, `fallback`, `runtimes`, `workspace`, or the aliases `settings` and
`everywhere` (General), `directory` (Workspace) and `environments` (Runtimes);
case-insensitive; only the first word is read. Completion offers the five names, in that
order, not the aliases. `flowverses`, the page that moved, prints `the flowverses are on /flow
now` (dim) and opens [`/flow`](#where-flows-come-from) on Flowverses.

### `/clear` {#clear-command}

Clears the view being read (only), resets its speaker marker, and redraws the opening box.

### `/afk [on|off]` {#afk-command}

Sets away through the host; no argument toggles. On an outworlder's view: that role only.
Elsewhere: every role this frontend may answer for (roles held by others keep their value);
the current state there counts as *on* only when every role is away.

| Result | Message |
| --- | --- |
| outworlder view, on / off | `away as <role>: agents that ask are told nobody is here` / `here as <role>: agents may stop and ask you` |
| elsewhere, on / off | `away: agents that ask are told nobody is here` / `here: an agent may stop and ask you` |

Away is held by the host and outlives this interface. See
[Questions](#questions-and-being-away).

### `/claim [on|off]` {#claim-command}

On an outworlder's view: `on` sends `claim` (`only you can answer for <role>`); `off` sends
`release` (`anyone can answer for <role>`); no argument toggles. Losing a claim prints
`<role> is <yours|<name>'s|anybody's> to answer now`.

### `/stop` {#stop}

Stops the run for every frontend: the turn under way is interrupted and the flow unwinds.
Equivalent to the second [`ctrl+c`](#ctrl-c). Resets the `ctrl+c` count. This frontend prints
`— stopping the flow —`; others print `— <name> is stopping the flow —`. While the run is
stopping, the next `ctrl+c` [forces](#ctrl-c) it.

### `/exit` {#leaving-and-letting-go}

Same as `ctrl+q`.

| State | Effect |
| --- | --- |
| no run going (and none stopping) | Leaves at once. |
| a run stopping, host is a daemon | Leaves at once and sends `force` (closes the run's conversations). |
| a run going | Opens the dialog below. |

```text
A flow is running.

❯ 1. stop the flow and exit
  2. detach and exit              run `hmz` here to reattach

enter choose · esc stay
```

| Row | Effect |
| --- | --- |
| `stop the flow and exit` | In process: closes the host. Daemon: sends `force` (waits up to 10 s), then leaves. Stops the run for every frontend. |
| `detach and exit` (daemon) | Closes btw and the link, and leaves. The run continues; claims are released; away settings remain. `hmz` here reads the run again from the top. |
| `cancel` (in process; replaces `detach and exit`) | Stays. |
| `esc` | Stays. |

## Starting a flow outright (`$`) {#starting-a-flow-outright}

```text
dollar-line = "$" , name , ( ws , task )? ;
name        = segment , { "/" , segment } , [ ":" , ( word-char | "." | "-" )+ ] ;
segment     = letter , { word-char | "." | "-" } ;
```

Regex: `[A-Za-z][\w.-]*(?:/[A-Za-z][\w.-]*)*(?::[\w.-]+)?` at `line[1:]`, followed by
whitespace (a newline included) or the end. The task is the rest, stripped. A line not
matching (`$ ls`, `$5`, `$(pwd)`, `$`) is an ordinary line. Paths are not names: use
`/flow ./path`.

| Condition | Result |
| --- | --- |
| btw on | Asked as a side question. |
| a question is answerable here (aggregate, monitor, or the asking outworlder's view) | Taken as the answer. |
| `<name>` not among the offered flows | `hmz: no such flow: <name>` |
| a run going | `hmz: cannot choose a flow while one is running` |
| the flow is [set up](#set-up) | Chosen; with a task, the run starts. Without a task, `enter a task to start the flow`. |
| not set up | `/flow` opens inside it, holding the task; the run starts when the menu is saved. Leaving without saving: `flow not set up; nothing started` (dim). |

<span id="set-up"></span>A flow is **set up** here when all hold: the remembered agent roles
are exactly the declared agent roles; every required environment role has a remembered
environment; remembered params validate against the flow's `FlowParams`; there is a budget,
unless the flow needs none (`chat`). A flow that fails to load counts as set up (and fails
when run).

Names are those offered by completion: bare for the flows built in and those installed from
`official` (`$chat`), `$local/<flow>`, `$user/<flow>`, `$<flowverse>/<flow>` for one installed
from another flowverse, and `…:<name>` for another flow in the same module.

## Talking to a running flow {#talking-to-a-running-flow}

A line that is not a command, not a `$` flow line and not in btw mode:

| # | Condition | Result |
| --- | --- | --- |
| 1 | a question is [answerable here](#questions-and-being-away) | Sent as its answer. |
| 2 | outworlder view, another frontend holds it | `hmz: <role> is <name>'s to answer, not yours` |
| 3 | outworlder view, nothing asked | `hmz: <role> is not asking anything now; read another transcript to say it to an agent` |
| 4 | a run going or starting | `say` with `to` = the view's key ([routing](/reference/daemon#say-routing)). |
| 5 | otherwise | Starts the flow set up, with the line as its task. `hmz: no coding agent is installed` where a role has no agent; `hmz: a flow is already running` where one is. |

Lines said and not yet taken are **pinned** on the left above the editor:

```text
❯ and fix the tests too · with assistant
❯ then push · by bob@tui
  … 3 more waiting
```

| Rule | |
| --- | --- |
| Order | Lines put into a turn (`given`) first, then queued ones, oldest first. |
| Format | `❯ <first line> · with <agent>` (given) `· by <name>` (another frontend's). Continuations indented 2. Cut with `…` to the width. |
| Limit | 5 lines; then `  … <n> more waiting`, `  … <n> more lines`, or `  … <n> more lines and <m> more waiting`. |
| Delivery | One line per agent at a time, into the turn open in the target conversation; queued otherwise, and taken into the prompt of the next turn to start. A line taken is moved into the transcript (`· by <name>` for another frontend's). |
| Refused mid-turn | The backend's reason in red; the line returns to the head of the queue. Backends that accept a line mid-turn: [Agents › Steering](/reference/agents). |
| Not acknowledged | Echoed, then `   sent to <agent>, which ended its turn without acknowledging it` (`them` for several). Discarded. |
| Run ends | Given lines: echoed + `   sent to the agent, not acknowledged: the flow stopped\|the flow ended`. Queued: echoed + `   never sent: the flow stopped\|the flow ended`. |

## Questions, and being away {#questions-and-being-away}

A question comes from a flow's `Outworlder` role, or from an agent asking its user through a
hook the flow hung. It is shown on the asking outworlder's view and on the aggregate:

```text
● Which region?
      1. north
      2. south
   yours to answer: type an answer, or /afk to stop being asked
```

| Element | Rule |
| --- | --- |
| Options | `      <n>. <option>` (6 spaces). |
| Footer | `   <name>'s to answer` (held by another), else `   [yours to answer: ]type an answer, or /afk to stop being asked`. |
| Answerable here | On the aggregate or monitor: the oldest pending question of any role; on an outworlder view: the oldest of that role. Only questions unowned or owned by this frontend, and not already being answered. None on a `session` view. |
| Answer | The next line typed. A bare number `1‥n` that is not itself an option picks that option (resolved by the host). Echoed as `❯ <text>[ · by <name>]`. |
| Refusals | `hmz: already answered by <name>`, `hmz: <role> is <name>'s`, `hmz: no question <id> is waiting`. |
| Away | While a role is away its questions are answered at once: `""` for text, a schema's defaults, or `OutworlderAway` for a field with none; an agent's question is told nobody answered. A question pending when away is set is withdrawn (the flow sees `OutworlderAway`). |
| End | Pending questions are withdrawn when the run ends, stops, is forced, or the host closes. |

## Side questions (`/btw`) {#btw}

| Aspect | Rule |
| --- | --- |
| Enter | `/btw [question]`. Prints `btw · <target\|btw agent> each line is a question; /btw or esc to exit`. The status line starts `btw · …`. |
| In btw mode | Every line not starting with `/` is one more turn of the same side conversation. |
| Leave | `/btw` alone or `esc`: `btw: exited`; a run starting: `btw: exited -- a new flow started`. Side sessions are closed (`unaside`). |
| Target | A `session` view: that conversation (for a role view, its newest). Any other view: the **btw agent** — the one set on [General](#general-page), else the flow's first declared role with a session, else its configured agent. |
| Session target | First question opens `aside(key, fork=True)`; where the CLI forks, the fork answers. Otherwise, or if the fork answers nothing, a fresh session of the same agent seeded with a snapshot of the run filtered to that role. Ended sessions included. |
| btw agent | Seeded with a snapshot (the last 32 of up to 80 observations, 600 characters each) and the list of sessions. It may reply with lines `@ask <role>/<n>: <question>` (regex `^\s*@ask\s+(\S+?)\s*:\s*(\S.*)$`); each is put to that session's side copy (`btw · asking <key>: <question>`), and answers return as `<answer from="<key>">…</answer>`. At most 4 asks per question; failures return as `(session <k> not found)`, `(could not ask: <e>)`, `(no answer)`. |
| Side sessions | Read-only permission, no goals, no skills, no allowed tools, MCP approval off, none of the flow's hooks. |
| Answer | `●` (cyan) `btw · <question>` (dim), then the answer in cyan, continuation lines indented 2, on the current view. |
| Failures | `hmz: btw is still answering the last question`, `hmz: /btw could not read flow progress: <e>`, `hmz: /btw could not start: <e>`, `hmz: /btw: <why>` (e.g. `the agent returned no answer`). |

## Several frontends {#several-people-on-one-run}

Each `hmz` in a directory is a separate frontend of one [host](/reference/daemon#hosting), with
its own views, monitor and prompt. Names: `HUMANIZE_NAME`, else the login, else `somebody`,
then `@tui`; a duplicate gets `#2`, `#3`, ….

| Aspect | Behaviour |
| --- | --- |
| Claims | [`/claim`](#claim-command) holds an outworlder for this frontend. Others see `<name>'s` beside it (outworlder line, monitor, question footer) and are refused with `hmz: <role> is <name>'s to answer, not yours`. Released on `/claim off` or when the frontend leaves. |
| Unclaimed questions | Any frontend may answer; the first answer wins; later ones get `hmz: already answered by <name>`. |
| Attribution | Lines, answers and runs from another frontend carry ` · by <name>`. |
| Readers | The monitor's `Reading` section lists every frontend where there is more than one. |
| Arriving late | The run is read from its `started` record: what was said, asked and answered, and the current state. |
| Stopping | `/stop`, `ctrl+c` twice and **stop the flow and exit** stop the run for everybody. |

## Keys {#keys}

<RefFilter
  label="Filter keys: try esc, enter, or a screen"
  :chips="['app', 'editor', 'offers', 'every menu', 'forms', '/settings', '/flow', 'dropdown', 'monitor']"
>

| Where | Key | Condition | Action |
| --- | --- | --- | --- |
| app | <span id="key-ctrl-c"></span><kbd>ctrl+c</kbd> | always, including over menus | [State machine](#ctrl-c). |
| app | <kbd>ctrl+q</kbd> | always | [`/exit`](#leaving-and-letting-go). |
| app | <span id="key-tab"></span><kbd>shift+tab</kbd> | the log is the only screen | Next view in the [round](#views). Also over the offers list. |
| app | <kbd>tab</kbd> | the log is the only screen, offers closed | Previous view. |
| app | <span id="key-left"></span><kbd>←</kbd> | the log is the only screen, editor empty, offers closed | Opens the [monitor](#watching-the-run). Otherwise moves the editor's cursor. |
| editor | <span id="key-enter"></span><kbd>enter</kbd> | offers open with a highlight | Takes the offer: replaces the last word, appends a space; does not send. |
| editor | <kbd>enter</kbd> | otherwise | Sends the line (if not blank). |
| editor | <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | | Inserts a newline. |
| editor | <kbd>↑</kbd> / <kbd>↓</kbd> | cursor on the first / last row | Older / newer [history](#history) entry. Otherwise moves the cursor. |
| editor | <kbd>esc</kbd> | btw on, offers closed | Leaves btw mode. |
| editor | <kbd>space</kbd> | monitor up, editor empty | Passed to the monitor. |
| offers | <kbd>↑</kbd> <kbd>↓</kbd> | offers open | Moves the highlight. |
| offers | <kbd>tab</kbd> | offers open | Takes the highlight. |
| offers | <kbd>esc</kbd> | offers open | Hides the offers until the text changes. |
| every menu | <kbd>↑</kbd> <kbd>↓</kbd> | | Previous / next row, wrapping, skipping headings and spacers. Ignored while a row is being written on the params and budget sheets. |
| every menu | <kbd>←</kbd> <kbd>→</kbd> | a sheet | Nothing: no value is stepped with them. |
| every menu | <kbd>enter</kbd> · click | | On `search…`: starts a search. On a `▾` row: drops its values (see dropdown). On a written row: begins writing it; again: keeps it. Otherwise: selects the row. |
| every menu | <kbd>esc</kbd> | | Puts back the row being written; else ends a running search; else leaves (asking [Save?](#save-box) if the menu holds changes). |
| every menu | typing · <kbd>backspace</kbd> | a search is running | Narrows it; the cursor goes to the first match. |
| forms | typing · <kbd>backspace</kbd> · paste | on a written row | Begins writing it; the first character replaces a pre-filled value. Paste keeps the first line only (except `variables`). |
| forms | <kbd>enter</kbd> | writing a row | Keeps it and moves to the next row still unanswered, else to `done`. |
| forms | <kbd>↑</kbd> <kbd>↓</kbd> | writing a row | Keeps it and moves. |
| forms | <kbd>esc</kbd> | writing a row | Puts it back. |
| forms | <kbd>shift+enter</kbd> <kbd>ctrl+j</kbd> | writing `variables` | Newline. |
| /settings | <kbd>enter</kbd> <kbd>→</kbd> · click | landing | Opens the page. |
| /settings | <kbd>esc</kbd> | landing | Leaves, asking [Save?](#save-box) if anything is held. |
| /settings | <kbd>←</kbd> <kbd>backspace</kbd> <kbd>esc</kbd> · click `/settings` | a page, list focused | Back to the landing screen. |
| /settings | <kbd>/</kbd> | a page with search, list focused | Opens the search box. |
| /settings | <kbd>tab</kbd> <kbd>shift+tab</kbd> | | Next / previous of: search box (when shown), list, enabled buttons. |
| /settings | <kbd>enter</kbd> <kbd>↓</kbd> | search box | To the list, keeping the filter. |
| /settings | <kbd>esc</kbd> | search box | Clears and hides it. |
| /settings | <kbd>←</kbd> <kbd>→</kbd> | a button focused | Previous / next enabled button, wrapping. |
| /settings | <kbd>↑</kbd> | a button focused | To the list. |
| /settings | <kbd>enter</kbd> · click | a button | Presses it. |
| /flow | <kbd>enter</kbd> · click | list focused | Goes into the row: a card, a flow's roles (Installed), a flowverse, a flow's releases; on a role, `params` or `budget` opens its sheet; on a release installs it. |
| /flow | <kbd>→</kbd> | list focused, first screen, Installed, Flowverses or one flowverse | As `enter`. |
| /flow | <kbd>←</kbd> <kbd>backspace</kbd> · click a step across the top | list focused | Out to the page above. Not on the roles of a flow `/flow` was opened on. |
| /flow | <kbd>esc</kbd> | list focused | Ends a search; else out to the page above; else leaves, asking [Save?](#save-box) if anything is held. |
| /flow | <kbd>/</kbd> · <kbd>tab</kbd> · buttons | | As on /settings. |
| dropdown | <kbd>↑</kbd> <kbd>↓</kbd> | | Moves. An on/off dropdown opens on the value not in force. |
| dropdown | <kbd>enter</kbd> · click | | Picks the value. |
| dropdown | <kbd>esc</kbd> · click outside | | Picks nothing. |
| monitor | <kbd>↑</kbd> <kbd>↓</kbd> | editor empty, offers closed | Previous / next node, wrapping. |
| monitor | <kbd>enter</kbd> · click | editor empty | [Opens the node](#monitor-nodes). |
| monitor | <kbd>space</kbd> | editor empty | Opens an agent out to its sessions, or shuts it. |
| monitor | <kbd>→</kbd> | editor empty, offers closed | Back to the log last read. |
| monitor | <kbd>ctrl+t</kbd> | always | Graph ↔ list. |
| environment page | <kbd>↑</kbd> <kbd>↓</kbd> <kbd>enter</kbd> · click | | Walk and read its sessions. |
| environment page | <kbd>esc</kbd> | | Back to the monitor. |
| exit dialog | <kbd>enter</kbd> / <kbd>esc</kbd> | | Choose / stay. |
| anywhere | drag · double click · triple click | | [Copies](#selecting-and-copying). |

</RefFilter>

Every menu shows its applicable keys on its bottom row, and only there. `esc` never opens the
monitor and `←` never stops anything.

### ctrl+c {#ctrl-c}

| # | Condition | Effect |
| --- | --- | --- |
| 1 | The prompt in front (the monitor's, if up) has text | Clears it; resets the count. |
| 2 | Otherwise the count becomes `count + 1` if the last press was within 3.0 s, else `1`. | |
| 3 | A run going, count 1 | `— press ctrl+c again to stop the flow —` |
| 4 | A run going, count 2 | Stops the run as [`/stop`](#stop); resets the count. |
| 5 | A run stopping (by anybody) | Any press, no time limit: sends `force`; prints `— closed <n> conversation(s) mid-turn —` where `n > 0`; resets the count. |
| 6 | No run, count 2 | Leaves at once, without the dialog. |
| 7 | No run, count 1 | `— press ctrl+c again to exit —` |

A refused command and `/stop` reset the count.

### Keyboard protocol {#keyboard-protocol}

`shift+enter` reaches the interface only from a terminal speaking the kitty keyboard protocol
(Ghostty, kitty, WezTerm, Alacritty); elsewhere it arrives as `enter`. `ctrl+j` works
everywhere. In iTerm2 without tmux, `hmz` sets `TEXTUAL_DISABLE_KITTY_KEY=1`
([CLI](/reference/cli#terminal-preparation)), so `shift+enter` sends and `ctrl+j` breaks the
line. Textual's escape-sequence length limit is raised to 1 024 characters so that a long
input-method commit arriving as one key report is not typed as raw escape text.

## Menus {#menus}

`/epics` and the sheets `/flow` and `/settings` open are sheets over the log; `/flow` and
`/settings` are screens of their own.

### Anatomy {#menu-anatomy}

<span id="the-menus-and-when-what-they-hold-lands"></span>

```text
  <title>
  <about>
  <page strip, if several>
❯ 1. <label>   <value> <mark>   <about>
  2. …

     <set-apart row>    <about>
  <message under the list>
  <key hints>
```

| Element | Rule |
| --- | --- |
| Marks | `▸` opens something; `▾` drops its values; `✔` (green) the choice in force; `❯` the cursor. |
| Set-apart rows | `search…`, `add …`, `save`, `set`, `done`, `check again`, …: unnumbered, each with a blank line above. Below the list, except on host pickers, where they sit above. |
| Height | At most 14 rows, at least 3. |
| Search | Case-insensitive subsequence of one field. Pick lists: label and about, ordered by how near a field comes (equal, then starts with, then contains, then the subsequence alone), keeping the list's order within each. `/epics`: flow, task, run name. Started from `search…` only; `esc cancel search` ends it. |
| Hints | `enter <verb>` for the row under the cursor (`open`, `choose` on a `▾` row, `change` on a written row of the params or budget sheet, `save`, `set`, `add`, `search`, `refresh`, `copy`, `done`, `type a host`), `esc <verb>`. On a form's written row `type to edit` replaces the enter hint. While writing a row: `[shift+enter/ctrl+j new line · ]enter keep · esc undo`. |

### Held and immediate changes {#held-changes}

| Menu | Held until saved | Applied at once |
| --- | --- | --- |
| `/flow`, roles, agent sheet, params, budget, environment form, unsaved host | the flow, its roles, params, budget and profiling | installing, updating, uninstalling; adding, fetching and removing a flowverse |
| `/settings` Settings, Workspace, Fallback | everything | — |
| `/settings` Accounts | edit settings, remove | add an account, sign in again, add a custom CLI |
| `/settings` Runtimes; `/epics` | — | everything |
| Monitor board | — | everything |

### Save? box {#save-box}

Opened by `esc` out of a menu (or form) holding changes.

```text
Save?
❯ 1. save
  2. discard
enter choose · esc back
```

`save` applies the menu, which may still refuse (the menu then stays, showing why);
`discard` leaves without applying; `esc` returns to the menu.

## `/flow` {#choosing-a-flow}

A screen of its own, drawn and keyed as [`/settings`](#settings-page-layout) is: the way here
across the top (`/flows › Installed › <flow>`), every step of it but the last a click back; the
list in a box with a block cursor; the line under it; a bar of buttons, **Save** at the far end;
the keys. `/flow` opens on **Installed**. What it holds -- the flow and its roles, params, budget
and profiling -- lands together on **Save**; installing, updating, uninstalling, fetching, adding and
removing happen at once.

```text
  /flows › Installed
  Flows ready to run here: pick one to set it up and run it, or install more from a flowverse.

  ╭──────────────────────────────────────────────────────────────────────────────────────────╮
  │ built in                                                                                 │
  │ chat ✔                                                                          built in │
  │   Talks to one agent for as long as you keep answering it.                               │
  │                                                                                          │
  │ mine                                                                                     │
  │ mine/review                                                               0.1.0  ↑ 0.2.0 │
  │   Review the current diff and write the findings to REVIEW.md.                           │
  ╰──────────────────────────────────────────────────────────────────────────────────────────╯

     Install more…       Update       Uninstall       Copy here       Search…         Save

  enter set up   / search   tab actions   esc back
```

| Page | Top line | About |
| --- | --- | --- |
| first screen | `/flows` | `Flows to run, and the flowverses more are installed from.` |
| Installed | `/flows › Installed` | `Flows ready to run here: pick one to set it up and run it, or install more from a flowverse.` |
| roles | `/flows › Installed › <flow>` (only `<flow>` when opened on it) | `Configure each role: an agent (CLI, account, model and effort) or an environment; then what the flow takes and what a run may spend.` |
| Flowverses | `/flows › Flowverses` | `Indexes of flows to install, cloned under ~/.hmz/flowverses. Fetching, adding and removing one happen at once.` |
| a flowverse | `/flows › Flowverses › <verse>` | `Flows <verse> lists, at their newest release. Open one for its others; installing happens at once.` |
| a flow's releases | `/flows › Flowverses › <verse> › <flow>` | `Releases of <flow>, newest first. Pick one to install it, or to switch to it.` |

`● unsaved changes` stands at the right of the top line while the flow or its roles differ from
what is saved. Keys: the `/flow` rows of [Keys](#keys). Leaving with changes asks
[Save?](#save-box). Every git and disk action runs off the event loop, one at a time:
`<installing|uninstalling|fetching|removing> <what>…` under the list while it runs (another is
refused with `wait for <it> to finish`), then the result there and, dim, in the transcript once
the menu closes; an `OSError` or `ValueError` is shown red under the list instead.

### First screen {#flow-first-screen}

Two cards, as `/settings`' landing: **▶ Installed** (`<n> flow(s) · <flow in force|none chosen>`;
`flows ready to run: built in, installed, or your own`) and **⑂ Flowverses** (the indexes by
name, `· ↑ <n> update(s)` where any; `indexes of flows to install, update and add to`). Keys
`enter open   esc close`.

### Installed page {#flow-list}

| Element | Value |
| --- | --- |
| Rows | Every flow there is to run, under headings: `built in` first, then by where it came from (`official`, added flowverses, `local`, `user`). `<name>[ ✔]`, its about under it; at the far end `built in`, or an installed flow's version and, where its index lists a newer one, `↑ <newer>`. `✔` marks the flow in force, where the cursor opens. |
| Empty | `no flows yet`; searching, `no matching flows`. |
| Search | flow name and about. |
| Keys | `enter set up   / search   tab actions   esc back` |

| Button | Does | Enabled |
| --- | --- | --- |
| **Install more…** | Goes to Flowverses. | always |
| **Update** | Installs the newer release of the flow under the cursor. | an update is listed |
| **Uninstall** | Uninstalls it: `<flow> is uninstalled`. Refused while another installed flow needs it. | an installed flow |
| **Copy here** | Copies it, what it imports and its skills into `./.humanize/flows/`: `copied to <path> -- you can edit it, and <name> now points to it`; errors `there is no flow called <x> to copy`, `there is already a flow of your own at <path>`. | not a `local` flow |
| **Search…** · **Save** | | **Save**: something held |

`enter` on a flow loads what is remembered for it (if another flow), asks its
[params](#setting-a-flow-up) if it declares any (also when re-choosing the same flow), then
opens its [roles](#roles-page). A flow that fails to load: `<flow> failed to load[: <first line
of the error>]` (red).

### Roles page {#roles-page}

Opened from Installed, by `/flow <name>` and a `$` line naming a flow not set up, and, while a
run is going, by `/flow` itself. The last three open on it alone: no way back across the top,
`esc` leaves, and params are not asked.

| Row | Value | `enter` opens |
| --- | --- | --- |
| each agent role (declared order) | `<cli>/<model>:<effort>` or `not set`; under it `agent[ · as <account>]` | [agent sheet](#what-each-agent-is) |
| each environment role | the `-e` spec after `<role>=`, or `not set`; under it `environment` | [environment form](#where-each-agent-works) |
| `params` (flows that take any) | the params changed from their defaults, or `defaults` | [params sheet](#setting-a-flow-up) |
| `budget` | `set` or `none`; under it `what a run may spend: <summary>` | [budget sheet](#what-a-run-of-it-may-spend) |
| <span id="profiling-row"></span>`profiling` (straight under `budget`) | `on` or `off`, the flow's remembered value, else off; under it `samples the programs agents start` or `traced only` | nothing: `enter` turns it over; a run started is [profiled](/reference/tracing#profiling-a-run) where it is on |

Button: **Save** (`save the flow and its roles`), which applies flow, roles, params, budget and
profiling together. Keys `enter open   tab actions   esc <back|close>`. Roles filled by the runtime
(`Outworlder`, `LocalEnv`) are not rows. Messages:
`<flow> has no roles to configure; it interacts only with you`, `<flow> failed to load: <e>;
nothing can be configured`.

| Save refusal (yellow) | Cause |
| --- | --- |
| `<role>[, <role>…] is not configured yet` | An agent role lacks a CLI or model, or a required environment role is unset. |
| `this flow requires a budget: set the budget first` | No budget, for a flow other than `chat`. |

### Flowverses page {#where-flows-come-from}

One card per flowverse with a URL (`official`, then added ones alphabetically; `local` and
`user` are not indexes): its name; at the far end `fetched`, `not fetched` or `edited` (tracked
files changed in the clone); under it the URL with credentials removed, `<n> flow(s)` listed,
`<n> installed`, `↑ <n> update(s)`. Search: name and URL. Same store as
[`Hmz().verses`](/reference/sdk#flowverses).

| Button | Rule |
| --- | --- |
| **Add flowverse…** | Form `Add a flowverse` (`A git repository indexing flows: flows/<flow>/<version>/flow.yaml, one manifest per release. …`): `repository` (`a URL, or owner/repo for one on GitHub`), `name` (`flowverse name, or leave blank for the repository name`); `done` `clones its index; install flows from it next`. Refusals: `repository URL is required`; `'<x>' is not a flowverse name: letters, digits, dot, dash and underscore, starting with a letter or a digit`; reserved and taken names. Then `fetching <name>…`, `<name> is fetched`; the cursor goes to it. |
| **Fetch again** (**Fetch** if never fetched) | Fetches the one under the cursor: `<name> is fetched`. Not a clone: `<name> is a directory that is not a clone of anything; remove it and add it again; there is nothing to fetch`. |
| **Remove** | Not for `official`. Asks `Remove <name>?`: `remove` (`its index[ and <n> installed flow(s)]`) or `keep`. Then `<name> was removed`. |
| **Search…** | |

`enter` or `→` on a card opens that flowverse.

### One flowverse {#flowverse-page}

Each flow its index lists, alphabetically: its name, the newest release's description under it,
and at the far end that release, `✔ <v> installed`, or `✔ <installed>  ↑ <newest>`. Under the
list, where nothing is listed: `not fetched yet: press fetch to clone its index`,
`this index lists no flows yet` or `no matching flows`; and where a manifest was skipped,
yellow, `skipped <flow>/<version>: <why>[ and <n> more]`. Search: name and description. Keys
`enter releases   / search   tab actions   esc back`.

| Button | Rule |
| --- | --- |
| **Install `<v>`** · **Update to `<v>`** · **Switch to `<v>`** · **Installed** | For the flow under the cursor at its newest release: installs it and what it needs, `<flow> <v> is installed[, with <dep> <v>, …]`. **Installed** (disabled) where that release is in. |
| **Uninstall** | Where it is installed: `<flow> is uninstalled`. |
| **Fetch again** · **Search…** | As on Flowverses. |

### Releases {#releases-page}

Every release of one flow, newest first: its version; at the far end `prerelease` and
`✔ installed` as they apply; under it `<ref> · <commit[:12]> · <license>[ · needs <dep> <range>…]`.
The cursor opens on the installed release, else the newest. `enter` or the first button
installs the release under the cursor (labelled as above); **Uninstall**; **Search…** (version,
ref). Keys `enter install   / search   tab actions   esc back`.

<span id="default-fill"></span>**Default fill.** An agent role with nothing remembered starts
on the first installed backend that has reported models, serves the role and can open: its
first model, effort `high` where the model takes it, else the model's easiest, else `auto`;
otherwise `not set`.

### Agent sheet {#what-each-agent-is}

```text
  Set up builder
  Configure this agent: select its CLI, account, model, and reasoning effort.

❯ 1. cli         claude ▸                          coding agent CLI to use
  2. account     as local ▸                        account to run as
  3. model       claude-opus-5 ▸                   model to use
  4. effort      high ▾                            reasoning effort

     save                      this agent

  enter open · esc close
```

| Row | Value | Kind | Rule |
| --- | --- | --- | --- |
| `cli` | CLI or `—` | ▸ | [CLI list](#which-cli-and-which-account). Changing it clears account, model, effort and swarm. |
| `account` | name or `as local` | ▸ | [Account list](#account-list). Keeps the model. Needs a CLI: `choose a coding agent first; accounts belong to the CLI`. |
| `model` | model or `—` | ▸ | [Model list](#what-each-agent-runs). Needs a CLI: `choose a coding agent first; models belong to the CLI`. A new model keeps the effort where it takes it, else the hardest, else `—`. |
| `effort` | effort or `—` | ▾ | The model's ladder, hardest first. Needs a model that names its efforts: `choose a model first; efforts belong to the model`. |
| `swarm` | `on`/`off` | ▾ | Only for a model that swarms (Kimi Code): `run turns as a swarm` / `run turns as one agent`. |
| `save` | `this agent` | set apart | Returns the agent into the flow's draft. |

Choosing an account never asked for its models asks it: `checking models for <cli> as <account>…`, then the list or `could not get models for <cli> as <account>[: <why>]` (red).
Permission, skills and required capabilities are the flow's, not rows.

### CLI list {#which-cli-and-which-account}

| Element | Value |
| --- | --- |
| Title | `Select a coding agent` |
| About | `The CLI for this agent. Accounts and models belong to the CLI, so choosing another resets them.` |
| Rows | Alphabetical: `<cli>[ ✔]  <n> model(s)` or `no models reported yet`. Only CLIs installed here whose harness is the one the role names (if any) and that support every capability the role requires. |
| Installable rows | `dsh` or `kimi` whose program is present but whose Python extra is missing, with the install line: `DeepSeek Harness is not installed; run: uv pip install --python <python> '<sdk>' 'python-dotenv>=1.2.3'; then reopen hmz` / `Kimi Code is installed, but the websockets package is not; run: uv pip install --python <python> 'websockets>=15,<18'; then reopen hmz`. |
| Set apart | `search…` |
| Empty | `<role> needs <harness>, <Capabilities>, and no coding agent installed here has that` / `no coding agent installed here can run this agent` |

### Account list {#account-list}

| Element | Value |
| --- | --- |
| Title | `Select the account to run as` |
| About | `Accounts belong to a specific CLI; each CLI has its own sign-ins. Sessions, settings, and skills belong to the CLI regardless of which account it runs as.` |
| Rows | `as local   use the account signed in on this machine` first (dsh: `use credentials and the base URL saved by dsh, or environment variables`), then each account: `<way> · <VARS>`. |
| Set apart | `search…`, `add   an account` |
| Empty | `<cli> has no saved accounts yet` |
| `add` | The [account form](#making-an-account) with the CLI fixed (title `Add a <cli> account`). On success the account is chosen. `<name> was saved, but sign-in failed with exit code <n>` where its login failed. |

An agent whose account has since been removed fails its first turn, naming the account.

### Model list {#what-each-agent-runs}

| Element | Value |
| --- | --- |
| Title | `Select a model for <cli>` |
| About | `The model <cli> uses for this agent's turns, and its reasoning effort. These are the models last reported for this account.` |
| Rows | `<model>[ ✔]  <efforts, hardest first>[ · swarms]` |
| Set apart | `search…`, `check again` |
| Messages | `checking <cli> for models…`; `<cli> has not reported any models[ as <account>] yet; select check again to query them`; `no models found for <cli>`; an error in red. |

A list is fetched: at every start for each installed CLI's own account when never fetched or
older than 7 days; when an account never asked is chosen; on `check again`.

### Environment form {#where-each-agent-works}

| Element | Value |
| --- | --- |
| Title | `Environment for <role>` |
| About | `The machine and working directory for this environment role. Choosing a machine saved on the runtimes page of /settings by name includes its saved working directory.` |
| Opens on | the first row still needed |

| Row | Kind | About / values |
| --- | --- | --- |
| `backend` | ▾ `local` `ssh` `docker` `swarm` `apple-container` | `this machine` / `a machine reached over ssh` / `a container on a docker daemon` / `a container on whichever node of a docker swarm has room` / `an Apple container on this Mac`, beside each on the list too. Starts on the first of `ssh`, `docker`, `swarm`, `apple-container` with a saved runtime, else `local`. Changing it clears host and workdir. |
| `host` (ssh, apple-container) · `daemon` (docker) · `swarm` (swarm) | ▸ | Opens the [host picker](#host-picker). Shows the saved runtime's description, `not saved: connects via ssh as entered`, `not saved in settings`, `choose a saved host, or add one` (ssh), or `none: <backend> on this machine, or choose a saved one` (docker, swarm, apple-container: left empty, it is this machine). Absent for `local`. |
| `workdir` | written | `absolute path on this machine` (local, and apple-container with nothing saved); `leave blank to use saved default: <dir>` (a runtime saved with one); `remote working directory: /path or ~/path under home`. Pre-filled with the runtime's workdir; while unchanged, the spec omits it. |
| `as -e` | written | `full -e spec: typing one sets the rows above` |
| `done` | | `sets <role> to <spec> when the flow is saved`, or `leaves <role> unset`. |

The rows are composed as `-e` spells them: no provider for `local`, nor for docker, swarm or
apple-container left on this machine (`docker/<workdir>`); an ssh host that is no saved runtime in brackets
(`ssh@[<host>]/<workdir>`). The composed spec is read as
[`-e`](/reference/cli#writing-an-environment) reads it and refused in its words (e.g.
`-e 'box=ssh@[somehost]': expected <role>=<backend>[@<provider>][/<workdir>]; /<workdir> may be left off only for a runtime saved with one`
where no workdir is given or saved). Partial answers: `fill in the <host|workdir> as well`,
`specify an environment`. Reachability and size are checked when the run starts.

#### Host picker {#host-picker}

| Element | Value |
| --- | --- |
| Title | `Select the ssh host to use` / `Select the docker host to use` / `Select the docker swarm to use` / `Select the host for Apple containers to use` |
| About | `Saved on the runtimes page of /settings; any host you add here is saved there.` |
| Rows above the list | `add an ssh host` / `add a docker host` / `add a docker swarm` / `add a host for Apple containers` (the [runtime forms](#runtimes), saving at once and returning with it chosen); `unsaved host   type any host ssh can reach` (ssh); `search…` |
| Empty | `no ssh host is saved yet` |

`unsaved host` opens **Unsaved ssh host** (`Connects using your ssh config with no extra
settings. To save a host with a name, go to the runtimes page of /settings.`): one row
`host   [user@]host[:port], or an alias in your ssh config`; `done` `assigns the role to this
host without saving it`, as `ssh@[<host>]`; errors `host is required`, `'<x>' is not a valid
host: cannot contain spaces, slashes or brackets`.

### Params sheet {#setting-a-flow-up}

| Element | Value |
| --- | --- |
| Title | `Set up <flow>` |
| About | `Configure how this flow runs. Options and validation are defined by the flow itself.` |
| Rows | `<n>. <field, padded to 34><value>[ ▾]  <field description>`; a heading per `json_schema_extra={"section": …}`. |
| Set apart | `set   all of the above` |

| Field type | Editing |
| --- | --- |
| `bool` | ▾ `on`/`off`, opening on the value not in force. |
| `Literal[…]` | ▾ in declared order. |
| `int`, `float` | Typed. |
| `str` | Typed. |
| other (list, dict, model, `Enum`, `Optional` with `None`) | Shown as Python `str()`; edited as text; not accepted by `set`. |

<kbd>enter</kbd> on a typed row begins writing it with its whole value selected, drawn
reversed: the first character typed replaces the value and <kbd>backspace</kbd> clears it.
After that, typing goes after what is there; `←` `→` do nothing.

`set` validates with the flow's model; a refusal shows the first error as `<field>: <message>`.
Equivalent on the command line: [`-p`](/reference/cli#writing-params).

### Budget sheet {#what-a-run-of-it-may-spend}

| Element | Value |
| --- | --- |
| Title | `Set budget for <flow>` |
| About | `A run stops at whichever limit it reaches first; at least one limit is required. Leave empty or 0 for no limit.` |

| Row | Kind | Default | About |
| --- | --- | --- | --- |
| `duration` | written | `""` | `maximum run duration: 1h30m, 90s, PT2H; empty for no limit` (read as [`-p budget.duration`](/reference/cli#writing-a-budget); reopens in days, hours, minutes and seconds, e.g. `6h`, `12d`, `1m30s`) |
| `cost` | written | `0.0` | `maximum cost in US dollars, 0 for no limit` |
| `output_tokens` | written | `0` | `maximum output tokens, 0 for no limit` |
| `graceful` | ▾ `on`/`off` | `on` | `finish the current turn when a limit is reached` |

Typed rows are written as on the [params sheet](#setting-a-flow-up): the first character
typed replaces the value.

| Refusal | Cause |
| --- | --- |
| `Value error, set at least one of duration, cost and output_tokens` | nothing set |
| `duration: Value error, '<v>' is not a duration: use seconds, 1h30m, or ISO 8601 like PT1H30M` | unreadable duration |
| `cost: Input should be greater than or equal to 0` | negative |
| `cost: Input should be a valid number, unable to parse string as a number` | empty or not a number |
| `output_tokens: Input should be a valid integer, unable to parse string as an integer` | empty or not an integer |

Row summary: `stops at <duration>, <n> out, <money>[, even mid-turn]` for the limits set, the
duration written as the sheet reopens it (e.g. `stops at 6h, $50.00`; `stops at 12d, $5.00`;
`stops at 1m30s, 12.0k out, $0.50, even mid-turn`); unset: `none set; a run needs one`, or for
`chat` `none needed; runs until you stop it`.

## `/epics` {#the-runs-that-have-already-happened}

| Element | Value |
| --- | --- |
| Title | `Epics` |
| About | `Every run of a flow in this directory, newest first: task, status, and session count.` |
| Rows | `YYYY-MM-DD HH:MM · <flow>`, about `<task (≤ 60 chars)\|no task> · <n> session(s)[ · failed\|stopped\|was left unfinished][ · resumable]`. `resumable`: the flow is resumable now and the run left a journal. A run in progress reads `was left unfinished`. |
| Set apart | `search…` (flow, task, run name) |
| Empty | `no flow has been run in this directory yet` |

`enter` on a run opens it:

| Element | Value |
| --- | --- |
| Title | `<when> · <flow>` |
| About | `<epic directory>` / `It finished\|failed\|stopped\|was left unfinished with <n> agent(s) in <n> session(s).` |
| `resume run` | `resume the flow from this run`. Offered where the flow is resumable now; otherwise `<flow> is not resumable, so this run cannot be resumed`. Refused while a run is going: `a flow is running; press ctrl+c twice to stop it before resuming another`. Otherwise as [`/resume`](#carrying-the-last-one-on-outright) with this run. |
| `export run` | `the entire run as an archive, with its trace`. Writes `./.humanize/<run>.epic.tar.gz` (records, session logs, manifest, and a [trace](/reference/tracing) also written to the run's `traces/`): `exporting <name>…`, then `<path> · <size> · <n> sessions, <n> slices[, <n> programs]`, repeated in the transcript on close. |

## `/resume` {#carrying-the-last-one-on-outright}

Picks up the newest run in this directory of a flow that can be picked up. Runs are scanned
newest first; the scan stops at the first run that is unreadable, was recorded resumable, or
whose flow is resumable now. On success: `resuming <run>: running <flow> from saved state`,
and the run's flow, agents, environments, params, budget, whether it was profiled and task
are used; the budget counts from zero.

| Message (`hmz: `, red) | Condition |
| --- | --- |
| `no flow has been run here, so there is nothing to resume` | no run here |
| `no run here was of a flow that can be resumed, so there is nothing to resume` | the scan found none |
| `<epic> cannot be read, so there is nothing to resume` | unreadable record |
| `<flow> does not support resuming, so <run> cannot be resumed` | the flow is not resumable now |
| `<run> has no saved state to resume: enter a task to start the flow from the beginning` | no journal entry |
| `cannot resume a run while a flow is running: press ctrl+c twice to stop it first` | a run going |
| `cannot resume a run while the flow is still stopping: it is finishing the turn it was in` | a run stopping |

`/resume` is unlisted while refused, and while the last background look found nothing (at
mount, after flowverse fetches, after `/epics` closes, when a run ends). Command-line
equivalent: [`hmz exec --resume`](/reference/cli#picking-a-run-up).

## `/settings` {#what-humanize-remembers}

A screen of five pages, from the broadest scope to the nearest: this machine, the accounts and
what takes over when one fails, where work runs, this directory. Where flows come from is
[`/flow`](#where-flows-come-from).
Storage keys are in [Settings](/reference/settings).

### Landing screen {#settings-landing}

```text
  /settings
  Every setting humanize keeps. What you change is held until you save it.

  ╭──────────────────────────────────────────────────────────────────────────╮
  │ ⚙  General                                      details off · reports on │
  │    this machine: what runs show, the /btw agent, error reports           │
  │──────────────────────────────────────────────────────────────────────────│
  │ ◉  Accounts                                        3 accounts  ● unsaved │
  │    what agents sign in as, under each CLI                                │
  │──────────────────────────────────────────────────────────────────────────│
  │ ↻  Fallback                                                      2 rules │
  │    where a turn goes when its agent fails                                │
  │──────────────────────────────────────────────────────────────────────────│
  │ ▦  Runtimes                                                    1 machine │
  │    ssh hosts, docker daemons, swarms and Apple containers                │
  │──────────────────────────────────────────────────────────────────────────│
  │ ⌂  Workspace                                        work/api · flow rlar │
  │    this directory: its flow, and forgetting it                           │
  ╰──────────────────────────────────────────────────────────────────────────╯
                                                                      Save
  enter open   tab actions   esc close
```

| Card | Summary | `● unsaved` when |
| --- | --- | --- |
| ⚙ General | `details on\|off · reports on\|off\|not set` | details, btw agent or reports changed |
| ◉ Accounts | `<n> account(s)` (named accounts) | an edit or removal held |
| ↻ Fallback | `<n> rule(s)` | rules differ from what is saved |
| ▦ Runtimes | `<n> machine(s)` | never |
| ⌂ Workspace | `<last 2 path parts> · flow <flow\|none>` | forget on |

**Save** is disabled (tooltip `nothing to save yet`) until a page holds a change (`save all
changes`). Hints: `enter open   [tab actions   ]esc close`; `tab actions` only while something
is held. Coming back out of a page puts the cursor on its card.

### Page layout {#settings-page-layout}

| Element | Rule |
| --- | --- |
| Top line | `/settings › <Page>`; `/settings` is clickable (back to landing); `● unsaved changes` at the right while any page holds a change. |
| Intro | Per page, below. |
| List | Rows under headings, which the cursor steps over; scrollable. |
| Buttons | Under the list, in the order below; label = the row's label capitalised; tooltip = its description. |
| Search | `/` or **Search…**: a box above the list, placeholder `type to filter`, filters as typed (case-insensitive subsequence). Letters typed on the list do not search. Cleared on leaving the page. |
| Message | One line under the list; kept, with the cursor row, while another page is read. |
| Focus on open | The list, or the first enabled button where the list has nothing selectable. |
| Hints | List: `enter <choose\|read\|open\|edit>   [/ search   ][tab actions   ]esc back`. Button: `enter <add\|search\|save\|import>   ←/→ move   tab list   esc back`. Search box: `enter to list   esc clear`. |

| Page | Buttons | Search matches |
| --- | --- | --- |
| General, Workspace | Save | — |
| Accounts | Add an account · Add a custom CLI · Search… · Save | account name, CLI, way |
| Fallback | Add fallback rule · Search… · Save | place, rule text |
| Runtimes | Add a runtime… · Import ~/.ssh/config · Search… | name, backend, row text |

**Add a runtime…** drops `ssh host`, `docker host`, `docker swarm` and `apple containers`
(titled `add a runtime`) over the button; picking one opens [its form](#ssh-form), `esc` or a
click off it none.

**Dropdowns.** A `▾` value -- here and on every other menu -- opens a framed list titled with
the row's name, under the value (above it where there is no room), at most 12 visible values:
`<value> ✔  <description>` with `✔` on the value in force. On/off lists open on the value not
in force.

### When saved changes take effect {#settings-effect}

| Setting | Takes effect | Note beside the row while held |
| --- | --- | --- |
| Error reports, Details | at once on save | — |
| /btw agent | next time btw mode is entered | `takes effect on next /btw` |
| Forget | next launch | `takes effect on next launch` |
| Account edit, removal | next agent session (running sessions keep their account) | `from the next agent session` |
| Fallback rules | next failed turn | — |
| Runtimes | at once | — |

Leaving `/settings` writes a dim transcript line per change: first the pages' own (in the
order done, including things done at once, even after a discard), then:

| Change | Line |
| --- | --- |
| Error reports on / off | `error reporting enabled` / `error reporting disabled` |
| Details on / off | `showing details: tool calls, thinking, and backend output` / `showing turn responses only, without details` |
| /btw agent | `/btw will ask <spec\|the flow's first agent> about the whole flow next time you enter btw mode` |
| Forget | `cleared saved settings for this directory; humanize will open without them on next launch` |

### General page {#general-page}

Intro: `How humanize behaves on this machine, in every directory.` Scope: this machine. Rows
in this order, under the heading in the first column.

| Heading | Row | Values (description) | Default | Stored as |
| --- | --- | --- | --- | --- |
| Display | **Details** ▾ `show every tool call and all of the thinking` | `on` (`show tool calls and thinking`), `off` (`show turn responses only`) | off | `details` |
| Agents | **/btw agent** ▾ `the agent /btw uses outside a session` | `the flow's first agent` (`whichever it names first`), the current choice (`chosen`), `another…` (`set one up`: the [agent sheet](#what-each-agent-is) titled `Set up btw agent`) | the flow's first agent | `btw` (`cli[@account]/model:effort`) |
| Privacy | **Error reports** ▾ `send error reports to humanize` | `on` (`send error reports`), `off` (`send nothing`) | not set | `enable_sentry` |
| Privacy | **What is sent** ▸ `what error reports include and exclude` | `enter` writes `Sent: …. Never sent: ….` under the list | — | — |

Once answered, Error reports cannot return to *not set*. Where `HUMANIZE_SENTRY` overrides it,
the page says `HUMANIZE_SENTRY is set, overriding this setting for this run`; the row shows the
saved value.

### Accounts page {#the-accounts-themselves}

Intro: `Each account is a named set of credentials, kept separate from the CLI's own and from
each other. You assign an account to an agent when setting it up. Creating and signing in
happen immediately; other changes take effect when this menu is saved, and apply from an
agent's next session.`

| Element | Rule |
| --- | --- |
| Groups | A muted heading per CLI; accounts alphabetically, then `as local` (`the account signed in on this machine`) where the CLI has an account. |
| Row | `<name>  <way> · <VAR>, <VAR>` (names only), then ` · checking models…`, ` · edited`, ` · will be removed`, ` · from the next agent session` as they apply. |
| Empty | `no accounts yet` |

`enter` on an account opens `<cli>/<name>` (or `<cli> as local`): `Editing and removal take
effect when /settings is saved; signing in happens immediately.`

| Row | Description | Lands |
| --- | --- | --- |
| `edit settings` | `ask the setup questions again` | on save. Secrets start blank (`leave blank to keep current value`). Copies for other CLIs start on. |
| `sign in again` | `run the CLI's sign-in again; takes over the terminal while running` | at once. `<name> uses <way>, which has no command to run; edit its settings instead`; `sign-in for <name> failed with exit code <n>`. |
| `remove` / `cancel removal` | `remove the account and its credentials when /settings is saved` / `will be removed when /settings is saved` | on save |

`as local` offers no rows: `this is <cli> as local: humanize keeps no credentials for it, so
you cannot edit, sign in, or remove it`. Where a failing turn goes is the
[Fallback page](#where-a-turn-goes-when-it-cannot-be-taken)'s, not an account's.

On save the transcript says, per change: `<cli>/<name> and its credentials were removed`,
`<cli>/<name> is updated` (and `<other>/<name> is updated with it`), then once `account
changes take effect from the next agent session`. Each account updated is then asked again,
in the background, what it runs: `<cli> supports <n> models as <name>`, or `could not get
models for <cli> as <name>[: <why>]; retry from the model row of an agent using this
account`.

#### Account form {#making-an-account}

| Opened as | Title | Intro |
| --- | --- | --- |
| Add an account | `Add an account` (`Add a <cli> account` where the CLI is known) | `A saved sign-in for one CLI, kept separate from the CLI's default and other accounts. Secrets are masked and never shown.` |
| edit settings | `Edit <cli>/<name>` | `Edit account settings. Secrets are never displayed, so leave blank to keep current values.` |
| sign in again | `Sign <cli>/<name> in again` | `Required settings for this sign-in method.` |

| Row | Kind | Rule |
| --- | --- | --- |
| `cli` | ▾ | New only, CLI not known. Installed CLIs first. Description: `installed here` / `not installed here yet`. |
| `way` | ▾ | New only. The CLI's [ways in](/reference/providers#the-ways-in), each with its description. |
| `name` | written | `account name`. Pre-filled with the way's name, suffixed `-2`, `-3` where any CLI already has an account of that name; the first key replaces it. |
| one per variable | written; secrets as `•` | The way's question. |
| `variables` | written, secret | `environment variables, as NAME=VALUE, one per line`. Only for a way that asks nothing and runs no login. Multi-line. |
| `also for <cli>` | ▾ on/off | Other CLIs the credentials can run; on where installed (new) or already copied (edit). ` · overwrites <cli>/<name>` where that exists. |
| `done` | | `adds <cli>/<name>` / `updates <cli>/<name> once /settings is saved` / `signs <cli>/<name> in again`, `, running its login in the terminal`, `, for <x>, <y> too`. |

Refusals: `<cli> has no sign-in method named <way>`, `<cli> already has an account named <name>; edit it from its row, or choose a different name`, `<VAR> is required`, `fill in
credentials to sign in`. Notes: `<cli> is not installed; install it to use this account`,
`<cli> is not installed, and this sign-in method requires running its login`.

After adding: transcript `<cli>/<name> saved to <path>`, `<cli>/<name> is signed in` (or
`hmz: sign-in failed with exit code <n>`), `<name> also saved for <x>, <y>`; under the list
`checking available models for <cli> as <name>…`, then `<cli> supports <n> model(s) as <name>`
or (red) `could not get models for <cli> as <name>[: <why>]; retry from the model row of an
agent using this account`.

#### Custom CLI form {#custom-cli}

Title `Add a CLI that speaks ACP`; intro `Any coding agent that supports the Agent Client
Protocol, communicating over stdin and stdout using the command you provide. The protocol does
not configure models or effort, so it runs with its own configuration.`; row `command` (`command
to run the agent, e.g. my-agent --acp`); `done` `saves it as a backend`. Applied at once, named
after the command's first word: `<name> added as a backend`; transcript ``<name> is saved as a
backend: `<command>` starts it``. Refusals: `command is required`, `<x> is already a backend
humanize drives`. See [Agents › A CLI of your own](/reference/agents#a-cli-of-your-own).

### Fallback page {#where-a-turn-goes-when-it-cannot-be-taken}

Intro: `Where a turn falls back when an agent fails, tried in order. An agent is a CLI, an
account and a model. A chain starts only from the agent it is written for. Saved rules apply
from the next failed turn.` Rows: `<place> ✔  <n> retries, <policy>[, up to <for>] · falls back to <a>[, then <b>…]` or `… · no fallback`. Empty: `no fallback rules configured yet`.
Semantics: [Providers](/reference/providers) and [Falling back](/user/settings#fallback).

Rule form: title `Add fallback rule` (or the place when editing); intro `What happens when an
agent cannot take a turn: retry as configured, then fall back to another agent in a new
conversation.`

| Row | Kind | Values | Default |
| --- | --- | --- | --- |
| `fails on` (new only) | ▸ | a place (`—` empty) | — |
| `falls back to` | ▸ | the first place of the chain, or `nowhere` | `nowhere` |
| `then` (one per further place) | ▸ | the next place of the chain (`if that fails too, in a new conversation`) | — |
| `then` (after the last, once the chain has one) | ▸ | `+ add` (`add an agent to try after the ones above`) | — |
| `tries` | ▾ | `none`, `1`, `2`, `3`, `5`, `8`, `13`, `21` | `none` |
| `policy` | ▾ | `none` (`try again at once, with no wait at all`), `constant` (`the same wait every time: 1s, 1s, 1s`), `linear` (`one second longer each time: 1s, 2s, 3s`), `exponential` (`twice as long each time: 1s, 2s, 4s, 8s`), `exponential-jitter` (`exponential, each wait anywhere up to it -- for agents failing at once`), `fibonacci` (`the Fibonacci sequence: 1s, 1s, 2s, 3s, 5s`) | `exponential-jitter` |
| `for` | ▾ | `no limit`, `30s`, `1m`, `5m`, `15m`, `60m` | `no limit` |
| `remove` (edit) | | `removes this fallback rule when saved` | |
| `done` | | `applies this fallback rule when /settings is saved` | |

Place picker: `Select the agent that fails` / `Select the fallback agent for <place>`; `Here an
agent is a CLI, an account and a model: what a turn can fail on. Search by any of the three.`
Rows `<cli>[@<account>]/<model>` (each CLI here × each account × each model), `nowhere` first
for a fallback (never the failing place); `<cli>[@<account>]/…  models not reported yet; select
to query them` for an account not yet asked. On a row of the chain, `nowhere` takes that place
off it, and a place already further along the chain swaps with the one there (how the chain is
reordered).

Refusals: `select the agent that fails`, `an agent cannot fall back to itself`, `an agent can
be on the chain only once`, `choose a fallback agent or set retries`. A place with a rule already pre-fills it: `<place> already has
a fallback rule; done will update it`. Transcript on save: `<place> <rule>` or `<place> has no
fallback`.

### Runtimes page {#runtimes}

Intro: `Saved ssh hosts, docker daemons with the resources each may hand out, docker swarms
with what their tasks may reserve, and this Mac's Apple containers, used by name as flow
environments in -e and /flow. Changes take effect immediately.` Rows under `ssh`, `docker`,
`swarm` and `apple-container` headings.
Empty: `no machines saved yet; a role can still name one directly`. `/settings environments`,
the page's former name, still opens it. Storage and semantics: [Machines ›
Runtimes](/reference/machines#runtimes).

| Row description | Format |
| --- | --- |
| ssh | `user@host[:port]` or `from ~/.ssh/config` / `…, from <config>`, then ` · key <path>`, ` · through <jump>`, ` · -o K=V, …` |
| docker | `<endpoint> · <image> · OCI runtime <r> · <cpus> CPUs, <mem>, GPUs <ids>\|no limits · max <n> containers` |
| swarm | `<endpoint> · <image> · on <constraint>, … · <cpus> CPUs, <mem>\|no limits · GPUs as <resource> · max <n> tasks` -- not its nodes |
| all | ` · working directory: <dir>`; ` · checking…` while checked |

`enter` on a runtime opens `<backend>/<name>`:

| Row | Description | Effect |
| --- | --- | --- |
| `edit` | `edit saved settings` | Its form, without `name`; checked after saving (`<backend>/<name> updated`). |
| `check` | ssh: `check host resources: home directory, CPUs, memory, and GPUs`; docker: `check daemon resources against its limits`; swarm: `check the swarm's nodes against its quota` | 30 s timeout: `checking <backend>/<name>…`, then `<backend>/<name> answers: …` -- for a swarm `answers: swarm <version>; <n> nodes: <a>, <b>, … and <k> more; <cpus> CPUs, <mem> all told`, naming the first 8 of the nodes that may take a task; for a docker daemon whose listed GPUs do not all answer, a yellow `<n> of <m> GPUs answer; GPU <ids> does not` / `do not`; a yellow `lacks configured resources: …`, or red `… could not be reached: …` / `… could not be checked: …`. |
| `remove` | `remove this host immediately` | At once: `<backend>/<name> removed`; yellow `<names> reached docker through this host; edit them`, and `<names> reached a swarm through this host; edit them` for a swarm whose endpoint or one of whose nodes it was. |

#### ssh host form {#ssh-form}

Title `Add an ssh host` / `Edit ssh/<name>`; intro `A machine where flow environments run.
Connects using your ssh config plus settings configured here. Keys are specified by path and
never read.`

| Row | Description |
| --- | --- |
| `alias` (edit, imported) | `the Host entry in <config>` |
| `host` | `hostname, IP address, or user@host:port` (imported: `override host; leave blank to use the config`). On keep, `user@` and a numeric `:port` fill blank `user` and `port`. |
| `name` (add) | `name used in -e and /flow`. Follows the host until typed: its first dotted label (an IP whole), characters outside `[A-Za-z0-9._-]` as `-`, leading `._-` stripped, `ssh` if empty, `-2`… to avoid saved names. |
| `user` | `username; leave blank to use your ssh config` |
| `port` | `leave blank to use your ssh config, or 22` |
| `identity file` | `path to private key` |
| `proxy jump` | `jump host to connect through, if any` |
| `options` | `additional ssh options: KEYWORD=VALUE, …` |
| `workdir` | `default working directory when -e specifies none: /abs or ~/path` |
| `falls back to` | `runtimes to try in order if this one cannot: docker:box, ssh:gpu2`. Entries apart by commas, saved as the runtime's [`fallback`](/reference/machines#falling-back); its row then ends `· falls back to <entries>`. |
| `harness runs on` | `where an agent's harness runs, in order, the next only when one has no room: self, local, ssh:<name>, docker:<name>; blank for its CLI here, else local`. The runtime's [`affinity`](/reference/remote-execution#affinity), entries apart by commas. |
| `done` | `adds ssh/<name>, and checks its resources` / `updates …` |

Refusals: `an ssh host named <name> already exists; edit it from its row, or choose a
different name`, `port: '<x>' must be a number`, `options: '<x>' is not KEYWORD=VALUE`, and a
[fallback or affinity refused](/reference/machines#validation).

#### docker host form {#docker-form}

Title `Add a docker host` / `Edit docker/<name>`; intro `A docker daemon where flow
environments run in containers: on this machine, over ssh, or at an address. Flows running on
it are limited to the resources configured here.`

| `endpoint` ▾ | Description | Extra rows | Saved as | Default name |
| --- | --- | --- | --- | --- |
| `local` | `the default docker daemon on this machine` | — | `local` | `local` |
| `socket` | `a daemon's unix socket on this machine` | `socket` (`socket path: /run/docker.sock`) | `unix://…` | `docker` |
| `tcp` | `a daemon listening at an address` | `address` (`host:port to connect to`), `tls` (`directory containing ca.pem, cert.pem and key.pem; blank for none`) | `tcp://…` | address's first label |
| `saved ssh host` | `the daemon on a saved ssh host` | `on` ▸ (host picker) | `ssh:<name>` | the host's name |
| `ssh address` | `the daemon on any host via ssh` | `address` (`[user@]host[:port]`) | `ssh://…` | address's first label |
| `context` | `an existing docker context` | `context` (`docker context name`) | `context:<name>` | the context |

Then `name` (add), `image` (`default image, unless specified by the flow`), `OCI runtime` (`e.g.
nvidia; blank for daemon default`), `run args` (`extra arguments for docker run`), `max
containers` (`max concurrent containers; blank for no limit`), `workdir` (`default working
directory when -e specifies no directory`), `falls back to` (as on the [ssh host
form](#ssh-form)), `harness runs on` (likewise), `cpus` (`max CPUs; blank to use all host CPUs`),
`memory` (`e.g. 64G; blank to use all host memory`), `gpus` (`GPU IDs, e.g. 0, 1; blank to use
all host GPUs`), `detect` (`detect host resources and fill them in`: `detecting resources on <endpoint>…`, then `detected …: auto-filled` with the cursor on `cpus` -- `gpus` written with only those that answer, and a yellow `<n> of <m> GPUs answer; …` where one does not -- or red `the daemon did
not respond: …`), `done` (`adds docker/<name> and detects host resources`).

Refusals: `a docker host named <name> already exists; …`, `memory: '<x>' must be a number and
unit, such as 64G or 512M`, `cpus: '<x>' is not a number`, `max containers: '<x>' must be a
number`, `run args: …`, `tls: home directory does not exist for '<x>'`, and an
[affinity refused](/reference/machines#validation).

#### docker swarm form {#swarm-form}

Title `Add a docker swarm` / `Edit swarm/<name>`; intro `A docker swarm where flow environments
run as services of one task, placed on whichever node has room. Reached through a manager's
daemon: on this machine, over ssh, or at an address. Flows on it are limited to the quota
configured here.`

`endpoint` and the rows under it are the [docker host form](#docker-form)'s, a manager's
daemon in place of a docker host's -- `local` being the swarm this machine manages -- and so is
the default name, `swarm` where a docker host's is `docker`. Then `name` (add), `image`
(`default image, unless specified by the flow; every node pulls it`), `run args` (`extra
arguments for docker service create`), `constraints` (`placement constraints, e.g.
node.labels.gpu==true, …`, a comma apart), `max tasks` (`max concurrent tasks; blank for no
limit`), `nodes` (`HOSTNAME=SSH-HOST, …; blank to reach each at ssh://its address`: a node's
host name and the saved ssh host, or the `[user@]host[:port]`, that reaches it), `workdir`
(`default working directory, on every node, when -e specifies none`), `falls back to` (as
on the ssh form), `gpu resource`
(`generic resource nodes advertise GPUs as, e.g. NVIDIA-GPU`), `cpus` (`CPUs all tasks may
reserve; blank for no quota`), `memory` (`e.g. 64G for all tasks; blank for no quota`),
`detect` (as the docker host form's, writing in the CPUs and memory of the nodes that may take
a task all told), `done` (`adds swarm/<name> and checks its nodes`). No `OCI runtime` and no
`gpus`: a service is told neither.

Refusals: `a docker swarm named <name> already exists; …`, `max tasks: '<x>' must be a number`,
`nodes: '<x>' is not HOSTNAME=SSH-HOST`, the store's own for a constraint that is not
`<attribute>==<value>` or `<attribute>!=<value>`, a node's ssh host that is neither saved nor
`[user@]host[:port]`, and a generic resource that is not one; and the docker host form's for
memory, CPUs, run args and TLS.

#### Apple containers form {#apple-container-form}

Title `Add a host for Apple containers` / `Edit apple-container/<name>`; intro `This Mac,
where flow environments run in Linux containers of Apple's container, each a small virtual
machine of its own. Flows running on it are limited to the resources configured here.`

The [docker host form](#docker-form)'s rows less `endpoint`, `OCI runtime` and `gpus`: `name`
(add; `local` unless taken), `harness runs on`, `image`, `run args` (`extra arguments for
container run`), `max containers`, `workdir`, `falls back to`, `cpus` (`max CPUs; blank to use
all of this Mac's`), `memory` (`e.g. 16G; blank to use all of this Mac's`), `detect` (`detect
this Mac's resources and fill them in`: `detecting resources on this Mac…`, then `detected …:
auto-filled` with the cursor on `cpus`, or red `Apple's container did not respond: …`),
`done` (`adds apple-container/<name> and detects host resources`). Refusals: `a host for
Apple containers named <name> already exists; …`, and the docker host form's for memory,
CPUs, max containers and run args.

#### Import form {#import-form}

Title `Import ssh hosts`; intro `Hosts from an ssh config, as read by ssh. Each is saved under
its Host name and continues reading the config, which is never modified.` Row `from` (`the ssh
config to read: default, or another file`, pre-filled `~/.ssh/config`), then an on/off row per
`Host` as `ssh -G` resolves it (`user@host:port · key … · through …`). A host starts **off**
with the reason: `invalid host name`, `<alias> already uses the name <name>`, `a manually added
host is already saved as <name>`, `already imported` (on re-imports it). `done`: `imports
nothing until a host is selected` / `imports <a>, <b>` / `imports <n> hosts`. Refusals: `the
config is still being read`, `select at least one host to import`, `<config>: <error>`. Result:
`imported <names> from <config>[; left <a>, <b>]. Open a host to check it.` Imported hosts are
not checked.

### Workspace page {#workspace-page}

Intro: `What <last 2 path parts> remembers: the flow it opens on and how it was last
configured.` Scope: `workspaces.<resolved cwd>`. Rows in this order, under the heading in the
first column.

| Heading | Row | Value | Kind |
| --- | --- | --- | --- |
| Flow | **Default flow** `configured with <n> agent(s); chosen with /flow` | the flow, or `none` | read-only |
| Reset | **Forget** `clear saved settings here, across <n> flow(s)` | `on` (`clear saved settings here`), `off` (`keep them`); starts off | ▾; on save deletes this directory's entry |

### First start {#first-start}

Where neither `HUMANIZE_SENTRY` nor `settings.yaml` answers reporting:

```text
Report errors to humanize?
Send error reports to help fix bugs. Sent: <…>. Never sent: <…>. You can change this later in /settings.
❯ 1. yes
  2. no
enter choose · esc ask again next time
```

Sent: the error and where in humanize it occurred; which flow was running, and what each agent
was configured to run; which coding agents are installed, and account names; which skills and
flowverses are active, by name; what humanize did that you undid, refused, or canceled; the
version of humanize, of Python, and the operating system and architecture. Never sent: nothing
you typed (no task, prompt, or command); no agent output, and nothing from any transcript or
session log; no files, directory names, or paths outside humanize itself; no keys, tokens, or
account credentials, not even environment variable names.

Answering writes `enable_sentry` and says `error reporting enabled; use /settings to turn it
off` or `error reporting disabled; use /settings to turn it on`. `esc` leaves it unanswered.

## Monitor {#watching-the-run}

A screen over the log's prompt showing the run as a graph or a list. Reached by `←` with the
editor empty, the offers closed and no menu up; never refused; never reached by `esc` or a
command. `→` (editor empty) returns to the view last read; picking a node returns to that
node's view. Commands work from its prompt as on the aggregate (view kind `monitor`), so
`/claim` is refused there. `tab`/`shift+tab` do nothing on it. The cursor opens on
`▣ all agents`. Redrawn every 0.5 s; when a run ends, every clock stops at its end.

```text
   graph  list
❯ ▣ all agents · 1 of 2 working · 17 turns · 7m11s · reading
  ◉ human · outworlder: messages from the flow to you · yours
  ┌──────────────────────────────────────────────────────────────────────┐
  │ ▸ ● builder                                                      43s │
  │ claude/claude-opus-5:high · 12 turns · 48.2k tokens                  │
  │ ▤ repo docker                                                        │
  └──────────────────────────────────────────────────────────────────────┘
    ├╴◆ read the tests
    └╴◇ find the flaky one
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
Set:              max                               20

Tokens:           claude-opus-5                48.2k     $1.34   91 out/s
                  gpt-5.6-sol                   9.1k             12 out/s
Kinds:            input                         1.2k
                  output                         980
                  cache_read                   46.0k
                  cache_write                   9.1k
────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────
  ▣ monitor · graph        ↑↓ node · enter open · → back · ctrl+t list
```

### Nodes {#monitor-nodes}

In order: the all-agents node, outworlder nodes, the graph or list, the board.

| Node | Format | `enter` / click |
| --- | --- | --- |
| all agents | `▣ all agents · <w> of <n> working · <t> turn(s) · <clock>[ · reading]`; `<n>` agents drawn, `<t>` all their turns, `<clock>` the run's age | reads the aggregate |
| outworlder | `◉ <role> · outworlder: messages from the flow to you[ · yours\|<name>'s][ · reading]`; declared order, then order first asked | reads its view |
| agent box | see [Graph](#monitor-graph) | reads the role's view |
| session | see Graph | reads `<role>/<n>` |
| environment | `▤ <role> · <kind> · <target> · <workdir>` | opens its [page](#an-environment-s-page) |
| board line | `◈ <name> <value>[ · flow's\|user's]` | edits it; refused for a `flow` line: `<key> can only be changed by the flow` |
| `+ add entry` | | adds a board line |

Clocks: `<n>s` under a minute, `<m>m<ss>s` under an hour, else `<h>h<mm>m`. Token counts as in
the [cost readout](#cost-readout).

### Graph {#monitor-graph}

| Element | Rule |
| --- | --- |
| Boxes | One per agent role that is working or has taken a turn, in the flow's declared order (others after, as first seen). Width `max(24, min(72, width − 8))`. |
| Box line 1 | `▸\|▾ ●\|○ <role>`; right: the open turn's clock (earliest where several), or `idle <since last turn>`. `▸` shut, `▾` opened, `●` working. |
| Box line 2 | `<cli>/<model>:<effort> · <n> turn(s)[ · <n> sessions][ · <k> tokens]`; right: `reading` or `unread`. Left part cut with `…`. |
| Box line 3 | `▤ <role> <kind>[ · …]`: the environments of its sessions that have taken a turn. |
| Handovers | Above each box but the first: `│   ↓ <d> · ↑ <u>` (zero sides omitted), or `┆` where none happened. Highlighted where the run's latest handover was. A handover is a turn starting on another agent than the one that last ended. |
| Sub-agents | Under a shut box, or under each session of an opened one: `├╴◆ <about>` (running), `├╴◇ <about>` (done), `└╴` last; the first 4, then `└╴◇ and <n> more`. |
| Sessions (opened agent) | `├╴●\|○ session <n> · <t> turn(s) · <k> tokens`, right `[reading · \|unread · ]<clock>`; `reading` also while the agent's view is read. None: `└╴no session has said which it is`. |
| Environments (opened agent) | Under each session: `│   ▤ <role> · <kind> · <target> · <workdir>`. |
| Nothing yet | `no agent has taken a turn yet; agents appear as they take turns` |

### List {#monitor-list}

`ctrl+t` or a click on `graph`/`list` switches; the choice and the opened agents persist for
the process, not across launches.

| Element | Rule |
| --- | --- |
| Header | `node`, `runs · where`, `turns`, `time`, `tokens` |
| Rows | Every agent (`▸\|▾ ●\|○ <role>[ reading\|unread]`, spec, turns, clock, tokens); under each opened agent its sessions (`<role> · session <n>`, spec, turns, clock, tokens); then every environment once (`▤ <role>`, `<kind> · <target> · <workdir>`, `<n> session(s)`, no time or tokens). |
| Order | Working rows first (stable), the rest in the order above. |
| Absent | Handovers, sub-agents, `Also`. |

### Sections {#monitor-sections}

Label `<Field>:` padded to 18; groups separated by a blank line: (`Flow`, `Agents`, `Set`,
`Reading`), (`Also`), (`Tokens`, `Kinds`), then the last line.

| Section | Content |
| --- | --- |
| `Flow` | Each flow call running: its name as offered, `   <s>s`; nested calls indented 2 per level with `▸ `. No calls: the flow's name. |
| `Agents` | Only before any box: `<role> · <cli>/<model>:<effort>[ · <account>]` per role. |
| `Set` | Params not at their default: name padded to 34, value. |
| `Reading` | Where more than one frontend: `<name> · you` first, then the others. |
| `Also` | Graph only: handovers between non-adjacent boxes, `<a> → <b> · ×<n>`. |
| `Tokens` | Per model, in the order each was first spent on (a model spent on later is added below; rows never swap): name (26), tokens (8), money (10, blank where unpriced), `   <n> out/s`. Nothing yet: `no tokens used yet`. |
| `Kinds` | Per kind (fixed order, as the readout): name (26), tokens (8), `+` for a floor; then `+ is a minimum: not all agents report this kind` where any `+`. |
| last line | The first line of whatever the interface last showed (command answers, errors, `— the flow is done —`, board saves). |

### Monitor keys and mouse {#monitor-keys}

| Input | Condition | Effect |
| --- | --- | --- |
| `↑` `↓` | editor empty, offers closed | Previous / next node, wrapping. The cursor follows its node across redraws. |
| `enter` | editor empty | Opens the node (table above). |
| `space` | editor empty | On an agent: opens/shuts it. On its session or environment: shuts the agent and moves to it. Elsewhere: nothing. |
| `→` | editor empty, offers closed | Back to the log. |
| `ctrl+t` | always | Graph ↔ list. |
| `ctrl+c` | text typed | Clears it. |
| click | a non-agent node | As `enter`. |
| click | an agent, on its first 8 columns (gutter, `▸`, `●`), or an agent already under the cursor | Opens/shuts it. |
| click | an agent elsewhere | Moves the cursor. |
| double click | an agent | Reads it. |
| click | `graph` / `list` | Switches. |

Status line: `▣ monitor · graph|list`; right side `enter send · ctrl+c clear` while typing,
else `↑↓ node[ · space sessions| · space shut] · enter open · → back · ctrl+t <other> · /
commands`, dropped from the **end** to fit.

### Environment page {#an-environment-s-page}

Title: the environment's role (or kind). About: `An environment of the run: where its sessions
work.` Redrawn every 0.5 s. Keys: `enter read session · esc back`. Gone from the run: `This
environment is not in the run.`

| Row | Value |
| --- | --- |
| `kind` | `LOCAL`, `SSH`, `DOCKER` |
| `target` | the ssh host or docker runtime, or `this machine` |
| `workdir` | as the run reported it |
| `set up as` | the role's `-e` spelling |
| `image` | the image the flow declares for the role |
| `grants` | the role's environment capabilities (class names without `EnvMixin`), or `nothing beyond running in it` |
| `needs` | `<n> CPUs · <x> GiB memory · <n> GPU(s) · <x> GiB per GPU` (declared parts only) |
| `harness` | `<placement>: <where>`, the placement being each session's [`opened.harness`](/reference/daemon#history-records). `<where>`: `local` (with an anchored environment) `on this machine; what it runs lands here`; `local` (no anchor) `on this machine, in this workdir`; `self` `on this environment's machine, with the CLI installed there`; `<backend>:<name>` `on a runtime of its own, reaching this environment through the anchor`. Where its sessions went different ways: `<placement> for <key>, <key> · <placement> for <key>`. |
| `status` | `<w> of <n> session(s) working` |
| `Sessions` | `●\|○ <role> · session <n> · <spec>` (or the bare key before its first turn); `enter` or a click reads it and leaves the monitor. |

Empty rows are omitted.

### Board {#the-board}

Drawn only where the run keeps a board: a blank row, `Board · shared by you and the flow`, one
`◈` row per line, `+ add entry`. Owners: `both` (no suffix), `user`, `flow` (read-only here).
The entry sheet (`Board entry` or the key; `Shared by you and the flow. Neither waits for the
other.`) asks `name` then `value`. Messages: `<name> saved to the board`, `<name> removed from
the board` (saved empty), `nothing was entered, so nothing was saved`, `a board entry needs a
name`, `<name> can only be changed by the flow`. Changes are sent at once. See
[The mission board](/user/board).

## Completion {#completion}

| Typed (cursor at the end) | Offered |
| --- | --- |
| `/<partial>` (one word) | Commands available now, alphabetically, whose name starts with it. |
| `/flow <partial>` | Flow names (no run going). |
| `/settings <partial>` | The five page names, in page order. |
| `$<partial>` (one word) | `$<flow>` for every flow (no run going); the flow list is cached 2 s. |
| three or more words | Nothing. |

| Rule | |
| --- | --- |
| Row | `<offer> <takes>` padded to 19, then the about text dimmed. |
| Exact word | A word already equal to an offer is offered nothing. |
| Hint row | Where nothing is offered and the first word is an available command: one unselectable row `/<name> <takes>  <about>`. `enter` still sends. |
| Suppressed | Cursor not at the end; line reached by walking history (until a non-arrow key); a `$` line while a question is answerable; after `esc` until the text changes. |
| Taking | Replaces the last word and appends a space. |

## History {#history}

`$HUMANIZE_HOME/history.jsonl`, one JSON object per line: `{"at", "workdir", "text"}`. Every
sent line is appended (tasks, lines to agents, answers, commands, btw questions); blank lines
and a line equal to the previous are skipped. No size limit. At start, if any entry's `workdir`
equals the resolved working directory, `↑`/`↓` walk only this directory's entries, otherwise
every entry. Walking off the newest end restores the draft.

## Selecting and copying {#selecting-and-copying}

| Gesture | Copies |
| --- | --- |
| drag | From press to release, across lines, on release. |
| double click | The word under the pointer, bounded by spaces. |
| triple click | The whole logical line, however many rows it wraps over. |
| `shift` + drag | The terminal's own selection. |

Copies are the text as written (unwrapped, unpadded), through OSC 52 (over ssh, to the local
clipboard; tmux needs `set-clipboard on`). The editor and menu lists select for themselves; a
click in a list is still a choice. A selection is dropped when its view is cleared or switched
and when the width changes. The status line says `· copied` for 2 s.

## What it remembers {#what-it-remembers}

`$HUMANIZE_HOME/settings.yaml`. Full schema: [Settings](/reference/settings).

| Key | Scope | Written by |
| --- | --- | --- |
| `enable_sentry` | machine | Error reports, the first-start question |
| `details` | machine | Details |
| `btw` | machine | /btw agent |
| `workspaces.<dir>.flow` | directory | saving `/flow` |
| `workspaces.<dir>.flows.<flow>.{agents, envs, params, budget, profile}` | directory, per flow | saving `/flow` |

`<flow>` is the name the flow is offered under (`chat`, `local/<f>`, `user/<f>`,
`<flowverse>/<f>`), so two flows with one bare name never share a setup. Roles are keyed by
their declared names. Params are read back through the flow's `FlowParams`. Away, claims, the
monitor's graph/list choice are not persisted.

## Colours {#colours}

The `terminal` theme: every surface is the terminal's default background; primary blue,
secondary cyan, accent bright black, warning yellow, error red, success green; the cursor blue
on bright white. `TEXTUAL_THEME` naming an available Textual theme replaces it; an unknown
name is ignored. The terminal is never queried for its colours. `NO_COLOR` is honoured by
Textual.

## Environment variables {#environment-variables}

| Variable | Effect |
| --- | --- |
| `HUMANIZE_HOME` | Location of `settings.yaml`, `history.jsonl`, `prices.json`, and everything else. |
| `HUMANIZE_DAEMON` | `off`/`0`/`no`: [runs held in process](/reference/cli#where-runs-are-held). |
| `HUMANIZE_NAME` | This frontend's name before `@tui`. |
| `HUMANIZE_SENTRY` | `on`/`1`/`true`/`yes` or `off`/`0`/`false`/`no`: answers reporting for this process. |
| `HUMANIZE_PRICES` | Price source URL or path; `""`, `off`, `0`, `no`, `none`: none. |
| `TEXTUAL_THEME` | Theme. |
| `NO_COLOR` | No colour. |
| `TMUX`, `TERM_PROGRAM`, `LC_TERMINAL` | [Keyboard protocol](#keyboard-protocol). |

## Timings {#timings}

| Constant | Value |
| --- | --- |
| Status line and monitor redraw | 0.5 s |
| `ctrl+c` double-press window | 3.0 s |
| `· copied` | 2.0 s |
| Cost readout recompute | ≤ 5 s; rate window 300 s |
| Backend log polling | 1.0 s |
| Model list considered stale | 7 days |
| Price list refresh | older than 24 h, ≤ 1 try/hour, 20 s timeout |
| Environment check | 30 s |
| Exit dialog `force` | waits ≤ 10 s |
| Transcripts kept | 32 × 2 000 lines |
| Pinned lines | 5 |
| btw asks per question | 4 |
