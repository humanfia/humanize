# Monitoring

## 1. Scope

This specification defines what **hmz** works out about an **epic** while it executes and after
it ends: the live figures every **frontend** draws (who is working, handovers, turns, tokens,
money, rate), the price list money is computed from, the notices hmz raises about the epics of
**this machine**, the Chrome traces and profiles hmz gathers of an epic, and the Exomyth timeline
of an epic.

Out of scope:

- How a frontend draws these figures, its keys and screens (`features/tui.md`,
  `features/web.md`, `features/desktop.md`).
- Side questions asked about an executing epic (`features/btw.md`).
- The wire format in which a frontend receives records and notices (`api/daemon.md`,
  `api/http.md`).
- Where traces and profiles are stored inside an epic (`api/files/epics.md`) and where the price
  list is stored (`api/files/machine.md`).
- Budgets and how a budget stops an epic (`features/epics.md` §3.4).

## 2. Definitions

**2.1** **Monitor**: the live model of one epic defined in §3.1.

**2.2** **Turn**: one prompt given to a **session** and the work its **agent** does until it
answers.

**2.3** **Handover**: the event in which an agent begins a turn after a different agent was the
last to finish one in the same epic.

**2.4** **Sub-agent**: an agent that a session's own CLI starts during a turn, without the
**flow** asking for it.

**2.5** **Token kind**: one of `input`, `output`, `cache_read`, `cache_write` and `reasoning`.

**2.6** **Floor**: a figure that is known to be lower than the true figure because some agent of
the epic does not report what the figure counts.

**2.7** **Rate**: the output tokens written in an epic per second over the last five minutes of
wall-clock time.

**2.8** **Price list**: the per-token model prices hmz keeps on this machine.

**2.9** **Notice**: one record, defined in §4.2, that something happened to an epic of this
machine that a **user** would want to be told.

**2.10** **Chrome trace**: a JSON document in the Chrome Trace Event format, readable by Perfetto
and `chrome://tracing`, describing the sessions of an epic on one timeline.

**2.11** **Environment profile**: the record, made while an epic executes, of every program its
agents started and of the threads of each.

**2.12** **Flow profile**: the record, made by sampling while an epic executes, of the call
stacks of the flow's own Python code.

**2.13** **Exomyth timeline**: the document, defined in §6, that lays one epic out as processes,
tracks and spans for a frontend to draw.

## 3. Live figures

### 3.1 Monitor

**3.1.1** hmz MUST work out the monitor of an epic once, and every frontend MUST draw the figures
of one epic as hmz worked them out, without computing any of them a second time.

**3.1.2** hmz MUST work out the monitor only from the records the **host slot** of the epic sends
to frontends and from the logs the agents' CLIs keep, and MUST NOT ask anything else.

**3.1.3** The monitor MUST count each turn against the agent and the session that took it.

**3.1.4** The monitor MUST report, for each agent, whether it is working, how many turns it has
taken, how many sessions it has opened, the tokens it has spent, and how long it has been at
what it is doing now.

**3.1.5** The monitor MUST report each sub-agent under the agent whose turn started it, with what
it was started about and whether it is still working.

**3.1.6** The monitor MUST count each handover from the agent that last finished a turn to the
agent that next began one, separately for each direction, and MUST identify the most recent
handover.

**3.1.7** The monitor MUST report, for the epic, how many agents are working, the turns taken,
the time since the epic began and, once the epic ends, the time at which it ended.

**3.1.8** The monitor MUST name each agent by its own name, with the **role** it fills shown
after it.

### 3.2 Cost tally

**3.2.1** hmz MUST read what a session spends from the log its CLI keeps, as the turn proceeds,
and MUST read it once more when the epic ends.

**3.2.2** For a session whose CLI ran on another **machine**, hmz MUST read the copy of its log
kept in the epic.

**3.2.3** hmz MUST report, per model, the tokens spent, the rate, and the money spent where the
price list prices that model.

**3.2.4** hmz MUST report the money of a model the price list does not price as absent, and MUST
NOT report it as zero.

**3.2.5** hmz MUST report, over the whole epic, the tokens spent of each token kind.

**3.2.6** hmz MUST mark a per-kind total as a floor where an agent of the epic runs a CLI that
does not report that kind, and MUST mark every per-kind total as a floor where a CLI reports
tokens without their kind.

