<script setup>
import SignInWays from '../.vitepress/theme/components/user-places/SignInWays.vue'
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const screen = (lines, mode) => [
  ...lines,
  '',
  { r: '[m]actor · claude/claude-opus-5:high · ○ 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high[/]' },
  { r: '[m]input 38.1k · output 4.2k · cache_read 612.0k · cache_write 29.4k[/]' },
  { r: '[m]$1.87 · 21 out/s[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: `${mode}[c]·|·[/] rlar… [m](252s · ctrl+c twice to stop)[/]`,
    keys: '/ commands · shift+enter newline · esc monitor · ctrl+c stop',
    hl: mode !== '',
  },
]

const notice = [
  {
    label: 'notice',
    lines: [
      '[y]●[/] [dim]claude is rate-limited (this account has spent its quota; another one, or a wait, is what answers it); carrying on as work[/]',
    ],
  },
]

const turn = [
  {
    label: 'details off',
    lines: screen(
      [
        '[dim]── actor[/]',
        '',
        '[dim]● actor is working[/]',
        '',
        '[g]●[/] The three failing tests pass now. The retry in charge() ran before the lock was taken, so a second charge could slip in between.',
        '',
        '[dim]✻ Worked for 74s · actor[/]',
      ],
      '',
    ),
    caption: 'The default: who is working, what each turn said, and how long it took.',
  },
  {
    label: 'details on',
    lines: screen(
      [
        '[dim]── actor[/]',
        '',
        '[dim]● actor is working[/]',
        '',
        '[g]●[/] Read[dim](tests/test_pay.py)[/]',
        '[g]●[/] Grep[dim](def charge)[/]',
        '[g]●[/] Read[dim](src/pay.py)[/]',
        '',
        '[dim i]The retry runs before the lock is taken. A second call can get in there.[/]',
        '',
        '[g]●[/] Edit[dim](src/pay.py)[/]',
        '[g]●[/] Bash[dim](pytest -q tests/test_pay.py)[/]',
        '',
        '[g]●[/] The three failing tests pass now. The retry in charge() ran before the lock was taken, so a second charge could slip in between.',
        '',
        '[dim]✻ Worked for 74s · actor[/]',
      ],
      '[m]details[/] · ',
    ),
    caption:
      'Every tool call and every line of thinking, and <code>details</code> in front of the status line.',
  },
]
</script>

# Settings — `/settings`

Everything humanize remembers is in one menu: `/settings`. It holds what is true of this
machine, what this directory remembers, the accounts agents run as, where a turn goes when it
cannot run, and where flows come from.

## Try it

```
/settings
```

![/settings opening on what is true of this machine, then → to this directory: workspace,
flow, profile and forget](/demo/profiling.gif)

The menu has five pages. <kbd>←</kbd> and <kbd>→</kbd> turn between them:

