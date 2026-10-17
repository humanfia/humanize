# Settings

## 1. Scope

This specification governs the settings file: its location, how it is read and written, every key
it holds with its type, default and validation, and which part of hmz reads each key. It also
governs every environment variable hmz reads from its own environment.

Out of scope:

- The accounts, which are kept outside the settings file (`features/accounts.md`,
  `api/files/home.md`).
- What a runtime does once an env is put on it, and how fallback between runtimes proceeds
  (`features/environments.md`).
- Where a harness runs under a runtime's harness setting (`features/placements.md`).
- What the fallback of a turn between places does at run time (`features/agents.md`).
- Backups as a feature (`features/backups.md`), notifications (`features/monitoring.md`), side
  questions (`features/btw.md`), error reports (`features/telemetry.md`), and the daemons of
  other machines (`features/daemons.md`).
- Environment variables hmz sets for the processes it starts (`api/files/harness-homes.md`,
  `api/files/targets.md`).

## 2. Definitions

**2.1** A **key path** names a value of the settings file by the keys that lead to it from the
top-level mapping, joined by `.`; `<x>` in a key path stands for any key of that mapping.

**2.2** A **machine key** is a key of the top-level mapping other than `workspaces`.

**2.3** A **workspace entry** is the value at `workspaces.<path>`.

**2.4** A **flow entry** is the value at `workspaces.<path>.flows.<flow>`.

**2.5** An **unreadable** settings file is one that exists but cannot be read, is not valid YAML,
or does not hold a mapping at its top level.

**2.6** A **writer** is any hmz process that changes the settings file.

**2.7** A place MUST be written as `features/agents.md` §2.3 defines it.

**2.8** An agent spec MUST be written as `features/agents.md` §2.2 defines it, which is the text
of an `-a` item after `<role>=` (`api/cli.md` §7.4).

**2.9** An **env spec** is the text of an `-e` item after `<role>=` (`api/cli.md §7.5`).

**2.10** A **runtime reference** is the text `<backend>:<name>`, `<backend>` being one of `ssh`,
`docker`, `swarm`, `apple-container` and `slurm`, and `<name>` a runtime name of §8.1.

## 3. The file

### 3.1 Location and format

**3.1.1** The settings file MUST be the file `settings.yaml` in the home.

**3.1.2** The settings file MUST hold one YAML mapping.

**3.1.3** hmz MUST NOT create the settings file, or the home, until it writes a setting.

### 3.2 Reading

**3.2.1** hmz MUST treat a settings file that does not exist, or that is unreadable, as an empty
mapping.

**3.2.2** An unreadable settings file MUST NOT prevent any hmz process from starting.

**3.2.3** A value whose type is not the type this specification gives for its key MUST be read as
absent, unless a section below specifies otherwise.

**3.2.4** hmz MUST preserve every key this specification does not define, at the top level and
in a workspace entry, across every write.

### 3.3 Writing

**3.3.1** Every write other than that of §4.7.2 MUST change exactly one thing: one machine key,
one workspace's `flow` key together with one flow entry, one workspace entry removed, the whole
value of `fallbacks`, of `clis`, of `backup`, of `daemons` or of `notifications`, or one runtime.

**3.3.2** A writer MUST guard, read and replace the settings file as `api/files/home.md` §5
states for `<home>/settings.yaml`.

**3.3.3** A writer MUST apply its change to the content the file holds at the time of the write,
and MUST NOT write back any other value it read earlier.

**3.3.4** A settings file that a write creates MUST have mode `0600`; a settings file that exists
MUST keep its mode.

**3.3.5** A writer MUST NOT write over an unreadable settings file.

**3.3.6** Every write MUST set the key `spelling` to `2`.

**3.3.7** Where a write of `enable_sentry`, `details`, `btw`, `every_epic`, `backup` or a
workspace entry fails, or the file is unreadable, the process MUST keep the change in its own
memory for as long as it runs and MUST NOT report an error.

