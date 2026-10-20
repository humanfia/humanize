# Telemetry

## 1. Scope

This specification defines the error reports **hmz** sends about itself: whether any report is
sent, when the **user** is asked, which events are reported, what a report holds, what a report
never holds, where reports go, and how reporting is turned on and off.

Out of scope:

- Exporting or backing up an epic, which the user does on purpose and which carries the epic's
  content (`features/backups.md`).
- Fetching the newest release and the price list, which send no data about the user
  (`features/updates.md`, `features/monitoring.md` §3.3).
- The settings key holding the answer (`api/settings.md`).

## 2. Definitions

**2.1** **Report**: one message hmz sends to the reporting destination (§2.4).

**2.2** **Crash report**: a report of an error raised inside hmz.

**2.3** **Halt report**: a report that an epic executing in the reporting process went the
halt time (§2.9) without any event from any of its agents.

**2.4** **Reporting destination**: the Sentry project of the hmz maintainers, reached at
`o4511914126344192.ingest.us.sentry.io`.

**2.5** **Answer**: the user's reply to the question whether hmz reports errors: **yes**, **no**,
or **unanswered**.

**2.6** **Override**: the environment variable `HUMANIZE_SENTRY`.

**2.7** **Sent list**: the six statements of §4.1, in the wording given there.

**2.8** **Never-sent list**: the four statements of §4.2, in the wording given there.

**2.9** **Halt time**: 300 seconds.

## 3. Consent

### 3.1 The answer

**3.1.1** hmz MUST keep the answer as a setting of the **home**, shared by every workspace, and
MUST read an absent setting as unanswered.

**3.1.2** hmz MUST NOT send any report while the effective answer is no or unanswered.

**3.1.3** Where the override is `on`, `1`, `true` or `yes`, ignoring case and surrounding space, the
effective answer MUST be yes for that process alone; where it is `off`, `0`, `false` or `no`, it
MUST be no for that process alone; the override MUST NOT write any setting.

**3.1.4** Where the override is absent or holds another value, the effective answer MUST be the
answer kept in settings.

### 3.2 Asking

**3.2.1** The terminal interface MUST ask the question when it starts and the kept answer is
unanswered and no override applies, and MUST show the sent list and the never-sent list in the
question.

**3.2.2** Dismissing the question without choosing MUST leave the answer unanswered, so that the
question is asked again at the next start.

**3.2.3** Choosing yes or no MUST be kept as the answer and MUST start or stop reporting in that
process at once.

**3.2.4** `hmz exec`, the **daemon**, `hmz web` and SDK programs MUST NOT ask the question.

**3.2.5** The terminal interface and the web interface MUST each let the user change the answer in
their settings, and the terminal interface MUST show there the sent list and the never-sent list.

**3.2.6** Changing the answer to no in the terminal interface MUST stop reporting in that process
at once.

> Informative: reports already handed to the network can still arrive.

### 3.3 Where reporting runs

**3.3.1** The terminal interface, `hmz exec` and the daemon MUST start reporting when they
start, where the effective answer is yes.

**3.3.2** Any other hmz process, an SDK program included, MUST start reporting no earlier than
the first report it makes or the moment the program asks for reporting (`api/sdk.md`), and only
where the effective answer is yes.

**3.3.3** A reporter that cannot start, information that cannot be gathered, and a report that
cannot be sent MUST each leave hmz and every epic behaving as they would without reporting.

### 3.4 What is reported

**3.4.1** hmz MUST send a crash report for an error that ends an epic or `hmz exec`, and for an
error that nothing in hmz catches.

**3.4.2** hmz MUST NOT send a crash report for an error of the same type raised at the same line
of the same file as one already reported by that process.

**3.4.3** Where something in the reporting process is told the events of an epic's agents
(`api/sdk.md` §5.3), hmz MUST send a halt report once that epic has gone the halt time with no such
event, not counting time spent waiting on the **outworlder**, and MUST send at most one halt
report per epic.

**3.4.4** hmz MUST NOT send any report other than a crash report or a halt report: no report of a
logged message, no timing data, and no profiles.

## 4. Content

### 4.1 What is sent

**4.1.1** A report MUST hold nothing beyond what the following list states, which hmz MUST show
in these words: "the error and where in humanize it occurred"; "which flow was running, and what
each agent was configured to run"; "which coding agents are installed, and account names";
"which skills and flowverses are active, by name"; "that a run went five minutes without any
sign of progress"; "the version of humanize, of Python, and the operating system and architecture".

**4.1.2** A crash report MUST hold the error's type, its message after §4.3, and its stack, each
frame named as §4.4 defines.

**4.1.3** A crash report MUST hold what hmz was doing, `a flow` or `hmz exec`.

**4.1.4** A report MUST hold, where an **epic** is executing in the reporting process, the flows
executing with their depth, caller and seconds executed, and, for each **agent** role, the flow,
role, CLI, model, effort, account name, permission scopes and skill names.

**4.1.5** A report from the terminal interface MUST hold the Python version, the operating
system, the installed CLIs by name, each account by CLI, name and sign-in method, the skill names
each CLI would load, and each flowverse by name with whether it has been fetched.

**4.1.6** A halt report MUST hold how many seconds the epic went without an event, and what
hmz was doing, `a flow`.

**4.1.7** A report MUST hold the release of hmz that sent it.

### 4.2 What is never sent

**4.2.1** hmz MUST show the following list in these words, and MUST NOT send anything it names:
"nothing you typed: no task, prompt, or command"; "no agent output, and nothing from any
transcript or session log"; "no files, directory names, or paths outside humanize itself"; "no
keys, tokens, or account credentials -- not even environment variable names".

**4.2.2** A report MUST NOT hold the command line of the reporting process.

**4.2.3** A report MUST NOT hold the values of any variable of any stack frame, nor source lines
around a frame.

**4.2.4** A report MUST NOT hold the host name, the user's identity, the network address, logs,
breadcrumbs, the list of installed modules, or the working directory.

**4.2.5** A report MUST NOT hold the content of any account, nor the names of the environment
variables an account sets.

### 4.3 Scrubbing

**4.3.1** In every string a report holds, hmz MUST replace a home-directory path prefix under
`/home/`, `/homes/` or `/Users/` by `~`.

**4.3.2** In every string a report holds, hmz MUST replace a user or password written into a URL
by `…`.

**4.3.3** In every string a report holds, hmz MUST replace by `…` every word that starts with
`sk`, `pk`, `ghp`, `gho`, `github_pat`, `xai`, `sk-ant` or `sk-proj`, followed by `-` or `_` and
at least eight further letters, digits, `_` or `-`.

**4.3.4** In every string a report holds, hmz MUST replace the command line a failed command
states of itself by `A command `.

**4.3.5** hmz MUST cut every string a report holds to 500 characters, followed by `…` where cut.

### 4.4 Stack frames

**4.4.1** A frame in hmz's own package or in a library installed beside it MUST be named by its
path relative to that installation root, with its line number.

**4.4.2** A frame in any other file MUST be named `<not humanize>` with its line number, and MUST
NOT state its file, module or function.

## 5. Destination

### 5.1 Destination

**5.1.1** hmz MUST send reports to the reporting destination alone, and MUST NOT let any setting
change the destination.

**5.1.2** hmz MUST NOT send any report, or any part of one, to any other destination.
