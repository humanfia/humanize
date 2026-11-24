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
  - [15.2. A turn: `start` and `say`](#152-a-turn-start-and-say)
  - [15.3. Exit of `start` and `say`](#153-exit-of-start-and-say)
  - [15.4. The chats written down](#154-the-chats-written-down)
  - [15.5. A chat where it is held](#155-a-chat-where-it-is-held)
  - [15.6. Harness sessions](#156-harness-sessions)
- [16. Declared commands](#16-declared-commands)
- [17. `hmz devices`](#17-hmz-devices)
  - [17.1. Synopsis](#171-synopsis)
  - [17.2. Behaviour](#172-behaviour)
- [18. `hmz epic` and `hmz hosts`](#18-hmz-epic-and-hmz-hosts)
  - [18.1. Synopsis](#181-synopsis)
  - [18.2. `hmz epic start`](#182-hmz-epic-start)
  - [18.3. `hmz epic attach`](#183-hmz-epic-attach)
  - [18.4. `hmz epic say`, `answer`, `face`, `stop`, `quit` and `board`](#184-hmz-epic-say-answer-face-stop-quit-and-board)
  - [18.5. `hmz epic claim`, `release`, `afk` and `status`](#185-hmz-epic-claim-release-afk-and-status)
  - [18.6. `hmz hosts`](#186-hmz-hosts)
- [19. `hmz runs`](#19-hmz-runs)
  - [19.1. Synopsis](#191-synopsis)
  - [19.2. Listing and reading](#192-listing-and-reading)
  - [19.3. Traces and timelines](#193-traces-and-timelines)
  - [19.4. Export and import](#194-export-and-import)
  - [19.5. Usage](#195-usage)
- [20. `hmz env`](#20-hmz-env)
  - [20.1. Synopsis](#201-synopsis)
  - [20.2. Reaching an environment](#202-reaching-an-environment)
  - [20.3. Environments and files](#203-environments-and-files)
  - [20.4. `hmz env exec`](#204-hmz-env-exec)
  - [20.5. `hmz env git`](#205-hmz-env-git)
  - [20.6. `hmz env term`](#206-hmz-env-term)
  - [20.7. Asking first](#207-asking-first)
- [21. `hmz flows`, `hmz flowverses` and `hmz workspaces`](#21-hmz-flows-hmz-flowverses-and-hmz-workspaces)
  - [21.1. Synopsis](#211-synopsis)
  - [21.2. `hmz flows`](#212-hmz-flows)
  - [21.3. `hmz flowverses`](#213-hmz-flowverses)
  - [21.4. `hmz workspaces`](#214-hmz-workspaces)
- [22. `hmz settings`, `hmz accounts` and `hmz nous`](#22-hmz-settings-hmz-accounts-and-hmz-nous)
  - [22.1. Synopsis](#221-synopsis)
  - [22.2. `hmz settings`](#222-hmz-settings)
  - [22.3. `hmz accounts`](#223-hmz-accounts)
  - [22.4. `hmz nous`](#224-hmz-nous)
- [23. `hmz runtimes`, `hmz easytier` and `hmz daemons`](#23-hmz-runtimes-hmz-easytier-and-hmz-daemons)
  - [23.1. Synopsis](#231-synopsis)
  - [23.2. `hmz runtimes`](#232-hmz-runtimes)
  - [23.3. `hmz easytier`](#233-hmz-easytier)
  - [23.4. `hmz daemons`](#234-hmz-daemons)
  - [23.5. `--daemon`](#235---daemon)
- [24. `hmz btw`, `hmz ai` and `hmz notices`](#24-hmz-btw-hmz-ai-and-hmz-notices)
- [25. `hmz skills`](#25-hmz-skills)
  - [25.1. Synopsis](#251-synopsis)
  - [25.2. The skill](#252-the-skill)
  - [25.3. Behaviour](#253-behaviour)
- [26. `hmz help`](#26-hmz-help)
  - [26.1. Synopsis](#261-synopsis)
  - [26.2. The help of `hmz`](#262-the-help-of-hmz)
  - [26.3. The help of a command](#263-the-help-of-a-command)
  - [26.4. `--json`](#264---json)
  - [26.5. Completion scripts](#265-completion-scripts)
  - [26.6. How a help is set](#266-how-a-help-is-set)
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
`web`, `daemon`, `relay`, `update` and `internal`.

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

**3.3.3** `hmz --help` MUST write the help of `hmz` that Section 26.2 specifies, which lists every
command with its summary under the group Section 26.2.2 places it in. The summaries of the commands
that are not declared commands (Section 16) MUST be:

```text
exec      run an agent flow in this directory
web       open this machine's epics in a browser on it
daemon    run, reach and install this machine's daemon
relay     relay daemons and the devices that reach them
update    update hmz to its newest release
internal  internal commands used by Humanize; do not run directly
```

and the summary of a declared command MUST be the one its declaration states.

**3.3.4** The help of a declared command MUST be what Section 16 states. Section 3.3.2 MUST hold of
each text in it other than what the command does and what it prints, each of which MUST be at most
one hundred words long: help is to be enough to use a command by.

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
specifies.

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

**5.2.10** `hmz chat start` and `hmz chat say` MUST exit with status 128 plus the signal number
where a signal ended them, as Section 15.3.5 specifies.

**5.2.11** A declared command that asks a daemon MUST exit with status 3 where the daemon cannot be
reached, did not answer in time, or went away under a call, as Section 16.9 specifies.

**5.2.12** A declared command MUST exit with status 130 where it is interrupted, as Section 16.14
specifies.

**5.2.13** `hmz runtimes check` MUST exit with status 4 where the runtime did not answer, as Section
23.2.6 specifies.

**5.2.14** `hmz env exec` MUST exit with status 5 where the command it ran did not exit with status
0, as Section 20.4.3 specifies.

**5.2.15** A declared command MUST NOT exit with a status other than 0, 1, 2, 3 and 130 and those
Section 5.2.10, Section 5.2.13 and Section 5.2.14 name.

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
longer than 15s and was left; `hmz backup run EPIC` sends it again`` to standard error and exit.

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
backup took longer than 60s and was left; `hmz backup run EPIC` sends it again`` to standard error, and
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
hmz backup run <epic> [--to <target>]... [--no-wait] [--timeout <seconds>]
hmz backup list [--target <target>]
hmz backup pull <key> --target <target>
```

**10.1.1** `hmz backup` MUST be a group of declared commands (Section 16) with the summary `back
epics up to git repositories, and download them again`, and Section 16 MUST hold of each of them.

**10.1.2** `--to` MUST be accepted any number of times, and `--timeout` MUST default to 600.

### 10.2. Backing an epic up

**10.2.1** `hmz backup run <epic>` MUST call `runs.backup` with `<epic>` as `name` and each `--to`
as `to`, where any is given, so that the daemon chooses the targets as Section 11.3.4.1 of [CORE]
states and refuses as Section 4.16.5 of [DAEMON] states.

**10.2.2** Without `--no-wait`, `hmz backup run` MUST then read the epic with `runs.get` until its
`backed` holds, for every target of `queued`, a record other than the one it held before the call
whose `why` is `manual`, for at most `--timeout` seconds. A `--timeout` of 0 or less MUST be as
`--no-wait`.

**10.2.3** For each target whose record has `ok` true, `hmz backup run` MUST write `<target>:
uploaded <at>` and a line feed to standard output, `<at>` being the record's `at`. Where every
target has, its JSON document MUST be `{"queued": [<target>...], "backed": {<target>: {"at", "ok",
"error", "why"}}}`.

**10.2.4** Where any target's record has `ok` false, `hmz backup run` MUST end as a declared command
the daemon refused (Section 16.7 to Section 16.9), its message being `<target>: failed, <error>
<at>` for each such target, joined by ` · `; without `--json` it MUST first write the lines of
Section 10.2.3 for the targets that took the epic.

**10.2.5** With `--no-wait`, `hmz backup run` MUST call no method but `runs.backup`; it MUST write `Uploading to
<targets>` and a line feed to standard output, `<targets>` being `queued` joined by `, `, and its
JSON document MUST be `{"queued": [<target>...], "backed": {}}`.

**10.2.6** Where the wait of Section 10.2.2 ends before every target has a record, `hmz backup run`
MUST end as a declared command whose daemon did not answer in time, with the message `The backup of
<epic> did not finish within <seconds> seconds, and carries on in the daemon.`, and MUST NOT stop
the backup.

### 10.3. Listing

**10.3.1** `hmz backup list` without `--target` MUST call `settings.get` and write one line per
target of its `backup.targets`, in their order: its name, its URL, its branch, its policies joined
by `,`, and `default` where `backup.defaults` names it, in columns. Its JSON document MUST be
`{"targets": [{"name", "url", "branch", "policies", "every"}], "defaults": [<target>...]}`.

**10.3.2** Where there is no target, `hmz backup list` without `--target` and without `--json` MUST
write `No backup target.` and a line feed to standard error, and MUST exit with status 0.

**10.3.3** `hmz backup list --target <target>` MUST call `backups.epics` and write one line per
epic or chat the target holds, in the daemon's order: its key, how it ended or `unfinished`, its
flow or `chat` for a chat, `here` where this machine holds it, and its task with white space runs
collapsed and cut to 60 characters, in columns. Its JSON document MUST be `{"epics": [...]}`, each
entry holding what `backups.epics` answers of it (Section 4.16.8.1 of [DAEMON]).

### 10.4. Downloading

**10.4.1** Where `<key>` holds a `/`, `hmz backup pull <key> --target <target>` MUST call
`backups.pull` with it as `key`.

**10.4.2** Where `<key>` holds no `/` it is an epic's name or a chat's: `hmz backup pull` MUST call
`backups.epics`, and MUST call `backups.pull` with the key of the one entry whose `epic` is
`<key>`. Where no entry is, it MUST end as a declared command the daemon refused with the message
`<target> holds no epic or chat <key>.`; where more than one is, with `<target> holds <key> from
more than one machine, name one of: <keys>.`, `<keys>` being their keys joined by `, `; in neither
case MUST it call `backups.pull`.

**10.4.3** Once the daemon has downloaded it, `hmz backup pull` MUST write the name `backups.pull`
answered and a line feed to standard output. Its JSON document MUST be `{"name": <name>}`.

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
hmz daemon install
hmz daemon uninstall
```

**13.1.1** `hmz daemon` MUST take a subcommand, `serve`, `connect`, `install` or `uninstall`;
anything else MUST be a usage error. Making a pairing code and listing and revoking the paired
devices are `hmz devices` (Section 17): `pair` and `devices` MUST NOT be subcommands of `hmz
daemon`.

**13.1.2** `--listen` MUST be accepted any number of times, each a listener spec of Section 3.9.2 of
[DAEMON]; another value MUST be a usage error saying `<spec> is not a listener.`

**13.1.3** `connect` MUST take `--stdio`, and without it MUST be a usage error.

**13.1.4** `install` and `uninstall` MUST take no option.

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

**13.2.4** `hmz daemon install` and `hmz daemon uninstall` MUST write, enable and start, or stop,
disable and remove, the service of Section 3.9.6 of [DAEMON], and MUST write `hmz daemon: installed
<path>` or `hmz daemon: uninstalled <path>` to standard output, `<path>` the file of the service.

### 13.3. Exit

**13.3.1** `hmz daemon serve` MUST exit with status 0 once stopped as Section 13.2.1 specifies.

**13.3.2** Where a daemon is already running, `hmz daemon serve` MUST write `hmz: a daemon is
already running (pid <pid>)` to standard error and exit with status 1.

**13.3.3** `hmz daemon connect --stdio` MUST exit with status 0 where its standard input or the
daemon ended the connection.

**13.3.4** Where the daemon cannot be reached or started, `hmz daemon connect` MUST write `hmz: the
daemon cannot be reached: <why>` to standard error and exit with status 1, and where it is of
another protocol version, the refusal of Section 3.7.5 of [DAEMON] and exit with status 1.

**13.3.5** `hmz daemon install` and `hmz daemon uninstall` MUST write `hmz: hmz daemon install runs
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
hmz chat start [-a <agent>] [-e <env>] [-w <dir> | --no-folder] [--worktree]
               [--permission <permission>] [--prefer native|flow] [--remember]
               [--detach] [--events] [--] <message>
hmz chat say <chat> [--detach] [--events] [--] <message>
hmz chat list [-w <dir> | --all] [--archived] [-q <text>] [--limit <n>] [--offset <n>]
hmz chat show <chat> [--trace]
hmz chat rename <chat> <title>
hmz chat fork <chat>
hmz chat archive <chat>
hmz chat unarchive <chat>
hmz chat delete <chat> [-y]
hmz chat stop <chat>
hmz chat set <chat> [--permission <permission>] [--prefer native|flow]
hmz chat move <chat> <env>
hmz chat agent <chat> <agent>
hmz chat commands <chat>
hmz chat backup <chat> [--to <target>]...
hmz chat harness list [-w <dir>] [--limit <n>] [--offset <n>]
hmz chat harness show <harness> <session> [-w <dir>] [--trace]
hmz chat harness adopt <harness> <session> [-w <dir>] [-a <agent>]
```

**15.1.1** `hmz chat` MUST be a group of declared commands (Section 16) with the summary `start chats
with an agent, send messages, and manage them`, holding the commands of this synopsis in this order,
`harness` being a group of three under it. `hmz chat` MUST NOT read or write a chat's files: each
command MUST do what it does by the methods of Section 4.25 of [DAEMON] this section names for it,
through `Client.chats` (Section 4.24 of [PYTHON]).

**15.1.2** `<chat>` MUST be a chat's id, which is the name of its directory (Section 8.2.12 of
[CORE]) and what `chat.list` answers as `id`; `hmz chat` MUST NOT name a chat an epic.

**15.1.3** `<agent>` MUST be one agent written as the text of an `-a` item of Section 7.4 after
`<role>=`, `<env>` one env written as the text of an `-e` item of Section 7.5 after `<role>=`, and
`<permission>` one of `read-only`, `workspace-write` and `danger-full-access`.

**15.1.4** `-w` and `--workspace` MUST be the same option and MUST name the workspace a command is
about, as Section 16.13 states.

**15.1.5** `<message>` MUST be exactly one positional argument; a message that begins with `-` MUST
be given after `--`.

**15.1.6** Where a command takes a chat no host holds and its method takes a workspace and a slot
(`chat.say`, `chat.stop`, `chat.set`, `chat.commands`), it MUST first carry the chat on
with nothing said (`chat.start` with `resume` the id and an empty `task`, Section 4.25.1.9 of
[DAEMON]) and MUST ask the host that then holds it.

### 15.2. A turn: `start` and `say`

**15.2.1** `hmz chat start` MUST start a chat (Section 8 of [CORE]) on a new chat slot of the
workspace (`chat.start` with `slot` `chat:`), `<message>` being its first message, with `-a` as
`agent`, `-e` as `env`, `--permission` as `permission`, `--prefer` as `prefer`, `--worktree` as
`worktree` `true` and `--remember` as `remember` `true`, each where it is given.

**15.2.2** Without `-a`, `hmz chat start` MUST use the chat agent the workspace remembers
(`settings.get`, Section 3.5.1.9 of [FILES]), and MUST refuse where none is remembered, and with
`--no-folder`, saying to name one with `-a`. Without `--remember` it MUST NOT change the remembered
setup of any workspace.

**15.2.3** With `--no-folder`, `hmz chat start` MUST start the chat in a folderless workspace made
for it alone (`epic.attach` with `scratch` `true` and `slot` `chat:`, Section 4.7.1.3 of [DAEMON],
then `chat.start` on the workspace and slot it answers), and MUST let that host go as a frontend
once the chat is started. `--no-folder` with `--worktree` MUST be refused before anything is asked
of the daemon.

**15.2.4** `hmz chat say` MUST say `<message>` to the chat as its next line (`chat.say`) on the host
that holds it (Section 15.1.6). A `<message>` of white space alone MUST be refused before anything is
asked of the daemon.

**15.2.5** Unless `--detach` is given, `start` and `say` MUST then follow the chat's host as one
more frontend (`epic.attach`) until the turn is done, the chat has ended or its host has gone, and
MUST then let the host go (`epic.detach`). The turn is done once the line has been taken -- a turn
opened or answered after it, or the chat asked for its next line -- and the chat is between turns.
`say` MUST attach before it says the line, with `replay` `false`, and MUST NOT take for the turn
anything the host said before it said that the line was taken (an `answered` record, a `said`
record of that text, the line among `given` of the `waiting` snapshot, or an `unheld` record of it).

**15.2.6** Once the turn is done, a command that started the chat's host -- `start`, and `say` to a
chat no host held -- MUST end the chat there with an empty next message (Section 8.4.8 of [CORE])
and MUST wait, for at most ten seconds, until no host holds the chat. `say` to a chat a host held
already MUST leave that host as it is.

**15.2.7** Without `--json` and `--events`, `start` and `say` MUST draw the turn on standard error
and write its answer to standard output as Section 7.12.1 to Section 7.12.5 state for `hmz exec`;
what a `!` command the chat ran printed MUST be written to standard output, and what the chat says
beside an answer -- why it refused a line, that its conversation is a new one -- to standard error.
`start` MUST first write `Chat <id>` to standard error once `chat.start` is answered.

**15.2.8** With `--json`, `start` and `say` MUST write the one document `{"chat", "workspace",
"slot", "answer", "notes", "detached"}`: the chat's id, its workspace, the slot of the host that held
it, what the last `result` of the turn said (`""` for none), what the chat said beside an answer, and
whether `--detach` was given.

**15.2.9** With `--events`, `start` and `say` MUST write each history record of the turn (Section
4.9.2 of [DAEMON]) to standard output as it arrives, one JSON object a line, then the document of
Section 15.2.8 as the last line, and MUST otherwise behave as with `--json`; this is the one
exception to Section 16.7.

**15.2.10** With `--detach`, `start` and `say` MUST return once the line is said, attaching to no
host and ending none; without `--json` they MUST write the chat's id to standard output.

### 15.3. Exit of `start` and `say`

**15.3.1** `start` and `say` MUST exit with status 0 once the turn is done, or the chat ended without
failing.

**15.3.2** Where the turn failed -- a `failed` event, an ending of `failed` or `crashed`, or a host
that went -- they MUST exit with status 1 and MUST write what the harness said, else why the chat
ended: as Section 16.8 states without `--json`, and with it as the document `{"error": {"code": 0,
"message"}, "chat", "workspace", "slot"}` (Section 8.4.9 of [CORE]).

**15.3.3** What the daemon refuses MUST be written and exit as Section 16 states; where the session
with the daemon ends while the turn is followed, or under a call of theirs (the error 503 of
Section 4.21.7 of [PYTHON]), they MUST exit with status 3 as Section 16 states for a daemon that
cannot be reached.

**15.3.4** `start` and `say` MUST NOT stop a turn: `hmz chat stop` does.

**15.3.5** On `SIGINT`, `SIGTERM` or `SIGHUP`, `start` and `say` MUST leave the chat to its host
(Section 8.8.6 of [CORE]), ending no host, and exit with status 128 plus the number of the signal;
a signal ignored when the command started MUST stay ignored.

### 15.4. The chats written down

**15.4.1** `hmz chat list` MUST call `chat.list` with the workspace -- with none under `--all` --
`--archived` as `archived` `true`, `-q` as `q`, `--limit` and `--offset`, and MUST write one line
per chat, in the daemon's order: its id, its `state` (Section 4.25.5.3 of [DAEMON]) and its title
with white space runs collapsed and cut to 60 characters, in columns. Its document MUST be
`chat.list`'s result.

**15.4.2** `hmz chat show <chat>` MUST call `chat.get`, with `trace` `true` under `--trace`, and MUST
write one line per field that says something, its name and its value: `id`, `title`, `state`,
`agent`, `model`, `permission`, `env`, `workdir`, `workspace`, `began`, `updated`, `archived`,
`slot`, `prefer`, `forked`, `adopted` and `task`; then, under `--trace`, for each session of the
trace an empty line, a line naming it and the name of each of its actions, indented. Its document
MUST be `chat.get`'s result.

**15.4.3** `rename`, `archive`, `unarchive` and `agent` MUST call the method of their name
(`chat.rename` with `title`, `chat.agent` with `agent`) and MUST write the chat's line as Section
15.4.1 states it, as the chat then stands; the document of each MUST be the chat row answered.

**15.4.4** `hmz chat fork <chat>` MUST call `chat.fork` and write the id of the new chat; its
document MUST be `{"chat": <id>}`.

**15.4.5** `hmz chat delete <chat>` MUST delete the chat (`chat.delete`), write nothing to standard
output without `--json`, and the document `{"deleted": <id>}` with it. It MUST first ask as
Section 16.12 states, naming the chat by its line of Section 15.4.1 (`chat.get`) and saying that it
cannot be brought back; where nobody can be asked it MUST NOT read the chat.

**15.4.6** `hmz chat backup <chat>` MUST call `chat.backup`, with each `--to` as `to` where any is
given, and MUST write each target the backup was queued for, a line apiece; its document MUST be
`{"queued": [<target>]}`.

### 15.5. A chat where it is held

**15.5.1** `hmz chat stop <chat>` MUST call `chat.stop` and write `Stopped`; its document MUST be
`{"stopped": <id>}`.

**15.5.2** `hmz chat set <chat>` MUST call `chat.set` with `--permission` as `permission` and
`--prefer` as `prefer`, each where it is given, then `chat.commands`, and MUST write the chat's
`permission`, `prefer` and `prefer_from` as they then are, a line apiece; its document MUST be
`{"chat", "permission", "prefer", "prefer_from"}`.

**15.5.3** `hmz chat move <chat> <env>` MUST call `chat.move` on the host that holds the chat and
write the env it answers; where no host holds the chat it MUST instead carry the chat on in that
env with nothing said (`chat.start` with `resume`, `env` and an empty `task`, Section 4.25.1.10 of
[DAEMON]) and write the chat's `env` as `chat.get` then answers it. Its document MUST be `{"chat",
"env"}`.

**15.5.4** `hmz chat commands <chat>` MUST call `chat.commands` and write one line per entry: its
sigil and name, its `source` and its `about`, in columns; its document MUST be `chat.commands`'s
result.

### 15.6. Harness sessions

**15.6.1** `hmz chat harness list` MUST call `chat.harness.list` with the workspace, `--limit` and
`--offset`, and MUST write one line per session: its harness, its id, when it was last written and
its title, collapsed and cut as a chat's is, in columns. Its document MUST be `chat.harness.list`'s
result.

**15.6.2** `hmz chat harness show <harness> <session>` MUST call `chat.harness.get`, with `trace`
`true` under `--trace`, and MUST write the session's row a field a line, then its trace as Section
15.4.2 states; its document MUST be the method's result.

**15.6.3** `hmz chat harness adopt <harness> <session>` MUST call `chat.harness.adopt`, with `-a` as
`agent` where it is given, and write the id of the new chat; its document MUST be `{"chat": <id>}`.

## 16. Declared commands

**16.1** A _declared command_ is a command written as one declaration: its name, its summary, what it
takes, example lines, what it prints, the fields of its JSON document, its exit statuses and the
methods of [OPENRPC] it calls. Section 10, Section 15 and Section 17 onwards specify the declared
commands; `exec`, `web`, `daemon`, `relay`, `update` and `internal` are not declared commands.

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
answered one (Section 6.6 of [WIRE]), `503` where the daemon cannot be reached, `504` where it did
not answer in time, `400` for a usage error (16.10), and `0` where the command itself refused.

**16.8** Without `--json`, a declared command that did not do what it was asked MUST write `hmz
<command>: <message>` and a line feed to standard error, `<command>` being its words after `hmz`.

**16.9** A declared command MUST exit with status 0 where it did what it was asked; 1 where the
daemon refused, where the command itself refused, and where it asked and was not answered yes
(16.12); 2 on a usage error; 3 where the daemon cannot be reached or did not answer in time, and
where the session with the daemon ended under a call (the error 503 of Section 4.21.7 of [PYTHON]),
which MUST be said as a daemon that cannot be reached is; and 130 where it was interrupted (16.14).
An error 503 the daemon answered over a session that goes on is a refusal, and MUST exit with
status 1. A declared command MUST NOT exit with another status but one its own section assigns it
and its help states.

**16.10** A usage error of a declared command MUST be written to standard error as `hmz <command>:
<what is wrong>`, followed by a line naming the `--help` to run, and MUST exit with status 2. A
command that finds, after its line was parsed, that the line cannot be read -- a value that is not
what its option takes, options that cannot be given together -- MUST end as a usage error before it
writes anything to a daemon; under `--json` it MUST instead write the document of 16.7 with `code`
`400`, and nothing to standard error.

**16.11** Every text a declared command writes that is not data MUST be a text the web interface
writes ([WEB]) wherever that interface has a text saying the same thing, word for word in its
English, and MUST otherwise be a text kept with hmz for that purpose; a declared command MUST NOT
compose such a text where it is written.

**16.12** A declared command that removes or discards something that cannot be brought back MUST
ask first, and MUST take `-y`/`--yes`: with it, it MUST NOT ask and MUST go on as though answered
yes. Without it, where `--json` is absent and standard input is a terminal, it MUST write its
question and ` [y/N] ` to standard error and read one line of standard input; `y` or `yes`, in
either case, is yes and anything else is not. Where the answer is not yes it MUST change nothing
and refuse, saying `Nothing was changed.`; where nobody can be asked -- `--json` is given or
standard input is not a terminal -- it MUST ask nothing, change nothing and refuse, saying to run
it again with `-y`. Either refusal MUST be said as a refusal is (16.7, 16.8), `code` being `0`, and
MUST exit with status 1; the help of such a command MUST state that status 1 is a refusal by the
daemon or an answer that was not yes.

**16.13** Where a declared command takes `-w`/`--workspace <dir>` to name a workspace of the
daemon's machine, a `<dir>` beginning `~` MUST be sent as written, for the daemon to expand; any
other MUST be sent as an absolute path, a relative one read against the directory the command is
run in, with no link followed; and where the option is absent that directory MUST be sent, but
where the command's own section states otherwise. Which workspace a path names, its links
followed, is the daemon's to say (Section 4.5.2 of [DAEMON]).

**16.14** A declared command that is interrupted (`SIGINT`) MUST exit with status 130, MUST write no
traceback and nothing more to either stream -- under `--json` too, 16.7 notwithstanding -- and MUST
let go of its session; whatever the daemon holds goes on. `hmz chat start` and `hmz chat say`,
which Section 15.3 has take `SIGTERM` and `SIGHUP` the same way, MUST exit as that section states.

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
hmz epic face <question> [-w <dir>] [--slot <slot>]
hmz epic stop [--force] [-w <dir>] [--slot <slot>]
hmz epic quit [-w <dir>] [--slot <slot>]
hmz epic board [<key> [<value>]] [--remove] [-w <dir>] [--slot <slot>]
hmz epic claim [<role>]... [--take] [--no-replay] [-w <dir>] [--slot <slot>]
hmz epic release <role> [-w <dir>] [--slot <slot>]
hmz epic afk [<role>] [--back] [-w <dir>] [--slot <slot>]
hmz epic status [-w <dir>] [--slot <slot>]
hmz hosts list [--running]
hmz hosts open [-w <dir>] [--slot <slot>]
hmz hosts detach [-w <dir>] [--slot <slot>]
hmz hosts stop [-w <dir>] [--slot <slot>]
```

**18.1.1** `hmz epic` and `hmz hosts` MUST each be a group of declared commands (Section 16), with
the summaries `start, follow and steer an epic held by this daemon` and `list and close the hosts
this daemon holds epics and chats in`.

**18.1.2** `-w` and `--workspace` MUST be the same option. Every command that takes it MUST name a
host (Section 4.6 of [DAEMON]) by `workspace`, the directory `-w` gives as Section 16.13 states, and
by `slot`, what `--slot` gives, or `""` where it is absent.

**18.1.3** A command of `hmz epic` other than `status` MUST attach to that host as one frontend
(`epic.attach` with `replay` false but where its paragraph states otherwise, Section 4.7.1 of
[DAEMON]), make its calls on the epic subscription that opens, and let the frontend go
(`epic.detach`) before it exits, however it ends. `hmz epic status` and the commands of `hmz hosts`
MUST NOT attach to a host.

**18.1.4** A command of `hmz epic` other than `start` and `status` MUST first call `hosts.status`
for that host and MUST NOT attach where it is refused: of `hmz epic`, only `hmz epic start` starts
a host.

**18.1.5** `hmz epic start`, `hmz epic attach` and `hmz epic claim` MUST exit with status 130 where
they are interrupted (16.14), and MUST NOT stop the epic by it; their help MUST state that the
epic goes on.

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
ends first; and with status 130 where it is interrupted (16.14). Its exiting MUST NOT stop the epic.

### 18.4. `hmz epic say`, `answer`, `face`, `stop`, `quit` and `board`

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

**18.4.5** `hmz epic face <question>` MUST read the messages sent on attach up to `live`, refusing
with status 1 where the host lets go before it, and find among the `pending` snapshot the question
whose `question` is `<question>`. Where none is it MUST refuse with code 404, saying `Question
<question> is not waiting.`, and where that question's `face` is `null`, saying `Question
<question> has no face.`; in neither case MUST it call `epic.face`. Otherwise it MUST call
`epic.face` (Section 4.8.10 of [DAEMON]) with the `hash` of that face, and write the `html`
answered to standard output exactly, with no line feed added. Its JSON document MUST be
`{"question": <question>, "title": <title>, "html": <html>}`. It MUST NOT run or render the HTML.

**18.4.6** `hmz epic quit` MUST call `epic.quit`, which closes the host as Section 4.13.6 of
[DAEMON] states: every waiting question withdrawn, every waiting line dropped, every epic stopped,
every frontend let go and every side conversation closed, the host process exiting within 15
seconds. It MUST write `Host closed.`, and its JSON document MUST be `{"workspace": <path>, "slot":
<slot>}`, as `epic.attach` answered them.

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

**18.6.3** `hmz hosts open` MUST call `hosts.open` (Section 4.6.2.3 of [DAEMON]) with the workspace
and slot of Section 18.1.2, which starts that host where none is and attaches nothing to it, and
MUST write one line: the host's process id, its workspace and its slot, in columns. Its JSON
document MUST be `{"pid", "workspace", "started", "kind", "protocol", "slot"}` as `hosts.open`
answered them, `slot` being the slot made where `--slot` was `exec:` or `chat:` alone.

**18.6.4** `hmz hosts detach` MUST call `hosts.detach` (Section 4.6.3.2 of [DAEMON]) with the
workspace and slot of Section 18.1.2, which lets every attached frontend go and leaves every epic
running, and MUST write how many were let go. Its JSON document MUST be `{"workspace": <path>,
"slot": <slot>, "let_go": <n>}`.

## 19. `hmz runs`

### 19.1. Synopsis

```text
hmz runs list [--workspace <path>] [--status <status>] [--flow <name>] [-q <text>]
              [--offset <n>] [--limit <n>]
hmz runs show <name>
hmz runs trace <name>
hmz runs timeline <name> [--spans]
hmz runs span <name> <id> [--layout <layout>]
hmz runs export <name> [-o <file>]
hmz runs import <file> [--there]
hmz runs usage [--days <n>] [--workspace <path>]
```

**19.1.1** `hmz runs` MUST be a group of declared commands (Section 16) with the summary `list, read
back, export and import epics, and total their spend`.

**19.1.2** `--status` MUST be one of `running`, `done`, `failed`, `stopped` and `unfinished`, and any
other MUST be a usage error. `-q` MUST also be spelled `--query`, and `-o` `--output`. `--limit`
MUST default to 50 and `--days` to 30.

**19.1.3** A `--workspace <path>` MUST be told to the daemon as an absolute path: `<path>` with a
leading `~` expanded and, where it is relative, taken from the working directory.

### 19.2. Listing and reading

**19.2.1** `hmz runs list` MUST call `runs.list` with `--workspace` as `workspace`, `--status` as
`status`, `--flow` as `flow`, `-q` as `q`, `--offset` as `offset` and `--limit` as `limit`, each
where it is given, and write one line per epic of `runs`, in the daemon's order: its `name`, `how`,
`flow`, `began` and `task`, in columns. Its JSON document MUST be what `runs.list` answers: `runs`,
`total`, `offset`, `limit`, `counts` and `flows` (Section 4.16.1.2 of [DAEMON]).

**19.2.2** Where `offset` plus the number of epics listed is less than `total`, `hmz runs list`
without `--json` MUST write `<shown> of <total> epics listed; pass `--offset <next>` for the next
ones.` and a line feed to standard error, `<shown>` being the number listed and `<next>` the
`offset` of the first epic not listed.

**19.2.3** `hmz runs show <name>` MUST call `runs.get` and write one line per field of its answer
but `task`, the field's name and its value in columns, in the answer's order, and then `task` on a
line of its own followed by each line of the task indented by two spaces. A value that is true MUST
be written `yes`, false `no`, `null` as nothing, a text with its white space runs collapsed, and a
list or an object as JSON on one line. Its JSON document MUST be what `runs.get` answers (Section
4.16.3.1 of [DAEMON]).

### 19.3. Traces and timelines

**19.3.1** `hmz runs trace <name>` MUST call `runs.trace` and write, for each session of
`sessions`, a line of its `key` and its `agent`, then one line per action indented by two spaces:
its `at`, its `seconds` to three decimal places, its `category` and its `name`, in columns. Its
JSON document MUST be `{"sessions": [...]}`.

**19.3.2** `hmz runs timeline <name>` MUST call `runs.timeline` and write, for each process, a line
of its `id`, `kind`, name, label, and its `start` and `end` in seconds to three decimal places,
leaving out a name or a label that is empty; then, for each of its tracks, a line indented by two
spaces of the track's name and `<count> span` or `<count> spans`, `span` where `<count>` is 1. Its
JSON document MUST be the timeline (Section 10.6.2 of [CORE]).

**19.3.3** With `--spans`, `hmz runs timeline` MUST write after each track one line per span of it,
indented by four spaces: its identifier (Section 10.6.2.9 of [CORE]), its start and its duration in
seconds to three decimal places, its category and its name, in columns.

**19.3.4** `hmz runs span <name> <id>` MUST call `runs.span` with `--layout` as `layout`; without
`--layout` it MUST first call `runs.timeline` and give that timeline's `layout`. It MUST write the
span as Section 19.2.3 writes an epic, `args` in place of `task` and written as JSON indented by two
spaces. Its JSON document MUST be what `runs.span` answers.

### 19.4. Export and import

**19.4.1** `hmz runs export <name>` MUST call `runs.bundle`, read the whole file of its `handle`
with `files.read`, and end the handle with `files.close`, however the reading went.

**19.4.2** The file MUST be written in the directory `-o` names, under the `filename` the daemon
answered, where `-o` is a directory or ends in a path separator, that directory being made where it
is not there; at `-o` otherwise; and in the working directory under that `filename` without `-o`; a file already there MUST be replaced, and MUST be left as it was where the
export fails.

**19.4.3** `hmz runs export` MUST write the absolute path of the file and a line feed to standard
output. Its JSON document MUST be `{"path": <path>, "filename": <filename>, "size": <bytes>}`.

**19.4.4** `hmz runs import <file>` MUST send the file to the daemon with `files.create` and
`files.write`, `name` being the file's own name, and MUST then call `runs.import` with the handle;
where the import is refused it MUST end the handle with `files.close`.

**19.4.5** `hmz runs import <file> --there` MUST send nothing, and MUST call `runs.import` with
`<file>`, as it was written, as `path`.

**19.4.6** `hmz runs import` MUST write `Imported <name>` and a line feed to standard output, and,
where the answer's `resumable` is false and its `why` is not empty, `Imported · not resumable here:
<why>` and a line feed after it. Its JSON document MUST be what `runs.import` answers: `name`,
`workspace`, `resumable` and `why`.

**19.4.7** Where the file of this machine cannot be read or written, `hmz runs export` and `hmz runs
import` MUST end as a declared command the daemon refused, with what the operating system said as
the message.

### 19.5. Usage

**19.5.1** `hmz runs usage` MUST call `runs.usage` with `--days` as `days` and `--workspace` as
`workspace`, where it is given. Its JSON document MUST be what `runs.usage` answers (Section
4.16.9.1 of [DAEMON]).

**19.5.2** Without `--json`, `hmz runs usage` MUST write one table, in columns: the line `Flow`,
`Epics`, `Cost`, `Output tokens`, `Time working`; one line per flow of `flows`, its `flow`, `runs`,
`money`, `tokens` and `worked`; the line `Day`, `Epics`, `Cost`, `Output tokens`, `Time working`;
one such line per day of `days` whose `runs` is not 0, its `day` first; and the line `Total` with
those figures of `whole`.

## 20. `hmz env`

### 20.1. Synopsis

```text
hmz env list
hmz env ls [<path>]
hmz env stat <path>
hmz env cat <path> [--offset <n>] [--length <n>]
hmz env find [<name>] [--limit <n>]
hmz env search <query> [--regex] [--case] [--glob <glob>] [--limit <n>]
hmz env write <path> [--from <file>] [--if-match <etag>]
hmz env mkdir <path>
hmz env mv <path> <to>
hmz env rm <path> [-y]
hmz env exec [--seconds <n>] [--env <role>] -- <argv>...
hmz env git status
hmz env git diff [<path>...] [--staged]
hmz env git log [--limit <n>]
hmz env git stage (<path>... | -A)
hmz env git unstage (<path>... | -A)
hmz env git discard (<path>... | -A) [-y]
hmz env git commit -m <text> [--amend] [-a]
hmz env git snapshots
hmz env git rewind <ref> [-y]
hmz env term open [--term <id>] [--cols <n>] [--rows <n>]
hmz env term list
hmz env term close <term>
```

**20.1.1** `hmz env` MUST be a group of declared commands (Section 16) with the summary `work in the
environments of a chat or an epic: their files, git and terminals`; `hmz env git` and `hmz env term`
MUST be groups under it.

**20.1.2** Every command of `hmz env` MUST take `-w`/`--workspace <dir>`, `--slot <slot>` and `--chat
<id>`, which name a host: the host of `--slot` in the workspace `--workspace`, the working directory
where `--workspace` is absent and the workspace's own host where `--slot` is absent; or, with
`--chat`, the host `chat.get` says that chat is going on, whatever `--workspace` and `--slot` say.
`--workspace` MUST be read as Section 16.13 states.

**20.1.3** Every command of `hmz env` but `list` and `exec` MUST take `--env <env>`, and MUST work in
the environment of the host's `envs` snapshot (Section 4.24.2 of [DAEMON]) whose `id` is `<env>`,
else whose `chain` is, else whose `role` is; where `--env` is absent, in the first environment that
is available and open, else the first. It MUST fail as a refusal does (16.7, 16.8), with status 1,
with `There is no environment <env>.` where none is so named, and with the web interface's text for
a host that has no environment where the snapshot is empty.

### 20.2. Reaching an environment

**20.2.1** A command of `hmz env` other than `exec` MUST reach its host as one frontend of it: it
MUST attach with `epic.attach`, `replay` `false`, make its calls to the environment (Section 4.24 of
[DAEMON]) on that subscription, and leave with `epic.detach` before it exits.

**20.2.2** Such a command MUST NOT start a host: where no host holds the workspace and slot it MUST
fail with the refusal of `hosts.status` (Section 4.6.1.1 of [DAEMON]), and for a chat no host holds
with `This chat has folded away.`

**20.2.3** A command that finds the `envs` snapshot empty once the host is live MUST wait up to two
seconds for the host to send one that is not, before it reads the snapshot as empty.

### 20.3. Environments and files

**20.3.1** `hmz env list` MUST write one line per environment of the snapshot, in its order: its
`id`, `chain`, `backend`, `workdir`, its `caps` joined by commas, and the web interface's word for
closed where it is not open or for unavailable where it is not available. Its JSON document MUST be
`{"workspace", "slot", "envs": [...]}`, `workspace` and `slot` as `epic.attach` answered them and
each of `envs` the fields of Section 4.24.2.2 of [DAEMON].

**20.3.2** `hmz env ls [<path>]` MUST call `env.list`, `<path>` being `.` where absent, and write one
line per entry in the order answered: `d` for a directory, `-` for a file, `l` for a link and `?`
otherwise; its size; when it last changed, in local time; and its name, followed by `/` for a
directory and by ` -> <target>` for a link. Its JSON document MUST be `{"path": <path>, "entries":
[{"name", "kind", "size", "mtime", "target"}]}`, `target` being `null` for what is not a link.

**20.3.3** `hmz env stat <path>` MUST call `env.stat` and write that entry as `ls` writes one, with
its absolute path for its name. Its JSON document MUST be `{"path", "name", "kind", "size", "mtime",
"target"}`, `path` being the absolute path answered.

**20.3.4** `hmz env cat <path>` MUST write the bytes of the file to standard output and nothing
else. With neither `--offset` nor `--length` it MUST write the whole file, read with as many calls
of `env.read` as its length takes, and MUST read it again from its start where its `etag` changed
between two of them; with either, it MUST make one call of `env.read` with them. Its JSON document
MUST be `{"path", "text", "size", "mtime", "etag", "eof"}`, `text` being what was read as UTF-8 with
U+FFFD for each byte that is not, and the rest as `env.read` answered them.

**20.3.5** `hmz env find [<name>]` MUST call `env.find` with `--limit` as `limit`, and MUST write the
paths answered that contain `<name>`, compared without regard to case, one a line; every path where
`<name>` is absent. Its JSON document MUST be `{"paths": [...], "truncated": <truncated>}`.

**20.3.6** `hmz env search <query>` MUST call `env.search` with `--regex` as `regex`, `--case` as
`case`, `--glob` as `glob` and `--limit` as `limit`, each sent only where given, and MUST write one
line per match, `<path>:<line>:<column>:<text>`. Its JSON document MUST be `{"matches": [{"path",
"line", "column", "text"}], "truncated": <truncated>}`.

**20.3.7** `hmz env write <path>` MUST call `env.write` with, as `data`, every byte of the file
`--from` names on the machine it is run on, or of standard input where `--from` is absent, and with
`--if-match` as `if_match` where it is given, the empty value included. Its JSON document MUST be
`{"path", "etag", "size", "mtime"}`, the last three as `env.write` answered them.

**20.3.8** `hmz env mkdir <path>` MUST call `env.mkdir`, and `hmz env mv <path> <to>` MUST call
`env.rename`. Their JSON documents MUST be `{"path": <path>}` and `{"path": <path>, "to": <to>}`.

**20.3.9** `hmz env rm <path>` MUST ask (Section 20.7) with the web interface's question for
deleting `<path>`, and where the answer is yes MUST call `env.remove`. Its JSON document MUST be
`{"path": <path>}`.

**20.3.10** Each of `find`, `search`, `git status`, `git diff`, `git log`, `git snapshots`, `git
stage`, `git unstage`, `git discard` and `term list` that has nothing to write, and `list` of a host
with no environment, MUST, without `--json`, write to standard error the web interface's text for
that list being empty; `find` and `search` MUST instead write there that there are more results
than shown where `truncated` was answered `true`.

### 20.4. `hmz env exec`

**20.4.1** `hmz env exec -- <argv>...` MUST call `hosts.env.exec` (Section 4.23.5 of [DAEMON]) with
`<argv>` as `argv`, `--seconds` as `seconds` where given, and as `env` the role `--env` names, or
where it is absent the `name` of the first env `hosts.env.list` answers. It MUST NOT attach to the
host; the workspace and slot of the host `--chat` names MUST be those `chat.get` answers.

**20.4.2** It MUST write the `stdout` answered to standard output and the `stderr` answered to
standard error, and nothing else. Its JSON document MUST be `{"code", "stdout", "stderr"}` as
answered.

**20.4.3** It MUST exit with status 0 where `code` is `0`, and with status 5 otherwise, `null`
included, with `--json` as without.

### 20.5. `hmz env git`

**20.5.1** `hmz env git status` MUST call `env.git.status` and write: the branch, or where there is
none the web interface's text for a detached commit with the first seven characters of `head`, or
its text for no commit yet where there is no `head`; then the web interface's text for how far the
branch is ahead of and behind its upstream, or for no upstream; then one line per file, its `index`
and `worktree` characters and its path, `<orig> -> <path>` where it has `orig`. Its JSON document
MUST be the result of `env.git.status`.

**20.5.2** `hmz env git diff [<path>...]` MUST call `env.git.diff` for each `<path>`, with `staged`
`true` where `--staged` is given; where no `<path>` is given, for each file of `env.git.status`
whose `worktree` is not `.`, or with `--staged` whose `index` is neither `.` nor `?`. For each file
it MUST write a unified diff of `old` and `new` read as UTF-8, headed `--- a/<path>` and `+++
b/<path>` with `/dev/null` for a side that is `null`, and for a file answered `binary` the web
interface's line for a binary file in its place. Its JSON document MUST be `{"staged": <boolean>,
"files": [{"path", "binary", "diff"}]}`, `diff` being that unified diff, `""` for a binary file. A line of either side MUST end at a line feed and nowhere
else.

**20.5.3** `hmz env git log` MUST call `env.git.log` with `--limit` as `limit` and write one line
per commit: the first seven characters of its `hash`, its `date`, its `author` and its `subject`.
Its JSON document MUST be `{"commits": [{"hash", "parents", "author", "date", "subject"}]}`.

**20.5.4** `hmz env git stage`, `unstage` and `discard` MUST each take either paths or `-A`/`--all`,
and a line with both or with neither MUST be a usage error (16.9, 16.10). With `--all` the paths MUST
be those of `env.git.status`: for `stage` and `discard` each file whose `worktree` is not `.`, and for
`unstage` each whose `index` is neither `.` nor `?`. Each MUST call its method, `env.git.stage`,
`env.git.unstage` or `env.git.discard`, with those paths, and MUST NOT call it with none; `unstage`
MUST add to them the `orig` of each that `env.git.status` answers one for, so that a rename is
unstaged whole. Each MUST write the paths, one a line, and its JSON document MUST be `{"paths":
[...]}`.

**20.5.5** `hmz env git discard` MUST ask (Section 20.7), once it knows its paths and before it calls
`env.git.discard`, with the web interface's question for discarding the changes to one file, naming
it, or to several, counting them.

**20.5.6** `hmz env git commit -m <text>` MUST call `env.git.commit` with `<text>` as `message` and,
where `--amend` is given, `amend` `true`; with `-a`/`--all` it MUST first call `env.git.stage` with
the paths `stage --all` would stage, where there are any. It MUST write the `head` answered, and its
JSON document MUST be `{"head": <head>}`.

**20.5.7** `hmz env git snapshots` MUST call `env.git.snapshots` and write the refs answered, one a
line. Its JSON document MUST be `{"snapshots": [...]}`.

**20.5.8** `hmz env git rewind <ref>` MUST ask (Section 20.7) with the web interface's question for
rewinding to `<ref>`, and where the answer is yes MUST call `env.git.rewind`. Its JSON document MUST
be `{"ref": <ref>}`.

### 20.6. `hmz env term`

**20.6.1** `hmz env term open` MUST call `env.term.open` with `--cols` and `--rows`, each where
absent the size of the terminal it is run in, or 80 and 24 where it is run in none, and with `--term`
as `term` where given.

**20.6.2** Without `--json` it MUST then write the `replay` answered and every `data` of the
terminal's `term` messages to standard output as they arrive, MUST type what it reads from standard
input into the terminal with `env.term.input`, and MUST acknowledge what it wrote with
`env.term.ack` (Section 4.24.4.5 of [DAEMON]) at least once for every 65536 bytes, until the
terminal's `term_exit`. It MUST then write to standard error the web interface's text for a terminal
that exited with that status, and exit with status 0. It MUST NOT call `env.term.close`. Where
typing into the terminal is refused it MUST stop viewing it and fail with that refusal.

**20.6.3** Where standard input is a terminal it MUST be put in raw mode for as long, and put back
as it was after; the terminal MUST be resized with `env.term.resize` whenever the terminal it is run
in changes size; and `~` followed by `.`, typed first after a carriage return or a line feed or first
of all, MUST NOT be typed into the terminal and MUST leave it running: the command MUST then stop
viewing it, write to standard error that it still runs and the line that comes back to it, and exit
with status 0. A `~` so placed and followed by `~` MUST be typed once, and one followed by anything
else MUST be typed with what follows it.

**20.6.4** Where standard input is not a terminal, every byte of it MUST be typed as it is, and its
end MUST NOT end the command, which goes on writing until the terminal's `term_exit`.

**20.6.5** With `--json` it MUST NOT view the terminal further: its JSON document MUST be `{"term",
"shell", "replay"}`, `term` and `shell` as answered and `replay` what was answered read as UTF-8,
and the terminal MUST be left running.

**20.6.6** `hmz env term list` MUST call `env.term.list` and write one line per terminal: its id, its
title, its size as `<cols>x<rows>`, and the web interface's text for exited where it is not alive.
Its JSON document MUST be `{"terms": [{"term", "env", "title", "cols", "rows", "alive"}]}`.

**20.6.7** `hmz env term close <term>` MUST call `env.term.close`. Its JSON document MUST be
`{"term": <term>}`.

### 20.7. Asking first

**20.7.1** `hmz env rm`, `hmz env git discard` and `hmz env git rewind` MUST ask first as Section
16.12 states of every declared command that asks, and MUST exit with status 1, as that section
states, where they are not answered yes.

## 21. `hmz flows`, `hmz flowverses` and `hmz workspaces`

### 21.1. Synopsis

```text
hmz flows list [-w <path>]
hmz flows show <name> [-w <path>]
hmz flows backends
hmz flows check <flow> [-a <agents>]... [-e <envs>]... [-p <params>]... [--profile-flow]
                [--profile-environment] [--backup <target>]... [--resume] [-w <path>]
hmz flows setup <flow> [-a <agents>]... [-e <envs>]... [-p <params>]... [--profile-flow]
                [--profile-environment] [--backup <target>]... [-w <path>]
hmz flows fork <flow> [-w <path>]
hmz flowverses list
hmz flowverses show <name>
hmz flowverses add <url> [--name <name>]
hmz flowverses fetch <name>
hmz flowverses remove <name> [-y]
hmz flowverses install <flow> [--version <version>]
hmz flowverses uninstall <flow> [-y]
hmz workspaces list
hmz workspaces add <path>
hmz workspaces forget <path>
hmz workspaces browse [<path>] [--files] [--hidden] [--env <env>]
hmz workspaces complete <typed>
```

**21.1.1** `hmz flows`, `hmz flowverses` and `hmz workspaces` MUST each be a group of declared
commands (Section 16), with the summaries `list flows, show what one declares, check and set up an
epic`, `add flowverses and install, update and uninstall their flows` and `list, add and forget
workspaces, and browse the daemon's folders`.

**21.1.2** `-w` and `--workspace` MUST be the same option. It MUST name the workspace a command of
`hmz flows` is about, the current directory where it is absent.

**21.1.3** A path a command of this section takes as a workspace, or `hmz workspaces browse` takes
without `--env`, MUST be sent to the daemon whole: one that begins with `/` or `~` as it is
written, and any other taken from the current directory. So MUST the `<typed>` of `hmz workspaces
complete` be, and a `<flow>` of `hmz flows check` or a `<url>` of `hmz flowverses add` that begins
with `./` or `../`.

**21.1.4** `-a` and `--agents`, `-e` and `--envs`, and `-p` and `--params` MUST each be the same
option, each accepted any number of times, and `-y` and `--yes` MUST be the same flag.

### 21.2. `hmz flows`

**21.2.1** `hmz flows list` MUST call `flows.list` with the workspace and write one line per flow,
in the daemon's order: its name, whose it is and what it is about, in columns. Its JSON document
MUST be the result of `flows.list` (Section 4.17.1 of [DAEMON]). Where there is no flow and no
`--json`, it MUST write nothing to standard output and say so on standard error.

**21.2.2** `hmz flows show <name>` MUST call `flows.get` with `name` and the workspace. Its JSON
document MUST be the result of `flows.get` (Section 4.17.2 of [DAEMON]). Without `--json` it MUST
write, in this order: the flow's name; its description, where it has one; its `ref`; whether it is
resumable; each agent role; each environment role; each param; what the workspace last set it up
with, where it has; and a line that starts it.

**21.2.3** For an agent role `hmz flows show` MUST write its name and, where the role is not `auto`,
whether it is required, the harnesses of `clis`, what its `permission` lets it touch and its skills;
for an environment role its name and, where the role is not `auto`, whether it is required and each
of `cpu`, `memory`, `gpu` and `image` it asks for as `<name>=<value>`; for a param its key as `-p`
takes it, its type, its default as JSON or that it is required, and its title and description.

**21.2.4** What the workspace last set the flow up with MUST be written as the options of `hmz exec`
that say it again: an `-a` for each agent, an `-e` for each environment, a `-p` for each param and
for each limit of the budget, `--profile-flow`, `--profile-environment`, and a `--backup` for each
target, `--backup none` for no target. A param kept as `null` MUST be left out.

**21.2.5** The line that starts the flow MUST be `hmz exec -f <name>`, then `-a <role>=HARNESS/MODEL`
for each required agent role that is not `auto`, `-e <role>=ENV` for each required environment role
that is not `auto`, `-p <key>=VALUE` for each required param, `-p budget.cost=USD` and `TASK`.

**21.2.6** `hmz flows backends` MUST call `flows.backends`. Its JSON document MUST be the result of
`flows.backends` (Section 4.17.3 of [DAEMON]). Without `--json` it MUST write, for each harness
installed, each of its accounts and each model of that account, one line of the agent as `-a` takes
it after `<role>=` (Section 7.4), `<harness>/<model>` for the account named `""` and
`<harness>@<account>/<model>` for any other, and the efforts of the model; then the same for each
harness that can be installed; then each of `envs`.

**21.2.7** `hmz flows check <flow>` MUST call `flows.check` with the workspace, `flow`, and what the
line sets the epic up with (21.2.9), `resume` being `true` with `--resume`. Its JSON document MUST
be the result of `flows.check` (Section 4.17.8 of [DAEMON]). Without `--json` it MUST write that
the epic can start, its `ref`, the agent of each role, the budget, the backup targets, and
`unreadable` where it is not empty. It MUST NOT start an epic.

**21.2.8** `hmz flows setup <flow>` MUST call `flows.setup` with the workspace, `flow`, and what the
line sets the epic up with (21.2.9), and write that the set-up was saved. Its JSON document MUST be
the result of `flows.setup` (Section 4.17.4 of [DAEMON]).

**21.2.8.1** The line of `hmz flows setup` MUST be the whole set-up: it MUST send `agents`, `envs`
and `params` as empty objects where the line gives none, and `profile_flow` and
`profile_environment` as `false` where the line does not ask for them, so that nothing the workspace
kept for the flow before outlasts a line that does not say it. `backup` MUST be left out without
`--backup`.

**21.2.8.2** `hmz flows setup` MUST first call `flows.get` for the flow's params, and MUST send a
param whose schema there lets it be a boolean, an integer or a number as that, where its text is
`true` or `false` in any case, a whole number, or a number; every other param MUST be sent as its
text.

**21.2.9** `hmz flows check` and `hmz flows setup` MUST read `-a`, `-e`, `-p`, `--profile-flow`,
`--profile-environment` and `--backup` as `hmz exec` reads them: items as Section 7.2, an `-a` or
`-e` item split at its first `=` into the role and what is sent for it, params and a budget as
Section 7.6, and backups as Section 7.11.2. They MUST send `agents` and `envs` as objects of role to
what was written, `params` as an object of key to text, `budget` as the JSON of a `Budget` (Section
3 of [PYTHON]), and `backup` as a list, and MUST leave out each that the line does not give. An
agent and an environment MUST be sent unread: whether each names one is the daemon's to say.

**21.2.10** An `-a` or `-e` item with no `=`, an empty role or nothing after the `=`, a role given
twice to one option, a `-p` that Section 7.6 makes a usage error, and `--backup none` beside
another target MUST each be a usage error (Section 16.10), and MUST call nothing.

**21.2.11** `hmz flows fork <flow>` MUST call `flows.fork` with the workspace and `flow`, and write
its `said`. Its JSON document MUST be `{"said", "at"}` (Section 4.17.4.3 of [DAEMON]).

### 21.3. `hmz flowverses`

**21.3.1** `hmz flowverses list` MUST call `flowverses.list`. Its JSON document MUST be the result
of `flowverses.list` (Section 4.17.6.1 of [DAEMON]). Without `--json` it MUST write, under a
heading, one line per flowverse: its name, its URL, how many flows are installed out of it, and that
it is not fetched where it is not; and, under a second heading, one line per installed flow: its
name, its version, its flowverse, and the newer version of `updates` where there is one.

**21.3.2** `hmz flowverses show <name>` MUST call `flowverses.get`. Its JSON document MUST be the
result of `flowverses.get` (Section 4.17.6.2 of [DAEMON]). Without `--json` it MUST write the
flowverse's name and URL, then one line per release, flows in the daemon's order and releases newest
first: the flow as `hmz flowverses install` takes it, the version, marked where it is a prerelease,
whether it is the one installed, and its description; then each of `skipped` with why.

**21.3.3** `hmz flowverses add <url>` MUST call `flowverses.add` with `url`, and `name` where
`--name` is given; `hmz flowverses fetch <name>` MUST call `flowverses.fetch`; `hmz flowverses
remove <name>` MUST call `flowverses.remove`; `hmz flowverses install <flow>` MUST call
`flowverses.install` with `flow`, and `version` where `--version` is given; and `hmz flowverses
uninstall <flow>` MUST call `flowverses.uninstall`. Each MUST write the `said` of its result, and
its JSON document MUST be that result (Section 4.17.6.3 of [DAEMON]).

> Informative: `hmz flowverses install <flow>` on a flow already installed updates it to the newest
> release, and with `--version` switches it to that one.

**21.3.4** `hmz flowverses remove` and `hmz flowverses uninstall` MUST first ask as Section 16.12
states, in the words the web interface asks in, and MUST make their call only where the answer is
yes.

**21.3.5** Where nobody can be asked, `hmz flowverses remove` and `hmz flowverses uninstall` MUST
call nothing, and MUST exit with status 1 as Section 16.12 states.

### 21.4. `hmz workspaces`

**21.4.1** `hmz workspaces list` MUST call `workspaces.list` with the current directory as `here`
and write one line per workspace, in the daemon's order: its path, its count of epics, its count of
chats, when the latest began or `-`, and whether it is running and whether its directory is missing.
Its JSON document MUST be the result of `workspaces.list` (Section 4.17.5.1 of [DAEMON]). Where
there is no workspace and no `--json`, it MUST write nothing to standard output and say so on
standard error.

**21.4.2** `hmz workspaces add <path>` MUST call `workspaces.add` with the path as `workspace` and
the current directory as `here`, and write `kept`. `hmz workspaces forget <path>` MUST call
`workspaces.forget` likewise, and write that it was forgotten. The JSON document of each MUST be
the result of its call (Section 4.17.5 of [DAEMON]).

**21.4.3** `hmz workspaces browse [<path>]` MUST call `paths.list` with the path as `at`, `~` where
none is given, `files` with `--files`, `hidden` with `--hidden` and `env` with `--env`; with `--env`
the path MUST be sent as it is written. It MUST write one line per entry, in the daemon's order: the
entry's whole path, ending in `/` for a directory; and, where `more` is not 0, how many were left
out, on standard error. Its JSON document MUST be the result of `paths.list` (Section 4.17.7.1 of
[DAEMON]).

**21.4.4** `hmz workspaces complete <typed>` MUST call `paths.complete` with `typed` (21.1.3) and
write one path per line. Its JSON document MUST be `{"paths": [<path>]}`.

## 22. `hmz settings`, `hmz accounts` and `hmz nous`

### 22.1. Synopsis

```text
hmz settings get [<key>] [-w <path>]
hmz settings set details|reports|harness_sessions on|off
hmz settings set chat <agent> [-w <path>]
hmz settings set prefer native|flow
hmz settings set listen [<spec>]...
hmz settings set ice_servers [<server>]...
hmz settings set backup <json>
hmz settings set backup.target <name> [--url <url>] [--branch <branch>] [--policy <policy>]...
                               [--every <n>] [--default | --no-default] [--remove]
hmz settings set backup.defaults [<name>]...
hmz settings forget -w <path>

hmz accounts list
hmz accounts ways [<cli>]
hmz accounts add <cli> <name> --way <way> [--set <name>=<value>]... [--env <name>[=<var>]]...
                 [--stdin <name>]
hmz accounts correct <cli> <name> [--set <name>=<value>]... [--env <name>[=<var>]]...
                     [--stdin <name>]
hmz accounts remove <cli> <name>
hmz accounts models <cli> [<name>]
hmz accounts copy <cli> <name> <into>

hmz nous list [--concrete]
hmz nous scan
hmz nous set <name> [--tries <n>] [--policy <policy>] [--timeout <seconds>] [--graph <graph>]...
             [--then <graph>]... [--no-then]
hmz nous rename <name> <to>
hmz nous clear <name>
```

**22.1.1** `hmz settings`, `hmz accounts` and `hmz nous` MUST each be a group of declared commands
(Section 16), and `hmz settings set` MUST be a group under `hmz settings` with one command for each
setting it writes.

**22.1.2** A command of this section that finds its line cannot be read after it was parsed MUST
end as the usage error of Section 16.10, and MUST NOT have written anything to the daemon.

### 22.2. `hmz settings`

**22.2.1** `-w <path>` MUST name a workspace of the daemon's machine, sent as Section 16.13 states.
Where `-w` is absent the command MUST send no `workspace`.

**22.2.2** `hmz settings get` MUST call `settings.get`. Its JSON document MUST be the result of
`settings.get`, whole. Without `--json` it MUST write one line for each of `workspace`, `flow`,
`flows`, `chat`, `prefer`, `ai_chan`, `details`, `harness_sessions`, `reports`, `backup`, `listen`
and `ice_servers`, in that order: its name and its value in columns, a value that is text as it is
and any other as JSON.

**22.2.3** `hmz settings get <key>` MUST write the value of that one setting alone, in the same form,
and its JSON document MUST be `{<key>: <value>}`. A `<key>` that is none of the names of 22.2.2 MUST
be a usage error (22.1.2), and `settings.get` MUST NOT be called.

**22.2.4** Each command of `hmz settings set` MUST call `settings.set` once with the one parameter
this section names for it, MUST write `Saved.`, and its JSON document MUST be the result of
`settings.set`, whole.

**22.2.5** `details`, `reports` and `harness_sessions` MUST take `on` or `true` for `true` and `off`
or `false` for `false`, and MUST send it as the parameter of the same name.

**22.2.6** `chat <agent>` MUST send `<agent>` as `chat`, with the workspace of `-w`. `prefer` MUST
take `native` or `flow` and send it as `prefer`.

**22.2.7** `listen` MUST send as `listen` a list of its arguments, each a listener spec; given one
argument that begins with `[`, it MUST send that argument read as a JSON list; given the one
argument `-`, the JSON list read from standard input; given none, an empty list. JSON read so that
is not a list MUST be a usage error (22.1.2), here and in 22.2.8.

**22.2.8** `ice_servers` MUST send as `ice_servers` a list of its arguments: one that begins with `{`
read as a JSON object, any other as `{"urls": <argument>}`. Given one argument that begins with `[`
it MUST send that argument read as a JSON list, and given the one argument `-` it MUST send the JSON
list read from standard input. A server whose `credential` is text MUST be taken from standard
input alone: given one on the command line, the command MUST refuse it as a usage error (22.1.2).

**22.2.9** `backup <json>` MUST send `<json>`, read as JSON, as `backup`; `-` MUST read the JSON from
standard input.

**22.2.10** `backup.target <name>` and `backup.defaults` MUST call `settings.get` with no workspace
and then `settings.set` with a `backup` that holds every target `settings.get` answered, each as it
was answered, changed only as 22.2.11 and 22.2.12 state.

**22.2.11** `backup.target <name>` MUST change the target of that name where there is one, and
otherwise MUST add a target of that name with the branch `main`, no policy and `every` 30. `--url`,
`--branch` and `--every` MUST set `url`, `branch` and `every`; `--policy`, given at all, MUST set
`policies` to those of `session`, `interval` and `end` that were given, `manual` standing for none;
`--default` MUST add the name to `defaults` where it is not there and `--no-default` MUST remove it,
`defaults` being otherwise sent as it was answered; `--remove` MUST remove the target, and its name
from `defaults`, instead, and where there is no target of that name MUST be a usage error (22.1.2).

**22.2.12** `backup.defaults` MUST set `defaults` to its arguments, in order.

**22.2.13** A value that is to be read as JSON and is not JSON MUST be a usage error (22.1.2).

**22.2.14** `hmz settings forget -w <path>` MUST call `settings.forget` with that workspace and
write `Forgotten.` where `forgot` is true and `Nothing to forget.` otherwise. Its JSON document MUST
be the result of `settings.forget`, whole.

### 22.3. `hmz accounts`

**22.3.1** A command of `hmz accounts` MUST NOT write the value of any answer it was given, to any
stream, in any case (Section 4.3).

**22.3.2** `hmz accounts list` MUST call `accounts.list` and write one line per account, in the
daemon's order: its harness, its name, the way it was made by, the names of the variables it sets
separated by commas, and how many models it runs, in columns. An account whose name is empty MUST be
written with the name `Local`. Its JSON document MUST be `{"gateway", "accounts": [{"cli", "name",
"way", "sets", "made", "models", "asked", "serves"}]}`.

**22.3.3** `hmz accounts ways` MUST call `accounts.list` and write, for each way of each harness,
one line of the harness, the way and what the way says of itself, a way whose `terminal` is true
marked as one made at a terminal; and under it, indented, one line for each answer the way asks:
the variable and what it is, with what it is left as where it has a `fixed`. `<cli>` MUST restrict
both the lines and the document to that harness. Its JSON document MUST be `{"gateway", "backends":
[{"cli", "wants", "ways": [{"name", "about", "group", "terminal", "asks": [{"env", "about", "secret",
"fixed"}]}]}]}`.

**22.3.4** `hmz accounts add` and `hmz accounts correct` MUST take answers in three ways, and in no
other: `--set <name>=<value>`, the value on the command line; `--env <name>`, the value of the
environment variable `<name>` of the command's own process, or of `<var>` where written
`<name>=<var>`; and `--stdin <name>`, everything read from standard input less the line feeds and
carriage returns it ends with.

**22.3.5** Before it makes or corrects an account, the command MUST call `accounts.list` and MUST
refuse as a usage error (22.1.2) a `--set` naming a variable whose `secret` is true in the way the
account is made by (`--way` for `add`, the account's own `way` for `correct`). Where `correct` finds
the account but not its way, every variable the account sets MUST be taken for secret.

**22.3.6** A `--set` that is not `<name>=<value>`, an `--env` naming an environment variable that
is not set, and an answer of `--env` or `--stdin` that is empty MUST be usage errors (22.1.2), and
what is written of the first MUST NOT repeat the argument.

**22.3.7** `hmz accounts add <cli> <name> --way <way>` MUST call `accounts.create` with the answers
and write `Made <cli>@<name>.`. `hmz accounts correct <cli> <name>` MUST call `accounts.correct`
with the answers and write `Saved.`. `hmz accounts remove <cli> <name>` MUST call `accounts.remove`
and write `Removed`. `hmz accounts copy <cli> <name> <into>` MUST call `accounts.copy` and write
`Copied to <into>`. The JSON document of each MUST be that of 22.3.2, from the method's result.

**22.3.8** `hmz accounts models <cli> [<name>]` MUST call `accounts.models`, `<name>` absent being
`""`, and write the models of that account in the result, one a line, or `No models listed` where
there are none. Where no name was given and the result lists no such account, the models MUST be
those of the `concrete` of `nous.list` that begin `<cli>/`, less that prefix. Its JSON document MUST
be `{"cli", "name", "models", "asked"}`.

### 22.4. `hmz nous`

**22.4.1** The JSON document of every command of `hmz nous` MUST be the result of its method, whole,
without `failed` unless the command is `hmz nous scan`.

**22.4.2** `hmz nous list` MUST call `nous.list` and write one line per nous written, in the daemon's
order: its name, whether it is virtual or concrete, its tries and policy, its limit, its graph and
its `then`, in columns. A graph in which every node uses one nous and goes on, for any fault, to the
next MUST be written as those nous separated by commas, and any other graph as JSON. `--concrete`
MUST write instead each of `concrete`, one a line.

**22.4.3** `hmz nous scan` MUST call `nous.scan`, write to standard output how many concrete nous
there are and of how many harnesses, and, without `--json`, write to standard error one line for
each entry of `failed`. A harness that would not answer MUST NOT change the exit status.

**22.4.4** `hmz nous set <name>` MUST call `nous.list` and then `nous.set` with, for each of `tries`,
`policy`, `timeout`, `graph` and `then`, what its option gave or, where the option is absent, what
`nous.list` answered for the nous of that name, so that what the line does not say stays as it was
written. `--no-then` MUST send no `then`. It MUST write `Saved.`.

**22.4.5** `--graph` and `--then` MUST each be read as a graph: given once with a value that begins
with `{`, `[` or `"`, that value read as JSON; otherwise the nous given, one alone as that nous and
several, in the order given or separated by commas, as a list of nous. A value that is to be read
as JSON and is not JSON MUST be a usage error (22.1.2).

**22.4.6** `hmz nous rename <name> <to>` MUST call `nous.rename` and write `Renamed`. `hmz nous clear
<name>` MUST call `nous.clear` and write `Removed`.

## 23. `hmz runtimes`, `hmz easytier` and `hmz daemons`

### 23.1. Synopsis

```text
hmz runtimes list
hmz runtimes show <backend> [<name>]
hmz runtimes set <backend> <name> [--set <field>=<value>]... [--replace]
hmz runtimes remove <backend> <name>
hmz runtimes check <backend> <name>
hmz runtimes hosts
hmz runtimes import [<host>]... [--update]
hmz easytier list
hmz easytier set <name> [--node <url>]... [--secret-stdin] [--secret-env <variable>]
hmz easytier remove <name>
hmz easytier nodes
hmz daemons list
hmz daemons add <name> [<route>]... [--id <id>] [--replace]
hmz daemons remove <name>
hmz daemons show <name> [--connect]
hmz daemons pair <name> <code> [--device <device>] [--replace]
```

**23.1.1** `hmz runtimes`, `hmz easytier` and `hmz daemons` MUST each be a group of declared
commands (Section 16).

**23.1.2** `--set` MUST be accepted any number of times; a value with no `=`, or with nothing before
it, MUST be a usage error.

### 23.2. `hmz runtimes`

**23.2.1** `hmz runtimes list` MUST call `runtimes.list` and write a line for the daemon's own
machine, `local` and its host name, then one line per runtime in the daemon's order: its backend,
its name and how it was made, in columns. Its JSON document MUST be `{"local", "runtimes":
[{"backend", "name", "made", "fields"}], "blanks"}`, `local` and `blanks` as the daemon answered
them and `fields` every member of the runtime other than `backend`, `name` and `made`.

**23.2.2** `hmz runtimes show <backend> <name>` MUST call `runtimes.list` and write one line
`<field>=<value>` for each field `blanks` names for the backend, the runtime's value where it has
one and the blank's otherwise; a value that is not text MUST be written as JSON. Without `<name>` it
MUST write the blank's values. Its JSON document MUST be `{"backend", "name", "made", "fields"}`,
`name` and `made` being `null` without `<name>`. A backend `blanks` does not name MUST be refused
with code `400`, and a runtime that is not written with code `404`.

**23.2.3** `hmz runtimes set <backend> <name>` MUST call `runtimes.set` with `backend`, `name`,
`fields` and, where `--replace` is given, `replace` `true`. `fields` MUST be made of each `--set`
in order, read by the value `blanks` (of `runtimes.list`) holds for its field:

- for a number, `<value>` as an integer, else as a decimal number;
- for a list, `<value>` added as one item, or the whole list where `<value>` is a JSON array;
- for an object, `<value>` as `<key>=<member>` added as one member, or the whole object where
  `<value>` is a JSON object;
- for a list or an object, an empty `<value>` as none;
- otherwise, and for a number that reads as neither, `<value>` as text.

**23.2.4** With `--replace`, where a runtime of that backend and name is written, `fields` MUST
start from that runtime's fields, and a field a `--set` names MUST be what this command line says
of it alone. Without `--replace`, `fields` MUST hold the fields of the command line alone.

**23.2.5** `hmz runtimes remove <backend> <name>` MUST call `runtimes.remove`, and `hmz runtimes
import` MUST call `runtimes.import` with each `<host>` as `names` and, where `--update` is given,
`update` `true`. `set`, `remove` and `import` MUST write `Saved`, `Removed` and `Imported`, and
their JSON document MUST be `{"runtimes": [...]}`, every runtime the daemon answered afterwards, as
`list` writes them.

**23.2.6** `hmz runtimes check <backend> <name>` MUST call `runtimes.check` and write one line per
member of the result, its name and its value, text as it is and anything else as JSON; its JSON
document MUST be the result. It MUST exit with status 4 where `reached` is false, and 0 otherwise.

**23.2.7** `hmz runtimes hosts` MUST call `runtimes.hosts` and write one line per host: its alias,
the machine it reaches, its user, its port, and `Saved` where `saved` is true. Its JSON document
MUST be the result.

### 23.3. `hmz easytier`

**23.3.1** `hmz easytier list` MUST call `easytier.list` and write one line per entry: its name,
`true` or `false` as a secret is written, and its nodes separated by spaces. Its JSON document MUST
be `{"networks": [{"name", "nodes", "keyed"}]}`, `keyed` a boolean.

**23.3.2** `hmz easytier set <name>` MUST call `easytier.set` with `name`, `nodes` and, where one is
given, `secret`. The secret MUST be read from standard input, less a trailing line end, where
`--secret-stdin` is given, and from the environment variable `--secret-env` names where that is
given; it MUST NOT be taken from the command line, and MUST NOT be written to either stream. Both
options given, or a variable that is not set, MUST be refused with code `400` and nothing called.

**23.3.3** Where no `--node` is given, `hmz easytier set` MUST call `easytier.list` and send the
nodes of the entry of that name, none where there is no such entry.

**23.3.4** `hmz easytier remove <name>` MUST call `easytier.remove`. `set` and `remove` MUST write
`Saved` and `Removed`, and their JSON document MUST be that of `list`, of the entries the daemon
answered afterwards.

**23.3.5** `hmz easytier nodes` MUST call `easytier.nodes` and write one line per node: its URL,
`up` or `down` where that is known, its share of the last 24 hours up where that is known, its
version and its name. Its JSON document MUST be `{"nodes": [{"url", "name", "version", "up",
"uptime"}]}`.

### 23.4. `hmz daemons`

**23.4.1** `hmz daemons` MUST read and write the registry of Section 4.14 of [PYTHON], which is
kept by the clients of this machine and by no daemon (Section 4.20.2 of [DAEMON]), in the calling
process; Section 16.2 does not hold of it. `list`, `add` and `remove` MUST call no daemon, and
`--daemon` MUST change nothing any command of the group does.

**23.4.2** `hmz daemons list` MUST write one line per daemon: its name, the id pinned for it and its
routes separated by spaces, this machine's first as `local`, with no id and the route `unix:`, then
each daemon of the registry in order. Its JSON document MUST be `{"daemons": [{"name", "id",
"routes"}]}`.

**23.4.3** `hmz daemons add <name> <route>...` MUST write the daemon to the registry with `id`
`--id`, `""` where absent, and the routes in order, and MUST write `Added`, or `Saved` with
`--replace`. Its JSON document MUST be the daemon as written, `{"name", "id", "routes"}`. It MUST
refuse a name already kept, unless `--replace` is given, with code `409` and `There is already a
daemon <name>.`; no route with code `400` and `A daemon needs at least one route.`; and a daemon the
registry refuses (Section 4.14.3 of [PYTHON]), `local` among them, with code `400` and the
registry's message.

**23.4.4** `hmz daemons remove <name>` MUST remove the daemon from the registry and write `Removed`;
its JSON document MUST be `{"name": <name>}`. A name not kept MUST be refused with code `404` and
`There is no daemon <name>.`, and `local` with code `400`.

**23.4.5** `hmz daemons show <name>` MUST write one line per member it knows, its name and its
value. Its JSON document MUST be `{"name", "id", "routes", "state", "version"}`, `state` and
`version` being `null` without `--connect`. With `--connect` it MUST reach the daemon as Section
23.5 states, `state` MUST be `up`, `version` the version `session.hello` answered, and `id` the id
kept, or the one answered where none is; where the daemon cannot be reached it MUST fail as Section
16.7 to Section 16.9 state of a daemon that cannot be. A name not kept MUST be refused with code
`404`.

**23.4.6** `hmz daemons pair <name> <code>` MUST claim the pairing code as `Remotes.pair` does
(Section 4.14.10 of [PYTHON]), under the device name `--device` where it is given, MUST write
`Added`, and its JSON document MUST be the daemon as written. `<code>` given as `-` MUST be read
from standard input. A name already kept MUST be refused as Section 23.4.3 states before anything
is claimed, `local` among them; a code that is not one with code `400`; a claim the daemon refuses
with the code and message of its refusal; a daemon claimed that cannot then be written with code
`500`; and where no route opens the command MUST fail as one whose daemon cannot be reached.

### 23.5. `--daemon`

**23.5.1** Absent, empty or `local`, `--daemon` MUST name this machine's daemon, reached as Section
4.21.1 of [PYTHON] states with `kind` `cli`.

**23.5.2** Any other `--daemon <name>` MUST name the daemon the registry keeps under `<name>`. The
command MUST be a client of that daemon in place of this machine's: reached over its routes as
`Client.named` reaches it (Section 4.30.9 of [PYTHON]) with `kind` `cli`, `hmz` never installed on a
machine that has none, and let go of as the command ends.

**23.5.3** Where the registry keeps no daemon under `<name>`, the command MUST be refused with code
`404` and `No daemon is kept under the name <name>.`, and exit with status 1. Where the daemon is
kept and cannot be reached, the command MUST fail as Section 16.7 to Section 16.9 state of a daemon
that cannot be reached, saying how it stands.

## 24. `hmz btw`, `hmz ai` and `hmz notices`

### 24.1. Synopsis

```text
hmz btw ask <question> [--to <session>] [--aside <name>] [-w <path>] [--epic <name> | --chat <name>]
hmz btw sessions (--epic <name> | --chat <name>)
hmz btw list [-w <path>] [--epic <name> | --chat <name>]
hmz btw show <aside> [-w <path>] [--epic <name> | --chat <name>]
hmz btw leave (<aside> | --all) [-w <path>]
hmz ai new <task> [--scope <scope>] [-w <path>] [--epic <name>] [--nous <nous>]
                  [--preset <preset>] [--wait] [--timeout <seconds>]
hmz ai list
hmz ai rename <id> <title>
hmz ai forget <id> [-y]
hmz ai say <id> <text> [--no-wait] [--timeout <seconds>]
hmz ai wait <id> [--timeout <seconds>]
hmz ai stop <id>
hmz notices list [--after <id>] [--kind <kind>]...
hmz notices follow [--after <id>] [--kind <kind>]...
```

**24.1.1** `hmz btw`, `hmz ai` and `hmz notices` MUST each be a group of declared commands (Section
16), with the summaries `ask side questions of a session of an epic or chat`, `talk to Ai-chan, who
operates hmz for you` and `list and follow what this daemon tells you about your epics and chats`.

**24.1.2** `-w`, `--workspace` MUST name a workspace of the daemon's machine as Section 16.13
states, the working directory where the option is absent, but where 24.3.1 states otherwise.

### 24.2. `hmz btw`

**24.2.1** `--epic` and `--chat` MUST be sent as the `epic` and the `chat` of `btw.ask` and
`btw.list` (Section 4.15 of [DAEMON]), each left out where it is absent; a line giving both MUST be
refused with status 1 and MUST call nothing.

**24.2.2** `hmz btw ask <question>` MUST call `btw.ask` with `question`, the workspace of 24.1.2,
`--to` as `to` and `--aside` as `aside`, and MUST write the answer and a line feed to standard
output. Where `--aside` is absent it MUST name a new side conversation itself, and, without
`--json`, MUST then write that name to standard error with the `--aside` that goes on in it. Its
JSON document MUST be `{"aside", "to", "question", "answer"}`.

**24.2.3** Where `--to` is absent and `--aside` names a side conversation `btw.list` answers, `hmz
btw ask` MUST ask the session that side conversation asks. Otherwise, where `--to` is absent, `hmz
btw ask` with `--chat` MUST ask the last session the chat
opened, as `hmz btw sessions` names it, and MUST be refused with status 1, `This chat has said
nothing to ask about yet.`, where the chat opened none; without `--chat` it MUST be refused with
status 1, `Pick the conversation to ask first.`

**24.2.4** `hmz btw sessions` MUST take exactly one of `--epic` and `--chat`, MUST read the epic's
sessions from `runs.get` or the chat's from `chat.get`, and MUST write one line per session, oldest
first: `<agent>/<n>`, `<agent>` the name of the session's agent and `<n>` counting that agent's
sessions from 1 in the order the daemon answers them, and its harness. Its JSON document MUST be
`{"sessions": [{"session", "agent", "harness"}]}`.

**24.2.5** `hmz btw list` MUST call `btw.list` and write one line per side conversation, in the
daemon's order: its name, the session it asks, how many questions it has answered and the question
it is answering, in columns. Its JSON document MUST be `{"asides": [{"aside", "to", "question",
"said": [{"question", "answer"}]}]}`.

**24.2.6** `hmz btw show <aside>` MUST call `btw.list` and write, for each question the side
conversation of that name answered, oldest first, `> ` and the question on one line and its answer
after it, an empty line between two. Its JSON document MUST be that side conversation's entry of
24.2.5. A name of no side conversation listed MUST be refused with status 1.

**24.2.7** `hmz btw leave <aside>` MUST call `btw.leave` with that `aside`, and `hmz btw leave
--all` MUST call it with none; a line giving both or neither MUST be refused with status 1 and MUST
call nothing. Its JSON document MUST be `{"aside": <name>}`, `null` for `--all`.

### 24.3. `hmz ai`

**24.3.1** `hmz ai new <task>` MUST call `aichan.create` (Section 4.22 of [DAEMON]) with `task`,
`--nous` as `nous` and `--preset` as `preset`, each left out where absent, and `scope` being
`--scope` where given, else `epic` where `--epic` is given, else `workspace` where `--workspace` is
given, else `daemon`. It MUST send `--epic` as `epic` where given, and as `workspace` what
`--workspace` names where given, else the working directory for the scopes `workspace` and `epic`,
else nothing. It MUST write the conversation's `id` and a line feed to standard output, before it
waits for anything.

**24.3.2** With `--wait`, `hmz ai new` MUST then wait as `hmz ai wait` does and write what Ai-chan
said after the `id`. Its JSON document MUST be `{"id", "workspace", "slot", "answer", "mode"}`,
`answer` and `mode` being `null` without `--wait`.

**24.3.3** `hmz ai list` MUST call `aichan.list` and write one line per conversation, in the
daemon's order: its `id`, `state`, `scope`, `preset`, `nous` and `title`, in columns. Its JSON
document MUST be `{"conversations": [...]}`, each as `aichan.list` answers it.

**24.3.4** `hmz ai rename <id> <title>` MUST call `aichan.rename`. Its JSON document MUST be `{"id",
"title"}`, `title` as it was given.

**24.3.5** `hmz ai forget <id>` MUST call `aichan.forget`. Without `--yes` it MUST first read the
conversation (`aichan.list`), so that one that is not there is refused as that, and MUST then ask
as Section 16.12 states, naming it by its `id` and title and saying that it cannot be brought back.
Its JSON document MUST be `{"id"}`.

**24.3.6** `hmz ai say <id> <text>` MUST attach to the conversation's host (`epic.attach` with its
`workspace` and `slot` and `replay` `false`, which carries a folded conversation on, Section 4.22.5
of [DAEMON]), and MUST then answer the first question the host's status holds (`epic.answer`) with
`<text>`, or, where it holds none and its `turn` is `running`, say `<text>` into the turn
(`epic.say`). It MUST wait while the host holds no question and its turn is not open, and MUST
detach (`epic.detach`) however it ends.

**24.3.7** Unless `--no-wait` is given, `hmz ai say` MUST then wait until the host's status holds a
question it did not hold when `<text>` was sent, and MUST write that question's `text` and a line
feed to standard output. Its JSON document MUST be `{"id", "answer", "mode"}`, `answer` that `text`
and `mode` that question's `mode`, both `null` with `--no-wait`.

**24.3.8** `hmz ai wait <id>` MUST attach as 24.3.6 states, wait until the host's status holds a
question, write the first one's `text` and a line feed to standard output, and detach. Its JSON
document MUST be `{"id", "answer", "mode"}`.

**24.3.9** Where the host holds no question, its turn is not open and its `ended` says how it
ended and that is not `stopped`, `hmz ai say`, `hmz ai wait` and `hmz ai new --wait` MUST be refused with status 1 and that `why`,
or `This conversation failed. Start a new one.` where it says none. Where `--timeout` seconds,
`600` where absent, pass before what is waited for comes, each MUST end as a daemon that did not
answer in time (Section 16.9).

**24.3.10** `hmz ai stop <id>` MUST call `epic.stop` on the conversation's host, attached to and
let go of as 24.3.6 states, and MUST NOT attach to a conversation whose `state` is `folded`, which
it MUST refuse with status 1, `Ai-chan is not answering, so there is nothing to stop`. Its JSON
document MUST be `{"id"}`.

**24.3.11** An `<id>` of no conversation MUST be refused with status 1, `There is no Ai-chan
#<id>.`, by every command of 24.3 that takes one.

### 24.4. `hmz notices`

**24.4.1** `hmz notices list` MUST call `notices.list` (Section 4.19.2 of [DAEMON]) with `--after`
as `after` and write one line per notice, oldest first: its `id`, when it was made in local time
as `YYYY-MM-DD HH:MM:SS`, its kind as the web interface names it (`Done`, `Failed`, `Stopped`,
`Question`, `Waiting`), its `chat` or else its `epic`, and the first line of its `text` that says
anything, or else of its `task`, in columns. Its JSON document MUST be `{"notices": [...], "last":
<id>}`, each notice as the daemon answers it and `last` the `id` of the newest notice the daemon
has made.

**24.4.2** `--kind`, which MAY be given more than once and MUST be one of `done`, `failed`,
`stopped`, `asked` and `listening`, MUST leave out every notice whose `kind` is none of those
given; it MUST NOT change `last`.

**24.4.3** `hmz notices follow` MUST open a notices subscription (`notices.subscribe`) with
`--after` as `after` and MUST write each notice it is told as a line of 24.4.1, as it is told. Under
`--json` it MUST write each notice as one JSON document and a line feed instead, which is the
exception to Section 16.7. Each line MUST be written out at once.

**24.4.4** Told that the subscription has gone (Section 6.10.1 of [WIRE]), `hmz notices follow`
MUST subscribe again after the last notice it was told, or, where it was told none, after the
`after` it gave or the `last` its first subscription was answered with.

**24.4.5** `hmz notices follow` MUST run until it is interrupted, when it MUST end the subscription
(`notices.unsubscribe`) and exit with status 130 (16.14); where the session with the daemon ends
first it MUST exit as a daemon that cannot be reached (Section 16.9).

## 25. `hmz skills`

### 25.1. Synopsis

```text
hmz skills add [--for <harness>]... [--dir <path>]
hmz skills list [--for <harness>]... [--dir <path>]
hmz skills remove [--for <harness>]... [--dir <path>] [-y | --yes]
hmz skills show
```

**25.1.1** `hmz skills` MUST be a group of declared commands (Section 16) with the summary `install,
list and remove the hmz skill for using the CLI`.

**25.1.2** The commands of `hmz skills` are _local_: they MUST NOT reach a daemon, and what they read
and write is the files of the user running them, on the machine they run on. Notwithstanding 16.6 and
16.9, a local command MUST NOT take `--daemon`, MUST NOT exit with status 3, and MUST exit with status
1 where it refuses what it was asked; its help MUST state `--json` and `--no-color` alone as common
options and the statuses 0, 1, 2 and 130 alone as common statuses. A file it cannot read or write MUST be
a refusal. Under `--json` the `code` of its error document (16.7) MUST be `0`.

**25.1.3** The _hmz skill_ is a directory named `hmz` holding a file `SKILL.md`, and a file
`reference.md` where 25.2.5 has one. A _skills directory_ is a directory a harness loads its user's
skills from, one directory per skill. The skills directory _of a harness_ MUST be the first
directory, of those that harness loads its user's skills from, that is under the harness's own home;
else the first under the directory programs keep their configuration in; else the first it shares
with other harnesses under the user's home. A harness that loads its user's skills from no directory
has none.

**25.1.4** `--for <harness>` MUST name a harness by any name `-a` takes for it (Section 7.4), whether
or not it is installed; a name no harness answers to, and a harness that has no skills directory,
MUST be refused. `--dir <path>` MUST name a skills directory by its path, and an empty path MUST be a usage error. A directory
reached by more than one of them is one place. The _places_ of a line are
the skills directory of each harness named and the directory `--dir` gives; where a line names
neither, they are those 25.3 states for its command.

### 25.2. The skill

**25.2.1** `SKILL.md` MUST begin with YAML front matter between two lines of `---`, holding `name`,
being `hmz`; `description`, one text saying what the skill is for and when to load it; and
`metadata`, a mapping holding `written-by`, being `hmz skills add`, and `hmz-version`, being the
version of the hmz that wrote the file.

**25.2.2** A skill is _hmz's own_ where the `metadata` of its `SKILL.md` holds `written-by` with the
value `hmz skills add`. Anything else in the place of the hmz skill, but a directory holding nothing,
is _foreign_.

**25.2.3** After its front matter, `SKILL.md` MUST state, in this order: what `hmz` is; how to read
about its commands, being `hmz --help`, `hmz COMMAND --help`, and `hmz help --json` where that command
exists (Section 26); what every declared command shares, being `--json` and the error document of
16.7, `--daemon`, each exit status of 16.9 with what it means, and which commands are local
(25.1.2); and every declared command, groups
and the commands under them, each as one line holding its usage line and its summary.

**25.2.4** `SKILL.md` MUST then state each of these sequences for which, of every step, some declared
command declares the method named, and MUST NOT state the others: starting a chat and reading the
answer (`chat.start`, then `chat.get`); starting an epic and following it (`epic.start`, then
`epic.attach` or `epic.status`); answering a question an epic asks (`epic.status` or `epic.attach`,
then `epic.answer`); listing the runs and exporting one (`runs.list`, then `runs.bundle`). A step MUST
be written as the first example line of its command with what that line does, or as its usage line
and summary where it declares no example.

**25.2.5** Where a `SKILL.md` stating every declared command would be longer than 500 lines, it MUST
instead state only the commands `hmz` is followed by, each as one line, and link `reference.md`; and
`reference.md` MUST state every declared command as 25.2.3 has them.

**25.2.6** Everything the skill states of a command MUST be read from that command's declaration
(Section 16) when the skill is written, and 16.11 MUST hold of every other text in it.

### 25.3. Behaviour

**25.3.1** `hmz skills add` MUST write the hmz skill into each of its places, making the directories
that are missing; where the line names no place, its places are the skills directories of the
harnesses installed on this machine, and a line with none MUST be refused. Where any of its places
holds a foreign skill it MUST be refused, naming that place, having written nothing anywhere. It MUST
replace hmz's own skill where one is there. It MUST write one line per place, naming the harness and
the path of the `SKILL.md`. Its JSON document MUST be `{"version": <version>, "written": [{"harness",
"path", "changed"}]}`, `harness` being `null` for a place of no harness and `changed` being whether
any file there was written, removed or replaced with different text.

**25.3.2** `hmz skills list` MUST write one line per place: the harness, with a note where it is not
installed on this machine; its skills directory; and the state of the hmz skill there. Where the line
names no place, its places are the skills directories of every harness that has one, in the order of
the harnesses, and then each other directory a harness loads its user's skills from that holds
anything in the place of the hmz skill, as a place of no harness. The state MUST be `absent` where nothing is there, `foreign` for a foreign skill, and
for hmz's own `current` where its `hmz-version` is this hmz's version and `older` otherwise. Its JSON
document MUST be `{"version": <version>, "harnesses": [{"harness", "installed", "directory", "path",
"state", "version"}]}`, `path` being where the `SKILL.md` is or would be written and `version` being
the `hmz-version` of hmz's own skill and `null` otherwise.

**25.3.3** `hmz skills remove` MUST remove hmz's own skill from each of its places that holds one:
the `SKILL.md` and the `reference.md`, and then the directory `hmz` where nothing else is in it. It
MUST NOT remove or change a foreign skill: one in a place the line names MUST be refused, having
removed nothing, and one in any other place MUST be passed over. Where the line names no place, its
places are those of 25.3.2. Its JSON document MUST be `{"removed": [{"harness", "path"}]}`, `path`
being the path of the `SKILL.md` removed; where there is nothing to remove it MUST say so and exit
with status 0.

**25.3.4** Without `--yes`, `hmz skills remove` MUST ask on standard error before removing each
skill, read the answer from standard input, and leave in place each one not answered `y` or `yes`,
going on to the next; where standard input is not a terminal, or `--json` is given, it MUST instead
be refused as Section 16.12 states, having removed nothing.

**25.3.5** `hmz skills show` MUST write the `SKILL.md` `hmz skills add` would write now, and MUST
write no file. Its JSON document MUST be `{"name": "hmz", "version": <version>, "files": [{"name",
"text"}]}`, holding every file of the skill, `SKILL.md` first.

**25.3.6** hmz MUST NOT write, change or remove any skill in a user's skills directories but as this
section states.

## 26. `hmz help`

### 26.1. Synopsis

```text
hmz help [--all] [<command>...]
hmz help --json [<command>...]
hmz help completions bash|zsh|fish
```

**26.1.1** `hmz help` MUST be a declared command (Section 16) with the summary `show the help of hmz
or of one command`.

**26.1.2** `hmz help` MUST NOT ask a daemon anything, and MUST NOT start one. Section 16.6
notwithstanding, it MUST NOT take `--daemon`, and its help MUST NOT state it; Section 16.9
notwithstanding, it MUST NOT exit with status 3.

### 26.2. The help of `hmz`

**26.2.1** The help of `hmz`, which `hmz --help`, `hmz -h` and `hmz help` write, MUST consist of
these parts, in this order: the lines `hmz` takes, `hmz [COMMAND] [ARGS...]` and `hmz --version`;
what `hmz` is, and that `hmz` with no command opens the terminal interface; every command with its
summary, under the groups of 26.2.2; what commands share, being `--json`, `--daemon <name>`,
`--no-color` and `-h, --help` with what each does, the exit statuses of Section 16.9 with what each
means, and that under `--json` a command writes one JSON document, whose `error` holds a `code` and a
`message` where it failed; and what to run next, being `hmz COMMAND --help`, `hmz help --json`, `hmz
help --all` and `hmz help completions SHELL`.

**26.2.2** The groups MUST be these, in this order, each holding these commands in this order:

| Group | Commands |
| --- | --- |
| `Chats and epics` | `chat`, `exec`, `epic`, `hosts` |
| `Past work and backups` | `runs`, `backup` |
| `Environments` | `env` |
| `Setting things up` | `flows`, `flowverses`, `workspaces`, `settings`, `accounts`, `nous`, `runtimes`, `easytier` |
| `Daemons and devices` | `daemon`, `daemons`, `devices`, `relay`, `web` |
| `Notices and questions` | `notices`, `ai`, `btw` |
| `This program` | `skills`, `help`, `update`, `internal` |

**26.2.3** The help of `hmz` MUST list every command there is when it is written, declared or not,
exactly once, and MUST list no other. A group none of whose commands there is MUST be left out. A
command no group names MUST be listed under a last group, `Other commands`, those that are not
declared commands first.

### 26.3. The help of a command

**26.3.1** `hmz help <command>...`, `<command>...` being the words of a declared command after
`hmz` or the name alone of a command that is not one, MUST write to standard output what `hmz
<command>... --help` writes, and MUST exit with the status that exits with.

**26.3.2** Where `<command>...` names no command, `hmz help` MUST answer with a usage error (Section
16.10) that names the first word that named nothing. A word after the name of a command that is not
a declared command names nothing, and `hmz help` MUST NOT hand that command any word but `--help`.

**26.3.3** `hmz help --all` MUST write the help of `hmz` and then the help of every command, in the
order the help of `hmz` lists them, a group of declared commands before the commands under it, in
the order it declares them. `hmz help --all <command>...` MUST write the help of that command and
then of every command under it. Each help after the first MUST be preceded by an empty line, a line
of hyphens and an empty line.

### 26.4. `--json`

**26.4.1** The JSON document of `hmz help` MUST hold: `version`, the installed version of hmz;
`usage`, the line `hmz` takes; `description`, what `hmz` is; `conventions`, an object holding
`options`, the options of Section 16.6 each as an entry of `arguments` (26.4.2), `exit_status`, the
statuses of Section 16.9 each with what it means, keyed by the status written in decimal, and
`json`, what a command writes under `--json`; `groups`, a list of `{"title", "commands"}` being the
groups the help of `hmz` writes and the names of the commands under each, in its order; and
`commands`, every command in that order.

**26.4.2** A declared command in `commands` MUST be an object holding `command`, its words beginning
with `hmz`; `summary`; `description`; and `usage`. A group MUST hold besides `commands`, the commands
under it, each such an object. Any other declared command MUST hold besides: `arguments`, a list of
`{"name", "flags", "description", "positional", "required", "repeatable", "takes_value", "choices",
"default"}`, its own before those of Section 16.6; `examples`, a list of `{"line", "does"}`; `prints`;
`json`, a list of `{"field", "type", "description"}`; `exit_status`, as in 26.4.1; `daemon_methods`,
the methods of [OPENRPC] it calls; and `see_also`. Everything in it MUST be what the help of that
command states.

**26.4.3** A command that is not a declared command MUST be in `commands` as `{"command", "summary",
"help"}`, `help` being the line that writes its help.

**26.4.4** `hmz help --json <command>...` MUST write the same document with `commands` holding that
command alone.

### 26.5. Completion scripts

**26.5.1** `hmz help completions <shell>`, `<shell>` being `bash`, `zsh` or `fish`, MUST write to
standard output a script that, read by that shell, completes the command line of `hmz`. Its JSON
document MUST be `{"shell": <shell>, "script": <the script>}`. Where `<shell>` is absent, is any
other word, or is followed by another word, `hmz help` MUST answer with a usage error.

**26.5.2** The script MUST be written from the commands there are when it is asked for, and MUST
offer: after `hmz`, the name of every command; after a group of declared commands, the commands under
it; where the word being written begins with `-`, the options the declared command being written
takes, and `-h`, `--help` and `--version` after `hmz` alone; after an option that takes only some
values, those values; and for an argument that takes only some values, those values. After `hmz
help` it MUST offer what it offers after `hmz`, one word further in, and `completions` followed by
the three shells.

**26.5.3** The word after an option that takes a value MUST NOT be read as the name of a command.

**26.5.4** The script MUST NOT run `hmz` while a line is being completed.

### 26.6. How a help is set

**26.6.1** The help of `hmz` and the help of a declared command MUST be written no wider than the
terminal where standard output is a terminal, no wider than 100 columns and no narrower than 40;
and 80 columns wide where it is not. A text longer MUST be continued on the next line, under where it began. A
usage line and the line of an example MUST NOT be broken.

**26.6.2** Such a help MAY write its headings in bold, and MUST write no other escape. It MUST write
none where Section 4.2.1 says no for standard output, and none where `--no-color` is given.

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
  of the address it serves (Section 8.2.4), and the code `hmz devices pair` writes admits one device
  to the daemon until it is claimed or expires (Section 17.2.3).
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
  listeners (Section 13.2.4). `hmz daemon connect --stdio` gives whoever runs it, as this user, the
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
