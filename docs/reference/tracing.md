# Tracing

What a run leaves on disk and how it is read back: the **epic** (the run's own record), the
sessions its CLIs logged, the optional **profile** of the programs it ran, the **trace** that
gathers all of it onto one timeline (a Chrome JSON trace, opened in
[ui.perfetto.dev](https://ui.perfetto.dev) or `chrome://tracing`), and the **bundle** a run is
exported as. Exomyth, humanize's visualizer, is the part that builds the trace and the
[timeline](#timeline) (`hmz.runtime.tracing`). Guides: [Exporting a run](/user/export), [Tracing](/user/tracing).

## Model

A trace is built from **sessions** and **actions** read out of each CLI's own logs.

| Concept | Is |
| --- | --- |
| session | One conversation (or sub-agent conversation) as one CLI logged it. Key `<backend>:<id>` (see [Readers](#where-the-trajectories-come-from)); a `parent` key for a sub-agent; a `label` (`main`, or what the sub-agent was started as); a `title` (a short id and the first prompt); `args` (model, effort, cwd, version, log path, …). |
| action | One slice of a session: `start`, `end` (epoch seconds), `name`, `category`, `args`, and `spawn` (the key of a session it started). |
| agent | What sessions are grouped by: see [What counts as one agent](#what-counts-as-one-agent). One agent is one process of the trace. |

| Action category | Is |
| --- | --- |
| `turn` | A prompt and everything until the next prompt; `args.prompt` holds the prompt. |
| `llm` | A model call or the reasoning before an output (`generate`, `think`, a step). |
| `tool` | A tool call: `args.tool`, `args.input`, and the result where logged. Named `<tool>: <summary>` from the first non-empty of `description`, `command`, `cmd`, `file_path`, `path`, `pattern`, `query`, `url`, `task_name`, `target`, `objective`, `prompt`, `message`, `input`. |
| `message` | Text the agent said (`say: <summary>`). |
| `event` | Anything else the log records (system messages, compaction, permission mode changes). |
| `session` | Added by the renderer: one banner per session spanning its first to last action. |

Strings in `args` longer than 4096 characters are cut (`… (+N chars)`); lists longer than
32 items are cut (`… (+N items)`). Slice names are one line of at most 96 characters (session
banners 120).

## What counts as one agent {#what-counts-as-one-agent}

Each session is named `<name> · <model> · <effort>` (empty parts omitted) after the **root**
session it hangs from, where `<name>` is:

1. the name given in `agents` for the root's id (a trace of a run passes each role and the ids
   it opened, from the epic); else
2. the root's backend.

Sessions with the same name are one agent. So a loop of a hundred one-shot sessions is one
agent, a sub-agent belongs to whatever started it, and two agents of one configuration are
one agent unless `agents` separates them. A trace of a run always separates them by role.

```python
Hmz().epics.trace(sessions=["0a1b2c3d", "5f6e7a8b"],
                  agents={"actor": ["0a1b2c3d"], "reviewer": ["5f6e7a8b"]})
```

With the lower-level [agent API](/reference/agents), each `AgentBase` has `id` and `opened`:
`agents={a.id: a.opened for a in (actor, reviewer)}`.

## Selecting sessions

| Argument | Rule |
| --- | --- |
| `workspace` | Keeps sessions whose recorded working directory equals it (compared as `os.path.abspath`, not resolved). Defaults to the current directory, unless sessions are named and no workspace is. |
| `sessions` | `None`: every session. A comma-separated string or an iterable of ids: only those. An **empty** iterable: none. Each id matches a session whose key, key without `<backend>:`, or short id **starts with** it. A kept session brings the sub-agents it started. |
| `start`, `end` | Any wording [dateparser](https://dateparser.readthedocs.io/) reads (`"3 days ago"`, `"2026-08-09 09:00"`), made timezone-aware. Records outside the window are dropped. Default: unbounded. |
| `profile` | A `profile.jsonl` path (or its epic directory), or the records; programs overlapping the window are drawn. |
| `flow_profile` | A `flow-profile.jsonl` path (or its epic directory), or the samples; drawn as one more process, `python`, whose one track `flow` nests each frame in the one that called it. Samples overlapping the window are drawn. |
| `kept` | Directories humanize kept sessions in, each holding `<cli>/` laid out as that CLI's home, read beside every CLI's own home. |

A trace of a **run** (`Epics.traced`) names exactly the ids the run's epic recorded, with no
workspace: a directory run in fifty times has fifty separate traces, a run that opened nothing
traces as nothing, and a run whose agents worked on another machine (logged under a path this
workspace never had) is traced all the same.

| Raises `ValueError` | Message |
| --- | --- |
| `start`/`end` not a time | `cannot parse time: <text>` |
| an empty id among `sessions` | `session id cannot be empty` |

An absent or unreadable home, database or log line is skipped; it never fails the trace.

## Where the logs are read from {#where-the-trajectories-come-from}

For each CLI with a reader, in this order — `claude`, `agy`, `codex`, `dsh`, `grok`, `kimi`,
`pi`, `omp`, `qwen`, `opencode`, `mimo`, `mcode` — the reader is run over the CLI's own home,
then over `<kept>/<cli>` for every `kept` directory. Homes are resolved as in
[Backend homes](/reference/environment#backend-homes).

| CLI | Home (default) | Reads | Workspace from | Key | Sub-agents |
| --- | --- | --- | --- | --- | --- |
| `claude` | `~/.claude` | `projects/<ws>/*.jsonl`; `projects/<ws>/*/subagents/**/*.jsonl` with `*.meta.json` | the project folder: the workspace with every non-`[A-Za-z0-9]` character → `-` | `claude:<id>`; sub-agent `claude:<root id>:<file stem>` | linked by tool-use id; labelled `<agentType> · <description>` |
| `codex` | `~/.codex` | `**/rollout-*.jsonl` | `session_meta.payload.cwd` (first line) | `codex:<thread id>` | threads with `parent_thread_id`; labelled by `agent_path` or nickname |
| `kimi` | `~/.kimi-code` | `sessions/*/session_*/state.json` and each agent's `wire.jsonl` | `state.json` `workDir` | `kimi:<session>:<agent id>` | agents with `parentAgentId`; labelled `<type> · <agent id>` |
| `grok` | `~/.grok` | `sessions/<percent-encoded cwd>/*/updates.jsonl` | the decoded folder name | `grok:<id>` (short id 18 characters) | spawned sessions found by following the log |
| `pi` | `~/.pi/agent` | `sessions/*/<started>_<id>.jsonl` | the `session` record's `cwd` | `pi:<id>` | none |
| `omp` | `~/.omp/agent` | `sessions/*/<started>_<id>.jsonl`, read as `pi`'s | the `session` record's `cwd` | `omp:<id>` | none |
| `qwen` | `~/.qwen` | `projects/<ws>/chats/*.jsonl` | the project folder, as `claude` | `qwen:<id>` | none |
| `dsh` | `~/.dsh` | `sessions/*/*/session*.jsonl` (highest generation) | the header's `cwd` | `dsh:<id>` | sessions with `parentSession` |
| `opencode` | `~/.local/share/opencode` | SQLite `opencode.db`: tables `session`, `message`, `part` (read-only) | `session.directory` | `opencode:<id>` | child sessions |
| `mimo` | `~/.local/share/mimocode` | SQLite `mimocode.db`, as opencode | `session.directory` | `mimo:<id>` | child sessions |
| `mcode` | `~/.minimax` | `v2/sessions/<y>/<m>/<d>/<opened>-session_<base64url id>/messages.jsonl` | `workspaceDir` of `local_runtime_sessions.record_json` in SQLite `v2/sqlite/runtime-state.sqlite`; a session absent there belongs to no workspace | `mcode:<id>` | none separate: a sub-agent's work is in its parent's log |
| `agy` | `~/.gemini/antigravity-cli` | SQLite `conversations/<id>.db` (`steps`, protobuf metadata read by field number); `conversation_summaries.db` | `cache/last_conversations.json` (workspace → last conversation opened there): a workspace keeps only that one conversation | `agy:<id>` | conversations with `parent_conversation_id` |
| `cursor-agent` | `~/.cursor` | <Badge type="warning" text="no reader" /> | | | |
| `acp` | | no logs humanize can find | | | |

Token counts are read as each CLI records them; where a CLI records cached input beside
input (pi, omp, opencode, mimo, mcode, agy), both are counted.

## The document {#document}

```json
{"traceEvents": [...], "displayTimeUnit": "ms", "otherData": {...}}
```

A trace with no session with actions and no program is
`{"traceEvents": [], "displayTimeUnit": "ms", "otherData": {<workspace/selected only>}}`.

### Processes and tracks

| Chrome concept | Is |
| --- | --- |
| process (`pid`) | One agent, numbered from 1 in order of its first action; then one per profiled program. Named `<agent> · <model>[ · <effort>] · <n> sessions` (`1 session` for one; the model and effort as the root session logged them, so one role on two models is two processes), or `<program> · <pid>` for a program. |
| track (`tid`) | A row of one agent's sessions, `tid = row × 100 + lane` (row from 1). Rows are packed per depth: sessions of one depth that do not overlap share a row. Roots and sub-agents never share a row. |

Row names:

| Depth | Name |
| --- | --- |
| 0 | `main` |
| 1 | `subagent`, or `subagent · <kind>` where every session in the row has one kind (the label before ` · `) |
| n ≥ 2 | `subagent <n>` (with ` · <kind>` likewise) |

A second row of the same name at the same depth is `<name> #2`, and so on. Actions that
overlap inside a row are pushed into extra lanes named `<name> ~2`, `~3`, …. A program's
tracks are its threads: `main` for the thread whose id is the process id, `thread <tid>`
otherwise, `tid = index × 100`.

### Events

| `ph` | Emitted for | Fields |
| --- | --- | --- |
| `M` | `process_name`, `process_sort_index`, `process_labels` per process; `thread_name`, `thread_sort_index` per track | `pid`, `tid`, `name`, `args` |
| `X` | every action, every session banner, every program thread | `pid`, `tid`, `cat` (the category; `process` for a program), `name`, `ts` and `dur` in µs (`dur` ≥ 1), `args` |
| `s`, `f` | a session starting another (`cat: "spawn"`, `name: "spawn"`, shared `id`) | `s` at the spawning action; `f` (`bp: "e"`) at the start of the spawned session |

`args` of an action slice: the action's own `args`, plus `at` (ISO 8601 UTC start) and
`session` (the session key). A banner's `args`: the session's `args`, `agent`, `parent`. A
program slice's `args`: `pid`, `ppid`, `argv` (joined), `cpu` (seconds), `at`.
`process_labels` is the workspace and selection, joined by ` · `.

### `otherData`

Every value is a string.

| Key | Present | Value |
| --- | --- | --- |
| `workspace` | a workspace was given | its path |
| `selected` | sessions were named | the ids joined with `, `, or `<n> sessions` for more than four |
| `agents` | the trace is not empty (sessions with actions, or programs) | the agent names, sorted, `, `-joined |
| `backends` | as `agents`; `""` where no session has actions | the backends, sorted, `, `-joined |
| `sessions`, `slices`, `tracks` | as `agents` | counts (sessions with actions; actions; tracks) |
| `start`, `end` | as `agents` | first and last moment of sessions and programs, ISO 8601 UTC |
| `programs` | the trace has a profile | count of programs |

## The Exomyth timeline {#timeline}

The same epic laid out for a viewer of its own rather than for Perfetto: compact, columnar, and
without the payloads, which are asked for one span at a time. Built by
`hmz.runtime.tracing.timeline.build` from the sessions a [trace](#document) of the epic would
be drawn from, the epic itself, the tree of flows it called, its `profile.jsonl` and its
`flow-profile.jsonl`; served as
[`GET /api/runs/<name>/timeline`](/reference/web#api-runs) and from Python as
[`Epics.timeline`](#epics-timeline). Unlike a Chrome trace, **every session is its own
process**, under the session that started it.

```json
{"version": 1, "layout": "9f2c41d07ab3e815", "epic": "20261012T093000.000Z",
 "origin": 1791800000.123, "live": false,
 "strings": ["", "chat", "flows", ...],
 "processes": [{"id": 0, "kind": "flow", "name": 1, "parent": -1, "tracks": [0], ...}, ...],
 "tracks": [{"process": 0, "name": 2, "first": 0, "count": 3, "depths": 2,
             "spans": {"start": [...], "dur": [...], "depth": [...], "cat": [...],
                       "name": [...], "model": [...], "in": [...], "out": [...]}}, ...],
 "spawns": {"span": [1, 57], "process": [1, 2]},
 "summary": {"start": 0, "end": 93000000, "processes": 3, "tracks": 4, "spans": 211,
             "categories": {"llm": {"count": 40, "time": 51000000, "in": 9000, "out": 2100}}}}
```

Every key is always present. Times are **whole microseconds since `origin`** (epoch seconds,
the earliest moment of anything in the document); durations are never negative and may be 0.
Every text field is an **index into `strings`**, whose index 0 is `""` (nothing said), except
a process's `kind`.

| Key | Is |
| --- | --- |
| `version` | `1`. A client MUST refuse a version it does not know. |
| `layout` | A hex digest that changes whenever an id would name another span (another process, track, start or category), and stays the same while spans only grow longer. |
| `epic` | The epic's name, or `""`. |
| `origin` | Epoch seconds (float) that time 0 is. Wall clock of `t` µs: `origin + t / 1e6`. |
| `live` | `true` while the epic has not ended: the document grows, so re-read it. |
| `strings` | The string table. |
| `processes` | Lanes of the chart's first level, by `id` (= index). |
| `tracks` | Lanes of the second level, by index, each one process's. |
| `spawns` | What started each process: columns `span` (the span that started it) and `process` (what it started), sorted by span. A sub-agent's comes from the action that started it; every other session's from the flow call that opened it, or the epic's own span. |
| `summary` | `start` (0), `end` (µs; the last moment anything did), counts of `processes`, `tracks`, `spans`, and `categories`: `{<category>: {count, time, in, out}}` (`time` = durations summed, µs; `in`/`out` = tokens). |

### Processes {#timeline-processes}

| Field | Is |
| --- | --- |
| `id` | Its index in `processes`. |
| `kind` | `flow` (the epic and the flows it called; first, where there is an epic; and, next, `python`, where the epic's [flow was profiled](#flow-profile-jsonl)), `session` (one agent or sub-agent conversation, ordered by start), or `os` (one program of a [profiled](#profiling-a-run) epic, ordered by start then pid). |
| `name` | `<label> · <title>` for a session (≤ 120 characters), the flow for `flow` (`python` for its profiled Python), `<program> · <pid>` for `os`. |
| `parent` | A process id, or `-1`. A sub-agent hangs from the session that started it, a session the epic opened (or a sub-agent whose starter did nothing) from the `flow` process (0), as does `python`, a program from the program that held its parent's pid when it started, where that was profiled. |
| `key` | The session key (`<backend>:<id>`); `epic:<name>` for `flow`, `python:epic:<name>` for `python`; `pid:<pid>:<start>` for `os`. |
| `pid` | The operating system's pid for `os`, else 0. |
| `agent` | The agent it ran on, as [a trace names one](#what-counts-as-one-agent). |
| `role` | The flow's role that opened it (root sessions the epic recorded), else `""`. |
| `backend`, `model` | The CLI, and the model the session logged. |
| `label` | `main` or what a sub-agent was started as; how the epic ended for `flow`, `python` for `python`; the program's name for `os`. |
| `record` | The epic's record of the call that opened it (`epic.jsonl` or `epic.<flow>_<id>.jsonl`); `""` for `flow` and `os`. |
| `start`, `end` | µs, over its spans. |
| `tracks` | Its track ids, in lane order. |

### Tracks and spans {#timeline-tracks}

A process's spans are stacked as a Chrome trace stacks them: each goes in the first lane
where it nests inside the span open on top, and one that overlaps without nesting spills into
the next lane. One lane is one track. Within a track, **two spans at one depth never overlap**,
and a span at depth `d + 1` lies inside the latest span at depth `d` before it.

| Track field | Is |
| --- | --- |
| `process` | Its process. |
| `name` | `main` or the session's label; `flows`; `threads`. The n-th lane (n ≥ 2) adds ` ~<n>`. |
| `first` | The id of its first span. |
| `count` | How many spans. |
| `depths` | Deepest depth + 1. |
| `spans` | Columns, each `count` long, **sorted by `start`** (so, by start within every depth too: binary-search what is on screen): `start`, `dur`, `depth`, `cat`, `name`, `model` (string indices), `in`, `out` (tokens the reader's `usage` gave for that span, else 0). |

| `cat` | Depth | Span |
| --- | --- | --- |
| `flow` | 0 for the epic, n for a call n flows deep | The epic, from its `began` to its `ended`, and each flow it called, inside its caller; one not yet returned ends at `summary.end`. |
| `session` | 0 | A session, over everything it did. |
| `turn`, `llm`, `tool`, `message`, `event` | 1, 2, … | Its [actions](#model). Where spans start and end together, `session` holds `turn` holds the rest. |
| `process` | 0, then 1 | One per thread: the program's main thread, the others inside it. |

**Span ids** number every span from 0 in track order with no gaps: span `i` of track `t` is
`tracks[t].first + i`. A span id is good for the timeline it came from: for a `live` epic, the
last one served. Pass its `layout` when asking for a span: a timeline laid out again since,
with ids moved, is `409` rather than some other span.

### One span, whole {#timeline-span}

`GET /api/runs/<name>/timeline/span/<id>?layout=<layout>` (`layout` optional), or
`Timeline.span(id)`:

```json
{"id": 57, "process": 1, "track": 1, "start": 16000000, "dur": 14000000, "depth": 2,
 "cat": "tool", "name": "Task: look", "at": "2026-10-12T09:30:16+00:00",
 "args": {"tool": "Task", "input": {...}, "session": "claude:..."}}
```

`args`: an action's own `args` and `session` (its key); a session banner's session `args`,
`agent`, `parent`, `session`; a flow's `flow`, `task`, `how`, `record`; a thread's `pid`,
`ppid`, `tid`, `argv` (joined), `cpu` (seconds); a frame of the flow's Python (category
`sample`), its `frame`. An id the timeline does not have is `404` (a
`KeyError` from Python).

## Profiling a run {#profiling-a-run}

A run is profiled two ways, each asked for apart -- with
[`hmz exec`](/reference/cli#hmz-exec)'s `--profile-flow` and `--profile-environment`,
`profile_flow=True` and `profile_environment=True` to `Hmz().run`, `Runner` or `Link.start`,
or the **profile flow** and **profile environment** rows of the
[`/flow`](/reference/tui#roles-page) menu, beside the budget:

- **The environment** samples every descendant process of the process running the flow, every
  0.05 s (psutil, on a daemon thread), from the epic's opening until it closes, into
  [`profile.jsonl`](#profile-jsonl). An unreadable process is skipped, a machine whose
  processes cannot be read gives an empty profile, and a process that lives less than one
  interval may be missed.
- **The flow** samples the flow's own Python every 0.001 s with
  [pyinstrument](https://pyinstrument.readthedocs.io/), on the thread and in the asyncio task
  the flow runs in and every task it starts, from the epic's opening until it closes, into
  [`flow-profile.jsonl`](#flow-profile-jsonl), written as it closes. Time a task spends
  awaiting something is a frame `[await]` under what awaited it; a thread something else is
  already profiling gives no profile.

Profiling never stops a run. Each is off unless asked; the epic's `began` record carries
`profile_flow: true` and `profile_environment: true` for a run that was, and `/resume` profiles
the run it picks up the same way.

### `profile.jsonl` {#profile-jsonl}

JSON Lines in the epic, appended as programs start and end.

```json
{"event": "ran", "pid": 41207, "ppid": 41190, "name": "pytest", "argv": ["pytest", "-q"],
 "began": 1790000000.12, "seen": 1790000000.15, "ended": 1790000000.15,
 "threads": [[41207, 1790000000.15, 1790000000.15, 0.0]]}
```

| Field | Type | |
| --- | --- | --- |
| `event` | `"ran"` \| `"left"` | first seen; gone (or still running when the profile stopped) |
| `pid`, `ppid` | `int` | |
| `name`, `argv` | `str`, `[str]` | as the process reports |
| `began` | `float` | the OS start time, epoch seconds |
| `seen` | `float` | when first sampled |
| `ended` | `float` | when last seen |
| `threads` | `[[tid, began, ended, cpu]]` | per thread; `cpu` is user + system seconds |

Read back per `(pid, began)`, the last record winning. Start times are then shifted by the
smallest `seen − began` in the profile (never negative) to put them on the clock the rest of
the trace uses.

### `flow-profile.jsonl` {#flow-profile-jsonl}

JSON Lines in the epic, one per stretch of time the flow's Python spent in one place.

```json
{"t": 1790000000.12, "dt": 0.409,
 "stack": ["run_flow /…/hmz/runtime/flowing/engine.py:1722", "chat /…/flows/chat.py:12", "[await]"]}
```

| Field | Type | |
| --- | --- | --- |
| `t` | `float` | when it began, epoch seconds |
| `dt` | `float` | how long, seconds |
| `stack` | `[str]` | each frame `function file:line` (the line it is defined on), outermost first |

The frames every stack shares with where sampling started -- the event loop and the runner
calling the flow -- are left off, and a stack held over several samples running is one line.
Drawn, a frame held over consecutive lines under the same frames is one slice, with what it
called nested under it.

## Epics {#epics}

Every run of a flow writes one **epic**: a directory created when the run starts and closed
when it ends, never reopened.

```
H/epics/<ws>/<stamp>-<hex6>/
    epic.jsonl                      the run's record
    epic.<flow>_<hex6>.jsonl        one record per flow call
    resume.jsonl                    the journal of a resumable run
    profile.jsonl                   programs, for a run whose environment was profiled
    flow-profile.jsonl              the flow's own Python, for a run whose flow was profiled
    sessions/<cli>/…                the run's sessions, laid out as the CLI's home
    traces/export.trace.json        written by "export epic" on /epics, replaced each time
    traces/<%Y%m%dT%H%M%SZ>.trace.json   written by Epics.traced, one per call
```

`H` is [humanize's home](/reference/files). `<ws>` is the workspace's resolved absolute path
with every character outside `[A-Za-z0-9]` replaced by `-` (`/home/you/code` →
`-home-you-code`). `<stamp>` is the UTC start, `%Y%m%dT%H%M%S.mmmZ`; `<hex6>` is random.
Epics sort by name, so in start order. Only a directory holding `epic.jsonl` is an epic.

### `epic.jsonl` {#epic-jsonl}

JSON Lines, one line per event, appended and flushed as it happens. Every line has `event` and
`at` (`%Y-%m-%dT%H:%M:%S.mmmZ`, UTC).

| `event` | When | Fields |
| --- | --- | --- |
| `began` | the epic opens | `flow` (as named), `ref` (canonical, when known), `task`, `workspace`, `resumable`, `picked_up` (epic name, when resumed), `agents` (list of `{agent, backend, model, effort, provider, name}`, one per role: `agent` is the role, `name` what the agent filling it is called; `name` is absent from an epic written before agents had names of their own, whose sessions were written under the role), `envs` (list of `role=<-e spec>`, as given; in a record with no `spelling`, one written in a spelling `-e` now refuses, `local@/x`, `docker@local/x`, `swarm@local/x`, `apple-container@local/x`, `slurm@local/x`, an unsaved ssh host out of brackets, is read back as `-e` spells it), `used` (the same, where an environment was put on a runtime its `-e` [fell back to](/reference/machines#falling-back); omitted where it equals `envs`), `params`, `budget` (`{duration, cost, output_tokens, graceful}` as JSON; `cost: "Infinity"` for unlimited), `profile_flow`, `profile_environment` (`true`, only for a run [profiled](#profiling-a-run) that way), `spelling` (`2`: `envs` and `used` are spelled as `-e` writes `@` only before a provider) |
| `opened` | a session's CLI has given it an id (when it opens, or during its first turn); a session whose CLI never started is not written | `agent` (the agent's own name, such as `NeiKos496`, never the role it fills), `backend`, `provider` (`local` for the machine's own sign-in), `session` (the CLI's id), `name` (`<agent>-<cli>@<account>-<id>`, characters outside `[A-Za-z0-9._@-]` → `-`), `where` (`sessions/<cli>` relative to the epic, or an absolute path for a session kept elsewhere), `parent` (the id it was forked from, when forked), `harness` (`local`, `env`, or the `<backend>:<name>` of the runtime a harness setting named; only when its work was on another machine; `self` in an epic an earlier humanize wrote is read as `env`) |
| `called` | the flow calls a flow | `flow` (callee's canonical ref), `task`, `epic` (the callee's record file name) |
| `returned` | that call ends, however | `flow`, `epic` |
| `usage` | the run ends | `cost` (USD), `output_tokens`, `seconds`: the run's total as its budget counted it |
| `ended` | the epic closes | `how`: `done`, `failed` or `stopped` |

`how` is `stopped` for a run cancelled from outside (<kbd>ctrl+c</kbd>, `Run.stop()`), whose
budget ran out, or that raised `FlowCancelled`; `failed` for any other exception; `done`
otherwise. A missing `ended` means the process was killed (or the run is still going).

```json
{"event": "began", "at": "2026-09-30T05:33:55.691Z", "flow": "chat", "task": "hi", "workspace": "/tmp/ws", "resumable": false, "ref": "chat:chat", "agents": [{"agent": "assistant", "backend": "claude", "model": "haiku", "effort": "low", "provider": "", "name": "NeiKos496"}], "envs": [], "params": {}, "budget": {"duration": null, "cost": "Infinity", "output_tokens": null, "graceful": true}}
{"event": "opened", "at": "2026-09-30T05:33:57.978Z", "agent": "NeiKos496", "backend": "claude", "provider": "local", "session": "56107ec6-dfa6-4484-97dc-ae0f49981bed", "name": "NeiKos496-claude@local-56107ec6-dfa6-4484-97dc-ae0f49981bed", "where": "sessions/claude"}
{"event": "usage", "at": "2026-09-30T05:33:58.796Z", "cost": 0.0, "output_tokens": 46, "seconds": 2.252695}
{"event": "ended", "at": "2026-09-30T05:33:58.796Z", "how": "done"}
```

### Records of called flows {#records-of-called-flows}

Each flow call gets `epic.<flow>_<hex6>.jsonl` beside `epic.jsonl`: `<flow>` is the callee's
canonical ref with characters outside `[A-Za-z0-9._@-]` → `-` (`phases:plan` →
`epic.phases-plan_ed763a.jsonl`), `<hex6>` random per call.

- Its `began` has `flow`, `task`, `workspace`, `resumable` and `under` (the record of the
  caller). Then the `opened`, `called`, `returned` events of what happened inside the call,
  and `ended` with how **the call** ended. No `usage`.
- A call made inside a called flow is written under that flow's record, so the records form
  the call tree. Concurrent calls are records whose `began`/`ended` overlap.
- One flow called twice is two records.

### Sessions {#sessions-dir}

`sessions/<cli>/` holds the sessions the run's CLIs wrote, **the only copy**: each turn's CLI
has these paths of its home answered from here instead, and resumes and forks from here. Its
settings, skills and credentials remain the CLI's own.

| CLI | Kept paths (relative to its home) |
| --- | --- |
| `claude` | `projects`, `sessions`, `file-history`, `session-env`, `tasks`, `todos`, `plans` |
| `codex` | `sessions`, `archived_sessions`, `session_index.jsonl`, `state_*.sqlite*`, `thread_history_*.sqlite*`, `goals_*.sqlite*`, `queue_*.sqlite*`, `memories_*.sqlite*`, `thread-writer-locks`, `shell_snapshots` |
| `agy` | `conversations`, `brain`, `annotations`, `implicit`, `presence`, `conversation_summaries.db*`, `jetbox_summaries_proto.pb`, `cache/last_conversations.json` |
| `dsh` | `sessions` (told to the CLI directly) |
| `grok` | `sessions`, `active_sessions.*` |
| `kimi` | `sessions`, `session_index.jsonl`, `workspaces.json`, `server/events`, `search-index`, `file-history` |
| `pi` | `sessions` |
| `omp` | `sessions` |
| `qwen` | `projects`, `tmp`, `file-history` |
| `opencode` | `opencode.db*`, `storage` |
| `mimo` | `mimocode.db*`, `storage` |
| `cursor-agent` | `chats`, `projects/*/agent-transcripts` |
| `mcode` | `v2/sqlite`, `v2/sessions`, `background-tasks` |

A session no turn could keep stays in the CLI's home, and its `opened.where` is that absolute
directory: a turn whose harness ran on another machine, any turn on a machine that cannot
supervise one (anything but Linux on x86-64 or aarch64, or a kernel that refuses tracing),
every turn under [`HUMANIZE_SESSIONS=off`](/reference/environment#humanize-sessions), and
every turn of an agent driven outside any run (the agent API, a fresh `/btw` side session). An
epic written before
sessions were kept holds a directory of links per session instead, and still reads back.

![One run's directory, and the one file under its sessions/: a Claude Code transcript kept at
sessions/claude/projects/-work-demo/, where Claude Code keeps it under its own home](/demo/run-kept.png)

### `resume.jsonl`

Only for a [resumable flow](/reference/flows#a-flow-that-can-be-picked-up); format in
[Flows › Journal](/reference/flows#journal). A run picked up from an epic copies this file
into its own epic and records `picked_up`.

## Export {#export}

*export epic* on `/epics`, `Epics.bundled(epic, output=…)`, or `hmz.runtime.exporting.bundle` writes one
gzip-compressed tar archive of a run, under the extension `.hmzepic`:

| Property | Value |
| --- | --- |
| Name | `<epic>.hmzepic` |
| Location | `output`, required: a file, or a directory — existing or ending in `/` — to put it in; made absolute |
| Write | to `.<name>.<random>.new` (mode `0600`, kept), then renamed over; exporting a run again replaces the archive |
| Refused | `ValueError: <dir> is not a run` for a directory holding no epic |

*export epic* first writes `traces/export.trace.json` (the run's trace, replacing any earlier
one), then the archive, and reports `<path> · <size> · <n> sessions, <n> slices[, <n> programs]`.

**Members**, under `<epic>/`, each scrubbed (below):

1. `epic.jsonl` and every `epic.*.jsonl`;
2. `resume.jsonl`, `profile.jsonl`, `flow-profile.jsonl` where present;
3. `traces/*`;
4. `sessions/<session name>/<path>`: every file each session was logged to, found by the CLI's
   log globs (e.g. `projects/*/<id>.jsonl` for Claude Code), under the session's `name` from
   `opened`;
5. `transcript.md`, only when a caller passes a transcript;
6. `manifest.json`.

### Import {#import}

`Epics.imported(archive)` or `hmz.runtime.exporting.unbundle` reads one back in:

| Property | Value |
| --- | --- |
| Takes | a `.hmzepic` holding exactly one `<epic>/` with `epic.jsonl` and `manifest.json`, nothing but plain files and directories, extracted with `tarfile`'s `data` filter |
| Lands | `<home>/epics/<workspace>/<epic>`, the workspace being `began.workspace`; written in a hidden directory beside it, then renamed in |
| Sessions | `sessions/<session name>/<path>` moved back to each session's `where`; a `where` that was a whole path (the other machine's CLI home) becomes `sessions/<cli>` and its `opened` line says so |
| Marks | an `imported` line, `{from, head}`: the file's name and the manifest's `workspace.head` |
| Refused | `ValueError` for another extension, a file that is not a gzipped tar, more or less than one epic, a member that is not a plain file or would land outside it, a run saying no workspace, and an epic already here |

An imported run is picked up (`picks_up`, `resumed`, `--resume`) only where `began.workspace`
is a directory here whose resolved path is itself and, when it is a git repository and `head`
is set, holds that commit. `Epics.foreign(epic)` says why not; resuming one is refused with it.

### `manifest.json`

| Key | Value |
| --- | --- |
| `humanize` | the installed version |
| `made` | when the archive was made |
| `python`, `machine` | `platform.python_version()`, `platform.platform()` |
| `epic` | the epic's name |
| `run` | `{flow, task, began, ended, how, resumable}`; `how` is `left unfinished` without `ended` |
| `workspace` | `{at, head}`: the path and its current `git rev-parse HEAD` (not the commit at run time) |
| `agents` | `[{agent, backend, model, effort, provider, runs}]`; the account by name only |
| `envs` | as `began.envs` |
| `used` | as `began.used`, else `envs` |
| `called` | the call tree |
| `sessions` | `[{name, agent, backend, provider, session, flow, record, at, logs}]`; `logs` lists what the archive holds for it |
| `backends` | per backend: `{command, executable, version, sha256, logs}`; `sha256` of the executable; `logs: false` for a CLI that writes no session log |
| `held` | every member, `manifest.json` last |
| `redacted` | the four statements below |

**Redaction.** Every byte written passes through the same scrubber:

- every value of every account's variables (by value, if at least 8 characters), except what
  the run says it ran;
- keys in vendor shapes: `sk-`, `pk-`, `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`,
  `glpat-`, `xai-`, `xoxb-`, `xoxp-`, `hf_` followed by ≥ 12 characters; `AIza…`; JWTs;
  `Bearer …`;
- the userinfo of a URL (`user:password@`, and a bare `user@` such as `git@`), and `token`, `key`, `secret`, `sig`, `signature`, `password`,
  `credential`, `access_token`, `api_key` query parameters;
- JSON values and `NAME=value` assignments whose name ends in `token`, `secret`, `api_key`,
  `password` or `credential` (not `tokens`: token counts are kept).

Each is replaced by `[redacted]`.

## From Python {#from-python}

[`Hmz().epics`](/reference/sdk#epics) (`hmz.runtime.Epics`) reads epics and makes traces and
bundles. Reading: `all()`, `read(epic)`, `sessions(epic)`, `opened(epic)`, `state(epic, flow)`,
`resumed(flow)`, `picks_up(epic)`, `foreign(epic)`; `imported(archive)` reads a bundle back
([SDK](/reference/sdk#epics)).

### `Epics.traced` {#epics-traced}

```python
def traced(self, epic: Path, *, output: str | os.PathLike[str] | None = None,
           start: str | None = None, end: str | None = None) -> tuple[Path, dict[str, Any]]
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `epic` | | The run's directory (one of `all()`). |
| `output` | `<epic>/traces/<%Y%m%dT%H%M%SZ>.trace.json` | Where to write; parent directories are created. |
| `start`, `end` | unbounded | As in [Selecting sessions](#selecting-sessions). |

Collects exactly the ids the run recorded, named by role (`opened`), reading the epic's
`sessions/` and every other directory a session says humanize kept it in, with the epic's
`profile.jsonl` and `flow-profile.jsonl`. Returns the path written and the document.

### `Epics.trace`

```python
def trace(self, *, sessions: str | Iterable[str] | None = None,
          agents: Mapping[str, Iterable[str]] | None = None,
          output: str | os.PathLike[str] | None = None,
          start: str | None = None, end: str | None = None,
          profile: str | os.PathLike[str] | None = None,
          flow_profile: str | os.PathLike[str] | None = None,
          kept: Iterable[str | os.PathLike[str]] | None = None) -> dict[str, Any]
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `sessions` | every session | See [Selecting sessions](#selecting-sessions). |
| `agents` | none | Names for sessions: name → ids. |
| `output` | nothing written | A file to write, parent directories created. |
| `start`, `end` | unbounded | Window. |
| `profile` | none | A `profile.jsonl` to draw. |
| `flow_profile` | none | A `flow-profile.jsonl` to draw. |
| `kept` | every epic's `sessions/` (of this workspace; of every workspace for an `Hmz()` with no workspace) | Where humanize kept sessions. |

The workspace is the `Hmz` workspace; with `Hmz()` and named sessions, sessions are collected
wherever they were recorded; `Hmz("/path")` keeps only sessions recorded there (the path is
taken as given; `~` is not expanded). Returns the document.

### `Epics.timeline` {#epics-timeline}

```python
def timeline(self, epic: Path) -> Timeline
```

Gathers what [`traced`](#epics-traced) gathers -- the ids the run recorded, where it kept
them -- with the run, the tree of flows it called, its `profile.jsonl` and its
`flow-profile.jsonl`, and lays them out as
an [Exomyth timeline](#timeline). Writes nothing. `Timeline.document` is the document;
`Timeline.span(id)` one span, whole.

### `Epics.bundled`

```python
def bundled(self, epic: Path, *, output: str | os.PathLike[str] | None = None,
            transcript: str | None = None) -> tuple[Path, dict[str, Any]]
```

Writes the [export](#export) archive; returns its path and the manifest as written.

### `collect` <Badge type="info" text="internal" />

`hmz.runtime.tracing.collect(workspace=None, *, sessions=None, agents=None, output=None,
start=None, end=None, profile=None, flow_profile=None, kept=None) -> dict`: what `traced` and `trace` call. `hmz.runtime.tracing.collector.gather(workspace=None, *, sessions=None, agents=None,
start=None, end=None, kept=None) -> list[Session]`: the sessions `collect` would draw, which
`timeline` lays out.

## Watching a run instead

A trace is made afterwards. While a run is going, the [monitor](/user/monitor) shows the
same agents, their handovers, and what each model has cost and is costing now.
