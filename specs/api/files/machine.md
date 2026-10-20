# Machine Directories

## 1. Scope

This document specifies every file and directory **hmz** creates on **this machine** outside
the **home** and outside any **workspace**: the machine directory in the temporary directory,
the cache directory `~/.cache/humanize/`, the files of the **daemon**, the directories of ssh
connection sharing, and the temporary directories **hmz** creates for one process. For each it
states the path, the creator, the format, the mode, the lifetime and when the **user** MAY
delete it.

Out of scope:

- The definitions and rules common to `api/files/`: `api/files/home.md` §2 and §3.
- The temporary directories **hmz** creates for a **harness** process, including virtual config
  homes: `api/files/harness-homes.md`.
- Files on a **machine** other than **this machine**: `api/files/targets.md`.
- Files of the macOS app: `api/files/desktop.md`.
- The messages carried over the socket of the **daemon**: `api/daemon.md`.

## 2. Definitions

**2.1** **Temporary directory** (`<tmp>`): the first of the directories named by the
environment variables `TMPDIR`, `TEMP` and `TMP` of the process of **hmz** that exists and is
writable, and otherwise the first of `/tmp`, `/var/tmp` and `/usr/tmp` that is.

**2.2** **Machine directory** (`<mdir>`): the directory `<tmp>/humanize-<uid>`, where `<uid>` is
the numeric user identifier of the process.

**2.3** **Cache directory**: the directory `~/.cache/humanize/`.

**2.4** **Process-private temporary directory**: a directory that **hmz** creates in `<tmp>` with
a name of the stated prefix followed by `<random>`, with mode `0700`.

## 3. The machine directory

**3.1** `hmz` MUST create `<mdir>` with mode `0700` where it does not exist, the first time a
process needs an entry in it.

**3.2** `hmz` MUST refuse to use `<mdir>` where it is not a directory, is not owned by the
**user**, or is writable by its group or by others.

**3.3** `hmz` MUST report the refusal of clause 3.2 as
`<mdir> is not a directory only this user can write; remove it`.

**3.4** `hmz` MUST NOT locate `<mdir>` by `XDG_RUNTIME_DIR`.

**3.5** `hmz` MUST NOT remove `<mdir>`.

**3.6** `hmz` MUST create again, when it next needs it, every entry of `<mdir>` that is missing;
the **user** MAY delete any entry of `<mdir>` while **hmz** is not running.

> Informative: an operating system that cleans its temporary directory can empty `<mdir>`.

**3.7** `<mdir>` MUST contain no entries other than those specified in §4 to §8 and in
`api/files/harness-homes.md`.

## 4. Caches in the machine directory

**4.1** `<mdir>/prices.json` MUST be a JSON object with the keys `source` (string, the URL or
path fetched), `etag` (string), `fetched` (number, seconds since the Unix epoch), `date`
(string) and `models` (object mapping a model identifier to an object with the keys `provider`,
`name` and `per_million`, the last an object with the number keys `input`, `output`,
`cache_read` and `cache_write`).

**4.2** `hmz` MUST write `<mdir>/prices.json` by atomic replacement when it is older than 24
hours and a process of **hmz** asks for prices, from the source `HUMANIZE_PRICES` names, and
MUST NOT write it from a source that gives any price that is not a finite number.

**4.3** `hmz` MUST remove, before each fetch of prices, every file `<mdir>/.prices.json.*.new` and
`<mdir>/prices.json.*` older than 10 minutes.

**4.4** `<mdir>/releases.json` MUST be the JSON object `{"latest": <string>}`, the newest release
of `hmz` that the source `HUMANIZE_RELEASES` names; `hmz` MUST write it by atomic replacement.

**4.5** `<mdir>/models/<cli>/<account>.json` and `<mdir>/models/<cli>/_local.json` MUST hold the
model catalogue of one **account** of the **harness** `<cli>`, and of the sign-in of that
**harness** outside any **account**, as the JSON object
`{"asked": <UTC timestamp to the second>, "models": [{"name": <string>, "efforts":
[<string>, ...], "swarms": <bool>}, ...]}`.

**4.6** `hmz` MUST write a model catalogue by atomic replacement.

**4.7** `hmz` MUST ask the **harness** again for a model catalogue as `features/accounts.md` §8.1
states.

**4.8** `hmz` MUST remove the model catalogue of an **account** when it removes the **account**.

**4.9** `<mdir>/pinned/<url-digest>/<commit>/` MUST be a `git` checkout of the repository at the
URL whose digest is `<url-digest>` (16 lowercase hexadecimal digits), detached at `<commit>`,
that **hmz** clones for a flow reference pinned to a commit and for a release it installs.

**4.10** `hmz` MUST create a checkout of clause 4.9 by cloning into
`<mdir>/pinned/<url-digest>/.<random>` and renaming it into place, and MUST NOT remove a checkout.

