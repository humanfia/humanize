<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Exporting a run

Pack one whole run into a single archive you can attach to an issue or send to somebody who
was not there. Use this when a run did something you want a second pair of eyes on, or when
you are reporting a bug in a flow or an agent. The archive holds the agents' own logs, a
timeline of the run and what each CLI was, with every credential struck out.

## Try it

Open `/epics`, press <kbd>enter</kbd> on the run, then choose **export run**.

<HmzCast name="epics" alt="/epics listing the runs of this directory, newest first; enter on one shows where it is written down and offers to resume it or export it; export it reports where the archive landed, how big it is, and what the trace inside it holds" />

When it is done, the line under the list, and the transcript, say where it went:

```text
/tmp/hmzdocs-C/app/.humanize/20260930T053725.504Z-a3d685.epic.tar.gz · 162 kB · 3 sessions, 53 slices
```

## Before you start

- A run to export. Every run of a flow is kept, finished or not, and `/epics` lists the runs of
  the directory you started `hmz` in: start it where the run was.
- Nothing else. Exporting starts no agent and spends nothing.

## What an export is

An export is the opposite of an [error report](/user/reporting). A report is sent by
humanize, on its own, and carries nothing you typed. An export is **your own run, sent on
purpose**: the task, the prompts, what the agents said, and whatever of your files they
wrote into a log. It is made on your machine, lands as a file, and goes nowhere until you
attach it somewhere yourself.

Three things go into it:

- **The run's own record**, as humanize kept it: what happened, a line at a time.
- **Each agent's log**, as its CLI wrote it, copied from where the run kept it.
- **A timeline** of the whole run, gathered as part of the export, so whoever receives it can
  open it in [Perfetto](/user/tracing) without having humanize.

Every file is scrubbed of credentials on the way in.

## Example: export a Ralph loop for an issue

A [Ralph loop](/flows/ralph-loop) ran three rounds on a small project and was stopped by its
budget. Open the run in `/epics`:

```text
   2026-09-30 05:37 · ralph_loop                                              ①
   /tmp/hmzdocs-C/home/epics/-tmp-hmzdocs-C-app/20260930T053725.504Z-a3d685     ②
   It stopped with 1 agent in 3 sessions.                                     ③

   ❯ 1. resume run                resume the flow from this run
     2. export run                the entire run as an archive, with its trace

   enter choose · esc back
```

Choose **export run**. A moment later the list is back, with a line under it:

```text
   /tmp/hmzdocs-C/app/.humanize/20260930T053725.504Z-a3d685.epic.tar.gz · 162 kB · 3 sessions, 53 slices
   ④                                                                      ⑤       ⑥
```

### What each part means

1. **When the run started, and its flow.** The same line `/epics` lists it on.
2. **Where the run is kept**: under `~/.humanize/epics/`, or wherever `HUMANIZE_HOME` points,
   as it did for this example. This is what gets packed. You never need to go there yourself.
3. **How it ended, and what it opened.** `stopped` covers a spent budget,
   <kbd>ctrl+c</kbd> and a stop by hand; three rounds of a Ralph loop are three sessions.
4. **The archive.** It lands in `.humanize/` under the directory you ran `hmz` in, named after
   the run. Exporting the same run again replaces it with a fresh one.
