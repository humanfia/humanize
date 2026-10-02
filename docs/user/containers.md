# Containers

Give a flow's work a container when the agents need a toolchain, an operating system or a set
of GPUs you do not have in your own shell. Use this page to put one of a flow's environments in
a container of its own, on docker here or on a daemon elsewhere, with a share of that machine's
CPUs, memory and GPUs, and to choose whether the agent's CLI runs here or in the container. Two
other ways, the whole run inside a container and a container reached as an ssh host, are at the
end.

<div class="ct-ways">
  <div class="ct-way">
    <p class="ct-name">A container per environment</p>
    <p class="ct-type"><code>hmz exec … -e ROLE=docker@RUNTIME/…</code></p>
    <dl>
      <dt>agents run</dt><dd>here, with your sign-in, unless the image has their CLI (<a href="#where-the-agent-s-cli-runs"><code>-H</code></a>)</dd>
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
      <dt>the image needs</dt><dd>humanize, the agents' CLIs, and their sign-in</dd>
      <dt>works with</dt><dd>any flow</dd>
    </dl>
  </div>
  <div class="ct-way">
    <p class="ct-name">A container as an ssh host</p>
    <p class="ct-type"><code>hmz exec … -e ROLE=ssh@HOST/…</code></p>
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
[`boxed`](#the-flow-used-on-this-page), name docker's default daemon and a directory:

```sh
hmz exec -f boxed -a coder=claude/claude-haiku-4-5-20251001:low \
    -e box=docker@local/home/me/myproject \
    -b duration=10m "Print this machine's hostname and OS, then fix add() in calc.py."
```

The agent's commands run in a fresh container, and its edits land in your directory:

```text
● coder is working
● Bash(hostname && uname -a)
● Read(…/envs/mirrors/humanize-local-box-67f7d9f2/731d95dbbabe/calc.py)
● **Hostname:** 14a684eac2e0
  …
● Edit(…/envs/mirrors/humanize-local-box-67f7d9f2/731d95dbbabe/calc.py)
● Fixed—the `add()` function now returns `a + b` instead of `a - b`.
✻ Worked for 12s · coder
```

## Before you start

- **humanize and one coding agent here**, installed and signed in: see
  [Installation](/user/installation).
- **Linux and `docker` here.** The daemon can be this machine's or one reached over a socket,
  TCP, ssh or a docker context; `docker info` must work against it.
- **An image with Python 3.12 or newer** and `/bin/sh`. It needs no ssh server, no coding agent
  and no sign-in. With nothing said, `python:3.12-slim` is used.
- **The directory on the daemon's host.** It is mounted into the container at the path it has,
  so it has to exist there. For `docker@local` that is this machine.
- **A flow with a role for another machine.** The flows humanize and the official flowverse
  ship all work in the directory you start in. This page uses
  [`boxed`](#the-flow-used-on-this-page), a one-role flow you can save into your project.

## How a container per environment works

A flow's environment role put on docker, with `-e role=docker@provider/workdir`, gets a
container of its own for the run:

- **The image** is the one the flow declares for the role, else the saved daemon's `image`,
  else `python:3.12-slim`. `boxed` declares `python:3.12-slim`.
- **The directory is mounted at the path it has**, so the work outlives the container, and a
  path in an error is one you can open on the daemon's host.
- **The container gets exactly what the role declares** of CPUs, memory and GPUs, out of what
  the daemon was saved to hand out. A daemon with less left than the role asks for refuses the
  run before any agent starts.
- **It goes when the run ends.** Every container humanize starts is labelled with your uid.
- **The agent's CLI runs here by default**, supervised, working in a copy of the directory kept
  under `~/.humanize/envs/mirrors/`. Every command it runs lands in the container through
  `docker exec`. That is why the tool lines above name a `…/envs/mirrors/…` path while the edit
  lands in `/home/me/myproject`. Because the copy is kept there rather than at the directory's
  own path, the directory may be your own checkout.

`docker@local/…` is docker's default here with nothing saved. For a daemon elsewhere, a
different image, or a cap on what a run may take, save the daemon under a name first.

## Example: a daemon saved under a name

Say this machine has 64 CPUs and two GPUs, and a flow's container should get no more than four
of those CPUs and 8 GB. Save the daemon with that allowance, then name it.

**1. Save it.** `/settings runtimes` opens the [Runtimes
page](/user/settings#runtimes). Choose **Add a docker host**:

```text
   Add a docker host
   A docker daemon where flow environments run in containers: on this machine, over ssh, or at an
   address. Flows running on it are limited to the resources configured here.
      1. endpoint        local ▾    the default docker daemon on this machine          ①
      2. name            gpubox     name used in -e and /flow                          ②
      3. image                      default image, unless specified by the flow        ③
      4. OCI runtime                e.g. nvidia; blank for daemon default
      5. run args                   extra arguments for docker run
      6. max containers             max concurrent containers; blank for no limit
      7. workdir                    default working directory when -e specifies no directory
      8. cpus            4          max CPUs; blank to use all host CPUs               ④
   ❯  9. memory          8G         e.g. 64G; blank to use all host memory
     10. gpus                       GPU IDs, e.g. 0, 1; blank to use all host GPUs
         detect                    detect host resources and fill them in
         done                      adds docker/gpubox and detects host resources
```

`done` saves it and asks the daemon at once:

```text
 docker
 gpubox                    local · 4 CPUs, 8G
 docker/gpubox answers: docker 29.4.3; 64 CPUs, 2015G, GPUs 0, 1; OCI runtimes      ⑤
 nvidia, io.containerd.runc.v2, runc
```

**2. Name it in the environment role:**

```sh
hmz exec -f boxed -a coder=claude/claude-haiku-4-5-20251001:low \
    -e box=docker@gpubox/home/me/myproject \
    -b duration=10m "Install pytest, then make test_calc.py pass."
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
   saved ssh host, an ssh address or a docker context. The row below it asks for whatever that
   choice needs.
2. **`name`** is what `-e` names: `docker@gpubox/…`.
3. **`image`**, left blank, leaves the choice to the flow, then `python:3.12-slim`.
4. **`cpus` and `memory`** cap what this daemon may hand out to humanize's containers, across
   every run on it at once. `detect` fills in everything the daemon has, to type over.
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

`-H`, or the `harness` row of `/flow`, says where each agent's CLI runs; the full story is on
[Remote execution](/user/remote-execution#where-the-agent-runs). For a container:

| `-H` | The agent's CLI runs | For a container |
| --- | --- | --- |
| `adaptive` *(default)* | in the container where the image has the CLI, and here otherwise | `python:3.12-slim` has none, so here |
| `local` | here, always | the container needs no CLI and no sign-in |
| `env` | in the container, always | refused where the image has no CLI |
| `standalone:docker@local` | in a second container of its own | that container needs the CLI |

**`adaptive`** looks once per role and machine. With an image that has no coding agent, every
role's CLI runs here, and the run says so: the transcript line
`coder's harness runs here (local)`, and `adaptive → local (last run)` on the flow's `harness`
row. Nothing to do.

**`local`** is the same as what `adaptive` came to above, said outright. Use it to keep the
agent's account off an image you did not build.

**`env`** runs the CLI the image has, in the container. It needs the CLI on the image's `PATH`,
and a sign-in there: an agent with an `@account` has the account's variables and credential
files sent in for each turn, and one without runs as the image's CLI is signed in, which a
fresh image is not. Its sessions are kept in the container, and go with it.

::: warning Never copy your own sign-in into an image or a container
A ChatGPT login of Codex and a subscription login of Claude Code renew themselves, and each
renewal cancels the copy it replaced: a container signed in with a copy of your
`~/.codex/auth.json` or `~/.claude/.credentials.json` signs this machine out the first time it
renews. Give the role an `@account` signed in with a key, sign the CLI in inside the container,
or run the role with `-H local`. An `@account` that is itself such a login goes in only while no
other turn is using it, and comes back renewed: see
[Providers › A sign-in that refreshes itself](/reference/providers#a-sign-in-that-refreshes-itself).
:::

On an image without the CLI, the run is refused before the flow starts, with exit status 2:

```text
hmz exec: error: claude is not installed on docker@local: npm i -g @anthropic-ai/claude-code there, or run its harness here with -H local
```

**`standalone:docker@local`** starts one more container just for the CLI, from the saved
daemon's image (else `python:3.12-slim`), holding `~/.humanize/harness`; a daemon other than
`local` needs the directory
said, as `standalone:docker@gpubox/srv/scratch`. That container is given `--cap-add
SYS_PTRACE`, which the CLI's supervisor needs there to hand each command's output back to it. It is only for a role granted everything, and
the image must have the CLI:

```text
hmz exec: error: coder=claude/claude-haiku-4-5-20251001:low: ClaudeCodeAgent: a fence cannot hold a harness that runs on another machine
… hmz: claude: not found on PATH
```

The first is a role at the default grant, refused before the flow starts with exit status 2;
the second, a role granted everything on an image with no `claude`, which fails its first
turn.

## Variations

### The whole run in one container

Mount the project at the path it already has, and run `hmz exec` in an image that has humanize
and the agents' CLIs:

```sh
docker run --rm -it -v "$PWD:$PWD" -w "$PWD" my-image-with-hmz \
    hmz exec -f ralph_loop -a agent=claude/claude-opus-5:max \
    -b cost=20 "get the suite green"
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
    -e box=ssh@test-box/home/me/box/myproject \
    -b cost=20 "get the suite green"
```

:::

The container needs an ssh server, Python and the project, and no CLI or sign-in.
[Remote execution](/user/remote-execution) walks through this road, `onbox` included, and its
pitfalls all apply here.

### A daemon on another machine

On the Add a docker host form, set `endpoint` to `saved ssh host` and choose the host: the
daemon there is reached with everything that host was saved with. The workdir is then a
directory of *that* host, and has to exist there.

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
| `could not install humanize on docker://…: … is not running` | The image has no Python 3.12 or newer; its last words say where it looked. |
| a tool the agent tries to install fails with a permission error | The role may write its workdir only. Put the tool in the image. |
| `claude is not installed on docker@…` | `-H env` on an image without the CLI. Use `-H local` or the default. |
| containers left behind after a run was killed | `docker rm -f $(docker ps -q --filter label=humanize=$(id -u))` removes yours and nobody else's. |

More are in [Troubleshooting](/user/troubleshooting).

## The flow used on this page

::: details `boxed`: one agent at work in a container of its own
Save it as `.humanize/flows/boxed/__init__.py` in your project, and it is offered as
`local/boxed`. What each line means is the [Weaver Guide's](/weaver/writing-a-flow) to explain.

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
    session = await coder.spawn(env=envs["box"])
    await coder.run(task, session=session)
```

`boxed8`, in the refusal above, is the same flow with `CPUEnvMixin` and `_cpu_count = 8` on
`Box`: a role that asks for eight CPUs.
:::

## Next steps

- [Remote execution](/user/remote-execution): the same `-e`, over ssh, and `-H` in full
- [Permissions](/user/permissions): what a role may touch, in a container as here
- [Machines › Docker environments](/reference/machines#docker-environments): every field of a
  saved daemon, and how a container is started
- [CLI › Choosing where the harness runs](/reference/cli#choosing-where-the-harness-runs)
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
