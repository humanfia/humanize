# In a browser (`hmz web`)

`hmz web` opens every epic on this machine in a browser on it -- of every directory, as the
[daemon](/features/daemon) holds every directory's runs: each epic going as it happens, every
epic written down, starting one in any directory, what they spent, and what humanize remembers.
It is one more window onto the runs `hmz` shows, not a copy of them. Start an epic in the
terminal and answer it in the browser, or the other way round.

::: info At a glance
- **You will** watch, steer and start epics in any directory from a browser, read an epic
  written down, and see what they spent.
- **Use it when** a picture of a run reads better than a transcript: its agents and who handed
  to whom, each session's turns laid out over time, a week's spend by flow.
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

`hmz web` is a frontend of every directory's runs, where `hmz` is a frontend of one. It reaches
a directory's runs through the same [host](/features/daemon) as `hmz` opened there, so what one
window does, every other window sees: a line said in the browser is in the terminal's transcript marked `· by browser`, and a
question answered in the terminal stops waiting in the browser.

That has three consequences:

- **The run does not live in the page.** Closing the tab, or stopping `hmz web`, leaves the run
  going, as closing a terminal does. See [Leaving it running](/user/leaving).
- **One page for the machine.** Start `hmz web` anywhere: it serves every directory, and the one
  it was started in is only the one a new epic is offered first. A directory is reached only
  while the page shows it or acts on it, so a host with nothing to do still goes.
