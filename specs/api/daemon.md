# Daemon protocol

## 1. Scope

This document governs the **daemon** as a client sees it: where a client finds the one daemon of
**this machine** for the current user, how it connects, the frames carried on a connection, every
request a client sends and every message and answer it receives, how protocol versions are told
apart, and every obligation of the daemon and its hosts that a client observes over a
connection. A client is a **frontend** (`hmz`, `hmz web`, a program using `api/sdk.md`) or a
program asking a single question. The internal structure of the daemon and of its host processes
is not governed here.

Out of scope:

- The Python objects that speak this protocol (`Daemon`, `Link`, `Host`): `api/sdk.md`.
- The files of the daemon directory as files on disk, and their cleanup: `api/files/machine.md`.
- The files an **epic** writes, `host.log` among them: `api/files/epics.md`.
- When `hmz` and `hmz web` use a daemon rather than holding epics in their own process, and the
  daemons of other machines: `features/daemons.md`.
- What a flow, a chat and a side question do beyond what is carried here: `features/epics.md`,
  `features/chat.md`, `features/btw.md`.

## 2. Definitions

**2.1** Every term of `README.md` §5 MUST carry the meaning given there.

**2.2** **Daemon directory**: the machine directory `<mdir>` of `api/files/machine.md` §2.2.

**2.3** **Socket**: the Unix stream socket `daemon.sock` in the daemon directory.

**2.4** **Daemon record**: the file `daemon.json` in the daemon directory.

**2.5** **Workspace path**: a workspace directory as an absolute path with every symbolic link
followed. Two spellings of one directory are one workspace path.

**2.6** **Slot**: the text naming one host of a workspace: `""` for the workspace's own host, or
`chat:` followed by 1 to 32 lowercase hexadecimal digits for the host of one chat.

**2.7** The term host MUST carry the meaning `features/daemons.md` §2.1 gives it; each slot of a
workspace names one host, which a client reaches only through the daemon.

**2.8** **Frame**: one unit carried on a connection, as §5 defines it.

**2.9** **Control request**: one JSON object carried in a `CONTROL` frame, as §6 defines it.

**2.10** **Request**: one JSON object a frontend sends in a `MESSAGE` frame, naming what it asks
in its field `do`.

**2.11** **Reply**: the message a host sends in answer to one request, with `type` `reply`.

**2.12** **Message**: one JSON object a host sends in a `MESSAGE` frame, naming its kind in its
field `type`.

**2.13** **Client id**: the text `c<n>` a host gives one attached frontend, `n` counting from 1
per host and never reused.

**2.14** **History record**: a message that carries the field `seq` (§9.2).

**2.15** **Snapshot**: a message without `seq` that says how one thing stands now (§9.3).

**2.16** **Epic number**: the number a host gives each epic it starts, counting from 1 per host.

## 3. The daemon directory

**3.1** The daemon directory MUST NOT be under the **home** directory.

**3.2** The daemon directory, the socket and the daemon record MUST be created, refused and
removed as `api/files/machine.md` §3 and §6 state.

**3.3** Where the full path of the socket exceeds 100 bytes, a client MUST connect by making the
daemon directory its current directory and naming the socket `daemon.sock`, and MUST restore its
former current directory afterwards.

## 4. Finding the daemon and a host

**4.1** A client MUST read a daemon as present only where the daemon record parses as a JSON
object whose `pid` is an integer naming an existing process, and the socket accepts a connection
within 1 second.

**4.2** A client MUST count a process that exists but that it cannot signal as existing.

**4.3** A client MUST NOT read a daemon as present on the strength of the socket file alone.

**4.4** Where the daemon record's `protocol` is absent or differs from the client's protocol
version, the client MUST NOT send any other frame to the socket and MUST report that an older
**hmz** holds the epics (§12.3).

**4.5** A client finds the hosts of the daemon with the control request `list` (§6.2); a client
MUST read a listed host as live only where its `pid` names an existing process.

