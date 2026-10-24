<script setup>
import ContainerEnv from '../.vitepress/theme/components/user-containers/ContainerEnv.vue'
</script>

# Containers

Give a flow's work a container when the agents need a toolchain, an operating system or a set
of GPUs you do not have in your own shell. Use this page to put one of a flow's environments in
a container of its own, on docker here or on a daemon elsewhere, with a share of that machine's
CPUs, memory and GPUs, and to choose whether the agent's CLI runs here or in the container. On
a Mac, [Apple's `container`](#apple-containers) does the same without docker. Two other ways,
the whole run inside a container and a container reached as an ssh host, are at the end, with
a docker swarm that picks the node for you.

<div class="ct-ways">
  <div class="ct-way">
    <p class="ct-name">A container per environment</p>
    <p class="ct-type"><code>hmz exec … -e ROLE=docker[@RUNTIME]/…</code></p>
    <dl>
      <dt>agents run</dt><dd>in the container, with the image's CLI, or here, with your sign-in (<a href="#where-the-agent-s-cli-runs">harness</a>)</dd>
      <dt>commands run</dt><dd>in the container</dd>
      <dt>the image needs</dt><dd>Python 3.12 or newer</dd>
      <dt>works with</dt><dd>a flow with a role for another machine</dd>
    </dl>
  </div>
  <div class="ct-way">
    <p class="ct-name">The whole run in a container</p>
    <p class="ct-type"><code>docker run … hmz exec …</code></p>
    <dl>
      <dt>agents run</dt><dd>in the container</dd>
      <dt>commands run</dt><dd>in the container</dd>
      <dt>the image needs</dt><dd>Humanize, the agents' CLIs, and their sign-in</dd>
      <dt>works with</dt><dd>any flow</dd>
    </dl>
  </div>
  <div class="ct-way">
    <p class="ct-name">A container as an ssh host</p>
    <p class="ct-type"><code>hmz exec … -e ROLE=ssh@[HOST]/…</code></p>
    <dl>
      <dt>agents run</dt><dd>here, with your sign-in</dd>
      <dt>commands run</dt><dd>in the container</dd>
      <dt>the image needs</dt><dd>an ssh server, Python 3.12 or newer, and the project</dd>
      <dt>works with</dt><dd>a flow with a role for another machine</dd>
    </dl>
  </div>
</div>

## Try it {#try-it-a-container-per-environment}

With docker running here and a flow that has a role for a container, such as
[`boxed`](#the-flow-used-on-this-page), save docker's default daemon under a name with the
agent's CLI here, in `~/.hmz/settings.yaml` (or at `/settings runtimes`, as
[below](#example-a-daemon-saved-under-a-name)), since `python:3.12-slim` has no CLI of its own:

```yaml
runtimes:
  docker:
    here:
      endpoint: local
      harness: local
```

Then name it and a directory:

```sh
hmz exec -f boxed -a coder=claude/claude-haiku-4-5-20251001:low \
    -e box=docker@here/home/me/myproject \
    -p budget.duration=10m "Print this machine's hostname and OS, then fix add() in calc.py."
```

The agent's commands run in a fresh container, and its edits land in your directory:

```text
● coder is working
● Bash(hostname && uname -a)
● Read(…/envs/mirrors/humanize-here-box-67f7d9f2/731d95dbbabe/calc.py)
● **Hostname:** 14a684eac2e0
  …
● Edit(…/envs/mirrors/humanize-here-box-67f7d9f2/731d95dbbabe/calc.py)
● Fixed—the `add()` function now returns `a + b` instead of `a - b`.
✻ Worked for 12s · coder
```

## Before you start

- **Humanize and one coding agent here**, installed and signed in: see
  [Installation](/user/installation).
- **Linux and `docker` here.** The daemon can be this machine's or one reached over a socket,
  TCP, ssh or a docker context; `docker info` must work against it.
- **An image with Python 3.12 or newer** and `/bin/sh`. It needs no ssh server, no coding agent
  and no sign-in. With nothing said, `python:3.12-slim` is used.
- **The directory on the daemon's host.** It is mounted into the container at the path it has,
  so it has to exist there. For docker's default here, `local`, that is this machine.
- **A flow with a role for another machine.** The flows Humanize ships and the official
  flowverse lists all work in the directory you start in. This page uses
  [`boxed`](#the-flow-used-on-this-page), a one-role flow you can save into your project.

## How a container per environment works

A flow's environment role put on docker, with `-e role=docker/workdir` or
`-e role=docker@provider/workdir`, gets a container of its own for the run:

- **The image** is the one the flow declares for the role, else the saved daemon's `image`,
  else `python:3.12-slim`. `boxed` declares `python:3.12-slim`.
- **The directory is mounted at the path it has**, so the work outlives the container, and a
  path in an error is one you can open on the daemon's host.
- **The container gets exactly what the role declares** of CPUs, memory and GPUs, out of what
  the daemon was saved to hand out. A daemon with less left than the role asks for refuses the
  run before any agent starts.
- **It goes when the run ends.** Every container Humanize starts is labelled with your uid.
- **The agent's CLI runs here with the daemon's harness `local`**, supervised, working in a
  copy of the directory kept under `~/.hmz/envs/mirrors/`. Every command it runs lands in the container through
  `docker exec`. That is why the tool lines above name a `…/envs/mirrors/…` path while the edit
  lands in `/home/me/myproject`. Because the copy is kept there rather than at the directory's
  own path, the directory may be your own checkout.

<ContainerEnv />

`docker/…`, naming no daemon, is docker's default here with nothing saved, and so has the
harness `env`: the CLI must be in the image. For the CLI here, a daemon elsewhere, a different
image, or a cap on what a run may take, save the daemon under a name first.

## Example: a daemon saved under a name

Say this machine has 64 CPUs and two GPUs, and a flow's container should get no more than four
of those CPUs and 8 GB. Save the daemon with that allowance, then name it.

**1. Save it.** `/settings runtimes` opens the [Runtimes
page](/user/settings#runtimes). Choose **Add a runtime…**, then `docker host`. Type the name,
`local` on `harness runs on`, `4` on `cpus` and `8G` on `memory`, then <kbd>tab</kbd> to the buttons and <kbd>→</kbd> to
**Done**:

```text
  hmz › /settings › Runtimes › Add a docker host             ● unsaved changes
  A docker daemon where flow environments run in containers: on this machine,
  over ssh, or at an address. Flows running on it are limited to the resources
  configured here.

  ╭──────────────────────────────────────────────────────────────────────────╮
  │ endpoint                                                         local ▾ │  ①
  │   the default docker daemon on this machine                              │
  │──────────────────────────────────────────────────────────────────────────│
  │ name                                                              gpubox │  ②
  │   name used in -e and /flow                                              │
  │──────────────────────────────────────────────────────────────────────────│
  │ harness runs on                                                    local │
  │   where an agent's harness runs, and nowhere else: env (the CLI on this  │
  │   runtime's machine), local (here), or ssh:<name>, docker:<name>,        │
  │   swarm:<name>, apple-container:<name>, slurm:<name>; blank for env      │
  │──────────────────────────────────────────────────────────────────────────│
  │ image                                                                  — │  ③
  │   default image, unless specified by the flow                            │
  │──────────────────────────────────────────────────────────────────────────│
  │ OCI runtime                                                            — │
  │   e.g. nvidia; blank for daemon default                                  │
  │──────────────────────────────────────────────────────────────────────────│
  │ run args                                                               — │
  │   extra arguments for docker run                                         │
  │──────────────────────────────────────────────────────────────────────────│
  │ max containers                                                         — │
  │   max concurrent containers; blank for no limit                          │
  │──────────────────────────────────────────────────────────────────────────│
  │ workdir                                                                — │
  │   default working directory when -e specifies no directory               │
  │──────────────────────────────────────────────────────────────────────────│
  │ falls back to                                                          — │
  │   runtimes to try in order if this one cannot: docker:box, ssh:gpu2      │
  │──────────────────────────────────────────────────────────────────────────│
  │ cpus                                                                   4 │  ④
  │   max CPUs; blank to use all host CPUs                                   │
  │──────────────────────────────────────────────────────────────────────────│
  │ memory                                                                8G │
  │   e.g. 64G; blank to use all host memory                                 │
  │──────────────────────────────────────────────────────────────────────────│
  │ gpus                                                                   — │
  │   GPU IDs, e.g. 0, 1; blank to use all host GPUs                         │
  ╰──────────────────────────────────────────────────────────────────────────╯
   adds docker/gpubox and detects host resources

  Detect                                                                  Done

  enter done   ←/→ move   tab list   esc back
```

**Done** saves it and asks the daemon at once:

```text
  ╭──────────────────────────────────────────────────────────────────────────╮
  │ docker                                                                   │
  │ gpubox                    local · 4 CPUs, 8G                             │
  ╰──────────────────────────────────────────────────────────────────────────╯
   docker/gpubox answers: docker 29.4.3; 64 CPUs, 2015G, GPUs 0, 1; OCI runtimes  ⑤
   nvidia, io.containerd.runc.v2, runc
```

**2. Name it in the environment role:**

```sh
hmz exec -f boxed -a coder=claude/claude-haiku-4-5-20251001:low \
    -e box=docker@gpubox/home/me/myproject \
    -p budget.duration=10m "Install pytest, then make test_calc.py pass."
```

```text
● coder is working
● Bash(ls -la)
● Bash(pip install pytest)                                                             ⑥
● Bash(pip install --break-system-packages pytest)
…
● Bash(python3 -m pip install pytest --target ./venv_local)
● Bash(export PYTHONPATH=./venv_local:$PYTHONPATH && python3 -m pytest test_calc.py -v)
● Perfect! ✓ Both tasks are complete:
  1. **pytest installed** — successfully installed to `./venv_local`
  2. **test_calc.py passes** — fixed the bug in `calc.py` (changed `return a - b` to `return a + b`)
✻ input 122 · output 2.5k · cache_read 357.9k · cache_write 14.5k · $0.07 · claude-haiku-4-5-20251001 · coder
✻ Worked for 51s · coder
```

### What each part means

1. **`endpoint`** is which daemon: `local` for this machine's, or a socket, a TCP address, a
   saved ssh host, an ssh address or a docker context. The rows under it then ask for whatever
   that choice needs; `local` needs none.
2. **`name`** is what `-e` names: `docker@gpubox/…`. `harness runs on`, set to `local`, keeps
   the agent's CLI here, as the image has none: see [Where the agent's CLI
   runs](#where-the-agent-s-cli-runs).
3. **`image`**, left blank, leaves the choice to the flow, then `python:3.12-slim`.
4. **`cpus` and `memory`** cap what this daemon may hand out to Humanize's containers, across
   every run on it at once. **Detect**, beside **Done**, asks the daemon and writes in
   everything it has, to type over: the line under the list says `detecting resources on
   local…`, then what it found, and the cursor lands on `cpus`.
5. **`answers`** is the check: the daemon's version, what it has, and its runtimes. What it was
   saved to hand out and has not got is said in yellow.
6. **`pip install pytest` failed** in the container, and the agent installed into the project
   instead. Under the default [permission](/user/permissions) an agent may write its workdir
   and nothing else of the machine, the container included: bake tools into the image rather
   than asking the agent to install them system-wide.

A role that asks for more than the daemon has left is refused in a second, before any agent
starts:

```console
$ hmz exec -f boxed8 … -e box=docker@gpubox/home/me/myproject …
hmz exec: error: docker@gpubox has 4 of 4 CPUs free, and 'box' asks for 8
```

### Check that it worked

- **The work is in the directory.** `cat /home/me/myproject/calc.py` shows the fix, and files
  the agent made in the container, such as `venv_local/`, are there too.
- **It ran in the container.** A command's own output says so: in the run above, `hostname`
  printed the container's id, `14a684eac2e0`, not this machine's name.
- **The container is gone.** `docker ps --filter label=humanize=$(id -u)` lists nothing once
  the run has ended.

## Where the agent's CLI runs

A saved docker daemon's harness, its `harness runs on` row at `/settings runtimes`, says where
the CLI of each agent working in one of its containers runs: one place, and the run is refused
where that cannot hold it. The full story is on
[Remote execution](/user/remote-execution#where-the-agent-runs). For a container:

| `harness` | The agent's CLI runs | For a container |
| --- | --- | --- |
| `env` *(blank, the default)* | in the container | the image needs the CLI; `python:3.12-slim` has none, so the run is refused |
| `local` | here | the container needs no CLI and no sign-in |
| `docker:<name>` | in a second container of its own, on the daemon saved as `<name>` | that container needs the CLI |

`docker/…`, with nothing saved, has `env`.

**`local`** runs every role's CLI here, and the run says so: the transcript line
`coder's harness runs here`. Use it for an image with no coding agent, or to keep the agent's
account off an image you did not build.

**`env`** runs the CLI the image has, in the container. It needs the CLI on the image's `PATH`,
and a sign-in there: an agent with an `@account` has the account's variables and credential
files sent in for each turn, and one without runs as the image's CLI is signed in, which a
fresh image is not. Its sessions are kept in the container, and go with it. A role with a hook
that decides whether each tool runs is refused: that needs `local`.

::: warning Never copy your own sign-in into an image or a container
A ChatGPT login of Codex and a subscription login of Claude Code renew themselves, and each
renewal cancels the copy it replaced: a container signed in with a copy of your
`~/.codex/auth.json` or `~/.claude/.credentials.json` signs this machine out the first time it
renews. Give the role an `@account` signed in with a key, sign the CLI in inside the container,
or set the daemon's harness to `local`. An `@account` that is itself such a login goes in
only while no other turn is using it, and comes back renewed: see
[Providers › A sign-in that refreshes itself](/reference/providers#a-sign-in-that-refreshes-itself).
:::

On an image without the CLI, `env` refuses the run before the flow starts, with exit status 2:

```text
hmz exec: error: docker@gpubox: claude's harness cannot run where its harness setting (env) says: claude is not installed on docker@gpubox: npm i -g @anthropic-ai/claude-code there, or set the harness of the runtime it is on to local
```

**`docker:<name>`** starts one more container just for the CLI, on that saved daemon, from its
image (else `python:3.12-slim`), holding its saved workdir, or an empty
`$TMPDIR/humanize-<uid>/harness` for a daemon on this machine saved without one. That container is given `--cap-add SYS_PTRACE`,
which the CLI's supervisor needs there to hand each command's output back to it. It counts
against that daemon's `max containers`: a daemon at its limit refuses the run, and nothing
else is tried. It is only for a role granted everything, and the image must have the CLI:

```text
hmz exec: error: docker@gpubox: claude's harness cannot run where its harness setting (docker:spare) says: coder=claude/claude-haiku-4-5-20251001:low: ClaudeCodeAgent: a fence cannot hold a harness that runs on another machine
… hmz: claude: not found on PATH
```

The first is a role at the default grant, refused before the flow starts with exit status 2;
the second, a role granted everything on an image with no `claude`, which fails its first
turn.

## Apple containers on a Mac {#apple-containers}

On a Mac with [Apple's `container`](https://github.com/apple/container) (macOS 26 on Apple
silicon), `-e ROLE=apple-container/…` gives a role a container of its own without docker.
Each container is a small Linux virtual machine; everything else is as for
[a container per environment](#how-a-container-per-environment-works): the image, the directory
mounted at its own path, the container started for the run and deleted after it.

**1. Start it, and pull the image once:**

```sh
container system start
container image pull python:3.12-slim
```

**2. Name it in the environment role.** `apple-container`, naming no runtime, is this Mac's
containers with nothing saved:

```sh
hmz exec -f boxed -a coder=claude/claude-haiku-4-5-20251001:low \
    -e box=apple-container/Users/me/myproject \
    -p budget.duration=10m "Print this machine's OS, then fix add() in calc.py."
```

While it runs, `container list` shows the role's container, `humanize-local-box-…`; it is gone
once the run ends.

**The agent's CLI has to run in the container.** Running it here, supervised, needs Linux, and
a Mac is not, so only the default [harness](#where-the-agent-s-cli-runs), `env`, works, with an
image that has the CLI. Save the runtime with an image with the CLI and its sign-in (see the
warning above), leaving `harness runs on` blank. A flow's own commands in the role, such as
`await envs["box"].exec(["uname", "-s"])`, need neither.

**To cap what runs may take, or change the image,** save it: `/settings runtimes`, **Add a
runtime…**, then `apple containers`. The form is a docker host's, less the daemon: a name
(`local` unless taken), `harness runs on`, `image`, `run args` for `container run`,
`max containers`, `workdir`, `falls back to`, `cpus` and `memory`; **Detect** fills in this Mac's.
Name it in `-e` as `apple-container@<name>/…`.

How it differs from docker:

- **No GPUs.** A role asking for one is refused before any agent starts.
- **Whole CPUs.** A role's CPUs and memory are its virtual machine's size; a role asking for
  neither gets `container`'s default, 4 CPUs and 1 GiB, which counts against what a saved
  runtime may hand out like any other container's.
- **This Mac only.** There is no daemon elsewhere to name; the directory is one of this Mac's,
  and a path holding a comma cannot be mounted.

## Variations

### The whole run in one container

Mount the project at the path it already has, and run `hmz exec` in an image that has Humanize
and the agents' CLIs:

```sh
docker run --rm -it -v "$PWD:$PWD" -w "$PWD" my-image-with-hmz \
    hmz exec -f ralph_loop -a agent=claude/claude-opus-5:max \
    -p budget.cost=20 "get the suite green"
```

Every agent and every command runs in the container, and any flow works this way. The project
is your own directory, mounted rather than copied, so the work is still there when the
container goes. The price is that the CLIs run in there too, so the image has to have them
installed and signed in.

### A container reached as an ssh host

A container running an ssh server is a host like any other. Name it in your ssh config, check
that `ssh test-box` works, and give it to a flow's environment role:

::: code-group

```text [~/.ssh/config]
Host test-box
    HostName localhost
    Port 2222
    User me
```

```sh{3} [hmz exec]
hmz exec -f onbox \
    -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:high \
    -e box=ssh@[test-box]/home/me/box/myproject \
    -p budget.cost=20 "get the suite green"
```

:::

The container needs an ssh server, Python and the project, and no CLI or sign-in.
[Remote execution](/user/remote-execution) walks through this road, `onbox` included, and its
pitfalls all apply here.

### A daemon on another machine

On the Add a docker host form, set `endpoint` to `saved ssh host` and choose the host on the
`on` row under it: the daemon there is reached with everything that host was saved with. The
workdir is then a directory of *that* host, and has to exist there.

### A docker swarm {#a-docker-swarm}

Where the machines are a docker swarm, let it choose the node: `-e ROLE=swarm[@RUNTIME]/…` gives
the role a service of one task on the swarm, which its scheduler puts on whichever node has room
for what the role declares. The task reserves that much of its node and is limited to it, and
everything else is as for a container here: the directory is mounted at its own path, the CLI
runs here by default, and the service is removed when the run ends.

```sh
hmz exec -f boxed -a coder=claude/claude-haiku-4-5-20251001:low \
    -e box=swarm/shared/myproject \
    -p budget.duration=10m "Print this machine's hostname and OS, then fix add() in calc.py."
```

`swarm/…`, naming no swarm, is the one this machine manages (`docker info` says
`Swarm: active` and `Is Manager: true`). For one managed elsewhere, a cap on what its tasks may
take, GPUs, or constraints on where they land, choose **Add a runtime…**, then `docker swarm`,
on the [Runtimes page](/user/settings#runtimes) and set its manager the way a daemon's is set:
a saved ssh host, `ssh://`, `tcp://` or a context.

- **The directory has to be on whichever node the task lands on**, at the same path: a shared
  filesystem every node mounts, or constraints (`node.labels.shared==true`,
  `node.hostname==gpu-1`) keeping the tasks where it is. A node without it refuses the task,
  and the run says so.
- **The image has to be one every node can pull.**
- **A task on the manager is reached through the manager; one on any other node over ssh to
  that node**, at the address the swarm knows it by. Where that is not how you reach it, say
  how under the runtime's nodes: a node's host name, then a saved ssh host or
  `user@host:port`. That ssh has to work without a password, and the node's `docker` has to
  answer you.
- **GPUs** are reserved as the generic resource your nodes advertise them as (`NVIDIA-GPU`):
  set it as the runtime's GPU resource. With none set, a role asking for a GPU is refused.
- **A task no node has room for is refused**, with the scheduler's own words, and its service
  removed: at once where no node could ever hold it, after 30 seconds of waiting otherwise.
- **On a swarm others use too**, give the runtime a `name_prefix` (`team-a`), in its entry of
  `settings.yaml` or under **Runtimes** on the [web page](/user/web#settings): its services
  are then named `team-a-<role>-<8 hex>` rather than `humanize-<runtime>-<role>-<8 hex>`, to
  keep a naming rule the swarm has and to tell yours from others' by name. A docker host takes
  one too, for its containers. Correcting the runtime on its form here keeps what it is set to.

### A container that is already running {#a-running-container}

Where a container is already running and stays up between runs, and you or another tool manage
it, a run can work in it instead of starting one of its own. Save a docker runtime whose
`container` names it, in your settings file or on the web page's runtime form:

```yaml
runtimes:
  docker:
    build-box:
      endpoint: local
      container: build-box
      exec_user: "1000:1000"
      exec_env: [TMPDIR=/scratch/u1000]
      exec_wrapper: [/usr/local/bin/limit, --nproc, "256"]
```

```sh
hmz exec -f boxed -a coder=claude/claude-haiku-4-5-20251001:low \
    -e box=docker@build-box/srv/myproject \
    -p budget.duration=10m "fix add() in calc.py"
```

- **Nothing is started, counted or stopped.** The container has to be running when the run
  starts, and is left running when it ends; only the run's own mirrors here are removed.
- **The workdir is a path in the container**, as the container sees it.
- **`exec_user`, `exec_env` and `exec_wrapper`** say who every command in it runs as, with what
  variables, and under what program, which has to run the command it is given after its own
  words. They work for a container of its own too.
- **The runtime says nothing else about a container**: an image, run arguments, a name prefix,
  or CPUs, memory and GPUs to hand out are refused beside `container`. What the environment has
  is what the container says it has.
- **A harness put in it** (a harness setting of `docker:build-box`) needs the container to have been
  started with `--cap-add SYS_PTRACE`; Humanize cannot add it to a running container.

See [Machines › A running container](/reference/machines#a-running-container).

### Another daemon when this one is full

A daemon at its `max containers`, or without the CPUs, memory or GPUs a role asks left free,
cannot hold that role, and the run is refused. Fill in `falls back to` on its form with other
saved runtimes, in the order to try them (`docker:spare, ssh:gpu2`), and the environment moves to
the first of them that can hold it instead, in that runtime's own workdir where it has one:

```text
hmz exec: docker:gpubox cannot hold 'box': docker@gpubox runs 2 of the 2 containers it may; using docker:spare
```

A docker swarm falls back the same way, when no node has room for the task or it is at its
`max tasks` (`swarm:cluster` names one in a list). Only the runtime `-e` named falls back: `docker:spare`'s own list is not walked, and
`-e box=docker@spare/…` walks nothing unless `spare` has a list of its own. The epic keeps the
`-e` as you gave it, and records under `used` where the role actually went. See
[Machines › Falling back](/reference/machines#falling-back).

### A container of an agent's own

Code that builds agents by hand, outside a flow, can give one agent a container of an image you
name, brought up on its first turn and taken down with it. That is Python below the flow API:
see the [Machines reference](/reference/machines).

## Pitfalls

::: warning A container is not a permission boundary
An agent can still rewrite whatever is mounted into its container, your project included.
Narrowing what an agent may do is [permissions](/user/permissions), and the agent's commands
are held to its role's permission inside the container too, by the container's own Landlock.
Read [Security](/user/security).
:::

| You see | What to do |
| --- | --- |
| `… has 4 of 4 CPUs free, and 'box' asks for 8` | The daemon, as saved, cannot give the role what it declares. Raise the daemon's allowance, or use another. |
| `could not start a container of python:3.12: …` | Docker's own words follow: no daemon to reach, an image not pulled, or no shell in the image. |
| `no directory to give the container on …` | The directory is not on the daemon's host. Make it there. |
| `could not install Humanize on docker://…: … is not running` | The image has no Python 3.12 or newer; its last words say where it looked. |
| a tool the agent tries to install fails with a permission error | The role may write its workdir only. Put the tool in the image. |
| `… claude's harness cannot run where its harness setting (env) says: claude is not installed on docker@…` | `env` (the default, and `docker/…` with nothing saved) on an image without the CLI. Save the daemon with its harness `local`, or use an image with the CLI. |
| containers left behind after a run was killed | `docker rm -f $(docker ps -q --filter label=humanize=$(id -u))` removes yours and nobody else's. |
| `swarm@…: no node of the swarm has …` or `no node took it within 30s` | No node has room for what the role reserves, or none answers the runtime's constraints. Free a node, loosen the constraints, or ask for less. |
| `swarm@…: no directory to give the task on the node it landed on` | The node has no such directory. Share it to every node, or constrain the runtime to the nodes that have it. |
| `swarm@… is in no active swarm` or `is a worker of its swarm` | The endpoint is not a swarm manager. Point it at one. |
| services left behind after a run was killed | `docker service rm $(docker service ls -q --filter label=humanize=$(id -u))` on the manager. |
| `apple-container[@…]: Apple's container was not found on this machine` | Install Apple's `container`, which needs macOS 26 on Apple silicon. |
| `could not connect to apple-container[@…]: … apiserver is not running` | Run `container system start`. |
| `apple-container[@…] has no GPU to hand out` | Apple's containers get no GPU. Use docker or an ssh host for that role. |
| an Apple container's agent fails its first turn here | The CLI cannot be supervised on a Mac. Set the runtime's harness to `env` (or leave it blank), with an image that has the CLI. |

More are in [Troubleshooting](/user/troubleshooting).

## The flow used on this page

::: details `boxed`: one agent at work in a container of its own
Save it as `.hmz/flows/boxed/__init__.py` in your project, and it is offered as
`@local/boxed`. What each line means is the [Weaver Guide's](/weaver/writing-a-flow) to explain.

```python
"""One agent at work in a container of its own."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    ImageEnvMixin,
    ShellEnvMixin,
    flow,
)


class Box(Env, ShellEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"  # the container this role gets


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    box: Box  # wherever -e says


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def boxed(task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    coder = agents["coder"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=envs["box"])
```

`boxed8`, in the refusal above, is the same flow with `CPUEnvMixin` and `_cpu_count = 8` on
`Box`: a role that asks for eight CPUs.
:::

## Next steps

- [Remote execution](/user/remote-execution): the same `-e`, over ssh, and the harness setting in full
- [Permissions](/user/permissions): what a role may touch, in a container as here
- [Machines › Docker environments](/reference/machines#docker-environments): every field of a
  saved daemon, and how a container is started
- [Machines › Swarm environments](/reference/machines#swarm-environments): every field of a
  saved swarm, and how a task is placed and reached
- [Machines › Apple container environments](/reference/machines#apple-container-environments):
  every field of saved Apple containers, and how one is started
- [Remote execution › The harness setting](/reference/remote-execution#harness-setting)
- [Security](/user/security)

<style scoped>
.ct-ways {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 22px 0 8px;
}

.ct-way {
  padding: 14px 16px 10px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
}

.ct-way p {
  margin: 0;
}

.ct-name {
  font-weight: 650;
  color: var(--vp-c-text-1);
}

.ct-type {
  margin-top: 6px !important;
  overflow-wrap: anywhere;
}

.ct-way dl {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 4px 12px;
  margin: 12px 0 4px;
  font-size: 14px;
  line-height: 1.5;
}

.ct-way dt {
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--vp-c-text-3);
  padding-top: 1px;
}

.ct-way dd {
  margin: 0;
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .ct-ways {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
