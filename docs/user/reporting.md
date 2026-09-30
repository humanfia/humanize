# Reporting

humanize can send its developers a report when it crashes, and a count when something it did
was undone or refused. This page says exactly what such a report holds, what it never holds,
and how to turn it on or off. Read it before you answer the question `hmz` asks the first time
it opens, or when you need to tell somebody what leaves your machine.

## Try it

The first time you open `hmz`, it asks. Nothing is sent until you say yes:

```text
╭────────────────────────────────────────────────────────────────╮
│                                                                │
│  Report errors to humanize?                                    │
│  Send error reports to help fix bugs. Sent: the error and      │
│  where in humanize it occurred; which flow was running, and    │
│  what each agent was configured to run; which coding agents    │
│  are installed, and account names; which skills and            │
│  flowverses are active, by name; what humanize did that you    │
│  undid, refused, or canceled; the version of humanize, of      │
│  Python, and the operating system and architecture. Never      │
│  sent: nothing you typed: no task, prompt, or command; no      │
│  agent output, and nothing from any transcript or session      │
│  log; no files, directory names, or paths outside humanize     │
│  itself; no keys, tokens, or account credentials -- not even   │
│  environment variable names. You can change this later in      │
│  /settings.                                                    │
│                                                                │
│     ❯ 1. yes                                                   │
│       2. no                                                    │
│                                                                │
│  enter choose · esc ask again next time                        │
│                                                                │
╰────────────────────────────────────────────────────────────────╯
```

To see or change your answer later, type `/settings` and open its first page, **Settings**:

```text
  /settings › Settings
  Global settings for humanize on this machine.

  │ Error reports                                                              ○ off ▾ │  ①
  │   send error reports to humanize                                                   │
  │────────────────────────────────────────────────────────────────────────────────────│
  │ What is sent                                                                     ▸ │  ②
  │   what error reports include and exclude                                           │
  │────────────────────────────────────────────────────────────────────────────────────│
  │ Details                                                                    ○ off ▾ │
  │   show every tool call and all of the thinking                                     │
```

1. **Error reports** is your answer. <kbd>enter</kbd> drops `on` and `off`; <kbd>tab</kbd>
   reaches **Save**. The first page of `/settings` sums it up as `reports on` or
   `reports off`.
2. **What is sent** reads out the same two lists as the question, and changes nothing.

## Before you start

Nothing to install. Reporting is part of humanize, and it is off on a machine where nobody has
answered the question.

## What is sent, and what never is

<div class="report-lists">
<div class="report-list sent">
<p class="report-head"><span aria-hidden="true">↑</span> Sent, once you say yes</p>
<ul>
<li><strong>The error, and where in humanize it occurred.</strong> Its type, its message, and
each frame of the stack named by its place inside humanize or a library, such as
<code>hmz/coganchor/agents/base.py</code>. A frame in your own code keeps its line number and
nothing else.</li>
<li><strong>Which flow was running, and what each agent was configured to run.</strong> The flow's
name, how deep it was called and for how long; for each agent role, the CLI, the model, the
effort, the account <em>by name</em>, what it may do, and its skills by name.</li>
<li><strong>Which coding agents are installed, and account names</strong>, and how each
account was signed in.</li>
<li><strong>Which skills and flowverses are active</strong>, by name.</li>
<li><strong>What humanize did that you undid, refused, or canceled</strong>, as
<a href="#the-friction-it-counts">named events with counts</a>.</li>
<li><strong>The versions of humanize and Python, and the operating system and
architecture.</strong></li>
</ul>
</div>
<div class="report-list kept">
<p class="report-head"><span aria-hidden="true">✕</span> Never sent</p>
<ul>
<li><strong>Nothing you typed.</strong> No task, prompt, or command.</li>
<li><strong>No agent output.</strong> Nothing from any transcript or session log.</li>
<li><strong>No files, directory names, or paths outside humanize itself.</strong></li>
<li><strong>No keys, tokens, or account credentials</strong>, not even the names of the
environment variables an account sets.</li>
</ul>
</div>
</div>

The machine's side, the installed agents, accounts, skills and flowverses, is described by
`hmz` itself. A report from `hmz exec` carries the error and the run without it.

## Example: what one report carries

Say humanize crashes in the middle of a [Ralph loop](/flows/ralph-loop) you started from
`hmz`, on a machine whose answer is yes. The report is the error, and two short files that
describe the run and the machine. The error, as it arrives:

