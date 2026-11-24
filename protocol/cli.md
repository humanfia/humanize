# The Humanize Protocol: Command-Line Interface

## Abstract

This document specifies the command-line interface of hmz: every command, its options and their
grammars, what it writes to its standard streams, its help, and its exit statuses; and the command line of
`coganchor`, the program that carries hmz's anchor.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [CLI].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Terminology](#2-terminology)
- [3. Invocation and routing](#3-invocation-and-routing)
  - [3.1. Program](#31-program)
  - [3.2. Routing](#32-routing)
  - [3.3. Help](#33-help)
- [4. Output conventions](#4-output-conventions)
  - [4.1. Streams](#41-streams)
  - [4.2. Colour](#42-colour)
  - [4.3. Secrets](#43-secrets)
- [5. Exit statuses](#5-exit-statuses)
  - [5.1. Statuses common to every command](#51-statuses-common-to-every-command)
  - [5.2. Statuses particular to commands](#52-statuses-particular-to-commands)
- [6. The terminal interface (`hmz` with no command)](#6-the-terminal-interface-hmz-with-no-command)
  - [6.1. Opening](#61-opening)
  - [6.2. Closing](#62-closing)
- [7. `hmz exec`](#7-hmz-exec)
  - [7.1. Synopsis](#71-synopsis)
  - [7.2. Items](#72-items)
  - [7.3. Naming a flow](#73-naming-a-flow)
  - [7.4. Writing an agent](#74-writing-an-agent)
  - [7.5. Writing an env](#75-writing-an-env)
  - [7.6. Writing params and a budget](#76-writing-params-and-a-budget)
  - [7.7. Refusals before the epic starts](#77-refusals-before-the-epic-starts)
  - [7.8. Where a harness runs](#78-where-a-harness-runs)
  - [7.9. Resuming](#79-resuming)
  - [7.10. Profiling](#710-profiling)
  - [7.11. Backups](#711-backups)
  - [7.12. Output for a person](#712-output-for-a-person)
  - [7.13. `--json`](#713---json)
  - [7.14. Nobody at the prompt](#714-nobody-at-the-prompt)
  - [7.15. Signals](#715-signals)
- [8. `hmz web`](#8-hmz-web)
  - [8.1. Synopsis](#81-synopsis)
  - [8.2. Behaviour](#82-behaviour)
  - [8.3. Exit](#83-exit)
- [9. `hmz update`](#9-hmz-update)
  - [9.1. Synopsis](#91-synopsis)
  - [9.2. Choosing the installer](#92-choosing-the-installer)
  - [9.3. Updating](#93-updating)
- [10. `hmz backup`](#10-hmz-backup)
  - [10.1. Synopsis](#101-synopsis)
  - [10.2. Backing an epic up](#102-backing-an-epic-up)
  - [10.3. Listing](#103-listing)
  - [10.4. Downloading](#104-downloading)
- [11. `hmz internal`](#11-hmz-internal)
  - [11.1. Status](#111-status)
  - [11.2. `hmz internal anchor`](#112-hmz-internal-anchor)
  - [11.3. `hmz internal cred`](#113-hmz-internal-cred)
  - [11.4. `hmz internal fence`](#114-hmz-internal-fence)
  - [11.5. `hmz internal hook`](#115-hmz-internal-hook)
  - [11.6. `hmz internal tools`](#116-hmz-internal-tools)
  - [11.7. `hmz internal cli`](#117-hmz-internal-cli)
- [12. Environment](#12-environment)
  - [12.1. Variables](#121-variables)
- [13. `hmz daemon`](#13-hmz-daemon)
  - [13.1. Synopsis](#131-synopsis)
  - [13.2. Behaviour](#132-behaviour)
  - [13.3. Exit](#133-exit)
- [14. `hmz relay`](#14-hmz-relay)
  - [14.1. Synopsis](#141-synopsis)
  - [14.2. Behaviour](#142-behaviour)
  - [14.3. Exit](#143-exit)
- [15. `hmz chat`](#15-hmz-chat)
  - [15.1. Synopsis](#151-synopsis)
  - [15.2. Output](#152-output)
  - [15.3. Exit](#153-exit)
  - [15.4. The chats written down](#154-the-chats-written-down)
- [16. Declared commands](#16-declared-commands)
- [17. `hmz devices`](#17-hmz-devices)
  - [17.1. Synopsis](#171-synopsis)
  - [17.2. Behaviour](#172-behaviour)
- [18. `hmz epic` and `hmz hosts`](#18-hmz-epic-and-hmz-hosts)
  - [18.1. Synopsis](#181-synopsis)
  - [18.2. `hmz epic start`](#182-hmz-epic-start)
  - [18.3. `hmz epic attach`](#183-hmz-epic-attach)
  - [18.4. `hmz epic say`, `answer`, `stop` and `board`](#184-hmz-epic-say-answer-stop-and-board)
  - [18.5. `hmz epic claim`, `release`, `afk` and `status`](#185-hmz-epic-claim-release-afk-and-status)
  - [18.6. `hmz hosts`](#186-hmz-hosts)
- [19. `hmz runs`](#19-hmz-runs)
- [20. `hmz env`](#20-hmz-env)
- [21. `hmz flows`, `hmz flowverses` and `hmz workspaces`](#21-hmz-flows-hmz-flowverses-and-hmz-workspaces)
- [22. `hmz settings`, `hmz accounts` and `hmz nous`](#22-hmz-settings-hmz-accounts-and-hmz-nous)
- [23. `hmz runtimes`, `hmz easytier` and `hmz daemons`](#23-hmz-runtimes-hmz-easytier-and-hmz-daemons)
- [24. `hmz btw`, `hmz ai` and `hmz notices`](#24-hmz-btw-hmz-ai-and-hmz-notices)
- [25. `hmz skills`](#25-hmz-skills)
- [26. `hmz help`](#26-hmz-help)
- [27. Security Considerations](#27-security-considerations)
- [28. References](#28-references)
  - [28.1. Normative References](#281-normative-references)

## 1. Introduction

This document specifies the program `hmz`: how a command line is routed to a command, every
command and its options, the grammars of the values `hmz exec` takes, what each command writes to
its standard output and standard error, the rules for colour and for `--json` output, and every exit
status.

The following are out of scope of this document and are specified where cited:

- What the terminal interface does once it is open ([TUI]).
- What the web interface serves (Section 3 of [WEB], Section 4 of [WEB]).
- The daemon every command but `hmz relay` and `hmz update` is a client of, and the methods it
  serves ([DAEMON], [WIRE]).
- What a flow is and how its params are validated (Section 3 of [PYTHON]).
- Which harnesses exist, their effort ladders and their accounts (Section 4 of [CORE], Section 5 of
  [CORE]).
- Envs, runtimes and fallback between runtimes (Section 7 of [CORE]).
- Where a harness runs and the arrangements of `hmz internal anchor` (Section 6 of [CORE]).
- The record an epic leaves on disk (Section 6 of [FILES]).
- Budgets, resuming and stopping an epic as features (Section 3 of [CORE]).
- Backups as a feature (Section 11 of [CORE]) and updates as a feature (Section 13 of [CORE]).
- The settings file and the environment variables hmz reads (Section 3 of [FILES]).

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 2. Terminology

**2.1** A **command line** is the sequence of arguments the operating system hands to `hmz`,
excluding the program name.

**2.2** A **command** is the first argument of a command line where it is one of `exec`, `chat`,
`web`, `daemon`, `relay`, `update`, `backup` and `internal`.

**2.3** A **usage error** is a refusal of a command line in which the refusing parser writes its
usage text and the line `<prog>: error: <reason>` to standard error and exits with status 2, where
`<prog>` is `hmz` followed by the command's words.

**2.4** A stream **is a terminal** where the operating system reports it as a terminal device.

**2.5** **Escapes** are terminal control sequences that set colour or style, or move the cursor.

**2.6** An **NDJSON stream** is a byte stream of UTF-8 text in which every line is exactly one JSON
object followed by a line feed.

**2.7** A **diagnostic** is a line `hmz` writes to standard error that is not the answer of a turn
and not part of an NDJSON stream.

**2.8** The **task** is the text an epic started by `hmz exec` is given to carry out.

**2.9** An **item** is one element of the list an occurrence of `-a`, `-e` or `-p` gives, split as
Section 7.2 specifies.

## 3. Invocation and routing

### 3.1. Program

**3.1.1** hmz MUST install a console script named `hmz`.

**3.1.2** `python -m hmz` MUST behave exactly as `hmz` with the same command line.

### 3.2. Routing

**3.2.1** Where the command line is empty, `hmz` MUST open the terminal interface as Section 6
specifies.

**3.2.2** Where the command line is exactly `--version`, `hmz` MUST write `hmz <version>` and a line
feed to standard output, `<version>` being the installed version of hmz, and MUST exit with status
0.

**3.2.3** Where the first argument is a command, `hmz` MUST hand every later argument to that
command unchanged, `--help` and `-h` included.

**3.2.4** Where the first argument is `-h` or `--help` and is not followed by a command, `hmz` MUST
write its help, listing every command with its summary, to standard output and exit with status 0.

**3.2.5** Where the command line is not empty and its first argument is neither a command,
`--version` alone, `-h` nor `--help`, `hmz` MUST answer with a usage error that names the commands.

**3.2.6** `hmz` MUST NOT offer a command that opens the terminal interface.

### 3.3. Help

**3.3.1** Every command MUST answer `-h` and `--help` by writing its help to standard output and
exiting with status 0.

**3.3.2** In every help text, the help of an option, the summary of a command, a description and an
epilog MUST each be at most thirty words long.

**3.3.3** The summaries `hmz --help` writes MUST be, in this order:

```text
exec      run an agent flow in this directory
chat      say one message to an agent in this directory
web       open this machine's epics in a browser on it
daemon    run, reach, pair and install this machine's daemon
relay     relay daemons and the devices that reach them
update    update hmz to its newest release
backup    back epics up to git repositories, or download them
internal  internal commands used by Humanize; do not run directly
```

followed by each declared command (Section 16) with its summary, in the order of their names.

**3.3.4** The help of a declared command MUST be what Section 16 states, and Section 3.3.2 MUST hold
of each text in it.

## 4. Output conventions

### 4.1. Streams

**4.1.1** A command MUST write to standard output only what a program reading it is to parse: help
and version text (Section 3), the answers of turns, an NDJSON stream, the lines Section 8 to Section
10, Section 13 and Section 14 name as standard output, what a declared command answers (Section 16), the bytes `hmz daemon connect --stdio`
relays, and what Section 11 relays or reports to standard output.

**4.1.2** A command MUST write every diagnostic to standard error.

**4.1.3** A command whose standard output is not a terminal MUST NOT write escapes to standard
output.

### 4.2. Colour

**4.2.1** hmz MUST write escapes to a stream only where the first of the following conditions that
holds says so: `NO_COLOR` is set and non-empty, which says no; `TERM` is `dumb`, which says no;
`FORCE_COLOR` is set, non-empty and not `0`, which says yes; the stream is a terminal, which says
yes; otherwise no.

**4.2.2** `FORCE_COLOR` MUST NOT make hmz treat a stream that is not a terminal as a terminal for
any purpose other than writing escapes.

### 4.3. Secrets

**4.3.1** A command MUST NOT write the value of a credential to any stream.

**4.3.2** Where a command writes an account, it MUST write the account's harness, its name and the
names of the environment variables it sets, and MUST NOT write their values.

**4.3.3** Where a command writes a URL, it MUST first remove any user information and any credential
the URL carries.

## 5. Exit statuses

### 5.1. Statuses common to every command

**5.1.1** Every command MUST exit with status 0 where it did what it was asked.

**5.1.2** Every command other than `hmz internal hook` MUST exit with status 2 on a usage error, and
on every refusal this document assigns status 2.

**5.1.3** A command MUST NOT exit with a status other than 0, 1 and 2, except as Section 5.2
and Section 16.9 specify.

### 5.2. Statuses particular to commands

**5.2.1** `hmz exec` MUST exit with status 128 plus the signal number where a signal stopped its
epic, as Section 7.15 specifies.

**5.2.2** `hmz internal anchor`, `hmz internal cred` and `hmz internal fence` MUST exit with the
exit status of the program they ran, where that program ran.

**5.2.3** `hmz internal cli` MUST exit with the status the flow answered, where the flow answered.

**5.2.4** `hmz internal fence` MUST exit with status 126 where the fence cannot be put up.

**5.2.5** `hmz internal anchor` MUST exit with status 127 where `--native` is given and the env
machine has no such harness.

**5.2.6** `hmz internal anchor`, other than its `serve` and `rendezvous` subcommands, MUST exit with
status 130 where it was interrupted.

**5.2.7** `hmz exec` MUST exit with status 130 where it is interrupted before its epic has started
or after it has ended, as Section 7.15.5 specifies.

**5.2.8** `hmz internal hook` MUST exit with status 1 on a usage error.

**5.2.9** `coganchor cog`, `coganchor anchor`, `coganchor broker`, `coganchor internal fence` and
`coganchor internal cred` MUST exit with the statuses Section 5.2.2 to Section 5.2.6 assign to the
`hmz internal` command each stands for (Section 11.2.12), in the same cases.

**5.2.10** `hmz chat` MUST exit with status 128 plus the signal number where a signal ended it, as
Section 15.3.5 specifies.

## 6. The terminal interface (`hmz` with no command)

### 6.1. Opening

**6.1.1** `hmz` with an empty command line MUST open the terminal interface in the calling process
on the current directory as its workspace, and MUST NOT start an epic.

**6.1.2** `hmz` MUST open the terminal interface as a frontend of this machine's daemon, over
`unix:` (Section 3.4 of [WIRE]), starting the daemon where none runs (Section 3 of [DAEMON]). Where
standard error is a terminal and escapes are allowed (Section 4.2), `hmz` MUST draw a spinner on
standard error while it reaches or starts the daemon, and MUST take it down before the interface
starts.

**6.1.3** Where the daemon cannot be reached or started for a reason other than Section 6.1.4, `hmz`
MUST write `hmz: the daemon cannot be reached: <reason>` to standard error, MUST NOT open the
interface, and MUST exit with status 1.

**6.1.4** Where this machine's epics are held by a daemon of an older, incompatible hmz, `hmz` MUST
write a diagnostic beginning `hmz: ` that names that daemon's process id, MUST NOT open the
interface, and MUST exit with status 1.

**6.1.5** Before the terminal interface starts, where `TMUX` is unset or empty and either
`TERM_PROGRAM` is `iTerm.app` or `LC_TERMINAL` is `iTerm2`, `hmz` MUST set
`TEXTUAL_DISABLE_KITTY_KEY=1` in its own environment unless that variable is already set.

### 6.2. Closing

**6.2.1** Once the interface is closed, where backups this process started have not finished, `hmz`
MUST write `hmz: backing epics up` to standard error and wait for them for at most 15 seconds.

**6.2.2** Where a backup has not finished after that wait, `hmz` MUST write ``hmz: a backup took
longer than 15s and was left; `hmz backup EPIC` sends it again`` to standard error and exit.

**6.2.3** `hmz` MUST exit with status 0 where the interface closed normally.

**6.2.4** `hmz` MUST exit with status 1 where the daemon let go of the interface first.

## 7. `hmz exec`

### 7.1. Synopsis

```text
hmz exec -f <ref> [-a <agents>]... [-e <envs>]... [-p <params>]...
         [--profile-flow] [--profile-environment] [--resume] [--json]
         [--backup <target>]... [--] <task>
```

**7.1.1** `hmz exec` MUST run the flow `<ref>` names, in the current directory as its workspace, to
its return, as one new epic, with no interface: it MUST attach to a new exec slot of that workspace
on this machine's daemon (`epic.attach` with `slot` `exec:`, Section 4.7.1 of [DAEMON]), starting
the daemon where none runs, set every role away (`epic.afk`), start the epic there (`epic.start`),
and follow its messages until `ended`.

**7.1.2** `-f` and `--flow` MUST be the same option; that option MUST be given; where it is given
more than once, the last occurrence MUST be the one used.

**7.1.3** `-a` and `--agents`, `-e` and `--envs`, and `-p` and `--params` MUST each be the same
option, and each MUST be accepted any number of times.

**7.1.4** `--profile-flow`, `--profile-environment`, `--resume` and `--json` MUST each be a flag
that takes no value.

**7.1.5** `--backup` MUST be accepted any number of times.

**7.1.6** `<task>` MUST be exactly one positional argument; a task that begins with `-` MUST be
given after `--`.

**7.1.7** Options MUST be accepted in any order, before or after `<task>`.

**7.1.8** An option of `hmz exec` MUST NOT have an equivalent environment variable.

**7.1.9** Where the daemon cannot be reached or started, `hmz exec` MUST write `hmz: the daemon
cannot be reached: <why>` to standard error and exit with status 1, and where it is of another
protocol version, the refusal of Section 3.7.5 of [DAEMON] and exit with status 1.

**7.1.10** `hmz exec` ending in any way but those of Section 7.15 MUST NOT stop its epic, which the
daemon holds to its end (Section 3.5.3 of [DAEMON]).

### 7.2. Items

**7.2.1** Each occurrence of `-a`, `-e` or `-p` MUST be split into items at every `,` that is
followed, after optional white space, by a `<key>` of Section 7.6, optionally preceded by `budget.`,
and then `=`; every other `,` MUST belong to the item that contains it.

**7.2.2** The items of every occurrence of one option MUST form one list, in the order written.

**7.2.3** An item that is empty or consists only of white space MUST be a usage error.

**7.2.4** White space around an `-a` item and around an `-e` item MUST be ignored.

> Informative: `-a x=claude/m,y=codex/n` and `-a x=claude/m -a y=codex/n` are the same line;
> `-p tags=a,b,c` is one item, and no value can contain `,<key>=`.

### 7.3. Naming a flow

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

**7.3.1** A `<ref>` MUST be read as a `vcs` where it begins with `git+` or contains `#`, as a `path`
where it begins with `.`, `/` or `~`, and as a `name` otherwise.

**7.3.2** A `name` with no `@<flowverse>/` MUST name a flow of the flowverse `official`.

**7.3.3** A `name` with a `<flowverse>` of `local` or `user` MUST NOT have an `<owner>`.

**7.3.4** `@local/<flow>` MUST name the flow `<flow>` in the directory `.hmz/flows` of the
workspace, and `@user/<flow>` the flow `<flow>` in `<data>/flows` (Section 4.9 of [FILES]).

**7.3.5** A bare `<flow>` MUST resolve to the first flow of that name found by looking, in order, in
`local`, `user`, `official` and then every other flowverse (Section 3 of [PYTHON]).

**7.3.6** `:<inner>` MUST name another flow defined in the same module as the flow before it.

**7.3.7** A `vcs` ref MUST name the flow in the directory `<subdir>` of the repository at `<url>`
checked out at `<rev>`, the repository's root where `#<subdir>` is absent and its default branch
where `@<rev>` is absent.

**7.3.8** `hmz exec` MUST NOT install a flow; a flow a flowverse lists but that is not installed
MUST be refused, naming the flowverse it is to be installed from.

**7.3.9** A name written as `local/<flow>`, `user/<flow>`, `official/<flow>` or `<flowverse>/<flow>`
for an existing flowverse MUST be refused with a message that gives the name as it is written now.

**7.3.10** A relative path written without its leading `./` MUST be refused with a message that
gives it with its `./`.

**7.3.11** The name `chat` MUST name a flow as any other name does; a chat is not a flow, and is
started by `hmz chat` (Section 15).

### 7.4. Writing an agent

```abnf
agent   = role "=" ( harness [ "@" account ] "/" model [ ":" effort ] / nous )
role    = identifier
nous    = ALPHA *( ALPHA / DIGIT / "_" / "." / "-" )
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

**7.4.9** Any other effort MUST be on the harness's ladder (Section 4 of [CORE]); an effort off the
ladder MUST be refused under Section 7.7.

**7.4.10** An `-a` item without `@<account>` MUST run the harness as the harness machine's own
login.

**7.4.11** A `<harness>` that names no harness MUST be a usage error.

**7.4.12** A `<role>` given twice across every `-a` MUST be a usage error.

**7.4.13** The rest of an `-a` item that contains no `/` MUST be read as `<nous>`, the name of a
virtual nous (Section 4.11.4 of [CORE]); a `<nous>` that names a harness, or no virtual nous written
in the settings file (Section 3.6 of [FILES]), MUST be a usage error.

> Informative: `coder=claude/claude-opus-5:high`, `rev=codex@work/gpt-5:medium`, `fast=smart` (the
> virtual nous `smart`),
> `m=opencode/openrouter/qwen3:8b` (the model is `openrouter/qwen3:8b`, no effort), and
> `m=opencode/ollama/qwen3:latest:auto` (the model is `ollama/qwen3:latest`).

### 7.5. Writing an env

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
`/`, `@<provider>` where an `@` follows, and `<workdir>` from the first `/` after the provider; an
item that cannot be read so MUST be a usage error.

**7.5.2** `<role>` MUST be a Python identifier.

**7.5.3** `<backend>` MUST be one of the six values of the grammar.

**7.5.4** `local` MUST NOT take a provider.

**7.5.5** `ssh` MUST take a provider.

**7.5.6** A `<runtime>` MUST name a runtime written in the settings file for that backend (Section
3.8 of [FILES]); a name no runtime of that backend is written under MUST be refused.

**7.5.7** A bracketed `<host>` MUST be accepted for `ssh` alone, MUST be handed to `ssh` as written,
and MUST NOT name a written runtime.

**7.5.8** For `docker`, `swarm`, `apple-container` and `slurm`, the absence of a provider MUST mean
this machine: docker's default daemon here, the swarm this machine manages, this Mac's Apple
containers, and the Slurm cluster this machine submits to, respectively.

**7.5.9** An `@` followed by no provider MUST be a usage error.

**7.5.10** `<workdir>` MAY be omitted only where the provider names a runtime written with a
workdir, in which case that workdir MUST be used.

**7.5.11** A `<workdir>` of `/~` or beginning `/~/` MUST name a directory relative to the home
directory of the login on the env machine.

**7.5.12** A `<role>` given twice across every `-e` MUST be a usage error.

**7.5.13** `local@<anything>`, `docker@local`, `swarm@local`, `apple-container@local` and
`slurm@local` where no runtime of that backend is written as `local`, and an unbracketed ssh
destination that names no written runtime, MUST each be a usage error whose message gives the item
as it is written now.

> Informative: `repo=local/home/me/repo`, `repo=ssh@gpu-box/~/repo`, `repo=ssh@gpu-box` (the
> workdir `gpu-box` was written with), `repo=ssh@[me@far.host:2222]/srv/repo`,
> `box=docker/srv/repo`, `box=docker@gpubox/srv/repo`.

### 7.6. Writing params and a budget

```abnf
param    = key "=" value / limit
key      = ( ALPHA / "_" ) *( wordchar / "-" )
wordchar = <a character Python's regular expressions match as \w>
value    = *<character>
limit    = "budget." ( name / "graceful" [ "." name ] ) "=" value
name     = "duration" / "cost" / "output_tokens"
```

**7.6.1** A `-p` item that is not `<key>=<value>` or `budget.<name>=<value>` MUST be a usage error.

**7.6.2** A key MUST be given at most once across every `-p`.

**7.6.3** `<value>` MUST be everything after the first `=`, unchanged.

**7.6.4** `hmz exec` MUST hand every param that is not a `budget.` limit to the flow's params model
(Section 3 of [PYTHON]); a param the model refuses MUST be refused under Section 7.7.

**7.6.5** `budget` with no limit MUST be a usage error.

**7.6.6** `budget.<name>` with a `<name>` other than `duration`, `cost`, `output_tokens`,
`graceful`, `graceful.duration`, `graceful.cost` and `graceful.output_tokens` MUST be a usage error.

**7.6.7** `budget.duration` MUST accept a non-negative finite number of seconds; a concatenation of
numbers each followed by one of the units `w`, `d`, `h`, `m` and `s`, each unit at most once; an ISO
8601 duration; or `HH:MM:SS`.

**7.6.8** `budget.cost` MUST accept a non-negative number of US dollars, optionally preceded by `$`,
or `inf` for no limit.

**7.6.9** `budget.output_tokens` MUST accept a whole number, optionally written with `_`, or a
decimal number followed by `k` (thousands) or `m` (millions) that comes to a whole number.

**7.6.10** `budget.graceful` and `budget.graceful.<name>` MUST accept `1`, `true`, `yes` and `on` as
true and `0`, `false`, `no` and `off` as false, in any case. `budget.graceful` MUST set whether
every limit is graceful, and `budget.graceful.<name>` whether the limit `<name>` is, overriding
`budget.graceful` for that limit.

**7.6.11** A limit value that Section 7.6.7 to Section 7.6.10 do not accept MUST be a usage error.

**7.6.12** A budget that sets none of `duration`, `cost` and `output_tokens` MUST be a usage error.

**7.6.13** A line with no `budget.` limit MUST be refused under Section 7.7.

### 7.7. Refusals before the epic starts

**7.7.1** Every refusal of a well-formed line MUST be written to standard error as `hmz exec: error:
<reason>`, MUST exit with status 2, and MUST happen before any agent has started; a refusal of
`epic.start` (Section 4.8.2.4 of [DAEMON]) MUST be written so, its message as `<reason>`.

**7.7.2** `hmz exec` MUST refuse a flow that cannot be found or loaded.

**7.7.3** `hmz exec` MUST refuse an agent or env role the flow does not declare, naming the roles it
declares.

**7.7.4** `hmz exec` MUST refuse a role the flow fills itself.

**7.7.5** `hmz exec` MUST refuse a line that leaves a required role unfilled, naming the role.

**7.7.6** `hmz exec` MUST refuse an agent whose harness is not the harness its role requires, or
lacks a capability its role requires.

**7.7.7** `hmz exec` MUST refuse an `@<account>` that names no account of that harness.

**7.7.8** `hmz exec` MUST refuse params the flow's params model refuses, with the model's reason.

**7.7.9** `hmz exec` MUST refuse a `--resume` that Section 7.9 cannot satisfy.

**7.7.10** `hmz exec` MUST refuse a `--backup` naming no backup target in the settings file.

**7.7.11** `hmz exec` MUST refuse an env that cannot be reached, or whose machine has fewer
resources than its role declares, naming the role, once every runtime fallback (Section 7 of [CORE])
has been tried.

**7.7.12** `hmz exec` MUST refuse a line where an agent's harness cannot run where the harness
setting of its env's runtime says (Section 6 of [CORE]).

**7.7.13** `hmz exec` MUST refuse a skill a role names that cannot be found or fetched.

> Informative: `hmz exec: error: aot needs an agent for 'coder'; specify each with -a
> ROLE=CLI/MODEL:EFFORT`; `hmz exec: error: aot requires a budget: specify with -p
> budget.cost=...,budget.duration=...,budget.output_tokens=...`.

### 7.8. Where a harness runs

**7.8.1** An option of `hmz exec` MUST NOT say where a harness runs.

**7.8.2** Where each harness runs MUST be decided as Section 6 of [CORE] specifies.

**7.8.3** Where an env moves to a fallback runtime, `hmz exec` MUST write `hmz exec: <runtime>
cannot hold '<role>': <reason>; using <runtime>` to standard error, each `<runtime>` written as
`<backend>:<name>`.

### 7.9. Resuming

**7.9.1** With `--resume`, `hmz exec` MUST pick up the newest epic of the same flow in this
workspace that saved progress and is not still running (Section 3 of [CORE]).

**7.9.2** With `--resume`, `hmz exec` MUST refuse a flow that cannot be resumed, and a flow with no
epic in this workspace that can be picked up.

**7.9.3** Without `--resume`, every epic MUST start from the beginning.

### 7.10. Profiling

**7.10.1** `--profile-flow` MUST profile the flow's own Python code for the epic (Section 10 of
[CORE]).

**7.10.2** `--profile-environment` MUST profile the programs the epic's agents start.

**7.10.3** Without the corresponding flag, `hmz exec` MUST NOT profile either, whatever the settings
file holds.

### 7.11. Backups

**7.11.1** `--backup <target>` MUST name a backup target the epic is backed up to; with several, the
epic MUST go to each.

**7.11.2** `--backup none` MUST mean no backup target; `none` together with any other target MUST be
a usage error.

**7.11.3** Without `--backup`, the epic MUST go to the default targets of the settings file (Section
3.9 of [FILES]).

**7.11.4** Once the epic has ended and its backups have not all finished, as `backed` of `runs.get`
(Section 4.16.3 of [DAEMON]) says, `hmz exec` MUST write `hmz exec: backing the epic up` to standard
error and wait for them for at most 60 seconds, staying attached so that its host waits too.

**7.11.5** Where a backup has not finished after that wait, `hmz exec` MUST write ``hmz exec: a
backup took longer than 60s and was left; `hmz backup EPIC` sends it again`` to standard error, and
MUST exit as the epic had it.

### 7.12. Output for a person

**7.12.1** Without `--json`, `hmz exec` MUST draw the epic from the `event` records of its epic
(Section 4.9.2 of [DAEMON]) on standard error, one line or block per event, and MUST write each
`printed` record to standard output and each `notice` record to standard error as `hmz exec:
<text>`.

**7.12.2** Each event line MUST say which agent it is about, and, where that agent holds two or more
sessions, which session.

**7.12.3** A turn's `result` MUST be followed on standard error by a line of what the turn cost in
tokens by kind and, where the model has a known price, in US dollars.

**7.12.4** A turn's answer MUST be written to standard output followed by a line feed, unless both
standard output and standard error are terminals.

**7.12.5** A turn whose answer is empty MUST write nothing to standard output.

**7.12.6** Where standard error is a terminal and escapes are allowed (Section 4.2), `hmz exec` MUST
draw a clock at the foot of the output that says which agent is working, or how many turns are
working, and for how many seconds, and that says the epic is starting, and for how many seconds,
before its first turn opens.

**7.12.7** Where a cost limit applies to a model with no known price, `hmz exec` MUST write `hmz
exec: nobody lists a price for <model>[, <model>...], so cost=<limit> cannot stop what it spends` to
standard error before the flow is called, and MUST run the epic.

**7.12.8** Where the epic's budget stopped it, `hmz exec` MUST write `hmz exec: stopped --
<reason>` to standard error and MUST exit with status 0.

**7.12.9** Where the epic ends `failed` or `crashed`, `hmz exec` MUST write the `why` of its `ended`
record -- the exception, or the traceback -- to standard error and exit with status 1.

### 7.13. `--json`

**7.13.1** With `--json`, `hmz exec` MUST write an NDJSON stream to standard output, one object per
`event` record of its epic, each flushed as it is written.

**7.13.2** With `--json`, `hmz exec` MUST write nothing else to standard output, and MUST write each
`printed` record, all the flow or code it calls writes, to standard error.

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

**7.13.4** The meaning of each `kind` MUST be as Section 4 of [CORE] defines it.

### 7.14. Nobody at the prompt

**7.14.1** An epic `hmz exec` starts MUST have its outworlder away for its whole length (Section 3
of [PYTHON]): a question the flow asks MUST be answered at once as the flow API specifies for an
away outworlder.

**7.14.2** An `asks` event MUST still be written.

### 7.15. Signals

**7.15.1** On `SIGINT`, `SIGTERM` or `SIGHUP`, `hmz exec` MUST stop its epic (`epic.stop`), MUST
wait until the epic has ended, and MUST then exit with status 128 plus the number of the first
signal received.

**7.15.2** A signal whose disposition was set to ignore when `hmz exec` started MUST remain ignored.

**7.15.3** A second `SIGTERM` or `SIGHUP` while the epic stops MUST be ignored.

**7.15.4** A second `SIGINT` while the epic stops MUST force it (`epic.force`) and end the process
at once by `SIGINT`.

**7.15.5** An interrupt that arrives before the epic has started or after it has ended MUST exit
with status 130 without writing a traceback.

## 8. `hmz web`

### 8.1. Synopsis

```text
hmz web [--port <port>] [--origin <origin>] [--no-open] [--attached]
```

**8.1.1** `--port` MUST take an integer from 0 to 65535; any other value MUST be a usage error.

**8.1.2** `--port` MUST default to the port the last `hmz web` of this home listened on (Section
4.15 of [FILES]), or 0 where none is kept; 0 MUST mean any free port. Where the port kept cannot be
listened on, `hmz web` MUST listen on any free port.

**8.1.3** `--origin` MUST take `<scheme>://<host>[:<port>]` whose scheme is `http` or `https`, the
origin a reverse proxy that rewrites `Host` serves the page at (Section 4.4.6 of [WEB]); any other
value MUST be a usage error.

### 8.2. Behaviour

**8.2.1** `hmz web` MUST serve the page (Section 3 of [WEB]), its bridge `/rpc` to this machine's
daemon and its `/dial` (Section 4 of [WEB]) until it is stopped, offering the current directory
first for a new epic.

**8.2.2** `hmz web` MUST listen on `127.0.0.1` and, where this machine has IPv6, on `::1`, on the
same port, and on no other address.

**8.2.3** `hmz web` MUST reach this machine's daemon, starting it where none runs, before it
listens, and MUST hold no epic in its own process.

**8.2.4** Once listening, `hmz web` MUST write `hmz web: http://127.0.0.1:<port>/?key=<key>` and a
line feed to standard output and flush it.

**8.2.5** Unless `--no-open` is given, `hmz web` MUST open that address in a browser where this
machine is a Mac or `DISPLAY` or `WAYLAND_DISPLAY` is set, and MUST NOT open a browser otherwise.

**8.2.6** `hmz web` MUST stop on `SIGINT`, `SIGTERM` or `SIGHUP`, and, with `--attached`, when its
standard input reaches its end or cannot be read.

**8.2.7** Stopping `hmz web` MUST NOT stop any epic the daemon holds.

### 8.3. Exit

**8.3.1** `hmz web` MUST exit with status 0 once stopped as Section 8.2.6 specifies.

**8.3.2** Where this machine's epics are held by a daemon of an older, incompatible hmz, `hmz web`
MUST write a diagnostic beginning `hmz: ` and exit with status 1.

**8.3.3** Where the daemon cannot be reached or no port can be listened on, `hmz web` MUST write
`hmz: the web interface cannot be served: <reason>` to standard error and exit with status 1.

## 9. `hmz update`

### 9.1. Synopsis

```text
hmz update
```

**9.1.1** `hmz update` MUST take no argument.

### 9.2. Choosing the installer

**9.2.1** Where hmz is not installed as a distribution, `hmz update` MUST write `hmz update: hmz is
not installed here, only run from its source` to standard error and exit with status 1.

**9.2.2** Where hmz was installed from a URL or a local directory, `hmz update` MUST write `hmz
update: hmz was installed from <url>, not PyPI; update it there` to standard error, `<url>` written
as Section 4.3.3 requires, and exit with status 1.

**9.2.3** Where hmz was installed by `uv tool`, `hmz update` MUST run `uv tool upgrade hmz`.

**9.2.4** Where hmz was installed by `pipx`, `hmz update` MUST run `pipx upgrade hmz`.

**9.2.5** Otherwise, where pip is importable by the interpreter running hmz, `hmz update` MUST run
`<python> -m pip install --upgrade hmz[<extras>]`, and where it is not, `uv pip install --python
<python> --upgrade hmz[<extras>]`, `<python>` being that interpreter and `<extras>` every extra of
hmz whose packages are all installed, the brackets omitted where there is none.

**9.2.6** Where the installer Section 9.2.3 to Section 9.2.5 chose is `uv` or `pipx` and is not on
`PATH`, `hmz update` MUST write `hmz update: <installer> installed hmz but is not on PATH` to
standard error and exit with status 1.

### 9.3. Updating

**9.3.1** After Section 9.2, `hmz update` MUST ask PyPI, or the source `HUMANIZE_RELEASES` names,
for the newest release of hmz, excluding pre-releases.

**9.3.2** Where no answer comes, `hmz update` MUST write `hmz update: PyPI could not be asked for
the newest release` to standard error and exit with status 1.

**9.3.3** Where the running version is the newest or newer, `hmz update` MUST write `hmz <version>
is the newest release` to standard output, run nothing, and exit with status 0.

**9.3.4** Otherwise `hmz update` MUST write `Updating hmz <old> to <new>: <command>` to standard
output and then run the installer, letting it write to the same streams.

**9.3.5** Where the installer exits with a non-zero status, `hmz update` MUST write `hmz update:
<installer> exited <status>` to standard error and exit with status 1.

**9.3.6** Where the version installed afterwards is not the newest release, `hmz update` MUST write
`hmz update: <installer> left hmz at <version>, not <new>` to standard error and exit with status 1.

**9.3.7** Otherwise `hmz update` MUST write `Updated hmz to <new>` to standard output and exit with
status 0.

**9.3.8** Where a daemon runs on this machine, `hmz update` MUST make the statement of Section
13.4.4.2 of [CORE] by writing `Epics held on this machine (pid <pid>) run hmz <old> until that
daemon stops` to standard output after Section 9.3.7.

## 10. `hmz backup`

### 10.1. Synopsis

```text
hmz backup [--to <target>]... <epic>
hmz backup --list [--to <target>]...
hmz backup --pull <epic> [--to <target>]...
```

**10.1.1** `--list` and `--pull` MUST be mutually exclusive.

**10.1.2** A positional `<epic>` together with `--list` or `--pull` MUST be a usage error.

**10.1.3** A line with neither `--list`, `--pull` nor a positional `<epic>` MUST be a usage error.

**10.1.4** `--to` MUST name a backup target of the settings file, and MUST be accepted any number of
times.

### 10.2. Backing an epic up

**10.2.1** `hmz backup <epic>` MUST back up the epic of the current workspace whose name is
`<epic>`, or, where none is, the chat of the current workspace whose id is `<epic>` (Section 8.3.14
of [CORE]), or, where none is, the epic or the chat at the path `<epic>`.

**10.2.2** The epic MUST go to the targets `--to` names; without `--to`, to the targets the epic was
started with; and where it was started with none, to the default targets.

**10.2.3** An epic that does not exist, a `--to` naming no target, and a line that leaves no target
at all MUST each be a usage error.

**10.2.4** `hmz backup` MUST wait for every backup it started to finish.

**10.2.5** For each target that took the epic, `hmz backup` MUST write `<target>: backed up to
<url>` to standard output.

**10.2.6** For each target that did not, `hmz backup` MUST write `<target>: failed: <reason>` to
standard error.

**10.2.7** `hmz backup` MUST exit with status 0 where every target took the epic, and with status 1
otherwise.

### 10.3. Listing

**10.3.1** `hmz backup --list` MUST read each target `--to` names, or every target without `--to`,
after fetching it.

**10.3.2** For each target read, `hmz backup --list` MUST write `<target>: <n> epic` or `<target>:
<n> epics` to standard output, `epic` where `<n>` is 1, followed by one line per epic the target
holds: two spaces, then its machine, workspace, epic name, how it ended or `unfinished`, and its
task with white space runs collapsed and cut to 60 characters, separated by two spaces.

**10.3.3** For a target that cannot be read, `hmz backup --list` MUST write `<target>: failed:
<reason>` to standard error, MUST go on to the next target, and MUST exit with status 1.

**10.3.4** The chats a target holds MUST NOT be counted or written among its epics. Where it holds
any, `hmz backup --list` MUST write, after the epics of that target, `<target>: <n> chat` or
`<target>: <n> chats`, `chat` where `<n>` is 1, followed by one line per chat as Section 10.3.2
states for an epic, the chat's id in place of the epic name and its first message in place of the
task.

### 10.4. Downloading

**10.4.1** `<epic>` after `--pull` MUST be an epic's name, a chat's id or
`<machine>/<workspace>/<name>`; a chat MUST be downloaded as this section states for an epic, into
this machine's chats (Section 8.3.14 of [CORE]).

**10.4.2** `hmz backup --pull` MUST download the epic from the first target that holds it, in the
order of Section 10.3.1, into this machine's epics as an import (Section 11 of [CORE]).

**10.4.3** Once it has downloaded the epic, `hmz backup --pull` MUST write the path the epic now has
to standard output.

**10.4.4** `hmz backup --pull` MUST exit with status 0 once it has downloaded the epic.

**10.4.5** Where a target holds epics of that name from more than one machine, `hmz backup --pull`
MUST answer with a usage error that lists each as `<machine>/<workspace>/<name>`.

**10.4.6** Where the epic is already on this machine, `hmz backup --pull` MUST write a diagnostic
beginning `hmz backup: ` and exit with status 1.

**10.4.7** Where every target answered and none holds the epic, `hmz backup --pull` MUST answer with
a usage error.

**10.4.8** Where a target could not be read and no other held the epic, `hmz backup --pull` MUST
write `hmz backup: no target that answered holds <epic>` to standard error and exit with status 1.

## 11. `hmz internal`

### 11.1. Status

**11.1.1** The commands under `hmz internal` MUST be the command lines hmz starts its own processes
with, and MUST NOT be a public interface of hmz.

**11.1.2** The help of `hmz internal`, and of each of its commands, MUST say that the command is not
to be run directly.

**11.1.3** Each `hmz internal` command MUST run when a user types it.

**11.1.4** `hmz internal` with no command, or with a command it does not have, MUST be a usage error
that lists its commands.

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

**11.1.6** `hmz internal anchor`, `hmz internal cred` and `hmz internal fence` MUST each run the
`coganchor` of this machine (Section 7.5 of [FILES]) with the command line Section 11.2.13 gives,
handing it its standard streams, and MUST exit with its status.

### 11.2. `hmz internal anchor`

```text
hmz internal anchor [<options>] <program> [<args>...]
hmz internal anchor serve --export <virtual>[:<real>]... (--stdio | --listen [<host>:]<port>
                          | --peer <ticket>@<host>:<port>) [--token <secret>]
                          [--log-level <level>]
hmz internal anchor rendezvous [--listen [<host>:]<port>] [--punching <seconds>]
                               [--log-level <level>]

coganchor cog [<options>] <program> [<args>...]
coganchor anchor --export <virtual>[:<real>]... (--stdio | --listen [<host>:]<port>
                 | --peer <ticket>@<host>:<port>) [--token <secret> | --token-file <file>]
                 [--log-level <level>]
coganchor broker [--listen [<host>:]<port>] [--punching <seconds>] [--log-level <level>]
coganchor internal fence (--policy (<json> | @<path>) [--sandbox <backend>] | --relay <dir>) [--]
                         <program> [<args>...]
coganchor internal cred (--map <from>=<to> | --keep <from>=<to>)... [--] <program> [<args>...]
coganchor --version
```

**11.2.1** `hmz internal anchor` MUST run `<program>` with its work landing on the machine
`--target` names, in the arrangement Section 6 of [CORE] specifies.

**11.2.2** `hmz internal anchor` MUST accept the options `--target`, `--harness`, `--broker`,
`--workspace`, `--chdir`, `--remote-path`, `--shadow`, `--local-path`, `--local-exec`, `--redirect`,
`--private`, `--net`, `--net-allow`, `--token`, `--token-file`, `--force`, `--native`, `--hush`,
`--project`, `--carry`, `--bring`, `--tell`, `--installs`, `--fence`, `--check` and `--log-level`,
whose meanings Section 6 of [CORE] specifies.

**11.2.3** `--target` MUST default to `HUMANIZE_TARGET`, else `local`; `--harness` to
`HUMANIZE_HARNESS`, else `local`; `--broker` to `HUMANIZE_RENDEZVOUS`; `--shadow` to
`HUMANIZE_SHADOW`, else `--workspace`; `--token` to `HUMANIZE_TOKEN`; and `--log-level` to
`HUMANIZE_LOG`, else `warning`.

**11.2.4** hmz MUST pass a secret to a process it starts with `--token-file`, never with `--token`.

**11.2.5** `hmz internal anchor` with neither a program nor `--check` MUST exit with status 2.

**11.2.6** `hmz internal anchor` MUST exit with status 1, writing `hmz: <reason>` to standard error,
on a connection, protocol, operating-system or value error.

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

**11.2.11** Where `HUMANIZE_LOG` holds a value other than `debug`, `info`, `warning` and `error`, in
any case and with surrounding white space removed, `hmz internal anchor`, `hmz internal anchor
serve` and `hmz internal anchor rendezvous` MUST each write `hmz: ignoring HUMANIZE_LOG='<value>',
which is not one of debug, info, warning, error` to standard error and log at the default level of
Section 11.2.3.

**11.2.12** `coganchor cog`, `coganchor anchor` and `coganchor broker` MUST be `hmz internal
anchor`, `hmz internal anchor serve` and `hmz internal anchor rendezvous`, and `coganchor internal
fence` and `coganchor internal cred` MUST be `hmz internal fence` and `hmz internal cred`: each MUST
take the same options with the same defaults, read the same variables, and write the same messages,
`hmz: <reason>`, `hmz internal anchor serve listening <host> <port>` and `hmz internal anchor
rendezvous listening <bound> <landed>` among them, word for word.

**11.2.13** `hmz internal anchor serve <args>` MUST run `coganchor anchor <args>`; `hmz internal
anchor rendezvous <args>` MUST run `coganchor broker <args>`; `hmz internal anchor <args>` otherwise
MUST run `coganchor cog <args>`; and `hmz internal fence <args>` and `hmz internal cred <args>` MUST
run `coganchor internal fence <args>` and `coganchor internal cred <args>`.

**11.2.14** `coganchor` with no mode, or with a mode it does not have, MUST be a usage error. A usage
error of `coganchor`, and of each command Section 11.2.13 runs it for, MUST write its reason to
standard error and exit with status 2, and MAY do so in another form than Section 2.3 gives.

**11.2.15** `coganchor --version` MUST write `coganchor <version>` to standard output, where
`<version>` is the version of hmz it was built with, and exit with status 0.

**11.2.16** The help of `coganchor` MUST list `cog`, `anchor` and `broker`, and MUST NOT list
`internal`.

**11.2.17** `hmz internal anchor serve --peer` with `--token` or `--token-file` MUST be a usage
error, and MUST ignore `HUMANIZE_TOKEN`: the ticket is its secret (Section 6.10.9 of [CORE]).

**11.2.18** `hmz internal anchor` reaching a serving half that does not prove the token (Section
6.10.12 of [CORE]) MUST exit with status 1, writing `hmz: <reason>` where `<reason>` says `the
serving half at <target> did not prove the token`.

### 11.3. `hmz internal cred`

```text
hmz internal cred (--map <from>=<to> | --keep <from>=<to>)... [--] <program> [<args>...]
```

**11.3.1** `hmz internal cred` MUST run `<program>` with every access to the absolute path `<from>`,
or to anything under it, answered from `<to>`.

**11.3.2** `--keep` MUST answer as `--map` does, MUST create what the program writes, and MUST
accept a glob in any component of `<from>`.

**11.3.3** `hmz internal cred` with no program, with no `--map` and no `--keep`, or with a malformed
mapping MUST exit with status 2.

**11.3.4** Where the program cannot be supervised, `hmz internal cred` MUST write `hmz internal
cred: <reason>` to standard error, MUST exit with status 1, and MUST NOT run the program.

### 11.4. `hmz internal fence`

```text
hmz internal fence (--policy (<json> | @<path>) [--sandbox <backend>] | --relay <dir>) [--] <program>
                   [<args>...]
```

**11.4.1** `hmz internal fence` MUST run `<program>` held to the paths and hosts the policy permits
(Section 4 of [CORE]).

**11.4.2** `hmz internal fence` with neither or both of `--policy` and `--relay`, or no program,
MUST exit with status 2.

**11.4.3** Where the fence cannot be put up on this machine, `hmz internal fence` MUST write `hmz
internal fence: <reason>` to standard error, MUST exit with status 126, and MUST NOT run the
program.

**11.4.4** `--sandbox` MUST select the backend on Linux as `sandbox.backend` does (Section 4.6.4.16
of [CORE]), an absent or other value as `auto`; hmz MUST pass the `sandbox.backend` of the machine
it runs on to the confinement it holds there, and nothing to confinement held on another machine.

**11.4.5** `hmz internal fence --relay <dir>` is the program bubblewrap starts in a network namespace
of its own (Section 4.6.4.18 of [CORE]): it MUST listen on this namespace's loopback at each port
`<port>` for which `<dir>` holds a socket `out-<port>.sock` and pass each connection to that socket,
MUST listen at `<dir>/in-<port>.sock` for each file `<dir>/in-<port>` and pass each connection to
`<port>` on this namespace's loopback, and MUST then run `<program>`.

### 11.5. `hmz internal hook`

```text
hmz internal hook --at <socket>
```

**11.5.1** `hmz internal hook` MUST read one hook call as JSON from standard input, send it on one
line to the Unix socket `<socket>`, and write the one line answered to standard output.

**11.5.2** `hmz internal hook` MUST exit with status 0 once it has read its input, whatever the
answer, and where the socket cannot be reached or closes without answering.

**11.5.3** Where the socket cannot be reached, `hmz internal hook` MUST write `hmz internal hook:
<socket>: <reason>` to standard error and write nothing to standard output.

**11.5.4** `hmz internal hook` MUST NOT exit with status 2, and MUST exit with status 1 where its
command line cannot be read.

### 11.6. `hmz internal tools`

```text
hmz internal tools --at <socket>
```

**11.6.1** `hmz internal tools` MUST carry bytes in both directions at once between its standard
streams and the Unix socket `<socket>`, and the end of either direction MUST end the other.

**11.6.2** `hmz internal tools` MUST exit with status 0 once either end has closed, with status 1
where the socket cannot be reached, and with status 2 without `--at`.

### 11.7. `hmz internal cli`

```text
hmz internal cli --at <socket> --name <name> [-- <words>...]
```

**11.7.1** `hmz internal cli` MUST send `{"name": <name>, "argv": <words>}` on one line to the Unix
socket `<socket>`, read one line `{"code", "out", "err"}` back, write `out` to standard output and
`err` to standard error, and exit with status `code`.

**11.7.2** `hmz internal cli` MUST pass every word after the first `--` unchanged, and MUST NOT read
standard input.

**11.7.3** Where the socket cannot be reached, `hmz internal cli` MUST write `<name>: the flow
serving it has ended (<reason>)` to standard error and exit with status 1.

**11.7.4** Where no answer comes back, `hmz internal cli` MUST write `<name>: the flow serving it
gave no answer` to standard error and exit with status 1.

**11.7.5** `hmz internal cli` without `--at` or `--name` MUST exit with status 2.

## 12. Environment

### 12.1. Variables

**12.1.1** The commands MUST read the environment variables Section 3.11 of [FILES] lists, with the
meanings given there.

## 13. `hmz daemon`

### 13.1. Synopsis

```text
hmz daemon serve [--listen <spec>]...
hmz daemon connect --stdio
hmz daemon pair [--route <route>]... [--seconds <seconds>]
hmz daemon devices [revoke <name>]
hmz daemon install
hmz daemon uninstall
```

**13.1.1** `hmz daemon` MUST take a subcommand, `serve`, `connect`, `pair`, `devices`, `install` or
`uninstall`; anything else MUST be a usage error.

**13.1.2** `--listen` MUST be accepted any number of times, each a listener spec of Section 3.9.2 of
[DAEMON]; another value MUST be a usage error saying `<spec> is not a listener.`

**13.1.3** `connect` MUST take `--stdio`, and without it MUST be a usage error.

**13.1.4** `--route` MUST be accepted any number of times, each a route of Section 3.3 of [WIRE];
another value MUST be a usage error saying `<route> is not a route.` `--seconds` MUST take an
integer from 60 to 86400; another value MUST be a usage error.

**13.1.5** `devices` MUST take nothing, or `revoke` and one name; anything else MUST be a usage
error.

**13.1.6** `install` and `uninstall` MUST take no option.

### 13.2. Behaviour

**13.2.1** `hmz daemon serve` MUST run this machine's daemon in its own process, in the foreground,
listening on its socket, on every listener `listen` names (Section 3.4.8 of [FILES]) and on every
`--listen`, as Section 3.9 of [DAEMON] states, until it receives `SIGINT` or `SIGTERM`.

**13.2.2** `hmz daemon serve` MUST write `hmz daemon: listening on <route>` and a line feed to
standard output, flushed, as each listener opens, `<route>` the listener's route (Section 3.9.3 of
[DAEMON]).

**13.2.3** `hmz daemon connect --stdio` MUST reach this machine's daemon over its socket, starting
it where none runs (Section 3.4 of [DAEMON]), MUST then write `hmz-stdio/1` and a line feed to
standard output (Section 3.4.11 of [WIRE]), and MUST then carry every byte of its standard input to
the socket and every byte of the socket to its standard output, unchanged and in order, until
either ends, and MUST then close both, half-closing neither (Section 3.4.10 of [WIRE]); it MUST
write nothing else to standard output.

**13.2.4** `hmz daemon pair` MUST call `pair.create` on this machine's daemon, starting it where
none runs, with the routes of `--route` where any is given and the lifetime `--seconds`, and MUST
write the code and a line feed to standard output, and `hmz daemon pair: claim this code on the
device to pair before <time>` to standard error, `<time>` the moment it expires in local time.

**13.2.5** `hmz daemon devices` MUST write one line per device paired with this machine's daemon,
oldest first, its name, fingerprint, when it was added and when it was last seen, separated by tab
characters; `hmz daemon devices revoke <name>` MUST call `devices.revoke` and write `hmz daemon
devices: revoked <name>; <n> sessions closed` to standard output.

**13.2.6** `hmz daemon install` and `hmz daemon uninstall` MUST write, enable and start, or stop,
disable and remove, the service of Section 3.9.6 of [DAEMON], and MUST write `hmz daemon: installed
<path>` or `hmz daemon: uninstalled <path>` to standard output, `<path>` the file of the service.

### 13.3. Exit

**13.3.1** `hmz daemon serve` MUST exit with status 0 once stopped as Section 13.2.1 specifies.

**13.3.2** Where a daemon is already running, `hmz daemon serve` MUST write `hmz: a daemon is
already running (pid <pid>)` to standard error and exit with status 1.

**13.3.3** `hmz daemon connect --stdio` MUST exit with status 0 where its standard input or the
daemon ended the connection.

**13.3.4** Where the daemon cannot be reached or started, `hmz daemon connect`, `pair` and `devices`
MUST write `hmz: the daemon cannot be reached: <why>` to standard error and exit with status 1, and
where it is of another protocol version, the refusal of Section 3.7.5 of [DAEMON] and exit with
status 1.

**13.3.5** Where the daemon refuses `pair.create` or `devices.revoke`, the command MUST write `hmz:
<message>` to standard error, the refusal's message, and exit with status 1.

**13.3.6** `hmz daemon install` and `hmz daemon uninstall` MUST write `hmz: hmz daemon install runs
on macOS and Linux alone` and exit with status 1 on any other system, and MUST write `hmz: <why>`
and exit with status 1 where `launchctl` or `systemctl` fails, or, for `uninstall`, where no service
is installed.

## 14. `hmz relay`

### 14.1. Synopsis

```text
hmz relay serve [--listen <host>:<port>]
```

**14.1.1** `hmz relay` MUST take the subcommand `serve`; anything else MUST be a usage error.

**14.1.2** `--listen` MUST take a host and a port from 0 to 65535, and MUST default to
`127.0.0.1:8765`; another value MUST be a usage error.

### 14.2. Behaviour

**14.2.1** `hmz relay serve` MUST serve the relay of Section 5 of [WIRE] on plain WebSockets at the
address `--listen` names, until it receives `SIGINT` or `SIGTERM`.

**14.2.2** Once listening, `hmz relay serve` MUST write `hmz relay: listening on ws://<host>:<port>`
and a line feed to standard output, flushed.

**14.2.3** `hmz relay serve` MUST NOT read the settings file, the home or the identity of this
machine, and MUST NOT start or reach a daemon.

### 14.3. Exit

**14.3.1** `hmz relay serve` MUST exit with status 0 once stopped as Section 14.2.1 specifies.

**14.3.2** Where it cannot listen, `hmz relay serve` MUST write `hmz: the relay cannot listen:
<why>` to standard error and exit with status 1.

## 15. `hmz chat`

### 15.1. Synopsis

```text
hmz chat [-a <agent>] [-e <env>] [--resume <chat> | --worktree] [--] <message>
hmz chat --list [--archived]
hmz chat --rename <chat> <title>
hmz chat --fork <chat>
hmz chat --archive <chat>
hmz chat --unarchive <chat>
hmz chat --delete <chat> [--yes]
```

**15.1.1** `hmz chat` MUST take one turn of a chat (Section 8 of [CORE]) in the current directory as
its workspace, with nobody at a prompt: it MUST start the chat on a new chat slot of that workspace
on this machine's daemon (`chat.start` with `slot` `chat:`, Section 4.25 of [DAEMON]), starting the
daemon where none runs, follow its messages (`epic.attach`) until the turn is done, and then end the
chat with an empty next message (Section 8.4.8 of [CORE]).

**15.1.2** `-a` and `--agent` MUST be the same option, MUST take one agent written as the text of an
`-a` item of Section 7.4 after `<role>=`, and, where given more than once, the last occurrence MUST
be the one used.

**15.1.3** Without `-a`, `hmz chat` MUST use the chat agent the workspace remembers (Section 3.5.1.9
of [FILES]), and MUST refuse where none is remembered, saying to give one with `-a`.

**15.1.4** `--resume <chat>` MUST carry on the chat of that id in this workspace (Section 8.7 of
[CORE]; `chat.start` with `resume` the id, Section 4.25 of [DAEMON]), with `<message>` as its next
turn and with its own agent unless `-a` is given. `<chat>` MUST be the id of a chat, which is the
name of its directory; `hmz chat` MUST NOT name a chat an epic, and MUST NOT carry on an epic.

**15.1.5** Without an option of Section 15.4, `<message>` MUST be exactly one positional argument
and MUST NOT be empty; a message that begins with `-` MUST be given after `--`.

**15.1.6** `<message>` MUST be served as Section 8.9 of [CORE] states, except that a `$` line that
names a flow and a name Section 8.9.7 of [CORE] keeps MUST be refused, naming it.

**15.1.7** `hmz chat` MUST NOT change the remembered setup of any workspace.

**15.1.8** `--worktree` MUST start the chat with its assistant working in a new git worktree of the
workspace (`chat.start` with `worktree` true, Section 4.25 of [DAEMON]). `--worktree` together with
`--resume` MUST be refused before anything is asked of the daemon: a chat carried on works where it
worked. Where the workspace is no git repository, the refusal of `chat.start` MUST be written as
Section 15.3.2 states.

**15.1.9** `-e` and `--env` MUST be the same option, MUST take one env written as the text of an
`-e` item of Section 7.5 after `<role>=`, and MUST start the chat with its assistant working there
(`chat.start` with `env`, Section 4.25.1.10 of [DAEMON]); with `--resume`, the chat MUST be carried
on there, which moves it (Section 8.3.16 of [CORE]). A refusal of `chat.start` MUST be written as
Section 15.3.2 states.

### 15.2. Output

**15.2.1** `hmz chat` MUST draw the turn on standard error and write its answer to standard output
as Section 7.12.1 to Section 7.12.5 state for `hmz exec`.

**15.2.2** Once `chat.start` is answered, `hmz chat` MUST write `hmz chat: chat <id>` to standard
error, `<id>` being the id of the chat started or carried on, which `--resume` and the options of
Section 15.4 take.

### 15.3. Exit

**15.3.1** `hmz chat` MUST exit with status 0 once the turn is done.

**15.3.2** Every refusal before the chat starts MUST be written to standard error as `hmz chat:
error: <reason>` and MUST exit with status 2; a refusal of `chat.start` MUST be written so, its
message as `<reason>`.

**15.3.3** Where the turn fails, `hmz chat` MUST write what the harness said to standard error and
exit with status 1 (Section 8.4.9 of [CORE]).

**15.3.4** Where the daemon cannot be reached or started, `hmz chat` MUST write and exit as Section
7.1.9 states for `hmz exec`.

**15.3.5** On `SIGINT`, `SIGTERM` or `SIGHUP`, `hmz chat` MUST leave the chat to its host (Section
8.8.6 of [CORE]) and exit with status 128 plus the number of the signal.

### 15.4. The chats written down

**15.4.1** `--list`, `--rename`, `--fork`, `--archive`, `--unarchive` and `--delete` MUST be
mutually exclusive and MUST take no turn of a chat; each together with `-a`, `-e`, `--resume` or
`--worktree`, a positional argument with any of them but `--rename`, `--archived` without `--list`
and `--yes` without `--delete` MUST each be a usage error.

**15.4.2** Each MUST be asked of this machine's daemon by the method of Section 4.25 of [DAEMON]
named for it, starting the daemon where none runs, `<chat>` being a chat's id; `hmz chat` MUST NOT
read or write a chat's files for any of them.

**15.4.3** `hmz chat --list` MUST write to standard output one line per chat of the current
workspace that is not archived (`chat.list` with `workspace`), newest first: its id, how it stands
and its title with white space runs collapsed and cut to 60 characters, separated by two spaces.
How it stands MUST be its state (Section 4.25.5.3 of [DAEMON]) where that is `turn`, `asking` or
`failed`, and `ready` otherwise, `going` and `resting` alike (Section 8.5.3 of [CORE]). With `--archived` it MUST write the archived chats alone.

**15.4.4** `hmz chat --rename <chat> <title>` MUST give the chat that title (`chat.rename`),
`<title>` being the one positional argument and saying something, else a usage error; `--archive
<chat>` MUST archive the chat (`chat.archive`) and `--unarchive <chat>` MUST put it back
(`chat.unarchive`). Each MUST write the chat's line as Section 15.4.3 states it, as the chat then
stands.

**15.4.5** `hmz chat --fork <chat>` MUST fork the chat (`chat.fork`) and write the id of the new
chat to standard output.

**15.4.6** `hmz chat --delete <chat>` MUST delete the chat (`chat.delete`) and write nothing to
standard output. Without `--yes` it MUST first ask on standard error, naming the chat by its line of
Section 15.4.3 (`chat.get`) and saying that it cannot be brought back, and MUST delete only where
`y` or `yes` is then read from standard input, compared without regard to case; where standard
input is not a terminal it MUST read nothing and say to give `--yes`. A chat not deleted for want of
a yes MUST be said on standard error and MUST exit with status 1.

**15.4.7** Each MUST exit with status 0 once done; what the daemon refuses MUST be written and exit
as Section 15.3.2 states, and a daemon that cannot be reached or started as Section 15.3.4 states.

## 16. Declared commands

**16.1** A _declared command_ is a command written as one declaration: its name, its summary, what it
takes, example lines, what it prints, the fields of its JSON document, its exit statuses and the
methods of [OPENRPC] it calls. Section 17 onwards specify the declared commands; `exec`, `web`,
`daemon`, `relay`, `update` and `internal` are not declared commands.

**16.2** A declared command MUST reach a daemon only as a client of it, through the `Client` of
Section 4.21 of [PYTHON] with `kind` `cli`, and MUST NOT read or write what a daemon keeps by any
other way.

**16.3** A group of declared commands, named with no command after it, MUST write its help to
standard output and exit with status 0.

**16.4** The help of a declared command MUST consist of these parts, in this order, each present
where the command has it: its usage line; what it does; its arguments; its options, the common
options of 16.6 and `-h, --help` after its own; its examples, each a line that can be typed and what
that line does; its output, being what it prints without `--json` and each field of its JSON document
with its type; its exit statuses with what each means; the methods of [OPENRPC] it calls; and the
commands to read beside it. The help of a group MUST consist of its usage line, what it is about, and
each command under it with its summary.

**16.5** Everything the help of a declared command states MUST be read from its declaration, and a
declared command MUST NOT take an argument, print a field or exit with a status its help does not
state.

**16.6** Every declared command MUST take `--json`, `--daemon <name>` and `--no-color`. `--daemon`
MUST name the daemon to ask as Section 23 keeps it, this machine's where it is absent.

**16.7** Under `--json` a declared command MUST write exactly one JSON document and a line feed to
standard output and nothing else to it, and MUST write nothing to standard error. Where it did what
it was asked the document MUST hold the fields its help states. Otherwise the document MUST be
`{"error": {"code": <code>, "message": <message>}}`, `code` being the error's code where a daemon
answered one (Section 6.6 of [WIRE]), `503` where the daemon cannot be reached and `504` where it
did not answer in time.

**16.8** Without `--json`, a declared command that did not do what it was asked MUST write `hmz
<command>: <message>` and a line feed to standard error, `<command>` being its words after `hmz`.

**16.9** A declared command MUST exit with status 0 where it did what it was asked, 1 where the daemon
refused, 2 on a usage error, and 3 where the daemon cannot be reached or did not answer in time.

**16.10** A usage error of a declared command MUST be written to standard error as `hmz <command>:
<what is wrong>`, followed by a line naming the `--help` to run.

**16.11** Every text a declared command writes that is not data MUST be a text the web interface
writes ([WEB]) wherever that interface has a text saying the same thing, word for word in its
English, and MUST otherwise be a text kept with hmz for that purpose; a declared command MUST NOT
compose such a text where it is written.

## 17. `hmz devices`

### 17.1. Synopsis

```text
hmz devices list
hmz devices revoke <name>
hmz devices pair [--route <route>]... [--seconds <n>]
```

**17.1.1** `hmz devices` MUST be a group of declared commands (Section 16) with the summary `list
and revoke the devices paired with this daemon`.

### 17.2. Behaviour

**17.2.1** `hmz devices list` MUST call `devices.list` and write one line per device, in the
daemon's order: its name, its fingerprint, when it was added and when it was last seen, in columns.
Its JSON document MUST be `{"devices": [{"name", "fingerprint", "added", "seen"}]}`, `seen` being
`null` for a device never seen.

**17.2.2** `hmz devices revoke <name>` MUST call `devices.revoke` with `name` and write how many
sessions were closed. Its JSON document MUST be `{"dropped": <n>}`.

**17.2.3** `hmz devices pair` MUST call `pair.create` with each `--route` as `routes`, where any is
given, and `--seconds` as `seconds`, where it is given; it MUST write the code and a line feed to
standard output, and to standard error when the code expires, in local time. Its JSON document MUST
be `{"code": <code>, "expires": <seconds since the epoch>}`.

## 18. `hmz epic` and `hmz hosts`

### 18.1. Synopsis

```text
hmz epic start <flow> [<task>] [-a <agents>]... [-e <envs>]... [-p <params>]...
               [--resume | --resume-from <epic>] [--backup <target>]... [--no-backup]
               [--profile-flow] [--profile-environment] [--remember] [--scratch]
               [--away] [--follow] [-w <dir>] [--slot <slot>]
hmz epic attach [--no-replay] [-w <dir>] [--slot <slot>]
hmz epic say <text> [--to <who>] [-w <dir>] [--slot <slot>]
hmz epic answer [<text>] [-q <id>] [--value <json>] [-w <dir>] [--slot <slot>]
hmz epic stop [--force] [-w <dir>] [--slot <slot>]
hmz epic board [<key> [<value>]] [--remove] [-w <dir>] [--slot <slot>]
hmz epic claim [<role>]... [--take] [--no-replay] [-w <dir>] [--slot <slot>]
hmz epic release <role> [-w <dir>] [--slot <slot>]
hmz epic afk [<role>] [--back] [-w <dir>] [--slot <slot>]
hmz epic status [-w <dir>] [--slot <slot>]
hmz hosts list [--running]
hmz hosts stop [-w <dir>] [--slot <slot>]
```

**18.1.1** `hmz epic` and `hmz hosts` MUST each be a group of declared commands (Section 16), with
the summaries `start, follow and steer an epic held by this daemon` and `list and close the hosts
this daemon holds epics and chats in`.

**18.1.2** `-w` and `--workspace` MUST be the same option. Every command that takes it MUST name a
host (Section 4.6 of [DAEMON]) by `workspace`, the directory `-w` gives as a whole path with its
links followed, or the current directory where it is absent, and by `slot`, what `--slot` gives, or `""` where it is absent.

**18.1.3** A command of `hmz epic` other than `status` MUST attach to that host as one frontend
(`epic.attach` with `replay` false but where its paragraph states otherwise, Section 4.7.1 of
[DAEMON]), make its calls on the epic subscription that opens, and let the frontend go
(`epic.detach`) before it exits, however it ends. `hmz epic status` and the commands of `hmz hosts`
MUST NOT attach to a host.

**18.1.4** A command of `hmz epic` other than `start` and `status` MUST first call `hosts.status`
for that host and MUST NOT attach where it is refused: only `hmz epic start` starts a host.

**18.1.5** `hmz epic start`, `hmz epic attach` and `hmz epic claim` MUST exit with status 130 where
they are interrupted, and MUST NOT stop the epic by it.

**18.1.6** A refusal of the daemon or of the host MUST be written and exited with as Section 16
states, in the words it was refused with.

### 18.2. `hmz epic start`

**18.2.1** `hmz epic start` MUST call `epic.start` (Section 4.8.2 of [DAEMON]) with `flow`
`<flow>`, `task` `<task>`, or `""` where it is absent, and what its options give, and MUST exit as
soon as the call is answered unless `--follow` is given; the epic MUST go on without it. It MUST
write one line naming the epic's number, its workspace and, where it is not `""`, its slot. Its JSON
document MUST be `{"run": <n>, "slot": <slot>, "workspace": <path>}`, as `epic.start` answered them.

**18.2.2** `-a` and `--agents`, `-e` and `--envs`, and `-p` and `--params` MUST each be the same
option, each accepted any number of times. Each `-a` and `-e` value MUST be one or more
`<role>=<spec>` items, separated by a comma that a role and `=` follow, and MUST be sent as `agents`
and `envs`, each `<spec>` unchanged under its `<role>`; an item that is not `<role>=<spec>`, and a
role given twice by one of the two options, MUST be a usage error. Each `-p` value MUST be read as Section 7.6 states: the params that are not `budget.`
limits MUST be sent as `params`, each value as text, and the limits as `budget`; a `-p` Section 7.6
makes a usage error MUST be one here. Where no `-p` gives a param, `params` MUST NOT be sent, and
where none gives a limit, `budget` MUST NOT be sent.

**18.2.3** `--resume` MUST send `resume` true and `--resume-from <epic>` MUST send `resume`
`<epic>`; `--backup`, accepted any number of times, MUST send `backup` the targets given, and
`--no-backup` MUST send `backup` `[]`; `--profile-flow`, `--profile-environment` and `--remember`
MUST send `profile_flow`, `profile_environment` and `remember` true. What no option gives MUST NOT
be sent.

**18.2.4** `--scratch` MUST attach with `scratch` true and no `workspace` (Section 4.7.1.3 of
[DAEMON]). `--slot exec:` MUST attach to a new exec slot (Section 4.7.1.2 of [DAEMON]).

**18.2.5** `--away` MUST call `epic.afk` with `on` true and no `role` before `epic.start`, unless
the `away` snapshot sent on attach says every role is away already; where `epic.start` is then
refused, it MUST call `epic.afk` with `on` false if it had called it with `on` true.

**18.2.6** With `--follow`, `hmz epic start` MUST, once the epic has started, write what Section
18.3 states of every message from then on until the epic's `ended`, and exit as Section 18.3.4
states. Under `--json` it MUST first write the JSON document of Section 18.2.1 on a line of its own.

**18.2.7** A usage error of Section 18.2.2 under `--json` MUST be written as the document
`{"error": {"code": 400, "message": <what is wrong>}}`.

### 18.3. `hmz epic attach`

**18.3.1** `hmz epic attach` MUST attach with `replay` true, or false where `--no-replay` is given,
and MUST write each message of the host (Section 4.9 of [DAEMON]) as it comes: the history records
kept first, and then what happens.

**18.3.2** Under `--json`, in place of the one document of Section 16.7, it MUST write every
message as one JSON object and a line feed to standard output, unchanged and in the order the host
sent them, and nothing to standard error.

**18.3.3** Without `--json`, it MUST write each `event` as `hmz exec` writes it (Section 7.12), each
`printed` line to standard output, and to standard error a line for each `started`, `asked`,
`answered`, `said`, `withdrawn`, `stopping`, `notice`, `ended` and `gone`; the line of an `asked`
MUST name its role and its question id and be followed by each option, numbered from 1, and by its
schema as JSON where it has one, and the line of an `ended` MUST say how it ended, followed by
its `why` where that is not empty.

**18.3.4** It MUST exit once `live` has come where the `run` snapshot says no epic is going or
stopping, with status 0; otherwise at the first `ended` after `live`, with status 1 where its `how`
is `failed`, `crashed` or `refused` and 0 otherwise; with status 1 at `gone`, and where the session
ends first; and with status 130 where it is interrupted. Its exiting MUST NOT stop the epic.

### 18.4. `hmz epic say`, `answer`, `stop` and `board`

**18.4.1** `hmz epic say <text>` MUST call `epic.say` with `text` and, where `--to` is given, `to`.
Its JSON document MUST be `{"text": <text>, "to": <who or "">}`.

**18.4.2** `hmz epic answer` MUST call `epic.answer` with `question` the id `-q` or `--question`
gives, `text` `<text>` where it is given, and `value` the JSON `--value` gives where it is given; a
`--value` that is not JSON MUST be a usage error. Where no id is given it MUST read `pending` of
`epic.status` and answer the one question there; it MUST refuse, with status 1 and code 409, where
none waits and where more than one does, naming their ids. Its JSON document MUST be `{"question":
<id>}`.

**18.4.3** `hmz epic stop` MUST call `epic.stop`, or with `--force` `epic.force`. Its JSON document
MUST be `{"forced": <boolean>, "closed": <n>}`, `closed` being what `epic.force` answered, and 0
without `--force`.

**18.4.4** `hmz epic board <key> <value>` MUST call `epic.board` with `key` and `value`, and `hmz
epic board <key> --remove` with `value` `""`; the JSON document of each MUST be `{"key": <key>,
"value": <value or "">}`. `--remove` with no `<key>` MUST be a usage error. Otherwise `hmz epic
board` MUST read the messages sent on attach up to `live`, refusing with status 1 where the host
lets go before it, and write the `items` of the `board` snapshot among them, those whose `key` is `<key>`
where one is given: one line each with its key, its value, whose it is and who wrote it, in
columns. Its JSON document MUST then be `{"items": [...]}`, each item as the snapshot holds it,
or `{"items": null}` for an epic with no board.

### 18.5. `hmz epic claim`, `release`, `afk` and `status`

**18.5.1** `hmz epic claim <role>...` MUST call `epic.claim` for each role, with `take` true where
`--take` is given, and MUST then write the host's messages as `hmz epic attach` does, with
`--no-replay` as there, until the first `ended` after `live`, exiting as Section 18.3.4 states
except that it MUST NOT exit for no epic going. While it runs, each line read from standard input
that is not empty MUST answer (`epic.answer` with `text`) the oldest question of the last `pending`
snapshot whose role is one it claimed and which it has not answered, the lines in the order read;
an answer refused with code 400 MUST leave its question to the next line, and one refused
otherwise MUST leave it to the next `pending` snapshot to say whether it still waits. The claims end with the
command (Section 4.10.2.2 of [DAEMON]).

**18.5.2** `hmz epic release <role>` MUST call `epic.claim` with `take` true and then
`epic.release`, so that no frontend claims the role. Its JSON document MUST be `{"role": <role>}`.

**18.5.3** `hmz epic afk [<role>]` MUST call `epic.afk` with `on` true, or false where `--back` is
given, and `role` where one is given. Its JSON document MUST be `{"away": <boolean>, "role": <role
or "">}`.

**18.5.4** `hmz epic status` MUST call `hosts.status` and write one line with the host's `state`,
`flow`, `epic` and `task`, and then one line for each question of `pending`: its id, its role and
its text. Its JSON document MUST hold `workspace`, `slot`, `pid`, `started`, `state`, `run`,
`epic_kind`, `flow`, `epic`, `chat`, `task`, `pending`, `ended`, `attached`, `clients`, `budget`,
`usage`, `flows` and `calls`, each as `hosts.status` answered it (Section 4.6.4 of [DAEMON]), or
`null` where it answered none.

### 18.6. `hmz hosts`

**18.6.1** `hmz hosts list` MUST call `hosts.list` and `hosts.running` and write one line per host
of `hosts.list`, in its order: its workspace, its slot, its state, its flow and its task, in
columns. Its JSON document MUST be `{"hosts": [{"workspace", "slot", "pid", "started", "state",
"kind", "flow", "epic", "chat", "task", "asking"}]}`: `state`, `kind`, `flow`, `epic`, `chat`,
`task` and `asking` as `hosts.running` says them of that workspace and slot, and `idle`, `""` and
`[]` for a host it does not name. With `--running`, only the hosts `hosts.running` names MUST be
written.

**18.6.2** `hmz hosts stop` MUST call `hosts.stop` with the workspace and slot of Section 18.1.2.
Its JSON document MUST be `{"workspace": <path>, "slot": <slot>}`.

## 19. `hmz runs`

This section is reserved for `hmz runs`, the declared commands of `runs.*`. It states no requirement yet: the change that adds it writes this section, and no other, in the same change.

## 20. `hmz env`

This section is reserved for `hmz env`, the declared commands of `env.*` and `hosts.env.*`. It states no requirement yet: the change that adds them writes this section, and no other, in the same change.

## 21. `hmz flows`, `hmz flowverses` and `hmz workspaces`

This section is reserved for `hmz flows`, `hmz flowverses` and `hmz workspaces`, the declared commands of `flows.*`, `flowverses.*`, `workspaces.*` and `paths.*`. It states no requirement yet: the change that adds them writes this section, and no other, in the same change.

## 22. `hmz settings`, `hmz accounts` and `hmz nous`

This section is reserved for `hmz settings`, `hmz accounts` and `hmz nous`, the declared commands of `settings.*`, `accounts.*` and `nous.*`. It states no requirement yet: the change that adds them writes this section, and no other, in the same change.

## 23. `hmz runtimes`, `hmz easytier` and `hmz daemons`

This section is reserved for `hmz runtimes`, `hmz easytier` and `hmz daemons`, the declared commands of `runtimes.*` and `easytier.*`, and the daemons `--daemon` names. It states no requirement yet: the change that adds them writes this section, and no other, in the same change.

## 24. `hmz btw`, `hmz ai` and `hmz notices`

This section is reserved for `hmz btw`, `hmz ai` and `hmz notices`, the declared commands of `btw.*`, `aichan.*` and `notices.*`. It states no requirement yet: the change that adds them writes this section, and no other, in the same change.

## 25. `hmz skills`

This section is reserved for `hmz skills`, which installs for a user's harnesses the skill of using `hmz`. It states no requirement yet: the change that adds it writes this section, and no other, in the same change.

## 26. `hmz help`

This section is reserved for `hmz help`, which writes the declarations of every declared command for a person or as JSON. It states no requirement yet: the change that adds it writes this section, and no other, in the same change.

## 27. Security Considerations

This section states no requirement; it summarises the security-relevant properties the rest of this
document states.

- **Untrusted command-line input.** Every value `hmz exec` takes is parsed against a grammar and
  refused as a usage error where it does not match (Section 7.2 to Section 7.6); every refusal of a
  well-formed line happens before any agent has started (Section 7.7.1). Two values are passed on
  unchecked: the model of an agent, which goes to the harness as written (Section 7.4.7), and a
  bracketed ssh host, which goes to `ssh` as written (Section 7.5.7). A `vcs` or `path` flow
  reference names Python code that `hmz exec` loads and runs (Section 7.3), so a flow reference is
  as trusted as a program. `hmz exec` never installs a flow (Section 7.3.8).
- **Secrets on the standard streams.** No command writes the value of a credential; an account is
  written by its names only, and a URL is written with its user information and credentials removed
  (Section 4.3, Section 9.2.2). The answers of turns, the event stream of `--json` and a flow's
  traceback are written as the agents and the flow produced them (Section 7.12, Section 7.13), so
  they hold whatever those produced. The line `hmz web` writes to standard output carries the key
  of the address it serves (Section 8.2.4), and the code `hmz daemon pair` writes admits one device
  to the daemon until it is claimed or expires (Section 13.2.4).
- **Secrets on command lines.** hmz passes a secret to a process it starts with `--token-file`,
  never with `--token` (Section 11.2.4). The secret a user types after `--token` is nonetheless on
  that user's own command line. No option of `hmz exec` has an equivalent environment variable
  (Section 7.1.8).
- **Listening addresses.** `hmz web` listens on loopback addresses only (Section 8.2.2). `hmz
  internal anchor serve`, which is `coganchor anchor` (Section 11.2.12), refuses to listen on a
  non-loopback address without a token and refuses a client that presents another token (Section
  11.2.8, Section 11.2.9); listening or met through a broker, it speaks only TLS, inside which the
  token or ticket is proved and never sent, and `hmz internal anchor` refuses one that cannot prove
  it back (Section 11.2.17, Section 11.2.18). `hmz internal anchor rendezvous` listens on `0.0.0.0` by default
  (Section 11.2.10). `hmz daemon serve` makes this machine's daemon reachable on every listener it
  is given, each admitting only paired devices over mutual TLS or WebRTC (Section 13.2.1). `hmz
  relay serve` listens where it is told, on plain WebSockets, admits anybody, and carries only what
  is secured end to end (Section 14.2.1).
- **Services.** `hmz daemon install` makes the daemon start at login and keeps it running with its
  listeners (Section 13.2.6). `hmz daemon connect --stdio` gives whoever runs it, as this user, the
  daemon's socket on its standard streams (Section 13.2.3).
- **`hmz internal`.** These commands are the command lines hmz starts its own processes with and
  are not a public interface, yet each runs when a user types it (Section 11.1). `hmz internal
  cred` and `hmz internal fence` run a program only under the supervision or fence they were asked
  for, and do not run it where that cannot be arranged (Section 11.3.4, Section 11.4.3). `hmz
  internal hook`, `hmz internal tools` and `hmz internal cli` relay between their standard streams
  and a Unix socket named on the command line (Section 11.5 to Section 11.7).
- **Programs hmz runs.** `hmz update` runs `uv`, `pipx` or pip as found on `PATH` or in the running
  interpreter, and asks PyPI, or the source `HUMANIZE_RELEASES` names, for the newest release
  (Section 9.2, Section 9.3.1). A daemon with an `easytier:` listener can download EasyTier
  (Section 3.8.5.6 of [DAEMON]). `hmz web` opens a browser unless `--no-open` is given (Section
  8.2.5).

## 28. References

### 28.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[TUI]** "The Humanize Protocol: Terminal Interface", [`tui.md`](tui.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WIRE]** "The Humanize Protocol: Carriers, Sessions and RPC", [`wire.md`](wire.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).
