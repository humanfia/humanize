# Command line

## 1. Scope

This specification governs the program `hmz`: how a command line is routed to a command, every
command and its options, the grammars of the values `hmz exec` takes, what each command writes to
its standard output and standard error, the rules for colour and for `--json` output, and every
exit status.

Out of scope:

- What the terminal interface does once it is open (`features/tui.md`).
- What the web interface serves (`features/web.md`, `api/http.md`).
- What a flow is and how its params are validated (`api/flows.md`).
- Which harnesses exist, their effort ladders and their accounts (`features/agents.md`,
  `features/accounts.md`).
- Envs, runtimes and fallback between runtimes (`features/environments.md`).
- Where a harness runs and the arrangements of `hmz internal anchor` (`features/placements.md`).
- The record an epic leaves on disk (`api/files/epics.md`).
- Budgets, resuming and stopping an epic as features (`features/epics.md`).
- Backups as a feature (`features/backups.md`) and updates as a feature (`features/updates.md`).
- The settings file and the environment variables hmz reads (`api/settings.md`).

## 2. Definitions

**2.1** A **command line** is the sequence of arguments the operating system hands to `hmz`,
excluding the program name.

**2.2** A **command** is the first argument of a command line where it is one of `exec`, `web`,
`update`, `backup` and `internal`.

**2.3** A **usage error** is a refusal of a command line in which the refusing parser writes its
usage text and the line `<prog>: error: <reason>` to standard error and exits with status 2, where
`<prog>` is `hmz` followed by the command's words.

**2.4** A stream **is a terminal** where the operating system reports it as a terminal device.

**2.5** **Escapes** are terminal control sequences that set colour or style, or move the cursor.

**2.6** An **NDJSON stream** is a byte stream of UTF-8 text in which every line is exactly one
JSON object followed by a line feed.

**2.7** A **diagnostic** is a line `hmz` writes to standard error that is not the answer of a turn
and not part of an NDJSON stream.

**2.8** The **task** is the text an epic started by `hmz exec` is given to carry out.

**2.9** An **item** is one element of the list an occurrence of `-a`, `-e` or `-p` gives, split as
§7.2 specifies.

## 3. Invocation and routing

### 3.1 Program

**3.1.1** hmz MUST install a console script named `hmz`.

**3.1.2** `python -m hmz` MUST behave exactly as `hmz` with the same command line.

### 3.2 Routing

**3.2.1** Where the command line is empty, `hmz` MUST open the terminal interface as §6
specifies.

**3.2.2** Where the command line is exactly `--version`, `hmz` MUST write `hmz <version>` and a
line feed to standard output, `<version>` being the installed version of hmz, and MUST exit with
status 0.

**3.2.3** Where the first argument is a command, `hmz` MUST hand every later argument to that
command unchanged, `--help` and `-h` included.

**3.2.4** Where the first argument is `-h` or `--help` and is not followed by a command, `hmz`
MUST write its help, listing every command with its summary, to standard output and exit with
status 0.

**3.2.5** Where the command line is not empty and its first argument is neither a command,
`--version` alone, `-h` nor `--help`, `hmz` MUST answer with a usage error that names the
commands.

**3.2.6** `hmz` MUST NOT offer a command that opens the terminal interface.

### 3.3 Help

**3.3.1** Every command MUST answer `-h` and `--help` by writing its help to standard output and
exiting with status 0.

**3.3.2** In every help text, the help of an option, the summary of a command, a description and
an epilog MUST each be at most thirty words long.

**3.3.3** The summaries `hmz --help` writes MUST be, in this order:

```text
exec      run an agent flow in this directory
web       open this machine's epics in a browser on it
update    update hmz to its newest release
backup    back epics up to git repositories, or download them
internal  internal commands used by humanize; do not run directly
```

## 4. Output conventions

### 4.1 Streams

**4.1.1** A command MUST write to standard output only what a program reading it is to parse:
help and version text (§3), the answers of turns, an NDJSON stream, the lines §8 to §10 name as
standard output, and what §11 relays or reports to standard output.

**4.1.2** A command MUST write every diagnostic to standard error.

**4.1.3** A command whose standard output is not a terminal MUST NOT write escapes to standard
output.

### 4.2 Colour

**4.2.1** hmz MUST write escapes to a stream only where the first of the following conditions
that holds says so: `NO_COLOR` is set and non-empty, which says no; `TERM` is `dumb`, which says
no; `FORCE_COLOR` is set, non-empty and not `0`, which says yes; the stream is a terminal, which
says yes; otherwise no.

**4.2.2** `FORCE_COLOR` MUST NOT make hmz treat a stream that is not a terminal as a terminal for
any purpose other than writing escapes.

### 4.3 Secrets

**4.3.1** A command MUST NOT write the value of a credential to any stream.

**4.3.2** Where a command writes an account, it MUST write the account's harness, its name and
the names of the environment variables it sets, and MUST NOT write their values.

**4.3.3** Where a command writes a URL, it MUST first remove any user information and any
credential the URL carries.

## 5. Exit statuses

### 5.1 Statuses common to every command

**5.1.1** Every command MUST exit with status 0 where it did what it was asked.

**5.1.2** Every command other than `hmz internal hook` MUST exit with status 2 on a usage error,
and on every refusal this specification assigns status 2.

**5.1.3** A command MUST NOT exit with a status other than 0, 1 and 2, except as §5.2 specifies.

### 5.2 Statuses particular to commands

**5.2.1** `hmz exec` MUST exit with status 128 plus the signal number where a signal stopped its
epic, as §7.15 specifies.

