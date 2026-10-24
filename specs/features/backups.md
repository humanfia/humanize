# Backups and Export

## 1. Scope

This specification defines how **hmz** copies an **epic** off **this machine** and back: backing
an epic up to git repositories, by policy and by hand; listing and downloading the epics a
backup target holds; exporting an epic as one `.hmzepic` archive; and importing such an archive
or a downloaded epic as an epic of this machine.

Out of scope:

- The command-line syntax of `hmz backup`, `hmz exec --backup` and their exit statuses beyond
  what is stated here (`api/cli.md`).
- The settings keys under which backup targets are kept (`api/settings.md`).
- The layout of an epic directory and of the git clones hmz keeps (`api/files/epics.md`,
  `api/files/machine.md`).
- How a frontend offers export, import, backup and download (`features/tui.md`,
  `features/web.md`).
- Whether an imported epic can be picked up (`features/epics.md` §3.7.11).

## 2. Definitions

**2.1** **Backup target**: a git repository, named in this machine's settings, to which epics
are backed up; it has a **name**, a **URL**, a **branch**, zero or more **policies** and an
**interval** in minutes.

**2.2** **Default targets**: the backup targets settings names as those an epic is backed up to
where it names none.

**2.3** **Policy**: one of `session`, `interval` and `end`, each a condition under which an epic
is backed up without anyone asking (§3.3).

**2.4** **Backup**: one commit, pushed to a backup target's branch, holding one epic as files.

**2.5** **Epic key**: the path `<machine>/<workspace>/<epic>` at which a backup target holds one
epic, where `<machine>` is this machine's host name up to its first dot, every character outside
`A-Z`, `a-z`, `0-9`, `.`, `_` and `-` replaced by `-`, `<workspace>` is the name of the directory
under which hmz keeps the epics of the workspace, and `<epic>` is the epic name.

**2.6** **Bundle**: a gzip-compressed tar archive that holds exactly one epic as files, named
`<epic>.hmzepic` unless the user names the file otherwise.

**2.7** **Manifest**: the file `manifest.json` that a bundle and a backup hold beside the epic's
records, stating what the epic was (§4.2).

**2.8** **Credential scrubbing**: the replacement, by the literal text `[redacted]`, of every
credential §4.3 lists in every byte hmz writes into a bundle or a backup.

**2.9** **Import**: placing an epic read from a bundle or from a backup target among the epics
of this machine.

## 3. Backups

### 3.1 Targets

**3.1.1** hmz MUST keep backup targets, and the default targets among them, as settings of the
**home** and not of any workspace.

**3.1.2** A backup target's name MUST be one to 32 characters of `A-Z`, `a-z`, `0-9`, `_` and
`-`, starting with a letter or digit.

**3.1.3** A backup target MUST have a non-empty URL.

**3.1.4** A backup target's branch MUST be `main` unless another is given.

**3.1.5** A backup target's interval MUST be a whole number of minutes of at least 1, and MUST be
30 unless another is given.

**3.1.6** A backup target with no policy MUST be backed up to by hand only.

**3.1.7** Writing backup targets MUST refuse, writing nothing, a target that violates §3.1.2 to
§3.1.5, a policy other than those of §2.3, two targets of one name, and a default target naming
no target; writing them MUST leave every other setting unchanged.

**3.1.8** Reading backup targets MUST read an entry that is not a valid target as no target, and
a default naming no target as no default.

### 3.2 Choosing targets

**3.2.1** An epic MUST be backed up to the targets it was started with: the default targets where
it was started with none named, and no target where it was started with an empty list
(`--backup none`).

**3.2.2** hmz MUST refuse to start an epic naming a backup target that settings does not hold.

**3.2.3** An epic MUST record the backup targets it was started with.

### 3.3 Policies

**3.3.1** Under `session`, hmz MUST back an epic up each time one of its sessions closes.

**3.3.2** Under `interval`, hmz MUST back an epic up every interval of the target while the epic
executes.

**3.3.3** Under `end`, hmz MUST back an epic up once when it ends, whatever its ending.

**3.3.4** hmz MUST apply each policy whichever way the epic was started.

### 3.4 Backing up by hand