**3.2.7** hmz MUST mark the epic's money as a floor where at least one model of the epic is
priced and at least one is not, and MUST report no money where no model of the epic is priced.

**3.2.8** hmz MUST divide a turn that names two or more models between those models in
proportion to what each took, and MUST NOT drop that turn.

**3.2.9** An epic that is stopped and still unwinding while a newer epic executes in the same
host slot MUST continue to be counted until it ends, against its own agents only.

**3.2.10** hmz MUST work the figures out again at least every five seconds and whenever an agent
reports anything.

**3.2.11** hmz MUST report the figures of a turn when that turn ends, in the epic's records, so
that `hmz exec` prints and `hmz exec --json` emits them per turn (`api/cli.md`).

### 3.3 Price list

**3.3.1** hmz MUST compute money from the price list, at list price, in US dollars.

**3.3.2** hmz MUST fetch the price list from OpenLLMPrices unless the environment variable
`HUMANIZE_PRICES` names another URL or file, and MUST fetch nothing where `HUMANIZE_PRICES` is
`off`, `0`, `no`, `none` or empty.

**3.3.3** hmz MUST treat the price list as stale once it is older than 24 hours.

**3.3.4** A frontend MUST refresh a stale price list in the background, and MUST NOT delay any
input or drawing while it does.

**3.3.5** hmz MUST keep the price list for this machine alone (`api/files/machine.md`).

**3.3.6** hmz MUST price a model by matching its name against the price list once both names are
stripped of a leading account or provider and a trailing release date.

### 3.4 Formats

**3.4.1** Every frontend MUST state a duration of the monitor or the cost tally as whole seconds
below one minute (`42s`), as minutes and two-digit seconds below one hour (`3m07s`), and as hours
and two-digit minutes from one hour (`2h05m`), truncating rather than rounding.

**3.4.2** Every frontend MUST state a token count of the monitor or the cost tally below 1,000 as a
whole number, below 1,000,000 in thousands with one decimal and the suffix `k`, and otherwise in
millions with two decimals and the suffix `M`.

**3.4.3** Every frontend MUST mark a floor of the cost tally by a `+` immediately after the figure.

## 4. Notices

### 4.1 Following

**4.1.1** A frontend attached to a host slot MUST follow every epic of that slot from the records
the slot sends, and MUST derive the monitor and the cost tally of those epics as §3 defines.

**4.1.2** A frontend that attaches to a host slot MUST receive the records of the executing or
last epic of that slot from the beginning, unless it asks for none, before records as they
happen.

### 4.2 Notices

**4.2.1** The web interface and the terminal interface MUST each work out the notices of the
epics of this machine by the rules of this section, from the status each host slot reports, and
MUST NOT attach to a host slot to do so.

**4.2.2** hmz MUST raise a notice of kind `done` when an epic ends `done`.

**4.2.3** hmz MUST raise a notice of kind `stopped` when an epic ends `stopped` by stopping or
forcing.

**4.2.4** hmz MUST raise a notice of kind `failed` when an epic fails, fails inside hmz, is
ended by its budget, or is refused
by hmz after a frontend asked to start it.

**4.2.5** hmz MUST raise a notice of kind `asked` when a flow asks a person a question.

**4.2.6** hmz MUST raise a notice of kind `listening` when a flow other than `chat` waits for the
next thing a person says.

**4.2.7** For a `chat` epic, hmz MUST raise a notice of kind `done` when a turn of its agent is
done, MUST raise a notice of its end only where it failed or ended during a turn not yet
noticed, and MUST NOT raise a notice of kind `stopped`.

**4.2.8** hmz MUST NOT raise a notice for anything that stood before hmz began working notices
out, and MUST NOT raise a second notice for a question already noticed.

**4.2.9** Every notice MUST carry an identifier, its kind, the workspace, the host slot, the epic
name, the flow, the task, the role where it concerns a question, a one-line text, and the moment
it was raised.

**4.2.10** hmz MUST number notices in the order they are raised, each identifier greater than
every identifier this machine raised before, including before hmz was last restarted.

