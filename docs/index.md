---
layout: home
---

<script setup>
import { withBase } from 'vitepress'
import HmzTabs from './.vitepress/theme/components/home/HmzTabs.vue'

const WAYS = [
  { id: 'prompt', name: 'At the prompt', hint: 'hmz' },
  { id: 'exec', name: 'From your shell', hint: 'hmz exec' },
]
</script>

<HmzHero />

## How it fits together

<HmzArch />

## Run a flow

Install humanize, give it a scratch repository with a bug in it, and watch an agent fix it.

::: warning Agents here act without asking
Every flow's agents run with approvals bypassed: they edit files, run commands and make commits
on their own. Use a scratch repository, and read [Security](/user/security) before you point
one at work you care about.
:::

<div class="hmz-steps">

### Install humanize

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) or pip, and a coding agent
CLI you have already signed in to: Claude Code, Codex, or [any of the
others](/features/backends). humanize drives it under that login.

::: code-group

```sh [uv]
uv tool install git+https://github.com/humanfia/humanize.git
```

```sh [pip]
pip install git+https://github.com/humanfia/humanize.git
```

```sh [for DeepSeek Harness or Kimi Code]
uv tool install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

:::

### Make a scratch repository

`calc.py` subtracts where it should add. That bug is the work.

```sh
mkdir -p ~/tmp/humanize-demo && cd ~/tmp/humanize-demo && git init -q
printf 'def add(a, b):\n    return a - b\n' > calc.py
git add -A && git commit -qm "a calculator with a bug in it" && git tag before
```

### Run a flow on it

The flow is `ralph_loop`. It gives the agent the same task round after round, each time in a
fresh conversation, and it does not stop when the work is done: its budget stops it, or you do.

<HmzTabs :tabs="WAYS" label="Two ways to run a flow">
<template #prompt>

Open the terminal interface in the repository. Its first start asks once whether to report
what goes wrong to humanize; answer as you like.

```sh
hmz
```

Type `$`, the flow's name, and the task:

<div class="hmz-term" data-title="hmz">

```text
$ralph_loop Fix the bug in calc.py.
```

</div>

The first time, the flow's menu opens and holds your line. Pick the CLI, model and effort for
its one role, `agent`, set a budget, and press <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd>: that
saves the setup and starts the run. This directory remembers the setup: next time, the same line starts the run
straight away.

<kbd>ctrl+c</kbd> twice stops the flow, `/` lists every command, and `/exit` leaves.

<figure class="hmz-shot">
  <img :src="withBase('/demo/tui.gif')" alt="hmz opens, / lists its commands, and /flow opens a flow's menu" loading="lazy" />
  <figcaption>
    <code>/</code> lists the commands and <code>/flow</code> opens a flow's menu. Recorded with
    stand-in CLIs, so no agent takes a turn.
  </figcaption>
</figure>

</template>
<template #exec>

The same run as one line. `hmz exec` downloads no flows, so if you have not opened `hmz` yet,
open it once first: it fetches the official flows, `ralph_loop` among them, as it starts.

Then pick your CLI:

::: code-group

```sh [Claude Code]
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b duration=10m "Fix the bug in calc.py."
```

```sh [Codex]
hmz exec -f ralph_loop -a agent=codex/gpt-5.6-sol:high -b duration=10m "Fix the bug in calc.py."
```

```sh [Antigravity]
hmz exec -f ralph_loop -a agent=agy/gemini-3.7-flash-high:high -b duration=10m "Fix the bug in calc.py."
```

```sh [Qwen Code]
hmz exec -f ralph_loop -a agent=qwen/qwen3-coder-plus:high -b duration=10m "Fix the bug in calc.py."
```

```sh [Kimi Code]
hmz exec -f ralph_loop -a agent=kimi/kimi-code/k3:high -b duration=10m "Fix the bug in calc.py."
```

```sh [Grok Build]
hmz exec -f ralph_loop -a agent=grok/grok-4.6:high -b duration=10m "Fix the bug in calc.py."
```

```sh [ZCode]
hmz exec -f ralph_loop -a agent=zcode/zai/glm-5.3:high -b duration=10m "Fix the bug in calc.py."
```

:::

- `-f` names the flow.
- `-a agent=CLI/MODEL:EFFORT` fills its one role, `agent`: which CLI, which model, and how hard
  the model thinks.
- `-b` caps what the run may spend: a `duration`, a `cost` in dollars, or `output_tokens`. It
  will not start without one.

<kbd>ctrl+c</kbd> stops it. [The command line](/reference/cli) has every flag.

</template>
</HmzTabs>

### See what it did

```sh
git diff before
```

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

</div>

::: details If it does not start

| If | Then |
| --- | --- |
| `hmz` says `no such flow` | It downloads the official flows in the background as it starts. Give it a few seconds and send the line again. |
| `hmz exec` says `not been fetched yet` | `hmz exec` downloads nothing. Open `hmz`, type `/flowverses`, and press <kbd>r</kbd> on `official`. |
| the model is refused | Model ids change with each CLI release, and your account decides which you may use. In `hmz`, type `/flow ralph_loop` and open the `agent` row: it lists the models your CLI offers. |
| your CLI is not in the tabs | Every backend, and how to sign each one in, is on [Installation](/user/installation). |

:::

**Next.** The [User Guide](/user/) covers the interface, accounts and reading a run back, and
its tutorials each take a real piece of work start to finish: [Beat a
benchmark](/user/tutorials/take-home), [Port a project](/user/tutorials/port-a-project) and
[Build a coding agent](/user/tutorials/build-an-agent). [Flows](/flows/) lists what else there
is to run.

## Weave a flow

A flow is an async Python function that declares the agents it drives. Save this one in the
scratch repository as `.humanize/flows/twice/__init__.py`. It has an agent do the task, then
review its own work in the same conversation:

::: code-group

```python{6,19,21-23} [.humanize/flows/twice/__init__.py]
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent  # a role: -a builder=… fills it