**3.3.8** Where a write of `fallbacks`, `clis`, `daemons`, `notifications` or a runtime fails, or
the file is unreadable, hmz MUST refuse the change with an error that names the file.

## 4. Machine keys

### 4.1 `enable_sentry`

**4.1.1** `enable_sentry` MUST be a boolean that says whether hmz sends error reports
(`features/telemetry.md`).

**4.1.2** An absent `enable_sentry` MUST mean that the user has not been asked.

**4.1.3** Reading `enable_sentry` MUST NOT write it.

**4.1.4** `HUMANIZE_SENTRY` (§11.2.4) MUST override `enable_sentry` as
`features/telemetry.md` §3.1 states.

### 4.2 `details`

**4.2.1** `details` MUST be a boolean that says whether the terminal interface shows every tool
call and all reasoning of a turn rather than its responses alone.

**4.2.2** Any value of `details` other than `true` MUST be read as `false`.

### 4.3 `btw`

**4.3.1** `btw` MUST be a string holding an agent spec, `<harness>[@<account>]/<model>[:<effort>]`,
or the empty string.

**4.3.2** `btw` MUST name the agent that answers a side question asked of The Epic, for every epic
(`features/btw.md` §7).

**4.3.3** An absent, empty or non-string `btw` MUST mean that there is no such agent, and that a
side question asked of The Epic is refused (`features/btw.md` §5.9).

### 4.4 `every_epic`

**4.4.1** `every_epic` MUST be a boolean that says whether the terminal interface's list of epics
shows every epic of this machine rather than those of the current workspace.

**4.4.2** Any value of `every_epic` other than `true` MUST be read as `false`.

### 4.5 `notifications`

**4.5.1** `notifications` MUST be a mapping with the keys `kinds` and `system`.

**4.5.2** `notifications.kinds` MUST be a mapping from each of `done`, `failed`, `stopped`, `asked`
and `listening` to a boolean that says whether a notice of that kind is given
(`features/monitoring.md`).

**4.5.3** `notifications.system` MUST be a boolean that says whether hmz also asks the operating
system to show each notice.

**4.5.4** Every kind and `system` MUST be read as `true` unless its value is `false`.

**4.5.5** A write of `notifications` MUST write every kind and `system`.

### 4.6 `daemons`

**4.6.1** `daemons` MUST be a list of mappings, each naming the daemon of one other machine reached
over ssh (`features/daemons.md`).

**4.6.2** Each entry MUST have the key `name` and MAY have the keys `host`, `user`, `port`,
`identity_file`, `proxy_jump`, `options`, `alias` and `config`, with the types and validation of
the fields of the same names of an ssh runtime (§8.3), but for `options` (§4.6.4).

**4.6.3** `name` MUST begin with a letter or a digit, MUST consist of letters, digits, `.`, `_`
and `-`, and MUST NOT be `local` in any case.

**4.6.4** `options` MUST be a list of two-element lists, each a keyword and its value, with the
validation of §8.3.6 and §8.3.7.

**4.6.5** An entry with a key outside §4.6.2, with an invalid value, or with a `name` an earlier
entry has MUST be ignored when read and MUST be removed at the next write of `daemons`.

**4.6.6** The daemon of this machine MUST NOT be written in `daemons`.

### 4.7 `spelling`

**4.7.1** `spelling` MUST be an integer that says how env specs in the file are written.

**4.7.2** Where `spelling` is absent and the file holds an env spec in a spelling that
`api/cli.md §7.5.13` refuses, hmz MUST, on first reading the file, rewrite in one write every such
env spec of every flow entry as §4.7.3 specifies, setting `spelling` to `2`.

