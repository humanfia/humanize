# Epic Directories

## 1. Scope

This document specifies the directory **hmz** writes for each **epic**: its path and name,
every file in it, the format of each record and the events it holds, the resume journal, the
profiles, the lock file, the session and trace directories, and the `.hmzepic` archive into
which an **epic** is exported and from which it is imported.

Out of scope:

- The definitions and rules common to `api/files/`, including `<home>`, the workspace key,
  atomic replacement and UTC timestamps: `api/files/home.md` §2 and §3.
- Which paths of a **harness** are kept under `sessions/`: `api/files/harness-homes.md` §5.
- The meaning of an **epic**, its states and how a **frontend** presents it:
  `features/epics.md`.
- The format of a Chrome trace document: `features/monitoring.md`.
- Backups of an **epic**: `features/backups.md`.

## 2. Definitions

**2.1** **Epic directory** (`<epic>`): the directory **hmz** writes for one **epic**.

**2.2** The epic name (`features/epics.md` §2.1) of an **epic** MUST be the last path component
of its epic directory.

**2.3** **Record**: a JSON Lines file in an epic directory whose lines are events.

**2.4** **Epic record**: the record `<epic>/epic.jsonl`, which describes the **flow** the
**epic** executes.

**2.5** **Call record**: a record `<epic>/epic.<flow>_<id>.jsonl`, which describes one call of a
**flow** by another **flow** within the **epic**.

**2.6** **Event**: one line of a record: a JSON object with the keys `event`, a string naming the
event, and `at`, the UTC timestamp at which **hmz** wrote it, and the further keys this document
specifies for that event.

**2.7** **Legible form** of a string: the string with every maximal run of characters outside
`[A-Za-z0-9._@-]` replaced by one `-`, and every leading and trailing `-` removed.

**2.8** Every agent spec in a record MUST be spelled as `features/agents.md` §2.2 defines an
agent spec.

**2.9** **Role env spec**: an env spec of `api/settings.md` §2.9, preceded by `<role>=`.

## 3. The epic directory

**3.1** The path of an epic directory MUST be `<home>/epics/<ws>/<stamp>-<hex6>/`, where `<ws>`
is the workspace key of the **workspace** of the **epic**, `<stamp>` is the moment the **epic**
began in UTC formatted `YYYYMMDDTHHMMSS.mmmZ`, and `<hex6>` is six random lowercase hexadecimal
digits.

**3.2** `hmz` MUST NOT give two epic directories created by one process the same `<stamp>`, and
MUST NOT give an epic directory a `<stamp>` earlier than that of an epic directory the same
process created before it.

**3.3** `hmz` MUST create the epic directory, and every missing parent, when the **epic** begins.

**3.4** `hmz` MUST treat as an epic directory only a directory under `<home>/epics/<ws>/` that
holds a regular file `epic.jsonl`; a reader listing epics MUST skip every other entry.

**3.5** `hmz` MUST list the epics of a **workspace** in ascending order of epic name.

**3.6** `hmz` MUST NOT remove an epic directory or any file in it.

**3.7** The **user** MAY delete an epic directory of an **epic** that is not running; the
**epic** then no longer exists.

> Informative: the epic directory holds the only copy of the sessions the epic kept (§9.6).

**3.8** An epic directory MUST contain no entries other than those specified in §4 to §10.

## 4. Records

**4.1** Every record MUST be a JSON Lines file of events.

**4.2** `hmz` MUST append each event to its record as one line when the event occurs, and MUST
NOT rewrite or truncate a record, except as clause 11.6 states.

**4.3** A record MUST be encoded in UTF-8, with every character outside ASCII escaped.

**4.4** A reader of a record MUST ignore a key it does not know, and MUST ignore an event whose
`event` it does not know.

**4.5** The name of a call record MUST be `epic.<flow>_<id>.jsonl`, where `<flow>` is the legible
form of the canonical reference of the called **flow**, or `flow` where that form is empty, and
`<id>` is six random lowercase hexadecimal digits chosen per call.

