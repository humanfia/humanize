# Workspace Files

## 1. Scope

This document specifies every file, directory and `git` object that **hmz** creates or leaves in
a **workspace** and in the `git` repository holding it, and states what **hmz** never places
there. It covers the directory `<workspace>/.hmz/`, the files **hmz** writes when a **flow** asks
it to modify an **env**, and the `git` references and objects **hmz** adds.

Out of scope:

- The definitions and rules common to `api/files/`: `api/files/home.md` §2 and §3.
- The changes the **agents** of a **flow** make to a **workspace** as their work.
- The directories **hmz** derives from a **workspace** outside it, including worktrees and
  temporary copies: `api/files/targets.md` §4.
- The copy of a **workspace** on another **machine**: `api/files/targets.md`.

## 2. Definitions

**2.1** **`<workspace>`**: the absolute path of a **workspace**.

**2.2** **Workspace directory**: the directory `<workspace>/.hmz/`.

**2.3** **Repository**: the `git` repository whose working tree contains `<workspace>`, where
there is one.

## 3. The workspace directory

**3.1** `hmz` MUST NOT create the workspace directory before it first writes a file under it.

**3.2** Where `<workspace>/.hmz/` does not exist and `<workspace>/.humanize/` is a directory,
`hmz` MUST rename `<workspace>/.humanize/` to `<workspace>/.hmz/` the first time a process looks
for the workspace directory, unless `<workspace>/.humanize/` is `~/.humanize/` or the directory
`HUMANIZE_HOME` names.

**3.3** Where both `<workspace>/.hmz/` and `<workspace>/.humanize/` exist, `hmz` MUST use
`<workspace>/.hmz/`, and MUST NOT read, modify, merge or remove `<workspace>/.humanize/`.

**3.4** `<workspace>/.hmz/flows/` holds the flows of the flowverse `local`, each as
`<flow>/__init__.py` with the files beside it, or as `<flow>.py`.

**3.5** `hmz` MUST write into `<workspace>/.hmz/flows/` only where the **user** asks **hmz** to
copy a flow into the **workspace**, by writing the copy into
`<workspace>/.hmz/flows/.<flow>.<random>/` and renaming it to `<workspace>/.hmz/flows/<flow>/`.

**3.6** `hmz` MUST NOT remove the workspace directory or any entry in it.

**3.7** `hmz` MUST NOT create in the workspace directory any entry other than those of clauses
3.4 and 3.5.

**3.8** `hmz` MUST NOT add the workspace directory to `.gitignore`, to `.git/info/exclude`, or to
any other file of the **workspace** or the **repository**.

**3.9** The **user** MAY delete the workspace directory at any time; the flows of the flowverse
`local` it held then no longer exist.

## 4. What hmz never places in a workspace

**4.1** `hmz` MUST NOT place in a **workspace** any skill, agent, command, hook, tool server
configuration, model declaration or instruction file for a **harness**, including any entry
under `.claude/`, `.agents/`, `.cursor/`, `.codex/`, `.gemini/`, `.qwen/` or `.grok/`, and any
`AGENTS.md`, `CLAUDE.md` or `.mcp.json`.

**4.2** `hmz` MUST NOT place in a **workspace** any record of an **epic**, any **session**, any
trace and any exported archive, unless the **user** names a path in the **workspace** as the
destination.

**4.3** `hmz` MUST NOT write into a **workspace** any file other than those this document
specifies, except the files the **agents** of a **flow** write and the files a **flow** writes
through its **env**.

## 5. Files written through an env

**5.1** Where a **flow** writes a file through an **env** whose **env machine** is **this
machine**, `hmz` MUST write it into `.<12 hexadecimal digits>.hmz-tmp` in the directory of the
file and rename that file over it.

**5.2** Where a **flow** writes a file through an **env** whose **env machine** is not **this
machine**, `hmz` MUST write it as `api/files/targets.md` §3.4 states.

**5.3** A file of clause 5.1 left after a killed process is the residue of that process; the
**user** MAY delete it at any time.

## 6. The repository

**6.1** Where a **flow** takes a snapshot of an **env** whose working directory is in a
**repository**, `hmz` MUST create the reference `refs/hmz/snapshots/<name>` in that
**repository**, pointing at a commit whose author and committer are
`humanize <humanize@localhost>`.

**6.2** The default `<name>` of a snapshot MUST be the moment of the snapshot in UTC formatted
`YYYYMMDDTHHMMSS.ffffffZ`, followed by `-` and four random lowercase hexadecimal digits.

**6.3** A snapshot MUST NOT include `.hmz/` or `.humanize/` at the top of the working tree.

**6.4** While it takes a snapshot, `hmz` MUST use a temporary index file
`<index>.hmz-snapshot.<pid>` beside the index of the **repository**, and MUST remove it and its
lock file when the snapshot ends.

**6.5** `hmz` MUST NOT remove a reference of clause 6.1; the **user** MAY delete it at any time.

**6.6** Where a **flow** rewinds an **env** to a snapshot or commit, `hmz` MUST move what is
checked out in that worktree, the branch or a detached `HEAD`, to the commit recorded by the
snapshot, with the reflog message `hmz: rewind to <ref>`, and MUST discard any merge,
cherry-pick or revert in progress.

**6.7** Where a **flow** rewinds an **env**, `hmz` MUST NOT modify or remove `.hmz/` or
`.humanize/` at the top of the working tree.

**6.8** Where a **flow** adds a `git` worktree of a **repository**, `git` records the worktree in
the administrative directory of that **repository**; `hmz` MUST NOT remove that record.

**6.9** `hmz` MUST NOT create or modify any branch, tag, remote or configuration entry of a
**repository**, except as clauses 6.1, 6.6 and 6.8 state.