**4.7.3** The rewriting of §4.7.2 MUST turn `local@/<dir>` into `local/<dir>`; `ssh@<name>/<dir>`,
where no ssh runtime is written as `<name>`, into `ssh@[<name>]/<dir>`; and
`docker@local/<dir>`, `swarm@local/<dir>`, `apple-container@local/<dir>` and
`slurm@local/<dir>`, where no runtime of that backend is written as `local`, into
`<backend>/<dir>`.

**4.7.4** Where `spelling` is `2`, hmz MUST read every env spec as written, whatever has become of
the runtimes it names.

## 5. `workspaces`

### 5.1 Workspace entries

**5.1.1** `workspaces` MUST be a mapping from the path of a workspace (§5.1.2) to its workspace
entry.

**5.1.2** The key of a workspace entry MUST be the workspace's absolute path with every symbolic
link resolved.

**5.1.3** A workspace entry MUST be a mapping, and MAY be empty.

**5.1.4** The web interface MUST write an empty workspace entry for a workspace a user opens by
its path, and every workspace with an entry MUST be offered by the web interface
(`features/web.md`).

**5.1.5** `workspaces.<path>.flow` MUST be a string naming, as `api/cli.md §7.3` names a flow, the
flow the terminal interface opens on in that workspace.

**5.1.6** An absent `flow` MUST make the terminal interface open on the flow `chat`.

**5.1.7** `workspaces.<path>.flows` MUST be a mapping from a flow's name, as the flowverse lists
it, to its flow entry.

**5.1.8** Removing a workspace's settings MUST remove its whole workspace entry.

### 5.2 Flow entries

**5.2.1** `agents` MUST be a mapping from each agent role of the flow to an agent spec.

**5.2.2** Where any value of `agents` cannot be read as an agent spec, the whole of `agents` MUST
be read as absent.

**5.2.3** `envs` MUST be a mapping from each env role of the flow to an env spec.

**5.2.4** Where any value of `envs` is not a string, the whole of `envs` MUST be read as absent.

**5.2.5** `params` MUST be a mapping of the flow's params, as JSON values.

**5.2.6** `params` MUST be validated through the flow's params model when read, and a value the
model refuses MUST make the flow read as not set up.

**5.2.7** `budget` MUST be a mapping with the keys `duration`, an ISO 8601 duration or null;
`cost`, a number, the string `"Infinity"`, or null; `output_tokens`, an integer or null; and
`graceful`, a boolean.

**5.2.8** A `budget` that does not validate as a budget MUST be read as absent.

**5.2.9** `profile_flow` MUST be a boolean that says whether an epic of the flow started from the
terminal or the web interface profiles the flow's own Python code.

**5.2.10** `profile_environment` MUST be a boolean that says whether such an epic profiles the
programs its agents start.

**5.2.11** `profile_flow` and `profile_environment` MUST be written only as `true`, and any other
value MUST be read as `false`.

**5.2.12** `backup` MUST be a list of backup target names (§9) that an epic of the flow is backed
up to; an empty list MUST mean no target.

**5.2.13** A `backup` that is absent or not a list MUST mean the default targets.

**5.2.14** A name in `backup` that names no backup target MUST be dropped by whoever starts the
epic.

### 5.3 Writing a flow entry

**5.3.1** Saving a flow's setup MUST set the workspace's `flow` and replace the whole flow entry.

**5.3.2** A save MUST always write `agents`.

**5.3.3** A save that gives no value for `envs`, `params`, `budget`, `profile_flow`,
`profile_environment` or `backup` MUST carry that key over from the file as it is at the write.

**5.3.4** A save that gives an empty `envs`, `params` or `budget`, or a `false` profiling switch,
MUST remove that key.

**5.3.5** A save that gives an empty `backup` MUST write an empty list.

### 5.4 Who reads it

**5.4.1** The terminal interface and the web interface MUST read the workspace entry to set up an
epic they start.

**5.4.2** `hmz exec` and the software development kit MUST NOT read `workspaces`.

