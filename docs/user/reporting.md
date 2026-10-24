# Reporting

Humanize can send its developers a report when it crashes, and when a run goes five minutes
without any sign of progress. Nothing else is sent. This page says exactly what such a report holds, what it never holds,
and how to turn it on or off. Read it before you answer the question `hmz` asks the first time
it opens, or when you need to tell somebody what leaves your machine.

## Try it

The first time you open `hmz`, it asks. Nothing is sent until you say yes:

```text
╭────────────────────────────────────────────────────────────────╮
│                                                                │
│  Report errors to Humanize?                                    │
│  Send error reports to help fix bugs. Sent: the error and      │
│  where in Humanize it occurred; which flow was running, and    │
│  what each agent was configured to run; which coding agents    │
│  are installed, and account names; which skills and            │
│  flowverses are active, by name; that a run went five minutes  │
│  without any sign of progress; the version of Humanize, of     │
│  Python, and the operating system and architecture. Never      │
│  sent: nothing you typed: no task, prompt, or command; no      │
│  agent output, and nothing from any transcript or session      │
│  log; no files, directory names, or paths outside Humanize     │
│  itself; no keys, tokens, or account credentials -- not even   │
│  environment variable names. You can change this later in      │
│  /settings.                                                    │
│                                                                │
│  Yes  No                                                       │
│                                                                │
│  enter yes   esc ask again next time                           │
│                                                                │
╰────────────────────────────────────────────────────────────────╯
```

The answers are the two buttons. **Yes** has the focus as the box opens, so <kbd>enter</kbd>
says yes; <kbd>→</kbd> moves to **No**, and <kbd>enter</kbd> then says no. <kbd>esc</kbd>, or a
click outside the box, answers nothing, and `hmz` asks again next time.

To see or change your answer later, type `/settings` and open its first page, **General**:

```text
  hmz › /settings › General
  How Humanize behaves on this machine, in every directory.

  ╭──────────────────────────────────────────────────────────────────────────╮
  │ Display                                                                  │
  │ Details                                                          ○ off ▾ │
  │   show every tool call and all of the thinking                           │
  │                                                                          │
  │ Agents                                                                   │
  │ /btw The Epic                                                     none ▾ │
  │   the agent that answers side questions asked of The Epic                │
  │                                                                          │
  │ Privacy                                                                  │
  │ Error reports                                                    ○ off ▾ │  ①
  │   send error reports to Humanize                                         │
  │──────────────────────────────────────────────────────────────────────────│
  │ What is sent                                                           ▸ │  ②
  │   what error reports include and exclude                                 │
  ╰──────────────────────────────────────────────────────────────────────────╯

                                                                          Save

  enter choose   esc back
```

1. **Error reports** is your answer. <kbd>enter</kbd> on it drops `on` and `off`; once you
   pick the other one, <kbd>tab</kbd> reaches **Save**. The General card of `/settings` sums
   it up as `reports on` or `reports off`.
2. **What is sent** reads out the same two lists as the question, and changes nothing.

## Before you start

Nothing to install. Reporting is part of Humanize, and it is off on a machine where nobody has
answered the question.

## What is sent, and what never is

<div class="report-lists">
<div class="report-list sent">
<p class="report-head"><span aria-hidden="true">↑</span> Sent, once you say yes</p>
<ul>
<li><strong>The error, and where in Humanize it occurred.</strong> Its type, its message, and
each frame of the stack named by its place inside Humanize or a library, such as
<code>hmz/coganchor/agents/base.py</code>. A frame in your own code keeps its line number and
nothing else.</li>
<li><strong>Which flow was running, and what each agent was configured to run.</strong> The flow's
name, how deep it was called and for how long; for each agent role, the CLI, the model, the
effort, the account <em>by name</em>, what it may do, and its skills by name.</li>
<li><strong>Which coding agents are installed, and account names</strong>, and how each
account was signed in.</li>
<li><strong>Which skills and flowverses are active</strong>, by name.</li>
<li><strong>That a run went five minutes without any sign of progress</strong>, as
<a href="#when-a-report-is-sent">a halt report</a>.</li>
<li><strong>The versions of Humanize and Python, and the operating system and
architecture.</strong></li>
</ul>
</div>
<div class="report-list kept">
<p class="report-head"><span aria-hidden="true">✕</span> Never sent</p>
<ul>
<li><strong>Nothing you typed.</strong> No task, prompt, or command.</li>
<li><strong>No agent output.</strong> Nothing from any transcript or session log.</li>
<li><strong>No files, directory names, or paths outside Humanize itself.</strong></li>
<li><strong>No keys, tokens, or account credentials</strong>, not even the names of the
environment variables an account sets.</li>
</ul>
</div>
</div>

