# `web`

The web interface `hmz web` serves: every workspace's runs on this machine, drawn in a browser on
it. Where the terminal interface is about the directory it is opened in, this is about the
machine, as the daemon is: one more frontend of the runs each workspace's host holds, beside
every terminal interface opened on them -- and, through the `hmz web` it starts on each over ssh,
of other machines' daemons. It runs flows and reads them back, defines no flows, drives no agents
and keeps no store of its own.

## API

```python
# __init__.py
@contextlib.contextmanager
def listening(*, port: int = 0, apart: bool = True) -> Generator[Site]: ...
def serve(
    *,
    port: int = 0,  # 0 for any free one
    apart: bool = True,  # the runs held by each workspace's host, or in this process
    shown: Callable[[str], object] = print,  # told the address once it listens
    opened: Callable[[str], object] | None = None,  # opens the address in a browser
) -> None: ...
# site.py
class Site(ThreadingHTTPServer):
    port: int  # property
    address: str  # property: http://127.0.0.1:<port>/?key=<key>
    notices: Notices
    remotes: Remotes
# notices.py -- what this machine's runs did that a person would want told
class Notices:
    def since(self, after: int = 0) -> list[dict[str, Any]]: ...  # each numbered after `after`
    def heard(self, callback: Callable[[dict[str, Any]], None]) -> None: ...  # each as it comes
# remote.py -- the daemons of other machines, each reached over ssh
class Remotes:
    def state(self, name: str) -> dict[str, Any]: ...  # {state, detail, version}
    def reached(self, name: str) -> tuple[int, str]: ...  # its port forwarded here, and its key
    def connect(self, name: str) -> None: ...
    def close(self) -> None: ...
```

```text
GET  /api/notices?after=<id>          {notices, last}, of this machine's runs alone
GET  /api/notices/stream              `notice` events, resumed from Last-Event-ID
     a notice                         {id, kind, workspace, epic, flow, task, role, text, at}
     its kind                         done | failed | stopped | asked | listening
GET  /api/daemons                     Local, then each SSH daemon, with how it stands
POST /api/daemons                     one added or changed
POST /api/daemons/remove              one removed
POST /api/daemons/import              ssh config's hosts not yet added, those named
GET  /api/daemons/hosts               ssh config's hosts not yet added
POST /api/daemons/<name>/connect      reached again
GET  /api/daemons/<name>/state        idle | connecting | installing | up | failed
     /d/<name>/api/...                that daemon's /api/..., proxied; /d/local/api/ is /api/
GET  /api/notifications               {items, unread}: every daemon's notices, each with
                                      its daemon and whether it is read
GET  /api/notifications/stream        `notification` events
POST /api/notifications/read          {ids} or {all}
POST /api/notifications/clear
GET  /api/notifications/settings      {kinds: {done, failed, stopped, asked, listening}, system}
POST /api/notifications/settings
```

```yaml
# settings.yaml, Local's alone
daemons:              # each SSH daemon; Local is always there and never written
  - {name, host, user, port, identity_file, proxy_jump, options: [[key, value]], alias, config}
notifications:        # every kind, and the system, on unless turned off
  kinds: {done: true, failed: true, stopped: true, asked: true, listening: true}
  system: true
```

`listening` attaches to the runs and listens without answering; `Site.serve_forever` answers
until `Site.shutdown`. `serve` is both, until it is interrupted.

## Requirements

### Reaching it

- MUST listen on this machine's loopback alone -- on every loopback it has, IPv4's and IPv6's,
  on one port -- and MUST be served by the standard library alone: no dependency and no build
  step beyond what `hmz` already installs.
- MUST let a browser in only by the key the printed address carries, made afresh each time it
  is served, and MUST then hold it by a cookie that is `HttpOnly` and `SameSite=Strict` and
  carries that key. Everything under `/api/` MUST be refused to a browser not let in, and to a
  request its browser says another page made -- a page served from another port of this
  machine included, to which the cookie is no barrier.
- MUST NOT put the key on any command line: a browser it opens MUST be opened on a page only
  this account can read, which sends it on to the address, and only where there is a desktop
  to open one on.
- MUST refuse any request whose connection did not come from this machine before anything else
  is read, and MUST NOT ask what name it was reached by: a port forwarded or proxied on to it
  from here MUST be let in, and a page elsewhere that points its own name at the loopback is
  kept out by the key, since a browser hands a name only that name's cookies.
- MUST take a write only as JSON sent from its own page's origin, and no larger than a request
  here may be -- save an epic to import, which MAY be sent as the `.hmzepic`'s own bytes, no
  larger than an archive here may be, kept among this machine's own files only until it is
  answered; MUST answer what it refuses as JSON saying why in one sentence, with a status
  saying what kind of refusal it is.
- MUST serve the page as its own files and nothing beside them, under a content policy that
  lets it load and run nothing else, and MUST NOT be framed.
