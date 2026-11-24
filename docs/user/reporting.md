---
title: Report a problem
description: Decide whether Humanize sends error reports, know exactly what one holds, and file an issue with a run and its logs attached.
---

# Report a problem

Humanize can send an error report to its developers when it fails. It sends nothing until you agree. For any other problem, file an issue on GitHub and attach the run.

![An error report carries the error, the flow and agent settings, names and versions; what you typed, agent output, files and keys stay on your machine](/diagrams/user-reporting-1.svg)

## What an error report holds

Humanize sends a report in two cases:

| Report | When |
| --- | --- |
| Crash | A run ends on an error that is not the flow's own failure, or Humanize hits an uncaught error. |
| Halt | An epic goes five minutes with no event from any agent. Time spent waiting for your answer does not count. |

| Sent | Never sent |
| --- | --- |
| The error and where in Humanize it occurred | Anything you typed: no task, prompt, or command |
| Which flow was running, and what each agent was configured to run | Agent output, or anything from a transcript or session log |
| Which coding agents are installed, and account names | Files, directory names, or paths outside Humanize itself |
| Which skills and flowverses are active, by name | Keys, tokens, or account credentials, not even environment variable names |
| The version of Humanize, of Python, and the operating system and architecture | The host name, your user name, the command line |

Before sending a report, Humanize replaces your home directory with `~`, replaces anything shaped like a key with `…`, and truncates every string to 500 characters. Stack frames in your own code appear as `<not Humanize>` with only the line number. Reports never include logs, timings, or profiles.

Reports go to the Humanize Sentry project.

## Turn error reports on or off

One machine-wide setting controls reporting: `enable_sentry` in `settings.toml`. It has three states: on, off, and not answered. When not answered, Humanize sends nothing.

### In the app

Open **Settings**, then **General** under **Daemon**. Set **Error reports** to **On** or **Off** and click **Save**. The app never prompts you, and the setting reads **Not set** until you choose. Once saved, it can only be switched between **On** and **Off**. The setting is saved on the machine of the daemon picked at the top of the page; **Batch apply** copies it to [your other daemons](/user/daemons).

![The General page of Settings in Humanize Desktop, with Error reports reading Not set](/shots/user-reporting-app.svg)

![Error reports is set to On, then Save is clicked and the button reads Saved](/shots/user-reporting-app-on.svg)

### In the terminal

`hmz` prompts you the first time you open it. Press <kbd>enter</kbd> to answer **Yes**, or press <kbd>→</kbd> then <kbd>enter</kbd> to answer **No**. Press <kbd>esc</kbd> to skip; `hmz` will ask again next time.

![The question hmz asks at first start: Send error reports to Humanize?, with what is sent and never sent, and Yes and No](/shots/user-reporting-question.svg)

To change your choice later, run `/settings general`. Select **Error reports**, press <kbd>enter</kbd>, pick `On` or `Off`, and select **Save**. The change applies immediately. An unanswered setting reads `Not set`.

![The General page of /settings in the terminal, with the cursor on Error reports, set to Off](/shots/user-reporting-terminal.svg)

Select **What is sent** below it to view what a report includes without changing the setting.

![The row What is sent, opened: the list of what is sent and what never is](/shots/user-reporting-terminal-sent.svg)

### From the command line

`hmz exec` never prompts you. It sends reports only if reporting is already turned on.

Set `HUMANIZE_SENTRY` to `on` or `off` to override the setting for a single process without saving:

```sh
HUMANIZE_SENTRY=off hmz
```

Set `HUMANIZE_SENTRY=off` in CI and scripted installs. With the variable set, `hmz` does not ask at first start. While this variable overrides the saved answer, `/settings general` displays `HUMANIZE_SENTRY is set, overriding this setting for this run`.

### From Python

A script using `hmz.sdk` sends reports only if you call `Hmz().reports()` and reporting is enabled. The call returns whether reporting is active.

```python
from hmz.sdk import Hmz

Hmz().reports()
```

## File an issue

Error reports never include your run. To have someone inspect a failure, check [Troubleshooting](/user/troubleshooting) for a known fix, then open an issue at [github.com/humanfia/humanize/issues](https://github.com/humanfia/humanize/issues) and attach:

1. The version from `hmz --version`. If it prints `0.0.0`, the install is from git: name the commit.

   ![hmz --version prints the version](/shots/user-reporting-version.svg)

2. The steps you took, whether a command or actions in the app or `hmz`. The form also asks for your operating system, the coding agents involved, and the flow.
3. The run. Open the ended epic and click **Export** in its header, or type `/epics` in `hmz`, open the epic, and choose `Export`. This creates a `.hmzepic` file containing the task, records, and session logs, with credentials replaced by `[redacted]`. See [Export and import a run](/user/export).

   ![The header of a finished epic, with the pointer on its Export button](/shots/user-reporting-export.svg)

4. The logs, if the run did not start or the daemon failed. The `.hmzepic` archive does not include them. Attach `host.log` from the epic's directory for the run process output, and `daemon.log` for the daemon's output. See [Files on disk](/reference/files) for their locations.

::: warning
Do not report a vulnerability in a public issue. Report it privately at [github.com/humanfia/humanize/security/advisories/new](https://github.com/humanfia/humanize/security/advisories/new).
:::

## Good to know

- An exported run contains your task and every transcript. Review it before attaching it to a public issue.
- Logs are not scrubbed. Remove keys, tokens, and private data before sharing them.
- Each unique crash location is reported once per process. A halted epic is reported at most once.
- Processes read the reporting setting at startup. If you change it in the app, running processes keep the old setting until they restart.
- Only the `hmz` terminal interface adds the machine's installed coding agents, accounts, skills, and flowverses to a report. Other processes describe only the running flow and its agents.
- Only processes that initialize reporting send reports: `hmz`, `hmz exec`, runs managed by the daemon, and scripts that call `Hmz().reports()`.
- See [settings.toml](/reference/settings) and [Environment variables](/reference/environment) for configuration details, and [Security](/user/security) for what agents can access.