**4.2.11** hmz MUST keep at least the 200 most recent notices, and MUST serve every kept notice
after a given identifier, and each new notice as it is raised, resuming after the last
identifier a frontend heard (`api/http.md`).

### 4.3 Notification preferences

**4.3.1** hmz MUST keep, as one setting of the **home** shared by every frontend, whether each
notice kind is told to the user and whether the operating system is also told
(`api/settings.md`).

**4.3.2** Every notice kind, and telling the operating system, MUST be on unless the user turned
it off.

**4.3.3** A frontend MUST NOT tell the user of a notice whose kind is turned off.

> Informative: how each frontend shows a notice is defined in `features/tui.md` and
> `features/web.md`.

## 5. Traces and profiles

### 5.1 Chrome traces

**5.1.1** hmz MUST gather a Chrome trace of an epic from the epic's own records and from the logs
its sessions' CLIs wrote, selecting sessions by the identifiers the epic recorded and not by the
directory the epic executed in.

**5.1.2** A Chrome trace MUST place every session, every action of each session, and every
sub-agent on one timeline, grouped by agent.

**5.1.3** Where the epic has an environment profile, the Chrome trace MUST show each program as a
process on the same timeline and scale as the sessions; where the epic has a flow profile, the
Chrome trace MUST show it as one further process named `python`.

**5.1.4** A Chrome trace MUST record a summary of the agents, backends, sessions, slices, tracks
and time span it covers, and the number of programs where it shows any.

**5.1.5** Unless a path is given, hmz MUST write a Chrome trace of an epic inside that epic,
named after the UTC moment it was gathered, so that gathering twice keeps both
(`api/files/epics.md`).

**5.1.6** hmz MAY gather a Chrome trace of sessions named by identifier, whole or as a prefix,
without an epic (`api/sdk.md`); naming no session MUST NOT be read as naming every session.

**5.1.7** hmz MUST accept a start and an end bounding a trace in any natural-language wording of
a time, MUST default them to the earliest and latest record, and MUST cut every session, program
and profile to that window.

**5.1.8** hmz MUST refuse, with an error, a trace bound it cannot read and an empty session
identifier.

**5.1.9** hmz MUST NOT fail a whole trace because the logs of one CLI are absent or unreadable.

**5.1.10** Two slices on one track of a Chrome trace at one depth MUST NOT overlap.

> Informative: Cursor Agent keeps no log a trace can read; its sessions are absent from traces.

### 5.2 Profiling switches

**5.2.1** hmz MUST record an environment profile of an epic only where the epic was started with
`profile_environment` on (`--profile-environment` on `hmz exec`).

**5.2.2** hmz MUST record a flow profile of an epic only where the epic was started with
`profile_flow` on (`--profile-flow` on `hmz exec`).

**5.2.3** Each profiling switch MUST be an option of one epic, given as its budget is given; a
setting of a workspace MUST NOT turn either on for an epic started by `hmz exec` or the SDK.

**5.2.4** An epic MUST record which profiling switches it was started with, and an epic that
records neither MUST read back as profiled in neither way.

### 5.3 Profiles

**5.3.1** Profiling MUST sample rather than intercept, and MUST NOT be able to stop or fail an
epic: a program that cannot be read, or a profile that cannot be written, MUST leave the epic as
it would otherwise have been.

**5.3.2** hmz MUST append an environment profile as each program is seen, and MUST NOT hold it
until the epic ends.

**5.3.3** hmz MUST time every profile against the same clock as the rest of the epic's trace.

**5.3.4** An environment profile MUST record, for each program, its process identifier, its
parent's process identifier, its name, its arguments, when it began, when it ended, and each of
its threads with when it began, when it ended and the CPU time it used.

**5.3.5** A flow profile MUST record the call stacks of the flow's own Python code from the
thread and task it executes in, leaving out the frames shared with where the epic was started,
each stack with its start time and duration, a frame being named by its function, file and
line, outermost first.

**5.3.6** A flow profile MUST merge consecutive samples of one stack into one record.

## 6. Exomyth timeline

### 6.1 Content

**6.1.1** hmz MUST lay out an Exomyth timeline for any epic, executing or ended, from exactly what
a Chrome trace of that epic is gathered from, together with the epic's tree of flow calls and its
profiles.

**6.1.2** hmz MUST NOT write an Exomyth timeline to disk.