- MUST hand a page nothing secret: an account MUST be its CLI, its name, its way in and the
  names of what it sets, never a value.
- MUST set up only a flow on offer here, never one a request names by path or by repository:
  setting a flow up loads it, which runs its code.

### One frontend of the runs

- MUST serve every workspace of this machine wherever it is started: each an epic was run in,
  each written down in humanize's settings, and any a page opens by its path, which is then
  written down there -- the one it was started in offered first -- and MUST NOT take a path
  that is not a directory as one.
- MUST attach through `daemon` as every frontend does -- to the host holding a workspace's
  runs, starting one where none is, or to runs held in its own process where they are not held
  apart -- only while a page follows that workspace's runs or acts on them, refusing runs held
  by an older humanize, MUST attach again whenever the runs let it go while it is followed, and
  MUST let go of a link no page has used for a while whose runs are idle, so that a host goes as
  it would with nobody reading; what runs where it holds no link MUST be asked of the daemon,
  which starts nothing.
- MUST ask for everything a page does to a run through its link -- starting and picking up,
  saying, answering, stopping and forcing, away, claiming and releasing, the board, side
  questions -- and MUST refuse a field a request does not take or a value of another kind
  before asking; what the runs refuse MUST be refused with their reason.
- MUST work out what it draws of a run with `runtime/watching`, from what it is told alone,
  and MUST hand a page every record kept and how everything stands, then each as it comes, as
  server-sent events a page resumes from the last one it heard; a page that heard another
  link's records MUST be told to start over.
- MUST ask a side question as `/btw` does, through `runtime/watching`'s `Btw`, of the btw agent
  or of one conversation's side copy -- of any epic's, one the runs hold no more carried on from
  where that epic kept it and told that epic rather than the run going -- MUST keep which are open and what was said in them for a
  page opened again, MUST close what it opened when the run it was about is replaced, and MUST
  NOT let a side question reach the run.
- MUST bound what it keeps of the runs' records, and what a page keeps, by count and by size.
- MUST read the runs written down, the flows on offer, what was spent and what humanize
  remembers through `runtime`'s one object, as the terminal interface reads them -- of the
  workspace a request names, the runs written down of every workspace or of one, and accounts,
  fallback and runtimes once for the machine.

### The page

- MUST do everything the terminal interface does to flows and runs, as it does it, beside what
  only a page can.
- MUST ask `coganchor.releases` which release of humanize is newest as it starts, in the
  background, and where it is newer than the one serving, MUST mark the machine and offer
  `Update` in its menu, which copies `hmz update`.
- MUST offer every workspace as a folder of its runs, newest first -- how each ended or that it
  is going, a chat `running` while its agent answers and `done` otherwise, short of failing --
  its task, flow and agents, what it spent and how long it took, how many sessions it
  opened, whether it can be picked up and where it is written down -- found by how it went, by
  workspace, by flow and by its task, a page at a time.
- MUST draw the run going as it happens: its sessions as lanes of turns over time, what each
  said as the terminal interface's transcript says it, its agents and who handed to whom, what
  it has spent against its budget and by model and kind of token -- never one lump over the
  kinds, a figure that is only a floor marked as one -- the questions it waits on a person for,
  the people it has and who holds each, its board -- a line the flow owns never offered to be
  changed -- the flows it is in, where each session works and where its harness went, and every
  frontend reading it; as a graph or, switched, as a list of its agents, the working first; and
  MUST offer, while it goes, every thing a person may do to it, never drawing over what somebody
  is typing while what it is about stands.
- MUST offer the transcripts the terminal interface keeps: one per session, one per agent
  across its sessions, one per person of what they are asked and answer, and one they all
  appear on -- a line said in one going to whose it is, and answering instead what that
  session's open turn asks.
- MUST name every agent of a run, going or written down, by its own name -- its sessions
  `<agent>/<n>`, its node, its transcript, its address and what is said to it -- the role it
  fills said only after the name, as the parameter it is; and a person by the role they answer.
- MUST open a chat started from it on its conversation, read as a chat app reads one: the task
  and every answer as the person's lines among the agent's, a line typed under it the next
  turn, what to say next never drawn as a question, and what the agent asks mid-turn asked at
  the end of the conversation with its answers there to pick.
- MUST draw a run written down: how it was set up, the tree of flows it called, its sessions,
  its turns and transcript read back out of its logs when asked for, an export, and picking it
  up where its flow says it can be.
- MUST let an epic exported anywhere be imported -- picked, dropped anywhere on the window, or
  named by its path on this machine at an address of its own -- as `runtime` imports one, and
  then open it, one named by its path on its Exomyth; MUST refuse one already here as a
  conflict naming it, and offer to open it; and MUST say why an imported epic cannot be
  picked up here, offering no picking up.
