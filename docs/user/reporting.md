# Reporting

humanize can send its developers a report when it crashes, and a count when something it did
was undone or refused. It asks you once, the first time you open `hmz`, and sends nothing until
you say yes.

```text{9}
   Report what goes wrong to humanize?

   A crash nobody sees is a bug nobody fixes. Sent: the error
   and where in humanize it happened; which flow was running,
   and what each of its agents was set up to run; … Never:
   nothing you typed: no task, no prompt, no line at the
   prompt; … /settings changes it later.

 ❯ 1. yes
   2. no

   enter choose · esc ask again next time
```

## What is sent, and what never is

<div class="report-lists">
<div class="report-list sent">
<p class="report-head"><span aria-hidden="true">↑</span> Sent, once you say yes</p>
<ul>
<li><strong>The error, and where in humanize it happened.</strong> Its type, its message, and
each frame of the stack named by its place inside humanize or a library, such as
<code>hmz/coganchor/agents/base.py</code>. A frame in your own code keeps its line number and
nothing else.</li>
<li><strong>Which flow was running, and what each agent was set up to run.</strong> The flow's
name, how deep it was called and for how long; for each agent role, the CLI, the model, the
effort, the account <em>by name</em>, what it may do, and its skills by name.</li>
<li><strong>Which coding agents are installed, and which accounts exist</strong>, by name, and
how each account was signed in.</li>
<li><strong>Which skills and flowverses are in play</strong>, by name.</li>
<li><strong>What humanize did that you then undid, refused or walked away from</strong>, as
<a href="#the-friction-it-counts">named events with counts</a>.</li>
<li><strong>The versions of humanize and Python, and the kind of machine.</strong></li>
</ul>
</div>
<div class="report-list kept">
<p class="report-head"><span aria-hidden="true">✕</span> Never sent</p>
<ul>
<li><strong>Nothing you typed.</strong> No task, no prompt, no line at the prompt.</li>
<li><strong>Nothing an agent said.</strong> Nothing out of any transcript or session log.</li>
<li><strong>No file, no path outside humanize itself, and no directory name.</strong></li>
<li><strong>No key, no token and no account credential</strong>, not even the names of the
variables an account sets.</li>
</ul>
</div>
</div>

The machine's side, the installed agents, accounts, skills and flowverses, is described by
`hmz` itself. A report from `hmz exec` carries the error and the run without it.

## Changing your answer

| Where | What happens |
| --- | --- |
| `hmz`, the first time | It asks. <kbd>esc</kbd> leaves the question unanswered, and it asks again next time. |
| `hmz`, after that | It does what you answered. [`/settings`](/user/settings) changes it: **report what goes wrong to humanize**, on the first page. |
| `hmz exec` | It never asks. It reports only if you answered yes. |
| a script using `hmz.sdk` | Nothing is reported unless the script calls `Hmz().reports()`, and then only if you answered yes. |
| any of them, under `HUMANIZE_SENTRY` | `on` or `off` answers for that one process and writes nothing down. `/settings` says so while it is set. |

```sh
HUMANIZE_SENTRY=off hmz          # this run reports nothing, whatever you answered
```

A machine nobody has asked sends nothing. Leaving the question unanswered is not a yes.

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
| `key-does-nothing` | a key pressed in `/providers` on this machine's own account, where it does nothing | which menu, and what was asked |
| `line-refused` | a typed line the agent refused | how long its refusal was |
| `lines-never-sent` | typed lines still waiting when the flow ended | how many |
| `skill-name-taken` | a skill a flow brought, where the CLI already loads another of that name | nothing more |
| `native-credential-stays-here` | an account whose files could not all go with a turn to another machine | nothing more |
| `watcher-raised` | something watching an agent failed on one of its events | the CLI, the kind of event, the type of error |

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
