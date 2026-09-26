# Tracing

A trace is one timeline of what a run's agents did: every tool call, message and wait for
reasoning, across every session, gathered afterwards out of the logs the coding agent CLIs
wrote. It is a Chrome JSON trace, so [ui.perfetto.dev](https://ui.perfetto.dev) or
`chrome://tracing` opens it.

::: code-group

```console [/epics]
/epics  →  the run  →  enter  →  export it

/home/you/code/.humanize/20260809T014455.212Z-9f21ab.epic.tar.gz · 812 kB · 3 sessions, 412 slices
```

```python [Python]
from hmz.sdk import Hmz

runs = Hmz().epics                      # or Hmz("~/code/other").epics
last = runs.all()[-1]                   # the newest run of this workspace
where, document = runs.traced(last)     # into the run's own traces/
print(document["otherData"])            # what it holds
```

:::

**Export it** writes the trace into the run's directory as `traces/export.trace.json` and
packs it into the archive beside the run; the line says where the archive went, its size, and
what the trace holds. A [profiled](#profiling-a-run) run adds a third count:
`1 session, 10 slices, 3 programs`. See [Exporting a run](/user/export).

## Collecting

| Call | Writes |
| --- | --- |
| **export it** on `/epics` | `traces/export.trace.json` in the run's directory, replaced each time, and the archive |
| [`Epics.traced(epic)`](#from-python) | `traces/<UTC datetime>.trace.json` in the run's directory, a new one each time |
| `Epics.traced(epic, output=…)`, `Epics.trace(output=…)` | that file, its directory made if missing |
| [`Epics.trace()`](#from-python) with no `output` | nothing: the document is returned |

## Reading the trace

```
process   agent          builder · 4 sessions
  track     main ──────────────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓
  track     subagent · explore ▶      ▓▓▓▓▓▓▓▓▓▓▓
process   agent          reviewer · 2 sessions
  track     main ──────────────▶            ▓▓▓▓        ▓▓▓▓
```

| In the trace | Is |
| --- | --- |
| a **process** | one [agent](#what-counts-as-one-agent) and everything it drove, named `<agent> · <n> sessions`; or, for a [profiled](#profiling-a-run) run, one program, named `<program> · <pid>` |
| a **track** | one row of that agent's sessions: `main` for the ones somebody started, `subagent` for what a turn reached for. Sessions of one agent that never overlap share a track; root sessions and sub-agents stay apart. For a program, one of its threads. |
| a **slice** | one action: a tool call, a message, or a wait for reasoning. Click one for its arguments: the prompt, the reasoning, the tool input and output, as much as the backend wrote down. |

A row of sub-agents all started as one kind is named after it: `subagent · explore`. A
sub-agent that started one of its own is `subagent 2`. A second row at the same depth has `#2`
after its name, and actions that overlap inside a row spill into lanes of their own, `~2`.

The document's `otherData` says what was asked for and what was found. Every value is a
string.

| Key | |
| --- | --- |
| `workspace` | The workspace collected, where there was one. |
| `selected` | The sessions named, or `<n> sessions` for many. |
| `agents`, `backends` | The agents and backends found, comma-separated. |
| `sessions`, `slices`, `tracks` | How many of each. |
| `start`, `end` | The first and last moment in it. |
| `programs` | How many programs were drawn. Only in a trace of a profiled run. |

A trace that found nothing carries `workspace` and `selected` alone.

## What counts as one agent {#what-counts-as-one-agent}

An **agent** is one configuration (a backend at a model at an effort) together with every
sub-agent it started. A Ralph loop of a hundred one-shot sessions reads as one agent, and a
sub-agent belongs to the agent that started it, whatever it ran at.

Two agents at the same configuration read as one, because a backend logs a session under an
id and never says whose it was. A trace of a run does not have that problem: it reads which
role opened which session off the run's own record, so `rlar` traces as `actor` and
`reviewer` whatever they ran at. For sessions no run recorded, say it yourself with `agents`,
each name mapped to the session ids it opened:

```python
Hmz().epics.trace(
    sessions=["0a1b2c3d", "5f6e7a8b"],
    agents={"actor": ["0a1b2c3d"], "reviewer": ["5f6e7a8b"]},
)
```

Driving agents yourself with the lower-level [agent layer](/reference/agents), each
`AgentBase` has that mapping on it: `agents={a.id: a.opened for a in (actor, reviewer)}`. The
flow API's `Agent` has neither attribute; a run of a flow writes the mapping into its epic.

Sessions nobody claims are read as the configuration they ran at.

## Epics {#epics}

Every run of a flow is one **epic**, a directory written as the run happens:

```
~/.humanize/epics/<workspace>/<datetime>-<hex>/
    epic.jsonl                      what happened, a line at a time
    epic.<flow>_<hex>.jsonl         the same, for one flow the run called
    resume.jsonl                    what a resumable flow did, for --resume
    profile.jsonl                   the programs it ran, for a run that was profiled
    sessions/<session>/…            a link per file the backend logged that session to
    traces/export.trace.json        the trace exporting the run gathers, replaced each time
    traces/<datetime>.trace.json    one gathered from Python, kept every time
```

- **`<workspace>`** is the absolute path with every character that is not a letter or a digit
  flattened to `-`, as the backends flatten a workspace into the folder they log it under:
  `/home/you/code` is `-home-you-code`.
- **`<datetime>-<hex>`** is the UTC moment the run began and six hex digits, since two runs
  may begin in one millisecond: `20260809T014455.212Z-9f21ab`.

`epic.jsonl` is JSON lines, appended and flushed as the run goes, so a run that died still
says what it got to. Every line has `event` and `at`.

| `event` | Written | Carries |
| --- | --- | --- |
| `began` | when the flow starts | `flow` as it was named, its canonical `ref`, `task`, `workspace`, `resumable`, `picked_up` (the epic it was picked up from, where there was one), `agents` (one per role: `agent`, `backend`, `model`, `effort`, `provider`), `envs` as `-e` spells each, `params` and `budget` |
| `opened` | each time an agent opens a session | `agent`, `backend`, `provider`, `session` (the backend's id), `name`, and `where` its links are |
| `called` | when the flow calls another flow | `flow` as it was asked for, `task`, and `epic`: the record that call is written to |
| `returned` | when that call returns, however it ended | `flow` and the same `epic` |
| `usage` | as the run stops | what every session spent: `cost`, `output_tokens`, `seconds` |
| `ended` | when the flow stops | `how`: `done`, `failed` or `stopped` |

An agent stopped by hand, and a run whose budget ran out, end `stopped` rather than `failed`.

```json
{"event": "opened", "at": "2026-08-09T01:44:58.020Z", "agent": "builder", "backend": "claude", "provider": "work", "session": "0a1b2c3d-…", "name": "builder-claude@work-0a1b2c3d-…", "where": "sessions/builder-claude@work-0a1b2c3d-…"}
```

**`sessions/<session>/`** holds a link to every file that session was logged to, named for the
role, the CLI, the account and the backend's id: `builder-claude@work-0a1b2c3d`, with
`@local` for the account this machine is already signed into. The links are made when the
session opens and again when the run ends, since a backend goes on writing after the turn that
opened the session. A filesystem that will not make one is a run without links rather than a
run that stops.

![One run's sessions/ directory: a directory per session, named for its agent, CLI and account,
holding a symlink to the log Claude Code itself is writing](/demo/run-linked.png)

**It is not a transcript.** The backend's own log is the turn-by-turn record. An epic keeps the
shape of the run: enough to gather a trace afterwards from the ids alone.

**An epic covers one run**, and closes when the flow finishes, fails or is stopped. Running the
flow again is another run and another epic. **`resume.jsonl`** is kept only by a
[resumable flow](/reference/flows#a-flow-that-can-be-picked-up): one JSON line per flow call
and how it ended, per write to `ctx.state` (`{"t": "set", …}`), per session once its CLI has
named it, and per temporary copy or scratch directory kept. A run picked up from it is a run
of its own, whose `began` says which epic it was `picked_up` from, so a week of stops and
starts reads as the week it was. See [Picking a run up](/user/resuming).

From Python, [`Hmz().epics`](/reference/sdk#epics) reads all of it back:

```python
from hmz.sdk import Hmz

runs = Hmz().epics
for epic in runs.all():                        # this workspace, oldest first
    ran = runs.read(epic)
    print(epic.name, ran.flow, ran.how, runs.opened(epic))
    # 20260809T014455.212Z-9f21ab rlar done {'actor': ['0a1b…'], 'reviewer': ['5f6e…']}
```

## Records of called flows

A flow may [call another](/reference/flows#a-flow-that-calls-another-flow), and each call
gets a record of its own beside the run's: `epic.<flow>_<hex>.jsonl`, the flow as it was
asked for with anything but letters, digits, `.`, `_`, `@` and `-` flattened to `-`. A call
of `phases:plan` is `epic.phases-plan_ed763a.jsonl`. The record of whatever called it says
`called` and `returned`, with that filename in `epic`. One flow called twice is two records,
each with its own sessions.

- A called flow's record holds the same events as the run's. Its `began` also carries
  `under`, the record that called it. Its `ended` says how *the call* ended: a call that
  raised is `failed` inside a run that may still be `done`.
- **Records nest.** A call made inside a called flow is written under *that* flow's record, so
  a recursion reads back as the tree it ran as. Two calls that ran at once are two records
  whose `began` and `ended` overlap.
- It is still one run and one directory. `Epics.sessions(epic)` reads every record, so every
  session of a run is one list, each saying which `flow` opened it and in which `record`.
- A session the flow [branched](/weaver/branching) also says `parent`, the id of the
  conversation it was forked from, which the backend's own log cannot say.

`Epics.read(epic).called` lists the calls the run itself made. The internal
`hmz.runtime.epic.tree(epic)` <Badge type="info" text="internal" /> reads the whole tree, each
call with what it called under `calls`.

## Profiling a run {#profiling-a-run}

An agent's turn is mostly other programs: the tests, the build, a grep. None of that is in a
backend's log, which records the tool call rather than the process. A workspace may have its
runs **profiled** as well as traced, on the second page of `/settings`:

```
3. profile          on   profile the programs a run here starts
```

While the flow runs, the programs under it are sampled (what each was, what started it, how
long it took) into `profile.jsonl` in the run's epic. Collecting the run draws them in the
same document as its sessions: a process is a program and a track is one of its threads.
So *what was this run doing at 09:41* has one answer:

```
process   agent          builder · 4 sessions
  track     main ──────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
process   program        pytest · 41207
  track     main ──────▶       ▓▓▓▓▓▓▓▓▓▓
```

It is sampled rather than intercepted: nothing sits between an agent and what it runs. A
program that lived thirty milliseconds may be missed, and a machine whose processes cannot be
read is a run with no profile rather than a run that stops.

## Where the logs are read from {#where-the-trajectories-come-from}

Each backend's own home directory, which humanize only reads:

| Backend | Moved by | Default |
| --- | --- | --- |
| Claude Code | `CLAUDE_CONFIG_DIR` | `~/.claude` |
| Codex | `CODEX_HOME` | `~/.codex` |
| DeepSeek Harness | `DSH_HOME` | `~/.dsh` |
| Grok Build | `GROK_HOME` | `~/.grok` |
| Kimi Code | `KIMI_CODE_HOME` | `~/.kimi-code` |
| pi | `PI_CODING_AGENT_DIR` | `~/.pi/agent` |
| Qwen Code | `QWEN_HOME` | `~/.qwen` |
| opencode | `XDG_DATA_HOME`, as `$XDG_DATA_HOME/opencode` | `~/.local/share/opencode` |
| MiMo Code | `XDG_DATA_HOME`, as `$XDG_DATA_HOME/mimocode` | `~/.local/share/mimocode` |
| Antigravity | nothing | `~/.gemini/antigravity-cli` |
| ZCode | nothing | `~/.zcode` |
| Cursor Agent | <Badge type="warning" text="no reader" /> | nothing is collected |

Every backend but Cursor Agent has a reader; opencode, MiMo Code and Antigravity keep their
sessions in SQLite and are read with a query. A CLI added over ACP keeps no log humanize can
find. A home that does not exist is skipped, so collecting on a machine with one backend
installed works.

## What one trace holds

**A trace of a run** holds the sessions that run opened and no others. They are asked for by
the ids the run wrote down, not by the directory it ran in, so a directory run in fifty times
has fifty separate traces, a run that opened nothing is a trace of nothing, and a flow that
ran on a [machine of its own](/reference/machines), logged under a path this workspace never
heard of, is in its own trace all the same.

```python
runs = Hmz().epics
last = runs.all()[-1]
runs.traced(last)                             # its own sessions, into its own traces/
runs.traced(last, start="3 days ago")         # and only what it did since
```

**A trace of a directory or of sessions** is how sessions no flow drove are read back, such
as an afternoon at `claude`:

```python
Hmz().epics.trace()                                    # every session of this workspace
Hmz("~/code/other").epics.trace()                      # every session of another
Hmz().epics.trace(sessions="0a1b2c3d,5f6e")            # two sessions, wherever they ran
Hmz("~/code/other").epics.trace(sessions="0a1b2c3d")   # that session, only if it ran there
```

- **Naming sessions alone**, on an `Hmz()` given no workspace, collects them wherever they
  were recorded.
- **Naming a workspace with them**, as `Hmz("~/code/other")`, keeps only the named sessions
  recorded there.
- **Naming no sessions** collects the workspace, whichever run opened what is in it.

A session is named by its whole id, by the key the trace shows it under, or by a leading part
of either, and the sub-agents it started come with it. This kind of trace belongs to no run,
so it is written only where an `output` says, and `/epics` does not offer it.

## From Python {#from-python}

[`Hmz().epics`](/reference/sdk#epics) is the way in: `traced` for a run, `trace` for anything
else.

### `Epics.traced`

```python
def traced(self, epic: Path, *, output: str | os.PathLike[str] | None = None,
           start: str | None = None, end: str | None = None) -> tuple[Path, dict[str, Any]]
```

| Parameter | |
| --- | --- |
| `epic` | The run, by its directory: one of `Epics.all()`. |
| `output` | Where to write it, or `None` for `traces/<UTC datetime>.trace.json` in the run's directory. |
| `start`, `end` | Cut out sessions outside this window, in any wording [dateparser](https://dateparser.readthedocs.io/) understands: `"3 days ago"`, `"2026-08-09 09:00"`. |

Returns where the trace was written and the document. It collects the ids the run's roles
opened, labelled by role, with the run's `profile.jsonl` where it was profiled.

### `Epics.trace`

```python
def trace(self, *, sessions: str | Iterable[str] | None = None,
          agents: Mapping[str, Iterable[str]] | None = None,
          output: str | os.PathLike[str] | None = None,
          start: str | None = None, end: str | None = None,
          profile: str | os.PathLike[str] | None = None) -> dict[str, Any]
```

| Parameter | |
| --- | --- |
| `sessions` | Which sessions: a comma-separated string or an iterable of ids. `None` is every session of the workspace; an **empty** iterable is no session at all. |
| `agents` | Names for sessions, each mapped to the ids it opened. See [What counts as one agent](#what-counts-as-one-agent). |
| `output` | A file to write it to, its directory made if missing, or `None` to write nothing. |
| `start`, `end` | As for `traced`. |
| `profile` | A run's `profile.jsonl`, to draw its programs beside the sessions. |

Returns the document. Both raise `ValueError` for a time dateparser cannot read
(`cannot parse time: …`) or an empty session id (`session id cannot be empty`).

<Badge type="info" text="internal" /> Both call `hmz.runtime.tracing.collect(workspace,
*, sessions, agents, output, start, end, profile)`, the workspace being the `Hmz` one or, for
`traced`, none.

## Watching a run instead

A trace is for afterwards. While a run is going, `/monitor` shows the same shape live: who is
working, each handover between agents and how often it happened, and what each model has cost
in tokens and money and the rate it is costing now. See [Monitor](/user/monitor).