**5.2.2** `hmz internal anchor`, `hmz internal cred` and `hmz internal fence` MUST exit with the
exit status of the program they ran, where that program ran.

**5.2.3** `hmz internal cli` MUST exit with the status the flow answered, where the flow answered.

**5.2.4** `hmz internal fence` MUST exit with status 126 where the fence cannot be put up.

**5.2.5** `hmz internal anchor` MUST exit with status 127 where `--native` is given and the env
machine has no such harness.

**5.2.6** `hmz internal anchor`, other than its `serve` and `rendezvous` subcommands, MUST exit
with status 130 where it was interrupted.

**5.2.7** `hmz exec` MUST exit with status 130 where it is interrupted before its epic has started
or after it has ended, as §7.15.5 specifies.

**5.2.8** `hmz internal hook` MUST exit with status 1 on a usage error.

## 6. The terminal interface (`hmz` with no command)

### 6.1 Opening

**6.1.1** `hmz` with an empty command line MUST open the terminal interface in the calling process
on the current directory as its workspace, and MUST NOT start an epic.

**6.1.2** Where `HUMANIZE_DAEMON` turns the daemon off (`features/daemons.md` §4), `hmz` MUST
hold the epics in its own process.

**6.1.3** Where standard input or standard output is not a terminal, `hmz` MUST hold the epics in
its own process.

**6.1.4** Otherwise `hmz` MUST open the terminal interface as a frontend of the daemon, starting
the daemon where none runs (`features/daemons.md`).

**6.1.5** Where the daemon cannot be reached or started for a reason other than §6.1.6, `hmz` MUST
write `hmz: runs cannot be detached from the terminal (<reason>), so they will run in this process
instead` to standard error and MUST hold the epics in its own process.

**6.1.6** Where this machine's epics are held by a daemon of an older, incompatible hmz, `hmz`
MUST write a diagnostic beginning `hmz: ` that names that daemon's process id, MUST NOT open the
interface, and MUST exit with status 1.

**6.1.7** Before the terminal interface starts, where `TMUX` is unset or empty and either
`TERM_PROGRAM` is `iTerm.app` or `LC_TERMINAL` is `iTerm2`, `hmz` MUST set
`TEXTUAL_DISABLE_KITTY_KEY=1` in its own environment unless that variable is already set.

### 6.2 Closing

**6.2.1** Once the interface is closed, where backups this process started have not finished,
`hmz` MUST write `hmz: backing epics up` to standard error and wait for them for at most 15
seconds.

**6.2.2** Where a backup has not finished after that wait, `hmz` MUST write
``hmz: a backup took longer than 15s and was left; `hmz backup EPIC` sends it again`` to standard
error and exit.

**6.2.3** `hmz` MUST exit with status 0 where the interface closed normally.

**6.2.4** `hmz` MUST exit with status 1 where the daemon let go of the interface first.

## 7. `hmz exec`

### 7.1 Synopsis

```text
hmz exec -f <ref> [-a <agents>]... [-e <envs>]... [-p <params>]...
         [--profile-flow] [--profile-environment] [--resume] [--json]
         [--backup <target>]... [--carry-on <key>=<conversation>]... [--] <task>
```

**7.1.1** `hmz exec` MUST run the flow `<ref>` names, in the current directory as its workspace,
to its return, as one new epic, with no interface.

**7.1.2** `-f` and `--flow` MUST be the same option; it MUST be given; where it is given more than
once, the last occurrence MUST be the one used.

**7.1.3** `-a` and `--agents`, `-e` and `--envs`, and `-p` and `--params` MUST each be the same
option, and each MUST be accepted any number of times.

**7.1.4** `--profile-flow`, `--profile-environment`, `--resume` and `--json` MUST each be a flag
that takes no value.

**7.1.5** `--backup` and `--carry-on` MUST each be accepted any number of times.

**7.1.6** `<task>` MUST be exactly one positional argument; a task that begins with `-` MUST be
given after `--`.

**7.1.7** Options MUST be accepted in any order, before or after `<task>`.

**7.1.8** An option of `hmz exec` MUST NOT have an equivalent environment variable.

### 7.2 Items

**7.2.1** Each occurrence of `-a`, `-e` or `-p` MUST be split into items at every `,` that is
followed, after optional white space, by a `<key>` of §7.6, optionally preceded by `budget.`, and
then `=`; every other `,` MUST belong to the item that contains it.

**7.2.2** The items of every occurrence of one option MUST form one list, in the order written.

**7.2.3** An item that is empty or consists only of white space MUST be a usage error.

**7.2.4** White space around an `-a` item and around an `-e` item MUST be ignored.

> Informative: `-a x=claude/m,y=codex/n` and `-a x=claude/m -a y=codex/n` are the same line;
> `-p tags=a,b,c` is one item, and no value can contain `,<key>=`.

### 7.3 Naming a flow

```abnf
ref        = name [ ":" inner ] / path / vcs
name       = [ "@" flowverse "/" ] [ owner "/" ] flow
flowverse  = word
owner      = part
flow       = part
inner      = identifier
path       = ( "." / "/" / "~" ) *VCHAR
vcs        = "git+" url [ "@" rev ] [ "#" subdir ] [ ":" inner ]
subdir     = part *( "/" part )
word       = ( ALPHA / DIGIT ) *( ALPHA / DIGIT / "." / "_" / "-" )
part       = <one or more characters, neither "/" nor ":", not beginning with ".">
identifier = <a Python identifier>
url        = <a URL with scheme https, http, ssh, file or git, naming a repository>
rev        = <a git revision>
```