**5.4.3** The terminal interface MUST use a flow entry to start the flow without asking only where
its agent roles equal the flow's declared agent roles, every required env role has an env spec,
its params validate, and a budget is present for every flow that requires one.

## 6. `fallbacks`

### 6.1 Entries

**6.1.1** `fallbacks` MUST be a list of mappings, each saying where a turn at one place goes when
that place cannot take it (`features/agents.md`).

**6.1.2** `spec` MUST be a string naming the place the entry is written against.

**6.1.3** `to` MUST be a list of places, tried in order once the place of `spec` has failed.

**6.1.4** `tries` MUST be a non-negative integer, the number of times a failed turn is tried again
at the place of `spec` before the next place is taken, defaulting to 0.

**6.1.5** `policy` MUST be one of `none`, `constant`, `linear`, `exponential`,
`exponential-jitter` and `fibonacci`, the wait between those tries, defaulting to
`exponential-jitter`.

**6.1.6** `timeout` MUST be a non-negative number of seconds for which trying again MAY go on, 0
meaning no limit, and defaulting to 0.

### 6.2 Reading and writing

**6.2.1** An entry that is not a mapping, whose `spec` does not name a place of an existing
harness, whose `spec` an earlier entry has, or that has an empty `to` and `tries` of 0 MUST be
ignored when read.

**6.2.2** A place in `to` that cannot be read as a place, equals `spec`, or repeats an earlier
place MUST be ignored when read.

**6.2.3** A `tries` or `timeout` that is not a finite number MUST be read as 0, and a negative one
as 0.

**6.2.4** A write of a fallback MUST be refused where a place cannot be read, where `to` contains
`spec`, or where `to` names one place twice.

## 7. `clis`

### 7.1 Entries

**7.1.1** `clis` MUST be a mapping from the name of a harness a user added to either a list of
strings, the command that starts it, or a mapping with the keys `command`, `hosts` and `state`.

**7.1.2** `command` MUST be a non-empty list of strings, the command that starts the harness,
speaking the Agent Client Protocol.

**7.1.3** `hosts` MUST be a list of hosts the harness MAY reach while a flow's permission cuts the
network.

**7.1.4** `state` MUST be a list of paths the harness MAY write while a flow's permission forbids
writing them.

**7.1.5** An entry whose command is not a non-empty list MUST be ignored when read.

**7.1.6** A write of an added harness MUST keep the `hosts` and `state` the entry already has.

## 8. `runtimes`

### 8.1 Layout

**8.1.1** `runtimes` MUST be a mapping from a backend, one of `ssh`, `docker`, `swarm`,
`apple-container` and `slurm`, to a mapping from a runtime's name to its fields.

**8.1.2** A runtime's name MUST begin with a letter or a digit and consist of letters, digits,
`.`, `_` and `-`.

**8.1.3** A runtime's backend and name MUST be the keys it is written under, whatever its fields
say.

**8.1.4** An entry that is not a mapping, has a field its backend does not have, has a value of the
wrong type or a value §8.2 to §8.7 refuse, or is written under an invalid name MUST be ignored
when read.

**8.1.5** A write of a runtime MUST be refused for any reason for which §8.1.4 ignores one.

**8.1.6** A boolean MUST NOT be accepted where a number is required.

**8.1.7** A number with no fractional part MUST be accepted where an integer is required.

**8.1.8** A runtime written with the field `affinity`, a list, MUST be read as though its
`harness` were the first entry of that list, `self` read as `env`, and as though it had no
`harness` where that list is empty; the next write of it MUST NOT have `affinity`.

### 8.2 Fields of every backend

**8.2.1** `workdir` MUST be a string that is empty, `~`, absolute, or begins with `~/`, and names
the directory an env on the runtime works in when its env spec gives none.

**8.2.2** `fallback` MUST be a list of runtime references, tried in order when the runtime cannot
hold an env; it MUST NOT name the runtime itself, and MUST NOT name one runtime twice.

