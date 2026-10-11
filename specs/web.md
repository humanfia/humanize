# `web`

The web interface `hmz web` serves: every workspace's runs on this machine, drawn in a browser on
it. Where the terminal interface is about the directory it is opened in, this is about the
machine, as the daemon is: one more frontend of the runs each workspace's host holds, beside
every terminal interface opened on them. It runs flows and reads them back, defines no flows,
drives no agents and keeps no store of its own.

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
  here may be; MUST answer what it refuses as JSON saying why in one sentence, with a status
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
  is going, its task, flow and agents, what it spent and how long it took, how many sessions it
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
  appear on -- a line said in one going to whose it is.
- MUST draw a run written down: how it was set up, the tree of flows it called, its sessions,
  its turns and transcript read back out of its logs when asked for, an export, and picking it
  up where its flow says it can be.
- MUST let a flow be set up in a workspace and saved without starting it, refused where a role
  has no agent or -- for every flow but chat -- nothing says what it may spend, and MUST save
  it as it is started.
- MUST start a run in the workspace picked -- any it serves, or one opened by its path,
  completed as it is typed -- as that workspace last set its flow up -- its agents,
  environments, params, budget and profiling -- and pick a run up, in its own workspace, as
  that run was started.
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
  kept, never a value shown -- fallback, runtimes and the workspace, for any workspace it
  serves. A way in that runs a CLI's own sign-in MUST be said to need a terminal rather than
  run.
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
- MUST draw in humanize's own colours and type, light or dark as the browser asks or as chosen,
  MUST be usable on a screen as narrow as a phone's, and MUST hold still where motion is asked
  to be reduced.
- MUST draw its chrome around the window controls of the desktop app when it is shown in it,
  and nothing else differently.
- MUST make every view an address that can be kept and opened again, and MUST say, rather than
  hide, a refusal where it happened.
