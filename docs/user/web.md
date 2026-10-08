# In a browser (`hmz web`)

`hmz web` opens this directory's runs in a browser on this machine: the run going as it happens,
every run written down here, starting a run, what the runs spent, and what humanize remembers.
It is one more window onto the run `hmz` shows, not a copy of it. Start a run in the terminal and
answer it in the browser, or the other way round.

::: info At a glance
- **You will** watch, steer and start runs from a browser, read a run written down, and see what
  the runs here spent.
- **Use it when** a picture of a run reads better than a transcript: several sessions at once, a
  long run's turns laid out over time, a week's spend by flow.
- **You need** humanize installed as in [Installation](/user/installation), and a browser on the
  machine `hmz` runs on, or an ssh tunnel to it.
:::

## Try it

```sh
cd ~/tmp/humanize-demo
hmz web
```

It prints the address it listens at, opens your browser on it, and serves the page until you
press <kbd>ctrl+c</kbd>:

```console
$ hmz web
hmz web: http://127.0.0.1:43017/?key=Xq1rB0…
```

## How it works

`hmz web` is a frontend of this directory's runs, as every `hmz` opened here is. It reaches the
same run through the same [host](/features/daemon), so what one window does, every other window
sees: a line said in the browser is in the terminal's transcript marked `· by browser`, and a
question answered in the terminal stops waiting in the browser.

That has three consequences:

- **The run does not live in the page.** Closing the tab, or stopping `hmz web`, leaves the run
  going, as closing a terminal does. See [Leaving it running](/user/leaving).
- **One run per directory.** `hmz web` serves the directory it was started in. Another project
  needs an `hmz web` of its own, on another port.