**7.3.1** A `<ref>` MUST be read as a `vcs` where it begins with `git+` or contains `#`, as a
`path` where it begins with `.`, `/` or `~`, and as a `name` otherwise.

**7.3.2** A `name` with no `@<flowverse>/` MUST name a flow of the flowverse `official`.

**7.3.3** A `name` with a `<flowverse>` of `local` or `user` MUST NOT have an `<owner>`.

**7.3.4** `@local/<flow>` MUST name the flow `<flow>` in the directory `.hmz/flows` of the
workspace, and `@user/<flow>` the flow `<flow>` in `~/.hmz/flows`.

**7.3.5** A bare `<flow>` MUST resolve to the first flow of that name found by looking, in order,
in `local`, `user`, `official` and then every other flowverse (`api/flows.md`).

**7.3.6** `:<inner>` MUST name another flow defined in the same module as the flow before it.

**7.3.7** A `vcs` ref MUST name the flow in the directory `<subdir>` of the repository at `<url>`
checked out at `<rev>`, the repository's root where `#<subdir>` is absent and its default branch
where `@<rev>` is absent.

**7.3.8** `hmz exec` MUST NOT install a flow; a flow a flowverse lists but that is not installed
MUST be refused, naming the flowverse it is to be installed from.

**7.3.9** A name written as `local/<flow>`, `user/<flow>`, `official/<flow>` or
`<flowverse>/<flow>` for an existing flowverse MUST be refused with a message that gives the name
as it is written now.

**7.3.10** A relative path written without its leading `./` MUST be refused with a message that
gives it with its `./`.

### 7.4 Writing an agent

```abnf
agent   = role "=" harness [ "@" account ] "/" model [ ":" effort ]
role    = identifier
harness = <a harness name or alias, or the name of a harness added under clis>
account = 1*<character other than "/">
model   = 1*<character>
effort  = [ letters *( ( "-" / "_" / SP ) letters ) ]
letters = 1*ALPHA
```

**7.4.1** `hmz exec` MUST read an `-a` item by splitting it at its first `=` into `<role>` and the
rest; an item with no `=` or with an empty `<role>` MUST be a usage error.

**7.4.2** `<role>` MUST be a Python identifier.

**7.4.3** The rest of an `-a` item MUST NOT contain `,`.

**7.4.4** `hmz exec` MUST take `<harness>`, and the `@<account>` that follows it, from the text
before the first `/` of the rest, splitting that text at its first `@`.

**7.4.5** An `@` followed by nothing before the `/` MUST be a usage error.

**7.4.6** Where the text after the first `/` contains `:` and the text after its last `:` is empty
or matches `<effort>`, `hmz exec` MUST take that text as `<effort>` and the text before that `:` as
`<model>`; otherwise the whole text after the first `/` MUST be `<model>` and the effort MUST be
none.

**7.4.7** `<model>` MUST NOT be empty, and MUST be passed to the harness unchecked.

**7.4.8** An effort that is empty, absent or `auto` MUST mean the harness's own default.

**7.4.9** Any other effort MUST be on the harness's ladder (`features/agents.md`); an effort off
the ladder MUST be refused under §7.7.

**7.4.10** An `-a` item without `@<account>` MUST run the harness as the harness machine's own
login.

**7.4.11** A `<harness>` that names no harness MUST be a usage error.

**7.4.12** A `<role>` given twice across every `-a` MUST be a usage error.

> Informative: `coder=claude/claude-opus-5:high`, `rev=codex@work/gpt-5:medium`,
> `m=opencode/openrouter/qwen3:8b` (the model is `openrouter/qwen3:8b`, no effort), and
> `m=opencode/ollama/qwen3:latest:auto` (the model is `ollama/qwen3:latest`).

### 7.5 Writing an env

```abnf
env       = role "=" backend [ "@" provider ] [ workdir ]
backend   = "local" / "ssh" / "docker" / "swarm" / "apple-container" / "slurm"
provider  = runtime / "[" host "]"
runtime   = word
host      = [ login "@" ] hostname [ ":" 1*5DIGIT ]
login     = ( ALPHA / DIGIT / "_" ) *( ALPHA / DIGIT / "." / "_" / "%" / "+" / "-" )
hostname  = ( ALPHA / DIGIT / "_" ) *( ALPHA / DIGIT / "." / "_" / "-" )
workdir   = "/" *VCHAR
```

**7.5.1** `hmz exec` MUST read an `-e` item as `<role>`, `=`, `<backend>` up to the first `@` or
`/`, `@<provider>` where an `@` follows, and `<workdir>` from the first `/` after the provider;
an item that cannot be read so MUST be a usage error.

**7.5.2** `<role>` MUST be a Python identifier.

**7.5.3** `<backend>` MUST be one of the six values of the grammar.

**7.5.4** `local` MUST NOT take a provider.

**7.5.5** `ssh` MUST take a provider.

**7.5.6** A `<runtime>` MUST name a runtime written in the settings file for that backend
(`api/settings.md §8`); a name no runtime of that backend is written under MUST be refused.

**7.5.7** A bracketed `<host>` MUST be accepted for `ssh` alone, MUST be handed to `ssh` as
written, and MUST NOT name a written runtime.

**7.5.8** For `docker`, `swarm`, `apple-container` and `slurm`, the absence of a provider MUST
mean this machine: docker's default daemon here, the swarm this machine manages, this Mac's Apple
containers, and the Slurm cluster this machine submits to, respectively.

