---
layout: home
---

<script setup>
import { withBase } from 'vitepress'
</script>

<HmzHero />

## How it fits together

<HmzArch />

## Run a flow

::: warning Use a scratch directory
Nothing an agent does is put to you for approval: every flow's agents run with approvals
bypassed, and what one may touch is what its flow declares — by default, writing its working
directory. Do this in a throwaway git repository, and read [Security](/user/security) before you
point it at work you care about.
:::

You need Python 3.12 or newer and **one coding agent CLI you have already logged into**.
humanize holds no API key and talks to no model provider itself, so you log in the way you
already log in.

```sh
pip install git+https://github.com/humanfia/humanize.git
```

Then make something for it to fix. `calc.py` subtracts where it should add, and that bug is the
work:

```sh
mkdir -p ~/tmp/humanize-demo && cd ~/tmp/humanize-demo && git init -q
printf 'def add(a, b):\n    return a - b\n' > calc.py
git add -A && git commit -qm "a calculator with a bug in it"
```

Both ways below run the same flow, `ralph_loop`: it gives the agent the same task over and over
in a fresh conversation each time, so it restarts from the task and the repository rather than
from a context window full of its own earlier attempts.

### At the prompt

```sh
hmz
```

That opens the terminal interface, on nothing in particular. Say which flow and what it is to
do, on one line:

```
$ralph_loop Fix the bug in calc.py.
```

`$` names a flow, and this directory has never run that one, so `/flow` opens inside it with
your line held. What it asks is what the flow declares: its one role, `agent` — the CLI you are
already logged into, which of its models, and how hard it should think — and a budget, how long
the run may take or how much it may spend. The models offered are the ones **your account** may
name, asked of the CLI itself rather than written into humanize. `save` starts the flow on the
line you typed — as **shift+enter** or **ctrl+j** does from anywhere on the menu.

You answer that once. What you chose is remembered for this directory, so the next `hmz` here
opens on it and `Fix the bug in calc.py.` is the whole of what you type.

The agent takes a **turn** — one exchange with the model, which may run tools and may take
minutes — and then the loop gives it the same task again. Type another line while it is working
and it goes *into* the running turn rather than starting a new one. `/` lists every command,
**ctrl+c** twice stops the loop, and `/exit` leaves.

### Or without the interface

The same flow, the same agent, with the task on the line instead. `ralph_loop` is one of
humanize's own flows, which live in a [flowverse](/weaver/flowverses) fetched the first time
the flow menu opens — so if you have come straight here, open `hmz` once first and press
`/flow`.

::: code-group

```sh [Claude Code]
hmz exec -f ralph_loop -a agent=claude/claude-opus-4-8:high -b duration=20m "Fix the bug in calc.py."
```

```sh [Codex]
hmz exec -f ralph_loop -a agent=codex/gpt-5.6-sol:high -b duration=20m "Fix the bug in calc.py."
```

```sh [Antigravity CLI]
hmz exec -f ralph_loop -a agent=agy/gemini-3.7-flash-high:high -b duration=20m "Fix the bug in calc.py."
```

```sh [Qwen Code]
hmz exec -f ralph_loop -a agent=qwen/qwen3-coder-plus:high -b duration=20m "Fix the bug in calc.py."
```

```sh [Kimi Code]
hmz exec -f ralph_loop -a agent=kimi/kimi-code/k3:high -b duration=20m "Fix the bug in calc.py."
```

```sh [Grok Build]
hmz exec -f ralph_loop -a agent=grok/grok-4.6:high -b duration=20m "Fix the bug in calc.py."
```

```sh [ZCode]
hmz exec -f ralph_loop -a agent=zcode/zai/glm-5.3:high -b duration=20m "Fix the bug in calc.py."
```

:::

`-f` names the flow. `-a` names an agent for one of its roles, written
`role=cli/model:effort` — the role it fills, the CLI that runs the turn, the model it asks for,
and how hard that model should think; `role=cli@account/model:effort` also says
[which account](/user/providers). A flow that drives several takes several, separated by commas
or given an `-a` apiece. `-b` is what the run may spend — a `duration`, a `cost` in dollars, a
count of `output_tokens` — and `hmz exec` will not start without one. A Ralph loop does not stop
on its own, which is what it is for: the budget stops it, or **ctrl+c** at the command line when
you have seen enough. Every round is written down, so stopping loses nothing.

Either way, check the work:

```sh
git diff
```

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

It made that edit with **nothing asked**: there is nobody at a prompt to answer, so every
flow's agents run with approvals bypassed, and edit files, run commands and make commits on
their own. What an agent may touch is the `Permission` its flow declares for its role — its
working directory, the rest of your home, the machine, the network — and the flow decides it,
which is the one thing to have understood before pointing this at a real repository.

::: details The model id is wrong, or your CLI is not above
A model id is whatever that CLI shipped this week, and which ones you may name depends on the
account you are logged in as. Open `/flow` in the interface and turn to its agents: humanize
asks each CLI once and keeps the answer. Every backend it drives, including the ones not in
those tabs, is in [Many backends, one agent](/features/backends);
[Installation](/user/installation) is how to sign each one in.
:::

**Next.** [`/epics`](/user/tracing) lists the runs of this directory and turns any one of them
into a timeline you can open in Perfetto. The [User Guide](/user/) has a page per thing
humanize does, and its tutorials each take a real piece of work start to finish: [Beat a
benchmark](/user/tutorials/take-home), [Port a project](/user/tutorials/port-a-project), and
[Build a coding agent](/user/tutorials/build-an-agent). For the words above, properly defined,
read [Concepts](/user/concepts).

## Weave a flow