**3.4.1** A backup by hand MUST go to the targets named, else to the targets the epic was started
with, else to the default targets.

**3.4.2** A backup by hand MUST be refused for a target settings does not hold, and for an epic
with no target to go to.

**3.4.3** `hmz backup <epic>` MUST wait for the backup to finish, MUST state for each target
whether it succeeded, naming the target's URL with any credential removed where it succeeded
and the error where it failed, and MUST exit 0 where every
target succeeded, 1 where any failed, and 2 for an epic or a target that does not exist or where
there is no target.

**3.4.4** A frontend offering a backup by hand MUST return at once, and MUST then show how the
backup went as the epic records it.

**3.4.5** While `hmz backup` waits on a target -- backing up to it, listing it, or downloading from
it -- and standard error is a terminal and escapes are allowed (`api/cli.md` §4.2), it MUST draw a
transient spinner there saying what it is doing and to which target, and MUST take it down before
it states how that went.

### 3.5 Content and delivery

**3.5.1** A backup MUST hold exactly the files a bundle of the epic holds (§4.1), scrubbed as a
bundle is, under the epic key on the target's branch, laid out as files rather than as an
archive.

**3.5.2** A backup MUST be one commit whose message names the epic and the reason it was made:
`session`, `interval`, `end` or `manual`.

**3.5.3** A backup MUST start from what the remote branch holds, MUST create the branch where the
remote has none, and MUST try once more where the push is refused.

**3.5.4** hmz MUST NOT make a commit where nothing but the manifest of the epic changed since the
last backup.

**3.5.5** A backup MUST NOT carry the epic's own record of how its earlier backups went.

**3.5.6** hmz MUST reach a backup target only with this machine's own git and the credentials
git already uses, MUST NOT prompt anyone for anything, and MUST bound every git command by a
timeout.

**3.5.7** Where git has no author identity configured, hmz MUST commit as `hmz <hmz@localhost>`.

**3.5.8** A backup MUST NOT delay the epic, any frontend or any other backup: each backup MUST be
queued and executed in the background, backups to one target MUST execute one at a time, and an
epic already queued for a target MUST NOT be queued for it a second time.

**3.5.9** Two processes on this machine MUST NOT back up to one target at the same time.

**3.5.10** A failed backup MUST be recorded in the epic and MUST NOT be raised to the epic or the
frontend.

**3.5.11** hmz MUST record in the epic, for each target, when its last backup was made, whether
it succeeded, why it failed with any credential removed, and why it was made, and MUST read this
back for every frontend.

**3.5.12** Once its epic has ended, `hmz exec` MUST wait at most 60 seconds for that epic's
queued backups, MUST state that it is waiting, and MUST state that a backup was left unfinished
where one was, without changing its exit status.

### 3.6 Listing and downloading

**3.6.1** hmz MUST list the epics a backup target holds by fetching the target's branch, under the
same exclusion, timeouts and absence of prompts as a backup, and MUST read the list from the
manifests there alone.

**3.6.2** A listed epic MUST state its epic key, its machine, the workspace it states it executed
in, its epic name, its flow, its task, when it began, when it ended, how it ended (empty where it
had not ended when backed up) and the commit its manifest states (§4.2.3).

**3.6.3** `hmz backup --list` MUST state, for each target named, else for every target, each
epic it holds on one line: machine, workspace, epic name, ending (`unfinished` where none) and
task.

**3.6.4** Downloading an epic MUST import it exactly as importing a bundle does (§4.5), with the
same refusals, an epic this machine backed up and still holds counting as an epic already here.

**3.6.5** A downloaded epic MUST record that it was imported from its epic key on its target,
naming the target's URL with any credential removed.