```text
KeyError: 'usage'                                                        ①
  hmz/coganchor/agents/claude.py, line 1204                              ②
  hmz/runtime/doing/hosting.py, line 958
  <not humanize>, line 31                                                ③
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

`flow.yaml`, in the shape humanize writes it:

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

The error and `flow.yaml` are illustrative: nobody crashed humanize to write this page.

### What each part means

1. **The error's type and message.** In the message, your home directory reads `~`, anything
   shaped like a key reads `…`, and a failed command's own command line reads `A command`,
   since that line could hold your task.
2. **A frame inside humanize**, named by its path inside the package. This is what makes a
   report fixable.
3. **A frame in your own code**, such as a flow you wrote: its line number, and nothing else.
   Its file, module and function are named by you, so they are not sent.
4. **What humanize was doing**: `a flow` for a run started from `hmz`, `hmz exec` for one
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
| `hmz`, the first time | It asks. <kbd>esc</kbd> leaves the question unanswered, and it asks again next time. |
| `hmz`, after that | It does what you answered. [`/settings`](/user/settings) changes it: **Error reports**, on its Settings page. A no stops reporting at once. |
| `hmz exec` | It never asks. It reports only if you answered yes. |
| a script using `hmz.sdk` | Nothing is reported unless the script calls `Hmz().reports()`, and then only if you answered yes. |
| any of them, under `HUMANIZE_SENTRY` | `on` or `off` answers for that one process and writes nothing down. While it is set, `/settings` says `HUMANIZE_SENTRY is set, overriding this setting for this run`. |

```sh
HUMANIZE_SENTRY=off hmz          # this run reports nothing, whatever you answered
```

A machine nobody has asked sends nothing. Leaving the question unanswered is not a yes.

## Check your answer

- **At the prompt:** `/settings` shows `reports on` or `reports off` against its Settings
  page.
- **On a machine set up by a script, or in CI:** set `HUMANIZE_SENTRY=off` where the runs
  start. Nothing in the settings file can then turn reporting on for them.

## The friction it counts

Some things worth knowing are not errors: each of these is somebody finding that humanize does
not work the way they expected. Each is sent as its name and the few counts or names in the
last column, with the same description of the run as a crash. None records a word of what was
typed.

| Name | When | Carries |
| --- | --- | --- |
| `unknown-command` | a `/` line that is not a command | how long the name was |
| `unknown-flow` | a `$` line that names no flow | how long the name was |
| `nothing-started` | a task typed with no coding agent to run it | why |
| `changes-dropped` | a menu answered, then its changes thrown away | which menu |
| `save-refused` | a menu that would not save, a role or a budget still unset | how many roles were unset |
| `key-does-nothing` | a key pressed on the Accounts page of `/settings` on this machine's own account, where it does nothing | which menu, and what was asked |
| `line-refused` | a typed line the agent refused | how long its refusal was |
| `lines-never-sent` | typed lines still waiting when the flow ended | how many |
| `skill-name-taken` | a skill a flow brought, where the CLI already loads another of that name | nothing more |
| `native-credential-stays-here` | an account whose files could not all go with a turn to another machine | nothing more |
| `watcher-raised` | something watching an agent failed on one of its events | the CLI, the kind of event, the type of error |

Typing `/sttings` by mistake, say, sends `unknown-command` and the number 7, and nothing else
of what you typed.

## How the promise is kept

Reports go to humanize's own [Sentry](https://sentry.io) project. The reporter is set up so
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
- In the error's message and every other string sent, your home directory becomes `~`, a
  password in a URL and anything shaped like a key become `…`, the command line of a failed
  command becomes `A command`, and anything over 500 characters is cut.

## Sending a run on purpose

A report never carries your run. When you want somebody to see what happened, [export the
run](/user/export) from `/epics` and attach the archive to an issue. That archive is the
opposite of a report: it holds your task and every transcript, because you chose to send it.
Credentials are still struck out of it.

## Next steps

- [Exporting a run](/user/export): sending a whole run, on purpose
- [Settings](/user/settings): everything else `/settings` keeps
- [Security](/user/security): what agents may touch on this machine
- [CLI reference](/reference/cli): `HUMANIZE_SENTRY` among humanize's environment variables

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
