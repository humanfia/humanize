---
title: Trace formats
description: Read the Chrome trace and the Exomyth timeline document that Humanize builds from an epic, and know which coding agent logs they are read from.
---

# Trace formats

Humanize builds two trace documents from an epic: a Chrome trace file on disk and an in-memory Exomyth timeline served on demand. Both read the same sessions from each coding agent's logs. To view them, see [Trace a run with Exomyth](/user/tracing).

## The two documents

| | Chrome trace | Exomyth timeline |
| --- | --- | --- |
| Made for | Perfetto, `chrome://tracing` | The Exomyth view of the app and the terminal |
| One process is | One agent and all its sessions | One session, one program, or the flow |
| Payloads | In every event | Left out, fetched one span at a time |
| On disk | `<epic>/traces/<YYYYMMDDTHHMMSSZ>.trace.json` | Never |
| From Python | `Hmz().epics.traced(epic)`, `Hmz().epics.trace(...)` | `Hmz().epics.timeline(epic)` |
| From the daemon | | `runs.timeline`, `runs.span` |

```python
from hmz.sdk import Hmz

epics = Hmz().epics
epic = epics.all()[-1]
path, trace = epics.traced(epic)
timeline = epics.timeline(epic)
```

`epics.all()` lists the epics in the current workspace, oldest first. `traced` writes a new trace file and returns its path and document. Selecting **export epic** in `/epics` in the terminal writes `<epic>/traces/export.trace.json` instead, replacing it each time. No `hmz` CLI command gathers a trace.

See the [SDK reference](/reference/sdk) for signatures and [Daemon and wire](/reference/daemon) for daemon methods.

## Sessions and actions

Every log reader produces the same model.

| Concept | Is |
| --- | --- |
| Session | One conversation of one agent or sub-agent. Its key is `<harness>:<id>`. It has a `label` (`main`, or what a sub-agent was started as), a `title` (a short id and the first prompt), a `parent` key for a sub-agent, and `args` such as `model`, `effort` and `cwd`. |
| Action | One slice of a session: a `name`, a `category`, a start and an end in epoch seconds, `args`, and the key of the session it started, if any. |
| Agent | What sessions are grouped by: `<name> · <model> · <effort>`, empty parts left out. |

A session takes its agent name from its root session. `<name>` is the agent name recorded by the epic, or the harness name if none was recorded. A sub-agent belongs to the agent that started it.

| Category | Is |
| --- | --- |
| `turn` | A prompt and everything until the next prompt. `args.prompt` holds the prompt. |
| `llm` | A model call or reasoning. |
| `tool` | A tool call, named `<tool>: <summary>`. `args.tool` and `args.input` hold the call. |
| `message` | Text the agent said, named `say: <summary>`. |
| `event` | Anything else the log records. |
| `session` | Added when drawing: one span over everything a session did. |

A name is one line. The summary in it is at most 96 characters; the name of a `session` span is at most 120. In `args`, strings are truncated at 4096 characters or fewer and lists at 32 items.

## Chrome trace {#chrome}

```json
{"traceEvents": [...], "displayTimeUnit": "ms", "otherData": {...}}
```

If an epic has no profile and no session with actions, `traceEvents` is empty.

### Processes and tracks

| Chrome concept | Is | Name |
| --- | --- | --- |
| Process, one per agent | Numbered from 1 in order of first action. | `<agent> · <n> sessions`, or `· 1 session` |
| Process, one per program | For an epic with an environment profile. Numbered after the agents. | `<program> · <pid>` |
| Process `python` | For an epic with a flow profile. Numbered last. | `python` |
| Track of an agent | A row of sessions. Sessions of one depth that do not overlap share a row. | `main` for root sessions; `subagent` one level down; `subagent <depth>` deeper. A row of sub-agents of one kind adds ` · <kind>`. |
| Track of a program | One thread. | `main`, or `thread <tid>` |
| Track of `python` | The frames, nested. | `flow` |

The second row of an agent at one depth is named `<name> #2`, the third `#3`, and so on. Actions that overlap without nesting go to extra lanes named `<name> ~2`, `~3`, and so on. Track IDs are `row × 100 + lane`, with rows counted from 1.

### Events