class Envs(EnvCollection):
    workspace: LocalEnv  # the directory you run it in


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def twice(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Does the work, then reads it back and fixes what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])  # one conversation
    await builder.run(task, session=session)
    await builder.run(  # the same one, so this turn remembers the last
        "Now review what you just did, and fix anything that is wrong.", session=session
    )
```

:::

Run it like any other flow: by name from your shell, or as `$local/twice` at the prompt.

::: code-group

```sh [hmz exec]
hmz exec -f twice -a builder=claude/claude-opus-5:high -b cost=5 "Add a subtract function to calc.py."
```

```text [at the prompt]
$local/twice Add a subtract function to calc.py.
```

:::

**Next.** The [Weaver Guide](/weaver/) is everything a flow can ask of its agents: loops,
params, goals, hooks and worktrees. [Build under test](/weaver/tutorials/build-under-test)
writes a useful flow start to finish, and [Testing a flow](/weaver/testing-flows) runs one on
stand-in agents before a real one takes a turn.

## Contribute {#work-on-humanize}

```sh
git clone https://github.com/humanfia/humanize.git && cd humanize
uv sync
```

Every change has to pass both of these:

```sh
uv run pre-commit run --all-files
uv run pytest
```

[Contributing](/contributing/) says where a change goes, what those checks hold it to, and when
to also run the tests that drive real CLIs. [Your first
patch](/contributing/tutorials/first-patch) takes one change from a clone to a pull request.

## Where to go next

<div class="hmz-paths by-three">
  <a :href="withBase('/user/')">
    <strong>User Guide</strong>
    <span>Running flows: the interface, agents and accounts, where the work lands, and reading
    a run back.</span>
  </a>
  <a :href="withBase('/flows/')">
    <strong>Flows</strong>
    <span>Every flow in humanize and its official flowverse, each with its loop played.</span>
  </a>
  <a :href="withBase('/weaver/')">
    <strong>Weaver Guide</strong>
    <span>Writing flows: what a flow may ask of an agent, and how to write and test one.</span>
  </a>
  <a :href="withBase('/features/')">
    <strong>Features</strong>
    <span>How humanize works, drawn: one diagram per capability.</span>
  </a>
  <a :href="withBase('/reference/')">
    <strong>Reference</strong>
    <span>Every command, key, flag and Python call, spelled out.</span>
  </a>
  <a :href="withBase('/contributing/')">
    <strong>Contributing</strong>
    <span>Working on humanize itself: the layers, the checks, and these docs.</span>
  </a>
</div>