**7.5.9** An `@` followed by no provider MUST be a usage error.

**7.5.10** `<workdir>` MAY be omitted only where the provider names a runtime written with a
workdir, in which case that workdir MUST be used.

**7.5.11** A `<workdir>` of `/~` or beginning `/~/` MUST name a directory relative to the home
directory of the login on the env machine.

**7.5.12** A `<role>` given twice across every `-e` MUST be a usage error.

**7.5.13** `local@<anything>`, `docker@local`, `swarm@local`, `apple-container@local` and
`slurm@local` where no runtime of that backend is written as `local`, and an unbracketed ssh
destination that names no written runtime, MUST each be a usage error whose message gives the
item as it is written now.

> Informative: `repo=local/home/me/repo`, `repo=ssh@gpu-box/~/repo`, `repo=ssh@gpu-box` (the
> workdir `gpu-box` was written with), `repo=ssh@[me@far.host:2222]/srv/repo`,
> `box=docker/srv/repo`, `box=docker@gpubox/srv/repo`.

### 7.6 Writing params and a budget

```abnf
param    = key "=" value / limit
key      = ( ALPHA / "_" ) *( wordchar / "-" )
wordchar = <a character Python's regular expressions match as \w>
value    = *<character>
limit    = "budget." ( "duration" / "cost" / "output_tokens" / "graceful" ) "=" value
```

**7.6.1** A `-p` item that is not `<key>=<value>` or `budget.<name>=<value>` MUST be a usage error.

**7.6.2** A key MUST be given at most once across every `-p`.

**7.6.3** `<value>` MUST be everything after the first `=`, unchanged.

**7.6.4** `hmz exec` MUST hand every param that is not a `budget.` limit to the flow's params
model (`api/flows.md`); a param the model refuses MUST be refused under §7.7.

**7.6.5** `budget` with no limit MUST be a usage error.

**7.6.6** `budget.<name>` with a `<name>` other than `duration`, `cost`, `output_tokens` and
`graceful` MUST be a usage error.

**7.6.7** `budget.duration` MUST accept a non-negative finite number of seconds; a concatenation
of numbers each followed by one of the units `w`, `d`, `h`, `m` and `s`, each unit at most once;
an ISO 8601 duration; or `HH:MM:SS`.

**7.6.8** `budget.cost` MUST accept a non-negative number of US dollars, optionally preceded by
`$`, or `inf` for no limit.

**7.6.9** `budget.output_tokens` MUST accept a whole number, optionally written with `_`, or a
decimal number followed by `k` (thousands) or `m` (millions) that comes to a whole number.

**7.6.10** `budget.graceful` MUST accept `1`, `true`, `yes` and `on` as true and `0`, `false`,
`no` and `off` as false, in any case.

**7.6.11** A limit value that §7.6.7 to §7.6.10 do not accept MUST be a usage error.

**7.6.12** A budget that sets none of `duration`, `cost` and `output_tokens` MUST be a usage
error.

**7.6.13** A line with no `budget.` limit MUST be refused under §7.7 for every flow but `chat`,
which MUST then run with no cost limit.

### 7.7 Refusals before the epic starts

**7.7.1** Every refusal of a well-formed line MUST be written to standard error as
`hmz exec: error: <reason>`, MUST exit with status 2, and MUST happen before any agent has started.

**7.7.2** `hmz exec` MUST refuse a flow that cannot be found or loaded.

**7.7.3** `hmz exec` MUST refuse an agent or env role the flow does not declare, naming the roles
it declares.

**7.7.4** `hmz exec` MUST refuse a role the flow fills itself.

**7.7.5** `hmz exec` MUST refuse a line that leaves a required role unfilled, naming the role.

**7.7.6** `hmz exec` MUST refuse an agent whose harness is not the harness its role requires, or
lacks a capability its role requires.

**7.7.7** `hmz exec` MUST refuse an `@<account>` that names no account of that harness.

**7.7.8** `hmz exec` MUST refuse params the flow's params model refuses, with the model's reason.

**7.7.9** `hmz exec` MUST refuse a `--resume` that §7.9 cannot satisfy.

**7.7.10** `hmz exec` MUST refuse a `--backup` naming no backup target in the settings file.

**7.7.11** `hmz exec` MUST refuse an env that cannot be reached, or whose machine has fewer
resources than its role declares, naming the role, once every runtime fallback
(`features/environments.md`) has been tried.

**7.7.12** `hmz exec` MUST refuse a line where an agent's harness cannot run where the
harness setting of its env's runtime says (`features/placements.md`).

**7.7.13** `hmz exec` MUST refuse a skill a role names that cannot be found or fetched.

**7.7.14** `hmz exec` MUST refuse a `--carry-on` that §7.9.7 or `features/epics.md` §3.8.7
refuses.

> Informative: `hmz exec: error: aot needs an agent for 'coder'; specify each with -a
> ROLE=CLI/MODEL:EFFORT`; `hmz exec: error: aot requires a budget: specify with -p
> budget.cost=...,budget.duration=...,budget.output_tokens=...`.

### 7.8 Where a harness runs

**7.8.1** An option of `hmz exec` MUST NOT say where a harness runs.

**7.8.2** Where each harness runs MUST be decided as `features/placements.md` specifies.

**7.8.3** Where an env moves to a fallback runtime, `hmz exec` MUST write
`hmz exec: <runtime> cannot hold '<role>': <reason>; using <runtime>` to standard error, each
`<runtime>` written as `<backend>:<name>`.