**8.2.3** The references `docker:local`, `swarm:local` and `apple-container:local` in `fallback`
MUST mean docker's default daemon here, the swarm this machine manages and this Mac's Apple
containers, where no runtime of that backend is written as `local`.

**8.2.4** `harness` MUST be `local`, `env` or a runtime reference, defaulting to `env`, and
names where the harness of an agent whose env is on the runtime runs
(`features/placements.md`).

**8.2.5** `harness` MUST NOT name the runtime itself as a runtime reference.

**8.2.6** `made` MUST be `typed` or, for an ssh runtime alone, `imported`, defaulting to `typed`.

**8.2.7** A string field, and every string element of a list field, MUST NOT contain a line
feed, a carriage return or a NUL.

**8.2.8** `cpus`, `memory` and every `max_` field MUST be non-negative, 0 meaning no limit.

**8.2.9** `memory` MUST be a number of bytes.

### 8.3 `ssh`

**8.3.1** An ssh runtime MUST have a non-empty `host` or a non-empty `alias`.

**8.3.2** `host`, `alias` and `user` MUST each be empty or begin with a letter, a digit or `_` and
consist of letters, digits, `.`, `_`, `%`, `+` and `-`.

**8.3.3** `port` MUST be an integer from 0 to 65535, 0 meaning the ssh configuration's port.

**8.3.4** `identity_file` and `config` MUST be strings with no double quote; `config` names an ssh
configuration file to read in place of the user's own.

**8.3.5** `proxy_jump` MUST be empty or begin with a letter, a digit or `_` and consist of letters,
digits, `.`, `_`, `%`, `+`, `@`, `:`, `,`, `[`, `]` and `-`.

**8.3.6** `options` MUST be a mapping from an ssh keyword, a letter followed by letters and
digits, to a non-empty value with no double quote.

**8.3.7** `options` MUST NOT hold the keyword `F`, nor, in any case, `HostName`, `User`, `Port`,
`IdentityFile` or `ProxyJump`.

### 8.4 `docker`

**8.4.1** `endpoint` MUST be `local`, `unix://<path>`, `tcp://<host>:<port>`,
`ssh://[<user>@]<host>[:<port>]`, `ssh:<name>` naming an ssh runtime, or `context:<name>` naming
a docker context, and MUST default to `local`.

**8.4.2** `tls_dir` MUST be empty unless `endpoint` begins with `tcp://`, and names the directory
holding `ca.pem`, `cert.pem` and `key.pem`.

**8.4.3** `container` MUST be empty or the name or id of a running container, beginning with a
letter or a digit and consisting of letters, digits, `_`, `.` and `-`.

**8.4.4** `exec_user` MUST be empty or `<uid>[:<gid>]` in decimal digits.

**8.4.5** `exec_env` MUST be a list of `<NAME>=<value>`, `<NAME>` beginning with a letter or `_`
and consisting of letters, digits and `_`.

**8.4.6** `exec_wrapper` MUST be a list of non-empty strings, the words of a program every command
in the env's container runs under.

**8.4.7** `image` MUST be empty or contain no white space.

**8.4.8** `runtime` MUST be empty or an OCI runtime name of the form of §8.3.2.

**8.4.9** `run_args` MUST be a list of strings.

**8.4.10** `name_prefix` MUST be empty or begin and end with a letter or a digit, consist of
letters, digits, `_` and `-`, and be at most 54 characters long.

**8.4.11** `cpus` MUST be a number; `memory`, `gpu_memory` and `max_containers` MUST be integers.

**8.4.12** `gpus` MUST be a list of distinct device ids, each beginning with a letter or a digit
and consisting of letters, digits, `_`, `.`, `:` and `-`.

**8.4.13** Where `container` is set, `image`, `runtime`, `run_args`, `name_prefix`, `cpus`,
`memory`, `gpus`, `gpu_memory` and `max_containers` MUST each be empty or 0.

