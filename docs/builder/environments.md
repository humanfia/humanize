---
title: Environment roles
description: Declare where a flow's agents work, run commands and read or write files there from the flow, and know what is checked before a run starts.
---

# Environment roles

An environment is a working directory on a machine. A flow declares one role for each directory it needs, and uses mixins to declare what the flow itself will do there.

![Each environment role is declared with mixins, filled by Humanize or by whoever runs the flow, and handed to the flow with only the methods its mixins grant](/diagrams/builder-environments-1.svg)

## Declare the roles

Subclass `EnvCollection` with one key per role. Type each role as `Env` or `LocalEnv`, and add mixins for the methods the flow calls on it.

```python
# .hmz/flows/tested/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    BashEnvMixin,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Workspace(LocalEnv, BashEnvMixin):
    """The folder the run started in. The flow runs commands in it."""


class Reports(Env, FilesEnvMixin):
    """Where the test report is kept. The flow writes files in it."""


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: Workspace  # filled by Humanize
    reports: Reports  # filled by whoever runs the flow


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def tested(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task in the package; the flow runs the tests and files the report."""
    coder, workspace, reports = agents["coder"], envs["workspace"], envs["reports"]
    package = await workspace.derive_subdir(subdir="shop")
    session = await coder.spawn()
    await coder.run(task, session=session, env=package)
    code, out, err = await workspace.exec(["python3", "-m", "pytest", "-q"], timeout=600)
    await reports.write("tests/latest.txt", (out + err).encode())
    return "tests pass" if code == 0 else "tests fail"
```

| Role type | Who fills it |
| --- | --- |
| `LocalEnv` | Humanize, with the workspace the run started in. You cannot set it with `-e`. |
| `Env` | The user running the flow. It can be on this machine, an ssh host, a container or a Slurm job. |
| `NotRequired[...]` | The user running the flow, or nobody. Read it with `envs.get("role")`, which returns `None` when omitted. |

Pass `env=` to a turn to set where the agent works. Mixins apply only to methods the flow calls directly. An agent does not need mixins to work in an environment.

## Properties on every environment

Every environment provides these properties and methods without a mixin.

| Name | What it is |
| --- | --- |
| `env.role` | The role name, such as `"workspace"`. |
| `env.backend` | An `EnvBackendKind`: `local`, `ssh`, `docker`, `swarm`, `apple-container` or `slurm`. |
| `env.provider` | The ssh host or saved runtime name. `""` on this machine. |
| `env.workdir` | The working directory for commands and relative paths, as a `PurePosixPath`. |
| `env.available` | Whether the machine was reachable and the workdir existed when last checked. |
| `await env.derive_subdir(subdir=...)` | Returns a new environment on the same machine, in a subdirectory of this one. |

## Work in a subdirectory

Call `derive_subdir` to get an environment rooted in a subdirectory of the parent. Humanize creates the directory if it is missing. The new environment keeps its parent's role and mixins.

```python
package = await workspace.derive_subdir(subdir="shop")
await coder.run(task, session=session, env=package)
```

`subdir` must be a relative path inside the workdir. An absolute path, or one that climbs out of the workdir with `..`, raises `ValueError`. A directory that cannot be created raises `EnvError`.

## Run a command

Add `ShellEnvMixin` to get `exec`. It runs a program in the workdir, waits for it to finish, and returns its exit status, stdout and stderr.

```python
code, out, err = await workspace.exec(["python3", "-m", "pytest", "-q"], timeout=600)
```

Pass the program and its arguments as a list to run without a shell. `timeout` is in seconds; `0` (the default) means no limit. If a command exceeds its timeout, Humanize kills it and raises `EnvCommandTimeout`. A command that cannot start raises `EnvError`. A non-zero exit status does not raise an error; check `code` instead.

Add `BashEnvMixin` (which includes `ShellEnvMixin`) to pass a shell string to `exec`, which runs as `bash -c`:

```python
code, out, err = await workspace.exec("python3 -m pytest -q 2>&1 | tail -1")
```

Passing a string to a role that only declares `ShellEnvMixin` raises `CapabilityNotGranted`.

## Read and write files

Add `FilesEnvMixin` to get `read` and `write`. Paths can be relative to the workdir or absolute.

```python
await reports.write("tests/latest.txt", (out + err).encode())
data = await reports.read("tests/latest.txt")
```

`read` returns the file's bytes. `write` replaces the file and creates any missing parent directories. A missing file raises `EnvFileNotFound`. Insufficient permissions raise `EnvPermissionDenied`.

## Other mixins