**4.11** `<mdir>/skills/<owner>-<repo>-<digest>/`, where `<digest>` is 12 lowercase hexadecimal
digits of the SHA-256 of the URL, MUST be a `git` clone of a skill repository that a **role** of
a **flow** not installed names by URL; `hmz` MUST fetch it again on each **epic** that names it.

**4.12** `<mdir>/compiled/pi/` and `<mdir>/compiled/qwen/` MUST be cache directories of the
**harnesses** `pi` and `qwen`, which **hmz** names to them in `NODE_COMPILE_CACHE` where that
variable is not set, and whose content those **harnesses** write; the **user** MAY delete them
while no process of those **harnesses** runs.

**4.13** `<mdir>/docker-ssh/<digest>/ssh`, where `<digest>` is 16 lowercase hexadecimal digits,
MUST be an executable shell script of mode `0700`, in a directory of mode `0700`, that runs
`ssh` with the options of one docker **runtime** reached over ssh; `hmz` MUST write it by atomic
replacement and MUST NOT remove it.

**4.14** `<mdir>/tokens/<digest>`, where `<digest>` is 32 lowercase hexadecimal digits of the
SHA-256 of a secret, MUST hold that secret alone, with mode `0600`, in a directory of mode
`0700`, for a command line that names a secret by file.

**4.15** `hmz` MUST remove a file of clause 4.14 when the Slurm job whose secret it holds is
stopped, and MAY leave every other such file.

**4.16** `<mdir>/harness/` MUST be an empty directory that **hmz** mounts as the working directory
of a **harness** placed in a container on **this machine** without a working directory; `hmz`
MUST NOT write into it and MUST NOT remove it.

**4.17** `<mdir>/backup/<target>/` MUST be a `git` clone of the repository of the backup target
`<target>`, and `<mdir>/backup/<target>.lock` an empty file that guards that clone; `hmz` MUST
NOT remove either.

**4.18** At most one process of `hmz` MUST use a clone of clause 4.17 at a time.

**4.19** `hmz` MUST NOT write into a backup clone any `git` configuration other than
`remote.origin.url`, `remote.origin.fetch` and, where `user.email` is not set in it,
`user.name` and `user.email`.

## 5. The bundle

**5.1** `<mdir>/humanize-<digest>.pyz`, where `<digest>` is 16 lowercase hexadecimal digits,
MUST be the zip application of **hmz** that **hmz** copies to a **machine** other than **this
machine**, with mode `0600`; `<digest>` identifies its content.

**5.2** `<mdir>/<stamp>.digest`, where `<stamp>` is 64 lowercase hexadecimal digits identifying
the source tree a bundle was built from, MUST hold the `<digest>` of that bundle followed by a
line feed, with mode `0600`.

**5.3** `hmz` MUST write a bundle into `<mdir>/humanize-<random>.pyz.new` and rename it into
place, and MUST write a `.digest` file by atomic replacement.

**5.4** `hmz` MUST update the modification time of the bundle an **epic** uses at least once an
hour while that **epic** runs.

**5.5** `hmz` MUST remove, each time it builds a bundle, every entry of `<mdir>` whose name begins
with `humanize-` or ends with `.digest` and whose modification time is more than 14 days ago,
and the files `<tmp>/humanize-<uid>.pyz` and `<tmp>/humanize-<uid>.stamp`.

**5.6** `hmz` MUST build a bundle in a process-private temporary directory with the prefix
`humanize-bundle-` and MUST remove it when the build ends.

## 6. The daemon

**6.1** `<mdir>/daemon.sock` MUST be the Unix-domain socket on which the **daemon** of the
**user** on **this machine** accepts **frontends**, with mode `0600`.

**6.2** `<mdir>/daemon.json` MUST be a JSON object with exactly the keys `pid` (integer, the
process identifier of the **daemon**), `started` (string, `YYYY-MM-DDTHH:MM:SSZ`), `kind` (the
string `daemon`) and `protocol` (integer, the protocol version specified in `api/daemon.md`),
with mode `0600`, written by atomic replacement.

**6.3** The **daemon** MUST remove a stale `<mdir>/daemon.sock` before it binds the socket, and
MUST remove `<mdir>/daemon.sock` and `<mdir>/daemon.json` when it closes.

**6.4** `<mdir>/daemon.lock` MUST be an empty file of mode `0600` that guards the **daemon** for
its whole life; `hmz` MUST NOT remove it.

**6.5** `<mdir>/daemon.log` MUST receive, appended, the standard output and standard error of the
**daemon** and of each of its host processes while that process holds no **epic**, with mode
`0600`; `hmz` MUST NOT rotate, truncate or remove it.

**6.6** The **daemon** MUST update the modification time of `<mdir>` and of each file of §6 at
least once an hour while it runs.

**6.7** The **user** MUST NOT delete `<mdir>/daemon.sock`, `<mdir>/daemon.json` or
`<mdir>/daemon.lock` while the **daemon** runs, and MAY delete `<mdir>/daemon.log` at any time.