### 8.5 `swarm`

**8.5.1** `endpoint`, `tls_dir`, `image`, `run_args` and `name_prefix` MUST be as §8.4 specifies
for a docker runtime, `endpoint` naming a manager of the swarm.

**8.5.2** `cpus` MUST be a number; `memory` and `max_tasks` MUST be integers.

**8.5.3** `gpu_resource` MUST be empty or a generic resource name beginning with a letter and
consisting of letters, digits, `.`, `_` and `-`.

**8.5.4** `constraints` MUST be a list of `<attribute>==<value>` or `<attribute>!=<value>`,
`<attribute>` beginning with a letter and consisting of letters, digits, `.`, `_`, `/` and `-`.

**8.5.5** `nodes` MUST be a mapping from a node's host name, of the form of §8.3.2, to the name of
an ssh runtime or an ssh destination `[<user>@]<host>[:<port>]`.

**8.5.6** `dial_back` MUST be empty or a host name or IPv4 address, consisting of letters, digits,
`_`, `.` and `-`, at which the swarm's nodes reach this machine (`features/environments.md`
§8.12); empty MUST mean that tasks are reached as §8.10 of that specification states.

### 8.6 `apple-container`

**8.6.1** An Apple container runtime MUST have exactly the fields `image`, `run_args`, `cpus`,
`memory`, `max_containers`, `workdir`, `fallback`, `made` and `harness`, with the types and
validation of §8.2 and §8.4.

### 8.7 `slurm`

**8.7.1** `partition`, `account` and `qos` MUST each be empty or begin with a letter, a digit or
`_` and consist of letters, digits, `.`, `_` and `-`.

**8.7.2** `time` MUST be empty, a number of minutes, `MM:SS`, `HH:MM:SS`, `D-HH[:MM[:SS]]`,
`UNLIMITED` or `INFINITE`.

**8.7.3** `constraint` MUST be empty or contain no white space and not begin with `-`.

**8.7.4** `python` MUST be empty, absolute, or begin with `~/`, and names a Python of at least
version 3.12 on the cluster's nodes.

**8.7.5** `via` MUST be `srun` or `tcp`, defaulting to `srun`.

**8.7.6** `run_args` MUST be a list of strings.

**8.7.7** `cpus` MUST be a number; `memory`, `max_jobs` and `max_wait` MUST be integers,
`max_wait` a number of seconds.

## 9. `backup`

### 9.1 Targets

**9.1.1** `backup` MUST be a mapping with the keys `targets` and `defaults`.

**9.1.2** `backup.targets` MUST be a list of mappings, each one git repository epics are backed up
to (`features/backups.md`).

**9.1.3** A target's `name` MUST match `[A-Za-z0-9][A-Za-z0-9_-]{0,31}` and MUST be unique among
the targets.

**9.1.4** A target's `url` MUST be a non-empty string that git can push to with this machine's own
credentials.

**9.1.5** A target's `branch` MUST be a string, defaulting as `features/backups.md` §3.1.4
states.

**9.1.6** A target's `policies` MUST be a list of distinct values from `session`, `interval` and
`end`, defaulting to the empty list, which means backing up on request alone.

**9.1.7** A target's `every` MUST be the interval of `features/backups.md` §3.1.5 as an integer
number of minutes.

### 9.2 Defaults

**9.2.1** `backup.defaults` MUST be a list of target names, the targets an epic is backed up to
when it is started without naming any.

### 9.3 Reading and writing

**9.3.1** A target that does not validate MUST be ignored when read, and a later target with the
name of an earlier one MUST be ignored.

**9.3.2** A default that names no target MUST be ignored when read.

**9.3.3** A write of `backup` MUST be refused, writing nothing, where a target does not validate,
two targets share a name, or a default names no target.

**9.3.4** Every process that starts an epic MUST read `backup` as the epic starts.

## 10. Account references

### 10.1 Naming an account

