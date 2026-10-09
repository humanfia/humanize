# `web`

The web interface `hmz web` serves: a workspace's runs drawn in a browser on this machine. It is
one more frontend of the runs a host holds there, beside every terminal interface opened on
them; it runs flows and reads them back, defines no flows, drives no agents and keeps no store
of its own.

## API

```python
# __init__.py
@contextlib.contextmanager
def listening(*, port: int = 0, apart: bool = True) -> Generator[Site]: ...
def serve(
    *,
    port: int = 0,  # 0 for any free one
    apart: bool = True,  # the runs held by this workspace's host, or in this process
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

- MUST attach through `daemon` as every frontend does -- to the host holding this workspace's
  runs, starting one where none is, or to runs held in its own process where they are not held
  apart -- refusing runs held by an older humanize, and MUST attach again whenever the runs let
  it go, for as long as it is served.
- MUST ask for everything a page does to a run through its link -- starting and picking up,
  saying, answering, stopping and forcing, away, claiming and releasing, the board, side
  questions -- and MUST refuse a field a request does not take or a value of another kind
  before asking; what the runs refuse MUST be refused with their reason.
- MUST work out what it draws of a run with `runtime/watching`, from what it is told alone,
  and MUST hand a page every record kept and how everything stands, then each as it comes, as
  server-sent events a page resumes from the last one it heard; a page that heard another
  link's records MUST be told to start over.
- MUST ask a side question as `/btw` does, through `runtime/watching`'s `Btw`, of the btw agent
  or of one conversation's side copy, MUST keep which are open and what was said in them for a
  page opened again, MUST close what it opened when the run it was about is replaced, and MUST
  NOT let a side question reach the run.
- MUST bound what it keeps of the runs' records, and what a page keeps, by count and by size.
- MUST read the runs written down, the flows on offer, what was spent and what humanize
  remembers through `runtime`'s one object, as the terminal interface reads them.

### The page

- MUST offer the runs of this directory newest first -- how each ended or that it is going,
  its task, flow and agents, what it spent and how long it took -- found by how it went, by
  flow and by its task, a page at a time.
- MUST draw the run going as it happens: its sessions as lanes of turns over time, what each
  said as the terminal interface's transcript says it, its agents and who handed to whom, what
  it has spent against its budget, the questions it waits on a person for, the people it has
  and who holds each, its board and the flows it is in; and MUST offer, while it goes, every
  thing a person may do to it, never drawing over what somebody is typing while what it is
  about stands.
- MUST draw a run written down: how it was set up, the tree of flows it called, its sessions,
  its turns and transcript read back out of its logs when asked for, an export, and picking it
  up where its flow says it can be.
- MUST start a run as this directory last set its flow up -- its agents, environments, params,
  budget and profiling -- and pick a run up as that run was started.
- MUST offer the flows on offer and what each declares, what the runs here spent by day and by
  flow, and the pages `/settings` has: general, accounts, fallback, runtimes and this
  workspace. A way in that runs a CLI's own sign-in MUST be said to need a terminal rather than
  run.
- MUST draw in humanize's own colours and type, light or dark as the browser asks or as chosen,
  MUST be usable on a screen as narrow as a phone's, and MUST hold still where motion is asked
  to be reduced.
- MUST make every view an address that can be kept and opened again, and MUST say, rather than
  hide, a refusal where it happened.