**4.6** A client MUST name a workspace to the daemon by its workspace path.

**4.7** A client that starts the daemon or a host MUST wait at most 10 seconds for it to come up.

**4.8** A client that starts the daemon or a host MUST report a failure the started process reports
as soon as it is reported, without waiting out the bound of §4.7.

**4.9** Where two clients start the daemon at once, exactly one daemon MUST come up, and both
clients MUST use it.

**4.10** Where two clients start a host of one slot of one workspace at once, exactly one host
MUST be taken on, and both clients MUST use it.

## 5. Frames

**5.1** Every byte on a connection MUST belong to a frame of the form: one byte of kind, then the
payload length as an unsigned 32-bit big-endian integer, then the payload.

**5.2** The kinds MUST be: `M` (`MESSAGE`), a payload of one UTF-8 JSON object, a request from a
frontend or a message from a host; `C` (`CONTROL`), a payload of one UTF-8 JSON object, a control
request or its answer; and `X` (`GONE`), a payload of UTF-8 text saying why the reader is let go.

**5.3** A reader MUST accept a payload of at most 4 194 304 bytes; a length above it MUST be
treated as a connection not carrying this protocol, which the reader closes.

**5.4** A host MUST NOT send a frame whose length with its 5-byte header exceeds 4 194 303 bytes;
a message that would MUST be dropped and recorded in the host's log, and replies are exempt.

**5.5** A host MUST encode JSON without escaping non-ASCII characters and MUST encode every value
that is not JSON-native as its text.

**5.6** A JSON payload that is not an object MUST be read as an empty object.

**5.7** A reader MUST hand out each whole frame exactly once, in the order received.

**5.8** On receiving a frame of a kind it does not know, the daemon and a host MUST answer with
one `GONE` frame carrying ``held for frontends by a newer humanize; `hmz` of it reads it`` and
close the connection.

## 6. Control requests

### 6.1 General

**6.1.1** A control request MUST be the first and only frame a client sends on its connection.

**6.1.2** A control request MUST carry `do` and MUST be answered with exactly one `CONTROL` frame,
after which the connection MUST be closed.

**6.1.3** A client MUST NOT send a control request whose `do` is `serve`; that request is
reserved for the host processes of **hmz**.

### 6.2 Control requests to the daemon

**6.2.1** A control request without `workspace` MUST be answered by the daemon itself.

**6.2.2** `do: "list"` MUST be answered `{"ok": true, "held": [...]}`, one entry per host taken
on, in the order taken on, each with `pid`, `workspace`, `started` and `slot`.

**6.2.3** Any other `do` MUST be answered `{"ok": false, "why": "no such request: <repr>"}`,
`<repr>` being the `do` given written as a Python literal: text in single quotes, a number as
written, `True`, `False` or `None` for `true`, `false` or `null`, and a list or object in brackets
or braces with each item so written.

### 6.3 Control requests to a host

**6.3.1** A control request with `workspace` and, for a host other than the workspace's own,
`slot` MUST be answered by that host.

**6.3.2** Where no host holds that workspace and slot, the daemon MUST answer
`{"ok": false, "why": "no runs are held in <workspace>"}`, with ` for <slot>` appended where
`slot` is not `""`.

**6.3.3** `do: "status"` MUST be answered `{"ok": true}` with the host's own `pid`, `workspace`,
`slot`, `started`, `kind` (`"host"`) and `protocol`, and every key of §6.4.

**6.3.4** `do: "detach"` MUST let every attached frontend go with `gone` `let go`, leave every
epic running, and be answered `{"ok": true, "let go": <n>}`, `n` the number let go.

**6.3.5** `do: "stop"` MUST be answered `{"ok": true}` before anything else happens, and the host
MUST then close as §13.6 states.

**6.3.6** Any other `do` MUST be answered `{"ok": false, "why": "no such request: <repr>"}`.

