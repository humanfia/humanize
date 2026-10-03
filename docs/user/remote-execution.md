# Remote execution

Point one of a flow's environments at another machine with `-e`, and the work the flow does
there (the files an agent edits, the builds and tests it runs) happens on that machine. Use
this when the build, the data or the GPUs are on a host you reach over ssh, and your coding
agent and its sign-in are on the machine in front of you. This page takes you from
`ssh build-box` working to a flow building on it, and shows each of the places the agent's
CLI itself can run.

<div class="re-split">
  <div class="re-side">
    <span class="re-where">this machine</span>
    <ul>
      <li>the agent's CLI, installed and signed in</li>
      <li>its account and its link to the model provider</li>
      <li>its sessions, which is what a trace is read from</li>
    </ul>
  </div>
  <div class="re-link" aria-hidden="true"><span>ssh</span></div>
  <div class="re-side re-there">
    <span class="re-where">build-box</span>
    <ul>
      <li>the project the agent reads and writes, at the host's own paths</li>
      <li>every command it runs: builds, tests, <code>git</code></li>
      <li>the network those commands reach</li>
    </ul>
  </div>
</div>

That split is what you get when the host has no CLI of the agent's own, which is the usual
case. Where it has one, the agent can run over there instead: see [Where the agent
runs](#where-the-agent-runs).

## Try it

With `ssh build-box` working and the project at `/home/me/build/myproject` on it, run a flow
that has a role for another machine, such as [`onbox`](#the-flow-used-on-this-page):

```sh
hmz exec -f onbox \
    -a builder=claude/claude-haiku-4-5-20251001:low \
    -a reviewer=claude/claude-haiku-4-5-20251001:low \
    -e box=ssh@build-box/home/me/build/myproject \
    -b duration=10m "Make test_calc.py pass."
```

The builder's tools name the host's paths, and what it changed is on the host when the run
ends:

```text
● builder is working
● Read(/home/me/build/myproject/test_calc.py)
● Read(/home/me/build/myproject/calc.py)
● Edit(/home/me/build/myproject/calc.py)
● Done! The bug was in `calc.py:2` — the `add` function was using subtraction … the test now passes.
✻ Worked for 16s · builder
● reviewer is working
```

## Before you start

- **humanize and one coding agent here**, installed and signed in: see
  [Installation](/user/installation).
- **`ssh build-box` works from here without a password prompt.** humanize uses your own ssh
  config, agent and keys, and adds nothing. `ssh -o BatchMode=yes build-box true` is the test:
  it must exit 0.
- **On the host:** Linux or macOS on any architecture, Python 3.12 or newer, and the project
  already at the path you will name. You install nothing else there: humanize brings what it
  needs.
- **This machine is Linux** on x86-64 or aarch64.
- **A flow with a role for another machine.** The flows humanize and the official flowverse
  ship all work in the directory you start in, so none of them takes an `-e`. This page uses
  [`onbox`](#the-flow-used-on-this-page), a two-role flow you can save into your project.

## How remote execution works

A flow declares **environment roles**: named places its agents work. One is always the
**workspace**, the directory you started `hmz` in, and humanize fills it. Any other is yours to
name, with `-e role=…` on the command line or on its row at `/flow`. `onbox` has one, `box`:
its builder works there, and its reviewer reads in the workspace.

What `-e` takes after the `=` is three parts, `backend@provider/workdir`:

| `-e box=` | Where the role's work happens |
| --- | --- |
| `ssh@build-box/home/me/build/myproject` | that directory on a host `ssh` reaches: a host you [saved under a name](#save-a-host-under-a-name), `host`, `user@host`, `host:port`, or an alias from your ssh config |
| `ssh@build-box/~/build/myproject` | the same, under the home directory of whoever ssh logs in as |
| `ssh@build-box` | the workdir the host saved as `build-box` was saved with |
| `docker@gpubox/home/me/myproject` | a [container of its own](/user/containers#try-it-a-container-per-environment) on the docker daemon saved as `gpubox`, holding that directory of the daemon's host |
| `docker@local/home/me/myproject` | the same, on docker's default here, with nothing saved |
| `local@/srv/project` | a directory on this machine |

Every session the flow opens in `box` works on the host: the files it reads and writes are the
host's, every command it runs runs there, and the flow's own steps on `box`, such as `onbox`'s
`git diff`, run there too.

The agent's CLI, and whatever supervises it, is its **harness**. Where the harness runs decides
whose sign-in the agent uses, where its sessions are kept, and which network its model is
reached over. Nothing on the command line says where: a host you [saved under a
name](#save-a-host-under-a-name) says it for every run on it, as its **affinity**, a list of
places tried in order.

| In an affinity | The agent's CLI runs |
| --- | --- |
| `self` | on the host itself, where the CLI is installed there and can hold the role's fence |
| `local` | here, reaching the host's files and commands |
| `ssh:<name>`, `docker:<name>` | on another saved runtime, reaching the host's work from there |

With no affinity, and on a host nobody saved, the CLI runs on the host where it is installed
there and here otherwise. Work in the workspace always has its harness here. The places are
worked through one by one [below](#where-the-agent-runs).

## Example: build on a host, review here

This is the run from [Try it](#try-it), in full. `build-box` has the project and Python, and no
coding agent CLI.

```text
hmz exec -f onbox                                               ①
    -a builder=claude/claude-haiku-4-5-20251001:low
    -a reviewer=claude/claude-haiku-4-5-20251001:low
    -e box=ssh@build-box/home/me/build/myproject                ②
    -b duration=10m                                             ③
    "Make test_calc.py pass."
```

```text
● builder is working
● Bash(find /home/me/build/myproject -type f -name "*.py" | head -20)       ④
● Read(/home/me/build/myproject/test_calc.py)
● Read(/home/me/build/myproject/calc.py)
● Edit(/home/me/build/myproject/calc.py)
● Bash(cd /home/me/build/myproject && python test_calc.py)                   ⑤
● Done! The bug was in `calc.py:2` — the `add` function was using subtraction … the test now passes.
✻ input 58 · output 1.1k · cache_read 143.4k · cache_write 8.6k · claude-haiku-4-5-20251001 · builder
✻ Worked for 16s · builder
● reviewer is working                                                          ⑥
● The original code had a bug: the `add()` function was performing subtraction (`a - b`) instead
  of addition (`a + b`). The diff correctly fixes this by changing the operator from `-` to `+`.
✻ Worked for 5s · reviewer
…
```

### What each part means

1. **`-f onbox`** names a flow with an environment role. A flow without one refuses `-e`:
   `ralph_loop has no environment role 'box'; available roles are none`.
2. **`-e box=ssh@build-box/home/me/build/myproject`** puts the `box` role on the host
   `build-box`, in that directory. `build-box` is whatever `ssh build-box` reaches, so an alias
   from your ssh config works as it is. The path is the host's, and has to exist there.
3. **`-b duration=10m`** is the budget, as for any flow. A remote run spends like any other.
4. **The builder's tools name `/home/me/build/myproject`**, the host's path. The agent sees the
   host's files at the host's own paths, so a path in a compiler error or a test failure is one
   you can open on the host.
5. **`Bash(… python test_calc.py)` ran on `build-box`**, with the host's Python and the host's
   network. Nothing the agent runs runs on this machine.
6. **The reviewer works in the workspace**, here, and reads a `git diff` the flow ran on the
   host. One flow can mix roles here and there.

Nothing said where the builder's CLI runs, and `build-box` was saved with no affinity, so with
no `claude` on `build-box` it ran here. At the prompt the transcript says so as the role's
first session opens:

```text
❯ Make test_calc.py pass.
builder's harness runs here
── builder
● builder is working
```

### Check that it worked

The change is on the host:

```console
$ ssh build-box "cd /home/me/build/myproject && git diff"
diff --git a/calc.py b/calc.py
…
-    return a - b
+    return a + b
```

- `/epics` lists the run, and [a trace](/user/tracing) of it shows the builder's sessions like
  any other, each with where its harness went.
- While a run goes, the monitor's page for `box` says the same on its `harness` row:
  `local: on this machine; what it runs lands here`. See [the monitor's environment
  page](/user/monitor#environments).
- `/home/me/build/myproject` also exists **here**: it is the copy the agent read and wrote
  through, kept at the same path. See [the path is taken here
  too](#the-path-is-taken-here-too).

## Example: set it up at the prompt

The same run, set up in `hmz` rather than on a command line, with the host saved once so that
nothing about it has to be typed again.

**1. Save the host.** `/settings runtimes` opens the [Runtimes
page](/user/settings#runtimes). Choose **Add a runtime…**, then `ssh host`, type the host, and fill in only
what your ssh config does not already say:

```text
   Add an ssh host
   A machine where flow environments run. Connects using your ssh config plus settings configured
   here. Keys are specified by path and never read.
     1. host             build-box                  hostname, IP address, or user@host:port   ①
     2. name             build-box                  name used in -e and /flow                 ②
     3. user                                        username; leave blank to use your ssh config
     4. port                                        leave blank to use your ssh config, or 22
     5. identity file                               path to private key
     6. proxy jump                                  jump host to connect through, if any
     7. options                                     additional ssh options: KEYWORD=VALUE, …
     8. workdir          /home/me/build/myproject   default working directory when -e …       ③
     9. falls back to                               runtimes to try in order if this one cannot…
  ❯ 10. harness runs on                             where an agent's harness runs, in order … ④
        done                      adds ssh/build-box, and checks its resources
```

`done` saves it and reaches it at once, as a run would:

```text
 ssh
 build-box                 build-box · working directory: /home/me/build/myproject
 ssh/build-box answers: home /root; 64 CPUs, 2015G                                  ⑤
```

**2. Put the role on it.** `/flow local/onbox` opens the flow's setup. Its environment role is
a row under its agents; <kbd>enter</kbd> on `box` opens a form of the parts `-e` takes after
`box=`. Choose `build-box` on the `host` row and leave `workdir` blank to use the one it was
saved with:

```text
   Environment for box
     1. backend  ssh ▾             a machine reached over ssh
     2. host     build-box ▸       build-box · working directory: /home/me/build/myproject
     3. workdir                    leave blank to use saved default: /home/me/build/myproject
     4. as -e    ssh@build-box     full -e spec: typing one sets the rows above
   ❯    done                      sets box to ssh@build-box when the flow is saved
```

**3. Save the flow, and type the task.**

```text
   local/onbox
   Configure each role: an agent (CLI, account, model and effort) or an environment.
     1. builder                   claude/claude-haiku-4-5-20251001:high
     2. reviewer                  claude/claude-haiku-4-5-20251001:high
     3. box                       ssh@build-box                                          ⑥
        budget                    stops at 10m
        save                      flow and roles
```

### What each part means

1. **`host`** is anything `ssh` takes: an alias, a name, an address, `user@host:port`. Typed as
   `user@host:port`, it is split into the `user` and `port` rows for you.
2. **`name`** is what `-e` and `/flow` call it from now on: `-e box=ssh@build-box`.
3. **`workdir`** is where a role put on this host works when nothing more is said, so
   `ssh@build-box` alone means `ssh@build-box/home/me/build/myproject`.
4. **`harness runs on`** is the host's affinity: where the CLI of an agent working on it runs,
   [below](#where-the-agent-runs). Blank is the default.
5. **`answers`** is the check: humanize reached the host with nobody there to type a password,
   and read its home, CPUs and memory. A host that cannot be reached says why on this line.
6. **The `box` row** holds what the form set, as `-e` spells it: `ssh@build-box`, the saved
   host and its saved workdir.

Your answers are kept with the flow's setup in this directory, like its agents. **Import
~/.ssh/config** on the same page saves every `Host` your config names in one go, each still
pointing at its `Host` so the config stays the one place it is written.

## Save a host under a name

A host that needs more than a name (a login, a port, a key, a jump host) is worth saving once,
as in [step 1 above](#example-set-it-up-at-the-prompt). On one saved host, **check** reaches it
again, **edit** reopens its form, and **remove** forgets it. Saved hosts are offered by name on
the `host` row of every environment form at `/flow`. What each field means is in
[Machines › Runtimes](/reference/machines#runtimes).

A docker daemon is saved on the same page with **Add a runtime…** and `docker host`, and named with
`-e box=docker@<name>/…`: see
[Containers](/user/containers#example-a-daemon-saved-under-a-name).
Its `endpoint` may be a saved ssh host, the daemon on that host, reached with everything the
host says. A docker swarm is saved there too, with `docker swarm` under **Add a runtime…** -- the same form for
one of its managers, with where its tasks may go in place of GPU ids -- and named with
`-e box=swarm@<name>/…`, or `swarm@local/…` for the swarm this machine manages.

## Where the agent runs {#where-the-agent-runs}

The harness is the agent's CLI and whatever supervises it. Where it runs is a setting of the
runtime the work is on, not of the run: the `harness runs on` row of a saved host's form, its
**affinity**. Write the places in the order to try them, separated by commas; the next is tried
only when the one before has no room:

```text
     8. workdir          /home/me/build/myproject   default working directory when -e …
   ❯ 9. harness runs on  docker:gpubox, local       where an agent's harness runs, in order …
```

| | *(blank)* | `local` | `self` | `ssh:<name>`, `docker:<name>` |
| --- | --- | --- | --- | --- |
| **The CLI runs** | on the host if it can, else here | here | on the host | on that runtime |
| **Signed in as** | whichever it came to | this machine's CLI, or the `@account` | the host's CLI, or the `@account` sent there | that machine's CLI |
| **Sessions kept** | whichever it came to | here, with the run | on the host | on that machine |
| **Needs on the host** | Python 3.12 | Python 3.12 | Python 3.12, the CLI, and Landlock for a fenced role | Python 3.12 |
| **No room when** | never | never | the CLI is not on the host, or it cannot hold the role's fence | it cannot be reached, has no share left, or the role is fenced |

Each role is settled once per machine, as its first session there opens, and before the flow
is called every role is walked against every machine of the run: where no place in an affinity
has room, the run is refused before anything runs, with the last place's refusal. The
affinity read is the one of the runtime the work is on; a runtime a harness is sent to is used
as it is, its own affinity never walked.

### No affinity: the default

The CLI runs on the host when all three hold, and here otherwise:

- the host has the CLI, on the `PATH` a command run there gets;
- the host can hold the role's [permission](/user/permissions), which takes Landlock there for
  any role not granted everything;
- the flow hangs no hook on the role that decides whether each tool runs, such as the builder
  of [`humanize1:rlcr`](/flows/humanize1): a CLI on another machine can only report what such a
  hook would have decided, so that role stays here. A hook that answers the agent's questions
  is not one of those: a question comes back from wherever the CLI runs.

A host given with `-e` and never saved, and docker's default `docker@local`, are always placed
this way. Nothing to do when it goes either way: the run is the same run. Give the host an
affinity only to insist.

### `local`: here

The CLI runs here, with this machine's sign-in and its sessions kept with the run. It works in
a copy of the host's directory that humanize keeps here, and every command it runs is sent to
the host. The transcript says `builder's harness runs here`. Use it when the host is one you
would not give your account to, or when its CLI is signed in as somebody else. `local` always
has room, so nothing after it is ever tried.

#### The path is taken here too

::: warning The copy here has the host's path
The copy the agent works in is kept **at the same path** on this machine. That path has to be
one you can create here, and must be free: absent, empty, or humanize's copy of that same host
from an earlier run.

- A directory with other files in it is refused rather than overwritten, so
  `ssh@build-box/home/me/code/myproject` fails when your own checkout is at
  `/home/me/code/myproject` on this machine.
- A path you may not create here fails the turn, as
  `cannot keep the local copy of the work at /home/me/build/myproject: Permission denied: /home/me`,
  marked `(unmirrored: …)`.

A `docker@` environment keeps its copy under `~/.humanize/envs/mirrors/` instead, so its
workdir may be your own checkout.
:::

### `self`: on the host

The CLI installed on the host runs there, in the host's directory, with nothing copied. The
transcript says `builder's harness runs on its environment's machine`. Use it when the host is
where the CLI should live: a machine with its own sign-in, or a network only it reaches.

- **Its sign-in is the host's.** An agent with no `@account` runs as the host's CLI is signed
  in. One with an `@account` has the account's variables and credential files sent to the host
  for each turn, and taken away after. An account signed in with a login that renews itself
  (Codex with ChatGPT, Claude Code with a subscription, and other OAuth logins) is sent only
  while no other turn is using it, and what the host renewed it to is brought back: two copies
  renewing apart get the login revoked. A turn that finds it in use the other way is refused
  with `… signs in with a token that refreshes itself …`; give such roles an account signed in
  with a key, or put `local` first in the host's affinity
  ([more](/user/troubleshooting#this-account-signs-in-with-a-token-that-refreshes-itself)).
- **Never copy your own sign-in to the host.** Sign the CLI in there itself. A copy of
  `~/.codex/auth.json` or `~/.claude/.credentials.json` renews apart from yours and signs this
  machine out.
- **Its sessions are kept on the host**, not with the run here.
- **The flow's own tools are not offered to it**, and a hook that decides whether each tool
  runs can only watch.
- **A role not granted everything needs Landlock on the host** to hold its permission.

Where the host has no CLI, or cannot hold the role's permission, `self` has no room and the
next place is tried. Where `self` is the last, the run is refused before the flow starts, with
exit status 2, saying what to do about the first one missing:

```text
hmz exec: error: ssh@build-box: nowhere its affinity (self) names has room for claude's harness; the last: claude is not installed on ssh@build-box: npm i -g @anthropic-ai/claude-code there, or put local in the affinity of the runtime it is on
```

::: tip Installed is on the `PATH` an ssh command gets
A CLI your shell profile puts on the `PATH`, such as one under `~/.local/bin`, is not found
there. `ssh build-box 'command -v claude'` prints nothing in that case: install it where that
command finds it, such as `/usr/local/bin`.
:::

### `ssh:<name>`, `docker:<name>`: on another runtime

The CLI runs on another saved runtime, and reaches the host's work from there. Use it when
neither this machine nor the host should hold the agent: a machine that is the only one signed
in, say, or a docker daemon with containers to spare. The runtime is opened as an environment
of its own for the run, probed with the others and taken down with them:

| In the affinity | The CLI runs |
| --- | --- |
| `ssh:gpu-box` | on the host saved as `gpu-box`, in its saved workdir, else the login's home |
| `docker:gpubox` | in a container of its own on the daemon saved as `gpubox`, holding its saved workdir; a daemon on this machine saved without one holds `~/.humanize/harness` |

Such a place has no room when it cannot be reached or opened, when a daemon has no share left
for the container (its `max containers` reached, say), and for any role not granted
everything. Its other caveats:

- **Only a role granted everything.** A permission cannot be held around a CLI on another
  machine, so a fenced role passes it by: `a fence cannot hold a harness that runs on another
  machine`. Most flows' roles run at the default grant; see [Permissions](/user/permissions).
- **The CLI must be installed and signed in there.** Nothing checks before the turn: a machine
  without it fails the turn with `claude: not found on PATH`. No `@account` is sent there.
- **It opens a port here, on every interface,** for as long as the run lasts, for the two
  machines to meet. Set `HUMANIZE_RENDEZVOUS_PORT` to pin it for a firewall.
- **It cannot be the host itself:** an affinity naming its own runtime is refused when it is
  saved; that is `self`.

## What it needs

| Where | What it needs |
| --- | --- |
| **This machine** | Linux on x86-64 or aarch64, and the agent's CLI installed and signed in, unless the harness runs elsewhere |
| **The host** | Linux or macOS on any architecture, Python 3.12 or newer, `ssh` access, and the project already at that path. The CLI too, for `self`. |
| **The flow** | a role for the host, besides its workspace |

A Mac gives a remote command no `python3` on its `PATH`, so humanize also looks where Homebrew
and the python.org installer put one, and says what it looked for if it finds none.

## Variations

- **Several roles, several hosts.** Give each environment role its own `-e`, or several in one
  separated by commas: `-e box=ssh@build-box,gpu=ssh@gpu-box/~/train`.
- **A path under the login's home.** `ssh@build-box/~/build/myproject` is the same directory
  for whoever ssh logs in as, without spelling out the home.
- **A container instead of a host.** `-e box=docker@local/home/me/myproject` gives the role a
  container of its own: see [Containers](/user/containers).
- **A directory on this machine.** `-e box=local@/srv/project` puts the role somewhere other
  than the workspace, on this machine.
- **Another host when this one is down.** Fill in **falls back to** on a saved host's form
  (`ssh:build-2, docker:box`): where `-e box=ssh@build-box/…` cannot reach `build-box`, the
  role goes to the first of those that it can, and the run says so —
  `hmz exec: ssh:build-box cannot hold 'box': …; using ssh:build-2`. Where the agent's CLI
  runs is still `-H`'s. See [Machines › Falling back](/reference/machines#falling-back).

## If it goes wrong {#when-it-refuses}

Most of these stop `hmz exec` before anything runs, as `hmz exec: error: …`, with exit
status 2.

| You see | What to do |
| --- | --- |
| `onbox needs an environment for 'box'; specify each with -e ROLE=BACKEND@RUNTIME/WORKDIR` | Say where `box` is, with `-e` or at `/flow`. |
| `ralph_loop has no environment role 'box'; available roles are none` | That flow only works in the directory you start it in. |
| `onbox: 'workspace' is the workspace the run started in and cannot be set with -e` | Start `hmz` in that directory instead. |
| `there is no ssh host build-box: …` | Nothing resolves the name. Check your ssh config. |
| `could not reach build-box over ssh: …` | Run `ssh build-box` yourself and fix what it says. |
| `could not reach build-box over ssh: … no python 3.12 or newer on this machine; …` | The host has no Python 3.12 or newer that humanize can find. Install one there. |
| `the workdir /home/me/build/myproject is not there` | Put the project on the host at that path. |
| `… 'box' needs 8 GPUs, and the environment given has 0` | The flow asks more of the host than it has. Pick another host. |
| `… already contains files and is not an humanize mirror …` | The same path here holds other files. See [the path is taken here too](#the-path-is-taken-here-too). |
| `… mirrors ssh://old-box, not ssh://build-box …` | That path here holds humanize's copy of another host. Use another path. |
| `cannot keep the local copy of the work at …` on the first turn | The path cannot be created here. Use one you can create, or put `self` in the host's affinity. |
| `… nowhere its affinity (self) names has room …: claude is not installed on ssh@build-box: …` | `self` and no CLI on the host's `PATH`. Install it there, or add `local` to the affinity. |
| `… nowhere its affinity (docker:gpubox) names has room …: a fence cannot hold a harness that runs on another machine` | A runtime in the affinity for a role not granted everything. Add `local` after it. |
| `build-box: 'somewhere' is not where a harness runs: self, local or <ssh\|docker\|swarm>:<runtime name>` | Saving the host refused an affinity entry. Spell each as one of those. |

More, with what causes each, are in [Troubleshooting](/user/troubleshooting).

::: details Good to know
- **Network.** With the harness here, the agent's own connection to its model provider stays
  here, and the commands it runs use the host's network. With `self` both are the host's.
- **Timing.** What a command changes on the host is visible to the agent once that command has
  exited. See [What is not guaranteed](/reference/remote-execution#what-is-not-guaranteed).
- **Other ways to reach a machine.** A port left listening, a running container, or a target
  reached by hand are below the flow API: see the
  [Remote execution reference](/reference/remote-execution).
:::

## The flow used on this page

::: details `onbox`: build on the box, review here
Save it as `.humanize/flows/onbox/__init__.py` in your project, and it is offered as
`local/onbox`. What each line means is the [Weaver Guide's](/weaver/writing-a-flow) to explain.

```python
"""Build on the box, review here."""

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


class Box(Env, ShellEnvMixin): ...


class Agents(AgentCollection):
    builder: Agent
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv  # the directory the run starts in
    box: Box             # wherever -e says


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def onbox(task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    builder, reviewer = agents["builder"], agents["reviewer"]
    working = await builder.spawn(env=envs["box"])
    await builder.run(task, session=working)
    for _ in range(3):
        _, diff, _ = await envs["box"].exec(["git", "diff"])
        reading = await reviewer.spawn(env=envs["workspace"])
        review = await reviewer.run(f"Say what is wrong with this diff:\n\n{diff}", session=reading)
        await builder.run(review, session=working)
```

:::

## Next steps

- [Containers](/user/containers): a container for a role, reached the same way
- [Permissions](/user/permissions): what a role may touch, on the host as here
- [Remote execution reference](/reference/remote-execution): the arrangements behind an
  affinity, and where the account lives in each
- [Machines › Runtimes](/reference/machines#runtimes): every field of
  a saved host, its affinity among them
- [humanize in CI](/user/ci): the same `-e` in a scheduled job

<style scoped>
.re-split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: stretch;
  gap: 0;
  margin: 22px 0 8px;
}

.re-side {
  padding: 12px 16px 6px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
}

.re-there {
  border-color: var(--hmz-accent);
}

.re-where {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--vp-c-text-3);
}

.re-there .re-where {
  color: var(--hmz-accent);
}

.re-side ul {
  margin: 6px 0 8px;
  padding-left: 18px;
}

.re-side li {
  margin: 2px 0;
  font-size: 14px;
  line-height: 1.5;
}

.re-link {
  display: flex;
  align-items: center;
  padding: 0 6px;
}

.re-link span {
  position: relative;
  padding: 2px 10px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .re-split {
    grid-template-columns: minmax(0, 1fr);
  }

  .re-link {
    justify-content: center;
    padding: 6px 0;
  }
}
</style>