| `ph` | Emitted for | Fields |
| --- | --- | --- |
| `M` | `process_name`, `process_sort_index` and `process_labels` per process; `thread_name` and `thread_sort_index` per track (the `flow` track of `python` has only `thread_name`) | `pid`, `tid`, `name`, `args` |
| `X` | Every action, every `session` span, every program thread, every frame | `pid`, `tid`, `cat`, `name`, `ts` and `dur` in microseconds, `args` |
| `s`, `f` | A session starting another | `cat` and `name` are `spawn`, with a shared `id`. `s` is at the action that started it, `f` (with `bp` set to `e`) at the start of the new session. |

`cat` is the action's category, `process` for a program thread, or `sample` for a Python flow frame. `ts` is epoch microseconds.

| Slice | `args` |
| --- | --- |
| Action | The action's own `args`, plus `at` (ISO 8601, UTC) and `session` (the session key) |
| `session` span | The session's `args`, plus `agent`, `parent`, `at` and `session` |
| Program thread | `pid`, `ppid`, `argv`, `cpu` (seconds), `at` |
| Frame | `at` |

Example slice:

```json
{"ph": "X", "pid": 1, "tid": 100, "cat": "tool", "name": "Task: look at the cart", "ts": 1795000004000000, "dur": 11000000, "args": {"tool": "Task", "input": {"description": "look at the cart"}, "at": "2026-11-18T11:06:44+00:00", "session": "claude:56107ec6"}}
```

### `otherData`

Every value is a string.

| Key | Present | Value |
| --- | --- | --- |
| `workspace` | A workspace was given | Its path |
| `selected` | Sessions were named | The ids, or `<n> sessions` for more than four |
| `agents`, `backends` | The trace is not empty | The names, sorted and joined with `, ` |
| `sessions`, `slices`, `tracks` | The trace is not empty | Counts |
| `start`, `end` | The trace is not empty | First and last moment, ISO 8601, UTC |
| `programs` | The trace has an environment profile | Count of programs |

### Select sessions

`traced` holds exactly the sessions the epic recorded, wherever they were logged. It takes `output`, `start` and `end` as `trace` does; with no `output` it writes into the epic's `traces/`. Use `trace` to select sessions manually.

| Argument of `trace` | Rule |
| --- | --- |
| `sessions` | `None` is every session of the workspace. A list of ids, or one comma-separated string, keeps those. An empty list is no session. An id matches a session whose key, id or short id starts with it. A kept session brings its sub-agents. |
| `agents` | Names for sessions, as a mapping of name to ids. |
| `start`, `end` | A time in any wording, such as `3 days ago`. Everything outside the window is dropped. |
| `profile`, `flow_profile` | Paths of an epic's `profile.jsonl` and `flow-profile.jsonl`. |
| `output` | A file to write. Nothing is written without it. |
| `kept` | Directories where Humanize kept sessions, read beside each harness's home. The default is the `sessions/` of every epic, or of the workspace's epics where `Hmz` was given a workspace. |

`trace` raises `ValueError` with `cannot parse time: <text>` for an invalid `start` or `end`, and `session id cannot be empty` for an empty ID. Missing or unreadable logs are skipped without failing the trace.

## Exomyth timeline {#timeline}

An epic with no sessions produces this timeline:

```json
{
  "version": 1,
  "layout": "a1ed23f784909965",
  "epic": "20261118T093000.000Z-4f2a9c",
  "origin": 1794994200.0,
  "live": false,
  "strings": ["", "flow", "ralph_loop", "flows", "epic:20261118T093000.000Z-4f2a9c", "done"],
  "processes": [
    {"id": 0, "kind": "flow", "name": 2, "key": 4, "pid": 0, "start": 0, "end": 60000000,
     "tracks": [0], "agent": 0, "role": 0, "backend": 0, "model": 0, "label": 5, "record": 0,
     "parent": -1}
  ],
  "tracks": [
    {"process": 0, "name": 3, "first": 0, "count": 1, "depths": 1,
     "spans": {"start": [0], "dur": [60000000], "depth": [0], "cat": [1], "name": [2],
               "model": [0], "in": [0], "out": [0]}}
  ],
  "spawns": {"span": [], "process": []},
  "summary": {"start": 0, "end": 60000000, "processes": 1, "tracks": 1, "spans": 1,
              "categories": {"flow": {"count": 1, "time": 60000000, "in": 0, "out": 0}}}
}
```