**3.6.6** hmz MUST refuse to download an epic key that is not three non-empty path segments, none
starting with `.` and none containing `\`.

**3.6.7** `hmz backup --pull <epic>` MUST download the epic, named by epic name or epic key, from
the first target named, else from the first target, that holds it, and MUST print where it now
is.

**3.6.8** `hmz backup --pull` MUST state every target that cannot be reached, and MUST exit 1
unless the epic was downloaded from another target; an epic already here MUST exit 1.

**3.6.9** `hmz backup --pull` MUST be a usage error where every target answered and none holds the
epic, or where a target holds epics of that name from more than one machine.

## 4. Export and import

### 4.1 Bundle content

**4.1.1** A bundle MUST hold, under one directory named after the epic, every record the epic
wrote, its flow state, its environment and flow profiles, and every trace gathered of it, each
only where the epic wrote one.

**4.1.2** A bundle MUST hold every log file of every session of the epic, under
`sessions/<session>/`, whether the epic keeps it or the CLI kept it elsewhere on this machine.

**4.1.3** A bundle MUST hold the screen transcript a frontend hands it, as `transcript.md`, and
none where none is handed.

**4.1.4** A bundle MUST hold a manifest.

**4.1.5** hmz MUST refuse to export a directory that holds no epic.

### 4.2 Manifest

**4.2.1** The manifest MUST state the version of hmz, when the bundle was made, the version of
Python, the operating system and architecture, and the epic name.

**4.2.2** The manifest MUST state the epic's flow, task, beginning, end, ending (`left
unfinished` where none) and whether it is resumable.

**4.2.3** The manifest MUST state the workspace the epic executed in and, where that workspace
is a git repository, the commit it is on when the bundle or backup is made.

**4.2.4** The manifest MUST state each agent role's agent, model, effort and account, each env as
given and as used, and the tree of flow calls.

**4.2.5** The manifest MUST state, for each session, its agent, backend, account, identifier,
flow call and log files, and MUST state of a session whose CLI keeps no log files that there are
none to hold.

**4.2.6** The manifest MUST state, for each backend the epic used, its command, the executable
found, its version and the SHA-256 hash of that executable, each empty where it cannot be found.

**4.2.7** The manifest MUST list every file the bundle holds and the credential classes that were
scrubbed (§4.3).

### 4.3 Credential scrubbing

**4.3.1** hmz MUST scrub every value of eight or more characters that any account on this
machine sets as an environment variable, except a value equal to the flow, or to a CLI, model,
effort, account or agent name, that the epic records it executed with.

**4.3.2** hmz MUST scrub keys in the formats vendors issue them, including those prefixed `sk-`,
`pk-`, `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`, `glpat-`, `xai-`, `xoxb-`, `xoxp-`,
`hf_` and `AIza`, JSON Web Tokens and bearer tokens.

**4.3.3** hmz MUST scrub a user and password written into a URL, and the value of a URL query
parameter whose name denotes a token, key, secret, signature, password or credential.

**4.3.4** hmz MUST scrub the value of any JSON field or `name=value` pair whose name denotes a
token, secret, API key, password or credential.

**4.3.5** hmz MUST NOT scrub token counts, costs or model names.

### 4.4 Writing a bundle

**4.4.1** hmz MUST write a bundle only to the path given: a file, or a directory into which it is
written as `<epic>.hmzepic`.

**4.4.2** hmz MUST write a bundle whole or not at all, and MUST leave nothing behind where
writing fails.

**4.4.3** A bundle MUST be readable and writable by the user who exported it alone.

**4.4.4** Exporting one epic again to the same path MUST replace the earlier bundle.

### 4.5 Importing

**4.5.1** hmz MUST import only a file whose name ends in `.hmzepic`, that is a gzip-compressed tar
archive, and that holds exactly one top-level directory containing the epic's record and a
manifest.

**4.5.2** hmz MUST refuse a bundle holding anything but plain files and directories, a member
that would land outside the epic, an epic whose name is empty or starts with `.`, and an epic
that states no absolute workspace.

**4.5.3** hmz MUST refuse to import an epic already present on this machine.

**4.5.4** hmz MUST place an imported epic among the epics of the workspace it states it executed
in, whether or not that workspace exists on this machine.

**4.5.5** hmz MUST place each session's logs where the session states it is kept; a session that
was kept in another machine's CLI home MUST be placed in the epic, and its record MUST be
rewritten to state so.

**4.5.6** An imported epic MUST record that it was imported, from which file or epic key, and the
commit its manifest states.

**4.5.7** hmz MUST import whole or not at all, and MUST leave nothing behind where importing
fails.