The machine's side, the installed agents, accounts, skills and flowverses, is described by
`hmz` itself. A report from `hmz exec` carries the error and the run without it.

## Example: what one report carries

Say Humanize crashes in the middle of a [Ralph loop](https://humanfia.ai/flows/ralph-loop) you started from
`hmz`, on a machine whose answer is yes. The report is the error, and two short files that
describe the run and the machine. The error, as it arrives:

```text
KeyError: 'usage'                                                        ①
  hmz/coganchor/agents/claude.py, line 1204                              ②
  hmz/runtime/doing/hosting.py, line 958
  <not Humanize>, line 31                                                ③
tags: doing = a flow                                                     ④
```

`machine.yaml`, as `hmz` wrote it on the machine this page was written on, put on fewer
lines:

```yaml
python: 3.12.14
system: Linux
clis: [agy, claude, codex, cursor-agent, dsh, grok, kimi, mcode, mimo, opencode, pi, qwen]  # ⑤
accounts: []                                                                                # ⑥
skills:
  claude: [hf-cli]                                                                          # ⑦
  codex: [hf-cli]
flowverses:
- {name: official, fetched: true}
- {name: local, fetched: true}
- {name: user, fetched: true}
```

`flow.yaml`, in the shape Humanize writes it:

```yaml
flow: ralph_loop:ralph_loop
calls: 1
running:
- {flow: ralph_loop:ralph_loop, deep: 0, under: '', for: 41}                   # ⑧
agents:
- flow: ralph_loop:ralph_loop
  called: agent
  cli: claude
  model: claude-haiku-4-5-20251001
  effort: low
  account: as this machine is signed in                                        # ⑨
  may: local=all user=read system=read online=all                               # ⑩
  skills: []
```

The error and `flow.yaml` are illustrative: nobody crashed Humanize to write this page.

### What each part means

1. **The error's type and message.** In the message, your home directory reads `~`, anything
   shaped like a key reads `…`, and a failed command's own command line reads `A command`,
   since that line could hold your task.
2. **A frame inside Humanize**, named by its path inside the package. This is what makes a
   report fixable.
3. **A frame in your own code**, such as a flow you wrote: its line number, and nothing else.
   Its file, module and function are named by you, so they are not sent.
4. **What Humanize was doing**: `a flow` for a run started from `hmz`, `hmz exec` for one
   started from the command line.
5. **Which CLIs are installed**, by name. Not where, and not which version.
6. **Accounts**: for each, its CLI, its name and how it was signed in. None on this machine.
7. **Skills**, by name, under each CLI that would load them. Never what is in them.
8. **The flow**: its name, how deep it was called, which flow called it, and how many seconds
   it had run.
9. **The account**, by name. `as this machine is signed in` is an agent given no `@account`.
10. **What the role may do**, as its [permission](/user/permissions) scopes.

## Changing your answer

| Where | What happens |
| --- | --- |
| `hmz`, the first time | It asks. <kbd>esc</kbd>, or a click outside the box, leaves the question unanswered, and it asks again next time. |
| `hmz`, after that | It does what you answered. [`/settings`](/user/settings) changes it: **Error reports**, on its General page. A no stops reporting at once. |
| `hmz exec` | It never asks. It reports only if you answered yes. |
| a script using `hmz.sdk` | Nothing is reported unless the script calls `Hmz().reports()`, and then only if you answered yes. |
| any of them, under `HUMANIZE_SENTRY` | `on` or `off` answers for that one process and writes nothing down. While it is set, `/settings` says `HUMANIZE_SENTRY is set, overriding this setting for this run`. |

```sh
HUMANIZE_SENTRY=off hmz          # this run reports nothing, whatever you answered
```

A machine nobody has asked sends nothing. Leaving the question unanswered is not a yes.

## Check your answer

- **At the prompt:** `/settings` shows `reports on` or `reports off` on its General card.
- **On a machine set up by a script, or in CI:** set `HUMANIZE_SENTRY=off` where the runs
  start. Nothing in the settings file can then turn reporting on for them.

## When a report is sent

A report is sent for two things only, so that every one of them is a problem somebody has to
fix:

| Report | When | Carries |
| --- | --- | --- |
| crash | a run, or `hmz exec`, ends on an error inside Humanize, or an error nothing in Humanize catches | the error, and the description of the run above |
| halt | a run you are watching goes five minutes without a word from any of its agents; time spent waiting for your answer does not count | how many seconds it stood still, and the description of the run above |

Each kind of crash, raised at the same place, is sent once per process, and a run is reported
as halted at most once. Nothing else is sent: no timings, no profiles, no log lines, and nothing
about a key you pressed or a menu you closed.

## How the promise is kept

Reports go to Humanize's own [Sentry](https://sentry.io) project. The reporter is set up so
that the list above stays true:

- `send_default_pii` is off: no IP address, no user, no machine name.
- `include_local_variables` is off, and each frame's variables are dropped again before
  sending. That is where the task, the prompt and the answer would be.
- The lines of source around each frame are dropped.
- `enable_logs` is off, and breadcrumbs are dropped: no log line leaves the machine.
- `server_name` is empty: no hostname.
- `ArgvIntegration` is off, and everything under `extra` is dropped: no command line, which for
  `hmz exec` holds the task.
- The list of installed packages, `user` and `request` are dropped.
- In the error's message and every other string sent, your home directory becomes `~`, the
  command line of a failed command becomes `A command`, and anything over 500 characters is
  cut. Every credential an [exported run](/user/export) has struck out becomes `…`: a password
  in a URL, a token in its query, a key in the shape a vendor mints it (`sk-`, `ghp_`, `ghs_`,
  `glpat-`, `hf_`, `AIza`), a JWT, a `Bearer` token, and a value named as a token, secret, key
  or password. Reports and exports use one list.
- Nothing is timed or profiled, and `LoggingIntegration` is off: no log line becomes a report.
- Only a process that started reporting reports: `hmz`, `hmz exec`, a run the daemon holds,
  and a script that called `Hmz().reports()`. A script that crashes without calling it sends
  nothing, whatever you answered.

## Sending a run on purpose

A report never carries your run. When you want somebody to see what happened, [export the
run](/user/export) from `/epics` and attach the archive to an issue. That archive is the
opposite of a report: it holds your task and every transcript, because you chose to send it.
Credentials are still struck out of it.

## Next steps

- [Exporting a run](/user/export): sending a whole run, on purpose
- [Settings](/user/settings): everything else `/settings` keeps
- [Security](/user/security): what agents may touch on this machine
- [CLI reference](/reference/cli): `HUMANIZE_SENTRY` among Humanize's environment variables

<style scoped>
.report-lists {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 20px 0;
}

.report-list {
  padding: 14px 18px 4px;
  border: 1px solid var(--hmz-panel-border);
  border-top: 3px solid var(--report-tone);
  border-radius: 12px;
  background: var(--hmz-panel-bg);
}

.report-list.sent {
  --report-tone: var(--vp-c-brand-1);
}

.report-list.kept {
  --report-tone: var(--vp-c-danger-1);
}

.report-head {
  margin: 0 0 6px;
  font-weight: 600;
  color: var(--report-tone);
}

.report-head span {
  display: inline-block;
  width: 1.2em;
}

.report-list ul {
  padding-left: 1.1em;
  font-size: 14px;
  line-height: 1.6;
}

.report-list li + li {
  margin-top: 8px;
}

@media (max-width: 640px) {
  .report-lists {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