**6.3.7** A connection carrying a control request MUST NOT count as a frontend attached to the
host.

### 6.4 Status

**6.4.1** The status of a host MUST carry the keys of the following list, and a client MUST read
an absent `turn` as the host not holding a chat.

- `attached`: Integer: the frontends attached.
- `clients`: `[{client, name, kind}]`, one per frontend attached.
- `slot`: The host's slot.
- `state`: `running`, `stopping` or `idle`.
- `run`: The epic number of the epic going, else stopping, else the last; `0` for none.
- `flow`: That epic's flow as named, or `""`.
- `epic`: That epic's directory name, `""` before it has one.
- `task`: That epic's task, or `""`.
- `pending`: `[{question, role, text, mode}]`: every question waiting on a person.
- `ended`: How the last epic to end on this host ended, `{how, why, epic, at, run, flow, task}`,
  `at` in Unix seconds; `null` before one has ended.
- `turn`: Of a chat only: `running` while its agent answers, `done` between turns and once it is
  over.
- `budget`, `usage`: The epic going's budget and spending as JSON, an infinite limit as the text
  `"Infinity"`; `null` while stopping or idle.
- `flows`: The canonical refs of the flow calls in progress.
- `calls`: `[{ref, name, depth, seconds, id, parent}]`, oldest first; `seconds` rounded to 0.001;
  `parent` the index of the calling entry, or `null`.

**6.4.2** The host-process keys are `pid`, `workspace`, `started`, `kind` and `protocol`.

**6.4.3** A client MUST read a host that does not answer a control request `status` as having the
host-process keys of its `list` entry, `attached` `0`, `flows` `[]` and `calls` `[]`.

## 7. Frontend connections

### 7.1 Attaching

**7.1.1** A frontend MUST send `hello` as the first request on its connection.

**7.1.2** `hello` MUST carry `workspace` (a workspace path) and, for a host other than the
workspace's own, `slot`; the daemon MUST hand the connection to the host of that workspace and
slot without consuming the frame, and the host MUST then read it.

**7.1.3** Where no host holds that workspace and slot, the daemon MUST answer with a reply whose
`to` is the request's `id`, `ok` `false` and `why` `no runs are held in <workspace>`, with
` for <slot>` appended where `slot` is not `""`, and close the connection.

**7.1.4** `hello` MUST take `name` (text, default `""`), `kind` (text, default `"sdk"`) and
`replay` (default `true`; only the JSON value `false` disables it).

**7.1.5** A host MUST name a frontend by `name` where it is not `""`, else
`<user>@<kind>`, `<user>` being `HUMANIZE_NAME` where set, else the login name, else `somebody`;
a name already attached MUST become `<name>#2`, `<name>#3` and on.

**7.1.6** `hello` MUST be answered with `client`, the frontend's client id.

**7.1.7** `hello` MUST be refused with `this frontend has already said hello` when sent twice,
`the frontend went while it was saying hello` where the connection closed meanwhile, and
`this host has closed` once the host is closed.

**7.1.8** Every request sent before `hello` MUST be refused with `a frontend says hello first`.

### 7.2 Replies

**7.2.1** A request MAY carry `id`; every request MUST be answered with exactly one reply on the
connection it came in on, whose `to` is that `id`, or `""` where it carried none.

**7.2.2** A reply MUST carry `ok`; a reply with `ok` `true` MUST carry the fields of the answer,
and one with `ok` `false` MUST carry `why`, one sentence.

**7.2.3** A request whose `do` names no request MUST be refused with `no such request: <repr>`.

**7.2.4** A request from a frontend no longer attached MUST be refused with
`this frontend is not attached`.

**7.2.5** A request that fails for any other reason MUST be refused with the text of the failure,
or the name of its type where the text is empty.

**7.2.6** A host MUST give every frontend the same answer and the same refusal, in the same
words, to the same request in the same state.

### 7.3 Order

