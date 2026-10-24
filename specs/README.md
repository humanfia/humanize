# hmz specifications

## 1. Scope

This document governs the specifications of hmz as a whole: what a specification is, where each
one is kept, the form every one of them takes, the meaning of the requirement keywords, how
clauses are numbered and cited, and the terms every specification uses with one meaning. It also
indexes every specification file.

Out of scope:

- Every requirement on hmz itself, which the files indexed in §6 state.
- The user documentation under `docs/`, which no clause of any specification depends on.

## 2. Definitions

**2.1** A **specification** is one Markdown file under `specs/` other than this one.

**2.2** A **clause** is one numbered paragraph of a specification that states exactly one
obligation, permission, prohibition or definition.

**2.3** An **externally observable** fact is one a user, a flow author or another program can
perceive without reading the source of hmz: a public Python name and its signature, a command,
a flag or another command-line token, an HTTP method and path, a file path or file format, an
environment variable, an exit status, a stream's content, a message the user sees, or a process
hmz starts and its arguments.

**2.4** An **implementation detail** is any fact about hmz that is not externally observable:
a private name, an internal module or class, an algorithm, a data structure, a thread, a lock or
an internal call order.

**2.5** An **informative block** is a block of a specification that begins with the marker
`> Informative:` and states no requirement.

## 3. The specifications

### 3.1 Purpose

**3.1.1** The specifications MUST state every externally observable behaviour of hmz.

**3.1.2** The specifications MUST NOT constrain any implementation detail.

**3.1.3** Where code and a specification disagree, the specification MUST be taken as the
intended behaviour and the code as defective.

### 3.2 Directories

**3.2.1** Every specification MUST be kept in exactly one of the directories `specs/api/` and
`specs/features/`.

**3.2.2** `specs/api/` MUST hold the interfaces of hmz: the flow API, the software development
kit, the daemon's protocol, the HTTP interface, the command line, the settings file, and every
file or directory hmz creates or reads on disk during or after an epic, under `specs/api/files/`.

**3.2.3** `specs/features/` MUST hold one specification per feature of hmz, each stating the
definition of the feature and every normative requirement on its behaviour.

**3.2.4** A requirement that concerns both an interface and a feature MUST be stated once, in
the specification of the feature, and the specification of the interface MUST cite it.

### 3.3 Form of a specification

**3.3.1** A specification MUST begin with one level-one heading, `# <Title>`.

**3.3.2** The second heading of a specification MUST be `## 1. Scope`, under which the
specification MUST state in one paragraph what it governs, followed by a list headed
`Out of scope:` in which each entry cites the specification that governs it.

**3.3.3** The third heading of a specification MUST be `## 2. Definitions`, under which every
term the specification defines MUST be written in bold in exactly one clause.

**3.3.4** A specification MUST use every term it defines, and every term of §5, with exactly the
defined meaning.

**3.3.5** A specification MUST NOT redefine a term of §5; it MUST cite it instead.

**3.3.6** Every heading after `## 2. Definitions` MUST be a requirement section numbered `## N.`
with N from 3, or a subsection of one numbered `### N.M`.

**3.3.7** A specification MUST NOT use a heading deeper than `###`.

**3.3.8** Every requirement section MUST consist either of subsections only or of clauses and
informative blocks only, and every subsection MUST consist of clauses and informative blocks only.

**3.3.9** A public Python interface MUST be given as signatures in a fenced `python` block,
followed by the clauses that govern it.

**3.3.10** A grammar MUST be given in ABNF (RFC 5234 and RFC 7405) in a fenced `abnf` block, or
in an equally exact notation that the specification defines before its first use.

**3.3.11** Every line of a specification MUST be at most 100 columns wide, but for a line of a
fenced block that cannot be broken without changing its meaning.

**3.3.12** A specification MUST be written in English.

### 3.4 Wording of a clause

**3.4.1** A clause MUST state exactly one obligation, permission, prohibition or definition.

**3.4.2** A clause MUST name its subject explicitly: hmz, a command, a file, a flow, a frontend
or another defined term.

**3.4.3** A clause MUST NOT contain a rationale, a history, or an example.

**3.4.4** An example MAY follow a clause in an informative block.

**3.4.5** A specification MUST NOT name an implementation detail.

**3.4.6** Normative text MUST NOT express obligation, permission or likelihood with any word
other than the keywords of §4.1, and MUST NOT use a Latin abbreviation.

**3.4.7** A specification MUST NOT call an epic a run.

**3.4.8** A specification MUST reproduce every quoted identifier, string and message exactly as
hmz emits or accepts it, even where it contains the word run.

