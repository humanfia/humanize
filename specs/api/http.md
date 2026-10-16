# HTTP API

## 1. Scope

This document governs the HTTP server `hmz web` runs: where it listens, how a browser is
admitted, the form of every request and answer, every endpoint it serves under `/api/`, the
event streams, and the paths `/d/<name>/api/...` through which it serves the API of a **daemon**
of another **machine**. Every endpoint is listed in §8 to §15; a method and path not listed there
is not served.

Out of scope:

- The `hmz web` command line, its options and exit statuses: `api/cli.md`.
- The page itself, its views and what it draws: `features/web.md`.
- The daemon protocol the server speaks to hosts: `api/daemon.md`.
- The Python objects behind the answers: `api/sdk.md`.
- The settings files the settings endpoints read and write: `api/settings.md`.
- Reaching the daemons of other machines over ssh, and installing `hmz` there:
  `features/daemons.md`.
- What a notice is and when one is made: `features/monitoring.md`.

## 2. Definitions

**2.1** Every term of `README.md` §5 MUST carry the meaning given there.

**2.2** **Server**: one process of `hmz web` answering HTTP.

**2.3** **Key**: the secret text the server makes when it starts and prints in its address.

**2.4** **Address**: the text `http://127.0.0.1:<port>/?key=<key>` the server prints.

**2.5** **Admission cookie**: the cookie named `hmz-<port>` whose value is the key.

**2.6** **API request**: a request whose path starts with `/api/`.

**2.7** **Write**: a `POST` request.

**2.8** **Refusal**: an answer whose status is 400 or above, whose body is a JSON object carrying
`error`, one sentence saying why.

**2.9** **Stream**: an answer of media type `text/event-stream` (§6).

**2.10** **Workspace parameter**: the field `workspace` of a request: the query parameter of a
`GET`, or the body field of a `POST`, naming a **workspace** by an absolute path, `~` expanded.

**2.11** **Slot parameter**: the field `slot` of a request, read as the workspace parameter is,
naming a host of the workspace as `api/daemon.md §2.6` defines a slot.

**2.12** **Daemon name**: `local` for this machine's daemon, or the name of an ssh daemon
written in the `daemons` list of `api/settings.md`.

**2.13** An epic name (`features/epics.md` §2.1) MUST be written as `api/files/epics.md` §2.2
states.

**2.14** **Epic row**: the JSON object §10.2 defines.

**2.15** **Notice**: the JSON object §15.1 defines.

## 3. Listening

**3.1** The server MUST listen on `127.0.0.1` and, where this machine has IPv6, on `::1`, on the
same port, and on no other address.

**3.2** Where the port asked for is `0`, the server MUST pick a port free on both loopback
addresses.

**3.3** The server MUST make a fresh key of 32 random bytes, URL-safe base64 encoded, each time it
starts, and MUST NOT write the key anywhere but in the address it prints and in the page of §3.4.

**3.4** Where the server opens a browser, it MUST open it on a file readable only by the current
user that forwards the browser to the address, and MUST NOT pass the key on any command line.

**3.5** The server MUST close a connection that sends nothing for 60 seconds.

## 4. Admission

**4.1** The server MUST check every request in the order of this section and MUST answer the
first check failed with the refusal stated.

**4.2** A request whose connection does not come from a loopback address MUST be refused 403,
`Open the address hmz web printed, on the machine it runs on.`

**4.3** The server MUST NOT check the `Host` the request names, so that a port forwarded or
proxied to the server from this machine is admitted.

**4.4** `GET /?key=<key>` with the server's key MUST be answered 303 to `/` setting the cookie
`hmz-<port>=<key>; HttpOnly; SameSite=Strict; Path=/`; with any other key it MUST be refused 403,
`That key is not this server's: open the address hmz web printed.`

**4.5** An API request without the admission cookie MUST be refused 401,
`Open the address hmz web printed to let this browser in.`

**4.6** An API request MUST be refused 403, `Use this server's own page to make this request.`,
where it carries `Sec-Fetch-Site` with a value other than `same-origin` or `none`, or carries no
`Sec-Fetch-Site` and an `Origin` whose host and port differ from its `Host`.

**4.7** A write MUST be refused 403, `Use this server's own page to make this request.`, unless it
carries `Sec-Fetch-Site: same-origin`, or carries no `Sec-Fetch-Site` and an `Origin` of scheme
`http` or `https` whose host and port equal its `Host`.

**4.8** A request outside `/api/` and `/d/` whose method is not `GET` MUST be refused 405,
`Only the page's own files are here.`