- MUST offer `Upload` on every epic, which backs it up now to the targets it was started with,
  else the defaults, answering at once with the targets it was queued for -- never waiting on a
  push -- and MUST say how its last backup to each target went, as it is read again.
- MUST offer `Download` on the Backup settings, which lists every epic a backup target holds --
  the target picked where there is more than one, fetched afresh off any other request, by
  machine and then by workspace, those already here marked -- and downloads one as an import
  does, opening it, a refusal said where it happened and a URL never shown with anything signed
  into it; and MUST say of an epic imported from a workspace this machine has not got why it
  cannot be picked up here.
- MUST serve a run's Exomyth timeline as `runtime/tracing` lays it out, and each span of it whole
  by its id, refusing an id it does not have as not found. A run that has ended MUST be laid
  out once until its record changes, the last few kept; a run still going MUST be laid out
  again on every request, answered with the tag that says whether the page has it already. A
  span's id MUST be read in the last timeline laid out of that run, and one asked for with a
  `layout` that is not that timeline's MUST be refused as a conflict.
- MUST draw any epic, going or written down, as its Exomyth: its timeline's processes as rows
  of their tracks under a ruler of time, each under the process that started it, folded or
  opened, with an arrow from each span that started one; moved over by keys, a wheel and a
  pinch as Perfetto is moved over; a span pointed at said in brief and one picked said whole
  with what it carried; a stretch of time picked summed by category; spans found by their
  words, one after the next; and, beside it, a flame graph of the stretch picked or the whole --
  each agent its stack, its sessions merged or apart, then its spans as they nest -- weighed by
  time, tokens in or out or count, zoomed by a click, and every slice name summed in a table
  sorted by any column. It MUST draw on one canvas, in the theme shown, only what shows, a
  frame of fifty thousand spans in well under a frame's time, sum them for the flame graph in
  well under a tenth of a second, and MUST read an epic going again while it is looked at and
  goes, asking only for what changed.
- MUST let a flow be set up in a workspace and saved without starting it, refused where a role
  has no agent or -- for every flow but chat -- nothing says what it may spend, and MUST save
  it as it is started.
- MUST start a run in the workspace picked -- any it serves, or one opened by its path,
  completed as it is typed -- as that workspace last set its flow up -- its agents,
  environments, params, budget, profiling and backup targets -- backed up to the default targets
  where it set none and none others are picked, and pick a run up, in its own workspace, as that run was started.
- MUST set an agent up as the terminal interface does, a step at a time: a CLI installed here
  that can fill the role, the account it runs as -- this machine's own or one made, and a way to
  make one -- a model known runnable as that account, asking the CLI where none is known yet and
  taking one typed where it cannot say, and an effort that model takes; and an environment by
  its backend, a runtime of it saved or made there, and its directory, completed as it is typed
  where it is on this machine. Each MUST come to what `-a` or `-e` spells.
- MUST offer the flows on offer in a workspace and what each declares, each installed out of
  an index with its release and the newer one its index lists, with updating, uninstalling and
  copying it into that workspace whole; and every flowverse -- whether its index is fetched or
  written into, the flows it lists, every release of each newest first, prereleases marked and
  the installed one marked -- with installing, switching to and uninstalling a release, and
  adding, fetching and removing a flowverse, removing what was installed out of it, asked
  first, a URL never shown with anything signed into it, and every manifest skipped named. It
  MUST fetch every index once as it starts, in the background and saying nothing, and say which
  installed flows have a newer release, and MUST NOT install, update or uninstall a flow while
  an epic runs on the machine.
- MUST offer what the runs spent by day and by flow -- of every workspace or of one -- and the
  pages `/settings` has: general, accounts -- correcting an account with what is left blank
  kept, never a value shown -- fallback, runtimes, backup -- every target, its policies and
  whether it is a default, a URL never shown with anything signed into it -- and the workspace,
  for any workspace it serves. A way in that runs a CLI's own sign-in MUST be said to need a
  terminal rather than run, and the ways in through the local LiteLLM gateway MUST be grouped as
  the terminal interface lists them, with the line that adds the `litellm` extra where it is
  missing.
- MUST name what it draws -- a button, a tab, a menu's choice, a heading, a field -- by a word
  or a short phrase, never a sentence, and MUST call a run of a flow an epic.
- MUST answer a right click as a desktop app does: with what can be done to the thing under it,
  in a menu of its own, and with the browser's own menu only where there is text to read or to
  write; and MUST NOT let what names the page's own parts be selected as text.
- MUST say in full, on hover and at once, whatever it cuts short -- a path above all -- and
  offer to copy what is worth copying.
- MUST let every path on this machine be browsed for, a directory at a time, as well as
  written; and every agent, place and runtime be set up a part at a time, as the terminal
  interface's forms set them up, never spelled whole.