5. **Its size.** Mostly the agents' logs. A long run of a chatty agent can be megabytes.
6. **What the timeline holds**: 3 sessions, and 53 slices, each a thing an agent did (a tool
   call, a message, a stretch of thinking). A run whose directory is
   [profiled](/user/tracing#profiling-a-run) adds the programs its agents ran:
   `1 session, 13 slices, 7 programs`.

## What is in it

<Term title="inside the archive">

<pre><span class="p">20260809T014455.212Z-9f21ab/</span>
├── <span class="b">manifest.json</span>            <span class="d">what this is: read it first</span>
├── epic.jsonl               <span class="d">what happened, a line at a time</span>
├── epic.&lt;flow&gt;_&lt;id&gt;.jsonl   <span class="d">the same, for each flow it called</span>
├── resume.jsonl             <span class="d">for a flow that can be picked up</span>
├── profile.jsonl            <span class="d">for a profiled run</span>
├── traces/
│   └── export.trace.json    <span class="d">the whole run as one timeline</span>
└── sessions/
    └── &lt;session&gt;/…          <span class="d">each CLI's own log of the conversation</span></pre>

</Term>

A file the run never wrote is left out: `resume.jsonl` only for a flow that
[can be picked up](/user/resuming), `profile.jsonl` only for a
[profiled](/user/tracing#profiling-a-run) run.

**`manifest.json`** is what lets somebody else read the rest:

- humanize's version, Python's, and the machine's;
- the flow, the task, and how the run ended;
- each agent's CLI, model, effort and account (by name only);
- the workspace, and the git commit it is on when you export;
- for each CLI, the version it reports and the SHA-256 of the program that took the turns.
  These CLIs change weekly, and a bug is a bug in one build.

**`traces/export.trace.json`** is gathered as part of the export, so whoever opens the archive
can open the run as a [timeline](/user/tracing) without gathering anything themselves.

**`sessions/`** holds the logs themselves, a folder per session. Some CLIs keep no log file of a
conversation to copy: opencode, mimo, cursor-agent, and CLIs you added on the Accounts page of
`/settings`. Their sessions have no directory here, and the manifest says why against each one.
The trace still covers opencode and mimo sessions.

## What is never in it

A credential is not part of your run. Every file is scrubbed on the way in, and what was struck
reads `[redacted]`:

- **every value of every [account](/user/settings#accounts)** on this machine, wherever it
  appears: the keys, and the endpoints too. The run's own model names are kept.
- **keys in the shapes vendors issue them**: `sk-…`, `sk-ant-…`, `ghp_…`, `AIza…`, a JWT, a
  bearer token.
- **anything signed into a URL**: a user, a password, a token in the query string.
- **anything a log labels** as a token, a secret, an API key, a password or a credential.

Token counts are kept, since they are how a turn's cost is read. The archive names no owner
or group, and the file is readable by you alone.

## Check that it worked

It is a plain `.tar.gz`. List it, and read the manifest before you send it:

```console
$ tar tzf .humanize/20260930T054014.242Z-bdae4a.epic.tar.gz
20260930T054014.242Z-bdae4a/epic.jsonl
20260930T054014.242Z-bdae4a/resume.jsonl
20260930T054014.242Z-bdae4a/profile.jsonl
20260930T054014.242Z-bdae4a/traces/export.trace.json
20260930T054014.242Z-bdae4a/sessions/agent-claude@local-42733b7e-…/projects/-tmp-hmzdocs-C-app/42733b7e-….jsonl
20260930T054014.242Z-bdae4a/manifest.json
$ ls -l .humanize/20260930T054014.242Z-bdae4a.epic.tar.gz
-rw------- 1 nvidia nvidia 58848 Sep 30 05:40 .humanize/20260930T054014.242Z-bdae4a.epic.tar.gz
```

This one is a resumed run of `ralph_loop` that was profiled, so it has both
`resume.jsonl` and `profile.jsonl`. Unpacked, its manifest reads, in part:

```json
{
  "humanize": "0.1.0",
  "python": "3.12.14",
  "machine": "Linux-6.8.0-139-generic-x86_64-with-glibc2.39",
  "epic": "20260930T054014.242Z-bdae4a",
  "run": {
    "flow": "ralph_loop",
    "task": "Make the tests in test_slug.py pass. Change slug.py only.",
    "began": "2026-09-30T05:40:14.439Z",
    "ended": "2026-09-30T05:40:33.576Z",
    "how": "stopped",
    "resumable": true
  },
  "workspace": { "at": "/tmp/hmzdocs-C/app", "head": "" },
  "agents": [
    {
      "agent": "agent",
      "backend": "claude",
      "model": "claude-haiku-4-5-20251001",
      "effort": "low",
      "provider": "",
      "runs": "claude/claude-haiku-4-5-20251001:low"
    }
  ],
  "backends": {
    "claude": {
      "command": "claude",
      "version": "2.1.285 (Claude Code)",
      "sha256": "33dad1ec615a2e08cc78b494f05c110e49916de2c79d78ec8799ebf46b233d29",
      "logs": true
    }
  },
  "redacted": [
    "every account's own variables, by value, less what the run says it ran",
    "keys in the shapes the vendors mint them -- sk-, ghp_, AIza, a JWT",
    "whatever is signed into a URL, as a user, a password or a query",
    "anything a log named as a token, a secret, a key or a password"
  ]
}
```

`provider` is empty for an agent that ran as this machine is signed in. `head` is the git
commit the workspace was on, empty here because the project is not a git repository.
`redacted` says in words what was struck out of every file. Drop `traces/export.trace.json`
into [ui.perfetto.dev](https://ui.perfetto.dev) to see the timeline the receiver will.

::: tip Look before you send
`tar xzf` it somewhere and read what is going out. The task and every transcript are in it.
:::

## Variations

### Copying a few lines instead

For a few lines of the transcript, drag across them with the mouse. The status line says
`copied`.

| Gesture | Copies |
| --- | --- |
| drag | everything between where you pressed and where you let go |
| double click | the word under it, so a path or an id comes whole |
| triple click | the whole line, however many rows it wraps over |

What you get is the text as written, not as wrapped on screen. Hold <kbd>shift</kbd> while
dragging to use your terminal's own selection instead, wrapping and all.

It works over ssh, and lands on the clipboard of the machine you are sitting at. In tmux, set
`set-clipboard on`; some other terminals need clipboard access turned on too.

### Exporting from a script

::: details From Python
The same export is two calls on the run's directory, which `Hmz().epics.all()` lists, oldest
first:

```python
from hmz.sdk import Hmz

runs = Hmz().epics
epic = runs.all()[-1]                                # the newest run here
runs.traced(epic)                                    # gather the trace into the run
runs.bundled(epic, output="/tmp/for-the-issue.tar.gz")
```

`output` may be a file or a directory. Leave it out for `.humanize/` under the current
directory. See [SDK reference](/reference/sdk).
:::

## If it goes wrong

- **The line says `0 sessions, 0 slices`.** The archive was written, but the timeline in it is
  empty: the run ended before its first turn, its agents ran on Cursor Agent, or the CLI's
  logs have moved. See [Troubleshooting](/user/troubleshooting#_0-sessions-0-slices).
- **A session has no folder under `sessions/`.** Its CLI keeps no log file to copy (opencode,
  mimo, cursor-agent, or a CLI you added). The manifest says so against the session.
- **The run is not in `/epics`.** `/epics` lists the runs of the directory `hmz` was started
  in. Start it where the run was.

## Next steps

- [Tracing a run](/user/tracing): reading the timeline yourself
- [Reporting](/user/reporting): what humanize sends on its own, which is far less
- [Picking a run up](/user/resuming): the other thing `/epics` offers about a run
- [Tracing reference](/reference/tracing): the archive and the trace, exactly

<style scoped>
kbd {
  display: inline-block;
  min-width: 1.7em;
  padding: 0 0.45em;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-base);
  font-size: 0.85em;
  font-weight: 500;
  line-height: 1.6;
  text-align: center;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}
</style>