**4.6** `hmz` MUST write a call record for each call of a **flow** by a **flow** within the
**epic**; one **flow** called twice MUST have two call records.

**4.7** A call made within a called **flow** MUST be written in the call record of that called
**flow**, and not in the epic record.

## 5. Events of the epic record

**5.1** The first event of an epic record MUST be `began`, written when the **epic** begins, with
the keys:

- `flow`: string, the **flow** as the **user** named it;
- `task`: string, the task given to the **flow**;
- `workspace`: string, the absolute path of the **workspace**, symbolic links resolved;
- `resumable`: boolean, whether the **flow** declares that it can be resumed;
- `ref`: string, the canonical reference of the **flow**; present only where it is known;
- `picked_up`: string, the epic name of the **epic** this one resumes; present only for an
  **epic** that resumes another;
- `agents`: array with one object per **role**, with the string keys `agent` (the **role**),
  `name` (the name of the **agent** filling it), `backend` (the **harness**), `model`,
  `effort` and `provider` (the **account**, `""` for none);
- `envs`: array of role env specs, one per **env** the **user** gave;
- `used`: array of role env specs stating where each **env** was placed; present only where it
  differs from `envs`;
- `params`: object, the parameters given to the **flow**;
- `budget`: object with the keys `duration` (number of seconds or `null`), `cost` (number of
  US dollars, or the string `"Infinity"` for none), `output_tokens` (integer or `null`) and
  `graceful` (boolean, or object with the boolean keys `duration`, `cost` and `output_tokens`);
- `profile_flow`: the value `true`; present only where the Python of the **flow** is profiled;
- `profile_environment`: the value `true`; present only where the processes of the **epic** are
  profiled;
- `backup`: array of the names of the backup targets of the **epic**; present only where it is
  not empty;
- `spelling`: the integer `2`, stating that `envs` and `used` follow the role env spec spelling of
  this document.

**5.2** A reader MUST read the `envs` and `used` of a `began` event without `spelling` as an
earlier spelling, and MUST convert each to the spelling of clause 2.9.

**5.3** `hmz` MUST write the event `reopened` into the epic record of an **epic** of a **chat**
when the **user** carries that **chat** on, with the key `task` (string, the task given on
carrying on), and MUST NOT write another `began` for it.

**5.4** `hmz` MUST write the event `opened` into the record of the **flow** that opened a
**session** when the **harness** of that **session** first states the identifier of the
**session**, with the keys:

- `agent`: string, the name of the **agent**, never the **role** it fills;
- `backend`: string, the canonical name of the **harness**;
- `provider`: string, the **account**, `local` where the **session** runs under no **account**;
- `session`: string, the identifier the **harness** gave the **session**;
- `name`: string, `<agent>-<backend>@<provider>-<session>` with each of the four parts in
  legible form;
- `where`: string, the directory holding the files of the **session**: `sessions/<cli>` relative
  to the epic directory where they are kept in it, and an absolute path otherwise;
- `parent`: string, the identifier of the **session** this one was forked from; present only for
  a forked **session**;
- `harness`: string, `local`, `env` or the `<backend>:<name>` of a harness runtime, where the
  **harness** went as `features/placements.md` §4.5.1 states; present only where the **env
  machine** is not **this machine**.

**5.5** `hmz` MUST NOT write `opened` for a **session** whose **harness** never stated an
identifier.

**5.6** `hmz` MUST write the event `called` into the record of the calling **flow** when a
**flow** calls a **flow**, with the keys `flow` (string, the canonical reference of the called
**flow**), `task` (string) and `epic` (string, the file name of the call record).

**5.7** `hmz` MUST write the event `returned` into the record of the calling **flow** when a call
ends, however it ends, with the keys `flow` and `epic`, equal to those of the matching `called`.

**5.8** A reader MUST match `returned` to `called` by the value of `epic`.

**5.9** `hmz` MUST NOT write the event `btw` into an epic record: the agent of side questions is
the setting of `api/settings.md` §4.3, and no epic's own.

**5.10** A reader MUST skip a `btw` event, which an earlier release of `hmz` wrote, as an event
that says nothing.