Every key is always present. Times are whole microseconds since `origin`. Inside `processes` and `tracks`, every text field except a process's `kind` is an integer index into `strings`, where index 0 is the empty string.

| Key | Is |
| --- | --- |
| `version` | `1`. |
| `layout` | A hex digest. It changes when a span id would name another span. It stays the same while spans only grow longer. |
| `epic` | The epic's name. |
| `origin` | Epoch seconds of the earliest moment in the document. The wall clock of `t` microseconds is `origin + t / 1e6`. |
| `live` | `true` while the epic has not ended. The document grows, so read it again. |
| `strings` | Every text of the document, each once. |
| `processes` | The first level of lanes. |
| `tracks` | The second level of lanes, each of one process. |
| `spawns` | What started each session: columns `span` and `process`, sorted. |
| `summary` | `start` (0), `end`, counts of `processes`, `tracks` and `spans`, and per category its `count`, summed `time`, and `in` and `out` tokens. |

### Processes

Processes are ordered: the epic's flows, `python` (if flow-profiled), sessions by start time, and programs by start time and PID.

| `kind` | Is | `name` | `key` | Track name |
| --- | --- | --- | --- | --- |
| `flow` | The epic and every flow it called | The flow, or `chat` for a chat | `epic:<name>` | `flows` |
| `flow` | The flow's own Python, where profiled | `python` | `python:epic:<name>` | `flow` |
| `session` | One session that did anything | `<label> · <title>` | The session key | The label, or `main` |
| `os` | One program of an environment profile | `<program> · <pid>` | `pid:<pid>:<start>` | `threads` |

| Field | Is |
| --- | --- |
| `id` | Its index in `processes`. |
| `parent` | A process id, or `-1`. A sub-agent hangs from the session that started it. A session the epic opened hangs from the epic's `flow` process, as does `python`. A program hangs from the profiled program that held its parent pid when it started. |
| `pid` | The operating system's pid for `os`, else 0. |
| `agent` | The agent, named as above. |
| `role` | The role of the flow that the agent filled, for a root session the epic recorded. |
| `backend`, `model` | The harness, and the model the session logged. |
| `label` | The session's label. For the epic, how it ended. For a program, its name. For `python`, `python`. |
| `record` | The epic's record file of the flow call that opened the session. |
| `start`, `end` | Over its spans. |
| `tracks` | Its track ids, in lane order. |

### Tracks and spans

Each span is placed in the first lane where it nests inside the open span above it. Spans that overlap without nesting go to the next lane, a track suffixed with ` ~<n>`. Two spans on the same track and depth never overlap.

| Track field | Is |
| --- | --- |
| `process` | Its process. |
| `name` | The track name. |
| `first` | The id of its first span. |
| `count` | How many spans. |
| `depths` | The deepest depth plus 1. |
| `spans` | Columns, each `count` long and sorted by start: `start`, `dur`, `depth`, `cat`, `name`, `model`, `in`, `out`. `in` and `out` are the tokens the span reports, else 0. |

| `cat` | Span |
| --- | --- |
| `flow` | The epic, and each flow call inside its caller. One that has not returned ends at `summary.end`. |
| `session` | A session, over everything it did. |
| `turn`, `llm`, `tool`, `message`, `event` | The session's actions, under the `session` span. Where spans start and end together, `session` holds `turn` and `turn` holds the rest. |
| `process` | One per thread of a program. |
| `sample` | One per merged frame of the flow's Python, named as the frame. |

A span ID is its track's `first` plus its index in the track. IDs number all spans from 0 in track order without gaps.

### One span

The timeline omits span payloads. Fetch a span's payload by ID using `timeline.span(id)` in Python or `runs.span` with `{name, id, layout}` from the daemon.

```json
{"id": 4, "process": 1, "track": 1, "start": 5804000000, "dur": 11000000, "depth": 2, "cat": "tool", "name": "Task: look at the cart", "at": "2026-11-18T11:06:44+00:00", "args": {"tool": "Task", "input": {"description": "look at the cart"}, "session": "claude:56107ec6"}}
```

