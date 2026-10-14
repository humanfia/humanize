# Home Directory

## 1. Scope

This document specifies the **home** of **hmz** on **this machine**: its location, every file
and directory **hmz** creates in it, the format of each machine-readable file, the mode **hmz**
sets, the lifetime of each entry, and when the **user** MAY delete it. It also specifies the
definitions and rules shared by every document under `api/files/`.

Out of scope:

- The epic directories under `<home>/epics/`: `api/files/epics.md`.
- The keys and values of `settings.yaml`: `api/settings.md`.
- The content of the account directories under `<home>/providers/`:
  `api/files/harness-homes.md` §4.
- Directories outside the **home** on **this machine**: `api/files/machine.md`.
- The state directory of **hmz** on a **machine** other than **this machine**:
  `api/files/targets.md`.
- The directory `<workspace>/.hmz/`: `api/files/workspace.md`.

## 2. Definitions

**2.1** **`<home>`**: the absolute path of the **home**: the value of the environment variable
`HUMANIZE_HOME` where it is set and not empty, and `$HOME/.hmz` otherwise.

**2.2** **Workspace key** (`<ws>`): the absolute path of a **workspace**, with every symbolic
link resolved, in which every character outside `[A-Za-z0-9]` is replaced by one `-`.

> Informative: `/home/you/code` has the workspace key `-home-you-code`. Two distinct paths can
> have one workspace key, such as `/a/b.c` and `/a/b-c`.

**2.3** **Atomic replacement**: writing a file `F` by creating a new file in the directory of
`F` named `.<name of F>.<16 lowercase hexadecimal digits>.new`, writing the whole content into
it, flushing it to stable storage, and renaming it over `F`.

**2.4** **UTC timestamp**: a string of the form `YYYY-MM-DDTHH:MM:SS.mmmZ` stating a moment in
Coordinated Universal Time with millisecond precision.

**2.5** **Umask mode**: the mode that the umask of the writing process leaves of `0666` for a
file, or of `0777` for a directory.

**2.6** **While hmz is not running**: while no `hmz` process and no **daemon** of the **user**
runs on the **machine** the entry is on.

## 3. Rules common to `api/files/`

**3.1** Where a document under `api/files/` states that **hmz** writes a file by atomic
replacement, a reader of that file MUST observe either the whole previous content or the whole
new content.

**3.2** A file named `.<name>.<16 hex>.new` beside a file that **hmz** writes by atomic
replacement is the residue of a killed writer; **hmz** MAY leave it, and the **user** MAY delete
it at any time.

**3.3** Where a document under `api/files/` states no mode for a file or directory that **hmz**
creates, its mode is the umask mode.

**3.4** Every timestamp that **hmz** writes into a file specified under `api/files/` MUST be a
UTC timestamp, except where the clause specifying the file states another format.

**3.5** In a document under `api/files/`, `~` names the home directory of the **user** on the
**machine** the path is on, and never the **home** of **hmz**.

**3.6** In a document under `api/files/`, `<random>` names a string that **hmz** chooses so that
the path does not exist when it is created; its length and alphabet are not specified.

**3.7** A JSON Lines file specified under `api/files/` MUST hold one JSON value per line, each
line terminated by one line feed; a reader MUST skip a line that is not valid JSON.

## 4. The home

**4.1** `hmz` MUST NOT create `<home>` before it first writes a file under it; the first writer
of a file under `<home>` MUST create every missing directory on its path.

**4.2** Where `HUMANIZE_HOME` is not set, `$HOME/.hmz` does not exist and `$HOME/.humanize` is a
directory, `hmz` MUST rename `$HOME/.humanize` to `$HOME/.hmz` the first time a process resolves
`<home>`, without printing any message.

**4.3** Where both `$HOME/.hmz` and `$HOME/.humanize` exist, `hmz` MUST use `$HOME/.hmz`, and
MUST NOT read, modify, merge or remove `$HOME/.humanize`.

**4.4** Where the rename of clause 4.2 fails, `hmz` MUST continue with `$HOME/.hmz` without
reporting an error.

**4.5** `hmz` MUST NOT create in `<home>` any entry other than those specified in §5 to §11.

**4.6** `hmz` MUST NOT remove `<home>`.

## 5. Settings

**5.1** `<home>/settings.yaml` holds the settings of **hmz**, as a YAML mapping whose keys and
values are specified in `api/settings.md`.

**5.2** `hmz` MUST create `<home>/settings.yaml` when it first writes a setting, with mode
`0600`, and MUST keep the mode of an existing file.

**5.3** `hmz` MUST write `<home>/settings.yaml` by atomic replacement.

**5.4** Each writer of `<home>/settings.yaml` MUST, by `<home>/.settings.yaml.lock`, keep every
other writer out while it reads the file, makes one change and writes the file.

**5.5** A writer that cannot keep the other writers out within 30 seconds, or cannot open
`<home>/.settings.yaml.lock`, MUST proceed without keeping them out.

**5.6** `hmz` MUST create `<home>/.settings.yaml.lock` empty, with mode `0600`, and MUST NOT
remove it.

**5.7** A reader of `<home>/settings.yaml` MUST NOT wait for a writer.

**5.8** `hmz` MUST treat a `<home>/settings.yaml` that is missing, unreadable, not valid YAML or
not a mapping as holding no settings.

**5.9** `hmz` MUST NOT overwrite a `<home>/settings.yaml` that is unreadable, not valid YAML or
not a mapping.

**5.10** `hmz` MUST NOT remove `<home>/settings.yaml`.

**5.11** The **user** MAY delete `<home>/settings.yaml` and `<home>/.settings.yaml.lock` while
**hmz** is not running; every setting then takes its default.

## 6. Prompt history