**4.9** The page's own files MUST be served without the admission cookie.

## 5. Requests and answers

### 5.1 Request bodies

**5.1.1** A write MUST send a JSON object with `Content-Type: application/json`, `{}` where it
sends nothing, except where §10.6 permits a file.

**5.1.2** A write of any other `Content-Type` MUST be refused 415, `Send JSON.`

**5.1.3** A write whose `Content-Length` is not a whole number of zero or more MUST be refused
411, `Say how long what is sent is.`

**5.1.4** A JSON body over 1 MiB, or a file over 2 GiB, MUST be refused 413,
`That is more than a request here may send.`

**5.1.5** A body that is not JSON MUST be refused 400, `Send JSON.`, and JSON that is not an
object 400, `Send a JSON object.`

**5.1.6** A query parameter given twice MUST be read as its last value.

### 5.2 Routing

**5.2.1** An API request whose path matches no endpoint MUST be refused 404, and one whose path
matches an endpoint of the other method 405, both `There is nothing here by that name.`

**5.2.2** A path segment written `{name}` in this document MUST match one or more characters
other than `/`.

### 5.3 Answers

**5.3.1** Every answer MUST carry `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`.

**5.3.2** A JSON answer MUST be `application/json; charset=utf-8`, encoded without escaping
non-ASCII characters, with `Cache-Control: no-cache` and a weak `ETag`; a `GET` carrying
`If-None-Match` equal to that tag MUST be answered 304 without a body.

**5.3.3** An endpoint this document says answers `201` MUST answer 201 Created with its JSON;
every other successful JSON answer MUST be 200.

**5.3.4** A download MUST be answered 200 with `Content-Disposition:
attachment; filename*=UTF-8''<name>`, `Cache-Control: no-store`, and the file's length.

**5.3.5** A refusal MUST carry `{"error": "<sentence>"}` and any further fields its endpoint
states.

**5.3.6** A failure an endpoint does not anticipate MUST be refused 500,
`Something went wrong here: <why>`, and its traceback written to the server's standard error.

**5.3.7** After refusing a write, the server MUST close the connection.

### 5.4 The page's files

**5.4.1** `GET /` MUST serve `index.html`, and `GET /<path>` the file of that path among the
page's files, with the media type of its extension (`.html`, `.js`, `.css`, `.svg`, `.json`).

**5.4.2** A path whose components are not each one or more letters, digits, `_` or `-`, whose
last component lacks one extension of lowercase letters or digits, or that is longer than 200
characters, MUST be refused 404, as MUST a path naming no file.

**5.4.3** An HTML file MUST be served with `Content-Security-Policy: default-src 'self';
img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self';
frame-ancestors 'none'; base-uri 'none'; form-action 'self'`.

## 6. Streams

**6.1** A stream MUST be answered 200 with `Content-Type: text/event-stream; charset=utf-8` and
`Cache-Control: no-store`, MUST begin with `retry: 2000`, and MUST end where the connection ends.

**6.2** Each event MUST be written as an optional `id: <id>` line, an `event: <name>` line and one
`data: <JSON>` line, followed by a blank line.

**6.3** A stream MUST write the comment `: quiet` after 15 seconds without an event.

**6.4** A stream MUST resume after the event whose id the request names in `Last-Event-ID`, or,
where that header is absent, in the query parameter `last`.

**6.5** Every stream MUST end when the server stops.

## 7. Workspaces and slots

**7.1** A workspace parameter absent or `""` MUST mean the directory the server started in.

**7.2** A workspace parameter that is not absolute after expanding `~` MUST be refused 400,
`Say the workspace as a whole path, not <workspace>.`; one naming no directory MUST be refused
404, `There is no directory <path>.`, except where an endpoint states it reads an epic of a
workspace since removed.

**7.3** A slot parameter absent or `""` MUST mean the workspace's own host; one that is not a slot
MUST be refused 400.

**7.4** The server MUST attach to a host, as a frontend named `browser` of kind `web`, only while
a page follows its stream or a request asks something of it, and MUST let go of it once neither
has happened for 60 seconds and its epics are idle, or its chat is between turns.

**7.5** Where a workspace's own host lets the server go while it is followed, the server MUST
attach to it again after 2 seconds; it MUST NOT attach again to a chat's host.

**7.6** The server MUST attach to a host held by an older **hmz** never, refusing 409 with the
text of `api/daemon.md §12.3`; a host it cannot reach MUST be refused 503,
`The epics of <workspace> could not be reached: <why>`.

