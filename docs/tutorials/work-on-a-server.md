---
title: Run the work on a server or in a container
description: Save a server and a Docker daemon as runtimes, start a chat and an epic whose agent works there, and open its files, changes and terminal from your own machine.
---

# Run the work on a server or in a container

Keep Humanize on your machine and run the agent's work on an SSH server or in a Docker container. By the end of this tutorial, you will have a chat working on a remote server with its files, changes and a shell open beside it.

![A chat in Humanize Desktop with a terminal pane open beside it; the shell prompt is on gpu-box, in ~/shop](/shots/tutorials-work-on-a-server-terminal.svg)

*The chat is on your machine. The shell beside it is on the server.*

## What you need

- Humanize on your machine with one coding agent signed in. See [Finish your first task in Humanize Desktop](/tutorials/first-task-desktop).
- A Linux or macOS server that `ssh` reaches without asking for a password. This tutorial uses `gpu-box`, a `Host` in `~/.ssh/config`. Test it: `ssh -o BatchMode=yes gpu-box true` must print nothing and exit 0.
- Your project on the server at `~/shop`.
- The same coding agent CLI installed and signed in on the server. Step 4 covers the alternative.
- Docker running on your machine for step 5.

You do not install Humanize on the server. Humanize copies a small binary there on the first connection.

## 1. Import the server

A runtime is a machine saved under a name.

1. Open **Settings**, then **Runtimes**.
2. Scroll to **SSH config**, click **Read SSH config**, tick `gpu-box`, and click **Import**.
3. Click **Check** on the new row. A tick and a CPU count confirm that Humanize can reach the server.

![Settings, Runtimes: Read SSH config lists the hosts, gpu-box is ticked and imported, and Check answers with a tick and 18 cpu](/shots/tutorials-work-on-a-server-import.svg)

In the terminal interface, open `/settings runtimes` and use **Import ~/.ssh/config** and **Add a runtime…** at the bottom.

![The terminal interface's Runtimes page, listing gpu-box under ssh and sandbox under docker](/shots/tutorials-work-on-a-server-tui.svg)

## 2. Start a chat on the server

1. Click **New chat**.
2. Click the environment chip (**This computer**) under the message box and pick `gpu-box` under **Runtimes**.
3. Type `~/shop` when asked for the server directory and click **Use this directory**. The chip now shows `gpu-box · shop`.
4. Type a task and press <kbd>enter</kbd>.

![A new chat: the environment chip opens, gpu-box is picked, ~/shop is typed as the directory, the task is sent, and the agent answers](/shots/tutorials-work-on-a-server-chat.svg)

The agent reads, edits and runs tests in `~/shop` on `gpu-box`. Your local folder does not change.

To start the same chat from the command line, run:

```sh
hmz chat -e 'ssh@gpu-box/~/shop' -a claude/claude-haiku-4-5 'Add a discount code to checkout'
```

## 3. Look at the files, changes and terminal

Use the buttons at the top right of the chat to open panes on the chat's environment. Each pane header shows `ssh · gpu-box ~/shop`.

Click **Files** to browse and edit the server's files.

![The Files pane beside the chat: the explorer lists the project on gpu-box and checkout.py is open in the editor](/shots/tutorials-work-on-a-server-files.svg)

Click **Changes** to view the agent's diff and commit on the server.

![The Changes pane beside the chat: the diff of checkout.py on gpu-box](/shots/tutorials-work-on-a-server-changes.svg)

Click **Terminal** to open a shell in the project directory on the server, as shown at the top of this page.

In the terminal interface, type `/env` in the chat to open the same **Files**, **Changes** and **Shell** pages.

## 4. Choose where the harness runs

The harness is the coding agent's CLI. By default, it runs on the server next to the project, which requires the CLI to be installed there.

To keep the CLI on your machine, open **Settings**, **Runtimes**, click **Edit** on the runtime's row, set **Harness runs on** to **This machine**, and click **Save**. The files and commands stay on the server. Your machine must run Linux to use this setting.

![Two arrangements. Inside the environment, the default: the harness runs on gpu-box beside your project. This machine: the harness runs beside Humanize, and your project stays on gpu-box](/diagrams/tutorials-work-on-a-server-1.svg)

## 5. Add a Docker container

1. In **Settings**, **Runtimes**, go to **New runtime**.
2. Set **Backend** to **Docker container** and **Name** to `sandbox`.
3. Leave **Endpoint** as `local` to use the Docker daemon on your machine.
4. Set **Image** to an image that includes your coding agent's CLI, such as `shop-dev:latest`. Leaving **Image** empty defaults to `python:3.12-slim`.
5. Click **Add**, then click **Check** on the new row.

![The New runtime form with Backend set to Docker container, Name sandbox and Image shop-dev:latest](/shots/tutorials-work-on-a-server-docker.svg)

![The Runtimes list with both rows checked: gpu-box answers 18 cpu, sandbox answers 8 cpu, 16 GiB and the Docker version](/shots/tutorials-work-on-a-server-runtimes.svg)

To use the container, start a new chat, click the environment chip, pick `sandbox`, and enter your project folder when asked for the directory. Humanize starts a container, mounts your folder at the same path, and removes the container when the environment closes. Your changes stay in the local folder.

## 6. Start an epic there

Official flows run in the folder where you start them. To run an epic on another machine, the flow must declare an environment.

1. Save this flow in your project as `.hmz/flows/on_box/__init__.py`:

```python
"""One agent does the task in an environment you choose."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Box(Env, ShellEnvMixin):
    """Another machine, and a shell on it."""


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv  # the folder the epic starts in
    box: Box  # wherever you say


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def on_box(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """One agent does the task in an environment you choose."""
    builder = agents["builder"]
    session = await builder.spawn()
    await builder.run(task, session=session, env=envs["box"])
```

2. Click **New epic** and pick `@local/on_box`.
3. On the `box` row, set **Backend** to **SSH host**, **Runtime** to `gpu-box`, and **Directory** to `~/shop`.
4. Set a budget, type the task, and send it.

![The New epic form for @local/on_box: the box row is set to SSH host, gpu-box and ~/shop](/shots/tutorials-work-on-a-server-epic.svg)

From the command line, pass `-e` to fill the `box` row:

```sh
hmz exec -f @local/on_box -a builder=claude/claude-haiku-4-5 -e 'box=ssh@gpu-box/~/shop' -p budget.output_tokens=20000 'Add a discount code to checkout'
```

![hmz exec runs the flow: the agent reads, edits and tests on gpu-box, then reports what it did](/shots/tutorials-work-on-a-server-exec.svg)

To run in the container instead, pass `-e 'box=docker@sandbox/~/shop'`.

## What you did

- Imported an SSH server as a runtime and checked the connection.
- Ran a chat in a directory on that server.
- Opened the server's files, diffs and shell beside the chat.
- Chose where the agent harness runs.
- Saved a Docker runtime and ran an epic on a runtime from the app and the CLI.

## Next

- [Runtimes: servers, containers and clusters](/user/runtimes): every runtime type and field.
- [Environments](/user/environments): pick, change and move where a chat or epic works.
- [Files, changes and terminal](/user/environment-panels): everything the three panes do.
- [Environment roles](/builder/environments): declare environments in your own flows.