**6.8** Two processes of **hmz** whose temporary directories differ MUST reach different
**daemons**.

## 7. Scratch directories in the machine directory

**7.1** `<mdir>/web-<port>.html`, where `<port>` is the port of the web **frontend**, MUST be an
HTML page that redirects to the address of that **frontend**, including its access key, with
mode `0600`; `hmz` MUST remove it when that **frontend** stops serving.

**7.2** `hmz` MUST hold an uploaded `.hmzepic` archive in a directory `<mdir>/tmp<random>/` of mode
`0700` while it imports it, and MUST remove that directory when the request ends.

**7.3** `hmz` MUST hold an archive the web **frontend** exports in a directory
`<mdir>/tmp<random>/` of mode `0700`, and MUST remove that directory when the download ends or
fails.

**7.4** `hmz` MUST hold a trace it computes for a transcript in a directory `<mdir>/tmp<random>/`
and MUST remove it when the computation ends.

**7.5** `<mdir>/aside-<random>/` MUST hold the **sessions** of one side question that recalls a
**session** of an earlier **epic**; `hmz` MUST remove it when the side question closes, when its
**frontend** leaves, or when its host process closes.

**7.6** `<mdir>/.<runtime-kind>.<runtime>.lock`, where `<runtime-kind>` is `docker`, `swarm`,
`slurm` or `apple-container` and `<runtime>` is the name of a **runtime**, MUST be an empty file
that guards that **runtime**; `hmz` MUST NOT remove it.

**7.7** At most one process of **hmz** MUST size, create or submit containers, services or jobs on
one **runtime** at a time.

## 8. Other process-private temporary directories

**8.1** `hmz` MUST create a process-private temporary directory with the prefix `hmz-sessions-`
for an **epic** that has no resume journal when a **flow** of it first stores a **session** in
its state, and MUST remove it when the **epic** ends.

**8.2** `hmz` MUST create, for each container of a docker or Apple container **env** and for each
swarm service or Slurm job of an **env**, a process-private temporary directory with the prefix
`humanize-`, holding the file `container` (the container identifier, docker and Apple container
only) and the directory `shadow`, and MUST remove it when the container, service or job is
removed.

**8.3** The directories of ssh connection sharing MUST be
`${XDG_RUNTIME_DIR:-<tmp>}/humanize-ssh-<uid>/`, with mode `0700`, holding the control sockets
`ssh` creates, named `%C` or `%C-<8 hexadecimal digits>`, which `ssh` removes 120 seconds after
their last use; `hmz` MUST NOT create the directory where `HUMANIZE_SSH_REUSE` turns sharing off,
and MUST NOT remove it.

## 9. The cache directory

**9.1** The location of the mirror records MUST be the directory `HUMANIZE_SHADOWS` names, `~`
expanded, where it is set and not empty, and `~/.cache/humanize/shadows/` otherwise; it MUST NOT
follow `HUMANIZE_HOME`.

**9.2** For each **mirror** on **this machine**, the directory of clause 9.1 MUST hold
`<sha16>.json`, where `<sha16>` is the first 16 lowercase hexadecimal digits of the SHA-256 of
the absolute path of the **mirror**.

**9.3** `<sha16>.json` MUST be the JSON object `{"shadow": <string>, "target": <string>}` naming
the absolute path of the **mirror** and the **machine** it mirrors, written by atomic
replacement each time a **harness** begins to use the **mirror**.

**9.4** `<sha16>.journal` MUST be a file of mode `0600` in which the **harness** processes using
the **mirror** record what they know of its files; its content is not specified.

**9.5** `<sha16>.live` MUST be an empty file of mode `0600` that marks the **mirror** as used while
any **harness** process uses it.

**9.6** `hmz` MUST empty `<sha16>.journal` when a **harness** process begins to use the
**mirror** while no other **harness** process uses it.

**9.7** `hmz` MUST NOT remove the files of §9 when it removes the **mirror** they describe.

**9.8** The **user** MAY delete the files of §9 while **hmz** is not running.

**9.9** `~/.cache/humanize/litellm/sessions/<id>.jsonl` MUST hold a **session** of the
**harness** `litellm` that is not kept in an **epic**, as JSON Lines whose first line is
`{"type": "session", "id", "parent", "cwd", "model", "timestamp"}` and whose following lines are
`{"type": "message", "timestamp", "message": {"role", "content", ...}}`.

**9.10** `hmz` MUST NOT remove a file of clause 9.9, and the **user** MAY delete it at any time.

## 10. Files hmz reads and never writes

**10.1** `hmz` MUST NOT write `~/.ssh/config`, any file it includes, or any other file under
`~/.ssh/`.

**10.2** `hmz` MUST NOT write `$DSH_HOME/settings.yaml`, `$DSH_HOME/.credentials.yaml` or
`$DSH_HOME/.env`.