## 8. The epics held

### 8.1 `GET /api/held`

**8.1.1** `GET /api/held` MUST answer `machine` (this machine's host name up to its first `.`),
`here` (the directory the server started in), `version` (the server's `hmz` version), `newer` (a
newer release of `hmz`, as `features/updates.md` defines it, or `""`) and `running`.

**8.1.2** `running` MUST hold, for every host of this machine whose epic is going or stopping,
its `run` snapshot (`api/daemon.md §9.3`) where the server follows it, else `state`, `run`,
`flow`, `epic`, `task` and, of a chat, `turn` from its status; each with `workspace` and `slot`.

**8.1.3** `GET /api/held` MUST NOT start any host.

### 8.2 `GET /api/held/stream`

**8.2.1** `GET /api/held/stream` MUST take the workspace and slot parameters and MUST answer a
stream of that host's epics, attaching to it, and starting the workspace's own host where none
is.

**8.2.2** For a chat's slot whose host has gone, it MUST be refused 409,
`This chat has folded away.`

**8.2.3** The stream's events MUST be those of the following table.

| Event | `id` | Data |
| --- | --- | --- |
| `hello` | none | `epoch` (the current attachment's id), `me` (the server's client id) |
| `record` | `<epoch>:<seq>` | One history record of `api/daemon.md §9.2` |
| `standing` | none | One snapshot of `api/daemon.md §9.3` |
| `figures` | none | What the epic has done and spent, §8.2.6 |
| `gone` | none | `why`: the host let the server go; the stream then ends |
| `again` | none | `{}`: the attachment changed or the server is stopping; the stream then ends |

**8.2.4** A stream MUST begin with `hello`, then every record kept after the one the request
names where that names the current epoch, else every record kept, then every snapshot, then each
record and changed snapshot as it comes.

**8.2.5** The server MUST keep at most the latest 20 000 records, and at most about 32 MiB of
them, per host.

**8.2.6** `figures` MUST be sent at most once a second and MUST hold `run`, `elapsed`, `lasting`,
`ended`, `agents` and `sessions` (each `name`, `turns`, `working`, `since`, `lasting`, `used`,
`tokens`, `under`), `handovers` (`[{from, to, count}]`), `latest`, `spending` (each `model`,
`tokens`, `rate`, `dollars`, `money`, `kinds`), `reckoning` (each `kind`, `tokens`, `whole`) and
`tally`.

### 8.3 `POST /api/held/{do}`

**8.3.1** `{do}` MUST be one of `start`, `say`, `answer`, `stop`, `force`, `afk`, `claim`,
`release` and `board`; any other MUST be refused 404, `There is no <do> to ask of an epic.`

**8.3.2** The body MUST carry the workspace and slot parameters and exactly the fields the
request of that name takes in `api/daemon.md §8`; a further field MUST be refused 400,
`<do> takes no <fields>.`, and a field of another type 400, `<do> takes <field> as <type>.`

**8.3.3** The server MUST send the request down its attachment to the host, and MUST answer with
the host's answer: its fields, with `ok` `true`.

**8.3.4** A request the host refuses MUST be refused 409 with the host's sentence; one the host
cannot be asked MUST be refused 503, `The epics could not be asked: <why>`.

**8.3.5** `start` MUST first write what the flow is started with as the workspace's set-up of
that flow, as §11.4 does, and MUST answer with `slot`, the host it started on, beside the host's
answer.

**8.3.6** `start` of the built-in `chat` flow without a slot parameter MUST start on a new chat
slot, starting its host; `start` on a chat slot MUST start that slot's host where none is.

## 9. Side questions

### 9.1 General

**9.1.1** A side question MUST be asked as `features/btw.md` defines it, through side
conversations the workspace's own host opens (`api/daemon.md §8.8`), and MUST NOT reach the epic.

**9.1.2** The **btw** agent MUST be chosen as `features/btw.md` §7 states: the `btw` setting of
`api/settings.md`, and no other.

### 9.2 `GET /api/btw`

**9.2.1** `GET /api/btw` MUST take the workspace parameter and `epic` (an epic name, `""` for the
epic in view on the workspace's own host).

**9.2.2** It MUST answer `open` (the conversations a side conversation is open on, `""` for the btw
agent's), `said` (each side question answered in a side conversation still open, oldest first, as
§9.3 answers it, the latest 200) and `default` (the `btw` setting of `api/settings.md`, `""` for
none, where a question to the btw agent is refused as `features/btw.md` §5.9 states).

**9.2.3** It MUST NOT attach to any host; where the server follows none of the workspace, `open`
and `said` MUST be `[]`.

### 9.3 `POST /api/btw`

**9.3.1** `POST /api/btw` MUST take the workspace parameter, `question` (text, required), `to`
(`""` for the btw agent, or `<agent>/<n>`) and `epic` (the epic `to` is of, `""` for none).

**9.3.2** The first question to a conversation MUST open a side conversation on it, and every
later question to it MUST go on in that side conversation until it is left.

**9.3.3** Where `epic` and `to` name a session the host (`features/daemons.md` §2.1) no longer
holds, the server MUST carry it on from where that epic kept it, tell the btw agent that epic rather
than the epic going, and name the conversation `<epic>/<agent>/<n>`; a session that epic did not
open, or whose agent it did not write, MUST be refused 404.

**9.3.4** It MUST answer `to`, `question`, `answer`, and `asked` (`[{to, question}]`, each
session the btw agent asked on the way to its answer).

**9.3.5** A question to a side conversation still answering MUST be refused 409,
`btw is still answering the last question asked of it.`; a question closed by a new epic starting
409, `A new epic started, which closed what was asked.`; an empty answer 502,
`The agent returned no answer.`

### 9.4 `POST /api/btw/leave`

**9.4.1** `POST /api/btw/leave` MUST take the workspace parameter and `to` (a conversation, or
absent for every one), MUST close the side conversations named, and MUST answer `{"ok": true}`.

**9.4.2** A `to` that is not text MUST be refused 400.

**9.4.3** A side conversation MUST be closed when an epic starts on its host.

## 10. Epics written down

### 10.1 `GET /api/runs`

**10.1.1** `GET /api/runs` MUST take `workspace` (only that workspace's epics; every
workspace's where absent), `status` (an ending of `features/epics.md`, `running` or
`unfinished`), `flow`, `q` (text found in the task, flow or epic name), `offset` (default `0`)
and `limit` (default `50`, at most `200`).

**10.1.2** It MUST answer `runs` (epic rows, newest first), `total`, `offset`, `limit`, `counts`
(`{ending: n}` over every epic) and `flows` (every flow, sorted); `offset` and `limit` that are
not whole numbers MUST be refused 400.

### 10.2 Epic rows

**10.2.1** An epic row MUST hold `name`, `workspace`, `flow`, `task` (its first line, cut at 240
characters with `…`), `began`, `ended`, `how` (its ending, `running` while going, `unfinished`
where its process went before it ended), `agents` (`[{name, role, runs}]`), `sessions` (a
count), `resumable`, `spent`, `held` (whether a host is going with it), `slot` (that host's),
`backup` (the targets it was started with) and `backed` (`{target: {at, ok, error, why}}`).

### 10.3 `GET /api/runs/{name}`

**10.3.1** It MUST answer the epic row of the epic, of whichever workspace, with `at`, the whole
`task`, `ref`, `agents` (each `name`, `role`, `runs`, `backend`, `model`, `effort`, `provider`),
`sessions` (each `agent`, `backend`, `provider`, `ident`, `name`, `at`, `flow`, `parent`,
`harness`), `envs`, `used`, `params`, `budget`, `picked_up`, `earlier` (of a chat carried on, how
many of its sessions it opened before it last was), `profile_flow`, `profile_environment`,
`picks_up`, `foreign` and `calls` (its tree of flow calls, each `flow`, `task`, `began`, `ended`,
`how`, `calls`).

**10.3.2** An epic of no such name MUST be refused 404, `There is no epic <name>.`, on this and
every endpoint under `/api/runs/{name}`.

### 10.4 Traces and timelines

**10.4.1** `GET /api/runs/{name}/trace` MUST answer `sessions`, as `Epics.transcripts` of
`api/sdk.md §12.15` returns them.

**10.4.2** `GET /api/runs/{name}/timeline` MUST answer the epic's Exomyth timeline as
`features/monitoring.md` defines it, laid out afresh on every request while the epic is going.

**10.4.3** `GET /api/runs/{name}/timeline/span/{id}` MUST take `layout` and answer one span of the
last timeline laid out of the epic, whole; an id it lacks MUST be refused 404,
`Epic <name> has no span <id>.`, and a `layout` other than that timeline's 409,
`Epic <name> has been laid out again; read it again.`

**10.4.4** `GET /api/runs/{name}/bundle` MUST answer the epic's `.hmzepic` (`api/sdk.md §12.17`)
as a download of type `application/vnd.hmz.epic+gzip`.

### 10.5 `POST /api/runs/{name}/backup`

**10.5.1** It MUST take `to` (a list of target names, or absent) and MUST back the epic up as
`Backups.push` of `api/sdk.md §13.2` does, answering `queued` at once without waiting.

**10.5.2** A `to` that is not a list of text, or names no target, MUST be refused 400; where there
is no target at all it MUST be refused 409, `There is no backup target: add one in Settings.`

### 10.6 `POST /api/runs/import`

**10.6.1** It MUST take either a body of `Content-Type` `application/vnd.hmz.epic+gzip` or
`application/octet-stream`, the archive's bytes, with `X-Hmz-Filename` its file name
percent-encoded; or JSON `{"path": "<absolute path of a .hmzepic on this machine>"}`.

**10.6.2** It MUST import the archive as `Epics.imported` of `api/sdk.md §12.18` does and answer
201 with `name`, `workspace`, `resumable` and `why`.

**10.6.3** A file sent MUST be kept on this machine only until the request is answered.

**10.6.4** A missing or unsafe `X-Hmz-Filename` MUST be refused 400; a `path` that is not
absolute 400, `Say path as a whole path on this machine.`; an archive that cannot be imported 400
with the runtime's sentence; and an epic already present 409 with the runtime's sentence and
`name`, that epic's name.

### 10.7 Backup targets

**10.7.1** `GET /api/backups/{target}/epics` MUST fetch the target afresh and answer `epics`,
newest first, each `key` (`<machine>/<workspace>/<epic>`), `machine`, `workspace`, `epic`,
`flow`, `task`, `began`, `ended`, `how`, `head`, and `here` (whether this machine holds that
epic).

**10.7.2** `POST /api/backups/{target}/pull` MUST take `key`, download that epic as
`Backups.pulled` of `api/sdk.md §13.7` does, and answer `name`.

**10.7.3** Both MUST refuse 400 for an unknown target or what `Backups` raises `ValueError` for,
and 502 where the repository cannot be reached; no refusal MUST carry credentials of a URL.

### 10.8 `GET /api/usage`

**10.8.1** It MUST take `days` (1 to 365, default 30) and `workspace` (only its epics), and MUST
answer `days_back`, `days` (per UTC day, oldest first), `flows` (costliest first), `ended`
(`{ending: n}`) and `whole`, each but `ended` holding `runs`, `cost`, `output_tokens`, `seconds`,
`money`, `tokens` and `worked`.

**10.8.2** A `days` that is not a whole number MUST be refused 400.

## 11. Flows

### 11.1 `GET /api/flows`

**11.1.1** It MUST take the workspace parameter and answer `flows` (`[{whose, name, about}]`),
`flow` (the flow that workspace opens on) and `running` (`[{ref, name, depth, since, task}]`).

### 11.2 `GET /api/flow`

**11.2.1** It MUST take `name` and the workspace parameter, and MUST answer what the flow
declares: `name`, `ref`, `description`, `resumable`, `resumes`, `agents` (each `name`,
`required`, `auto`, `harness`, `permission`, `skills`, and `clis`: the CLIs installed here that
can fill it), `envs` (each `name`, `required`, `auto`, `cpu`, `memory`, `gpu`, `image`), `params`
(its JSON schema) and `remembered` (`agents`, `envs`, `params`, `budget`, `profile_flow`,
`profile_environment`, `backup`, as the workspace last set the flow up).

**11.2.2** A missing `name` MUST be refused 400; a name that is not one of `GET /api/flows` 404,
`<name> is not a flow on offer here.`; a flow that will not load 404.

**11.2.3** The server MUST NOT load a flow named by a path or a repository.

### 11.3 `GET /api/backends`

**11.3.1** It MUST answer `clis` (`{cli: {accounts: [{name, models: [{name, efforts}], asked}]}}`
for each CLI installed, this machine's own sign-in first as `""`), `installable`
(`{cli: [{name, efforts}]}`) and `envs` (`Runtimes.kinds()` of `api/sdk.md §10.2`).

### 11.4 `POST /api/flows/setup`

**11.4.1** It MUST take the workspace parameter, `flow`, and as `start` takes them `agents`,
`envs`, `params`, `budget`, `profile_flow`, `profile_environment` and `backup`.

**11.4.2** It MUST write what the workspace runs the flow with, as `api/settings.md` defines it,
and answer as `GET /api/flow` does.

**11.4.3** It MUST be refused 404 for a flow not on offer or that will not load; 400 for an
agent that is not an agent spec, a role left without an agent, a flow other than `chat` with no
budget limit, and a `backup` naming an unknown target.

### 11.5 Workspaces

**11.5.1** `GET /api/workspaces` MUST answer `here` and `workspaces`, each `path`, `name`,
`epics` (a count), `last` (when the latest began), `running`, `here` and `there` (whether the
directory exists): where the server started first, then those going, then those where epics ran,
newest first, then those only written in the settings.

**11.5.2** `POST /api/workspaces` MUST take `workspace`, write it in the settings, and answer
`kept` (its absolute path) beside what `GET` answers.

**11.5.3** `POST /api/workspaces/forget` MUST take `workspace`, forget what it was set up with,
and answer as `GET` does.

### 11.6 Flowverses

**11.6.1** `GET /api/flowverses` MUST answer `verses` (each `name`, `url` without credentials,
`fetched`, `fixed`, `edited`, `installed`), `installed` (each `flow`, `verse`, `listed`,
`version`, `repo`, `ref`) and `updates` (each `flow`, `from`, `to`).

**11.6.2** `GET /api/flowverses/{name}` MUST answer `name`, `url`, `fetched`, `fixed`, `edited`,
`flows` (each `listed`, `flow` as `install` takes it, `installed`, and `releases` newest first,
each `version`, `description`, `prerelease`, `license`, `repo`, `dependencies`) and `skipped`
(each `at`, `why`); an unknown name MUST be refused 404, `There is no flowverse <name>.`

**11.6.3** `POST /api/flowverses` (`url`, `name`), `POST /api/flowverses/fetch` (`name`),
`POST /api/flowverses/remove` (`name`), `POST /api/flowverses/install` (`flow`, `version`) and
`POST /api/flowverses/uninstall` (`flow`) MUST do what `Flowverses.add`, `fetch`, `remove`,
`install` and `uninstall` of `api/sdk.md §8` do, and answer `said` (what was done, in words)
beside what `GET /api/flowverses` answers; what those raise MUST be refused 400.

**11.6.4** Install, uninstall and remove MUST be refused 409,
`An epic is running: flows change once none is.`, while an epic is going on this machine.

**11.6.5** `POST /api/flows/fork` MUST take `flow` and the workspace parameter, copy the flow as
`Flows.fork` of `api/sdk.md §7.7` does, and answer `said` and `at`; what that raises MUST be
refused 400.

## 12. Paths

**12.1** `GET /api/files` MUST take `at` (a directory, `~` expanded, the home directory where
absent), `files` (`1` to list files) and `hidden` (`1` to list names starting with `.`), and MUST
answer `at` (spelled from `~` where under the home directory), `whole`, `up` (the parent, `""` at
the root), `entries` (each `name`, `dir`, directories first, at most 500) and `more` (how many
were left out); a directory that cannot be read MUST be refused 404.

**12.2** `GET /api/paths` MUST take `typed` and answer `paths`: at most 50 directories the text
typed could become, sorted, spelled as typed, each ending in `/`, names starting with `.` only
where a `.` was typed.

## 13. Settings

### 13.1 General settings

**13.1.1** `GET /api/settings` MUST take the workspace parameter, for a workspace that need not
exist, and answer `workspace`, `flow`, `btw`, `details`, `reports` (`null` where never answered),
`flows` (the flows set up there) and `backup` (`targets`, each `name`, `url` without
credentials, `branch`, `policies`, `every`; and `defaults`).

**13.1.2** `POST /api/settings` MUST take the workspace parameter and any of `btw` (text),
`details` (boolean), `reports` (boolean) and `backup` (`{targets, defaults}`, every target).

**13.1.3** `POST /api/settings` MUST write `btw`, `details` and `backup` as `api/settings.md`
defines them.

**13.1.4** `POST /api/settings` MUST write `reports` as the key `enable_sentry` of
`api/settings.md`.

**13.1.5** `POST /api/settings` MUST answer as `GET /api/settings` does.

**13.1.6** A target whose `url` equals the credential-free URL `GET` answered MUST keep the URL
written; a `url` still holding `***@` otherwise MUST be refused 400.

**13.1.7** Any other field, or a value of another type, MUST be refused 400 and nothing written.

**13.1.8** `POST /api/settings/forget` MUST take the workspace parameter, forget what that
workspace was set up with, and answer `forgot` (whether there was anything) beside what `GET`
answers.

### 13.2 Accounts

**13.2.1** `GET /api/accounts` MUST answer `gateway` (`"LiteLLM"`), `accounts` (each `cli`,
`name`, `way`, `sets` (the names of the variables it sets), `made`, `models`, `asked`, `serves`)
and `backends` (each `cli`, `ways`, each `name`, `about`, `group`, `terminal`, `asks` (each
`env`, `about`, `secret`, `fixed`); and `wants`).

**13.2.2** No answer MUST carry the value of any variable an account sets.

**13.2.3** `POST /api/accounts` MUST take `cli`, `name`, `way` and `answers` (`{variable:
value}`), and make the account; it MUST be refused 400 for an unknown way, a way whose
`terminal` is true, a variable left unanswered or an invalid name, and 409 for a name taken.

**13.2.4** `POST /api/accounts/correct` MUST take `cli`, `name` and `answers`, write the account
again keeping every variable not answered, and be refused 400 for a variable the way does not ask
and for a way whose `terminal` is true.

**13.2.5** `POST /api/accounts/remove` (`cli`, `name`), `POST /api/accounts/models` (`cli`,
`name`, `""` for this machine's own) and `POST /api/accounts/copy` (`cli`, `name`, `into`) MUST
remove the account, ask the CLI what it runs as that account, and copy the account to the CLI
`into`; an unknown account MUST be refused 404 and a CLI that will not answer 502.

**13.2.6** Every write of §13.2 MUST answer as `GET /api/accounts` does.

### 13.3 Fallbacks

**13.3.1** `GET /api/fallbacks` MUST answer `steps` (each `spec`, `to`, `tries`, `policy`,
`timeout`), `policies`, `default` and `places`.

**13.3.2** `POST /api/fallbacks` MUST take `spec` (a place), `to` (places, in order), `tries`
(default `0`), `policy` (default `exponential-jitter`) and `timeout` (seconds, `0` for none),
write the step, and answer as `GET` does; a value `Fallbacks` refuses MUST be refused 400.

**13.3.3** `POST /api/fallbacks/clear` MUST take `spec`, remove its step, and answer as `GET`
does; a place with no step MUST be refused 404.

### 13.4 Runtimes

**13.4.1** `GET /api/runtimes` MUST answer `runtimes` (each as `held()` gives it) and `blanks`
(each backend's fields as a new runtime holds them).

**13.4.2** `POST /api/runtimes` MUST take `backend`, `name`, `fields` and `replace` (boolean),
and write the runtime; `backend` or `name` among `fields`, or an invalid runtime, MUST be refused
400.

**13.4.3** `POST /api/runtimes/remove` (`backend`, `name`) MUST remove the runtime, and
`POST /api/runtimes/check` (`backend`, `name`) MUST answer what `Runtimes.check` of
`api/sdk.md §10.12` returns, each field by name; an unknown runtime MUST be refused 404.

**13.4.4** `GET /api/runtimes/hosts` MUST answer `hosts`, each `alias`, `host`, `user`, `port`,
`identity_files`, `proxy_jump` and `saved`; an unreadable ssh config MUST be refused 503.

**13.4.5** `POST /api/runtimes/import` MUST take `names` (a list) and `update` (boolean), save an
ssh runtime per name, and answer as `GET /api/runtimes` does; an empty list or unknown host MUST
be refused 400.

**13.4.6** `POST /api/runtimes` and `POST /api/runtimes/remove` MUST answer as
`GET /api/runtimes` does.

## 14. Daemons

### 14.1 The daemon list

**14.1.1** `GET /api/daemons` MUST answer `daemons`: first `local` (label `Local`, state `up`,
the server's version), then each ssh daemon written, each `name`, `label`, `host`, `user`,
`port`, `identity_file`, `proxy_jump`, `options` (`[keyword, value]` pairs), `alias`, `config`,
`state`, `detail` and `version`.

**14.1.2** `POST /api/daemons` MUST take `name`, `fields` and `replace` (boolean), and write the
daemon as `api/sdk.md §14.3` does; a further field or an invalid daemon MUST be refused 400, a
name taken without `replace` 409, and a failed write 500.

**14.1.3** `POST /api/daemons/remove` MUST take `name`; `local` MUST be refused 400 and an unknown
name 404.

**14.1.4** `GET /api/daemons/hosts` MUST answer `hosts`, each `Host` of the ssh config not yet a
daemon (`alias`, `name`, `host`, `user`, `port`, `identity_files`, `proxy_jump`); an unreadable
config MUST be refused 503.

**14.1.5** `POST /api/daemons/import` MUST take `aliases`, add a daemon per alias, skipping those
present, and answer `added` beside what `GET` answers; an invalid list MUST be refused 400 and an
alias the config lacks 404.

**14.1.6** `POST /api/daemons` and `POST /api/daemons/remove` MUST answer as `GET /api/daemons`
does.

### 14.2 Reaching a daemon

**14.2.1** `GET /api/daemons/{name}/state` MUST answer `state` (`idle`, `connecting`,
`installing`, `up` or `failed`), `detail` and `version`; `local` MUST answer `up` at the server's
version; an unknown daemon MUST be refused 404, `There is no daemon by that name.`

**14.2.2** `POST /api/daemons/{name}/connect` MUST start reaching the daemon, or reach it again
where it failed, and answer as `state` does; for `local` it MUST answer as `state` does and
reach nothing; it MUST be refused 404 for an unknown daemon and 503 while the server is stopping.

### 14.3 `/d/{name}/api/...`

**14.3.1** A request to `/d/local/api/<rest>` MUST be answered exactly as `/api/<rest>`.

**14.3.2** A daemon name of characters other than letters, digits, `.`, `_` and `-`, or a path
not continuing `/api/`, MUST be refused 404, `There is nothing here by that name.`

**14.3.3** A request to `/d/<name>/api/<rest>` for an ssh daemon MUST be admitted as §4 states
for API requests and writes, and MUST then be sent to that daemon's `hmz web` at `/api/<rest>`
with its query, admitted there with that server's own key, and answered with that server's status,
headers and body as they arrive, streams and file bodies included.

**14.3.4** The server MUST forward only the request headers `Accept`, `Content-Type`,
`Content-Length`, `If-None-Match`, `Last-Event-ID` and `X-Hmz-Filename`, and MUST NOT pass back
`Set-Cookie`, nor any header holding a line break.

**14.3.5** No page MUST receive the other server's key or cookie.

**14.3.6** An unknown daemon MUST be refused 404; a daemon not up 503 with `state`, `detail` and
`version` beside `error`; and a daemon whose server does not answer 502,
`The daemon did not answer.`

**14.3.7** `/api/daemons...` and `/api/notifications...` MUST be asked of the server a page is
open on, never through `/d/`.

## 15. Notices and notifications

### 15.1 Notices

**15.1.1** A notice MUST hold `id` (an integer greater than every earlier one, across restarts of
the server on this machine), `kind` (`done`, `failed`, `stopped`, `asked` or `listening`),
`workspace`, `slot`, `epic`, `flow`, `task`, `role`, `text` and `at` (Unix seconds), as
`features/monitoring.md` defines them.

**15.1.2** The server MUST work notices out of each host's status without attaching to any host.

**15.1.3** `GET /api/notices` MUST take `after` (an id, default `0`) and answer `notices` (those
kept after it, oldest first, the latest 200) and `last` (the newest id, `0` for none); an `after`
that is not a whole number MUST be refused 400, `Say after as a whole number.`

**15.1.4** `GET /api/notices/stream` MUST answer a stream of `notice` events, each `id` the
notice's id, from after the id the request names, or from now where it names none.

### 15.2 Notifications

**15.2.1** A notification MUST be a notice of this machine or of an ssh daemon reached, with `id`
(text of an integer counted from 1 each time the server starts), `daemon` (a daemon name) and
`read`; the server MUST keep the latest 200, in memory.

**15.2.2** The server MUST follow the `GET /api/notices/stream` of each ssh daemon while it is
up, from the last notice heard of it.

**15.2.3** A notice of a kind turned off in `api/settings.md` MUST NOT be kept nor sent, read
afresh for every notice.

**15.2.4** `GET /api/notifications` MUST answer `items` (newest first) and `unread`.

**15.2.5** `GET /api/notifications/stream` MUST answer a stream of `notification` events, each
`id` its id, every one kept after the id named, every one kept where the id named exceeds every
id here, and from now where none is named.

**15.2.6** `POST /api/notifications/read` MUST take `ids` (a list) or `all` (`true`), mark them
read, and answer as `GET` does; any other body MUST be refused 400,
`Say ids as a list, or all as true.`

**15.2.7** `POST /api/notifications/clear` MUST forget every notification and answer as `GET`
does.

**15.2.8** `GET /api/notifications/settings` MUST answer `kinds` (`{done, failed, stopped,
asked, listening}`, each a boolean) and `system` (boolean), as `api/settings.md` holds them.

**15.2.9** `POST /api/notifications/settings` MUST take any of `kinds` and `system`, write them,
and answer as `GET` does; any other field, kind or type MUST be refused 400 and nothing written,
and a failed write 409.
