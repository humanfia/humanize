# Containers

A container gives an agent a toolchain and a filesystem that are not yours, without giving up
your workspace: you name an image, and humanize holds **this project directory at the path it
already has** inside it. Reach for it when the agent needs a toolchain you have not got.

**A flow cannot ask for one.** The flow API's environments are a directory on this machine and a
directory on a host reached with ssh, and nothing in between: a flow says *where* its work
happens by the [environments](/reference/flows#where-each-agent-works) it declares, and a
container is not one of them. What there is instead is below — a whole run inside a container,
a container reached as a host, and a container of an agent's own for agents you build in
Python.

## The whole run in one container

The simplest: run humanize itself in the image, with the project mounted where it already is.
Every environment of the run is then the container's, every command a flow runs is the
container's command, and every agent's turns land there.

```sh
docker run --rm -it -v "$PWD:$PWD" -w "$PWD" my-image-with-hmz \
    hmz exec -f ralph_loop -a agent=claude/claude-opus-5:max -b cost=20 "get the suite green"
```

The image then needs humanize and the CLIs the agents run, and their credentials — which is
the cost of this way round: the agent processes are in the container too.

## A container reached as a host

A container that runs an ssh server is a host like any other, and an environment of a flow can
be pointed at it with `-e`:

```sh
hmz exec -f tested -a builder=claude/claude-opus-5:max -a tester=codex/gpt-5.6-sol:high \
    -e suite=ssh@test-box/work/myproject -b cost=20 "get the suite green"
```

where the flow declares the environment its tester's sessions are spawned in — the
[weaver's](/weaver/writing-a-flow) part:

```python
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, LocalEnv, ShellEnvMixin


class Suite(Env, ShellEnvMixin): ...


class Agents(AgentCollection):
    builder: Agent
    tester: Agent


class Envs(EnvCollection):
    workspace: LocalEnv   # this directory, which the builder works in
    suite: Suite          # wherever -e says, which the tester works in
```

The agent **process** stays on this machine, keeping its credentials and its link to its model
provider; what happens on the host is the project it reads and the commands it runs. A flow's
own `await envs["suite"].exec(["python", "-m", "pytest", "-q"])` runs there too. See
[Remote execution](/user/remote-execution).

## A container of an agent's own, from Python

**For anyone building agents by hand**, outside a flow. An agent's config takes a machine, and
one of the machines is a container of an image you name:

```python
from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.machines import DockerConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-5",
    effort="high",
    machine=DockerConfig(image="node:22", workspace="/home/me/code/myproject"),
)
builder = ClaudeCodeAgent(config, name="builder")
builder("upgrade the toolchain")
```

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | Needs a `python3` for the target half, plus whatever the agent will reach for. |
| `workspace` | this directory | The directory **itself**, mounted — not a copy — so the work outlives the container. |

An image with no Python the target half can use is refused where the machine is set up, rather
than a turn later; where the image keeps one does not matter, since it is looked for off the
`PATH` as well as on it. An agent told to run `pytest` in an image without it spends a turn
discovering that, so a good image is one you already build for CI.

### What the container is

- runs as **your uid and gid**, so files it writes are yours;
- has `HOME=/tmp`, away from the workspace, so what a command caches is not the project's;
- is reached as a `docker://` [target](/user/remote-execution), and needs no port and no
  secret;
- is labelled `humanize=<your uid>`.

### When it comes up, and when it goes

- **On the agent's first turn**, not when the agent is constructed. Configuring an agent pulls
  no image.
- **Shared by every session that agent opens**, so its sessions find the workspace as the last
  turn left it.
- **One machine per agent.** Two agents built from the same config get one container each.
- **Taken down when the agent is collected**, or at exit for one held to the end.
- **The workspace is left behind** either way.

Cleaning up after a script that was killed outright:

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

The label carries your uid, so this cannot reach past you on a machine several people share.

### The agent is still here

This is the same arrangement as [remote execution](/user/remote-execution), with the far end a
container instead of a host. The agent **process** stays on this machine, keeping its
credentials and its link to its model provider, so the container needs no network access and no
login. Everything the agent *does* happens in the container.

The work therefore happens in a **mirror** rather than in this directory, and the backend logs
the agent's turns under a path this project has never heard of. The agent wrote down the ids of
the sessions it opened — `builder.opened` — and that is what a trace of them is gathered by:
[`Hmz().epics.trace(sessions=…)`](/user/tracing).

## Isolation here is about environment, not permission

A container does **not** stop the agent editing the workspace mounted into it. Narrowing what
the agent may do at all is [permissions](/user/permissions) — a different thing the flow says,
on the role, and the two compose. Read [Security](/user/security).

## Requirements

For a container of an agent's own: `docker` on your `PATH` and a daemon to reach, plus what
remote execution needs — Linux on x86-64 or aarch64 here, and a `python3` in the image. For a
container reached as a host: an ssh server in it that `ssh` here can reach.

## See also

- [Remote execution](/user/remote-execution)
- [Machines reference](/reference/machines)
- [Permissions](/user/permissions)
- [Security](/user/security)
