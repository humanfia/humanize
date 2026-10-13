---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Web reference

The web interface `hmz web` serves: every workspace's runs on a machine, drawn in a browser on
it, as one more [frontend](/reference/daemon#hosting) of the runs each workspace's host holds. Its command
line, how a browser is let in, what is refused, the page's addresses, every route the page
calls, and the stream it follows. Package `hmz.web`. Notation:
[Conventions](/reference/#conventions). The task-by-task guide is
[In a browser](/user/web).

The server is the standard library's `http.server`, and the page is plain ES modules served as
they are: `hmz web` installs nothing beyond `hmz` and builds nothing.

## Command line {#command-line}

```text
hmz web [--port <port>] [--no-open] [--attached]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--port <port>` | `0` | The port to listen on, on `127.0.0.1` and, where this machine has IPv6, on `::1` too. `0` picks any free one on both. |
| `--no-open` | off | Print the address and open no browser. |
| `--attached` | off | Stop once standard input closes. |

Once listening it prints one line to stdout, flushed, and serves until `SIGINT`, `SIGTERM` or
`SIGHUP` -- or, with `--attached`, until standard input closes, so that the program that
started it takes it down by exiting, crashed or killed included. Each stops it the same way,
exiting `0`: every stream ends, the port is let go of, and the page below is removed. A
`SIGTERM`, `SIGHUP` or closed stdin while it stops is ignored and a second `SIGINT` cuts the
stopping short; a signal already ignored when it starts, as a hangup is under `nohup`, stays
ignored.

Unless `--no-open` was given, or there is no desktop to open a browser on (Linux with neither
`DISPLAY` nor `WAYLAND_DISPLAY`), it also opens a browser, through Python's `webbrowser`, on a
page that only this account can read -- `web-<port>.html` in this machine's own directory,
removed when it stops -- which sends the browser on to the address: the key is never on a
browser's command line, which every account on the machine can read.

```text
hmz web: http://127.0.0.1:<port>/?key=<key>
```

### Where the runs are held {#where-runs-are-held}

| Condition | Runs |
| --- | --- |
| `HUMANIZE_DAEMON` stripped and lower-cased is `off`, `0` or `no` | Held in this process, a host per workspace; `hmz web` stopping closes them. |
| anything else | Held by each workspace's host process, found or started through [`hmz.daemon.attach`](/reference/daemon#module), tried **3** times **0.5 s** apart. They outlive `hmz web`. |

`hmz web` serves every workspace wherever it is started; the directory it started in is only the
one a new epic is offered first. It attaches to a workspace's host as one frontend, named
`browser` (`#2`, `#3`… beside another of that name), of `kind` `web`, only while a page follows
that workspace or asks its runs something, and lets go **60 s** after the last of that once its
runs are idle -- so that a host with nothing to do goes, as it would with nobody reading. What
runs where it holds no link it asks of the daemon every **5 s**, which starts nothing. Whenever a
followed host lets it go, it attaches again **2 s** later; a page following the stream is then
told to [start over](#stream).

### Exit statuses {#exit-statuses}

| Status | stderr | When |
| --- | --- | --- |
| `0` | — | Interrupted (`SIGINT`) after it was serving. |
| `1` | `hmz: the web interface cannot be served: <OSError>` | The port could not be listened on. |

A workspace whose runs an older humanize holds, or whose runs cannot be reached, is refused where
a page asks for them -- `409` or `503`, saying why -- and every other workspace is served.
| `2` | argparse's usage error | The line was wrong. |

## Letting a browser in {#sign-in}

| Step | What happens |
| --- | --- |
| The key | 32 random bytes, URL-safe base64 (43 characters), made afresh each time `hmz web` starts, and only ever printed in the address. |
| `GET /?key=<key>` | `303` to `/`, setting `hmz-<port>=<key>; HttpOnly; SameSite=Strict; Path=/`. A key that is not this server's: `403`. |
| Every request under `/api/` | Answered only where the cookie carries the key; otherwise `401`, and the page says `This browser is not let in.` |
| The page's own files | Served without the cookie; they hold nothing of the runs. |

## What is refused {#refused}

Every refusal is JSON, `{"error": "<one sentence>"}`, with the status below. They are checked in
this order.

| Status | Condition | `error` |
| --- | --- | --- |
| `403` | The connection did not come from a loopback address | `Open the address hmz web printed, on the machine it runs on.` |
| `401` | `/api/…` without the key's cookie | `Open the address hmz web printed to let this browser in.` |
| `403` | `/api/…` that the browser says came from another page: `Sec-Fetch-Site` other than `same-origin` or `none` (a `POST`: other than `same-origin`); or, from a browser that sends no `Sec-Fetch-Site`, an `Origin` whose host and port are not the `Host` asked, by `http` or `https` -- for a `POST`, a missing `Origin` too | `Use this server's own page to make this request.` |
| `404` / `405` | No route of that path / none for that method | `There is nothing here by that name.` |
| `415` | `POST` whose `Content-Type` is not `application/json` -- nor, to [`POST /api/runs/import`](#api-import), `application/vnd.hmz.epic+gzip` or `application/octet-stream` | `Send JSON.` |
| `411` | `POST` whose `Content-Length` is not a number, or is below `0` | `Say how long what is sent is.` |
| `413` | `POST` body over **1 MiB** -- a file sent to `POST /api/runs/import`, over **2 GiB** | `That is more than a request here may send.` |
| `400` | Body not a JSON object | `Send JSON.` or `Send a JSON object.` |
| `405` | A method other than `GET` outside `/api/` | `Only the page's own files are here.` |
| `400` | A field a request does not take, or of another type | e.g. `start takes no rounds.`, `say takes text as text.` |
| `409` | The runs refused the request | Their own sentence, as [`Refused`](/reference/sdk#refused) gives it. |
| `503` | The runs could not be asked | `The runs could not be asked: <why>` |
| `500` | Anything else, with a traceback on `hmz web`'s stderr | `Something went wrong here: <why>` |

Which name the server was reached by is not asked: a port forwarded over ssh, or proxied on to
it by a server on this machine, is answered under whatever name the browser used, once that
browser has been let in there with the key. A web page elsewhere that points a name of its own
at `127.0.0.1` reaches the server, but its browser hands it that name's cookies only, never the
key's, so it is answered `401`. A page served from another port of this
machine is the same site to a cookie, so its browser sends the cookie along; it is refused all
the same, by what the browser says of where the request came from. A connection that says
nothing for **60 s** is closed.

## The page {#page}

The files under `hmz/web/static/` are served as they are, `/` being `index.html`. Every answer
carries `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and
`X-Frame-Options: DENY`, a weak `ETag` and `Cache-Control: no-cache` (`304` when it has not
changed). The page itself carries:

```text
Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self';
  script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none';
  form-action 'self'
```

Each view is an address after `#`, so it can be kept and opened again:

| Address | View |
| --- | --- |
| `#/new[?workspace=&flow=&resume=<name>]` | A new epic: in the workspace picked (where `hmz web` started by default), the flow picked, or the epic named picked up. The page opens here. |
| `#/live` | The epic going; its address becomes `#/epics/<name>` once it is written down -- a `chat`'s, its conversation's, `#/epics/<name>/sessions/assistant%2F1`, once that opens. |
| `#/epics/import?path=<file>` | Imports the `.hmzepic` at that whole path on this machine, as [`POST /api/runs/import`](#api-import) does -- in the desktop app as it is opened; in a browser, which any page elsewhere could have sent here, once **Import** under the path is pressed -- then stands in for itself with `#/epics/<name>/exomyth`, its [Exomyth](/user/web#exomyth) -- going back does not import it again; a refusal is said in its place, with the epic's own address where it is here already. What the desktop app is to open a `.hmzepic` with. |
| `#/epics/<name>` | One epic, by its directory's name, drawn as a graph of its agents; live where it is the epic going. |
| `#/epics/<name>/agents/<role>` | The same graph, with that agent picked out. |
| `#/epics/<name>/sessions/<agent>/<n>` | The thread of the `n`-th session that agent opened, as the epic going names it (`/` written `%2F`). |
| `#/epics/<name>/logs[/<role>]` | The log every agent and person appears on; or one agent's, across its sessions; or one person's, what they are asked and answer. |
| `#/epics/<name>/exomyth[?tab=flame]` | The epic's [Exomyth](/user/web#exomyth): its timeline, or its flame graph. |
| `#/flows[?workspace=&flow=]` | The flows on offer in a workspace, one opened. |
| `#/flows?tab=verses[&verse=]` | The flowverses, one opened. |
| `#/search[?status=&flow=&q=&offset=]` | A dialog finding epics. `status`: how it went, `running` or `unfinished`. |
| `#/download[?target=]` | A dialog downloading an epic out of a backup target: the first in settings without `target`. |
| `#/settings/<page>[?days=]` | A dialog: `general`, `themes`, `accounts`, `fallback`, `runtimes`, `backup`, `workspace`, `usage`, `daemons` or `notifications`; `days` is how far `usage` looks back (7, 30, 90 or 365; default 30), by UTC day. |

Every address above is of one daemon. `#/@<name>/<view>` -- `#/@local/new`, `#/@gpu/epics/<name>`
-- is that view of the daemon named; an address naming none is Local's, as every address
written before daemons were is. The page shows only the daemon its address names: every link
it draws keeps the `@<name>` the address carries, and going to another daemon's address draws
the view and the sidebar again, of that daemon, closing what the page streamed of the last.
Everything the page asks of a daemon is under `/d/<name>/api/…`, Local's `/d/local/api/…`
being the same as `/api/…`; what is the same whichever daemon the page is on --
`/api/daemons…` and `/api/notifications…` -- is asked of Local, unscoped.

The page keeps a few conveniences in the browser's `localStorage`, each forgotten without
harm: the colours chosen as `hmz-theme` (`light`, `dark`, or absent for the system's), a sidebar
folded away as `hmz-sidebar`, a side panel closed as `hmz-panel`, which epics are opened out
in the sidebar as `hmz-opened` and which workspaces folded away as `hmz-shut`, and whether an
epic's agents are drawn as a list as `hmz-shape`.

## API {#api}

JSON in and out. A `POST` takes a JSON object, `{}` where nothing is sent.

### The runs held {#api-held}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/held` | | `machine` (this machine's name), `here` (where `hmz web` started), `version`, `newer` (a newer release of `hmz` PyPI lists, asked as `hmz web` starts and at most once a day, or `""`), `running` (`{workspace: run}`: the [`run` snapshot](/reference/daemon#snapshots) of each workspace whose epic is going, or what its host's `status` says of it) |
| `GET /api/held/stream` | `?workspace=`; `Last-Event-ID` header, or `?last=` | [The stream](#stream) of that workspace's runs, attaching to them |
| `POST /api/held/start` | `workspace`; `flow`, `task` (both required); `agents`, `envs` (`{role: spec}`); `params`, `budget` (object or `null`); `profile_flow`, `profile_environment` (bool); `resume` (bool, or an epic); `backup` (target names, `[]` for none; `null`, the default, for the defaults) | The host's answer: `run` |
| `POST /api/held/say` | `text`; `to` (`""`, an agent, `<agent>/<n>`, or `outworlder:<role>`, routed as [`say` routes it](/reference/daemon#say-routing)) | The host's answer |
| `POST /api/held/answer` | `question`, `text` | The host's answer |
| `POST /api/held/stop`, `/force` | | The host's answer |
| `POST /api/held/afk` | `on` (bool); `role` | The host's answer |
| `POST /api/held/claim` | `role`; `take` (bool) | The host's answer |
| `POST /api/held/release` | `role` | The host's answer |
| `POST /api/held/board` | `key`; `value` (`""` removes the line) | The host's answer |
| `GET /api/btw` | `?workspace=` | `open` (the conversations a side one is open on, `""` the btw agent's) and `said` (each question answered since, oldest first, as `POST` answers it; the last **200**) |
| `POST /api/btw` | `workspace`; `question`; `to` (`""` the btw agent, or `<agent>/<n>`); `epic` (the epic `to` is of: a session of one the runs hold no more is carried on from where that epic kept it, its conversation answered as `<epic>/<agent>/<n>`) | `to`, `question`, `answer`, and `asked`: `[{to, question}]`, each session the btw agent asked on the way |
| `POST /api/btw/leave` | `workspace`; `to`, or nothing for every side conversation | `{"ok": true}` |

Every request about one workspace's runs names it as `workspace` -- in the query of a `GET`, in
the body of a `POST` -- a whole path, `~` and all; with none it is the one `hmz web` started in.
A path that is not a directory is refused `404`, one that is not whole `400`. A workspace is
attached to only while a page follows its stream or asks its runs something, and let go of once
nothing has for **60 s** and its runs are idle.

Each `POST /api/held/<do>` is the [request](/reference/daemon#requests) of that name, sent down
this frontend's link as given. A side question is asked as [`/btw`](/reference/tui#btw-command)
asks one, through the same side conversations: a second question to one still answering is
`409`, and a run starting closes them.

### The runs written down {#api-runs}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/runs` | `workspace` (only its runs; every workspace's without), `status`, `flow`, `q` (in its task, flow or name), `offset` (`0`), `limit` (`50`, at most `200`) | `runs` (rows, newest first), `total`, `offset`, `limit`, `counts` (`{how: n}` over every run), `flows` |
| `GET /api/runs/<name>` | | Of whichever workspace it ran in: the row (`workspace` among it), and `at`, the whole `task`, `ref`, `agents` (`role`, `runs`, `backend`, `model`, `effort`, `provider`), `sessions`, `envs`, `used`, `params`, `budget`, `picked_up`, `profile_flow`, `profile_environment`, `picks_up` (whether it can be picked up), `foreign` (why one [imported](/user/export#importing-a-run) cannot be picked up here, or `""`), `calls` (the tree of flows it called) |
| `GET /api/runs/<name>/trace` | | `sessions`: each with its `key`, `agent` and `actions` (`category`, `name`, `at`, `start`, `seconds`, `args`), read out of the run's logs as [tracing](/reference/tracing) reads them; the last **4** of runs that have ended kept, until the run's journal changes |
| `GET /api/runs/<name>/timeline` | | The run's [Exomyth timeline](/reference/tracing#timeline): compact JSON, with an `ETag`. A run that has ended is laid out once, the last **4** kept until its journal changes; a run going is laid out again on every request |
| `GET /api/runs/<name>/timeline/span/<id>` | `layout` (the timeline's own) | [One span](/reference/tracing#timeline-span) of the last timeline laid out of the run, whole; `404` for an id it does not have, `409` where `layout` is not the last timeline's |
| `GET /api/runs/<name>/bundle` | | The run's [export](/reference/tracing), as a download |
| `POST /api/runs/import` | A file, or `path` -- see [Importing](#api-import) | `201`: `name`, `workspace`, `resumable`, `why` |
| `POST /api/runs/<name>/backup` | `to` (target names; the run's own, else the defaults, without) | `queued`: the targets it was [backed up](/user/backups) to, on threads of their own -- nothing waits for the push; `400` for a target there is none of, `409` where there is no target at all |
| `GET /api/backups/<target>/epics` | | `epics`, newest first: each `key` (`<machine>/<workspace>/<epic>`), `machine`, `workspace`, `epic`, `flow`, `task`, `began`, `ended`, `how`, `head`, and `here` (whether this machine has an epic of that name). Fetched afresh, so it can take a while; `400` for a target there is none of, `502` where the repository could not be reached |
| `POST /api/backups/<target>/pull` | `key` | `name`: the epic, [downloaded](/user/backups#downloading-an-epic) as an import is; `400` for one already here, a key naming nothing there, or a target there is none of; `502` where the repository could not be reached |
| `GET /api/usage` | `days` (`30`; 1 to 365); `workspace` (only its runs) | `days` (per UTC day, oldest first), `flows` (costliest first), `ended` (`{how: n}`), `whole`: each with `runs`, `cost`, `output_tokens`, `seconds`, and `money`, `tokens`, `worked` as the terminal interface says them |

A row is `name`, `flow`, `task` (its first line, cut at 240 characters), `began`, `ended`,
`how` (as the run ended; `running` for a run going -- held by a host, or by another process such
as `hmz exec` -- and `unfinished` for one whose process went before it said),
`agents` (`[{role, runs}]`), `sessions` (a count), `resumable`, `held` (whether it is the run a
host is going with, which the page follows live and can stop), `spent`: what its budget counted as it ended, or `null`, `backup` (the targets it was
started with) and `backed` (`{target: {at, ok, error, why}}`: how its last backup to each
went). A run of no such name is `404`.

#### Importing {#api-import}

`POST /api/runs/import` reads an [exported](/user/export) epic back in, as
[`Epics.imported`](/reference/sdk) does: under the workspace it says it ran in, whichever that
is. It is sent one of two ways, each from the page's own origin as every write is:

| `Content-Type` | Body | Also |
| --- | --- | --- |
| `application/vnd.hmz.epic+gzip` or `application/octet-stream` | The `.hmzepic`'s bytes, at most **2 GiB**, with its `Content-Length` | `X-Hmz-Filename`: the file's name, percent-encoded (`encodeURIComponent`) -- its last part is kept, and must end `.hmzepic` |
| `application/json` | `{"path": "/whole/path/to/<name>.hmzepic"}`: a file already on this machine | |

A file sent is written into a directory of its own under this machine's own directory, and
removed once it has been answered.

| Status | Body | When |
| --- | --- | --- |
| `201` | `name` (the epic's), `workspace` (where it ran, resolved), `resumable` (whether it can be picked up here), `why` (why an imported epic cannot be, or `""`) | Imported |
| `400` | `error` | Not named `.hmzepic`, not a gzipped tar, not one epic holding its record and manifest, holding anything but plain files under it, saying no workspace; a `path` that is not whole, or no file; no `X-Hmz-Filename` |
| `409` | `error`, `name` | An epic of that name is here already: `name` is it, at `#/epics/<name>` |
| `413` | `error` | Over **2 GiB** |

Every `error` but the last is the runtime's own sentence, e.g.
`20261012-101500-ab12 is already here, at /…/epics/-work-app/20261012-101500-ab12.`

### Flows {#api-flows}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/flows` | `workspace` | `flows` (`[{whose, name, about}]`), `flow` (the one that workspace opens on), `running` (the flows going, `[{ref, name, depth, since, task}]`) |
| `GET /api/flow` | `name`; `workspace` | What it declares: `ref`, `description`, `resumable`, `resumes`, `agents` (`name`, `required`, `auto`, `harness`, `permission`, `skills`, and `clis`: the CLIs installed here that can fill it), `envs`, `params` (its JSON schema), and `remembered` (what that workspace last set it up with: `agents`, `envs`, `params`, `budget`, `profile_flow`, `profile_environment`, and `backup`, the target names or `null` for the defaults). `404` for a name that is not one of `GET /api/flows`' -- a path or a repository is never loaded -- and for one that will not load. |
| `GET /api/backends` | | `clis`: each CLI installed here, `{cli: {accounts: [{name, models: [{name, efforts}], asked}]}}`, this machine's own account first as `""`; `installable`: `{cli: [{name, efforts}]}`; `envs`: every backend `-e` takes |
| `GET /api/workspaces` | | `here`, and `workspaces`: each `path`, `name`, `epics` (how many), `last` (when the latest began), `running`, `here`, `there` (whether the directory is still there) -- where `hmz web` started first, then those going, then where epics ran, newest first, then those only written down in the settings |
| `POST /api/workspaces` | `workspace` | Writes it down in the settings: `kept` (its whole path), and as `GET` |
| `POST /api/workspaces/forget` | `workspace` | Forgets what it was set up with, which stops it being offered where no epic ran there; as `GET` |
| `POST /api/flows/setup` | `workspace`; `flow`, and as `POST /api/held/start` takes them `agents`, `envs`, `params`, `budget`, `profile_flow`, `profile_environment`, `backup` (`null` or absent leaves what was saved) | Writes down what that workspace runs the flow with, as `/flow` saves it -- which a start writes too; as `GET /api/flow`. `400` where a role has no agent or, but for `chat`, there is no budget |
| `GET /api/flowverses` | | `verses` (`name`, `url` with nothing signed into it, `fetched`, `fixed`, `edited`, `installed`), `installed` (`flow`, `verse`, `listed`, `version`, `repo`, `ref`), `updates` (`flow`, `from`, `to`). Every index is fetched once as `hmz web` starts, in the background, but one written into |
| `GET /api/flowverses/<name>` | | Its index: `flows` (`listed`, `flow` as installing takes it, `installed`, `releases`: `version`, `description`, `prerelease`, `license`, `repo`, `dependencies`, newest first) and `skipped` (`at`, `why`) |
| `POST /api/flowverses` | `url`; `name` | Clones the index and keeps it; `said`, and as `GET` |
| `POST /api/flowverses/fetch`, `/remove` | `name` | Fetches it again, or removes it and what was installed out of it; `said`, and as `GET` |
| `POST /api/flowverses/install` | `flow`; `version` (`""` for the newest that is not a prerelease) | Installs, updates or switches it, with what it needs; `said`, and as `GET` |
| `POST /api/flowverses/uninstall` | `flow` | `said`, and as `GET`. Installing, uninstalling and removing are refused `409` while an epic runs on the machine |
| `POST /api/flows/fork` | `flow`; `workspace` | Copies it whole into that workspace's own flows: `said`, `at` |
| `GET /api/files` | `at` (a directory, `~` and all; `~` without), `files` (`1` to list files beside directories), `hidden` (`1` to list what starts with a dot) | `at` as written from `~`, `whole`, `up` (the one above, or `""`), `entries` (`name`, `dir`, directories first, at most **500**), `more`. `404` for one that cannot be read |
| `GET /api/paths` | `typed` (query): a path being written, `~` and all | `paths`: the directories it could become, spelled as typed, each ending in `/`, at most 50 |

### Settings {#api-settings}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/settings` | `workspace` | `workspace`, `flow`, `btw`, `details`, `reports` (`null` where never answered), `flows` (set up here), `backup` (`targets`: each `name`, `url` with nothing signed into it, `branch`, `policies`, `every`; `defaults`) |
| `POST /api/settings` | any of `btw` (text), `details`, `reports` (bool), `backup` (`{targets, defaults}`, every one of them; a `url` sent back as `GET` showed it keeps the one written) | As `GET`; `400`, and nothing written, for a target that is not one |
| `POST /api/settings/forget` | `workspace` | `forgot` (whether there was anything), and as `GET` |
| `GET /api/accounts` | | `accounts` (`cli`, `name`, `way`, `sets`, `made`, `models`, `asked`, `serves`) and `backends` (each CLI's `ways`: `name`, `about`, `terminal`, `asks`) |
| `POST /api/accounts` | `cli`, `name`, `way`; `answers` (`{variable: value}`) | As `GET`. A way whose `terminal` is true is refused: it runs the CLI's own sign-in. |
| `POST /api/accounts/remove` | `cli`, `name` | As `GET` |
| `POST /api/accounts/correct` | `cli`, `name`; `answers` (`{env: value}`, what is left out kept) | Writes it again with what changed, never answering with a value; as `GET`. `400` for a way that asks nothing of that name, and for one that runs the CLI's own sign-in, which a terminal corrects |
| `POST /api/accounts/models` | `cli`; `name` (`""` for this machine's own) | As `GET`, once the CLI has said what it runs; `502` where it would not say |
| `POST /api/accounts/copy` | `cli`, `name`, `into` | As `GET` |
| `GET /api/fallbacks` | | `steps` (`spec`, `to`, `tries`, `policy`, `timeout`), `policies`, `default`, `places` |
| `POST /api/fallbacks` | `spec`; `to` (places, in order); `tries`; `policy`; `timeout` (seconds, `0` none) | As `GET` |
| `POST /api/fallbacks/clear` | `spec` | As `GET` |
| `GET /api/runtimes` | | `runtimes` (each as it is written down) and `blanks` (each backend's fields, as a new one holds them) |
| `POST /api/runtimes` | `backend`, `name`, `fields`; `replace` (bool) | As `GET` |
| `POST /api/runtimes/remove` | `backend`, `name` | As `GET` |
| `POST /api/runtimes/check` | `backend`, `name` | What it said: `reached`, `said`, `home`, `cpus`, `memory`, `gpus`, `usable`, `gpu_memory`, `runtimes`, `version`, `short`, `nodes` |
| `GET /api/runtimes/hosts` | | `hosts` your ssh config names (`alias`, `host`, `user`, `port`, `identity_files`, `proxy_jump`, `saved`) |
| `POST /api/runtimes/import` | `names`; `update` (bool) | As `GET /api/runtimes` |
| `GET /api/daemons` | | `daemons`: `Local` first, then each ssh daemon (`name`, `label`, `host`, `user`, `port`, `identity_file`, `proxy_jump`, `options` as `[keyword, value]` pairs, `alias`, `config`) with `state`, `detail` and `version` |
| `POST /api/daemons` | `name`, `fields`; `replace` (bool) | As `GET` |
| `POST /api/daemons/remove` | `name` | As `GET` |
| `GET /api/daemons/hosts` | | `hosts` your ssh config names that are not daemons yet (`alias`, `name`, `host`, `user`, `port`, `identity_files`, `proxy_jump`) |
| `POST /api/daemons/import` | `aliases` | As `GET`, and `added`: the daemons made, skipping any already there |
| `GET /api/daemons/{name}/state` | | `state` (`idle`, `connecting`, `installing`, `up` or `failed`), `detail` (what was said last, such as uv's last line) and `version` (its `hmz`'s) |
| `POST /api/daemons/{name}/connect` | | As `GET …/state`, once it is being reached: its `hmz` installed at this version where none or another is and it holds no running epics, `hmz web --no-open --attached` started there over ssh, and a port of this machine forwarded to it |
| any `/d/{name}/api/…` | as `/api/…` there | What that daemon's own interface answers, passed through as it comes -- a stream included -- signed in with its key, which no page sees; `503` while it is not up, `404` for a daemon not written down |

An account is listed by the names of the variables it sets (`sets`), never by a value.

### Notices {#api-notices}

What happened to this machine's runs worth telling somebody about. They are worked out of each
workspace's host [`status`](/reference/daemon#status), asked every **2 s** without attaching to
any host, so a host goes as it would with nobody reading. Anything already standing when
`hmz web` starts is not news.

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/notices` | `after` (an `id`; `0`, the default, for every one kept) | `notices` (those kept after it, oldest first; the last **200**), `last` (the newest `id`, `0` for none); `400` where `after` is not a whole number |
| `GET /api/notices/stream` | `Last-Event-ID` header, or `?last=` | `text/event-stream`: each `notice` event's `id` is its `id` and its data the notice, from after the one named (without one, from now on), then each as it comes; `: quiet` after **15 s** of nothing |

A notice is `id` (a whole number, larger than any before it, on this machine too after
`hmz web` starts again), `kind`, `workspace`, `epic`, `flow`, `task`, `role`, `text` and `at`
(Unix seconds):

| `kind` | When | `role`, `text` |
| --- | --- | --- |
| `done` | An epic ended done | `""`, `""` |
| `failed` | An epic ended failed, crashed, refused or over its budget | `""`, why |
| `stopped` | An epic was stopped | `""`, `""` |
| `asked` | A flow asks a person a question (mode `ask`) | The role asking, the question |
| `listening` | A flow waits for what to say next: a chat between turns (mode `listen`) | The role asking, what it asks |

### Notifications {#api-notifications}

What every daemon's notices come to, served by the interface a page is open on alone: its own
machine's as they are heard, and each SSH daemon's while it is reached, off the
`/api/notices/stream` that daemon's own interface serves -- from what it says once first
reached, and from where it was last heard after that. A notification is the notice, with its own
`id` (counted from `1` each time `hmz web` starts), `daemon` (`local` or the daemon's name) and
`read`. The last **200** are kept, in memory.

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/notifications` | | `items` (newest first), `unread` (how many are not read) |
| `GET /api/notifications/stream` | `Last-Event-ID` header, or `?last=` | `text/event-stream`: a `notification` event, `id` its `id`, for each kept after the one named -- every one kept where it names one later than any here -- then each as it comes; with none, from now. `: quiet` after **15 s** of nothing |
| `POST /api/notifications/read` | `ids` (a list), or `all: true` | As `GET` |
| `POST /api/notifications/clear` | | As `GET`, with nothing kept |
| `GET /api/notifications/settings` | | `kinds` (`{done, failed, stopped, asked, listening}`: whether each is told) and `system` (whether the page asks the system to show them too), as [`notifications`](/reference/settings#machine-settings) holds them |
| `POST /api/notifications/settings` | any of `kinds` (any of those five, each a bool), `system` (bool) | As `GET`; `400`, and nothing written, for anything else |

A notice of a kind turned off is never kept nor sent. Which kinds are told is read afresh for
every notice, so a change takes effect at once.

## The stream {#stream}

`GET /api/held/stream` answers `text/event-stream`, starting with `retry: 2000`. Each event is
named, its data one JSON object:

| Event | `id` | Data |
| --- | --- | --- |
| `hello` | | `epoch` (this link's), `me` |
| `record` | `<epoch>:<seq>` | One [history record](/reference/daemon#history-records), in order |
| `standing` | | One [snapshot](/reference/daemon#snapshots), each time it changes |
| `figures` | | What the run has done and cost, worked out by `hmz.runtime.watching`, at most once a second |
| `gone` | | `why`: the runs let this link go. The stream ends. |
| `again` | | `{}`: the link changed, or the server is stopping. Start over. |

A stream starts with every record kept (the latest **20,000**, and about **32 MiB** of them) after the one named by
`Last-Event-ID`, or `?last=`, where that names this link's epoch, and from the first kept
otherwise; then how everything stands; then each as it comes. A comment, `: quiet`, is sent
after **15 s** of nothing.

`figures` holds `run`, `elapsed` and `lasting` (the clock), `ended`, `agents` and `sessions`
(each `name`, `turns`, `working`, `since`, `lasting`, `used`, `tokens`, `under`), `handovers`
(`[{from, to, count}]`), `latest`, `spending` (per model: `tokens`, `rate`, `dollars`, `money`,
`kinds`), `reckoning` (per kind: `tokens`, `whole`) and `tally`: the two lines the terminal
interface draws under a run.

## Module `hmz.web` {#module}

```python
@contextlib.contextmanager
def listening(*, port: int = 0, apart: bool = True) -> Generator[Site]: ...
def serve(*, port: int = 0, apart: bool = True, shown: Callable[[str], object] = print,
          opened: Callable[[str], object] | None = None) -> None: ...
```

`listening` attaches to the runs and listens, answering nothing until `Site.serve_forever` is
called; leaving the block lets go of the runs, and closes them where they were held in this
process. `serve` is both, until `KeyboardInterrupt`, telling `shown` the address once it
listens and handing it to `opened`. `Site.address` is the address with its key; `Site.port` the
port.