**3.4.9** The underscore-prefixed class attributes that `api/flows.md` lists (`_permission`,
`_skills`, `_tools`, `_clis`, `_cpu_count`, `_memory`, `_gpu_count`, `_gpu_memory` and `_image`)
MUST be read as public names of the flow API.

## 4. Keywords, numbering and citation

### 4.1 Keywords

**4.1.1** The keywords MUST, MUST NOT and MAY MUST be read as described in RFC 2119 and RFC 8174,
and only when they appear in upper case.

**4.1.2** MUST states an absolute requirement on the clause's subject.

**4.1.3** MUST NOT states an absolute prohibition on the clause's subject.

**4.1.4** MAY states a permission: the clause's subject is free to do the thing or not, and every
other party MUST accept either.

**4.1.5** A specification MUST NOT use the keywords SHOULD, SHOULD NOT, SHALL, SHALL NOT,
REQUIRED, RECOMMENDED, NOT RECOMMENDED or OPTIONAL.

### 4.2 Numbering

**4.2.1** A clause of `## 2. Definitions` MUST be numbered `2.K`, K counting from 1.

**4.2.2** A clause directly under a requirement section `## N.` MUST be numbered `N.K`, K counting
from 1 within the section.

**4.2.3** A clause of a subsection `### N.M` MUST be numbered `N.M.K`, K counting from 1 within
the subsection.

**4.2.4** A clause number MUST be written in bold at the start of its paragraph, as `**N.K**` or
`**N.M.K**`, followed by one space and the clause's text.

**4.2.5** Section, subsection and clause numbers MUST be consecutive within their parent, without
gaps.

### 4.3 Citation

**4.3.1** A citation of another specification MUST give its path relative to `specs/` and, where
it cites a part of it, a section sign and the number, as `api/flows.md §3.1` or
`api/cli.md §7.5.2`.

**4.3.2** A citation within one specification MUST give the section sign and the number alone,
as `§3.4`.

**4.3.3** A citation of a part of a specification MUST name a subsection or a clause that exists.

## 5. Glossary

### 5.1 Parties and places

**5.1.1** **hmz** is the software this repository builds, and the program of the same name that
it installs.

**5.1.2** A **user** is the person who operates hmz through a frontend or the software
development kit.

**5.1.3** A **machine** is one running operating-system instance, on which processes run and
which has its own file systems and its own temporary directory.

**5.1.4** **This machine** is the machine on which the hmz process being described runs.

**5.1.5** The **home** is the directory named by the environment variable `HUMANIZE_HOME` where
that variable is set and non-empty, and the directory `.hmz` in the user's home directory
otherwise.

**5.1.6** A **workspace** is a directory of a machine in which epics are run, identified by its
absolute path with every symbolic link resolved.

**5.1.7** A distribution of the Windows Subsystem for Linux (WSL) is a machine apart
from the Windows that runs it.

**5.1.8** For the desktop application on Windows, which runs hmz in WSL, this machine is
the WSL distribution in which it runs hmz, and not the Windows that runs the application.

### 5.2 Flows and epics

**5.2.1** A **flow** is a Python function, declared through the flow API (`api/flows.md`), that
directs agents and envs to carry out a task.

**5.2.2** A **flow author** is a person who writes a flow.

**5.2.3** A **flowverse** is a named collection of flows from which hmz resolves a flow's name.

**5.2.4** An **epic** is one execution of one flow, from its start to its end, together with the
record hmz keeps of it.

**5.2.5** A **role** is a named place that a flow declares and that an agent or an env fills for
one epic.

**5.2.6** A **turn** is one message given to a session together with everything the harness does
until it answers that message.

**5.2.7** A **side question**, also called **btw**, is a question about an epic that the user
asks a separate agent, outside every session of the epic.

### 5.3 Agents and where they run

**5.3.1** A **harness** is a coding-agent command-line program that hmz drives to take an
agent's turns.

**5.3.2** An **agent** is one harness, run as one account or as the harness machine's own login,
on one model at one effort, that fills one agent role of an epic.

**5.3.3** A **session** is one conversation between an agent and its harness, which keeps its
history from one turn to the next.

**5.3.4** A **provider**, also called an **account**, is a named set of credentials and settings
for one harness, kept by hmz, under which that harness's turns run.

**5.3.5** The **harness machine** of a session is the machine on which its harness process runs.

**5.3.6** An **env** is the place where an agent's commands act and its files are read and
written: one directory of one machine, filling one env role of an epic.