A **weaver** is whoever writes a flow. A flow is a directory whose `__init__.py` holds an async
function decorated with `@flow`, which declares the agents it drives, the environments they work
in and the params it takes — and is handed exactly those. Write one when you want the same
agents run the same way again and again, rather than typed out afresh each time.

```sh
mkdir -p .humanize/flows/twice
```

```python
# .humanize/flows/twice/__init__.py
"""Two passes: do the work, then read it back and fix what is wrong."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def twice(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Does the work, then reads it back and fixes what is wrong."""
    builder = agents["builder"]
    session = await builder.spawn(env=envs["workspace"])
    await builder.run(task, session=session)
    await builder.run(
        "Now review what you just did, and fix anything that is wrong.", session=session
    )
```

Run it by name. humanize also offers it in the interface: `/flow` lists the flows it ships,
every [flowverse](/weaver/flowverses) fetched here, and your own — the ones in
`.humanize/flows` as `local`, the ones in `~/.humanize/flows` as `user`.

```sh
hmz exec -f twice -a builder=claude/claude-opus-4-8:high -b cost=5 "add a --dry-run flag to calc.py"
```

What it declares is the whole contract:

| | |
| --- | --- |
| `@flow(agents=…, envs=…, params=…)` on an `async def` | The function takes the task, then `agents`, `envs`, `params` and `ctx` by keyword |
| A role is a key of the collection | `builder: Agent` is filled by `-a builder=…`, and is what a trace and the interface call it |
| A role's type says what the flow will ask of it | `Agent` alone runs turns; `class Worker(Agent, GoalCommandAgentMixin)` may also run a `/goal` |
| `LocalEnv` is the directory the run was started in | The runtime fills it, so it takes no `-e` |

A run is checked against the declaration before its first turn — a role left out, a CLI that
cannot do what its role asks — and the flow is handed agents that can do exactly what it
declared, whatever the CLI underneath could do.

Whether the second turn remembers the first is the other choice you are making:

```python
session = await builder.spawn(env=workspace)  # a conversation you hold
await builder.run("do the task", session=session)
await builder.run("keep going", session=session)  # the first turn still in context
fresh = await builder.spawn(env=workspace)  # another, starting from nothing
```

Try it before a real agent ever does, on stand-ins that answer from a script:

```python
import asyncio

from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake

builder = FakeAgentDriver(reply="done")
asyncio.run(run_fake("./.humanize/flows/twice", "fix calc.py", agents={"builder": builder}))
print(builder.prompts)  # ['fix calc.py', 'Now review what you just did, and fix anything …']
```

See [Testing a flow](/weaver/testing-flows).

**Next.** The [Weaver Guide](/weaver/) is what a flow may do and how to write one — loops,
params, goals, shapes, hooks, worktrees. [Build under
test](/weaver/tutorials/build-under-test) is the shortest useful flow there is, start to finish.

## Work on humanize

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync
uv run pre-commit install
```

Installing the hooks once means every commit is checked before it is made. There are two gates
and both have to pass:

```sh
uv run pre-commit run --all-files   # the formatter, the linter and the type checker
uv run pytest                       # every tier this machine can run
```

The tests sit in three directories, by what is on the other side of them: `tests/unit/` calls
`hmz` and nothing else, `tests/integration/` talks only to things this repository wrote — a
stand-in CLI, a fake app server, a loopback socket, a mock LLM service — and `tests/system/`
wants the real thing. The first two are the gate, and they are all CI runs. The third is a run
you make on purpose, on a machine that has a coding agent signed in:

```sh
uv run pytest tests/unit            # the fast loop, while you are still writing it
uv run pytest --run-agents          # also the system tier: real CLIs, real tokens
```

See [Contributing](/contributing/) for what belongs where.

What the code is held to: **`pyright` in strict mode** over `src` and `tests`, with `# type:
ignore` switched off — a suppression names a rule; **`ruff` with every rule on**, less the ones
annotated in `pyproject.toml`; **Google-style docstrings**; and a popular, well-maintained
library in preference to a custom implementation.

Each package depends only downwards, and a test checks the layering —
[Architecture](/contributing/architecture) has the layers and the rules that keep them. Most
packages have a SPEC under `specs/`, whose tree mirrors `src/hmz/`. **Do not modify a SPEC**
unless you were asked to: it is the contract, and the code is what has to move.

**Next.** [Contributing](/contributing/) is the whole of it, and [Your first
patch](/contributing/tutorials/first-patch) takes one change from clone to pull request.

## Where to go next

<div class="hmz-paths by-three">
  <a :href="withBase('/features/')">
    <strong>Features</strong>
    <span>What humanize is, drawn rather than described — one diagram per capability.</span>
  </a>
  <a :href="withBase('/flows/')">
    <strong>Flows</strong>
    <span>What it can run out of the box, with the shape of each loop played.</span>
  </a>
  <a :href="withBase('/user/')">
    <strong>User Guide</strong>
    <span>Running flows: a page per thing humanize does, opening with something to
    paste.</span>
  </a>
  <a :href="withBase('/weaver/')">
    <strong>Weaver Guide</strong>
    <span>Writing flows: what a flow may ask of an agent, and how to write one.</span>
  </a>
  <a :href="withBase('/contributing/')">
    <strong>Contributing</strong>
    <span>Working on humanize itself: the layers, the gates, and these docs.</span>
  </a>
  <a :href="withBase('/reference/')">
    <strong>Reference</strong>
    <span>Every command, key, flag and Python call, spelled out.</span>
  </a>
</div>

<p class="hmz-warn">
Nothing an agent does is put to you for approval — it edits files, runs commands and makes
commits without asking, within the permission its flow declares. Read
<a :href="withBase('/user/security')">Security</a> before you point one at a repository you care
about.
</p>