**6.1** `<home>/history.jsonl` is a JSON Lines file holding the lines submitted at the prompt of
the TUI, in the order submitted.

**6.2** Each line of `<home>/history.jsonl` MUST be a JSON object with exactly the keys:

- `at`: string, the moment of submission, `YYYY-MM-DDTHH:MM:SS.ffffffZ` in UTC with microsecond
  precision;
- `workdir`: string, the absolute path of the directory the TUI ran in, symbolic links resolved;
- `text`: string, the submitted line.

**6.3** The TUI MUST append one line to `<home>/history.jsonl` for each submitted prompt line,
except a blank line and a line equal to the line submitted immediately before it.

**6.4** `hmz` MUST NOT truncate, rewrite or remove `<home>/history.jsonl`.

**6.5** The **user** MAY delete `<home>/history.jsonl` at any time.

## 7. Accounts

**7.1** `<home>/providers/<cli>/<name>/` is the directory of one **account**, where `<cli>` is
the canonical name of a **harness** and `<name>` is the account name, matching
`[A-Za-z0-9][A-Za-z0-9._-]*`.

**7.2** `hmz` MUST create `<home>/providers/`, `<home>/providers/<cli>/` and each account
directory with mode `0700`.

**7.3** The content of an account directory is specified in `api/files/harness-homes.md` §4.

**7.4** `hmz` MUST remove an account directory, with everything in it, when the **user**
removes the **account**, and MUST NOT remove it otherwise.

**7.5** The **user** MAY delete an account directory while **hmz** is not running; the
**account** then no longer exists.

**7.6** `<home>/local/` is a directory that an earlier release of **hmz** wrote; `hmz` MUST NOT
read or write it, and the **user** MAY delete it at any time.

## 8. Flowverses

**8.1** `<home>/flowverses/<verse>/` holds one flowverse known to **hmz**, where `<verse>` is
the flowverse name; `hmz` MUST create it when the flowverse is added.

**8.2** `<home>/flowverses/<verse>/index/` MUST be a `git` clone of depth 1 of the index
repository of the flowverse.

**8.3** `hmz` MUST create `<home>/flowverses/<verse>/index/` by cloning into
`<home>/flowverses/<verse>/.index.<random>/` and renaming that directory into place.

**8.4** `hmz` MUST update `<home>/flowverses/<verse>/index/` by fetching the head of its remote
at depth 1 and resetting the clone to it.

**8.5** `hmz` MUST remove a directory `<home>/flowverses/<verse>/.index.<random>/` older than 60
seconds before it next clones the index of that flowverse.

**8.6** `<home>/flowverses/<verse>/installed/[<owner>/]<flow>/` holds one installed flow, where
`<owner>/` is present only for a flow the index lists under an owner.

**8.7** An installed flow directory MUST hold the files of the release at its commit, without
`.git` and `__pycache__` directories, every skill the flow names by URL under
`skills/<skill>/`, and the file `.installed.json`.

**8.8** `hmz` MUST write an installed flow into `<parent>/.<flow>.<random>/` and rename it into
place.

**8.9** `hmz` MUST remove a directory `<parent>/.<flow>.<random>/` older than 600 seconds before
it next installs a flow named `<flow>` into `<parent>`.

**8.10** `.installed.json` MUST be a JSON object with exactly the keys:

- `verse`: string, the flowverse name;
- `owner`: string, the owner, `""` for a flow listed without one;
- `name`: string, the flow name;
- `version`: string, the release installed;
- `commit`: string, the commit the files were copied from;
- `repo`, `ref`, `subdir`: strings, as the manifest of the release states them;
- `dependencies`: object mapping a flow reference to a version range;
- `skills`: object mapping each skill URL the flow names to the list of skill names fetched for
  it.

**8.11** `hmz` MUST NOT treat as installed a directory whose `.installed.json` is missing,
unreadable, or names a `verse`, `owner` or `name` other than those of its path.

**8.12** `hmz` MUST remove an installed flow directory when the **user** uninstalls the flow or
an update replaces it.

**8.13** `hmz` MUST remove `<home>/flowverses/<verse>/installed/<owner>/` when the last flow in
it is removed.

**8.14** `hmz` MUST remove `<home>/flowverses/<verse>/` when the **user** removes the flowverse.

**8.15** `hmz` MUST NOT remove `<home>/flowverses/official/`.

**8.16** The **user** MAY delete `<home>/flowverses/` or any directory in it while **hmz** is
not running; the flowverses and flows it held are then neither known nor installed.

## 9. User flows

**9.1** `~/.hmz/flows/` holds the flows of the flowverse `user`; its location MUST be
`$HOME/.hmz/flows/` whatever `HUMANIZE_HOME` is set to.

**9.2** `hmz` MUST NOT create, modify or remove an entry of `~/.hmz/flows/`, except where the
**user** asks **hmz** to copy a flow into that directory by naming it.

**9.3** Where clause 9.2 permits a copy, `hmz` MUST write it into `~/.hmz/flows/.<flow>.<random>/`
and rename it to `~/.hmz/flows/<flow>/`.

## 10. Environment state

**10.1** `<home>/envs/` holds the directories that **hmz** derives from the working directory of
an **env** whose **env machine** is **this machine**; its content is specified in
`api/files/targets.md` §4.

**10.2** `<home>/envs/mirrors/` holds the local mirrors of **envs** whose **env machine** is a
container, a swarm service or a Slurm job; its content is specified in `api/files/targets.md` §6.

## 11. Epics

**11.1** `<home>/epics/<ws>/` holds the epic directories of the **workspace** whose workspace key
is `<ws>`; its content is specified in `api/files/epics.md`.

**11.2** `hmz` MUST NOT remove `<home>/epics/` or any directory in it, except the staging
directories specified in `api/files/epics.md` §11.4.