**5.3.7** The **env machine** of a session is the machine of the env in which its commands act.

**5.3.8** The **placement** of a session is two settings: its **env location**, which is
**local** where the env machine is this machine and **standalone** otherwise; and its **harness
location**, which is **local** where the harness machine is this machine, **env** where the
harness is the program installed on a standalone env machine and runs there without a mirror,
and **standalone** where the harness machine is the machine of a runtime other than this machine,
the env machine included, and the harness works in a mirror there.

**5.3.9** A **mirror** is a directory on a harness machine that reproduces an env's workspace,
filled on demand, in which a harness works whose location is standalone, or local with the env
standalone.

**5.3.10** A **runtime** is a named description, written in the settings file, of an ssh host, a
docker daemon, a docker swarm, the Apple containers of a Mac, or a Slurm cluster on which envs
are put.

### 5.4 Processes and frontends

**5.4.1** The **daemon** is the hmz process of one user on one machine that holds that machine's
epics apart from every frontend.

**5.4.2** A **frontend** is a way for a user to start, watch and steer epics: the command line,
the terminal interface (TUI), the web interface, or the desktop application for macOS or for
Windows.

**5.4.3** The **settings file** is the file `settings.yaml` in the home (`api/settings.md`).

## 6. Index

### 6.1 Interfaces

**6.1.1** [`api/cli.md`](api/cli.md) MUST specify every `hmz` command, its options and grammars,
its output and its exit statuses.

**6.1.2** [`api/settings.md`](api/settings.md) MUST specify every key of the settings file and
every environment variable hmz reads.

**6.1.3** [`api/flows.md`](api/flows.md) MUST specify the public Python API a flow is written
against, `hmz.flows`.

**6.1.4** [`api/sdk.md`](api/sdk.md) MUST specify the public Python API through which another
program drives hmz, `hmz.sdk`.

**6.1.5** [`api/daemon.md`](api/daemon.md) MUST specify the protocol between the daemon and a
frontend.

**6.1.6** [`api/http.md`](api/http.md) MUST specify every HTTP path the web interface serves.

**6.1.7** [`api/files/home.md`](api/files/home.md) MUST specify the layout of the home.

**6.1.8** [`api/files/workspace.md`](api/files/workspace.md) MUST specify what hmz keeps inside a
workspace.

**6.1.9** [`api/files/epics.md`](api/files/epics.md) MUST specify the record of an epic on disk.

**6.1.10** [`api/files/machine.md`](api/files/machine.md) MUST specify what hmz keeps in this
machine's own directory and caches.

**6.1.11** [`api/files/harness-homes.md`](api/files/harness-homes.md) MUST specify what hmz reads
and writes in, or builds in place of, a harness's own configuration directories.

**6.1.12** [`api/files/desktop.md`](api/files/desktop.md) MUST specify the files of the desktop
application.

**6.1.13** [`api/files/targets.md`](api/files/targets.md) MUST specify what hmz places on an env
machine or a harness machine other than this machine.

### 6.2 Features

**6.2.1** [`features/agents.md`](features/agents.md) MUST specify agents, harnesses, sessions and
turns.

**6.2.2** [`features/accounts.md`](features/accounts.md) MUST specify providers and accounts.

**6.2.3** [`features/placements.md`](features/placements.md) MUST specify placements, mirrors and
where a harness runs.

**6.2.4** [`features/environments.md`](features/environments.md) MUST specify envs and runtimes.

**6.2.5** [`features/epics.md`](features/epics.md) MUST specify epics: starting, stopping,
resuming, and budgets.

**6.2.6** [`features/monitoring.md`](features/monitoring.md) MUST specify tracing, profiling and
notifications.

**6.2.7** [`features/backups.md`](features/backups.md) MUST specify backing epics up to git
repositories and downloading them.

**6.2.8** [`features/telemetry.md`](features/telemetry.md) MUST specify error reports.

**6.2.9** [`features/updates.md`](features/updates.md) MUST specify how hmz learns of and moves
to a newer release.

**6.2.10** [`features/chat.md`](features/chat.md) MUST specify the chat flow and chats.

**6.2.11** [`features/btw.md`](features/btw.md) MUST specify side questions.

**6.2.12** [`features/tui.md`](features/tui.md) MUST specify the terminal interface.

**6.2.13** [`features/web.md`](features/web.md) MUST specify the web interface.

**6.2.14** [`features/desktop.md`](features/desktop.md) MUST specify the desktop application.

**6.2.15** [`features/daemons.md`](features/daemons.md) MUST specify the daemon and the daemons
of other machines a frontend reaches.