**5.11** `hmz` MUST write the event `usage` into the epic record immediately before each `ended`
of the epic record, with the keys `cost` (number, US dollars), `output_tokens` (integer) and
`seconds` (number), stating what the budget of the **epic** counted since it began or was last
reopened.

**5.12** `hmz` MUST write the event `ended` as the last event of each record when the **flow**
it describes stops, with the key `how` (string): `stopped` where the **flow** was cancelled from
outside, ran out of budget or raised the cancellation of its **flow**; `failed` where it raised
any other exception; and `done` otherwise.

**5.13** A reader MUST take the end of an epic record as the last `ended` after the last
`reopened`, and MUST take an epic record with no such `ended` as an **epic** that is running or
whose process was killed, telling the two apart by the lock of §9.1.

**5.14** A reader MUST take the spending of an **epic** as the sum of all `usage` events of its
epic record.

**5.15** `hmz` MUST write the event `backed` into the epic record each time it backs the **epic**
up, with the keys `to` (string, the name of the backup target), `ok` (boolean), `error`
(string, `""` where `ok` is `true`) and `why` (string, one of `session`, `interval`, `end` and
`manual`).

**5.16** `hmz` MUST write the event `imported` into the epic record as the last event when it
imports the **epic**, with the keys `from` (string, the file name of the archive, or a
description of the backup it was pulled from) and `head` (string, the commit of the
**workspace** that the archive manifest states, `""` for none).

**5.17** A reader MUST ignore the `backup` key of `began` and every `backed` event preceding the
last `imported` event.

**5.18** `hmz` MAY write `backed` and `imported` events after the last `ended` of an epic record.

**5.19** A epic record MUST contain no events other than those of §5.

## 6. Events of a call record

**6.1** The first event of a call record MUST be `began`, with the keys `flow` (string, the
canonical reference of the called **flow**), `task` (string), `workspace` (string), `resumable`
(boolean) and `under` (string, the file name of the record of the calling **flow**).

**6.2** A call record MUST contain only the events `began`, `opened`, `called`, `returned` and
`ended`, each as §5 specifies it.

**6.3** The `ended` event of a call record MUST state how the call ended.

## 7. Resume journal

**7.1** `<epic>/resume.jsonl` is the journal of an **epic** whose top-level **flow** is
resumable; `hmz` MUST NOT create it for any other **epic**.

**7.2** Each line of `<epic>/resume.jsonl` MUST be a JSON object without whitespace between
tokens, whose key `t` names its kind:

- `{"t":"journal","v":1}`: the header, always the first line;
- `{"t":"call","id":<int>,"parent":<int>,"digest":<string>,"seq":<int>,"ref":<string>}`: a
  **flow** call began; `parent` is `0` for the top-level **flow**; `digest` is 32 lowercase
  hexadecimal digits identifying the reference, task, **roles** and parameters of the call;
- `{"t":"end","id":<int>,"ok":<bool>}`: the call ended;
- `{"t":"set","id":<int>,"key":<string>,"value":<JSON>}`: the call stored a state value;
- `{"t":"del","id":<int>,"key":<string>}`: the call deleted a state value;
- `{"t":"session","id":<int>,"role":<string>,"harness":<string>,"model":<string>,
  "session":<string>}`: a **session** of the call;
- `{"t":"tmp","id":<int>,"env":<string>,"kind":<string>,"name":<string>,"chain":<string>,
  "workdir":<string>}`: a temporary directory derived from an **env** of the call.

**7.3** A state value that holds a kept **session** MUST be the object
`{"\u0000session":{"harness":<string>,"id":<string>,"at":<string>,"role":<string>}}`, where
`at` is the directory of the copy of §9.7.

**7.4** `hmz` MUST write `<epic>/resume.jsonl` by atomic replacement when the **epic** begins:
the header alone for an **epic** that resumes nothing, and the header followed by the compacted
journal for an **epic** that resumes another.

**7.5** The compacted journal MUST hold, for each call in ascending order of `id`, the `call`
line, one `set` line per key with its last value, the `session` and `tmp` lines, and the `end`
line where one was written.