| Mixin | What it adds | Page |
| --- | --- | --- |
| `GitWorktreeEnvMixin` | `derive_worktree`: another worktree of the repository. | [Worktrees, clones and scratch](/builder/worktrees) |
| `TemporaryClonedDirEnvMixin` | A throwaway copy of the workdir. | [Worktrees, clones and scratch](/builder/worktrees) |
| `ScratchDirEnvMixin` | An empty directory beside the workdir. | [Worktrees, clones and scratch](/builder/worktrees) |
| `GitEnvMixin` | Snapshots, and rewinding to one. | [Worktrees, clones and scratch](/builder/worktrees) |
| `CPUEnvMixin`, `MemoryEnvMixin`, `GPUEnvMixin`, `ImageEnvMixin` | Hardware and image requirements for the machine. | [Machines and moving sessions](/builder/machines) |

## Fill roles when running a flow

The person running the flow sets the location for each `Env` role. `LocalEnv` roles are set automatically. For the user guide, see [Environments](/user/environments).

### In the app

On the **New epic** page, find **Environment** and set the **Backend** and **Directory** for each `Env` role. A backend other than this machine also has a **Runtime** to pick.

![The Environment section of the New epic page for the tested flow: the folder shop, then a row for the reports role with Backend set to This machine and Directory ~/reports](/shots/builder-environments-form.svg)

While the epic runs, open the **Epic** panel and click **Open its 3 environments** under **Environments** (the number is how many the epic holds). The Environments view lists each environment by role. Directories created with `derive_subdir` appear nested under their parent environment.

![Humanize Desktop on the Environments view of a running epic: reports, workspace, and under workspace the derived workspace#subdir(shop), selected, with the package's files in the explorer](/shots/builder-environments-view.svg)

*`workspace#subdir(shop)` is the directory the flow derived from `workspace`.*

### In the terminal

In `hmz`, run `/flow tested`. The configuration sheet shows one row per agent role and per `Env` role; open **reports** to set its location.

![The terminal's sheet for the tested flow: a coder row with its agent, and a reports row marked environment and not set](/shots/builder-environments-terminal.svg)

### From the command line

Pass `-e ROLE=BACKEND[@PROVIDER][/WORKDIR]` to `hmz exec` for each `Env` role. If you omit a required role, the run fails before starting.

```sh
hmz exec -f tested -a coder=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 "Add a discount code to checkout"
```

![hmz exec refuses the run: tested needs an environment for 'reports'; specify each with -e ROLE=BACKEND[@PROVIDER]/WORKDIR](/shots/builder-environments-refused.svg)

Provide the `reports` directory to run the flow:

```sh
hmz exec -f tested -a coder=claude/claude-haiku-4-5 -e reports=local/~/reports \
    -p budget.output_tokens=20000 "Add a discount code to checkout"
```

![hmz exec runs the flow with -e reports=local/~/reports: the agent edits checkout.py and answers](/shots/builder-environments-exec.svg)

The flow runs the tests in the workspace and writes the output to `reports`:

![cat of ~/reports/tests/latest.txt prints 1 passed](/shots/builder-environments-report.svg)

### From Python

Pass the same role strings to `Hmz().run(...)`: `envs={"reports": "local/~/reports"}`. See [The Python SDK](/builder/sdk). In tests, pass a `FakeEnvDriver` per role to `run_fake` in `envs=`, and the one for a `LocalEnv` role as `local=`. See [Test a flow](/builder/testing).

## Pre-run checks

Humanize connects to every environment and verifies it before calling the flow function. The first failed check stops the run.

1. Every required `Env` role is filled, and no `LocalEnv` role is set by the user.
2. Each machine is reachable and its workdir exists. Otherwise, Humanize raises `EnvConnectionError` or `EnvUnavailable`.
3. Each machine supports every mixin its role declares. `BashEnvMixin` requires `bash` on the machine's PATH. `GitEnvMixin` and `GitWorktreeEnvMixin` require `git`. The other mixins on this page are always supported; hardware mixins are checked against the machine too, see [Machines and moving sessions](/builder/machines).

If a machine lacks support for a mixin, the run fails with `CapabilityMissing`. Here is the same command on a machine without `bash`:

![hmz exec refuses the run: 'workspace' needs BashEnvMixin, which the workspace's directory on this machine does not support: BashEnvMixin needs bash on the machine's PATH, and it has none](/shots/builder-environments-missing.svg)

## Good to know

- A flow can only call methods from mixins the role declares. Calling a method from an undeclared mixin raises `CapabilityNotGranted`, even if the machine supports it.
- Humanize never deletes directories created by `derive_subdir`.
- `exec` runs commands with an empty stdin and decodes output as UTF-8.
- Each command runs in its own process group. A timeout, a cancelled flow or the environment closing kills the whole group.
- `EnvCommandTimeout` includes `stdout` and `stderr` with the output written before the command was killed.
- Every environment error subclasses `EnvError`. See [Context, errors and cleanup](/builder/context).
- A turn without `env=` runs in the epic's workspace.