### 7.9 Resuming and carrying on

```abnf
carry-on     = key "=" conversation
key          = 1*( %x21-3C / %x3E-7E )
conversation = epic "/" agent "/" n
epic         = <an epic name, or the path of an epic directory>
agent        = 1*( %x21-2E / %x30-7E )
n            = %x31-39 *DIGIT
```

**7.9.1** With `--resume`, `hmz exec` MUST pick up the newest epic of the same flow in this
workspace that saved progress and is not still running (`features/epics.md`).

**7.9.2** With `--resume`, `hmz exec` MUST refuse a flow that cannot be resumed, and a flow with
no epic in this workspace that can be picked up.

**7.9.3** Without `--resume`, every epic MUST start from the beginning.

**7.9.4** Each `--carry-on <key>=<conversation>` MUST carry a conversation on in the epic
`hmz exec` starts, as `features/epics.md` §3.8 specifies, `<epic>`, `<agent>` and `<n>` naming
its source and session (§3.8.2 there) and `<key>` its state key (§3.8.5 there).

**7.9.5** `hmz exec` MUST read `<agent>` and `<n>` from after the last two `/` of a
`<conversation>`, and `<epic>` from before them.

**7.9.6** A `--carry-on` without `=`, with a `<key>` that does not match `key`, or naming a
`<key>` an earlier `--carry-on` of the line names MUST be a usage error.

**7.9.7** `hmz exec` MUST refuse a `--carry-on` whose `<conversation>` does not match
`conversation`, before the epic starts.

**7.9.8** `--carry-on` MAY be given together with `--resume` (`features/epics.md` §3.8.10).

> Informative: `hmz exec -f prove --carry-on session=20261016T120000.000Z-a1b2c3/Ada/1 -- go on`
> starts a new epic whose flow reads `ctx.state["session"]` as a session that carries on Ada's
> first conversation of that epic.

### 7.10 Profiling

**7.10.1** `--profile-flow` MUST profile the flow's own Python code for the epic
(`features/monitoring.md`).

**7.10.2** `--profile-environment` MUST profile the programs the epic's agents start.

**7.10.3** Without the corresponding flag, `hmz exec` MUST NOT profile either, whatever the
settings file holds.

### 7.11 Backups

**7.11.1** `--backup <target>` MUST name a backup target the epic is backed up to; with several,
the epic MUST go to each.

**7.11.2** `--backup none` MUST mean no backup target; `none` together with any other target MUST
be a usage error.

**7.11.3** Without `--backup`, the epic MUST go to the default targets of the settings file
(`api/settings.md §9`).

**7.11.4** Once the epic has ended and its backups have not all finished, `hmz exec` MUST write
`hmz exec: backing the epic up` to standard error and wait for them for at most 60 seconds.

**7.11.5** Where a backup has not finished after that wait, `hmz exec` MUST write
``hmz exec: a backup took longer than 60s and was left; `hmz backup EPIC` sends it again`` to
standard error, and MUST exit as the epic had it.

### 7.12 Output for a person

**7.12.1** Without `--json`, `hmz exec` MUST draw the epic from the event stream of its agents
(`features/agents.md`) on standard error, one line or block per event.

**7.12.2** Each event line MUST say which agent it is about, and, where that agent holds two or
more sessions, which session.

**7.12.3** A turn's `result` MUST be followed on standard error by a line of what the turn cost in
tokens by kind and, where the model has a known price, in US dollars.

**7.12.4** A turn's answer MUST be written to standard output followed by a line feed, unless both
standard output and standard error are terminals.

**7.12.5** A turn whose answer is empty MUST write nothing to standard output.

**7.12.6** Where standard error is a terminal and escapes are allowed (§4.2), `hmz exec` MUST
draw a clock at the foot of the output that says which agent is working, or how many turns are
working, and for how many seconds.

**7.12.7** Where a cost limit applies to a model with no known price, `hmz exec` MUST write
`hmz exec: nobody lists a price for <model>[, <model>...], so cost=<limit> cannot stop what it
spends` to standard error before the flow is called, and MUST run the epic.

**7.12.8** Where the epic's budget stopped it, `hmz exec` MUST write `hmz exec: stopped --
<reason>` to standard error and MUST exit with status 0.

**7.12.9** Where the flow raises any other exception, `hmz exec` MUST write its traceback to
standard error and exit with status 1.

### 7.13 `--json`

**7.13.1** With `--json`, `hmz exec` MUST write an NDJSON stream to standard output, one object
per event, each flushed as it is written.

**7.13.2** With `--json`, `hmz exec` MUST write nothing else to standard output, and MUST send to
standard error anything the flow or a layer under it writes to standard output.

**7.13.3** Every object MUST carry exactly the keys of the following table, every time:

```text
key      type    value
at       number  Unix time the event was recorded
agent    string  the agent's own name, never the role it fills
cli      string  the harness
model    string  the model the agent was configured with
session  string  the harness's own id for the session; "" before it has one, and for an
                 event not about one session
kind     string  begins, ends, text, reasoning, tool, subagent, subagent-ends, asks,
                 took, notice, failed or result