| Page | What it holds |
| --- | --- |
| [**Everywhere**](#everywhere) | whether humanize reports what goes wrong, whether the screen [shows the working](#details), and which agent `/btw` talks to |
| [**This directory**](#this-directory) | the flow it opens on, whether its runs are profiled, and forgetting it |
| [**Accounts**](#accounts) | every account an agent may run as, under a heading per CLI |
| [**Fallback**](#fallback) | where a turn goes when the place taking it cannot take it |
| [**Flowverses**](#flowverses) | the git repositories flows come from |

On the first two pages, <kbd>enter</kbd> on a row begins changing it, <kbd>←</kbd> <kbd>→</kbd>
flip it, and <kbd>enter</kbd> keeps it (<kbd>esc</kbd> puts it back). The last three are lists:
the `add` row adds one, <kbd>enter</kbd> opens the one under the cursor, and the `search…` row
narrows them. Nothing held changes until you save: choose the **save** row. Leave with
<kbd>esc</kbd> and unsaved changes, and it asks **save** or **discard**; <kbd>esc</kbd> on that
question takes you back into the menu.

### When a change lands {#saving}

What every page holds lands together, when you save: choose the **save** row. Leave with <kbd>esc</kbd>
and unsaved changes, and it asks **save** or **discard**; <kbd>esc</kbd> on that question
takes you back into the menu.

A few things happen as you ask rather than on save: making an account, signing one in, and
everything on the Flowverses page. And a few that are saved cannot take hold at once, because
something already running started without them. The row says when while the change is held,
and the transcript says it again once saved:

| Change | Takes hold |
| --- | --- |
| reports, details, fallback steps | at once |
| profile | from the next flow run |
| correcting an account, what it falls back to, taking it away | from the next agent session: a session already running keeps the account it started with |
| forget | from the next launch: the interface open now keeps what it opened with |

## Everywhere

What is true of this machine, for every project on it.

| Row | What it is |
| --- | --- |
| reports | whether humanize [reports what goes wrong](/user/reporting) to its developers |
| sent | what a report carries and what it never does. <kbd>enter</kbd> reads it out. |
| details | whether the screen [shows the working](#details): every tool call and all of the thinking |
| btw agent | the agent [`/btw`](/user/btw) talks to outside a session. Shown only once humanize has one. |

### Details

By default the screen shows what each turn said and nothing of how it got there. Turn
**details** on to see every tool call, every line of thinking, and whatever a flow or backend
prints along the way. Reach for it when a turn is slow or does something you did not expect.

It is off until you turn it on, and it is remembered: the next `hmz` opens the way you left it.
While it is on, the status line starts with `details`.

Here is one turn of [`rlar`](/flows/rlar)'s actor, both ways:

<TermScreen title="hmz · rlar" :frames="turn" />

Turning it on shows what arrives from then on. What scrolled past while it was off stays
hidden, but the run's [trace](/user/tracing) has all of it.

A yellow `●` line is humanize saying what it is doing about a turn: waiting out a rate limit,
carrying on as another account, cutting a turn off. It shows either way, because it is what
tells a turn that is waiting apart from one that has hung.

<TermScreen title="hmz · rlar" :frames="notice" />

It changes only the screen. The agents are not told, and they do not work any differently. The
run and its trace are the same either way.

| Turn it on | Leave it off |
| --- | --- |
| The first time you run a flow, to see what its turns do | For a long run you only check on now and then |
| When a turn takes far longer than it should | When you want each answer without scrolling past its tools |

A flow can watch its agents' tool calls itself. See [Hooks](/weaver/hooks).

## This directory

Run `hmz` in a directory you have used before and it opens on the flow you last saved there,
with the agents you gave it. This page shows what this directory remembers, and is where you
make it forget.

| Row | What it is |
| --- | --- |
| workspace | the directory these settings belong to |
| flow | the flow it opens on, and how many agents that flow was set up with |
| profile | whether a run here [profiles](#whether-a-run-here-is-profiled) the programs it starts |
| forget | forget everything this directory remembers |

**forget** clears this directory only. Every other directory, and everything on the other
pages, stay as they were. The next `hmz` here opens as it did the first time; the one open now
carries on with what it opened with.

### What a directory remembers

- **The flow** it last ran.
- **For each flow it has run:**
  - what each agent role runs: the CLI, the [account](#accounts), the model and the
    effort;
  - where each environment role works;
  - how the flow itself was [set up](/reference/tui), and what a run of it may spend.
- **Whether its runs are profiled.**

Each flow's setup is kept under the name the flow is offered by: `ralph_loop` for one humanize
ships, `local/twice` for a project flow, `user/twice` for a personal one. Within a flow, each
agent is kept under its role name. A flow that gains a new role does not hand an existing
role's model to it.

When the flow changes, what was saved is checked against it again. A setting the flow has
since dropped or renamed is asked for again, rather than carried over.

### Changing it

Change it where you set it: in [`/flow`](/reference/tui). Choose the flow, set each agent and
environment and what a run may spend, and save. That save is what the next `hmz` here opens
on. It only opens there: nothing runs until you send the first line.

Saving checks the lot before any of it is kept. The flow is loaded, every role is checked
against what the flow declares, and a flow that refuses a combination of its own settings says
why. You fix it in the menu, not half an hour into a run.

### Whether a run here is profiled

The **profile** row adds the programs a run starts (the tests, the builds, the greps) and how
long each took to the run's [trace](/user/tracing), on the same timeline as the agents. It is
off until you turn it on, and it belongs to the directory: a repository whose tests take an
hour is a different question from one whose tests take a minute.

It takes effect from the next run, not the one under way. An `hmz exec` run in this
directory is profiled too. What is recorded, and how to read it, is
[Tracing](/user/tracing).

### `hmz exec` starts from none of this

What an `hmz exec` line runs is what the line says: `-f`, `-a`, `-e`, `-p` and `-b`. An
unattended run inherits nothing from how this directory was last set up. It reads only two
things from here:

- whether runs in this directory are profiled;
- whether you said yes to [reporting](/user/reporting).

### The first time

With nothing remembered, `hmz` opens on the [`chat`](/flows/chat) flow, with the first
installed CLI that can run without further setup, at the first model that CLI lists, at effort
`high` where the model offers it.

::: details Where it is kept
The first two pages are one file, `~/.humanize/settings.yaml` (under `$HUMANIZE_HOME` if you
set that). Deleting it makes every directory start over, turns details off, and asks the
reporting question again.
:::

## Accounts

An **account**, or [provider](/user/concepts), is one named sign-in for one coding agent CLI,
kept apart from the CLI's own sign-in and from every other account. You make one on this page,
then name it after an `@` when you pick an agent. Reach for one when an agent should run on
another subscription, key or gateway than the one you are signed in with, or when two agents
of one CLI should run as two accounts in the same run.

### Try it {#accounts-try-it}

In `hmz`:

1. Type `/settings`, press <kbd>→</kbd> twice to turn to **Accounts**, then choose the `add`
   row.
2. Choose the CLI. Each row lists the ways that CLI can be signed in:

   ![add on the accounts page asks which coding agent the account is for, and lists each CLI's
   ways in beside it, with a CLI of your own last](/demo/account-backends.png)

3. Choose a way, say `gateway`. Give the account a name, `deepseek`, and answer what the way
   asks. A secret shows as bullets. A way that is a login hands the terminal to the CLI's own
   login until it is done.
4. Name the account after the CLI in `-a`:

```sh{3}
hmz exec -f flame_chase \
    -a first_chaser=claude/claude-opus-5:max \
    -a second_chaser=claude@deepseek/deepseek-chat:high \
    -b cost=20 "fix the build"
```

`flame_chase` has two agents take turns on one task. Here both run the same Claude Code: the
first as you are signed in, the second as `deepseek`.

### Choosing one for an agent

::: code-group

```text [hmz exec]
-a builder=claude@work/claude-opus-5:max
           ^^^^^^ ^^^^ ^^^^^^^^^^^^^ ^^^
           CLI    account  model     effort
```

```text [at the prompt]
/flow, choose the flow, enter on a role, then its provider row:

   Select the account its turns run as

   ❯ 1. as local                  signed in as you signed it in
     2. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     3. work                      login

        add                       an account
```

:::

- An agent with no account runs **`as local`**: the CLI signed in the way you signed it in
  yourself.
- At the prompt, that list's `add` row makes an account without leaving it. It is the same walk as on the Accounts page, without the question of which CLI, and the
  new account comes back chosen.
- An account belongs to one CLI. What signs in to Claude Code is not what signs in to codex, so
  the list only offers that CLI's accounts.

An agent never quietly runs as you instead. An account that is not there fails every turn of
that agent, naming it, and a bare `@` is refused before anything runs:

```console
$ hmz exec -f ralph_loop -b duration=1h \
    -a agent=claude@gone/claude-opus-5:max "…"
round 1
round 1 failed: agent: no claude provider called 'gone'
…
stopping: 3 rounds in a row answered with nothing
```

### The ways in

A **way** is one kind of sign-in: the CLI's own login, an API key, a gateway, a cloud account.
Pick a CLI to see what each of its ways asks for.

<SignInWays />

A way that runs a command hands it the terminal: its browser or device code owns the screen
until it is done, and what it writes lands in the account rather than in the CLI's own sign-in.
A way that only asks keeps your answers as the variables the CLI reads. `env` takes whichever
variables you type, one `NAME=VALUE` per line.

### Managing accounts

The Accounts page lists every account under a heading per CLI: its name, the way it was made
by, and the names of the variables it sets. It never shows a value.

![the Accounts page of /settings listing a claude account and as local, enter opening what can
be done with the account, and a asking which CLI a new account is for](/demo/accounts.gif)

<kbd>enter</kbd> on an account opens what you can do with it:

| On the menu | What it does |
| --- | --- |
| **correct what it holds** | Asks its way's questions again. Secrets are never shown back, so you type them again. |
| **sign in again** | Runs its login again. It owns the terminal while it does. |
| **falls back to** | The account a turn carries on under when this one fails. |
| **take it away** | The account and its credentials. |

Making an account and signing one in happen at once. Correcting, falling back and taking away
are held until you [save the menu](#saving), and while one is held its row says `from the next
agent session`: an agent picks the change up when it next opens a session, and a session
already running keeps the account it started with.

Under a CLI that has accounts, the last row is `as local`: the CLI as you signed it in
yourself. humanize keeps no credentials for it, so the only thing it offers is **falls back
to**.

### One account, several CLIs

An API key belongs to the vendor, not to the CLI. An Anthropic key works in Claude Code, pi,
opencode, mimocode and ZCode alike. So when you make an account that other CLIs could run as,
humanize asks which of them to copy it to:

![after claude/shared is made: pi, opencode, mimo and zcode, each marked not installed here
yet and switched off](/demo/alike.png)

- CLIs installed here start ticked; <kbd>enter</kbd>, <kbd>←</kbd>/<kbd>→</kbd>,
  <kbd>enter</kbd> changes one, and `copy` writes the copies.
- A copy takes **the same name**, so `claude/shared` becomes `pi/shared` and
  `opencode/shared` too, and it replaces a copy already there.
- Correcting the account asks again, so a rotated key is typed once and written over every
  copy you tick.
- Only variables travel. An account made by a login stays with its CLI.

::: tip Before you trust a rotation
The ticks follow which CLIs are installed, not which ones already hold a copy. A copy on a CLI
you did not tick keeps the old key. The Accounts page shows the copies: the same name under
another CLI's heading.
:::

### Which models an account can run

Which models a turn may name depends on the subscription, key or gateway behind it, so a new
account is asked what it runs as soon as it is made. A gateway account lists what the gateway
itself serves.

The list is what the `model` row offers at `/flow`. `ask it again` there asks again: do it when
the model you want is missing, or when a failed turn says the list is out of date. Nothing asks
again on its own.

### When an account fails

Each account can name another account of the same CLI to carry on under: **falls back to**, on
its menu. A turn that fails on one walks that chain and keeps its conversation.

```text
claude/subscription ──fails──▶ claude/key ──fails──▶ claude/gateway
```

`as local` can start a chain, but nothing falls back *to* it. How many times a failed turn is
tried again first, and moving on to another CLI or another model, are set on the
[Fallback](#fallback) page.

### Good to know {#accounts-good-to-know}

- **Only the credentials belong to the account.** Sessions, settings and skills stay the CLI's
  own, so a turn under an account still shows up in a [trace](/user/tracing), still counts
  towards the [cost readout](/user/tally), and still has your skills.
- **Other accounts' variables are unset.** A turn under an account runs without every variable
  that CLI would read an account from, unless this account set it. An `ANTHROPIC_API_KEY` left
  in your shell profile cannot quietly win over the account you chose.

::: details From Python
Every step of the walk is a call on `Hmz().accounts`:

```python
from hmz.sdk import Hmz

accounts = Hmz().accounts
shared = accounts.make("claude", "shared", accounts.way("claude", "key"), {
    "ANTHROPIC_API_KEY": key,
})

accounts.serves(shared)                     # ('pi', 'opencode', 'mimo', 'zcode')
accounts.copies(shared, "pi")               # pi/shared, holding the same key
accounts.points("claude", "work", "shared")  # work falls back to shared
```

`make` writes an account down. For a way that runs a login, `sign_in(account, way)` runs it.
See [SDK › Accounts](/reference/sdk#accounts).
:::

## Fallback

When a turn cannot run where it is (the model was retired, the CLI will not start, the whole
account is rate-limited), the Fallback page sends it somewhere else: another CLI, another
account, or another model. Each of those places is written `CLI[@ACCOUNT]/MODEL`, for example
`claude@work/claude-opus-5`.

It is the second of two fallbacks, and the one that costs the conversation:

| | Another account of the same CLI | Another place |
| --- | --- | --- |
| **Set on** | [Accounts](#when-an-account-fails) | Fallback |
| **Answers** | a subscription used up, a key refused | a model retired, a CLI missing, a whole account throttled |
| **The conversation** | carries on where it was | starts over, in a new session at the new place |
| **Tried** | first | once no account of that CLI is left to try |

### Try it {#fallback-try-it}

Type `/settings` and press <kbd>→</kbd> three times to turn to **Fallback**:

<Term title="/settings · Fallback">

<pre><span class="p b">Settings</span>

<span class="m">Everywhere · This directory · Accounts ·</span> <span class="p b">Fallback</span> <span class="m">· Flowverses</span>   <span class="d">←/→ page</span>

<span class="m">Where a turn goes when the place taking it cannot take it at all.
A place is a CLI, an account and a model.</span>

<span class="p">❯</span> <span class="d">1.</span> <span class="p">claude@work/claude-opus-5</span>  <span class="m">2 more tries, linear · falls back to codex/gpt-5.6</span>
  <span class="d">2.</span> <span class="p">codex/gpt-5.6</span>              <span class="m">falls back to dsh/deepseek-v4-flash</span>

     <span class="p">search…</span>
     <span class="p">add</span>                        <span class="m">a step</span>
     <span class="p">save</span>                       <span class="m">what is set here</span>

<span class="d">enter what happens · esc close</span></pre>

</Term>

1. Choose **add**. Pick the place that fails: its CLI, then one of its
   accounts, then one of the models it runs.
2. Pick the place that takes its turns, the same way.
3. Save: choose **save**. Leaving with <kbd>esc</kbd> asks whether to save or discard. Once saved, the next turn that fails reads
   it.

<kbd>enter</kbd> on a step asks three things about it: where it **falls back to**, how often
a failed turn is **taken again** there first, and whether to **take it away**.

Steps chain. Above, a turn that fails at `claude@work/claude-opus-5` is tried twice more
there, then moves to `codex/gpt-5.6`, and if it fails there too, on to
`dsh/deepseek-v4-flash`.

### Trying again

**taken again** sets how a failed turn is retried at this place before it moves on. Change
each value with <kbd>enter</kbd>, <kbd>←</kbd> <kbd>→</kbd>, <kbd>enter</kbd>, then
choose **set**:

| Setting | Choices | What it is |
| --- | --- | --- |
| tries | none, 1, 2, 3, 5, 8, 13, 21 | how many more times a failed turn is taken here |
| policy | the six below | how long to wait between tries |
| timeout | as long as it takes, 30s, 1m, 5m, 15m, 60m | the longest the retrying may go on |

Nothing is retried unless you set **tries**: a prompt the model refused is refused every time,
and only you know which of your places fail the other way. The exceptions are the failures in
the next section where another go is the answer.

| Policy | Waits before the 2nd, 3rd, 4th… try |
| --- | --- |
| `none` | no wait at all |
| `constant` | 1s, 1s, 1s |
| `linear` | 1s, 2s, 3s |
| `exponential` | 1s, 2s, 4s, 8s |
| `exponential-jitter` <Badge type="tip" text="default" /> | anywhere from 0 up to the exponential wait. Use it when several agents fail at once, so they do not all retry on the same second. |
| `fibonacci` | 1s, 1s, 2s, 3s, 5s |

No wait is ever longer than 60 seconds. The timeout is checked before each wait, so a retry
never starts once its time is up.

### What went wrong

A failed turn first works out what kind of failure it was, from what the CLI said and how it
exited. Each kind gets its own answer:

| What happened | Tried again here | Then goes to |
| --- | --- | --- |
| **Too many requests**: 429, a quota spent, `RESOURCE_EXHAUSTED`, `overloaded` | at least once, after 30 s or more | account → place |
| **Credentials refused**: 401, an expired login, a revoked key | never | account → place |
| **Model refused** for this account: `key not allowed to access model` | never | account → place |
| **No such model**: 404, a retired model | never | **place** |
| **CLI not installed** | never | **place** |
| **Sandbox would not start**: `bwrap: setting up uid map: Permission denied` | never | **place** |
| **Its own store was busy**: opencode's `database is locked` | at least 3 times, 1 s apart | account → place |
| **Lost the connection**: `ECONNRESET`, 502, 503, a timeout | at least once, in the same conversation | account → place |
| **Killed**: out of memory, `SIGKILL` | at least once, after 1 s | account → place |
| **Anything else** | as the step says | account → place |

"At least" because a step that asks for more tries gets them; "never" holds whatever the
step asks. **account** is the next [account](#accounts) of the same CLI, in the same
conversation. **place** is the next place on the chain, in a new conversation, once no account
is left or none would help. An agent that has moved to another account stays there for its
later turns. If there is nowhere left, the turn fails as it would with no step written.

Each move shows in the transcript as it happens, even with [details](#details) off, so a run
that is recovering does not look hung:

```
claude is rate-limited (this account has spent its quota; another one, or a wait, is what answers it); trying again in 30s (1 of 1)
claude is rate-limited (this account has spent its quota; another one, or a wait, is what answers it); carrying on as work
```

Where there is something to do about it, the line says so in brackets: an account that needs
signing in again, a CLI to install, or a model list to refresh with `ask it again`. Under
`hmz exec --json`, these lines are `notice` events.

::: details Antigravity (agy) fails with nothing said
agy exits with `Agent execution terminated due to error` and writes the real status only to
its own log, `~/.gemini/antigravity-cli/cli.log` or `~/.gemini/antigravity-cli/log/cli-*.log`.
humanize reads the end of that log when the output says nothing, so a rate-limited agy turn is
still treated as one. Look there yourself when an agy turn fails with no reason given.
:::

### What comes across the step

The step decides three things: the CLI, the account and the model. Everything else about the
agent comes along unchanged:

- its effort, on the nearest rung the new CLI has;
- its permission level, and whether it may search the web;
- the skills and callbacks the flow gave it;
- the run's budget, which goes on counting.

Settings that only one CLI understands come along when the step stays on the same CLI, and
are left behind when it moves to another.

### What it will not do {#fallback-will-not}

- **Carry the conversation.** The next place starts a new conversation and reads the
  repository, not the history. That conversation is then kept for the rest of the run, so a
  loop that moved is one conversation there, not a new one every round.
- **Go round in circles.** A chain stops at the first place it has already visited, and a
  place cannot fall back to itself.
- **Fork.** A place has one next place. Writing a new step for it replaces the old one.
- **Drop a setting quietly.** If the next CLI cannot be told something this agent was told,
  such as web search off, or cannot take the flow's callbacks, the turn fails where it is
  rather than move.
- **Retry what no retry can fix.** A prompt longer than the model's context window fails
  once, whatever the chain says.

::: details From Python
The steps you save at the prompt are the ones `Hmz().fallbacks` reads and writes:

```python
from hmz.sdk import Hmz

falls = Hmz().fallbacks
falls.points("claude@work/claude-opus-5", "codex/gpt-5.6")
falls.points("codex/gpt-5.6", "dsh/deepseek-v4-flash")
falls.retrying("claude@work/claude-opus-5", 2, "linear", 0)  # tries, policy, timeout in s
falls.chain("claude@work/claude-opus-5")
# ['claude@work/claude-opus-5', 'codex/gpt-5.6', 'dsh/deepseek-v4-flash']
falls.clear("claude@work/claude-opus-5")
```

The rest is in the [SDK reference](/reference/sdk).
:::

## Flowverses

A [flowverse](/weaver/flowverses) is a git repository of flows. The last page lists every place
flows come from: `official`, the package's own, your `local` and `user` flows, and every
flowverse you have added. Type `/settings` and press <kbd>→</kbd> four times to reach it, or
choose `where flows come from` below the flows of `/flow`, which opens `/settings` on this page.

![the Flowverses page of /settings: every place flows come from, then enter on one to read what
it holds](/demo/flowverses.gif)

| Row | What it does |
| --- | --- |
| a flowverse | <kbd>enter</kbd> says what it holds, then offers `fetch it again` and `take … away`. |
| `search…` | Narrows the list by what you type. |
| `add` | Adds one: a URL or `owner/repo`, then a name to keep it under. |

Everything here happens as you ask, not on save. `hmz` also fetches every flowverse that has a
URL in the background each time it starts. A flowverse never fetched is listed anyway, marked
`not fetched yet`, and a flow from it says so:

```
the official flowverse has not been fetched yet -- open the flowverses page of /settings and fetch it from its own sheet
```

Adding one, publishing your own and naming a flow by URL are in
[Flowverses](/weaver/flowverses).

## See also

- [History](/user/history): the other thing kept between starts
- [Tracing](/user/tracing): what a profiled run is drawn into
- [Providers reference](/reference/providers): every way in, every field, and adding a CLI
- [Accounts, drawn](/features/accounts): the account chain and its waits, step by step
- [Unattended runs](/user/unattended): where a place to fall back to earns its keep
- [TUI › /settings](/reference/tui#what-humanize-remembers): the menu, row by row

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
