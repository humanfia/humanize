# Remote execution

Point one of a flow's environments at another machine with `-e`, and every agent the flow
opens there runs **here** while its work happens **there**. Reach for it when the build, the
tests or the GPUs are on another machine, and the agent's CLI and your sign-in are on this one.

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

## Try it

First check that `ssh build-box` works from here, and that the project is on the host at the
path you are about to name. humanize uses your own ssh config, agent and keys.

Then say where the flow's role is, on the command line or at the prompt:

::: code-group

```sh{3} [hmz exec]
hmz exec -f onbox \
    -a builder=claude/claude-opus-5:high -a reviewer=codex/gpt-5.6-sol:high \
    -e box=ssh@build-box/home/me/build/myproject \
    -b cost=20 "fix the build"
```

```text [at the prompt]
/flow, choose local/onbox. Its environment roles are rows under its agents:

   ❯ 1. builder                  claude/claude-opus-5:high
     2. reviewer                 codex/gpt-5.6-sol:high
     3. box                      not said yet

enter on box asks "Where box is". Type it as -e spells it after the =:

     ssh@build-box/home/me/build/myproject
```

:::

`onbox` is a project flow with two places: `workspace`, the directory you started in, and
`box`, which you name. The builder works on the box and the reviewer reads here. The flow's own
steps on `box`, such as a `git diff`, run on the box too. At the prompt, your answer is saved
with the flow's setup, like its agents.

::: details The flow, to try this yourself
Save it as `.humanize/flows/onbox/__init__.py` in your project. What each line means is the
[Weaver Guide's](/weaver/writing-a-flow) to explain.

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

## What `-e` takes

| `-e box=` | Where the role's work happens |
| --- | --- |
| `ssh@build-box/home/me/build/myproject` | that directory on a host `ssh` reaches: `host`, `user@host`, `host:port`, or an alias from your ssh config |
| `ssh@build-box/~/build/myproject` | the same, under the home directory of whoever ssh logs in as |
| `local@/srv/project` | a directory on this machine |

**Only a role the flow declares for it.** The workspace is always the directory you started
in, and naming it with `-e` is refused. The flows humanize and the official flowverse ship all
work in the workspace alone, so none of them takes an `-e`. A flow written for another machine
declares a role like `box`: see
[Flows › Where each agent works](/reference/flows#where-each-agent-works).

::: warning The path is taken on this machine too
The agent works in a copy of the host's directory that humanize keeps here **at the same
path**. That path has to be one you can create on this machine, and must be free here:
absent, empty, or humanize's copy of that same host from an earlier run. A directory with other
files in it is refused rather than overwritten, so `ssh@build-box/home/me/code/myproject`
fails when your own checkout is at `/home/me/code/myproject` on this machine.
:::

## What it needs

| Where | What it needs |
| --- | --- |
| **This machine** | Linux on x86-64 or aarch64, and the agent's CLI installed and signed in |
| **The host** | Linux or macOS on any architecture, Python 3.12 or newer, `ssh` access, and the project already at that path. You install nothing else there: humanize brings what it needs. |
| **The flow** | a role for the host, besides its workspace |

A Mac gives a remote command no `python3` on its `PATH`, so humanize also looks where Homebrew
and the python.org installer put one, and says what it looked for if it finds none.

## When it refuses

Most of these stop `hmz exec` before anything runs, as `hmz exec: error: …`, with exit
status 2.

- `onbox needs an environment for 'box'; give each with -e ROLE=BACKEND@PROVIDER/WORKDIR`\
  Say where `box` is, with `-e` or at `/flow`.
- `ralph_loop has no environment role 'box'; its environment roles are none`\
  That flow only works in the directory you start it in.
- `onbox: 'workspace' is the workspace the run is started in, and is not given with -e`\
  Start `hmz` in that directory instead.
- `there is no ssh host build-box: …`\
  Nothing resolves the name. Check your ssh config.
- `could not reach build-box over ssh: …`\
  Run `ssh build-box` yourself and fix what it says.
- `could not reach build-box over ssh: … no python 3.12 or newer on this machine; …`\
  The host has no Python 3.12 or newer that humanize can find. Install one there.
- `the workdir /home/me/build/myproject is not there`\
  Put the project on the host at that path.
- `… 'box' needs 8 GPUs, and the environment given has 0`\
  The flow asks more of the host than it has. Pick another host.
- `… already contains files and is not an humanize mirror …`\
  The same path on this machine holds other files. See the warning above.
- `… mirrors ssh://old-box, not ssh://build-box …`\
  That path here holds humanize's copy of another host. Use another path.

::: details Good to know
- **Network.** The agent's own connection to its model provider stays here. The commands it
  runs use the host's network.
- **Timing.** What a command changes on the host is visible to the agent once that command has
  exited. See [What is not guaranteed](/reference/remote-execution#what-is-not-guaranteed).
- **Other ways to reach a machine.** A port left listening, a running container, or the agent
  itself moved to the host are below the flow API: see the
  [Remote execution reference](/reference/remote-execution).
:::

## See also

- [Containers](/user/containers): a container reached the same way
- [Remote execution reference](/reference/remote-execution)
- [Troubleshooting](/user/troubleshooting)
- [humanize in CI](/user/ci)

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