text     string  the event's words
whose    string  for subagent and subagent-ends, the harness's id for the subagent; else ""
tokens   object  on result, tokens by model where the harness reports them; else {}
spent    object  on result, tokens by kind where the harness reports them; else {}
```

**7.13.4** The meaning of each `kind` MUST be as `features/agents.md` defines it.

### 7.14 Nobody at the prompt

**7.14.1** An epic `hmz exec` starts MUST have its outworlder away for its whole length
(`api/flows.md`): a question the flow asks MUST be answered at once as the flow API specifies for
an away outworlder.

**7.14.2** An `asks` event MUST still be written.

### 7.15 Signals

**7.15.1** On `SIGINT`, `SIGTERM` or `SIGHUP`, `hmz exec` MUST stop its epic, MUST wait until the
epic has released everything it created, and MUST then exit with status 128 plus the number of
the first signal received.

**7.15.2** A signal whose disposition was set to ignore when `hmz exec` started MUST remain
ignored.

**7.15.3** A second `SIGTERM` or `SIGHUP` while the epic stops MUST be ignored.

**7.15.4** A second `SIGINT` while the epic stops MUST end the process at once by `SIGINT`.

**7.15.5** An interrupt that arrives before the epic has started or after it has ended MUST exit
with status 130 without writing a traceback.

## 8. `hmz web`

### 8.1 Synopsis

```text
hmz web [--port <port>] [--no-open] [--attached]
```

**8.1.1** `--port` MUST take an integer from 0 to 65535; any other value MUST be a usage error.

**8.1.2** `--port` MUST default to 0, which MUST mean any free port.

### 8.2 Behaviour

**8.2.1** `hmz web` MUST serve the web interface (`features/web.md`) of every workspace of this
machine until it is stopped, offering the current directory first for a new epic.

**8.2.2** `hmz web` MUST listen on `127.0.0.1` and, where this machine has IPv6, on `::1`, on the
same port, and on no other address.

**8.2.3** `hmz web` MUST hold the epics in its own process where `HUMANIZE_DAEMON` is `off`, `0`
or `no`, and through the daemon otherwise.

**8.2.4** Once listening, `hmz web` MUST write `hmz web: http://127.0.0.1:<port>/?key=<key>` and a
line feed to standard output and flush it.

**8.2.5** Unless `--no-open` is given, `hmz web` MUST open that address in a browser where this
machine is a Mac or `DISPLAY` or `WAYLAND_DISPLAY` is set, and MUST NOT open a browser otherwise.

**8.2.6** `hmz web` MUST stop on `SIGINT`, `SIGTERM` or `SIGHUP`, and, with `--attached`, when its
standard input reaches its end or cannot be read.

**8.2.7** Stopping `hmz web` MUST NOT stop any epic the daemon holds.

### 8.3 Exit

**8.3.1** `hmz web` MUST exit with status 0 once stopped as §8.2.6 specifies.

**8.3.2** Where this machine's epics are held by a daemon of an older, incompatible hmz, `hmz web`
MUST write a diagnostic beginning `hmz: ` and exit with status 1.

**8.3.3** Where the epics cannot be reached or the port cannot be listened on, `hmz web` MUST
write `hmz: the web interface cannot be served: <reason>` to standard error and exit with
status 1.

## 9. `hmz update`

### 9.1 Synopsis

```text
hmz update
```

**9.1.1** `hmz update` MUST take no argument.

### 9.2 Choosing the installer

**9.2.1** Where hmz is not installed as a distribution, `hmz update` MUST write
`hmz update: hmz is not installed here, only run from its source` to standard error and exit with
status 1.

**9.2.2** Where hmz was installed from a URL or a local directory, `hmz update` MUST write
`hmz update: hmz was installed from <url>, not PyPI; update it there` to standard error, `<url>`
written as §4.3.3 requires, and exit with status 1.

**9.2.3** Where hmz was installed by `uv tool`, `hmz update` MUST run `uv tool upgrade hmz`.

**9.2.4** Where hmz was installed by `pipx`, `hmz update` MUST run `pipx upgrade hmz`.

**9.2.5** Otherwise, where pip is importable by the interpreter running hmz, `hmz update` MUST run
`<python> -m pip install --upgrade hmz[<extras>]`, and where it is not, `uv pip install --python
<python> --upgrade hmz[<extras>]`, `<python>` being that interpreter and `<extras>` every extra of
hmz whose packages are all installed, the brackets omitted where there is none.

**9.2.6** Where the installer §9.2.3 to §9.2.5 chose is `uv` or `pipx` and is not on `PATH`,
`hmz update` MUST write `hmz update: <installer> installed hmz but is not on PATH` to standard
error and exit with status 1.

### 9.3 Updating

**9.3.1** After §9.2, `hmz update` MUST ask PyPI, or the source `HUMANIZE_RELEASES` names, for the
newest release of hmz, excluding pre-releases.

**9.3.2** Where no answer comes, `hmz update` MUST write `hmz update: PyPI could not be asked for
the newest release` to standard error and exit with status 1.

**9.3.3** Where the running version is the newest or newer, `hmz update` MUST write
`hmz <version> is the newest release` to standard output, run nothing, and exit with status 0.

**9.3.4** Otherwise `hmz update` MUST write `Updating hmz <old> to <new>: <command>` to standard
output and then run the installer, letting it write to the same streams.

**9.3.5** Where the installer exits with a non-zero status, `hmz update` MUST write
`hmz update: <installer> exited <status>` to standard error and exit with status 1.

**9.3.6** Where the version installed afterwards is not the newest release, `hmz update` MUST
write `hmz update: <installer> left hmz at <version>, not <new>` to standard error and exit with
status 1.

**9.3.7** Otherwise `hmz update` MUST write `Updated hmz to <new>` to standard output and exit
with status 0.