**7.6** After clause 7.4, `hmz` MUST only append to `<epic>/resume.jsonl`.

**7.7** Where an **epic** resumes another, `hmz` MUST copy `resume.jsonl` of the resumed **epic**
into the new epic directory before compacting it, and MUST NOT modify the file of the resumed
**epic**.

**7.8** Where a **chat** is carried on in its own epic directory, `hmz` MUST compact
`<epic>/resume.jsonl` in place by atomic replacement.

## 8. Profiles

**8.1** `<epic>/profile.jsonl` MUST exist only for an **epic** whose processes are profiled, and
MUST hold one JSON object per line with the keys:

- `event`: string, `ran` where the process was first seen, `left` where it was last seen or the
  profile stopped;
- `pid`, `ppid`: integers;
- `name`: string; `argv`: array of strings;
- `began`: number, the start of the process as the operating system states it, in seconds since
  the Unix epoch;
- `seen`: number, the moment it was first sampled, in seconds since the Unix epoch;
- `ended`: number, the moment it was last seen, in seconds since the Unix epoch;
- `threads`: array of arrays `[tid, began, ended, cpu]`, where `cpu` is user and system seconds.

**8.2** A reader of `<epic>/profile.jsonl` MUST take, for each pair of `pid` and `began`, the
last line.

**8.3** `<epic>/flow-profile.jsonl` MUST exist only for an **epic** whose **flow** is profiled,
and MUST hold one JSON object per line with the keys `t` (number, start in seconds since the
Unix epoch), `dt` (number, duration in seconds) and `stack` (array of strings, each
`<function> <file>:<line>`, outermost first).

**8.4** `hmz` MUST write `<epic>/flow-profile.jsonl` when the **epic** ends.

## 9. Other files

**9.1** `<epic>/.held` MUST be an empty file of mode `0600`, on which the process executing the
**epic** holds an exclusive advisory lock (`flock`) from the moment the **epic** begins or is
reopened until `ended` is written.

**9.2** A reader MUST take an **epic** as running exactly while a shared advisory lock on
`<epic>/.held` cannot be granted.

**9.3** `hmz` MUST NOT remove `<epic>/.held`.

**9.4** `<epic>/host.log` MUST exist only for an **epic** a **daemon** holds, and MUST hold,
appended in the order written, the standard error of the host process of the **daemon** holding
the **epic**, including the output of the **harness** processes it starts; its mode MUST be
`0600`, and `hmz` MUST NOT rotate or truncate it.

**9.5** `<epic>/sessions/<cli>/` MUST hold the files of every **session** of the **harness**
`<cli>` kept in the **epic**, laid out as that **harness** lays them out under its own home
directory; which paths are kept is specified in `api/files/harness-homes.md` §5.

**9.6** `hmz` MUST NOT write a **session** into `<epic>/sessions/` and into the home directory of
its **harness** both.

**9.7** `<epic>/sessions/<cli>/.kept/<id>/`, where `<id>` is 32 lowercase hexadecimal digits,
MUST hold a copy of a **session** that a **flow** stored in its state, laid out as clause 9.5
states.

**9.8** An epic directory written by an earlier release of **hmz** MAY hold
`sessions/<session name>/` directories of symbolic links; a reader MUST read them as the files
of that **session**.

**9.9** `<epic>/traces/<YYYYMMDDTHHMMSSZ>.trace.json` MUST be a Chrome trace document of the
**epic**, written when a program asks for a trace of it without naming an output.

**9.10** `<epic>/traces/export.trace.json` MUST be a Chrome trace document of the **epic**,
written each time the TUI exports the **epic**, replacing the previous one.

**9.11** `<epic>/manifest.json` and `<epic>/transcript.md` MUST exist only in an epic directory
that **hmz** imported, as copies of the members of that name of §10.

## 10. The `.hmzepic` archive

**10.1** An exported **epic** MUST be one gzip-compressed POSIX tar archive with the file name
extension `.hmzepic` and the media type `application/vnd.hmz.epic+gzip`.