- **It only listens on this machine.** The address is `127.0.0.1` (`localhost` works too, over
  IPv4 or IPv6), and it carries a key made
  afresh each time `hmz web` starts. Opening the address hands your browser that key as a
  cookie, and only a browser holding it is answered. See [What it refuses](#what-it-refuses).

## The page {#the-page}

The page is laid out as a desktop chat app is. In it, every run of a flow is an **epic**, the
way every conversation of an agent is a session: the sidebar lists your epics as a chat app
lists its chats, and an epic opens out into its agents and the sessions each opened.

| Where | What it shows | What you can do there |
| --- | --- | --- |
| **Sidebar** | **New epic**, **Search epics**, **Flows**, then a folder per directory -- every one an epic ran in or that was opened here -- with its epics newest first: how each ended, or `live` | Open an epic; press its arrow to open it out into its agents, and each agent into its sessions; **+** on a folder starts an epic there |
| **New epic** | A box for the task, the directory and the flow picked at the top as a chat app picks a model | Start it; **Options** on the box sets the rest up. See [Starting an epic](#starting-an-epic) |
| **An epic** | Its graph: who handed to whom -- a `chat` opens on its conversation instead | Read it, steer it while it goes, export it, pick it up. See [An epic](#an-epic) |
| **A session** | Its thread, as the terminal draws it | Say a line into it, or answer what it asks, while the epic goes |
| **Flows** | **Installed**: a card for each flow on offer in the directory picked, its release and any newer one, and what one declares. **Flowverses**: every place flows come from, and every release each index lists | Start one, update, uninstall or copy it into the directory; install, switch or uninstall a release; add, fetch or remove a flowverse |
| **Search epics** (<kbd>⌘K</kbd>) | Every epic, with its directory, agents, what it spent and how long it took | Find epics by how they went, by directory, by flow, or by a word of their task |
| **Settings** | What humanize remembers, and what the epics here spent | Change it, as [`/settings`](/user/settings) does |

The foot of the sidebar names this machine and says how many epics are going on it;
its menu opens **Settings** and **Usage**. Where a newer humanize is out, the machine is marked ↑ and its menu offers
**Update**, which copies `hmz update` to run in a terminal. <kbd>⇧⌘O</kbd> opens a new epic and <kbd>⌘.</kbd> folds the sidebar away. On a phone
the sidebar is a drawer behind the button in the corner.

Every view is an address: copy it, keep it, or open it in another tab.

**Right-click** anything for what can be done to it: a folder in the sidebar (new epic here, its
flows, search it, copy its path, settings), an epic (open, its log, resume, copy its link or task,
export, stop), an agent or a session, a node on the graph, a flow or flowverse card, a search
result, a line of a thread (copy it, or the whole thread). Where there is text to read or write,
selected text keeps the browser's own menu. **Hover** over anything cut short -- a folder's name,
a task, a path -- to read it in full.

**Paths** are browsed for rather than typed: the folder button beside a path opens a list of
what is in a folder; click your way in, and press **Choose** (or click a file, where a file is
wanted). Typing still works, and completes as you go.

### An epic {#an-epic}

An epic opens as a graph, drawn from what the host tells the page, as the terminal interface's
monitor is:

- **Agents.** A node per agent, in a frame for the flow it worked in, saying what it runs,
  whether it is working or idle and for how long, and its tokens. A person the flow has is a
  dashed node. Click an agent to pick it out; the panel beside says the rest of it.
- **Handovers.** An arrow from one agent to the next each way the epic handed over, with how
  many times it did. The last handover is the red arrow, and the agent working now is lit.
- **Sessions.** On each node, a lane per session it opened, with a mark for each turn it took
  over the epic. A turn still open is lit. Click a session to read its thread.

The panel beside it (the button at the top right shows and hides it) holds:

- **Epic.** How long it has been going, what it has spent and how fast, a meter for each limit of
  its [budget](/features/allowances), the task, who handed to whom in words, **Spending** by
  model and kind of token (`≥` marks a figure that is only a floor), **Environments** -- where
  each session works and where its harness went -- the **Frontends** reading it, the flows going
  or the flows it called, and how it was set up and where it is written down.
- **Aside.** A side question, as [`/btw`](/user/btw) asks it: of the btw agent, or of one
  session's side copy -- any epic's session, an earlier one forked from where that epic kept it,
  so it answers with that session's own history. The epic never sees it. Every question after the first goes on in the
  same side conversation until you press **Close them**, or a new epic starts.
- **Board.** For an epic that holds one: edit, remove and add its lines. See
  [The mission board](/user/board).
- **People.** Each person the flow has: **Answer it here** holds the role for this browser,
  **Take it** takes it from another window, **Let go** gives it back; **Away** answers its
  questions with nothing, as [`/afk`](/user/afk) does.

And under the graph, while it goes:

- **Waiting for you.** A question the epic put to a person, with its offered answers as buttons
  and a field for your own. A question another window holds says whose it is. A `chat` waiting
  for your next line puts nothing here, and what its agent asks is asked in its conversation. See
  [Questions](/user/questions).
- **Say something.** <kbd>Enter</kbd> sends a line to the epic as a line typed in `hmz` goes
  (`the next turn`), to a role, to one session (marked `working` while it has a turn open), or
  to a person the flow has; <kbd>Shift</kbd>+<kbd>Enter</kbd> starts a new line. In a session's
  thread it goes into that session, or answers what that session's open turn asks. See
  [Talking to a running turn](/user/steering).
- **Stop.** Asks first, then stops the epic for everybody reading it. While it unwinds,
  **Force** closes every session under its turn. See [Stopping](/user/stopping).

### A session {#a-session}

A session opens as its thread, drawn as the terminal draws it: an agent's words on a dot, your
lines set apart on the right, a tool on a mark of its own, and `✻ Worked for …` closing a turn.

A `chat` reads as a chat app's conversation, and is where one started from the page opens: your
task, then each reply and each line you typed under it, on the right. The box under it is how
you answer -- between turns it is your next turn, and while the agent asks something mid-turn
it answers that, the answers it offers buttons at the end of the conversation.

**Log**, first under an epic in the sidebar, is the transcript every agent and person appears
on; each node's **log** row is that agent's across its sessions, and a person's node opens what
they were asked and answered. A line typed under one goes to whose it is.

**List**, at the top right of the graph, draws the agents as a list instead, the working first;
your choice is kept in this browser.

### An epic written down

An epic that has ended keeps its graph and its panel. Opened later, it says how it was set up
-- its agents, environments, params and budget -- the flows it called, its sessions, what it
spent, and how long it took, with how much of that was spent working.

- **Read its turns** reads who handed to whom, and each session's turns, out of the logs it
  kept, as [tracing](/user/tracing) does. It takes a moment on a long epic. Opening a session
  reads its thread the same way.
- **Export** (the arrow at the top) downloads the epic as one archive, struck of credentials.
  See [Exporting a run](/user/export).
- **Upload** (the up arrow at the top, or in the epic's menu) backs it up now to the targets it
  was started with, else the defaults, and says which at once; hover it for how its last
  backup to each target went. See [Backing epics up](/user/backups).
- **Pick it up** opens a new epic on it, where its flow can be picked up. See
  [Picking a run up](/user/resuming).

### Starting an epic {#starting-an-epic}

**New epic** opens on the directory `hmz web` started in, or the folder whose **+** was pressed,
and on the flow that directory last ran; pick another of either at the top. **Open folder…**
takes any directory by its path, completed as you type, and keeps it in the sidebar. Type the
task and press <kbd>Enter</kbd>. **Options** holds what the flow is set up with, as that
directory last set it up:

- **Agents.** Per role: the **CLI** (installed ones that can fill it), the **Account** it runs
  as (**Local** is this machine's own sign-in; **Add account…** opens Settings), the **Model**
  and the **Effort**. A CLI never asked what it runs is asked the first time it is picked, which
  can take a while; the refresh button asks again. Where it cannot say, pick **Other…** and type
  the model.
- **Environments.** Per role: the **Backend**, the **Runtime** of it (or **Add runtime…**, or
  for ssh **Other host…**), and the **Directory**, completed as you type on this machine.
- **Parameters**, the **Budget**, **Backup** -- the [targets](/user/backups) the epic is backed
  up to, the defaults ticked until a choice is saved -- and **Profile**. **Save** keeps them all for that directory
  without starting an epic, as saving `/flow` does; starting keeps it too. The chips beside **Options** say what is set. Every flow but `chat`
needs at least one limit. The page goes to the epic once it starts -- a `chat` to its
conversation.

### Settings

The same pages as [`/settings`](/user/settings), in the same order, and what the epics spent:

| Page | What is there |
| --- | --- |
| **General** | Whether a turn's working is shown, the [`/btw` agent](/user/btw), and [error reports](/user/reporting) |
| **Themes** | The [themes](#themes) of this browser, and which two **Auto** follows your system with |
| **Accounts** | Every [account](/user/settings#accounts) by its CLI, way in and the names of what it sets: ask what it runs again, **Edit** it (what you leave blank stays as it was), copy it to another CLI, remove it, or make one |
| **Fallback** | Each [step](/user/settings#fallback): where a turn goes when a place cannot take it, and how it is tried again |
| **Runtimes** | Every runtime: add one from its backend's fields, change, check or remove it, or bring hosts in from your ssh config |
| **Backup** | Every [backup target](/user/backups): its repository and branch, when an epic goes to it (**On session close**, **Every N minutes**, **On epic end**, or none: by hand only), and whether it is a **Default**; add, edit or remove one. A URL is shown with nothing signed into it |
| **Workspace** | What a directory was last set up with, and forgetting it -- which also takes it out of the sidebar where no epic ran there |
| **Usage** | What the epics spent, of every directory or of one, by day and by flow, looking back 7, 30, 90 or 365 days |

An account is never shown by its values: a page lists the names of the variables it sets, and
nothing else. A way in that runs a CLI's own sign-in, such as `login`, needs a terminal: it is
offered as `(at a terminal)` and made from `/settings` in `hmz`.

### Themes {#themes}

The page is drawn in a theme. humanize comes with **presets**, each a pair of a light theme and a
dark one: its own, **Humanize Green**, and **Temperate Gold**, **Concordant Scarlet**,
**Restrained Crimson**, **Critical Teal**, **Desirous Indigo**, **Peaceful Lilac**,
**Hateful Silver**, **Devoted Pink**, **Self-Negating Plum**, **Dominant Azure**,
**Surviving Jade** and **Lamenting Orchid**.

A theme is picked only under **Settings → Themes**. **Auto**, the default, follows your system
with a pair: under **Auto** pick a **Pair** -- or any theme for the system's **Light** and any
for its **Dark**, your own included. Click a preset's light or dark
swatch to use that one theme whatever the system is.

**New** makes a theme from the one showing, and **New pair** a pair of your own -- a light theme
and a dark one, which Auto can follow your system with as it does a preset -- from the pair
showing. **Duplicate** copies any theme, or a whole pair. **Edit** opens one of yours:

- **Name**, and the **Base** it is made on, Light or Dark, whose colour any you leave blank is.
  In a pair, the name is both themes', and **Side** switches between its light and its dark.
- Every colour, by what it colours: **Backgrounds** (page, sidebar, surface, raised),
  **Text**, **Controls** (button, its text, primary button, its text, field, edge), **Lines**,
  **Accents** and the **Graph**'s lanes. Pick one or type any CSS colour, such as
  `#102030` or `rgba(255, 255, 255, 0.1)`; × gives back the base's.
- **Pictures** behind the **Page**, **Sidebar**, **Panel** and **Dialog**: a PNG, JPEG, GIF,
  WebP, AVIF or SVG -- an animated SVG moves -- each to **Cover**, **Fit** or **Tile** its plane.
  Where your system asks for reduced motion, a moving picture is held still.

The page shows a theme as you change it, and keeps every change at once. **Export** saves a
theme, or a pair with both its themes, pictures and all, as a `.hmztheme` file; **Import** reads
one back, here or in any other browser. Themes are kept by the browser, as the rest of what the page remembers is, so another
browser -- or [the app](/user/desktop) -- has its own until you import them there.

A `.hmztheme` file is JSON:

```json
{
  "hmztheme": 1,
  "name": "Night",
  "base": "dark",
  "colors": { "paper": "#102030", "primary": "#ec6fa3" },
  "images": { "page": { "fit": "cover", "data": "data:image/svg+xml;base64,…" } }
}
```

A pair holds both its themes, each with its `colors` and `images`, in place of a `base`:

```json
{
  "hmztheme": 1,
  "name": "Dusk",
  "light": { "colors": { "paper": "#fff8e0" }, "images": {} },
  "dark": { "colors": { "paper": "#201008" }, "images": {} }
}
```

`colors` is keyed by the page's colour tokens (`paper`, `side`, `surface`, `raised`, `ink`,
`ink-2`, `ink-3`, `on-ink`, `on-fill`, `link`, `control`, `control-ink`, `primary`,
`on-primary`, `field`, `edge`, `line`, `line-strong`, `hover`, `scrim`, `green`, `cyan`,
`cyan-ink`, `pink`, `pink-ink`, `lavender`, `gold`, `done`, `fail`, `lane-1` to `lane-6`), and
`images` by plane (`page`, `sidebar`, `panel`, `dialog`). Importing keeps what a theme can hold
and drops the rest: an unknown token, a value that is not a colour, a picture that is not an image.

## Example: start an epic in the browser, answer it in the terminal

Start `hmz web` in a project, and open **New epic**:

1. Pick `chat` at the top. Open **Options** and give `assistant` an agent such as
   `claude/claude-haiku-4-5:high`. Type a task and press <kbd>Enter</kbd>. The page goes to
   the conversation, `assistant/1`.
2. When the agent has answered, `chat` waits for your next line, typed in the box under it.
3. In a terminal in the same directory, run `hmz`. It opens on the same run, waiting for you
   to say what next.
4. Answer it in the terminal. In the browser, your answer is a line of yours in the
   conversation, and the agent's reply follows it.
5. Press **Stop** in the browser, then **Stop it**. The terminal says
   `— browser is stopping the flow —`.

### Check it worked

- The terminal's transcript shows the task you typed in the browser, marked `· by browser`.
- The sidebar lists the epic, `stopped`; **Search epics** shows what it spent.

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
side works too: change the port in the address and keep the key. So does any name the port is
reached by -- a forwarded port in VS Code or Codespaces, or a reverse proxy on the server such
as `tailscale serve` -- as long as the proxy runs on the same machine as `hmz web`: change the
start of the address and keep `/?key=…`.

## What it refuses {#what-it-refuses}

Anything that can reach a port on this machine could otherwise drive your runs, so the page is
answered only where it was meant to be:

- **Only this machine.** It listens on the loopback alone, and answers only connections from
  this machine -- whatever name they used, so a port forwarded or proxied from here works. A web
  page elsewhere that points a name of its own at your machine still reads nothing: your browser
  never hands that name the key's cookie.
- **Only the browser it was opened in.** The key in the address becomes a cookie that scripts
  cannot read and other sites cannot send. A browser without it is told it is not let in.
- **Only its own page.** Every change is JSON from the page's own address, and every question
  about the runs comes from it: a page elsewhere -- even one served from another port of this
  machine -- reaches nothing, and a form on another site cannot post to it.
- **The key on no command line.** The browser `hmz web` opens is opened on a page only you can
  read, which sends it on to the address: another account on a shared machine cannot read the
  key off the browser's command line.
- **No secret on the page.** Accounts are shown by the names of what they set, never by a
  value.

The key changes every time `hmz web` starts, so an address from an earlier one lets nobody in.

## Variations

- **A port of your own.** `hmz web --port 8765` listens on that port. `0`, the default, picks
  any free one.
- **No browser.** `hmz web --no-open` only prints the address, for a browser of your choosing.
  On a machine without a desktop -- one reached over ssh -- it opens none anyway.
- **Stopped by what started it.** `hmz web --attached` stops once its standard input closes,
  so a program that starts it -- a desktop app, a script -- takes it down by exiting, even by
  crashing.
- **Runs that end with it.** With `HUMANIZE_DAEMON=off`, `hmz web` holds the runs in its own
  process, and stopping it stops them, as [`hmz` does](/user/leaving#when-it-cant-be-left-running).

## Troubleshooting

### `This browser is not let in.`

The browser has no key, or the key of an `hmz web` that has since stopped. Open the address the
running `hmz web` printed, key and all.

### `hmz: the web interface cannot be served: … Address already in use`

Something already listens on that port: another `hmz web`, perhaps. Pick another `--port`, or
leave it out.

### `the runs … are held by an older humanize`

An older humanize holds that directory's runs, or this machine's: the page says so where it
asks for them, and serves every other directory. Stop them with that version, as the message
says.

### The sidebar says why the host let it go

The host holding the runs went: it was closed, or it let this window go. The page reaches the
runs again by itself a moment later, starting a host where none is, and the foot of the sidebar
says `idle` or how many are `live` again once it has.

### A way in is marked `(at a terminal)`

It runs the CLI's own sign-in, which needs a terminal. Make that account from `/settings` in
`hmz`.

## Next steps

- [Watching a run (the monitor)](/user/monitor): the same run, drawn in the terminal.
- [Leaving it running](/user/leaving): how a run outlives every window onto it.
- [Web reference](/reference/web): the command line, every route the page uses, and the stream.