**9.3.8** Where a daemon runs on this machine, `hmz update` MUST make the statement of
`features/updates.md` §4.4.2 by writing `Epics held on this machine (pid <pid>) run hmz <old> until
that daemon stops` to standard output after §9.3.7.

## 10. `hmz backup`

### 10.1 Synopsis

```text
hmz backup [--to <target>]... <epic>
hmz backup --list [--to <target>]...
hmz backup --pull <epic> [--to <target>]...
```

**10.1.1** `--list` and `--pull` MUST be mutually exclusive.

**10.1.2** A positional `<epic>` together with `--list` or `--pull` MUST be a usage error.

**10.1.3** A line with neither `--list`, `--pull` nor a positional `<epic>` MUST be a usage error.

**10.1.4** `--to` MUST name a backup target of the settings file, and MUST be accepted any number
of times.

### 10.2 Backing an epic up

**10.2.1** `hmz backup <epic>` MUST back up the epic of the current workspace whose name is
`<epic>`, or, where none is, the epic at the path `<epic>`.

**10.2.2** The epic MUST go to the targets `--to` names; without `--to`, to the targets the epic
was started with; and where it was started with none, to the default targets.

**10.2.3** An epic that does not exist, a `--to` naming no target, and a line that leaves no
target at all MUST each be a usage error.

**10.2.4** `hmz backup` MUST wait for every backup it started to finish.

**10.2.5** For each target that took the epic, `hmz backup` MUST write
`<target>: backed up to <url>` to standard output.

**10.2.6** For each target that did not, `hmz backup` MUST write `<target>: failed: <reason>` to
standard error.

**10.2.7** `hmz backup` MUST exit with status 0 where every target took the epic, and with status 1
otherwise.

### 10.3 Listing

**10.3.1** `hmz backup --list` MUST read each target `--to` names, or every target without
`--to`, after fetching it.

**10.3.2** For each target read, `hmz backup --list` MUST write `<target>: <n> epic` or
`<target>: <n> epics` to standard output, `epic` where `<n>` is 1, followed by one line per epic
the target holds: two spaces, then its machine, workspace, epic name, how it ended or
`unfinished`, and its task with white space runs collapsed and cut to 60 characters, separated by
two spaces.

**10.3.3** For a target that cannot be read, `hmz backup --list` MUST write
`<target>: failed: <reason>` to standard error, MUST go on to the next target, and MUST exit with
status 1.

### 10.4 Downloading

**10.4.1** `<epic>` after `--pull` MUST be an epic's name or `<machine>/<workspace>/<name>`.

**10.4.2** `hmz backup --pull` MUST download the epic from the first target that holds it, in
the order of §10.3.1, into this machine's epics as an import (`features/backups.md`).

**10.4.3** Once it has downloaded the epic, `hmz backup --pull` MUST write the path the epic now
has to standard output.

**10.4.4** `hmz backup --pull` MUST exit with status 0 once it has downloaded the epic.

**10.4.5** Where a target holds epics of that name from more than one machine, `hmz backup --pull`
MUST answer with a usage error that lists each as `<machine>/<workspace>/<name>`.

**10.4.6** Where the epic is already on this machine, `hmz backup --pull` MUST write a diagnostic
beginning `hmz backup: ` and exit with status 1.

**10.4.7** Where every target answered and none holds the epic, `hmz backup --pull` MUST answer
with a usage error.

**10.4.8** Where a target could not be read and no other held the epic, `hmz backup --pull` MUST
write `hmz backup: no target that answered holds <epic>` to standard error and exit with status 1.

## 11. `hmz internal`

### 11.1 Status

**11.1.1** The commands under `hmz internal` MUST be the command lines hmz starts its own
processes with, and MUST NOT be a public interface of hmz.

**11.1.2** The help of `hmz internal`, and of each of its commands, MUST say that the command is
not to be run directly.

**11.1.3** Each `hmz internal` command MUST run when a user types it.

**11.1.4** `hmz internal` with no command, or with a command it does not have, MUST be a usage
error that lists its commands.

**11.1.5** `hmz internal` MUST have exactly the commands `anchor`, `cli`, `cred`, `fence`, `hook`
and `tools`, with the summaries:

```text
anchor  run an agent turn on another machine
cli     relay agent runs of a flow's command line to the flow
cred    run a program with credentials from an account
fence   run a program held to what its flow permits
hook    relay agent hooks to a flow
tools   relay agent tool calls to a flow
```

**11.1.6** `hmz internal anchor` MUST NOT load any part of hmz but the part that drives
harnesses.

### 11.2 `hmz internal anchor`

```text
hmz internal anchor [<options>] <program> [<args>...]
hmz internal anchor serve --export <virtual>[:<real>]... (--stdio | --listen [<host>:]<port>
                          | --peer <ticket>@<host>:<port>) [--token <secret>]
                          [--log-level <level>]
hmz internal anchor rendezvous [--listen [<host>:]<port>] [--punching <seconds>]
                               [--log-level <level>]
```

**11.2.1** `hmz internal anchor` MUST run `<program>` with its work landing on the machine
`--target` names, in the arrangement `features/placements.md` specifies.

**11.2.2** `hmz internal anchor` MUST accept the options `--target`, `--harness`, `--broker`,
`--workspace`, `--chdir`, `--remote-path`, `--shadow`, `--local-path`, `--local-exec`,
`--redirect`, `--private`, `--net`, `--net-allow`, `--token`, `--token-file`, `--force`,
`--native`, `--hush`, `--project`, `--carry`, `--bring`, `--tell`, `--installs`, `--fence`,
`--check` and `--log-level`, whose meanings `features/placements.md` specifies.