**10.1.1** The settings file MUST NOT hold the credentials of any account.

**10.1.2** An account MUST be referred to in the settings file only by its name after an `@` in an
agent spec or a place, in `workspaces.<path>.flows.<flow>.agents`, `btw` and `fallbacks`.

**10.1.3** A reference to an account that does not exist MUST be refused when an epic is started
with it (`api/cli.md §7.7.7`), and MUST NOT make the settings file unreadable.

## 11. Environment variables

### 11.1 Reading

**11.1.1** A variable set to the empty string MUST be treated as unset unless this section says
otherwise.

**11.1.2** Where this section lists `off`, `0` or `no` as values, hmz MUST compare them after
removing surrounding white space and lower-casing letters.

### 11.2 hmz's own variables

**11.2.1** `HUMANIZE_HOME` MUST name the home; a relative value MUST be taken relative to the
current directory.

**11.2.2** `HUMANIZE_DAEMON` MUST act as `features/daemons.md` §4 states.

**11.2.3** `HUMANIZE_NAME` MUST name the user part of a frontend's name (`api/daemon.md` §7.1.5).

**11.2.4** `HUMANIZE_SENTRY` MUST act as the override of `features/telemetry.md` §3.1.

**11.2.5** `HUMANIZE_SESSIONS` set to `off`, `0` or `no` MUST make every harness keep its sessions
in its own home rather than in the epic (`api/files/epics.md`).

**11.2.6** `HUMANIZE_WATCHDOG` MUST act as `features/agents.md` §12.1.3 states.

**11.2.7** `HUMANIZE_PRICES` MUST name the URL, where it contains `://`, or the file from which hmz
refreshes model prices; `off`, `0`, `no`, `none` or the empty string MUST turn refreshing off.

**11.2.8** `HUMANIZE_RELEASES` MUST name the URL, where it contains `://`, or the file from which
hmz learns the newest release; `off`, `0`, `no`, `none` or the empty string MUST turn asking off.

**11.2.9** `HUMANIZE_SHADOWS` MUST name the directory in which hmz keeps the records of mirrors,
defaulting to `~/.cache/humanize/shadows` (`api/files/machine.md`).

**11.2.10** `HUMANIZE_SSH_REUSE` set to `off`, `0`, `no`, `false` or the empty string MUST stop
hmz from sharing one ssh connection between the ssh commands it runs to one destination.

**11.2.11** `HUMANIZE_RENDEZVOUS` MUST name the host or address of the rendezvous broker, and
`HUMANIZE_RENDEZVOUS_PORT` the port of every broker a process starts, the one for the afar
arrangement and the one for each dial-back address (`features/placements.md` §10.23), 0
meaning any free port.

**11.2.12** `HUMANIZE_TARGET`, `HUMANIZE_HARNESS`, `HUMANIZE_SHADOW`, `HUMANIZE_TOKEN` and
`HUMANIZE_LOG` MUST be the defaults of the options of `hmz internal anchor` that
`api/cli.md §11.2.3` names.

### 11.3 Other variables

**11.3.1** `NO_COLOR`, `TERM` and `FORCE_COLOR` MUST decide escapes as `api/cli.md §4.2`
specifies.

**11.3.2** `TEXTUAL_THEME` MUST name the theme of the terminal interface; a name the interface
does not have MUST be ignored.

**11.3.3** `TMUX`, `TERM_PROGRAM` and `LC_TERMINAL` MUST be read as `api/cli.md §6.1.7`
specifies.

**11.3.4** `DISPLAY` and `WAYLAND_DISPLAY` MUST be read as `api/cli.md §8.2.5` specifies.

**11.3.5** `CUDA_VISIBLE_DEVICES` MUST limit the GPUs a local or ssh env reports to those it
lists (`features/environments.md`).

**11.3.6** `TMPDIR` MUST decide this machine's own directory as `api/files/machine.md` specifies.