**6.1.3** An Exomyth timeline MUST hold one process of kind `flow` for the epic, first; then one
process of kind `flow` named `python` where the epic has a flow profile; then one process of kind
`session` per session that did anything, in order of start; then one process of kind `os` per
program of an environment profile, in order of start and then of process identifier.

**6.1.4** The epic's `flow` process MUST hold one span for the epic and one span for every flow
call, each inside the span of its caller.

**6.1.5** A flow call that has not returned, and an epic that has not ended, MUST be laid out as
ending at the last moment anything in the timeline did.

**6.1.6** A `session` process MUST hold one `session` span covering everything the session did,
and one span per action of the session under it, in the action's own category.

**6.1.7** An `os` process MUST hold one `process` span per thread; the `python` process MUST hold
one `sample` span per merged frame of the flow profile, named as the frame is.

**6.1.8** The parent of a sub-agent's process MUST be the session that started it; the parent of a
session the epic opened, of a sub-agent whose starter did nothing, and of the `python` process
MUST be the epic's `flow` process; the parent of a program's process MUST be the program that held
its parent process identifier when it started, where that program was profiled.

**6.1.9** A session process MUST name the role its agent filled, read from the epic's agents by
the agent's name, and MUST name no role where no agent of the epic has that name.

**6.1.10** An Exomyth timeline MUST hold one spawn edge from each action that started a session
to that session's process, and one from the flow call that opened each other session, or from
the epic's span where no flow call opened it, to that session's process.

### 6.2 Document

**6.2.1** hmz MUST serve an Exomyth timeline as one JSON document holding exactly the keys
`version`, `layout`, `epic`, `origin`, `live`, `strings`, `processes`, `tracks`, `spawns` and
`summary` (`api/http.md`).

**6.2.2** `origin` MUST be the epoch seconds of the earliest moment of anything in the document,
and every time in the document MUST be whole microseconds since `origin`; every duration MUST be
whole microseconds and MUST NOT be negative.

**6.2.3** `live` MUST be true exactly while the epic has not ended.

**6.2.4** `strings` MUST hold every text the document states, each once, with the empty string at
index 0, and every other text field except a process's `kind` MUST be an index into `strings`.

**6.2.5** Every process MUST carry `id`, `kind`, `name`, `key`, `pid` (0 except for a program),
`start`, `end`, `parent` (a process `id`, or -1), `tracks`, `agent`, `role`, `backend`, `model`,
`label` and `record`.

**6.2.6** `tracks` MUST hold one track per lane of a process's spans, named after the process's
lane, with ` ~<n>` appended for the n-th further lane, each track carrying `process`, `name`,
`first`, `count`, `depths` and `spans`.

**6.2.7** `spans` of a track MUST be columns `start`, `dur`, `depth`, `cat`, `name`, `model`, `in`
and `out`, each `count` long and sorted by start; `in` and `out` MUST be the input and output
tokens a span reports, and 0 where it reports none.

**6.2.8** Two spans on one track at one depth MUST NOT overlap; where two spans start and end
together, a `session` span MUST hold a `turn` span and a `turn` span MUST hold every other span.

**6.2.9** A span's identifier MUST be its track's `first` plus its index in the track, numbering
every span of the document from 0 in track order with no gaps.

**6.2.10** `layout` MUST differ between two documents of one epic where a span identifier names a
span of a different process, track, start or category, and MUST be equal while spans only grow
longer.

**6.2.11** `spawns` MUST be columns `span` and `process`, sorted.

**6.2.12** `summary` MUST carry `start` (0), `end`, the counts of `processes`, `tracks` and
`spans`, and per category its `count`, its summed `time`, and its `in` and `out` tokens.

### 6.3 Span details

**6.3.1** The document MUST NOT carry what each span carries beyond §6.2.7; hmz MUST answer a span
by identifier with its `id`, `process`, `track`, `start`, `dur`, `depth`, `cat`, `name`, `at`
(ISO 8601, UTC) and `args`.

**6.3.2** hmz MUST answer a span identifier from the last timeline laid out of that epic, and
MUST refuse an identifier that timeline does not have.

> Informative: the timeline is laid out fast enough that an epic of fifty thousand spans is
> drawn without a perceptible wait.