**10.2** The default file name of an archive MUST be `<epic name>.hmzepic`.

**10.3** `hmz` MUST write an archive to a temporary file `.<file name>.<random>.new` of mode
`0600` in the destination directory and rename it over the destination; the archive keeps mode
`0600`.

**10.4** Every member of an archive MUST be a regular file under the one directory
`<epic name>/`, with mode `0644`, owner and group `0` and empty owner and group names.

**10.5** An archive MUST hold exactly these members, in this order:

- `epic.jsonl`, then every call record in ascending order of name;
- `resume.jsonl`, `profile.jsonl` and `flow-profile.jsonl`, each where it exists;
- `traces/<name>` for each regular file directly in `<epic>/traces/`;
- `sessions/<session name>/<path>` for each file of each **session**, where `<session name>` is
  the `name` of its `opened` event and `<path>` is relative to its `where`;
- `transcript.md`, only where the exporting program supplies a transcript;
- `manifest.json`.

**10.6** `hmz` MUST replace in every member each secret it can identify by the string
`[redacted]`; `features/epics.md` specifies which strings are secrets.

**10.7** `manifest.json` MUST be a JSON object with the keys:

- `humanize`: string, the version of **hmz** that wrote it;
- `made`: string, the UTC timestamp of the export;
- `python`, `machine`: strings, the version of Python and a description of the platform;
- `epic`: string, the epic name;
- `run`: object with the keys `flow`, `task`, `began`, `ended`, `how` (`left unfinished` where
  the **epic** has no end) and `resumable`;
- `workspace`: object with the keys `at` (string, the path) and `head` (string, the `head` of
  the last `imported` event where there is one, and the current commit of the **workspace**
  otherwise);
- `agents`: array of objects with the keys `agent`, `name`, `backend`, `model`, `effort`,
  `provider` and `runs` (an agent spec);
- `envs`, `used`: arrays of role env specs;
- `called`: array of objects with the keys `flow`, `task`, `record`, `under`, `began`, `ended`
  and `how`, one per call record;
- `sessions`: array of objects with the keys `name`, `agent`, `backend`, `provider`, `session`,
  `flow`, `record`, `at`, `logs` (array of the member paths held for it) and, only where `logs`
  is empty, `because` (string);
- `backends`: object mapping each **harness** to an object with the keys `command`,
  `executable`, `version`, `sha256` and, for a **harness** **hmz** knows, `logs` (boolean);
- `held`: array of every member path, `manifest.json` last;
- `redacted`: array of strings stating what was redacted.

**10.8** A **user** MAY delete an archive at any time; **hmz** MUST NOT remove an archive it wrote
to a destination the **user** chose.

## 11. Import

**11.1** `hmz` MUST refuse to import a file whose name does not end in `.hmzepic`, that is not a
gzip-compressed tar archive, that holds other than exactly one top-level directory, whose
top-level directory name is empty, `.`, `..`, begins with `.` or contains `\`, that holds a
member that is neither a regular file nor a directory or whose path contains `..`, or that lacks
`<epic name>/epic.jsonl` or `<epic name>/manifest.json`.

**11.2** `hmz` MUST place an imported **epic** at `<home>/epics/<ws>/<epic name>/`, where `<ws>`
is the workspace key of the `workspace` of its `began` event, and MUST refuse an archive whose
`workspace` is not an absolute path.

**11.3** `hmz` MUST refuse to import an **epic** whose destination exists, and MUST NOT modify
that destination.

**11.4** `hmz` MUST extract an archive into a staging directory `<home>/epics/<ws>/.<epic
name>.<random>/` of mode `0700` and rename the result into place, and MUST remove the staging
directory however the import ends.

**11.5** `hmz` MUST move the files of each **session** from `sessions/<session name>/` to its
`where`, where that `where` is within the epic directory.

**11.6** `hmz` MUST rewrite each `opened` event whose `where` is an absolute path so that `where`
is `sessions/<backend>`, in every record of the imported **epic**.

**11.7** `hmz` MUST append `imported` to the epic record before the rename of clause 11.4.