- MUST draw in humanize's own type and in a theme: one of the pairs it comes with -- a light and
  a dark of humanize's own, Humanize Green, and of twelve more, each named for a mood and its
  colour -- or one made in the browser on Light or Dark, alone or with a light and a dark as a
  pair of its own -- any of its colours, and a picture, still or moving, behind any of the
  page's large planes -- chosen, or under Auto the one picked for the browser's light and the one
  for its dark, a pair at once or any two; MUST let a theme, or a pair with both its themes, be
  written out whole as a `.hmztheme` file and read back in, and MUST be usable on a screen as
  narrow as a phone's, and MUST hold still where motion is asked to be reduced.
- MUST let a theme be chosen only in Settings, never from the sidebar's menu, in the browser
  and the desktop app alike.
- MUST draw its chrome around the window controls of the desktop app when it is shown in it,
  and nothing else differently.
- MUST make every view an address that can be kept and opened again, the daemon it is of
  included, and MUST say, rather than hide, a refusal where it happened.

### Daemons

- MUST keep the daemons in Local's settings: `Local`, this machine's, always there and never
  removed or renamed, and every other an SSH host -- set up a part at a time as a runtime's ssh
  host is, or imported from the ssh config, those already added skipped -- named by letters,
  digits, `.`, `_` and `-`, `local` being Local's alone.
- MUST reach an SSH daemon by running `hmz web --no-open --attached --port 0` there over ssh, as
  its entry says, and forwarding a free port of this machine's loopback to the address it prints,
  holding ssh's input open so that it goes as this does; MUST try again, waiting longer each
  time, where it drops; and MUST stop everything it started there as it goes.
- MUST find the `hmz` there as a login shell finds it, `~/.local/bin` included, and where none is
  or it is not this one's version, install this one's with `uv tool install --force --python
  '>=3.12' 'hmz==<version>'`, getting uv there with astral's installer first where it has none,
  saying `Installing` while it does. It MUST NOT replace one while that machine's daemon holds
  running epics, nor where it cannot tell, saying why and reaching nothing; and a development
  build, `0.0.0`, MUST install nothing.
- MUST hand a page an SSH daemon's `/api/` under `/d/<name>/api/` of its own origin --
  server-sent events and uploads streamed through, and the key and cookie that daemon's `hmz web`
  takes put in here, never handed to the page -- and nothing else of it; `/d/local/api/` MUST be
  `/api/`. One not reached MUST be refused as unavailable, saying how it stands.
- MUST draw the sidebar's foot as the daemon bar: the daemon shown, its host, how it stands and
  how many epics it runs. A click on it MUST open its menu: `Daemon`, opening beside it every
  daemon and how it stands, one picked switched to, `Connect` on one that failed, and `Manage`
  for the daemons in Settings; then `Settings` and `Usage`, and nothing else but `Update` where
  a newer release is out.
- MUST show the daemon picked alone -- its workspaces, epics, flows, settings and everything
  else but the notifications -- carrying it in every address as `#/@<name>/...`, an address
  without one being Local's, and MUST draw everything again of the daemon switched to.
- MUST group Settings as `App`, what is this page's and Local's alone -- themes, daemons and
  notifications -- and `Daemon`, every page a daemon keeps -- general, accounts, fallback,
  runtimes, backup, workspace and usage -- read and written of the daemon picked on them, the
  one shown at first. Each Daemon page MUST offer `Batch apply`, which writes what that page
  saves to every daemon picked and says how each went; MUST NOT carry what only a secret sets,
  and MUST say so where it is left out.

### Notifications

- MUST tell, of this machine's runs, every epic that ends -- `done`, `stopped`, or `failed`
  where it failed, crashed, ran out of budget or was refused -- every question a flow asks a
  person, `asked`, and every other flow waiting on what to say next, `listening`; of a chat,
  each turn done as `done` and its end only where it failed or ended a turn not yet told,
  never `stopped`: each a notice, numbered
  in order and kept to a bound, served after a number and as server-sent events resumed from the
  last heard, `hmz web` reached over ssh included. It MUST work them out of each host's status as
  the daemon answers it, never by attaching, so that no host is kept for them.
- MUST gather, on Local alone, the notices of every daemon reached into one list of
  notifications, each naming its daemon and whether it is read, the newest few hundred kept, and
  MUST keep out of it, before it is kept or sent, every kind turned off.
- MUST offer them, whichever daemon is shown, behind a bell with how many are unread: each
  opening its epic on its daemon, marked read one or all, and cleared; and each new one as a card
  that goes after a while.
- MUST tell the system of a new one where the page is hidden or not focused, unless that is
  turned off: in the desktop app by its `notify`, and in a browser by its notifications, leave
  for which is asked only by a click in Settings.
- MUST keep which kinds are told and whether the system is in Local's settings alone, never a
  daemon's.
