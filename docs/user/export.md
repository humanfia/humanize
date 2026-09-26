<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Exporting a run

An export packs one whole run into a single archive you can attach to an issue or send to
somebody who was not there. It holds the agents' own logs, a timeline of the run, and what
each CLI was, with every credential struck out.

## Try it

Open `/epics`, press <kbd>enter</kbd> on the run, then choose **export it**.

![/epics listing the runs of this directory, newest first; enter on one shows where it is
written down and offers to resume it or export it; export it reports where the archive
landed, how big it is, and what the trace inside it holds](/demo/epics.gif)

When it is done, the line under the list, and the transcript, say where it went:

```
/home/you/code/app/.humanize/20260809T014455.212Z-9f21ab.epic.tar.gz · 812 kB · 3 sessions, 412 slices
```

The archive lands in `.humanize/` under the directory you ran `hmz` in, named for the run.
Exporting the same run again replaces it with a fresh one.

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
[profiled](/user/settings#whether-a-run-here-is-profiled) run.

**`manifest.json`** is what lets somebody else read the rest:

- humanize's version, Python's, and the machine's;
- the flow, the task, and how the run ended;
- each agent's CLI, model, effort and account (by name only);
- the workspace, and the git commit it is on when you export;
- for each CLI, the version it reports and the SHA-256 of the program that took the turns.
  These CLIs change weekly, and a bug is a bug in one build.

**`traces/export.trace.json`** is gathered as part of the export, so whoever opens the archive
can open the run as a [timeline](/user/tracing) without gathering anything themselves.

**`sessions/`** holds the logs themselves, not links to them. Some CLIs keep no log file of a
conversation to copy: opencode, mimo, cursor-agent, and CLIs you added at `/providers`. Their
sessions have no directory here, and the manifest says why against each one. The trace still
covers opencode and mimo sessions.

## What is never in it

An export sends your own run on purpose: the task, the prompts, what the agents said, and
whatever of your files they wrote into a log. A credential is not part of that. Every file is
scrubbed on the way in, and what was struck reads `[redacted]`:

- **every value of every [account](/user/providers)** on this machine, wherever it appears: the
  keys, and the endpoints too. The run's own model names are kept.
- **keys in the shapes vendors issue them**: `sk-…`, `sk-ant-…`, `ghp_…`, `AIza…`, a JWT, a
  bearer token.
- **anything signed into a URL**: a user, a password, a token in the query string.
- **anything a log labels** as a token, a secret, an API key, a password or a credential.

Token counts are kept, since they are how a turn's cost is read. The archive names no owner
or group, and the file is readable by you alone.

::: tip Look before you send
It is a plain `.tar.gz`. `tar xzf` it somewhere and read what is going out.
:::

## Copying a few lines instead

For a few lines, drag across them with the mouse. The status line says `copied`.

| Gesture | Copies |
| --- | --- |
| drag | everything between where you pressed and where you let go |
| double click | the word under it, so a path or an id comes whole |
| triple click | the whole line, however many rows it wraps over |

What you get is the text as written, not as wrapped on screen. Hold <kbd>shift</kbd> while
dragging to use your terminal's own selection instead, wrapping and all.

It works over ssh, and lands on the clipboard of the machine you are sitting at. In tmux, set
`set-clipboard on`; some other terminals need clipboard access turned on too.

::: details From Python
The same export is two calls on the run's directory, which `Hmz().epics.all()` lists:

```python
from hmz.sdk import Hmz

runs = Hmz().epics
runs.traced(epic)                                    # gather the trace into the run
runs.bundled(epic, output="/tmp/for-the-issue.tar.gz")
```

`output` may be a file or a directory. Leave it out for `.humanize/` under the current
directory. See [SDK reference](/reference/sdk).
:::

## See also

- [Tracing](/user/tracing): reading a run yourself, as a timeline
- [Reporting](/user/reporting): what humanize sends on its own, which is far less
- [Picking a run up](/user/resuming): the other thing `/epics` offers about a run

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