**7.3.1** A host MUST carry out the requests of one frontend in the order sent, except `aside`,
which MUST be carried out apart from that order so that no other request waits on it.

**7.3.2** A host MUST NOT let a request of one frontend delay the requests or messages of
another.

### 7.4 Leaving

**7.4.1** A frontend leaves by closing its connection, or by the request `detach`; the host MUST
then send it `gone` `let go`, MUST release every role it claimed, and MUST close every aside it
opened.

**7.4.2** A frontend leaving MUST NOT stop any epic.

## 8. Requests

### 8.1 General

**8.1.1** Each request MUST take exactly the fields its subsection lists, with the stated types
and defaults; a field not sent MUST take its default.

### 8.2 `start`

**8.2.1** `start` MUST take `flow` (text, required: a flow name of `api/cli.md`), `task` (text,
`""`), `agents` (object of role to agent spec, `{}`), `envs` (object of role to environment spec,
`{}`), `params` (object, `null` for the flow's defaults), `budget` (a `Budget` as JSON, `null`),
`profile_flow` (boolean, `false`), `profile_environment` (boolean, `false`), `resume` (`false`,
`true`, or the text of an epic directory, `false`) and `backup` (list of target names, `null` for
the defaults).

**8.2.2** `start` MUST start the epic as `Hmz.run` of `api/sdk.md §4.5` does and MUST be answered
with `run`, its epic number.

**8.2.3** `start` MUST be refused with `a flow to start is named` for a missing `flow`;
`backup is a list of backup target names` for a `backup` that is not one; `this host has closed`;
`a flow is already running` while an epic is going; `a flow is already starting` while another
`start` is under way; `this chat has folded away; carry it on from its epic` on a chat host that
has folded (§13.8); and with the `Refused` message of `api/sdk.md §6` for everything `Hmz.run`
refuses.

**8.2.4** An epic that is stopping MUST NOT prevent `start`.

### 8.3 `say`

**8.3.1** `say` MUST take `text` (text, required, not empty) and `to` (text, `""`), and MUST
route the line as §10.1 states.

**8.3.2** `say` MUST be refused with `a line says something` for an empty `text`;
`no flow is running to say it to` while no epic is going, a stopping epic included; and
`<role> is <name>'s` where `to` is `outworlder:<role>` and another frontend claims `role`.

### 8.4 `answer`

**8.4.1** `answer` MUST take `question` (text, a question id) and `text` (text, required, not
empty).

**8.4.2** Where `text`, stripped, is a decimal number `n` from 1 to the number of the question's
options and is not itself an option, the answer MUST be the `n`-th option; otherwise it MUST be
`text`.

**8.4.3** `answer` MUST be refused with `an answer says something`; `already answered by <name>`
for a question answered; `no question <id> is waiting`; and `<role> is <name>'s` where another
frontend claims the question's role.

### 8.5 `stop` and `force`

**8.5.1** `stop` MUST take no field, MUST interrupt the turn under way and let the flow unwind,
and MUST be refused with `the flow is already stopping: it is closing out the turn it was in`
while one is stopping and `no flow is running, so there is nothing to stop` while none is going.

**8.5.2** `force` MUST take no field, MUST stop the epic going where there is one, MUST close
every session of the stopping epic that has a turn open, and MUST be answered with `closed`, the
number of sessions closed; it MUST be refused with
`no flow is running, so there is nothing to stop` where no epic is going or stopping.

### 8.6 `afk`, `claim` and `release`

**8.6.1** `afk` MUST take `on` (boolean, required) and `role` (text, `""` for every role), MUST
set away as §10.3 states, and MUST be refused with `afk is on or off` for an `on` that is not a
boolean and `<role> is <name>'s` for a role another frontend claims.

**8.6.2** `claim` MUST take `role` (text, required) and `take` (boolean, `false`), MUST claim the
role for this frontend as §10.2 states, and MUST be refused with `a role to claim is named` and,
without `take`, `<role> is <name>'s` for a role another frontend claims.

**8.6.3** `release` MUST take `role` (text) and MUST be refused with
`<role> is not yours to release` for a role this frontend does not claim.

**8.6.4** `afk`, `claim` and `release` MUST NOT require an epic to be going, and `claim` MUST NOT
check the role against the flow.

### 8.7 `board`

**8.7.1** `board` MUST take `key` (text) and `value` (text, `""`), and MUST write the line `key`
of the last epic's board as the user, or remove it where `value` is `""`.

**8.7.2** `board` MUST be refused with `this run has no board`, `<key> is not on the board`, and
the board's own refusal where the line is not the user's to change.

### 8.8 `aside` and `unaside`

**8.8.1** `aside` without `side` MUST open a side conversation and be answered with `side`
(`s<n>`) and `forked` (boolean: whether it carries the history of a session).

**8.8.2** `aside` with `key` (`<agent>/<n>`, a session of the last epic) and `fork` (boolean) MUST
open the side conversation on that session: a fork of it where `fork` is `true` and its harness
forks, otherwise a new session of a copy of its agent.

**8.8.3** `aside` with `runs` (an agent spec) MUST open a new session of that agent in the
workspace; with `runs` and `recall` (the harness's id of a session an earlier epic kept), `kept`
(where that epic kept it) and `cwd`, it MUST open a fork of that session where `fork` is `true`
and its harness forks it, otherwise a new session of that agent.

**8.8.4** `aside` with a `key` that names no session MUST be refused with
`<key> has no conversation to ask`.

**8.8.5** `aside` with a `runs` that names no agent this host makes MUST be refused with
`<runs> is not an agent that can be made here`.

**8.8.6** `aside` that names neither `key` nor `runs` MUST be refused with
`an aside is about a conversation, or asks an agent`.

**8.8.7** `aside` from a frontend that has gone MUST be refused with `this frontend has gone`.

**8.8.8** `aside` with `side` and `prompt` MUST take one turn of that side conversation and be
answered with `answer`, its text stripped.

**8.8.9** `aside` with a `side` this frontend has not open MUST be refused with
`no aside <side> is open`.

**8.8.10** `aside` with a `side` that is taking a turn MUST be refused with
`the aside is still answering the last question`.

**8.8.11** `unaside` MUST take `side`, MUST close that side conversation, and MUST be refused with
`no aside <side> is open`.

**8.8.12** Every side conversation MUST be read-only, MUST carry no skills, MUST NOT be seen by the
epic, MUST be answered only to the frontend that opened it, and MUST NOT write where any epic
keeps its sessions nor into the harness's own home.

**8.8.13** A side conversation MUST be closed by `unaside`, when its frontend leaves, when an epic
starts on the host, and when the host closes; no message announces side conversations.

### 8.9 `status`, `detach` and `quit`

**8.9.1** `status` MUST be answered with every key of §6.4.1.

**8.9.2** `detach` MUST let this frontend go as §7.4 states.

**8.9.3** `quit` MUST close the host as §13.6 states.

## 9. Messages

### 9.1 Attaching

**9.1.1** On `hello`, a host MUST send the new frontend, before any other message and with no
other message between them: `welcome`; every history record kept, oldest first, unless `replay`
is `false`; every snapshot, in the order `clients`, `claims`, `away`, `run`, `sessions`, `calls`,
`waiting`, `pending`, `usage`, `board`; and `live`.

**9.1.2** After `live`, a host MUST send each history record and each changed snapshot as it
happens.

**9.1.3** `welcome` MUST carry `client`, `name`, `kind`, `workspace`, `slot`, `pid` (the host's
process) and `protocol`.

**9.1.4** `live` MUST carry `seq`, the `seq` of the last history record, and `elided`, the number
of history records dropped from the front.

### 9.2 History records

**9.2.1** Every history record MUST carry `seq`, an integer that increases by one with each
record across the host's life.

**9.2.2** A host MUST keep the history records of the epic going or the last, starting afresh
with each `start`, up to 32 MiB of JSON, dropping the oldest whole records first and counting
them in `elided`.

**9.2.3** Every history record other than `printed` MUST carry `run`, its epic number.

**9.2.4** The history records MUST be those of the following list, with those fields.

- `started`: `flow`, `ref`, `task`, `by`, `client`, `roles` (agent roles not filled by the runtime),
  `names` (`{role: agent name}`), `outworlders`, `agents`, `envs` (`{role: spec}`), `params`,
  `budget`, `profile_flow`, `profile_environment`, `backup`, `resume` (`""`, or the text given),
  `began` (host monotonic seconds), `at` (Unix seconds).
- `opened`: `role`, `key` (`<agent>/<n>`), `agent`, `cli`, `model`, `counts` (token kinds the
  backend reports, sorted), `forks`, `person`, `kept` (directory of the session's logs, `""` for a
  person or the harness's own home), `env`, `harness`, `mono`, `wall`.
- `event`: `key`, `session`, `agent`, `cli`, `model`, `ident`, `kind`, `text`, `whose`, `tokens`,
  `spent`, `at`, `mono`: the record `hmz exec --json` writes (`api/cli.md`).
- `asked`: `question` (`q<n>`), `role`, `text`, `options`, `mode` (`ask` or `listen`), `key`.
- `answered`: `question`, `role`, `by`, `client`, `text`.
- `withdrawn`: `question`, `why` (`away` or `over`).
- `said`: `text`, `key`, `by`, `client`.
- `refused`: `agent`, `text`, `because`.
- `unheld`: `agent`, `texts`.
- `dropped`: `given` (`[{agent, text, by, client}]`), `queued` (`[{text, by, client, to}]`),
  `because` (`stopped` or `ended`).
- `printed`: `text`: one line printed in the host process.
- `notice`: `text`: a notice of **hmz** about the epic, as `features/epics.md` defines notices.
- `stopping`: `by`, `client`.
- `ended`: `how` (`done`, `stopped`, `budget`, `refused`, `failed` or `crashed`), `why`, `mono`.

**9.2.5** A conversation MUST be keyed `<agent>/<n>`, `<agent>` the agent's own name and `n` the
count of sessions that agent opened in the epic, assigned once as the session opens.

**9.2.6** `opened.env` MUST be `null` where the driver reported no **placement**, and otherwise
`{role, kind, target, workdir, anchored}` as `features/placements.md` defines them;
`opened.harness` MUST be `""`, `local`, `self` or `<backend>:<name>` as that document defines.

**9.2.7** `ended.why` MUST be `""` for `done` and `stopped`, the limit reached for `budget`, the
`Refused` message for `refused`, `<ExceptionType>: <message>` for `failed`, and a traceback for
`crashed`.

**9.2.8** `ended.how` MUST be read as the endings of `features/epics.md` §3.6: `done` as `done`,
`stopped` and `budget` as `stopped`, `failed` and `crashed` as `failed`, and `refused` as an epic
refused before it was created, which has no ending.

### 9.3 Snapshots

**9.3.1** A host MUST keep the latest of each snapshot, MUST send every snapshot on attach, and
MUST send a snapshot to every frontend whenever it changes.

**9.3.2** The snapshots MUST be those of the following list, with those fields and initial
values.

- `clients`: `clients`: `[{client, name, kind}]`; initially `[]`.
- `claims`: `claims`: `{role: client}`; initially `{}`.
- `away`: `all` (boolean), `of` (`{role: boolean}`); initially `false`, `{}`.
- `run`: `state`, the `started` fields of the epic going or the last (`run` `0` for none),
  `stopping` (epic number or `null`), `epic` (`""` before it has one), `slot`, and of a chat `turn`;
  initially `idle`.
- `sessions`: `run`, `open` (keys still open), `working` (keys with a turn open); initially `0`,
  `[]`, `[]`.
- `calls`: `calls`: `[{ref, name, depth, since, id, parent}]`; initially `[]`.
- `waiting`: `queued` (`[{text, by, client, to}]`), `given` (`[{agent, text, by, client}]`);
  initially `[]`, `[]`.
- `pending`: `pending`: `[{question, run, role, text, options, mode, key, owner}]`; initially `[]`.
- `usage`: `run`, `usage`, `budget`; sent at most once a second; initially `0`, `null`, `null`.
- `board`: `items`: `[{key, value, about, whose, by, at}]`, or `null` for an epic with no board;
  initially `null`.

### 9.4 `gone`

**9.4.1** `gone` MUST be the last message a host sends a frontend, carrying `why`.

**9.4.2** `why` MUST be `let go` where the frontend left; `the host was closed` where the host
closed; `fell too far behind; open it again` or `too far behind; attach again` where the frontend
fell behind (§11.1).

**9.4.3** After `gone`, a host MUST send that frontend no message other than replies, and MUST
give the connection at most 5 seconds to take what it is owed before closing it.

**9.4.4** A client MUST read the end of the connection, a failed read, or a frame of no valid
length, without a preceding `gone`, as `gone` with `why` `the host went away`, and a `GONE` frame
as `gone` with its text as `why`.

## 10. Semantics a frontend observes

### 10.1 Lines

**10.1.1** A line said with `to` `""` MUST answer a waiting `listen` question this frontend may
answer, else go into the first session with a turn open, in the order the epic opened them.

**10.1.2** A line said with `to` an agent's name MUST go into that agent's newest session with a
turn open; a line said with `to` `<agent>/<n>` MUST go into that session.

**10.1.3** In a chat, a line said to an agent or session with no turn open MUST answer the
waiting `listen` question this frontend is permitted to answer, and MUST go into no turn.

**10.1.4** A line said with `to` `outworlder:<role>` MUST only answer that role's waiting
`listen` question and MUST NOT go into any turn.

**10.1.5** A line MUST go into a session only while a turn is open there, one line per agent at a
time until the agent acknowledges it; a line that cannot go in MUST wait, and the next turn to
start for its target MUST take the oldest such line into its prompt.

**10.1.6** A line a session takes MUST be recorded with `said`; a line the backend refuses MUST
be recorded with `refused` and return to the head of the queue; lines a turn ended holding MUST
be recorded with `unheld`; lines still waiting when an epic stops or ends MUST be recorded with
`dropped`.

**10.1.7** Claims MUST NOT restrict a line said to an agent or session.

### 10.2 Claims and questions

**10.2.1** A claimed `Outworlder` role MUST be answered, spoken to as `outworlder:<role>`, and
set away only by the frontend claiming it; `take` MUST move a claim from another frontend.

**10.2.2** A claim MUST be released when its frontend leaves, and the `owner` of its questions
MUST become `null`.

**10.2.3** A question MUST be recorded only while its epic is going, the host is open, and its
role is not away; otherwise the flow MUST receive no answer at once.

**10.2.4** A question MUST be answerable by its role's claimant, or by any frontend where the
role is unclaimed, the first answer winning; it MUST stay waiting with no frontend attached.

**10.2.5** A question MUST be `ask` where it has options or a turn is open, else `listen`; a
question asked while exactly one session has a turn open MUST carry that session's key.

**10.2.6** A question MUST be withdrawn with `away` when its role goes away, and with `over` when
its epic stops or ends, is forced, or the host closes.

### 10.3 Away

**10.3.1** Away MUST be held per role by the host and MUST outlive the frontend that set it.

**10.3.2** `afk` with a role MUST set that role; `afk` without a role MUST, where no role is
claimed, set every role and clear every per-role value, and, where roles are claimed, leave the
value of every role another frontend claims unchanged.

## 11. Limits

**11.1** A host MUST NOT wait on a slow frontend: where more than 64 MiB of messages wait for one
frontend, the host MUST let it go with `gone`, sent after the frame in progress.

**11.2** Every text longer than 262 144 characters in a history record or a snapshot MUST be cut
to that length followed by `… (<n> more characters)`, `n` the characters cut.

## 12. Protocol versions

**12.1** The protocol version this document defines MUST be `2`.

**12.2** The daemon MUST write its protocol version in the daemon record
(`api/files/machine.md` §6.2), and a host MUST
send it in `welcome`.

**12.3** A client finding a daemon of another protocol version, or of none, MUST NOT reach it
and MUST NOT start a daemon beside it, and MUST report `the runs in <workspace> are held by an
older humanize (pid <pid>); stop it with that version`, with `on this machine` in place of
`in <workspace>` where no workspace is concerned.

**12.4** The daemon and a host MUST answer a reader that speaks another protocol, by a frame kind
they do not know, with `GONE` as §5.8 states, rather than leave it waiting.

## 13. Lifecycle

### 13.1 The daemon

**13.1.1** There MUST be at most one daemon per machine and user, and it MUST hold the hosts of
every workspace.

**13.1.2** The daemon MUST have no controlling terminal and MUST ignore `SIGHUP`, so that closing
the terminal it was started from does not end it.

**13.1.3** The daemon MUST hand each frontend connection to its host without carrying the
frontend's frames itself.

**13.1.4** The daemon MUST refuse a second host of one slot of one workspace while the first is
alive.

**13.1.5** The daemon MUST exit once it has held no host for 2 seconds, or 60 seconds after it
started where no host was ever taken on, and on `SIGTERM`.

### 13.2 Hosts

**13.2.1** Each host MUST run in a process of its own whose current directory is its workspace.

**13.2.2** The hosts of a workspace MUST run its epics as `features/daemons.md` §3
states.

**13.2.3** A host MUST send every line its process prints on its standard output or standard
error to every frontend as a `printed` record, one line per record.

**13.2.4** A host MUST ignore `SIGINT`.

### 13.3 Idle hosts

**13.3.1** A host MUST close once it is idle and either a frontend has ever said `hello` to it or
60 seconds have passed since it started.

**13.3.2** A host MUST read as idle where no frontend is attached, no epic is going, starting or
stopping, and no epic awaits a frontend.

**13.3.3** An epic that ended while no frontend was attached, and that no frontend stopped, MUST
await a frontend until one attaches, except a chat that folded.

### 13.4 Hosts losing the daemon

**13.4.1** A host whose daemon has gone MUST close as §13.6 states.

### 13.5 Killing

**13.5.1** `SIGTERM` to a host process MUST close the host as §13.6 states and MUST leave the
daemon and every other host running.

### 13.6 Closing a host

**13.6.1** Closing a host MUST withdraw every waiting question, drop every waiting line, stop
every epic, let every frontend go with `gone` `the host was closed`, and close every side
conversation.

**13.6.2** Closing a host MUST wait at most 15 seconds, from the first close, for its epics to
release what they made, and the host process MUST then exit.

**13.6.3** A connection arriving at a closed host MUST be closed at once.

### 13.7 Failures

**13.7.1** Nothing a frontend sends MUST end an epic other than `stop`, `force` and `quit`.

**13.7.2** A failure that belongs to an epic MUST be written to that epic's `host.log`
(`api/files/epics.md`), and one that belongs to none to `daemon.log` in the daemon directory
(`api/files/machine.md`).

### 13.8 Folding a chat

**13.8.1** A chat's host MUST fold its chat once the chat has waited between turns with no
frontend attached for 60 seconds: every role becomes away, the waiting question is answered with
nothing, and the chat ends `done`.

**13.8.2** A folded chat host MUST refuse `start` (§8.2.3); a folded chat is carried on by
starting the `chat` flow on a new slot with `resume` its epic directory, which continues in that
same epic.