| Span | `args` |
| --- | --- |
| Action | The action's own `args`, plus `session` |
| `session` | The session's `args`, plus `agent`, `parent`, `session` |
| `flow` | `flow`, `task`, `how`, `record` |
| `process` | `pid`, `ppid`, `tid`, `argv`, `cpu` (seconds) |
| `sample` | `frame` |

An unknown ID raises `KeyError` in Python and returns `404` from the daemon: `Epic <name> has no span <id>.` Pass the `layout` from which you read the ID. If the epic was laid out again since, the daemon returns `409`: `Epic <name> has been laid out again; read it again.`

## Transcripts

`Hmz().epics.transcripts(epic)` and the daemon's `runs.trace` return the same sessions as plain lists in memory; the daemon answers them under `sessions`. Each session has `key`, `agent` (the name of its Chrome process), and `actions`. Each action has `category`, `name`, `at`, `start` (epoch seconds), `seconds`, and `args`.

## Profile files

Profile files are JSON Lines in the epic directory, written only when the epic is started with the matching profiling switch; the table names the `hmz exec` flag. See [Files on disk](/reference/files) for the rest of the directory.

| File | Switch | One line is | Fields |
| --- | --- | --- | --- |
| `profile.jsonl` | `--profile-environment` | One program seen or gone, sampled every 0.05 s | `event` (`ran` or `left`), `pid`, `ppid`, `name`, `argv`, `began`, `seen`, `ended`, `threads` |
| `flow-profile.jsonl` | `--profile-flow` | One stretch the flow's Python spent in one stack, sampled every 0.001 s | `t`, `dt`, `stack` |

Times are epoch seconds. Each entry in `threads` contains the thread ID, start time, end time, and CPU seconds. Each frame in `stack` is `function file:line`, outermost first.

## Readers per harness {#readers}

Humanize reads logs from each harness's home directory and from the epic's `sessions/<harness>/` directory. To change home paths, see [Environment variables](/reference/environment).

| Harness | Default home | Reads | Session key | Sub-agents |
| --- | --- | --- | --- | --- |
| `claude` | `~/.claude` | `projects/<workspace>/*.jsonl` and `subagents/**/*.jsonl` under it | `claude:<id>`, sub-agent `claude:<id>:<file>` | Yes |
| `agy` | `~/.gemini/antigravity-cli` | SQLite `conversations/<id>.db` | `agy:<id>` | Yes |
| `codex` | `~/.codex` | `rollout-*.jsonl` under `sessions` and `archived_sessions` | `codex:<id>` | Yes |
| `dsh` | `~/.dsh` | `sessions/*/*/session*.jsonl` | `dsh:<id>` | Yes |
| `grok` | `~/.grok` | `sessions/*/*/updates.jsonl` | `grok:<id>` | Yes |
| `kimi` | `~/.kimi-code` | `sessions/*/session_*/state.json` and each agent's `wire.jsonl` | `kimi:<session>:<agent>` | Yes |
| `pi` | `~/.pi/agent` | `sessions/*/*.jsonl` | `pi:<id>` | No |
| `omp` | `~/.omp/agent` | `sessions/*/*.jsonl` | `omp:<id>` | No |
| `qwen` | `~/.qwen` | `projects/<workspace>/chats/*.jsonl` | `qwen:<id>` | No |
| `opencode` | `~/.local/share/opencode` | SQLite `opencode.db`, read-only | `opencode:<id>` | Yes |
| `mimo` | `~/.local/share/mimocode` | SQLite `mimocode.db`, read-only | `mimo:<id>` | Yes |
| `mcode` | `~/.minimax` | `v2/sessions/*/*/*/*-session_*/messages.jsonl`, and SQLite `v2/sqlite/runtime-state.sqlite` for the workspace, read-only | `mcode:<id>` | No, their work is in the parent's log |
| `litellm` | `~/.cache/humanize/litellm` | `sessions/*.jsonl` | `litellm:<id>` | A forked conversation hangs from its origin |

`cursor-agent` and CLIs added over ACP have no reader; their sessions do not appear in traces, timelines, or transcripts.

For harness capabilities, see [Agents and harnesses](/reference/agents).
