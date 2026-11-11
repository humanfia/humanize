# The Humanize Protocol: Settings, Environment Variables and Files

## Abstract

This document specifies the settings file of hmz, every environment variable hmz reads, and every
file and directory hmz creates, reads, writes or removes: in the home, in a workspace, for an epic,
in this machine's own directories, in or in place of a harness's configuration directories, and on
other machines.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [FILES].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Conventions and Terminology](#2-conventions-and-terminology)
- [3. Settings File and Environment Variables](#3-settings-file-and-environment-variables)
  - [3.1. Scope](#31-scope)
  - [3.2. Terminology](#32-terminology)
  - [3.3. The file](#33-the-file)
  - [3.4. Machine keys](#34-machine-keys)
  - [3.5. `workspaces`](#35-workspaces)
  - [3.6. `fallbacks`](#36-fallbacks)
  - [3.7. `clis`](#37-clis)
  - [3.8. `runtimes`](#38-runtimes)
  - [3.9. `backup`](#39-backup)
  - [3.10. Account references](#310-account-references)
  - [3.11. Environment variables](#311-environment-variables)
- [4. The Home](#4-the-home)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. Rules common to Section 4 to Section 9](#43-rules-common-to-section-4-to-section-9)
  - [4.4. The home](#44-the-home)
  - [4.5. Settings](#45-settings)
  - [4.6. Prompt history](#46-prompt-history)
  - [4.7. Accounts](#47-accounts)
  - [4.8. Flowverses](#48-flowverses)
  - [4.9. User flows](#49-user-flows)
  - [4.10. Environment state](#410-environment-state)
  - [4.11. Epics](#411-epics)
  - [4.12. The server](#412-the-server)
  - [4.13. EasyTier](#413-easytier)
- [5. Workspaces](#5-workspaces)
  - [5.1. Scope](#51-scope)
  - [5.2. Terminology](#52-terminology)
  - [5.3. The workspace directory](#53-the-workspace-directory)
  - [5.4. What hmz never places in a workspace](#54-what-hmz-never-places-in-a-workspace)
  - [5.5. Files written through an env](#55-files-written-through-an-env)
  - [5.6. The repository](#56-the-repository)
- [6. Epic Records](#6-epic-records)
  - [6.1. Scope](#61-scope)
  - [6.2. Terminology](#62-terminology)
  - [6.3. The epic directory](#63-the-epic-directory)
  - [6.4. Records](#64-records)
  - [6.5. Events of the epic record](#65-events-of-the-epic-record)
  - [6.6. Events of a call record](#66-events-of-a-call-record)
  - [6.7. Resume journal](#67-resume-journal)
  - [6.8. Profiles](#68-profiles)
  - [6.9. Other files](#69-other-files)
  - [6.10. The `.hmzepic` archive](#610-the-hmzepic-archive)
  - [6.11. Import](#611-import)
- [7. This Machine](#7-this-machine)
  - [7.1. Scope](#71-scope)
  - [7.2. Terminology](#72-terminology)
  - [7.3. The machine directory](#73-the-machine-directory)
  - [7.4. Caches in the machine directory](#74-caches-in-the-machine-directory)
  - [7.5. The bundle](#75-the-bundle)
  - [7.6. The daemon](#76-the-daemon)
  - [7.7. Scratch directories in the machine directory](#77-scratch-directories-in-the-machine-directory)
  - [7.8. Other process-private temporary directories](#78-other-process-private-temporary-directories)
  - [7.9. The cache directory](#79-the-cache-directory)
  - [7.10. Files hmz reads and never writes](#710-files-hmz-reads-and-never-writes)
- [8. Harness Homes](#8-harness-homes)
  - [8.1. Scope](#81-scope)
  - [8.2. Terminology](#82-terminology)
  - [8.3. Real harness homes](#83-real-harness-homes)
  - [8.4. Account directories](#84-account-directories)
  - [8.5. Sessions kept in an epic](#85-sessions-kept-in-an-epic)
  - [8.6. Virtual config homes](#86-virtual-config-homes)
  - [8.7. Process-private temporary directories of a harness process](#87-process-private-temporary-directories-of-a-harness-process)
- [9. Other Machines](#9-other-machines)
  - [9.1. Scope](#91-scope)
  - [9.2. Terminology](#92-terminology)
  - [9.3. The state directory](#93-the-state-directory)
  - [9.4. Directories derived from a working directory](#94-directories-derived-from-a-working-directory)
  - [9.5. The bundle](#95-the-bundle)
  - [9.6. Mirrors](#96-mirrors)
  - [9.7. Containers, services and jobs](#97-containers-services-and-jobs)
  - [9.8. Per-turn directories](#98-per-turn-directories)
  - [9.9. Lifetimes after an epic](#99-lifetimes-after-an-epic)
- [10. Security Considerations](#10-security-considerations)
- [11. References](#11-references)
  - [11.1. Normative References](#111-normative-references)

## 1. Introduction

This document specifies the settings file of hmz, every environment variable hmz reads, and every
file and directory hmz creates, reads, writes or removes: in the home, in a workspace, for an epic,
in this machine's own directories, in or in place of a harness's configuration directories, and on
other machines.

This document is organised as follows:

- Section 3: Settings File and Environment Variables.
- Section 4: The Home.
- Section 5: Workspaces.
- Section 6: Epic Records.
- Section 7: This Machine.
- Section 8: Harness Homes.
- Section 9: Other Machines.

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 3. Settings File and Environment Variables

### 3.1. Scope

Section 3 governs the settings file: its location, how it is read and written, every key it holds
with its type, default and validation, and which part of hmz reads each key. It also governs every
environment variable hmz reads from its own environment.

Out of scope:

- The accounts, which are kept outside the settings file (Section 5 of [CORE], Section 4).
- What a runtime does once an env is put on it, and how fallback between runtimes proceeds (Section
  7 of [CORE]).
- Where a harness runs under a runtime's harness setting (Section 6 of [CORE]).
- What the fallback of a turn between places does at run time (Section 4 of [CORE]).
- Backups as a feature (Section 11 of [CORE]), notifications (Section 10 of [CORE]), side questions
  (Section 9 of [CORE]), error reports (Section 12 of [CORE]), and the daemons of other machines
  (Section 3 of [DAEMON]).
- Environment variables hmz sets for the processes it starts (Section 8, Section 9).

### 3.2. Terminology

**3.2.1** A **key path** names a value of the settings file by the keys that lead to it from the
top-level mapping, joined by `.`; `<x>` in a key path stands for any key of that mapping.

**3.2.2** A **machine key** is a key of the top-level mapping other than `workspaces`.

**3.2.3** A **workspace entry** is the value at `workspaces.<path>`.

**3.2.4** A **flow entry** is the value at `workspaces.<path>.flows.<flow>`.

**3.2.5** An **unreadable** settings file is one that exists but cannot be read, is not valid YAML,
or does not hold a mapping at its top level.

**3.2.6** A **writer** is any hmz process that changes the settings file.

**3.2.7** A place MUST be written as Section 4.2.3 of [CORE] defines it.

**3.2.8** An agent spec MUST be written as Section 4.2.2 of [CORE] defines it, which is the text of
an `-a` item after `<role>=` (Section 7.4 of [CLI]).

**3.2.9** An **env spec** is the text of an `-e` item after `<role>=` (Section 7.5 of [CLI]).

**3.2.10** A **runtime reference** is the text `<backend>:<name>`, `<backend>` being one of `ssh`,
`docker`, `swarm`, `apple-container` and `slurm`, and `<name>` a runtime name of Section 3.8.1.

### 3.3. The file

#### 3.3.1. Location and format

**3.3.1.1** The settings file MUST be the file `settings.yaml` in the home.

**3.3.1.2** The settings file MUST hold one YAML mapping.

**3.3.1.3** hmz MUST NOT create the settings file, or the home, until it writes a setting.

#### 3.3.2. Reading

**3.3.2.1** hmz MUST treat a settings file that does not exist, or that is unreadable, as an empty
mapping.

**3.3.2.2** An unreadable settings file MUST NOT prevent any hmz process from starting.

**3.3.2.3** A value whose type is not the type Section 3 gives for its key MUST be read as absent,
unless a paragraph of Section 3 specifies otherwise.

**3.3.2.4** hmz MUST preserve every key Section 3 does not define, at the top level and in a
workspace entry, across every write.

#### 3.3.3. Writing

**3.3.3.1** Every write other than that of Section 3.4.7.2 MUST change exactly one thing: one
machine key, one workspace's `flow` key together with one flow entry, one workspace entry removed,
the whole value of `fallbacks`, of `clis`, of `backup`, of `daemons` or of `notifications`, or one
runtime.

**3.3.3.2** A writer MUST guard, read and replace the settings file as Section 4.5 states for
`<home>/settings.yaml`.

**3.3.3.3** A writer MUST apply its change to the content the file holds at the time of the write,
and MUST NOT write back any other value it read earlier.

**3.3.3.4** A settings file that a write creates MUST have mode `0600`; a settings file that exists
MUST keep its mode.

**3.3.3.5** A writer MUST NOT write over an unreadable settings file.

**3.3.3.6** Every write MUST set the key `spelling` to `2`.

**3.3.3.7** Where a write of `enable_sentry`, `details`, `btw`, `every_epic`, `backup` or a
workspace entry fails, or the file is unreadable, the process MUST keep the change in effect for
itself for as long as it runs and MUST NOT report an error.

**3.3.3.8** Where a write of `fallbacks`, `clis`, `daemons`, `notifications` or a runtime fails, or
the file is unreadable, hmz MUST refuse the change with an error that names the file.

### 3.4. Machine keys

#### 3.4.1. `enable_sentry`

**3.4.1.1** `enable_sentry` MUST be a boolean that says whether hmz sends error reports (Section 12
of [CORE]).

**3.4.1.2** An absent `enable_sentry` MUST mean that the user has not been asked.

**3.4.1.3** Reading `enable_sentry` MUST NOT write it.

**3.4.1.4** `HUMANIZE_SENTRY` (Section 3.11.2.4) MUST override `enable_sentry` as Section 12.3.1 of
[CORE] states.

#### 3.4.2. `details`

**3.4.2.1** `details` MUST be a boolean that says whether the terminal interface shows every tool
call and all reasoning of a turn rather than its responses alone.

**3.4.2.2** Any value of `details` other than `true` MUST be read as `false`.

#### 3.4.3. `btw`

**3.4.3.1** `btw` MUST be a string holding an agent spec,
`<harness>[@<account>]/<model>[:<effort>]`, or the empty string.

**3.4.3.2** `btw` MUST name the agent that answers a side question asked of The Epic, for every epic
(Section 9.7 of [CORE]).

**3.4.3.3** An absent, empty or non-string `btw` MUST mean that there is no such agent, and that a
side question asked of The Epic is refused (Section 9.5.9 of [CORE]).

#### 3.4.4. `every_epic`

**3.4.4.1** `every_epic` MUST be a boolean that says whether the terminal interface's list of epics
shows every epic of this machine rather than those of the current workspace.

**3.4.4.2** Any value of `every_epic` other than `true` MUST be read as `false`.

#### 3.4.5. `notifications`

**3.4.5.1** `notifications` MUST be a mapping with the keys `kinds` and `system`.

**3.4.5.2** `notifications.kinds` MUST be a mapping from each of `done`, `failed`, `stopped`,
`asked` and `listening` to a boolean that says whether a notice of that kind is given (Section 10 of
[CORE]).

**3.4.5.3** `notifications.system` MUST be a boolean that says whether hmz also asks the operating
system to show each notice.

**3.4.5.4** Every kind and `system` MUST be read as `true` unless its value is `false`.

**3.4.5.5** A write of `notifications` MUST write every kind and `system`.

#### 3.4.6. `daemons`

**3.4.6.1** `daemons` MUST be a list of mappings, each naming the daemon of one other machine
reached over ssh or over EasyTier (Section 3 of [DAEMON]).

**3.4.6.2** Each entry MUST have the key `name` and MAY have the key `via`, `ssh` or `easytier`, an
entry without `via` being `ssh`. An `ssh` entry MAY have the keys `host`, `user`, `port`,
`identity_file`, `proxy_jump`, `options`, `alias` and `config`, with the types and validation of the
fields of the same names of an ssh runtime (Section 3.8.3), but for `options` (Section 3.4.6.4).

**3.4.6.3** `name` MUST begin with a letter or a digit, MUST consist of letters, digits, `.`, `_`
and `-`, and MUST NOT be `local` in any case.

**3.4.6.4** `options` MUST be a list of two-element lists, each a keyword and its value, with the
validation of Section 3.8.3.6 and Section 3.8.3.7.

**3.4.6.5** An entry with a key outside Section 3.4.6.2, with an invalid value, or with a `name` an
earlier entry has MUST be ignored when read and MUST be removed at the next write of `daemons`.

**3.4.6.6** The daemon of this machine MUST NOT be written in `daemons`.

**3.4.6.7** An `ssh` entry with `alias` and none of `host`, `user`, `port`, `identity_file`,
`proxy_jump` and `options` MUST be reached through the ssh configuration's host of that alias; any
other `ssh` entry MUST be reached from the fields it holds. Which of the two an entry is MUST NOT be
stored.

**3.4.6.8** An `easytier` entry MUST have the keys `secret` and `peers` and MUST NOT have any other
key but `name` and `via`; an `ssh` entry MUST NOT have `secret` or `peers`.

**3.4.6.9** `secret` MUST be a string of at least 16 bytes in UTF-8; a writer given a shorter one
MUST refuse it with `A secret must be at least 16 bytes.`

**3.4.6.10** `peers` MUST be a non-empty list of strings, each the URL of a shared EasyTier node
(Section 3.8.5.10 of [DAEMON]); a writer given none MUST refuse it with `An EasyTier daemon needs at
least one node.`

#### 3.4.7. `spelling`

**3.4.7.1** `spelling` MUST be an integer that says how env specs in the file are written.

**3.4.7.2** Where `spelling` is absent and the file holds an env spec in a spelling that Section
7.5.13 of [CLI] refuses, hmz MUST, on first reading the file, rewrite in one write every such env
spec of every flow entry as Section 3.4.7.3 specifies, setting `spelling` to `2`.

**3.4.7.3** The rewriting of Section 3.4.7.2 MUST turn `local@/<dir>` into `local/<dir>`;
`ssh@<name>/<dir>`, where no ssh runtime is written as `<name>`, into `ssh@[<name>]/<dir>`; and
`docker@local/<dir>`, `swarm@local/<dir>`, `apple-container@local/<dir>` and `slurm@local/<dir>`,
where no runtime of that backend is written as `local`, into `<backend>/<dir>`.

**3.4.7.4** Where `spelling` is `2`, hmz MUST read every env spec as written, whatever has become of
the runtimes it names.

### 3.5. `workspaces`

#### 3.5.1. Workspace entries

**3.5.1.1** `workspaces` MUST be a mapping from the path of a workspace (Section 3.5.1.2) to its
workspace entry.

**3.5.1.2** The key of a workspace entry MUST be the workspace's absolute path with every symbolic
link resolved.

**3.5.1.3** A workspace entry MUST be a mapping, and MAY be empty.

**3.5.1.4** The web interface MUST write an empty workspace entry for a workspace a user opens by
its path, and every workspace with an entry MUST be offered by the web interface (Section 3 of
[WEB]).

**3.5.1.5** `workspaces.<path>.flow` MUST be a string naming, as Section 7.3 of [CLI] names a flow,
the flow the terminal interface opens on in that workspace.

**3.5.1.6** An absent `flow` MUST make the terminal interface open on the flow `chat`.

**3.5.1.7** `workspaces.<path>.flows` MUST be a mapping from a flow's name, as the flowverse lists
it, to its flow entry.

**3.5.1.8** Removing a workspace's settings MUST remove its whole workspace entry.

#### 3.5.2. Flow entries

**3.5.2.1** `agents` MUST be a mapping from each agent role of the flow to an agent spec.

**3.5.2.2** Where any value of `agents` cannot be read as an agent spec, the whole of `agents` MUST
be read as absent.

**3.5.2.3** `envs` MUST be a mapping from each env role of the flow to an env spec.

**3.5.2.4** Where any value of `envs` is not a string, the whole of `envs` MUST be read as absent.

**3.5.2.5** `params` MUST be a mapping of the flow's params, as JSON values.

**3.5.2.6** `params` MUST be validated through the flow's params model when read, and a value the
model refuses MUST make the flow read as not set up.

**3.5.2.7** `budget` MUST be a mapping with the keys `duration`, an ISO 8601 duration or null;
`cost`, a number, the string `"Infinity"`, or null; `output_tokens`, an integer or null; and
`graceful`, a boolean or a mapping from any of `duration`, `cost` and `output_tokens` to a boolean.

**3.5.2.8** A `budget` that does not validate as a budget MUST be read as absent.

**3.5.2.9** `profile_flow` MUST be a boolean that says whether an epic of the flow started from the
terminal or the web interface profiles the flow's own Python code.

**3.5.2.10** `profile_environment` MUST be a boolean that says whether such an epic profiles the
programs its agents start.

**3.5.2.11** `profile_flow` and `profile_environment` MUST be written only as `true`, and any other
value MUST be read as `false`.

**3.5.2.12** `backup` MUST be a list of backup target names (Section 3.9) that an epic of the flow
is backed up to; an empty list MUST mean no target.

**3.5.2.13** A `backup` that is absent or not a list MUST mean the default targets.

**3.5.2.14** A name in `backup` that names no backup target MUST be dropped by the process that
starts the epic.

#### 3.5.3. Writing a flow entry

**3.5.3.1** Saving a flow's setup MUST set the workspace's `flow` and replace the whole flow entry.

**3.5.3.2** A save MUST always write `agents`.

**3.5.3.3** A save that gives no value for `envs`, `params`, `budget`, `profile_flow`,
`profile_environment` or `backup` MUST carry that key over from the file as it is at the write.

**3.5.3.4** A save that gives an empty `envs`, `params` or `budget`, or a `false` profiling switch,
MUST remove that key.

**3.5.3.5** A save that gives an empty `backup` MUST write an empty list.

#### 3.5.4. Who reads it

**3.5.4.1** The terminal interface and the web interface MUST read the workspace entry to set up an
epic they start.

**3.5.4.2** `hmz exec` and the software development kit MUST NOT read `workspaces`.

**3.5.4.3** The terminal interface MUST use a flow entry to start the flow without asking only where
its agent roles equal the flow's declared agent roles, every required env role has an env spec, its
params validate, and a budget is present for every flow that requires one.

### 3.6. `fallbacks`

#### 3.6.1. Entries

**3.6.1.1** `fallbacks` MUST be a list of mappings, each saying where a turn at one place goes when
that place cannot take it (Section 4 of [CORE]).

**3.6.1.2** `spec` MUST be a string naming the place the entry is written against.

**3.6.1.3** `to` MUST be a list of places, tried in order once the place of `spec` has failed.

**3.6.1.4** `tries` MUST be a non-negative integer, the number of times a failed turn is tried again
at the place of `spec` before the next place is taken, defaulting to 0.

**3.6.1.5** `policy` MUST be one of `none`, `constant`, `linear`, `exponential`,
`exponential-jitter` and `fibonacci`, the wait between those tries, defaulting to
`exponential-jitter`.

**3.6.1.6** `timeout` MUST be a non-negative number of seconds for which trying again MAY go on, 0
meaning no limit, and defaulting to 0.

#### 3.6.2. Reading and writing

**3.6.2.1** An entry that is not a mapping, whose `spec` does not name a place of an existing
harness, whose `spec` an earlier entry has, or that has an empty `to` and `tries` of 0 MUST be
ignored when read.

**3.6.2.2** A place in `to` that cannot be read as a place, equals `spec`, or repeats an earlier
place MUST be ignored when read.

**3.6.2.3** A `tries` or `timeout` that is not a finite number MUST be read as 0, and a negative one
as 0.

**3.6.2.4** A write of a fallback MUST be refused where a place cannot be read, where `to` contains
`spec`, or where `to` names one place twice.

### 3.7. `clis`

#### 3.7.1. Entries

**3.7.1.1** `clis` MUST be a mapping from the name of a harness a user added to either a list of
strings, the command that starts it, or a mapping with the keys `command`, `hosts` and `state`.

**3.7.1.2** `command` MUST be a non-empty list of strings, the command that starts the harness,
speaking the Agent Client Protocol.

**3.7.1.3** `hosts` MUST be a list of hosts the harness MAY reach while a flow's permission cuts the
network.

**3.7.1.4** `state` MUST be a list of paths the harness MAY write while a flow's permission forbids
writing them.

**3.7.1.5** An entry whose command is not a non-empty list MUST be ignored when read.

**3.7.1.6** A write of an added harness MUST keep the `hosts` and `state` the entry already has.

### 3.8. `runtimes`

#### 3.8.1. Layout

**3.8.1.1** `runtimes` MUST be a mapping from a backend, one of `ssh`, `docker`, `swarm`,
`apple-container` and `slurm`, to a mapping from a runtime's name to its fields.

**3.8.1.2** A runtime's name MUST begin with a letter or a digit and consist of letters, digits,
`.`, `_` and `-`.

**3.8.1.3** A runtime's backend and name MUST be the keys it is written under, whatever its fields
say.

**3.8.1.4** An entry that is not a mapping, has a field its backend does not have, has a value of
the wrong type or a value Section 3.8.2 to Section 3.8.7 refuse, or is written under an invalid name
MUST be ignored when read.

**3.8.1.5** A write of a runtime MUST be refused for any reason for which Section 3.8.1.4 ignores
one.

**3.8.1.6** A boolean MUST NOT be accepted where a number is required.

**3.8.1.7** A number with no fractional part MUST be accepted where an integer is required.

**3.8.1.8** A runtime written with the field `affinity`, a list, MUST be read as though its
`harness` were the first entry of that list, `self` read as `env`, and as though it had no `harness`
where that list is empty; the next write of it MUST NOT have `affinity`.

#### 3.8.2. Fields of every backend

**3.8.2.1** `workdir` MUST be a string that is empty, `~`, absolute, or begins with `~/`, and names
the directory an env on the runtime works in when its env spec gives none.

**3.8.2.2** `fallback` MUST be a list of runtime references, tried in order when the runtime cannot
hold an env; it MUST NOT name the runtime itself, and MUST NOT name one runtime twice.

**3.8.2.3** The references `docker:local`, `swarm:local` and `apple-container:local` in `fallback`
MUST mean docker's default daemon here, the swarm this machine manages and this Mac's Apple
containers, where no runtime of that backend is written as `local`.

**3.8.2.4** `harness` MUST be `local`, `env` or a runtime reference, defaulting to `env`, and names
where the harness of an agent whose env is on the runtime runs (Section 6 of [CORE]).

**3.8.2.5** `harness` MUST NOT name the runtime itself as a runtime reference.

**3.8.2.6** `made` MUST be `typed` or, for an ssh runtime alone, `imported`, defaulting to `typed`.

**3.8.2.7** A string field, and every string element of a list field, MUST NOT contain a line feed,
a carriage return or a NUL.

**3.8.2.8** `cpus`, `memory` and every `max_` field MUST be non-negative, 0 meaning no limit.

**3.8.2.9** `memory` MUST be a number of bytes.

#### 3.8.3. `ssh`

**3.8.3.1** An ssh runtime MUST have a non-empty `host` or a non-empty `alias`.

**3.8.3.2** `host`, `alias` and `user` MUST each be empty or begin with a letter, a digit or `_` and
consist of letters, digits, `.`, `_`, `%`, `+` and `-`.

**3.8.3.3** `port` MUST be an integer from 0 to 65535, 0 meaning the ssh configuration's port.

**3.8.3.4** `identity_file` and `config` MUST be strings with no double quote; `config` names an ssh
configuration file to read in place of the user's own.

**3.8.3.5** `proxy_jump` MUST be empty or begin with a letter, a digit or `_` and consist of
letters, digits, `.`, `_`, `%`, `+`, `@`, `:`, `,`, `[`, `]` and `-`.

**3.8.3.6** `options` MUST be a mapping from an ssh keyword, a letter followed by letters and
digits, to a non-empty value with no double quote.

**3.8.3.7** `options` MUST NOT hold the keyword `F`, nor, in any case, `HostName`, `User`, `Port`,
`IdentityFile` or `ProxyJump`.

#### 3.8.4. `docker`

**3.8.4.1** `endpoint` MUST be `local`, `unix://<path>`, `tcp://<host>:<port>`,
`ssh://[<user>@]<host>[:<port>]`, `ssh:<name>` naming an ssh runtime, or `context:<name>` naming a
docker context, and MUST default to `local`.

**3.8.4.2** `tls_dir` MUST be empty unless `endpoint` begins with `tcp://`, and names the directory
holding `ca.pem`, `cert.pem` and `key.pem`.

**3.8.4.3** `container` MUST be empty or the name or id of a running container, beginning with a
letter or a digit and consisting of letters, digits, `_`, `.` and `-`.

**3.8.4.4** `exec_user` MUST be empty or `<uid>[:<gid>]` in decimal digits.

**3.8.4.5** `exec_env` MUST be a list of `<NAME>=<value>`, `<NAME>` beginning with a letter or `_`
and consisting of letters, digits and `_`.

**3.8.4.6** `exec_wrapper` MUST be a list of non-empty strings, the words of a program every command
in the env's container runs under.

**3.8.4.7** `image` MUST be empty or contain no white space.

**3.8.4.8** `runtime` MUST be empty or an OCI runtime name of the form of Section 3.8.3.2.

**3.8.4.9** `run_args` MUST be a list of strings.

**3.8.4.10** `name_prefix` MUST be empty or begin and end with a letter or a digit, consist of
letters, digits, `_` and `-`, and be at most 54 characters long.

**3.8.4.11** `cpus` MUST be a number; `memory`, `gpu_memory` and `max_containers` MUST be integers.

**3.8.4.12** `gpus` MUST be a list of distinct device ids, each beginning with a letter or a digit
and consisting of letters, digits, `_`, `.`, `:` and `-`.

**3.8.4.13** Where `container` is set, `image`, `runtime`, `run_args`, `name_prefix`, `cpus`,
`memory`, `gpus`, `gpu_memory` and `max_containers` MUST each be empty or 0.

#### 3.8.5. `swarm`

**3.8.5.1** `endpoint`, `tls_dir`, `image`, `run_args` and `name_prefix` MUST be as Section 3.8.4
specifies for a docker runtime, `endpoint` naming a manager of the swarm.

**3.8.5.2** `cpus` MUST be a number; `memory` and `max_tasks` MUST be integers.

**3.8.5.3** `gpu_resource` MUST be empty or a generic resource name beginning with a letter and
consisting of letters, digits, `.`, `_` and `-`.

**3.8.5.4** `constraints` MUST be a list of `<attribute>==<value>` or `<attribute>!=<value>`,
`<attribute>` beginning with a letter and consisting of letters, digits, `.`, `_`, `/` and `-`.

**3.8.5.5** `nodes` MUST be a mapping from a node's host name, of the form of Section 3.8.3.2, to
the name of an ssh runtime or an ssh destination `[<user>@]<host>[:<port>]`.

#### 3.8.6. `apple-container`

**3.8.6.1** An Apple container runtime MUST have exactly the fields `image`, `run_args`, `cpus`,
`memory`, `max_containers`, `workdir`, `fallback`, `made` and `harness`, with the types and
validation of Section 3.8.2 and Section 3.8.4.

#### 3.8.7. `slurm`

**3.8.7.1** `partition`, `account` and `qos` MUST each be empty or begin with a letter, a digit or
`_` and consist of letters, digits, `.`, `_` and `-`.

**3.8.7.2** `time` MUST be empty, a number of minutes, `MM:SS`, `HH:MM:SS`, `D-HH[:MM[:SS]]`,
`UNLIMITED` or `INFINITE`.

**3.8.7.3** `constraint` MUST be empty or contain no white space and not begin with `-`.

**3.8.7.4** `python` MUST be empty, absolute, or begin with `~/`, and names a Python of at least
version 3.12 on the cluster's nodes.

**3.8.7.5** `via` MUST be `srun` or `tcp`, defaulting to `srun`.

**3.8.7.6** `run_args` MUST be a list of strings.

**3.8.7.7** `cpus` MUST be a number; `memory`, `max_jobs` and `max_wait` MUST be integers,
`max_wait` a number of seconds.

### 3.9. `backup`

#### 3.9.1. Targets

**3.9.1.1** `backup` MUST be a mapping with the keys `targets` and `defaults`.

**3.9.1.2** `backup.targets` MUST be a list of mappings, each one git repository epics are backed up
to (Section 11 of [CORE]).

**3.9.1.3** A target's `name` MUST match `[A-Za-z0-9][A-Za-z0-9_-]{0,31}` and MUST be unique among
the targets.

**3.9.1.4** A target's `url` MUST be a non-empty string that git can push to with this machine's own
credentials.

**3.9.1.5** A target's `branch` MUST be a string, defaulting as Section 11.3.1.4 of [CORE] states.

**3.9.1.6** A target's `policies` MUST be a list of distinct values from `session`, `interval` and
`end`, defaulting to the empty list, which means backing up on request alone.

**3.9.1.7** A target's `every` MUST be the interval of Section 11.3.1.5 of [CORE] as an integer
number of minutes.

#### 3.9.2. Defaults

**3.9.2.1** `backup.defaults` MUST be a list of target names, the targets an epic is backed up to
when it is started without naming any.

#### 3.9.3. Reading and writing

**3.9.3.1** A target that does not validate MUST be ignored when read, and a later target with the
name of an earlier one MUST be ignored.

**3.9.3.2** A default that names no target MUST be ignored when read.

**3.9.3.3** A write of `backup` MUST be refused, writing nothing, where a target does not validate,
two targets share a name, or a default names no target.

**3.9.3.4** Every process that starts an epic MUST read `backup` as the epic starts.

### 3.10. Account references

#### 3.10.1. Naming an account

**3.10.1.1** The settings file MUST NOT hold the credentials of any account.

**3.10.1.2** An account MUST be referred to in the settings file only by its name after an `@` in an
agent spec or a place, in `workspaces.<path>.flows.<flow>.agents`, `btw` and `fallbacks`.

**3.10.1.3** A reference to an account that does not exist MUST be refused when an epic is started
with it (Section 7.7.7 of [CLI]), and MUST NOT make the settings file unreadable.

### 3.11. Environment variables

#### 3.11.1. Reading

**3.11.1.1** A variable set to the empty string MUST be treated as unset unless Section 3.11 says
otherwise.

**3.11.1.2** Where Section 3.11 lists `off`, `0` or `no` as values, hmz MUST compare them after
removing surrounding white space and lower-casing letters.

#### 3.11.2. hmz's own variables

**3.11.2.1** `HUMANIZE_HOME` MUST name the home; a relative value MUST be taken relative to the
current directory.

**3.11.2.2** `HUMANIZE_DAEMON` MUST act as Section 3.4 of [DAEMON] states.

**3.11.2.3** `HUMANIZE_NAME` MUST name the user part of a frontend's name (Section 4.7.1.5 of
[DAEMON]).

**3.11.2.4** `HUMANIZE_SENTRY` MUST act as the override of Section 12.3.1 of [CORE].

**3.11.2.5** `HUMANIZE_SESSIONS` set to `off`, `0` or `no` MUST make every harness keep its sessions
in its own home rather than in the epic (Section 6).

**3.11.2.6** `HUMANIZE_WATCHDOG` MUST act as Section 4.12.1.3 of [CORE] states.

**3.11.2.7** `HUMANIZE_PRICES` MUST name the URL, where it contains `://`, or the file from which
hmz refreshes model prices; `off`, `0`, `no`, `none` or the empty string MUST turn refreshing off.

**3.11.2.8** `HUMANIZE_RELEASES` MUST name the URL, where it contains `://`, or the file from which
hmz learns the newest release; `off`, `0`, `no`, `none` or the empty string MUST turn asking off.

**3.11.2.9** `HUMANIZE_SHADOWS` MUST name the directory in which hmz keeps the records of mirrors,
defaulting to `~/.cache/humanize/shadows` (Section 7).

**3.11.2.10** `HUMANIZE_SSH_REUSE` set to `off`, `0`, `no`, `false` or the empty string MUST stop
hmz from sharing one ssh connection between the ssh commands it runs to one destination.

**3.11.2.11** `HUMANIZE_RENDEZVOUS` MUST name the host or address of the rendezvous broker, and
`HUMANIZE_RENDEZVOUS_PORT` the port of the broker a process starts, 0 meaning any free port.

**3.11.2.12** `HUMANIZE_TARGET`, `HUMANIZE_HARNESS`, `HUMANIZE_SHADOW`, `HUMANIZE_TOKEN` and
`HUMANIZE_LOG` MUST be the defaults of the options of `hmz internal anchor` that Section 11.2.3 of
[CLI] names.

**3.11.2.13** `HUMANIZE_EASYTIER` MUST name an EasyTier binary for hmz to use in place of the one it
downloads (Section 3.8.5 of [DAEMON]); one that does not exist MUST be ignored.

**3.11.2.14** `HUMANIZE_EASYTIER_NODES` MUST name the Uptime Kuma server whose status page
`easytier` hmz reads the community's shared EasyTier nodes from (Section 3.8.5.11 of [DAEMON]), in
place of EasyTier's own.

#### 3.11.3. Other variables

**3.11.3.1** `NO_COLOR`, `TERM` and `FORCE_COLOR` MUST decide escapes as Section 4.2 of [CLI]
specifies.

**3.11.3.2** `TEXTUAL_THEME` MUST name the theme of the terminal interface; a name the interface
does not have MUST be ignored.

**3.11.3.3** `TMUX`, `TERM_PROGRAM` and `LC_TERMINAL` MUST be read as Section 6.1.7 of [CLI]
specifies.

**3.11.3.4** `DISPLAY` and `WAYLAND_DISPLAY` MUST be read as Section 8.2.5 of [CLI] specifies.

**3.11.3.5** `CUDA_VISIBLE_DEVICES` MUST limit the GPUs a local or ssh env reports to those it lists
(Section 7 of [CORE]).

**3.11.3.6** `TMPDIR` MUST decide this machine's own directory as Section 7 specifies.

## 4. The Home

### 4.1. Scope

Section 4 specifies the **home** of **hmz** on **this machine**: its location, every file and
directory **hmz** creates in it, the format of each machine-readable file, the mode **hmz** sets,
the lifetime of each entry, and when the **user** MAY delete it. It also specifies the definitions
and rules shared by Section 4 to Section 9.

Out of scope:

- The epic directories under `<home>/epics/`: Section 6.
- The keys and values of `settings.yaml`: Section 3.
- The content of the account directories under `<home>/providers/`: Section 8.4.
- Directories outside the **home** on **this machine**: Section 7.
- The state directory of **hmz** on a **machine** other than **this machine**: Section 9.
- The directory `<workspace>/.hmz/`: Section 5.
- The process of `hmz server`: Section 13 of [CLI] and Section 3.8.5 of [DAEMON].

### 4.2. Terminology

**4.2.1** **`<home>`**: the absolute path of the **home**: the value of the environment variable
`HUMANIZE_HOME` where it is set and not empty, and `$HOME/.hmz` otherwise.

**4.2.2** **Workspace key** (`<ws>`): the absolute path of a **workspace**, with every symbolic link
resolved, in which every character outside `[A-Za-z0-9]` is replaced by one `-`.

> Informative: `/home/you/code` has the workspace key `-home-you-code`. Two distinct paths can
> have one workspace key, such as `/a/b.c` and `/a/b-c`.

**4.2.3** **Atomic replacement**: writing a file `F` by creating a new file in the directory of `F`
named `.<name of F>.<16 lowercase hexadecimal digits>.new`, writing the whole content into it,
flushing it to stable storage, and renaming it over `F`.

**4.2.4** **UTC timestamp**: a string of the form `YYYY-MM-DDTHH:MM:SS.mmmZ` stating a moment in
Coordinated Universal Time with millisecond precision.

**4.2.5** **Umask mode**: the mode that the umask of the writing process leaves of `0666` for a
file, or of `0777` for a directory.

**4.2.6** **While hmz is not running**: while no `hmz` process and no **daemon** of the **user**
runs on the **machine** the entry is on.

### 4.3. Rules common to Section 4 to Section 9

**4.3.1** Where Section 4 to Section 9 state that **hmz** writes a file by atomic replacement, a
reader of that file MUST observe either the whole previous content or the whole new
content.

**4.3.2** A file named `.<name>.<16 hex>.new` beside a file that **hmz** writes by atomic
replacement is the residue of a killed writer; **hmz** MAY leave it, and the **user** MAY delete it
at any time.

**4.3.3** Where Section 4 to Section 9 state no mode for a file or directory that **hmz** creates,
the mode of that file or directory MUST be the umask mode.

**4.3.4** Every timestamp that **hmz** writes into a file specified in Section 4 to Section 9 MUST
be a UTC timestamp, except where the paragraph specifying the file states another format.

**4.3.5** In Section 4 to Section 9, `~` names the home directory of the **user** on the **machine**
the path is on, and never the **home** of **hmz**.

**4.3.6** In Section 4 to Section 9, `<random>` names a string that **hmz** chooses so that the path
does not exist when it is created; the length and alphabet of that string are not specified.

**4.3.7** A JSON Lines file specified in Section 4 to Section 9 MUST hold one JSON value per line,
each line terminated by one line feed; a reader MUST skip a line that is not valid JSON.

### 4.4. The home

**4.4.1** `hmz` MUST NOT create `<home>` before it first writes a file under it; the first writer of
a file under `<home>` MUST create every missing directory on its path.

**4.4.2** Where `HUMANIZE_HOME` is not set, `$HOME/.hmz` does not exist and `$HOME/.humanize` is a
directory, `hmz` MUST rename `$HOME/.humanize` to `$HOME/.hmz` the first time a process resolves
`<home>`, without printing any message.

**4.4.3** Where both `$HOME/.hmz` and `$HOME/.humanize` exist, `hmz` MUST use `$HOME/.hmz`, and MUST
NOT read, modify, merge or remove `$HOME/.humanize`.

**4.4.4** Where the rename of Section 4.4.2 fails, `hmz` MUST continue with `$HOME/.hmz` without
reporting an error.

**4.4.5** `hmz` MUST NOT create in `<home>` any entry other than those specified in Section 4.5 to
Section 4.13.

**4.4.6** `hmz` MUST NOT remove `<home>`.

### 4.5. Settings

**4.5.1** `<home>/settings.yaml` holds the settings of **hmz**, as a YAML mapping whose keys and
values are specified in Section 3.

**4.5.2** `hmz` MUST create `<home>/settings.yaml` when it first writes a setting, with mode `0600`,
and MUST keep the mode of an existing file.

**4.5.3** `hmz` MUST write `<home>/settings.yaml` by atomic replacement.

**4.5.4** Each writer of `<home>/settings.yaml` MUST, by `<home>/.settings.yaml.lock`, keep every
other writer out while it reads the file, makes one change and writes the file.

**4.5.5** A writer that cannot keep the other writers out within 30 seconds, or cannot open
`<home>/.settings.yaml.lock`, MUST proceed without keeping them out.

**4.5.6** `hmz` MUST create `<home>/.settings.yaml.lock` empty, with mode `0600`, and MUST NOT
remove it.

**4.5.7** A reader of `<home>/settings.yaml` MUST NOT wait for a writer.

**4.5.8** `hmz` MUST treat a `<home>/settings.yaml` that is missing, unreadable, not valid YAML or
not a mapping as holding no settings.

**4.5.9** `hmz` MUST NOT overwrite a `<home>/settings.yaml` that is unreadable, not valid YAML or
not a mapping.

**4.5.10** `hmz` MUST NOT remove `<home>/settings.yaml`.

**4.5.11** The **user** MAY delete `<home>/settings.yaml` and `<home>/.settings.yaml.lock` while
**hmz** is not running; every setting then takes its default.

### 4.6. Prompt history

**4.6.1** `<home>/history.jsonl` is a JSON Lines file holding the lines submitted at the prompt of
the TUI, in the order submitted.

**4.6.2** Each line of `<home>/history.jsonl` MUST be a JSON object with exactly the keys:

- `at`: string, the moment of submission, `YYYY-MM-DDTHH:MM:SS.ffffffZ` in UTC with microsecond
  precision;
- `workdir`: string, the absolute path of the directory the TUI ran in, symbolic links resolved;
- `text`: string, the submitted line.

**4.6.3** The TUI MUST append one line to `<home>/history.jsonl` for each submitted prompt line,
except a blank line and a line equal to the line submitted immediately before it.

**4.6.4** `hmz` MUST NOT truncate, rewrite or remove `<home>/history.jsonl`.

**4.6.5** The **user** MAY delete `<home>/history.jsonl` at any time.

### 4.7. Accounts

**4.7.1** `<home>/providers/<cli>/<name>/` is the directory of one **account**, where `<cli>` is the
canonical name of a **harness** and `<name>` is the account name, matching
`[A-Za-z0-9][A-Za-z0-9._-]*`.

**4.7.2** `hmz` MUST create `<home>/providers/`, `<home>/providers/<cli>/` and each account
directory with mode `0700`.

**4.7.3** The content of an account directory is specified in Section 8.4.

**4.7.4** `hmz` MUST remove an account directory, with everything in it, when the **user** removes
the **account**, and MUST NOT remove it otherwise.

**4.7.5** The **user** MAY delete an account directory while **hmz** is not running; the **account**
then no longer exists.

**4.7.6** `hmz` MUST NOT read or write the directory `<home>/local/`, and the **user** MAY delete
that directory at any time.

> Informative: an earlier release of **hmz** wrote `<home>/local/`.

### 4.8. Flowverses

**4.8.1** `<home>/flowverses/<verse>/` holds one flowverse known to **hmz**, where `<verse>` is the
flowverse name; `hmz` MUST create it when the flowverse is added.

**4.8.2** `<home>/flowverses/<verse>/index/` MUST be a `git` clone of depth 1 of the index
repository of the flowverse.

**4.8.3** `hmz` MUST create `<home>/flowverses/<verse>/index/` by cloning into
`<home>/flowverses/<verse>/.index.<random>/` and renaming that directory into place.

**4.8.4** `hmz` MUST update `<home>/flowverses/<verse>/index/` by fetching the head of its remote at
depth 1 and resetting the clone to it.

**4.8.5** `hmz` MUST remove a directory `<home>/flowverses/<verse>/.index.<random>/` older than 60
seconds before it next clones the index of that flowverse.

**4.8.6** `<home>/flowverses/<verse>/installed/[<owner>/]<flow>/` holds one installed flow, where
`<owner>/` is present only for a flow the index lists under an owner.

**4.8.7** An installed flow directory MUST hold the files of the release at its commit, without
`.git` and `__pycache__` directories, every skill the flow names by URL under `skills/<skill>/`, and
the file `.installed.json`.

**4.8.8** `hmz` MUST write an installed flow into `<parent>/.<flow>.<random>/` and rename it into
place.

**4.8.9** `hmz` MUST remove a directory `<parent>/.<flow>.<random>/` older than 600 seconds before
it next installs a flow named `<flow>` into `<parent>`.

**4.8.10** `.installed.json` MUST be a JSON object with exactly the keys:

- `verse`: string, the flowverse name;
- `owner`: string, the owner, `""` for a flow listed without one;
- `name`: string, the flow name;
- `version`: string, the release installed;
- `commit`: string, the commit the files were copied from;
- `repo`, `ref`, `subdir`: strings, as the manifest of the release states them;
- `dependencies`: object mapping a flow reference to a version range;
- `skills`: object mapping each skill URL the flow names to the list of skill names fetched for it.

**4.8.11** `hmz` MUST NOT treat as installed a directory whose `.installed.json` is missing,
unreadable, or names a `verse`, `owner` or `name` other than those of its path.

**4.8.12** `hmz` MUST remove an installed flow directory when the **user** uninstalls the flow or an
update replaces it.

**4.8.13** `hmz` MUST remove `<home>/flowverses/<verse>/installed/<owner>/` when the last flow in it
is removed.

**4.8.14** `hmz` MUST remove `<home>/flowverses/<verse>/` when the **user** removes the flowverse.

**4.8.15** `hmz` MUST NOT remove `<home>/flowverses/official/`.

**4.8.16** The **user** MAY delete `<home>/flowverses/` or any directory in it while **hmz** is not
running; the flowverses and flows it held are then neither known nor installed.

### 4.9. User flows

**4.9.1** `~/.hmz/flows/` holds the flows of the flowverse `user`; its location MUST be
`$HOME/.hmz/flows/` whatever `HUMANIZE_HOME` is set to.

**4.9.2** `hmz` MUST NOT create, modify or remove an entry of `~/.hmz/flows/`, except where the
**user** asks **hmz** to copy a flow into that directory by naming it.

**4.9.3** Where Section 4.9.2 permits a copy, `hmz` MUST write it into
`~/.hmz/flows/.<flow>.<random>/` and rename it to `~/.hmz/flows/<flow>/`.

### 4.10. Environment state

**4.10.1** `<home>/envs/` holds the directories that **hmz** derives from the working directory of
an **env** whose **env machine** is **this machine**; its content is specified in Section 9.4.

**4.10.2** `<home>/envs/mirrors/` holds the local mirrors of **envs** whose **env machine** is a
container, a swarm service or a Slurm job; its content is specified in Section 9.6.

### 4.11. Epics

**4.11.1** `<home>/epics/<ws>/` holds the epic directories of the **workspace** whose workspace key
is `<ws>`; its content is specified in Section 6.

**4.11.2** `hmz` MUST NOT remove `<home>/epics/` or any directory in it, except the staging
directories specified in Section 6.11.4.

### 4.12. The server

**4.12.1** `<home>/server.json` MUST be a JSON object with exactly the keys `pid` (integer, the
process identifier of the server), `mode` (the string `p2p`), `port` (integer, the port of its `hmz
web` on the loopback) and `version` (string, the version of **hmz** it runs), with mode `0600`,
written by atomic replacement; `<home>/server.json` MUST NOT hold the secret of the server (Section
3.8.5.1 of [DAEMON]).

**4.12.2** `hmz server start` MUST write `<home>/server.json` once the server has started, and `hmz
server stop` MUST remove it once the server has gone.

**4.12.3** A `<home>/server.json` whose `pid` is not running MUST be read as no server, and MAY be
removed by `hmz`; the **user** MAY delete it while no server runs.

### 4.13. EasyTier

**4.13.1** `<home>/easytier/<version>/` MUST hold the binaries of the release `<version>` of
EasyTier that **hmz** downloaded (Section 3.8.5.6 of [DAEMON]), each binary executable by the
**user**.

**4.13.2** `hmz` MUST NOT leave in `<home>/easytier/<version>/` a binary that has not passed the
check of Section 3.8.5.6 of [DAEMON], and MUST NOT download again a binary present there.

**4.13.3** The **user** MAY delete `<home>/easytier/` or any directory in it while no process of
**hmz** uses EasyTier; `hmz` downloads it again when next needed.

## 5. Workspaces

### 5.1. Scope

Section 5 specifies every file, directory and `git` object that **hmz** creates or leaves in a
**workspace** and in the `git` repository holding it, and states what **hmz** never places there. It
covers the directory `<workspace>/.hmz/`, the files **hmz** writes when a **flow** asks it to modify
an **env**, and the `git` references and objects **hmz** adds.

Out of scope:

- The definitions and rules common to Section 4 to Section 9: Section 4.2 and Section 4.3.
- The changes the **agents** of a **flow** make to a **workspace** as their work.
- The directories **hmz** derives from a **workspace** outside it, including worktrees and temporary
  copies: Section 9.4.
- The copy of a **workspace** on another **machine**: Section 9.

### 5.2. Terminology

**5.2.1** **`<workspace>`**: the absolute path of a **workspace**.

**5.2.2** **Workspace directory**: the directory `<workspace>/.hmz/`.

**5.2.3** **Repository**: the `git` repository whose working tree contains `<workspace>`, where
there is one.

### 5.3. The workspace directory

**5.3.1** `hmz` MUST NOT create the workspace directory before it first writes a file under it.

**5.3.2** Where `<workspace>/.hmz/` does not exist and `<workspace>/.humanize/` is a directory,
`hmz` MUST rename `<workspace>/.humanize/` to `<workspace>/.hmz/` the first time a process looks for
the workspace directory, unless `<workspace>/.humanize/` is `~/.humanize/` or the directory
`HUMANIZE_HOME` names.

**5.3.3** Where both `<workspace>/.hmz/` and `<workspace>/.humanize/` exist, `hmz` MUST use
`<workspace>/.hmz/`, and MUST NOT read, modify, merge or remove `<workspace>/.humanize/`.

**5.3.4** `<workspace>/.hmz/flows/` holds the flows of the flowverse `local`, each as
`<flow>/__init__.py` with the files beside it, or as `<flow>.py`.

**5.3.5** `hmz` MUST write into `<workspace>/.hmz/flows/` only where the **user** asks **hmz** to
copy a flow into the **workspace**, by writing the copy into
`<workspace>/.hmz/flows/.<flow>.<random>/` and renaming it to `<workspace>/.hmz/flows/<flow>/`.

**5.3.6** `hmz` MUST NOT remove the workspace directory or any entry in it.

**5.3.7** `hmz` MUST NOT create in the workspace directory any entry other than those of Section
5.3.4 and Section 5.3.5.

**5.3.8** `hmz` MUST NOT add the workspace directory to `.gitignore`, to `.git/info/exclude`, or to
any other file of the **workspace** or the **repository**.

**5.3.9** The **user** MAY delete the workspace directory at any time; the flows of the flowverse
`local` it held then no longer exist.

### 5.4. What hmz never places in a workspace

**5.4.1** `hmz` MUST NOT place in a **workspace** any skill, agent, command, hook, tool server
configuration, model declaration or instruction file for a **harness**, including any entry under
`.claude/`, `.agents/`, `.cursor/`, `.codex/`, `.gemini/`, `.qwen/` or `.grok/`, and any
`AGENTS.md`, `CLAUDE.md` or `.mcp.json`.

**5.4.2** `hmz` MUST NOT place in a **workspace** any record of an **epic**, any **session**, any
trace and any exported archive, unless the **user** names a path in the **workspace** as the
destination.

**5.4.3** `hmz` MUST NOT write into a **workspace** any file other than those this document
specifies, except the files the **agents** of a **flow** write and the files a **flow** writes
through its **env**.

### 5.5. Files written through an env

**5.5.1** Where a **flow** writes a file through an **env** whose **env machine** is **this
machine**, `hmz` MUST write it into `.<12 hexadecimal digits>.hmz-tmp` in the directory of the file
and rename that file over it.

**5.5.2** Where a **flow** writes a file through an **env** whose **env machine** is not **this
machine**, `hmz` MUST write it as Section 9.3.4 states.

**5.5.3** A file of Section 5.5.1 left after a killed process is the residue of that process; the
**user** MAY delete it at any time.

### 5.6. The repository

**5.6.1** Where a **flow** takes a snapshot of an **env** whose working directory is in a
**repository**, `hmz` MUST create the reference `refs/hmz/snapshots/<name>` in that **repository**,
pointing at a commit whose author and committer are `humanize <humanize@localhost>`.

**5.6.2** The default `<name>` of a snapshot MUST be the moment of the snapshot in UTC formatted
`YYYYMMDDTHHMMSS.ffffffZ`, followed by `-` and four random lowercase hexadecimal digits.

**5.6.3** A snapshot MUST NOT include `.hmz/` or `.humanize/` at the top of the working tree.

**5.6.4** While it takes a snapshot, `hmz` MUST use a temporary index file
`<index>.hmz-snapshot.<pid>` beside the index of the **repository**, and MUST remove it and its lock
file when the snapshot ends.

**5.6.5** `hmz` MUST NOT remove a reference of Section 5.6.1; the **user** MAY delete it at any
time.

**5.6.6** Where a **flow** rewinds an **env** to a snapshot or commit, `hmz` MUST move what is
checked out in that worktree, the branch or a detached `HEAD`, to the commit recorded by the
snapshot, with the reflog message `hmz: rewind to <ref>`, and MUST discard any merge, cherry-pick or
revert in progress.

**5.6.7** Where a **flow** rewinds an **env**, `hmz` MUST NOT modify or remove `.hmz/` or
`.humanize/` at the top of the working tree.

**5.6.8** Where a **flow** adds a `git` worktree of a **repository**, `git` records the worktree in
the administrative directory of that **repository**; `hmz` MUST NOT remove that record.

**5.6.9** `hmz` MUST NOT create or modify any branch, tag, remote or configuration entry of a
**repository**, except as Section 5.6.1, Section 5.6.6 and Section 5.6.8 state.

## 6. Epic Records

### 6.1. Scope

Section 6 specifies the directory **hmz** writes for each **epic**: its path and name, every
file in it, the format of each record and the events it holds, the resume journal, the profiles, the
lock file, the session and trace directories, and the `.hmzepic` archive into which an **epic** is
exported and from which it is imported.

Out of scope:

- The definitions and rules common to Section 4 to Section 9, including `<home>`, the workspace
  key, atomic replacement and UTC timestamps: Section 4.2 and Section 4.3.
- Which paths of a **harness** are kept under `sessions/`: Section 8.5.
- The meaning of an **epic**, its states and how a **frontend** presents it: Section 3 of [CORE].
- The format of a Chrome trace document: Section 10 of [CORE].
- Backups of an **epic**: Section 11 of [CORE].

### 6.2. Terminology

**6.2.1** **Epic directory** (`<epic>`): the directory **hmz** writes for one **epic**.

**6.2.2** The epic name (Section 3.2.1 of [CORE]) of an **epic** MUST be the last path component of
its epic directory.

**6.2.3** **Record**: a JSON Lines file in an epic directory whose lines are events.

**6.2.4** **Epic record**: the record `<epic>/epic.jsonl`, which describes the **flow** the **epic**
executes.

**6.2.5** **Call record**: a record `<epic>/epic.<flow>_<id>.jsonl`, which describes one call of a
**flow** by another **flow** within the **epic**.

**6.2.6** **Event**: one line of a record: a JSON object with the keys `event`, a string naming the
event, and `at`, the UTC timestamp at which **hmz** wrote it, and the further keys Section 6.5 and
Section 6.6 specify for that event.

**6.2.7** **Legible form** of a string: the string with every maximal run of characters outside
`[A-Za-z0-9._@-]` replaced by one `-`, and every leading and trailing `-` removed.

**6.2.8** Every agent spec in a record MUST be spelled as Section 4.2.2 of [CORE] defines an agent
spec.

**6.2.9** **Role env spec**: an env spec of Section 3.2.9, preceded by `<role>=`.

### 6.3. The epic directory

**6.3.1** The path of an epic directory MUST be `<home>/epics/<ws>/<stamp>-<hex6>/`, where `<ws>` is
the workspace key of the **workspace** of the **epic**, `<stamp>` is the moment the **epic** began
in UTC formatted `YYYYMMDDTHHMMSS.mmmZ`, and `<hex6>` is six random lowercase hexadecimal digits.

**6.3.2** `hmz` MUST NOT give two epic directories created by one process the same `<stamp>`, and
MUST NOT give an epic directory a `<stamp>` earlier than that of an epic directory the same process
created before it.

**6.3.3** `hmz` MUST create the epic directory, and every missing parent, when the **epic** begins.

**6.3.4** `hmz` MUST treat as an epic directory only a directory under `<home>/epics/<ws>/` that
holds a regular file `epic.jsonl`; a reader listing epics MUST skip every other entry.

**6.3.5** `hmz` MUST list the epics of a **workspace** in ascending order of epic name.

**6.3.6** `hmz` MUST NOT remove an epic directory or any file in it.

**6.3.7** The **user** MAY delete an epic directory of an **epic** that is not running; the **epic**
then no longer exists.

> Informative: the epic directory holds the only copy of the sessions the epic kept (Section 6.9.6).

**6.3.8** An epic directory MUST contain no entries other than those specified in Section 6.4 to
Section 6.10.

### 6.4. Records

**6.4.1** Every record MUST be a JSON Lines file of events.

**6.4.2** `hmz` MUST append each event to its record as one line when the event occurs, and MUST NOT
rewrite or truncate a record, except as Section 6.11.6 states.

**6.4.3** A record MUST be encoded in UTF-8, with every character outside ASCII escaped.

**6.4.4** A reader of a record MUST ignore a key it does not know, and MUST ignore an event whose
`event` it does not know.

**6.4.5** The name of a call record MUST be `epic.<flow>_<id>.jsonl`, where `<flow>` is the legible
form of the canonical reference of the called **flow**, or `flow` where that form is empty, and
`<id>` is six random lowercase hexadecimal digits chosen per call.

**6.4.6** `hmz` MUST write a call record for each call of a **flow** by a **flow** within the
**epic**; one **flow** called twice MUST have two call records.

**6.4.7** A call made within a called **flow** MUST be written in the call record of that called
**flow**, and not in the epic record.

### 6.5. Events of the epic record

**6.5.1** The first event of an epic record MUST be `began`, written when the **epic** begins, with
the keys:

- `flow`: string, the **flow** as the **user** named it;
- `task`: string, the task given to the **flow**;
- `workspace`: string, the absolute path of the **workspace**, symbolic links resolved;
- `resumable`: boolean, whether the **flow** declares that it can be resumed;
- `ref`: string, the canonical reference of the **flow**; present only where it is known;
- `picked_up`: string, the epic name of the **epic** this one resumes; present only for an **epic**
  that resumes another;
- `agents`: array with one object per **role**, with the string keys `agent` (the **role**), `name`
  (the name of the **agent** filling it), `backend` (the **harness**), `model`, `effort` and
  `provider` (the **account**, `""` for none);
- `envs`: array of role env specs, one per **env** the **user** gave;
- `used`: array of role env specs stating where each **env** was placed; present only where it
  differs from `envs`;
- `params`: object, the parameters given to the **flow**;
- `budget`: object with the keys `duration` (number of seconds or `null`), `cost` (number of US
  dollars, or the string `"Infinity"` for none), `output_tokens` (integer or `null`) and `graceful`
  (boolean, or object with the boolean keys `duration`, `cost` and `output_tokens`);
- `profile_flow`: the value `true`; present only where the Python of the **flow** is profiled;
- `profile_environment`: the value `true`; present only where the processes of the **epic** are
  profiled;
- `backup`: array of the names of the backup targets of the **epic**; present only where it is not
  empty;
- `spelling`: the integer `2`, stating that `envs` and `used` follow the role env spec spelling of
  Section 6.2.9.

**6.5.2** A reader MUST read the `envs` and `used` of a `began` event without `spelling` as an
earlier spelling, and MUST convert each to the spelling of Section 6.2.9.

**6.5.3** `hmz` MUST write the event `reopened` into the epic record of an **epic** of a **chat**
when the **user** carries that **chat** on, with the key `task` (string, the task given on carrying
on), and MUST NOT write another `began` for it.

**6.5.4** `hmz` MUST write the event `opened` into the record of the **flow** that opened a
**session** when the **harness** of that **session** first states the identifier of the **session**,
with the keys:

- `agent`: string, the name of the **agent**, never the **role** it fills;
- `backend`: string, the canonical name of the **harness**;
- `provider`: string, the **account**, `local` where the **session** runs under no **account**;
- `session`: string, the identifier the **harness** gave the **session**;
- `name`: string, `<agent>-<backend>@<provider>-<session>` with each of the four parts in legible
  form;
- `where`: string, the directory holding the files of the **session**: `sessions/<cli>` relative to
  the epic directory where they are kept in it, and an absolute path otherwise;
- `parent`: string, the identifier of the **session** this one was forked from; present only for a
  forked **session**;
- `harness`: string, `local`, `env` or the `<backend>:<name>` of a harness runtime, where the
  **harness** went as Section 6.4.5.1 of [CORE] states; present only where the **env machine** is
  not **this machine**.

**6.5.5** `hmz` MUST NOT write `opened` for a **session** whose **harness** never stated an
identifier.

**6.5.6** `hmz` MUST write the event `called` into the record of the calling **flow** when a
**flow** calls a **flow**, with the keys `flow` (string, the canonical reference of the called
**flow**), `task` (string) and `epic` (string, the file name of the call record).

**6.5.7** `hmz` MUST write the event `returned` into the record of the calling **flow** when a call
ends, however it ends, with the keys `flow` and `epic`, equal to those of the matching `called`.

**6.5.8** A reader MUST match `returned` to `called` by the value of `epic`.

**6.5.9** `hmz` MUST NOT write the event `btw` into an epic record.

> Informative: the agent of side questions is the setting of Section 3.4.3, and no epic's own.

**6.5.10** A reader MUST skip a `btw` event in an epic record.

> Informative: an earlier release of `hmz` wrote `btw` events.

**6.5.11** `hmz` MUST write the event `usage` into the epic record immediately before each `ended`
of the epic record, with the keys `cost` (number, US dollars), `output_tokens` (integer) and
`seconds` (number), stating what the budget of the **epic** counted since it began or was last
reopened.

**6.5.12** `hmz` MUST write the event `ended` as the last event of each record when the **flow** it
describes stops, with the key `how` (string): `stopped` where the **flow** was cancelled from
outside, ran out of budget or raised the cancellation of its **flow**; `failed` where it raised any
other exception; and `done` otherwise.

**6.5.13** A reader MUST take the end of an epic record as the last `ended` after the last
`reopened`, and MUST take an epic record with no such `ended` as an **epic** that is running or
whose process was killed, telling the two apart by the lock of Section 6.9.1.

**6.5.14** A reader MUST take the spending of an **epic** as the sum of all `usage` events of its
epic record.

**6.5.15** `hmz` MUST write the event `backed` into the epic record each time it backs the **epic**
up, with the keys `to` (string, the name of the backup target), `ok` (boolean), `error` (string,
`""` where `ok` is `true`) and `why` (string, one of `session`, `interval`, `end` and `manual`).

**6.5.16** `hmz` MUST write the event `imported` into the epic record as the last event when it
imports the **epic**, with the keys `from` (string, the file name of the archive, or a description
of the backup it was pulled from) and `head` (string, the commit of the **workspace** that the
archive manifest states, `""` for none).

**6.5.17** A reader MUST ignore the `backup` key of `began` and every `backed` event preceding the
last `imported` event.

**6.5.18** `hmz` MAY write `backed` and `imported` events after the last `ended` of an epic record.

**6.5.19** An epic record MUST contain no events other than those of Section 6.5.

### 6.6. Events of a call record

**6.6.1** The first event of a call record MUST be `began`, with the keys `flow` (string, the
canonical reference of the called **flow**), `task` (string), `workspace` (string), `resumable`
(boolean) and `under` (string, the file name of the record of the calling **flow**).

**6.6.2** A call record MUST contain only the events `began`, `opened`, `called`, `returned` and
`ended`, each as Section 6.5 specifies it.

**6.6.3** The `ended` event of a call record MUST state how the call ended.

### 6.7. Resume journal

**6.7.1** `<epic>/resume.jsonl` is the journal of an **epic** whose top-level **flow** is resumable;
`hmz` MUST NOT create it for any other **epic**.

**6.7.2** Each line of `<epic>/resume.jsonl` MUST be a JSON object without whitespace between
tokens, whose key `t` names its kind:

- `{"t":"journal","v":1}`: the header, always the first line;
- `{"t":"call","id":<int>,"parent":<int>,"digest":<string>,"seq":<int>,"ref":<string>}`: a **flow**
  call began; `parent` is `0` for the top-level **flow**; `digest` is 32 lowercase hexadecimal
  digits identifying the reference, task, **roles** and parameters of the call;
- `{"t":"end","id":<int>,"ok":<bool>}`: the call ended;
- `{"t":"set","id":<int>,"key":<string>,"value":<JSON>}`: the call stored a state value;
- `{"t":"del","id":<int>,"key":<string>}`: the call deleted a state value;
- `{"t":"session","id":<int>,"role":<string>,"harness":<string>,"model":<string>,
  "session":<string>}`: a **session** of the call;
- `{"t":"tmp","id":<int>,"env":<string>,"kind":<string>,"name":<string>,"chain":<string>,
  "workdir":<string>}`: a temporary directory derived from an **env** of the call.

**6.7.3** A state value that holds a kept **session** MUST be the object
`{"\u0000session":{"harness":<string>,"id":<string>,"at":<string>,"role":<string>}}`, where `at` is
the directory of the copy of Section 6.9.7.

**6.7.4** `hmz` MUST write `<epic>/resume.jsonl` by atomic replacement when the **epic** begins: the
header alone for an **epic** that resumes nothing, and the header followed by the compacted journal
for an **epic** that resumes another.

**6.7.5** The compacted journal MUST hold, for each call in ascending order of `id`, the `call`
line, one `set` line per key with its last value, the `session` and `tmp` lines, and the `end` line
where one was written.

**6.7.6** After Section 6.7.4, `hmz` MUST only append to `<epic>/resume.jsonl`.

**6.7.7** Where an **epic** resumes another, `hmz` MUST copy `resume.jsonl` of the resumed **epic**
into the new epic directory before compacting it, and MUST NOT modify the file of the resumed
**epic**.

**6.7.8** Where a **chat** is carried on in its own epic directory, `hmz` MUST compact
`<epic>/resume.jsonl` in place by atomic replacement.

### 6.8. Profiles

**6.8.1** `<epic>/profile.jsonl` MUST exist only for an **epic** whose processes are profiled, and
MUST hold one JSON object per line with the keys:

- `event`: string, `ran` where the process was first seen, `left` where it was last seen or the
  profile stopped;
- `pid`, `ppid`: integers;
- `name`: string; `argv`: array of strings;
- `began`: number, the start of the process as the operating system states it, in seconds since the
  Unix epoch;
- `seen`: number, the moment it was first sampled, in seconds since the Unix epoch;
- `ended`: number, the moment it was last seen, in seconds since the Unix epoch;
- `threads`: array of arrays `[tid, began, ended, cpu]`, where `cpu` is user and system seconds.

**6.8.2** A reader of `<epic>/profile.jsonl` MUST take, for each pair of `pid` and `began`, the last
line.

**6.8.3** `<epic>/flow-profile.jsonl` MUST exist only for an **epic** whose **flow** is profiled,
and MUST hold one JSON object per line with the keys `t` (number, start in seconds since the Unix
epoch), `dt` (number, duration in seconds) and `stack` (array of strings, each `<function>
<file>:<line>`, outermost first).

**6.8.4** `hmz` MUST write `<epic>/flow-profile.jsonl` when the **epic** ends.

### 6.9. Other files

**6.9.1** `<epic>/.held` MUST be an empty file of mode `0600`, on which the process executing the
**epic** holds an exclusive advisory lock (`flock`) from the moment the **epic** begins or is
reopened until `ended` is written.

**6.9.2** A reader MUST take an **epic** as running exactly while a shared advisory lock on
`<epic>/.held` cannot be granted.

**6.9.3** `hmz` MUST NOT remove `<epic>/.held`.

**6.9.4** `<epic>/host.log` MUST exist only for an **epic** a **daemon** holds, and MUST hold,
appended in the order written, the standard error of the host process of the **daemon** holding the
**epic**, including the output of the **harness** processes it starts; its mode MUST be `0600`, and
`hmz` MUST NOT rotate or truncate it.

**6.9.5** `<epic>/sessions/<cli>/` MUST hold the files of every **session** of the **harness**
`<cli>` kept in the **epic**, laid out as that **harness** lays them out under its own home
directory; which paths are kept is specified in Section 8.5.

**6.9.6** `hmz` MUST NOT write a **session** into `<epic>/sessions/` and into the home directory of
its **harness** both.

**6.9.7** `<epic>/sessions/<cli>/.kept/<id>/`, where `<id>` is 32 lowercase hexadecimal digits, MUST
hold a copy of a **session** that a **flow** stored in its state, laid out as Section 6.9.5 states.

**6.9.8** An epic directory written by an earlier release of **hmz** MAY hold `sessions/<session
name>/` directories of symbolic links; a reader MUST read them as the files of that **session**.

**6.9.9** `<epic>/traces/<YYYYMMDDTHHMMSSZ>.trace.json` MUST be a Chrome trace document of the
**epic**, written when a program asks for a trace of it without naming an output.

**6.9.10** `<epic>/traces/export.trace.json` MUST be a Chrome trace document of the **epic**,
written each time the TUI exports the **epic**, replacing the previous one.

**6.9.11** `<epic>/manifest.json` and `<epic>/transcript.md` MUST exist only in an epic directory
that **hmz** imported, as copies of the members of that name of Section 6.10.

### 6.10. The `.hmzepic` archive

**6.10.1** An exported **epic** MUST be one gzip-compressed POSIX tar archive with the file name
extension `.hmzepic` and the media type `application/vnd.hmz.epic+gzip`.

**6.10.2** The default file name of an archive MUST be `<epic name>.hmzepic`.

**6.10.3** `hmz` MUST write an archive to a temporary file `.<file name>.<random>.new` of mode
`0600` in the destination directory and rename it over the destination; the archive keeps mode
`0600`.

**6.10.4** Every member of an archive MUST be a regular file under the one directory `<epic name>/`,
with mode `0644`, owner and group `0` and empty owner and group names.

**6.10.5** An archive MUST hold exactly these members, in this order:

- `epic.jsonl`, then every call record in ascending order of name;
- `resume.jsonl`, `profile.jsonl` and `flow-profile.jsonl`, each where it exists;
- `traces/<name>` for each regular file directly in `<epic>/traces/`;
- `sessions/<session name>/<path>` for each file of each **session**, where `<session name>` is the
  `name` of its `opened` event and `<path>` is relative to its `where`;
- `transcript.md`, only where the exporting program supplies a transcript;
- `manifest.json`.

**6.10.6** `hmz` MUST replace in every member each secret it can identify by the string
`[redacted]`; Section 3 of [CORE] specifies which strings are secrets.

**6.10.7** `manifest.json` MUST be a JSON object with the keys:

- `humanize`: string, the version of **hmz** that wrote it;
- `made`: string, the UTC timestamp of the export;
- `python`, `machine`: strings, the version of Python and a description of the platform;
- `epic`: string, the epic name;
- `run`: object with the keys `flow`, `task`, `began`, `ended`, `how` (`left unfinished` where the
  **epic** has no end) and `resumable`;
- `workspace`: object with the keys `at` (string, the path) and `head` (string, the `head` of the
  last `imported` event where there is one, and the current commit of the **workspace** otherwise);
- `agents`: array of objects with the keys `agent`, `name`, `backend`, `model`, `effort`, `provider`
  and `runs` (an agent spec);
- `envs`, `used`: arrays of role env specs;
- `called`: array of objects with the keys `flow`, `task`, `record`, `under`, `began`, `ended` and
  `how`, one per call record;
- `sessions`: array of objects with the keys `name`, `agent`, `backend`, `provider`, `session`,
  `flow`, `record`, `at`, `logs` (array of the member paths held for it) and, only where `logs` is
  empty, `because` (string);
- `backends`: object mapping each **harness** to an object with the keys `command`, `executable`,
  `version`, `sha256` and, for a **harness** **hmz** knows, `logs` (boolean);
- `held`: array of every member path, `manifest.json` last;
- `redacted`: array of strings stating what was redacted.

**6.10.8** A **user** MAY delete an archive at any time; **hmz** MUST NOT remove an archive it wrote
to a destination the **user** chose.

### 6.11. Import

**6.11.1** `hmz` MUST refuse to import a file whose name does not end in `.hmzepic`, that is not a
gzip-compressed tar archive, that holds other than exactly one top-level directory, whose top-level
directory name is empty, `.`, `..`, begins with `.` or contains `\`, that holds a member that is
neither a regular file nor a directory or whose path contains `..`, or that lacks `<epic
name>/epic.jsonl` or `<epic name>/manifest.json`.

**6.11.2** `hmz` MUST place an imported **epic** at `<home>/epics/<ws>/<epic name>/`, where `<ws>`
is the workspace key of the `workspace` of its `began` event, and MUST refuse an archive whose
`workspace` is not an absolute path.

**6.11.3** `hmz` MUST refuse to import an **epic** whose destination exists, and MUST NOT modify
that destination.

**6.11.4** `hmz` MUST extract an archive into a staging directory `<home>/epics/<ws>/.<epic
name>.<random>/` of mode `0700` and rename the result into place, and MUST remove the staging
directory however the import ends.

**6.11.5** `hmz` MUST move the files of each **session** from `sessions/<session name>/` to its
`where`, where that `where` is within the epic directory.

**6.11.6** `hmz` MUST rewrite each `opened` event whose `where` is an absolute path so that `where`
is `sessions/<backend>`, in every record of the imported **epic**.

**6.11.7** `hmz` MUST append `imported` to the epic record before the rename of Section 6.11.4.

## 7. This Machine

### 7.1. Scope

Section 7 specifies every file and directory **hmz** creates on **this machine** outside the
**home** and outside any **workspace**: the machine directory in the temporary directory, the cache
directory `~/.cache/humanize/`, the files of the **daemon**, the directories of ssh connection
sharing, and the temporary directories **hmz** creates for one process. For each it states the path,
the creator, the format, the mode, the lifetime and when the **user** MAY delete it.

Out of scope:

- The definitions and rules common to Section 4 to Section 9: Section 4.2 and Section 4.3.
- The temporary directories **hmz** creates for a **harness** process, including virtual config
  homes: Section 8.
- Files on a **machine** other than **this machine**: Section 9.
- Files of the macOS app: Section 4 of [DESKTOP].
- The record of `hmz server` and the EasyTier binaries, both in the **home**: Section 4.12 and
  Section 4.13.
- The messages carried over the socket of the **daemon**: Section 4 of [DAEMON].

### 7.2. Terminology

**7.2.1** **Temporary directory** (`<tmp>`): the first of the directories named by the environment
variables `TMPDIR`, `TEMP` and `TMP` of the process of **hmz** that exists and is writable, and
otherwise the first of `/tmp`, `/var/tmp` and `/usr/tmp` that is.

**7.2.2** **Machine directory** (`<mdir>`): the directory `<tmp>/humanize-<uid>`, where `<uid>` is
the numeric user identifier of the process.

**7.2.3** **Cache directory**: the directory `~/.cache/humanize/`.

**7.2.4** **Process-private temporary directory**: a directory that **hmz** creates in `<tmp>` with
a name of the stated prefix followed by `<random>`, with mode `0700`.

### 7.3. The machine directory

**7.3.1** `hmz` MUST create `<mdir>` with mode `0700` where it does not exist, the first time a
process needs an entry in it.

**7.3.2** `hmz` MUST refuse to use `<mdir>` where it is not a directory, is not owned by the
**user**, or is writable by its group or by others.

**7.3.3** `hmz` MUST report the refusal of Section 7.3.2 as `<mdir> is not a directory only this
user can write; remove it`.

**7.3.4** `hmz` MUST NOT locate `<mdir>` by `XDG_RUNTIME_DIR`.

**7.3.5** `hmz` MUST NOT remove `<mdir>`.

**7.3.6** `hmz` MUST create again, when it next needs it, every entry of `<mdir>` that is missing;
the **user** MAY delete any entry of `<mdir>` while **hmz** is not running.

> Informative: an operating system that cleans its temporary directory can empty `<mdir>`.

**7.3.7** `<mdir>` MUST contain no entries other than those specified in Section 7.4 to Section 7.8
and in Section 8.

### 7.4. Caches in the machine directory

**7.4.1** `<mdir>/prices.json` MUST be a JSON object with the keys `source` (string, the URL or path
fetched), `etag` (string), `fetched` (number, seconds since the Unix epoch), `date` (string) and
`models` (object mapping a model identifier to an object with the keys `provider`, `name` and
`per_million`, the last an object with the number keys `input`, `output`, `cache_read` and
`cache_write`).

**7.4.2** `hmz` MUST write `<mdir>/prices.json` by atomic replacement when it is older than 24 hours
and a process of **hmz** asks for prices, from the source `HUMANIZE_PRICES` names, and MUST NOT
write it from a source that gives any price that is not a finite number.

**7.4.3** `hmz` MUST remove, before each fetch of prices, every file `<mdir>/.prices.json.*.new` and
`<mdir>/prices.json.*` older than 10 minutes.

**7.4.4** `<mdir>/releases.json` MUST be the JSON object `{"latest": <string>}`, the newest release
of `hmz` that the source `HUMANIZE_RELEASES` names; `hmz` MUST write it by atomic replacement.

**7.4.5** `<mdir>/models/<cli>/<account>.json` and `<mdir>/models/<cli>/_local.json` MUST hold the
model catalogue of one **account** of the **harness** `<cli>`, and of the sign-in of that
**harness** outside any **account**, as the JSON object `{"asked": <UTC timestamp to the second>,
"models": [{"name": <string>, "efforts": [<string>, ...], "swarms": <bool>}, ...]}`.

**7.4.6** `hmz` MUST write a model catalogue by atomic replacement.

**7.4.7** `hmz` MUST ask the **harness** again for a model catalogue as Section 5.8.1 of [CORE]
states.

**7.4.8** `hmz` MUST remove the model catalogue of an **account** when it removes the **account**.

**7.4.9** `<mdir>/pinned/<url-digest>/<commit>/` MUST be a `git` checkout of the repository at the
URL whose digest is `<url-digest>` (16 lowercase hexadecimal digits), detached at `<commit>`, that
**hmz** clones for a flow reference pinned to a commit and for a release it installs.

**7.4.10** `hmz` MUST create a checkout of Section 7.4.9 by cloning into
`<mdir>/pinned/<url-digest>/.<random>` and renaming it into place, and MUST NOT remove a checkout.

**7.4.11** `<mdir>/skills/<owner>-<repo>-<digest>/`, where `<digest>` is 12 lowercase hexadecimal
digits of the SHA-256 of the URL, MUST be a `git` clone of a skill repository that a **role** of a
**flow** not installed names by URL; `hmz` MUST fetch it again on each **epic** that names it.

**7.4.12** `<mdir>/compiled/pi/` and `<mdir>/compiled/qwen/` MUST be cache directories of the
**harnesses** `pi` and `qwen`, which **hmz** names to them in `NODE_COMPILE_CACHE` where that
variable is not set, and whose content those **harnesses** write; the **user** MAY delete them while
no process of those **harnesses** runs.

**7.4.13** `<mdir>/docker-ssh/<digest>/ssh`, where `<digest>` is 16 lowercase hexadecimal digits,
MUST be an executable shell script of mode `0700`, in a directory of mode `0700`, that runs `ssh`
with the options of one docker **runtime** reached over ssh; `hmz` MUST write it by atomic
replacement and MUST NOT remove it.

**7.4.14** `<mdir>/tokens/<digest>`, where `<digest>` is 32 lowercase hexadecimal digits of the
SHA-256 of a secret, MUST hold that secret alone, with mode `0600`, in a directory of mode `0700`,
for a command line that names a secret by file.

**7.4.15** `hmz` MUST remove a file of Section 7.4.14 when the Slurm job whose secret it holds is
stopped, and MAY leave every other such file.

**7.4.16** `<mdir>/harness/` MUST be an empty directory that **hmz** mounts as the working directory
of a **harness** placed in a container on **this machine** without a working directory; `hmz` MUST
NOT write into it and MUST NOT remove it.

**7.4.17** `<mdir>/backup/<target>/` MUST be a `git` clone of the repository of the backup target
`<target>`, and `<mdir>/backup/<target>.lock` an empty file that guards that clone; `hmz` MUST NOT
remove either.

**7.4.18** `hmz` MUST NOT let more than one of its processes use a clone of Section 7.4.17 at a
time.

**7.4.19** `hmz` MUST NOT write into a backup clone any `git` configuration other than
`remote.origin.url`, `remote.origin.fetch` and, where `user.email` is not set in it, `user.name` and
`user.email`.

### 7.5. The bundle

**7.5.1** `<mdir>/humanize-<digest>.pyz`, where `<digest>` is 16 lowercase hexadecimal digits, MUST
be the zip application of **hmz** that **hmz** copies to a **machine** other than **this machine**,
with mode `0600`; `<digest>` identifies its content.

**7.5.2** `<mdir>/<stamp>.digest`, where `<stamp>` is 64 lowercase hexadecimal digits identifying
the files of **hmz** a bundle was built from, MUST hold the `<digest>` of that bundle followed by a
line feed, with mode `0600`.

**7.5.3** `hmz` MUST write a bundle into `<mdir>/humanize-<random>.pyz.new` and rename it into
place, and MUST write a `.digest` file by atomic replacement.

**7.5.4** `hmz` MUST update the modification time of the bundle an **epic** uses at least once an
hour while that **epic** runs.

**7.5.5** `hmz` MUST remove, each time it builds a bundle, every entry of `<mdir>` whose name begins
with `humanize-` or ends with `.digest` and whose modification time is more than 14 days ago, and
the files `<tmp>/humanize-<uid>.pyz` and `<tmp>/humanize-<uid>.stamp`.

**7.5.6** `hmz` MUST build a bundle in a process-private temporary directory with the prefix
`humanize-bundle-` and MUST remove it when the build ends.

### 7.6. The daemon

**7.6.1** `<mdir>/daemon.sock` MUST be the Unix-domain socket on which the **daemon** of the
**user** on **this machine** accepts **frontends**, with mode `0600`.

**7.6.2** `<mdir>/daemon.json` MUST be a JSON object with exactly the keys `pid` (integer, the
process identifier of the **daemon**), `started` (string, `YYYY-MM-DDTHH:MM:SSZ`), `kind` (the
string `daemon`) and `protocol` (integer, the protocol version specified in Section 4 of [DAEMON]),
with mode `0600`, written by atomic replacement.

**7.6.3** The **daemon** MUST remove a stale `<mdir>/daemon.sock` before it binds the socket, and
MUST remove `<mdir>/daemon.sock` and `<mdir>/daemon.json` when it closes.

**7.6.4** `<mdir>/daemon.lock` MUST be an empty file of mode `0600` that guards the **daemon** for
its whole life; `hmz` MUST NOT remove it.

**7.6.5** `<mdir>/daemon.log` MUST receive, appended, the standard output and standard error of the
**daemon** and of each of its host processes while that process holds no **epic**, with mode `0600`;
`hmz` MUST NOT rotate, truncate or remove it.

**7.6.6** The **daemon** MUST update the modification time of `<mdir>` and of each file of Section
7.6 at least once an hour while it runs.

**7.6.7** The **user** MUST NOT delete `<mdir>/daemon.sock`, `<mdir>/daemon.json` or
`<mdir>/daemon.lock` while the **daemon** runs, and MAY delete `<mdir>/daemon.log` at any time.

**7.6.8** Two processes of **hmz** whose temporary directories differ MUST reach different
**daemons**.

### 7.7. Scratch directories in the machine directory

**7.7.1** `<mdir>/web-<port>.html`, where `<port>` is the port of the web **frontend**, MUST be an
HTML page that redirects to the address of that **frontend**, including its access key, with mode
`0600`; `hmz` MUST remove it when that **frontend** stops serving.

**7.7.2** `hmz` MUST hold an uploaded `.hmzepic` archive in a directory `<mdir>/tmp<random>/` of
mode `0700` while it imports it, and MUST remove that directory when the request ends.

**7.7.3** `hmz` MUST hold an archive the web **frontend** exports in a directory
`<mdir>/tmp<random>/` of mode `0700`, and MUST remove that directory when the download ends or
fails.

**7.7.4** `hmz` MUST hold a trace it computes for a transcript in a directory `<mdir>/tmp<random>/`
and MUST remove it when the computation ends.

**7.7.5** `<mdir>/aside-<random>/` MUST hold the **sessions** of one side question that recalls a
**session** of an earlier **epic**; `hmz` MUST remove it when the side question closes, when its
**frontend** leaves, or when its host process closes.

**7.7.6** `<mdir>/.<runtime-kind>.<runtime>.lock`, where `<runtime-kind>` is `docker`, `swarm`,
`slurm` or `apple-container` and `<runtime>` is the name of a **runtime**, MUST be an empty file
that guards that **runtime**; `hmz` MUST NOT remove it.

**7.7.7** `hmz` MUST NOT let more than one of its processes size, create or submit containers,
services or jobs on one **runtime** at a time.

### 7.8. Other process-private temporary directories

**7.8.1** `hmz` MUST create a process-private temporary directory with the prefix `hmz-sessions-`
for an **epic** that has no resume journal when a **flow** of it first stores a **session** in its
state, and MUST remove it when the **epic** ends.

**7.8.2** `hmz` MUST create, for each container of a docker or Apple container **env** and for each
swarm service or Slurm job of an **env**, a process-private temporary directory with the prefix
`humanize-`, holding the file `container` (the container identifier, docker and Apple container
only) and the directory `shadow`, and MUST remove it when the container, service or job is removed.

**7.8.3** The directory of ssh connection sharing MUST be `<sdir>/humanize-ssh-<uid>/`, with mode
`0700`, holding the control sockets `ssh` creates, named `%C` or `%C-<8 hexadecimal digits>`, which
`ssh` removes 120 seconds after their last use.

**7.8.4** `<sdir>` MUST be `${XDG_RUNTIME_DIR:-<tmp>}` where the path
`<sdir>/humanize-ssh-<uid>/%C-<8 hexadecimal digits>.<16 hexadecimal digits>`, the longest name
`ssh` binds a control socket under, is at most 103 bytes long, and `/tmp` otherwise where `/tmp` is
writable.

**7.8.5** `hmz` MUST NOT create the directory of Section 7.8.3 where `HUMANIZE_SSH_REUSE` turns
sharing off, MUST NOT remove it, and MUST NOT share connections where it is not a directory owned
by the **user** that no other user is permitted to read, write or enter.

### 7.9. The cache directory

**7.9.1** The location of the mirror records MUST be the directory `HUMANIZE_SHADOWS` names, `~`
expanded, where it is set and not empty, and `~/.cache/humanize/shadows/` otherwise; it MUST NOT
follow `HUMANIZE_HOME`.

**7.9.2** For each **mirror** on **this machine**, the directory of Section 7.9.1 MUST hold
`<sha16>.json`, where `<sha16>` is the first 16 lowercase hexadecimal digits of the SHA-256 of the
absolute path of the **mirror**.

**7.9.3** `<sha16>.json` MUST be the JSON object `{"shadow": <string>, "target": <string>}` naming
the absolute path of the **mirror** and the **machine** it mirrors, written by atomic replacement
each time a **harness** begins to use the **mirror**.

**7.9.4** `<sha16>.journal` MUST be a file of mode `0600` in which the **harness** processes using
the **mirror** record what they know of its files; its content is not specified.

**7.9.5** `<sha16>.live` MUST be an empty file of mode `0600` that marks the **mirror** as used
while any **harness** process uses it.

**7.9.6** `hmz` MUST empty `<sha16>.journal` when a **harness** process begins to use the **mirror**
while no other **harness** process uses it.

**7.9.7** `hmz` MUST NOT remove the files of Section 7.9 when it removes the **mirror** they
describe.

**7.9.8** The **user** MAY delete the files of Section 7.9 while **hmz** is not running.

**7.9.9** `~/.cache/humanize/litellm/sessions/<id>.jsonl` MUST hold a **session** of the **harness**
`litellm` that is not kept in an **epic**, as JSON Lines whose first line is `{"type": "session",
"id", "parent", "cwd", "model", "timestamp"}` and whose following lines are `{"type": "message",
"timestamp", "message": {"role", "content", ...}}`.

**7.9.10** `hmz` MUST NOT remove a file of Section 7.9.9, and the **user** MAY delete it at any
time.

### 7.10. Files hmz reads and never writes

**7.10.1** `hmz` MUST NOT write `~/.ssh/config`, any file it includes, or any other file under
`~/.ssh/`.

**7.10.2** `hmz` MUST NOT write `$DSH_HOME/settings.yaml`, `$DSH_HOME/.credentials.yaml` or
`$DSH_HOME/.env`.

## 8. Harness Homes

### 8.1. Scope

Section 8 specifies the files and directories **hmz** creates for a **harness** process on its
**harness machine**, and the files of the home directory of a **harness** that **hmz** reads, keeps
elsewhere or never writes: the virtual config homes, the account directories, the redirection of
**sessions** into an **epic**, and the process-private temporary directories of a **harness**
process.

Out of scope:

- The definitions and rules common to Section 4 to Section 9: Section 4.2 and Section 4.3, and
  Section 7.2.
- The layout of an epic directory: Section 6.
- How a **harness** is driven, and which **harness** supports which feature: Section 4 of [CORE].
- How an **account** is created and signed in: Section 5 of [CORE].
- Files on a **machine** on which only an **env** runs: Section 9.

### 8.2. Terminology

**8.2.1** **Harness home**: the directory in which a **harness** keeps its configuration,
credentials and **sessions**, located for each **harness** as Section 8.3.1 states.

**8.2.2** **Real harness home**: the harness home that the environment of the **user** locates,
outside any directory **hmz** creates.

**8.2.3** **User configuration file**: a file of the real harness home, or a file in the home
directory of the **user** that a **harness** reads as its configuration, that holds settings, model
or provider declarations, agents, commands, skills, hooks or tool servers.

**8.2.4** The term managed item MUST carry the meaning Section 4.2.9 of [CORE] gives it.

**8.2.5** **Virtual config home**: a process-private temporary directory on the **harness machine**
that **hmz** creates for one **harness** process and that the process uses as its harness home.

**8.2.6** **Kept path**: a path, relative to the harness home, at which a **harness** writes the
files of its **sessions**.

### 8.3. Real harness homes

**8.3.1** The real harness home of each **harness** MUST be located by the variable and default
below, where a variable that is set names the directory, `<var>/<sub>` where a sub-directory is
stated, and the default applies under `$HOME` otherwise:

- `claude`: `CLAUDE_CONFIG_DIR`, default `~/.claude`;
- `codex`: `CODEX_HOME`, default `~/.codex`;
- `dsh`: `DSH_HOME`, default `~/.dsh`;
- `grok`: `GROK_HOME`, default `~/.grok`;
- `kimi`: `KIMI_CODE_HOME`, default `~/.kimi-code`;
- `pi`: `PI_CODING_AGENT_DIR`, default `~/.pi/agent`;
- `omp`: `PI_CODING_AGENT_DIR`, default `~/.omp/agent`;
- `qwen`: `QWEN_HOME`, default `~/.qwen`;
- `opencode`: `XDG_DATA_HOME` with sub-directory `opencode`, default `~/.local/share/opencode`;
- `mimo`: `XDG_DATA_HOME` with sub-directory `mimocode`, default `~/.local/share/mimocode`;
- `cursor-agent`: `CURSOR_CONFIG_DIR`, default `~/.cursor`;
- `mcode`: `MINIMAX_DATA_DIR`, default `~/.minimax`;
- `agy`: no variable, default `~/.gemini/antigravity-cli`;
- `litellm`: no variable, default `~/.cache/humanize/litellm`.

**8.3.2** `hmz` MUST NOT create, modify, replace or remove any user configuration file, on any
**machine**.

**8.3.3** The user configuration files of Section 8.3.2 MUST include `~/.claude.json`, every file
under `~/.claude/`, `~/.codex/config.toml`, `~/.grok/config.toml`, `~/.pi/agent/models.json`,
`~/.omp/agent/models.yml`, the `config.yaml` of MiniMax Code, every file under
`~/.gemini/antigravity-cli/agents/`, and the settings files of Qwen Code, opencode, MiMo Code, Kimi
Code and Cursor Agent.

**8.3.4** `hmz` MUST NOT write credentials into a real harness home, except where the **user** signs
a **harness** in outside any **account** and the **harness** itself writes them.

**8.3.5** Where a **session** is not kept in an **epic** (Section 8.5.6), `hmz` MUST leave the
**harness** to write that **session** at its kept paths in the real harness home, and `hmz` MAY
copy into those paths the files of a **session** that it forks or carries on.

### 8.4. Account directories

**8.4.1** The account directory `<home>/providers/<cli>/<name>/` (Section 4.7) MUST hold
`provider.json`, and MAY hold the directories `home/`, `user/` and `config/`, each of mode `0700`.

**8.4.2** `provider.json` MUST be a JSON object with the keys `cli` (string), `name` (string), `way`
(string, the sign-in way, default `env`), `env` (object mapping a variable name to a string value),
`args` (array of strings) and `made` (string, `YYYY-MM-DDTHH:MM:SSZ`), with mode `0600`, written by
atomic replacement.

**8.4.3** A reader of `provider.json` MUST take `cli` and `name` from the path where they differ
from the file, and MUST ignore the key `fallback`.

**8.4.4** `home/<path>` MUST hold a credential file the **harness** writes at `<path>` relative to
its harness home, `user/<path>` one it writes at `<path>` relative to `~`, and `config/<path>` one
it writes at `<path>` relative to `${XDG_CONFIG_HOME:-~/.config}`, each written by the **harness**
itself while it runs under the **account**.

**8.4.5** The credential files of each **harness** MUST be these, and no others:

- `claude`: `home/.credentials.json`, `home/.claude.json`, `user/.claude.json`, `config/anthropic`;
- `codex`: `home/auth.json`;
- `agy`: `home/antigravity-oauth-token`;
- `grok`: `home/auth.json`, `home/mcp_credentials.json`;
- `kimi`: `home/credentials`, `home/oauth`;
- `pi`: `home/auth.json`, `home/auth.json.lock`;
- `opencode`, `mimo`: `home/auth.json`, `home/mcp-auth.json`;
- `cursor-agent`: `home/cli-config.json`, `config/cursor/auth.json`, `user/.cursor/auth.json`;
- `mcode`: `home/config.yaml`, `home/auth`;
- `dsh`, `omp`, `qwen`, `litellm`: none.

**8.4.6** Where `hmz` stages copies of credential files for a **harness** process on Linux, it MUST
place them in `/dev/shm/hmz-<pid>-<16 hexadecimal digits>-<random>/` of mode `0700`, as files
`<n>.<name>` of mode `0600` no larger than 1 MiB each, where `<pid>` is the process that staged
them.

**8.4.7** `hmz` MUST use a staged copy of Section 8.4.6 only to answer a read of the **harness**
process, and MUST take it afresh from the credential file of the **account** once that file changes.

**8.4.8** Every write of a **harness** process to a credential file of which `hmz` staged a copy
MUST reach the credential file of the **account** at once, and MUST NOT reach the staged copy.

**8.4.9** `hmz` MUST NOT write a staged copy back to the credential file of the **account**.

**8.4.10** `hmz` MUST remove a staging directory of Section 8.4.6 when the process that staged it
ends, and MUST remove every such directory of the **user** whose `<pid>` no longer runs before it
creates another.

**8.4.11** Where a **harness** runs under an **account** under harness location env on a **machine**
other than **this machine**, `hmz` MUST place copies of the credential files on that **machine** as
Section 9.8 states.

**8.4.12** Under harness location standalone, `hmz` MUST NOT place any credential file of an
**account** on the **harness machine** (Section 6.5.3.3 of [CORE]).

### 8.5. Sessions kept in an epic

**8.5.1** For a **session** kept in an **epic**, `hmz` MUST make the **harness** process read and
write each kept path at `<epic>/sessions/<cli>/<kept path>` instead of in its harness home.

**8.5.2** The kept paths of each **harness** MUST be these:

- `claude`: `projects`, `sessions`, `file-history`, `session-env`, `tasks`, `todos`, `plans`;
- `codex`: `sessions`, `archived_sessions`, `session_index.jsonl`, `state_*.sqlite*`,
  `thread_history_*.sqlite*`, `goals_*.sqlite*`, `queue_*.sqlite*`, `memories_*.sqlite*`,
  `thread-writer-locks`, `shell_snapshots`;
- `agy`: `conversations`, `brain`, `annotations`, `implicit`, `presence`,
  `conversation_summaries.db*`, `jetbox_summaries_proto.pb`, `cache/last_conversations.json`;
- `dsh`: the whole harness home, named to the **harness** in `DSH_HOME`;
- `grok`: `sessions`, `active_sessions.*`;
- `kimi`: `sessions`, `session_index.jsonl`, `workspaces.json`, `server/events`, `search-index`,
  `file-history`;
- `pi`, `omp`: `sessions`;
- `qwen`: `projects`, `tmp`, `file-history`;
- `opencode`: `opencode.db*`, `storage`;
- `mimo`: `mimocode.db*`, `storage`;
- `cursor-agent`: `chats`, `projects/*/agent-transcripts`;
- `mcode`: `v2/sqlite`, `v2/sessions`, `background-tasks`;
- `litellm`: `sessions`, written by **hmz** as Section 7.9.9 states.

**8.5.3** `hmz` MUST NOT change the paths of a **harness** process other than its kept paths, its
harness home (Section 8.6) and its credential files (Section 8.4).

**8.5.4** Where a fenced `mcode` process runs whose **session** is not kept, `hmz` MUST place the
lock file of MiniMax Code in `<mdir>/mcode/`.

**8.5.5** For a side question that recalls a **session** of an earlier **epic**, `hmz` MUST keep its
**sessions** in the directory of Section 7.7.5, and MUST NOT write them into the earlier **epic**.

**8.5.6** `hmz` MUST NOT keep a **session** in an **epic**, other than one of `dsh` or `litellm`,
where the **harness machine** can neither supervise the **harness** process nor link its kept paths
as Section 8.5.7 states, where the **harness machine** is not **this machine**, where
`HUMANIZE_SESSIONS` is `off`, `0` or `no`, or where the **agent** is driven outside any **epic**.

**8.5.7** Where **this machine** cannot supervise a **harness** process that runs in a virtual
config home (Section 8.6) and whose kept paths are each a name directly under its harness home,
`hmz` MUST keep its **session** in the **epic** through that virtual config home instead:

- each kept path that is not a glob MUST be a symbolic link to `<epic>/sessions/<cli>/<kept path>`,
  that directory being created where the kept path is a directory, and no file being created where
  the kept path is a file;
- each entry of the real harness home or of `<epic>/sessions/<cli>/` whose name matches a kept path
  that is a glob MUST be a symbolic link to `<epic>/sessions/<cli>/<name>`, whether or not that file
  exists there;
- where the process creates a file in the virtual config home whose name matches a kept path that is
  a glob, `hmz` MUST move it into `<epic>/sessions/<cli>/` when it removes the virtual config home,
  unless a file of that name is there already.

### 8.6. Virtual config homes

**8.6.1** For each process of the **harnesses** `claude`, `codex` and `qwen`, and for each process
of the **harnesses** `grok`, `pi`, `omp`, `mcode`, `agy`, `cursor-agent` and `kimi` to which **hmz**
adds a managed item, `hmz` MUST create a virtual config home on the **harness machine** before the
process starts, as Section 4.5.2 of [CORE] states.

**8.6.2** A virtual config home MUST be a directory under the temporary directory of the **harness
machine**, of mode `0700`, owned by the **user** the **harness** process runs as.

**8.6.3** A virtual config home MUST hold a copy of each configuration file of the real harness home
that the **harness** rewrites while running, merged with the managed items of the process, a
user-level skills directory holding the **user**'s skills and the flow's, the symbolic links of
Section 8.5.7 where that paragraph applies, and a symbolic link to each other entry of the real
harness home.

**8.6.4** `hmz` MUST NOT copy a credential file into a virtual config home; the virtual config home
MUST reach each credential file of the **account** through a symbolic link or through the
redirection of Section 8.4.

**8.6.5** `hmz` MUST make the **harness** process use the virtual config home as its harness home,
through the variable of Section 8.3.1 or a command-line argument of the **harness**.

**8.6.6** `hmz` MUST remove a virtual config home when its **harness** process exits, and MUST NOT
reuse it for another process.

**8.6.7** A change a **harness** process makes to a copied user configuration file MUST remain in
the virtual config home and MUST NOT reach the real harness home.

**8.6.8** A write a **harness** process makes through a symbolic link of Section 8.6.3 MUST reach
the real harness home, or the **epic** where the link is one of Section 8.5.7.

**8.6.9** Where a **harness** process replaces a symbolic link of Section 8.6.3 with a file or a
directory, `hmz` MUST, when the process exits, write that file, or each new or changed file of that
directory, to the entry the link named, or to the **account**'s file where Section 8.4 redirects it,
unless that entry is at least as new.

**8.6.10** `hmz` MUST deliver every managed item to a **harness** process only through its virtual
config home, its command-line arguments, its environment, or a process-private temporary directory
of Section 8.7.

### 8.7. Process-private temporary directories of a harness process

**8.7.1** `hmz` MUST create the directories of Section 8.7 on the **harness machine** with mode
`0700`, and MUST remove each when the **agent** or **session** it serves ends. A directory of
Section 8.7.2 to Section 8.7.5 MUST be created in `/tmp` rather than `<tmp>` where the path of its
socket would otherwise be longer than 103 bytes and `/tmp` is writable.

**8.7.2** A directory with the prefix `humanize-hook-` MUST hold the Unix-domain socket `hook.sock`
on which the hooks of a **harness** process report to **hmz**.

**8.7.3** A directory with the prefix `humanize-tools-` MUST hold the Unix-domain socket
`tools.sock` through which a **harness** process calls the tools a **flow** defines.

**8.7.4** A directory with the prefix `humanize-preload-` MUST hold the Unix-domain socket
`said.sock` on which a **harness** process reports what it does.

**8.7.5** A directory with the prefix `humanize-clis-` MUST hold the Unix-domain socket `cli.sock`
and the directory `bin/`, holding one executable shell script of mode `0700` for each command line a
**flow** defines; `hmz` MUST prepend `bin/` to the `PATH` of the **harness** process.

**8.7.6** A directory with the prefix `hmz-dsh-` MUST hold `humanize.patch.yml`, the configuration
patch of one `dsh` process.

**8.7.7** A directory with the prefix `hmz-gateway-` MUST hold `config.yaml`, of mode `0600`, the
configuration of one LiteLLM gateway process, including the credentials of its **account**.

**8.7.8** A directory with the prefix `hmz-fence-` MUST be the temporary directory of a fenced
process, named to it in `TMPDIR`, `TMP` and `TEMP`, and MAY hold `cache/<variable>/` for each cache
variable whose usual location the fence does not let the process write.

**8.7.9** A directory with the prefix `hmz-homes-` MUST hold, for each turn of a **harness** that
runs under harness location env on another **machine** under an **account**, one file named by 32
lowercase hexadecimal digits whose lines are `<VARIABLE>=<path>`, naming the directory on that
**machine** in which each harness home variable of the turn points; `hmz` MUST remove each such file
when its turn ends.

**8.7.10** The **user** MUST NOT delete a directory of Section 8.6 or Section 8.7 while its process
runs, and MAY delete it after that process ends.

## 9. Other Machines

### 9.1. Scope

Section 9 specifies everything **hmz** creates on a **machine** that an **env** or a **harness**
is placed on, including **this machine** where an **env** runs on it: the state directory, the
directories derived from the working directory of an **env**, the bundle of **hmz**, the
**mirrors**, the containers, swarm services and Slurm jobs with their names and labels, and the
per-turn directories; and it states when each is removed.

Out of scope:

- The definitions and rules common to Section 4 to Section 9: Section 4.2 and Section 4.3, and
  Section 7.2.
- How a **placement** chooses a **machine** and a **runtime**: Section 6 of [CORE].
- What an **env** offers a **flow**: Section 7 of [CORE] and Section 3 of [PYTHON].
- The process-private temporary directories of a **harness** process: Section 8.7.
- The **workspace** itself and its **repository**: Section 5.

### 9.2. Terminology

**9.2.1** **Target**: a **machine** on which **hmz** places an **env** or a **harness**: an ssh
host, a docker or Apple container, a swarm service, a Slurm job, a server reached over TCP, or
**this machine**.

**9.2.2** **State directory** (`<state>`): on **this machine**, `<home>`; on an ssh host or a Slurm
node, `${HUMANIZE_HOME:-$HOME/.hmz}` as the login shell of the **user** there expands it, a relative
value taken under `$HOME`.

**9.2.3** **Bundle cache** (`<cache>`): the directory on a **target** that holds the bundle of
**hmz**: `$HOME/.cache/humanize` on an ssh host and on a Slurm node; `/tmp/humanize` in a container;
`/tmp/humanize-<user>` in a docker container whose **runtime** names the user `<user>` to execute
as.

**9.2.4** **Mirror root** (`<mirrors>`): the directory on a **harness machine** other than **this
machine** that holds **mirrors**: `$HOME/.cache/humanize-mirrors` on an ssh host and on a Slurm
node; `/tmp/humanize-mirrors` in a container; `/tmp/humanize-mirrors-<user>` in a docker container
whose **runtime** names the user `<user>`.

**9.2.5** **Workdir digest**: lowercase hexadecimal digits of a BLAKE2b digest of the absolute path
of a working directory.

### 9.3. The state directory

**9.3.1** `hmz` MUST create on a **target** only the entries Section 9 and Section 8 specify,
besides the files the **agents** and the **flow** write as their work.

**9.3.2** Where `HUMANIZE_HOME` is not set on an ssh host, `$HOME/.hmz` does not exist there and
`$HOME/.humanize` is a directory there, `hmz` MUST rename `$HOME/.humanize` to `$HOME/.hmz` when it
first probes that host.

**9.3.3** `hmz` MUST NOT create on a **target** other than **this machine** any entry of `<state>`
other than `envs/`.

**9.3.4** Where **hmz** writes a file on a **target** other than **this machine**, it MUST write it
into `<file>.humanize-<pid>-<n>.tmp` beside it, where `<pid>` is the serving process and `<n>` a
sequence number, and rename that file over it; a killed writer MAY leave such a file, and the
**user** MAY delete it at any time.

### 9.4. Directories derived from a working directory

**9.4.1** `<state>/envs/<name>-<digest>/`, where `<name>` is the last component of the working
directory of an **env**, truncated to 32 characters, and `<digest>` its workdir digest, MUST hold
everything **hmz** derives from that working directory on that **target**.

**9.4.2** `<state>/envs/<name>-<digest>/clones/<id>-<digest>/` MUST be a temporary copy of the
working directory, where `<id>` is the identifier the **flow** gives the copy, truncated to 40
characters, and `<digest>` a digest of that identifier.

**9.4.3** `hmz` MUST make a temporary copy in `<copy>.part.<pid>/` and rename it into place, and
MUST remove a `<copy>.part.<pid>/` whose `<pid>` no longer runs before it makes another copy in the
same directory.

**9.4.4** `hmz` MUST remove a temporary copy when the **flow** destroys it or the call that made it
ends, and MUST keep it where the **epic** is resumable and has not ended.

**9.4.5** `hmz` MUST remove a directory of Section 9.4 by renaming it to
`<path>.part.gone.<random>.<pid>` and then removing that.

**9.4.6** On **this machine**, `<copy>.lock` MUST be a file of mode `0644` on which the process
holding the temporary copy holds an exclusive advisory lock; `hmz` MUST remove it when the copy is
destroyed.

**9.4.7** `<state>/envs/<name>-<digest>/scratch/<id>-<digest>/` MUST be a scratch directory a
**flow** asks for, with the lifetime of Section 9.4.4.

**9.4.8** `<state>/envs/<name>-<digest>/worktrees/<ref>-<8 hexadecimal digits>/` MUST be a `git`
worktree a **flow** adds without naming its directory, where `<ref>` is the reference checked out,
truncated to 32 characters, or `head`; `hmz` MUST NOT remove it.

**9.4.9** The **user** MAY delete `<state>/envs/` while no **epic** uses it.

### 9.5. The bundle

**9.5.1** `<cache>/humanize-<digest>.pyz` MUST be the bundle of **hmz** of Section 7.5, copied to
the **target**.

**9.5.2** `hmz` MUST create `<cache>` where it is missing; in a docker container whose **runtime**
names the user to execute as, `hmz` MUST give `<cache>` mode `0700` and refuse a `<cache>` that is a
symbolic link or not owned by that user.

**9.5.3** `hmz` MUST write a bundle into `<path>.<pid>` and rename it into place, and MUST NOT
rewrite a bundle whose content matches its `<digest>`.

**9.5.4** `hmz` MUST update the modification time of the bundle each time it runs it.

**9.5.5** `hmz` MUST remove, each time it copies a bundle to a `<cache>`, every other entry of that
`<cache>` whose name begins with `humanize-` and contains `.pyz` and whose modification time is more
than 14 days ago.

**9.5.6** The **user** MAY delete `<cache>` while **hmz** is not running on that **target**.

### 9.6. Mirrors

**9.6.1** For an **env** in a container, a swarm service or a Slurm job, `hmz` MUST keep the
**mirror** of its working directory on **this machine** at `<home>/envs/mirrors/<unit>/<workdir
digest>/`, where `<unit>` is the name of the container, service or job.

**9.6.2** `hmz` MUST remove `<home>/envs/mirrors/<unit>/` when it removes the container, service or
job, and when it finds the container, service or job of a process of the **user** on the same host
that no longer runs.

**9.6.3** For a **harness** whose **harness machine** is not **this machine**, `hmz` MUST keep the
**mirror** of the **workspace** at `<mirrors>/<sha16>/` on the **harness machine**, where `<sha16>`
is 16 lowercase hexadecimal digits of a SHA-256 digest of the **workspace**, the path on the **env
machine** and the **env machine**, and MUST name it to the **harness** process in `HUMANIZE_SHADOW`.

**9.6.4** `hmz` MUST NOT remove a **mirror** of Section 9.6.3; the **user** MAY delete it while no
**harness** uses it.

**9.6.5** On every **harness machine** that holds a **mirror**, `hmz` MUST write the mirror records
of Section 7.9.

**9.6.6** A **mirror** MUST hold the files of the working directory it mirrors, and MAY hold, while
the content of a file is being fetched, a file `<file>.humanize-fetch`; `hmz` MUST NOT write any
other file of its own into a **mirror**.

**9.6.7** `hmz` MUST refuse to use as a **mirror** a directory that holds files and is not recorded
as a **mirror**, and a directory recorded as the **mirror** of another **machine**, unless the
**user** forces it.

### 9.7. Containers, services and jobs

**9.7.1** The name of a container, swarm service or Slurm job **hmz** creates for an **env** MUST be
`<name_prefix>-<role>-<8 hexadecimal digits>` where the docker or swarm **runtime** sets
`name_prefix`, and `humanize-<runtime>-<role>-<8 hexadecimal digits>` otherwise, where `<runtime>`
is the name of the **runtime** and `<role>` the **role** of the **env**.

**9.7.2** Each container, swarm service and Slurm job **hmz** creates MUST carry the labels
`humanize=<uid>`, `humanize.provider=<runtime>`, `humanize.role=<role>`, `humanize.host=<host name
of this machine>` and `humanize.pid=<process identifier>`, and `humanize.cpus`, `humanize.memory`
and `humanize.gpus` where the **env** sets them; an Apple container MUST NOT carry `humanize.gpus`.

**9.7.3** A Slurm job MUST carry its labels, and `humanize.name=<job name>`, URL-encoded in its
comment.

**9.7.4** A docker container **hmz** creates for an **env** MUST mount only the working directory of
the **env**, at the same path, and MUST run with `HOME=/tmp`, and with `NVIDIA_VISIBLE_DEVICES=void`
where no GPU is handed to it.

**9.7.5** `hmz` MUST remove a container, swarm service or Slurm job it created when the **env** it
serves closes, and when it finds that the process named by its `humanize.pid` on the host named by
its `humanize.host` no longer runs.

**9.7.6** `hmz` MUST create a container named `humanize-gpus-<8 hexadecimal digits>` and a container
probing the owner of the working directory only with automatic removal on exit, each labelled
`humanize=<uid>`.

**9.7.7** A Slurm job submitted for an **env** reached over TCP MUST write its output to
`/tmp/humanize-slurm-<job id>.out` on its node; `hmz` MUST NOT remove that file.

**9.7.8** `hmz` MUST NOT write a batch script file for a Slurm job.

### 9.8. Per-turn directories

**9.8.1** For each turn of a **harness** that runs natively on a **target** other than **this
machine** under an **account** whose credential files are in its harness home, `hmz` MUST create on
that **target**, with umask `077`, a directory by `mktemp -d` in the temporary directory of the
**target**, and MUST give it mode `0700`.

**9.8.2** The directory of Section 9.8.1 MUST hold each credential file of the **account** at
`<variable>/<path>`, where `<variable>` is the lowercase name of the harness home variable and
`<path>` the path of the file under that home, each with mode `0600`; `hmz` MUST name the directory
to the **harness** in that variable and in `XDG_CONFIG_HOME`.

**9.8.3** `hmz` MUST remove the directory of Section 9.8.1 when the turn ends, and MAY leave it
where the connection to the **target** is lost.

**9.8.4** For a fenced **harness** process on a **target** other than **this machine**, `hmz` MUST
create its temporary directory at the path of Section 8.7.8 on the **target**, with mode `0700`, and
MUST NOT remove it.

**9.8.5** For a fenced **harness** process, `hmz` MUST create, with mode `0700`, each missing
directory of the home directory of the **user** that the fence lets the process write and whose name
has no `.`, and MUST NOT remove it.

### 9.9. Lifetimes after an epic

**9.9.1** `hmz` MUST NOT leave, after an **epic** ends, any container, swarm service or Slurm job it
created for that **epic**, any `<home>/envs/mirrors/<unit>/` of it, or any per-turn directory of
Section 9.8.1, except as Section 9.6.2 and Section 9.8.3 permit.

**9.9.2** After an **epic** ends, `hmz` MUST leave on a **target** only these entries of its own:

- the temporary copies and scratch directories of a resumable **epic** (Section 9.4.2 and Section
  9.4.7);
- the worktrees of Section 9.4.8;
- `<cache>` and the bundles in it (Section 9.5);
- the **mirrors** of Section 9.6.3 and their records;
- the Slurm output files of Section 9.7.7;
- the directories of Section 9.8.4 and Section 9.8.5;
- the residue files of Section 9.3.4.

## 10. Security Considerations

This section states no requirement of its own. It names the properties stated elsewhere in this
document on which the security of a user's machine, credentials and work depends.

- The settings file MUST NOT hold the credentials of any account and refers to an account only by
  its name (Section 3.10.1.1 and Section 3.10.1.2).
- A settings file that hmz creates, and its lock file `<home>/.settings.yaml.lock`, have mode `0600`
  (Section 3.3.3.4, Section 4.5.2 and Section 4.5.6).
- The `secret` of an `easytier` entry of `daemons` is stored in the settings file and is at least 16
  bytes long (Section 3.4.6.8 and Section 3.4.6.9).
- `<home>/providers/`, each `<home>/providers/<cli>/` and each account directory are created with
  mode `0700` (Section 4.7.2).
- `<home>/server.json` has mode `0600` and does not hold the secret of the server (Section 4.12.1).
- `HUMANIZE_TOKEN` carries the default of a token option of `hmz internal anchor` in the environment
  of a process (Section 3.11.2.12).
- hmz places no skill, hook, tool server configuration or instruction file for a harness in a
  workspace, and no record of an epic or session there unless the user names such a destination
  (Section 5.4.1 and Section 5.4.2).
- hmz keeps in `<home>/easytier/<version>/` no downloaded binary that has not passed its check
  (Section 4.13.2).
- An exported archive is written with mode `0600`, and every secret **hmz** can identify is
  replaced in each of its members by `[redacted]` (Section 6.10.3 and Section 6.10.6).
- An archive is refused on import where it holds a member that is neither a regular file nor a
  directory, a member path containing `..`, or other than exactly one top-level directory, and an
  import never modifies an existing destination (Section 6.11.1 and Section 6.11.3).
- The machine directory has mode `0700` and is refused where it is not a directory, is not owned by
  the **user**, or is writable by its group or by others (Section 7.3.1 and Section 7.3.2).
- The socket, record, lock and log of the **daemon**, the secret files under `<mdir>/tokens/` and
  the redirect page holding the access key of the web **frontend** each have mode `0600` (Section
  7.4.14, Section 7.6 and Section 7.7.1).
- `hmz` never creates, modifies, replaces or removes a user configuration file on any **machine**,
  and never writes a file under `~/.ssh/` (Section 7.10.1 and Section 8.3.2).
- Credential files of an **account** are held in directories of mode `0700`, staged copies of them
  have mode `0600` in a directory of mode `0700` that is removed when the staging process ends, and
  no credential file is copied into a virtual config home (Section 8.4.1, Section 8.4.6, Section
  8.4.10 and Section 8.6.4).
- Under harness location standalone no credential file of an **account** is placed on the
  **harness machine**, and credential files placed on another **target** for a turn are held with
  mode `0600` in a directory of mode `0700` that is removed when the turn ends, except where the
  connection to the **target** is lost (Section 8.4.12 and Section 9.8.1 to Section 9.8.3).
- After an **epic** ends, `hmz` leaves on a **target** only the entries Section 9.9.2 lists, and no
  container, swarm service, Slurm job or per-turn credential directory except as Section 9.9.1
  permits.

## 11. References

### 11.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[DESKTOP]** "The Humanize Protocol: Desktop Application", [`desktop.md`](desktop.md).
- **[PYTHON]** "The Humanize Protocol: Python Interfaces", [`python.md`](python.md).