- **It only listens on this machine.** The address is `127.0.0.1`, and it carries a key made
  afresh each time `hmz web` starts. Opening the address hands your browser that key as a
  cookie, and only a browser holding it is answered. See [What it refuses](#what-it-refuses).

## The views

The bar across the top says which directory this is, links to each view, and says whether a run
is going: `live · <flow>` takes you to it. The last control switches between your system's
colours, light and dark.

| View | What it shows | What you can do there |
| --- | --- | --- |
| **Runs** | Every run of this directory, newest first: how it went, its task and flow, its agents, what it spent, how long it took, when it began | Find runs by how they went, by flow, or by a word of their task; open one |
| **Live** | The run going, or the last one, as it happens | Everything a person may do to a run; see [The run going](#the-run-going) |
| **A run** | One run written down | Read its turns and transcript out of its logs, export it, pick it up |
| **Start** | A flow set up as this directory last ran it | Start it, or pick an earlier run up |
| **Flows** | The flows on offer here, and what each declares | Start one |
| **Usage** | What the runs here spent, by day and by flow | Look back 7, 30, 90 or 365 days |
| **Settings** | What humanize remembers | Change it, as [`/settings`](/user/settings) does |

Every view is an address: copy it, keep it, or open it in another tab.

### The run going {#the-run-going}

**Live** draws the run from what the host tells it, as the terminal interface does:

- **The figures.** How long it has been going, what it has spent and how fast, the tokens by
  kind, and a meter for each limit of its [budget](/features/allowances).
- **Turns.** A lane per session, with a capsule for each turn it took. A turn still open is
  ringed; a line marks now. Click a lane or a turn to read that session's transcript.
- **Transcript.** What each session said, drawn as the terminal draws it: an agent's words on
  a dot, your lines on `❯`, a tool on a mark of its own, and `✻ Worked for …` closing a turn.
  The **all** tab is every session at once.
- **Agents.** A card per role: working or idle and for how long, its turns and tokens, the
  sub-agents it started, and who handed to whom.

And, while it goes, what a person does to a run:

- **Waiting for you.** A question the run put to a person, with its offered answers as
  buttons and a field for your own. A question another window holds says whose it is. See
  [Questions](/user/questions).
- **Say a line.** To the run as a line typed in `hmz` goes (`the next turn`), to a role, to
  one session (marked `working` while it has a turn open), or to a person the flow has. See
  [Talking to a running turn](/user/steering).
- **Ask beside it.** A side question, as [`/btw`](/user/btw) asks it: of the btw agent, or of
  one session's side copy. The run never sees it. Every question after the first goes on in
  the same side conversation until you press **Close them**, or a new run starts.
- **People.** Each person the flow has: **Answer it here** holds the role for this browser,
  **Take it** takes it from another window, **Let go** gives it back; **Away** answers its
  questions with nothing, as [`/afk`](/user/afk) does.
- **Board.** For a run that holds one: edit, remove and add its lines. See
  [The mission board](/user/board).
- **Stop.** Asks first, then stops the run for everybody reading it. While it unwinds,
  **Force** closes every session under its turn. See [Stopping](/user/stopping).

### A run written down

Open a run from **Runs**, or press **Its epic** on **Live**. The page says how it was set up --
its agents, environments, params and budget -- the flows it called, its sessions, what it
spent, and how long it took, with how much of that was spent working.

- **Read its turns and transcript** reads what each session did out of the logs it kept, as
  [tracing](/user/tracing) does. It takes a moment on a long run.
- **Export** downloads the run as one archive, struck of credentials. See
  [Exporting a run](/user/export).
- **Pick it up** opens **Start** on that run, where its flow can be picked up. See
  [Picking a run up](/user/resuming).

### Starting a run

**Start** opens on the flow this directory last ran, set up as it was: an agent for each role,
spelled as `-a` spells one (the field offers the models each installed CLI said it runs), where
each environment works, the flow's params, its budget, and whether it is profiled. Every flow but
`chat` needs at least one limit. **Start** sends it, and the page goes to **Live**.

### Settings

The same pages as [`/settings`](/user/settings), in the same order:

| Page | What is there |
| --- | --- |
| **General** | Whether a turn's working is shown, the [`/btw` agent](/user/btw), and [error reports](/user/reporting) |
| **Accounts** | Every [account](/user/settings#accounts) by its CLI, way in and the names of what it sets: ask what it runs again, copy it to another CLI, remove it, or make one |
| **Fallback** | Each [step](/user/settings#fallback): where a turn goes when a place cannot take it, and how it is tried again |
| **Runtimes** | Every runtime: add one from its backend's fields, change, check or remove it, or bring hosts in from your ssh config |
| **Workspace** | What this directory was last set up with, and forgetting it |

An account is never shown by its values: a page lists the names of the variables it sets, and
nothing else. A way in that runs a CLI's own sign-in, such as `login`, needs a terminal: it is
offered as `(at a terminal)` and made from `/settings` in `hmz`.

## Example: start a run in the browser, answer it in the terminal

Start `hmz web` in a project, and open **Start**:

1. **flow** is `chat`. Type a task, give `assistant` an agent such as
   `claude/claude-haiku-4-5:high`, and press **Start**. The page goes to **Live**.
2. When the agent has answered, **Waiting for you** shows the question `chat` puts to you.
3. In a terminal in the same directory, run `hmz`. It opens on the same run, with the same
   question waiting.
4. Answer it in the terminal. In the browser, the question goes, and the answer is in the
   transcript.
5. Press **Stop** in the browser, then **Stop it**. The terminal says
   `— browser is stopping the flow —`.

### Check it worked

- The terminal's transcript shows the task you typed in the browser, marked `· by browser`.
- **Runs** lists the run, `stopped`, with what it spent.

## From another machine {#over-ssh}

`hmz web` only listens on the machine it runs on. To use it from your laptop while `hmz` runs on
a server, forward a port over ssh:

```sh
ssh -L 8765:127.0.0.1:8765 you@devbox
```

Then, in that ssh session:

```sh
cd ~/src/api
hmz web --port 8765 --no-open
```

Open the printed address in your laptop's browser. A port forwarded to another number on your
side works too: change the port in the address and keep the key.

## What it refuses {#what-it-refuses}

Anything that can reach a port on this machine could otherwise drive your runs, so the page is
answered only where it was meant to be:

- **Only this machine.** It listens on `127.0.0.1` alone, and refuses any request that names
  another host. That stops a web page elsewhere from pointing a name of its own at your machine
  and reading the runs through your browser.
- **Only the browser it was opened in.** The key in the address becomes a cookie that scripts
  cannot read and other sites cannot send. A browser without it is told it is not let in.
- **Only its own page.** Every change is JSON from the page's own address. A form on another
  site cannot post to it.
- **No secret on the page.** Accounts are shown by the names of what they set, never by a
  value.

The key changes every time `hmz web` starts, so an address from an earlier one lets nobody in.

## Variations

- **A port of your own.** `hmz web --port 8765` listens on that port. `0`, the default, picks
  any free one.
- **No browser.** `hmz web --no-open` only prints the address, for a machine without a desktop
  or a browser of your choosing.
- **Runs that end with it.** With `HUMANIZE_DAEMON=off`, `hmz web` holds the runs in its own
  process, and stopping it stops them, as [`hmz` does](/user/leaving#when-it-cant-be-left-running).

## Troubleshooting

### `This browser is not let in.`

The browser has no key, or the key of an `hmz web` that has since stopped. Open the address the
running `hmz web` printed, key and all.

### `hmz: the web interface cannot be served: … Address already in use`

Something already listens on that port: another `hmz web`, perhaps for another directory. Pick
another `--port`, or leave it out.

### `hmz: the runs … are held by an older humanize`

An older humanize holds this directory's runs, or this machine's. Stop them with that version, as
the message says, then start `hmz web` again.

### The bar says why the runs let it go

The host holding the runs went: it was closed, or it let this window go. The page reaches the
runs again by itself a moment later, starting a host where none is, and the bar says
`no run going` or `live` again once it has.

### A way in is marked `(at a terminal)`

It runs the CLI's own sign-in, which needs a terminal. Make that account from `/settings` in
`hmz`.

## Next steps

- [Watching a run (the monitor)](/user/monitor): the same run, drawn in the terminal.
- [Leaving it running](/user/leaving): how a run outlives every window onto it.
- [Web reference](/reference/web): the command line, every route the page uses, and the stream.