**11.2.3** `--target` MUST default to `HUMANIZE_TARGET`, else `local`; `--harness` to
`HUMANIZE_HARNESS`, else `local`; `--broker` to `HUMANIZE_RENDEZVOUS`; `--shadow` to
`HUMANIZE_SHADOW`, else `--workspace`; `--token` to `HUMANIZE_TOKEN`; and `--log-level` to
`HUMANIZE_LOG`, else `warning`.

**11.2.4** hmz MUST pass a secret to a process it starts with `--token-file`, never with
`--token`.

**11.2.5** `hmz internal anchor` with neither a program nor `--check` MUST exit with status 2.

**11.2.6** `hmz internal anchor` MUST exit with status 1, writing `hmz: <reason>` to standard
error, on a connection, protocol, operating-system or value error.

**11.2.7** `hmz internal anchor serve` MUST require at least one `--export` and exactly one of
`--stdio`, `--listen` and `--peer`.

**11.2.8** `hmz internal anchor serve --listen` on an address other than `127.0.0.1`, `::1` and
`localhost` without a token MUST write `hmz: cannot listen on a non-loopback address without
--token` to standard error and exit with status 2.

**11.2.9** `hmz internal anchor serve` MUST refuse a client that presents a token other than its
own.

**11.2.10** `hmz internal anchor rendezvous` MUST write `hmz internal anchor rendezvous listening
<bound> <landed>` to standard error once listening, MUST default `--listen` to `0.0.0.0:0` and
`--punching` to 4 seconds, and MUST exit with status 2 on a malformed address and status 1 where
it cannot listen.

**11.2.11** Where `HUMANIZE_LOG` holds a value other than `debug`, `info`, `warning` and `error`,
in any case and with surrounding white space removed, these three commands MUST write `hmz:
ignoring HUMANIZE_LOG='<value>', which is not one of debug, info, warning, error` to standard
error and log at their default level.

### 11.3 `hmz internal cred`

```text
hmz internal cred (--map <from>=<to> | --keep <from>=<to>)... [--] <program> [<args>...]
```

**11.3.1** `hmz internal cred` MUST run `<program>` with every access to the absolute path
`<from>`, or to anything under it, answered from `<to>`.

**11.3.2** `--keep` MUST answer as `--map` does, MUST create what the program writes, and MUST
accept a glob in any component of `<from>`.

**11.3.3** `hmz internal cred` with no program, with no `--map` and no `--keep`, or with a
malformed mapping MUST exit with status 2.

**11.3.4** Where the program cannot be supervised, `hmz internal cred` MUST write
`hmz internal cred: <reason>` to standard error, MUST exit with status 1, and MUST NOT run the
program.

### 11.4 `hmz internal fence`

```text
hmz internal fence --policy (<json> | @<path>) [--] <program> [<args>...]
```

**11.4.1** `hmz internal fence` MUST run `<program>` held to the paths and hosts the policy
permits (`features/agents.md`).

**11.4.2** `hmz internal fence` with no `--policy` or no program MUST exit with status 2.

**11.4.3** Where the fence cannot be put up on this machine, `hmz internal fence` MUST write
`hmz internal fence: <reason>` to standard error, MUST exit with status 126, and MUST NOT run the
program.

### 11.5 `hmz internal hook`

```text
hmz internal hook --at <socket>
```

**11.5.1** `hmz internal hook` MUST read one hook call as JSON from standard input, send it on
one line to the Unix socket `<socket>`, and write the one line answered to standard output.

**11.5.2** `hmz internal hook` MUST exit with status 0 once it has read its input, whatever the
answer, and where the socket cannot be reached or closes without answering.

**11.5.3** Where the socket cannot be reached, `hmz internal hook` MUST write
`hmz internal hook: <socket>: <reason>` to standard error and write nothing to standard output.

**11.5.4** `hmz internal hook` MUST NOT exit with status 2, and MUST exit with status 1 where its
command line cannot be read.

### 11.6 `hmz internal tools`

```text
hmz internal tools --at <socket>
```

**11.6.1** `hmz internal tools` MUST carry bytes in both directions at once between its standard
streams and the Unix socket `<socket>`, and the end of either direction MUST end the other.

**11.6.2** `hmz internal tools` MUST exit with status 0 once either end has closed, with status 1
where the socket cannot be reached, and with status 2 without `--at`.

### 11.7 `hmz internal cli`

```text
hmz internal cli --at <socket> --name <name> [-- <words>...]
```

**11.7.1** `hmz internal cli` MUST send `{"name": <name>, "argv": <words>}` on one line to the
Unix socket `<socket>`, read one line `{"code", "out", "err"}` back, write `out` to standard
output and `err` to standard error, and exit with status `code`.

**11.7.2** `hmz internal cli` MUST pass every word after the first `--` unchanged, and MUST NOT
read standard input.

**11.7.3** Where the socket cannot be reached, `hmz internal cli` MUST write
`<name>: the flow serving it has ended (<reason>)` to standard error and exit with status 1.

**11.7.4** Where no answer comes back, `hmz internal cli` MUST write
`<name>: the flow serving it gave no answer` to standard error and exit with status 1.

**11.7.5** `hmz internal cli` without `--at` or `--name` MUST exit with status 2.

## 12. Environment

### 12.1 Variables

**12.1.1** The commands MUST read the environment variables `api/settings.md §11` lists, with the
meanings given there.

**12.1.2** `hmz exec` MUST NOT read `HUMANIZE_DAEMON`.
