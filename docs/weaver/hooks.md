<script setup>
import RoleFit from '../.vitepress/theme/components/weaver-asking/RoleFit.vue'
</script>

# Hooks

In this guide you hang your own code on the moments of an agent's sessions. You build
`watched`, which prints every tool its agent reaches for and adds a reminder to every prompt,
and `gated`, which refuses any command that deletes a file.

Reach for a hook to watch an agent, add to what it is told, refuse something it reaches for, or
keep it from stopping. Everything a hook does happens inside a turn, while the flow's own code
is waiting on `run`.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- A repository with a `calc.py` and a `check.py`, as in [Worktrees, copies and
  scratch](/weaver/worktrees#snapshots-and-rewinding), to follow the runs exactly.
:::

## How it works

A **hook** is an async function you hang on one **moment** of an agent's sessions: a prompt
about to go, a tool about to run, a turn about to end. humanize calls it with what it knows of
that moment, as a params object, and the CLI waits for its answer, a result object.

Each moment has one method on the agent, named `on_` and the moment, and one params and result
class in `hmz.flows`, named after it: `on_stop` takes a function from `StopHookParams` to
`StopHookResult`. A hook hung on the wrong moment is a type error.

Six moments are on every agent, because every CLI reaches them:

| Method | When | Told | What the result does |
| --- | --- | --- | --- |
| `on_session_start` | a session is about to take its first turn | — | `context` goes in front of the first prompt |
| `on_user_prompt_submit` | a prompt is about to go to the agent | `prompt` | `context` is added to it; `block` refuses it, and `run` raises `SessionError` saying `reason` |
| `on_pre_tool_use` | the agent has reached for a tool that has not run yet | `tool`, `input` | `block` refuses it and tells the agent `reason`, [on the CLIs that wait](#stopping-a-tool) |
| `on_notification` | the agent has stopped to tell its user something | `message` | nothing: it is heard, not answered |
| `on_stop` | a turn is about to end | `said`, `again` | `block` keeps the agent going, with `reason` as its next prompt |
| `on_session_end` | a session is being closed | — | nothing |

Four more reach only some CLIs, so each is on a role that [declares the
mixin](#declaring-a-mixin) named after it, such as `PermissionRequestHookAgentMixin` for
`on_permission_request`:

| Method | When | Told | What the result does |
| --- | --- | --- | --- |
| `on_permission_request` | the CLI asks whether a tool may run | `tool`, `input` | `allow=False` refuses it and tells the agent `reason` |
| `on_subagent_start` | the agent has started a subagent of its own | `subagent`, `task` | nothing: no CLI waits on it |
| `on_subagent_stop` | one of those is about to finish | `subagent`, `said` | nothing: no CLI waits on it |
| `on_ask_user` | the agent has stopped mid-turn to ask its user a question | `question`, `options` | `answer` is what it is told; `None` lets it carry on without one |

Every params also carries `ctx`, the [context](/reference/flows#the-context) of the flow the
agent belongs to, and `session`, the session the moment arrived in. An outworlder made with
`Outworlder.new()` has one more moment, `on_outworlder_run`, which answers for it. See [The
person as an agent](/weaver/human-agent#stand-in-for-the-person).

## Example: watch the agent

The gentlest hooks only look, or add a line. `watched` does both:

```python
# .hmz/flows/watched/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    PreToolUseHookParams,
    PreToolUseHookResult,
    UserPromptSubmitHookParams,
    UserPromptSubmitHookResult,
    flow,
)


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


async def seen(params: PreToolUseHookParams) -> PreToolUseHookResult:  # ①
    print(f"  → {params.tool}: {str(dict(params.input))[:60]}")  # ②
    return PreToolUseHookResult()  # ③


async def remind(params: UserPromptSubmitHookParams) -> UserPromptSubmitHookResult:  # ④
    return UserPromptSubmitHookResult(context="Run python3 check.py before you finish.")


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def watched(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Do the task, saying every tool the agent reaches for."""
    agent = agents["agent"]
    agent.on_pre_tool_use(seen)  # ⑤
    agent.on_user_prompt_submit(remind)
    session = await agent.spawn()
    await agent.run(task, session=session, env=envs["workspace"])
```

### What each part does

1. **`seen`** is a hook for the moment a tool is about to run. It takes a
   `PreToolUseHookParams` and returns a `PreToolUseHookResult`, and it must be `async`.
2. **`params.tool` and `params.input`** are the tool's name, as the CLI names it, and what it
   was called with. A flow's `print` lands in the run's transcript, so this is also how a flow
   says something.
3. **An empty result changes nothing.** The tool runs as it would have.
4. **`remind`** adds `context` to every prompt before it goes to the agent. The flow's prompts
   stay short, and the reminder is in one place.
5. **`on_pre_tool_use(seen)`** hangs the hook on the agent, so it covers every session the
   agent opens, including a fresh one each round of a loop. Hang hooks before the turn they
   should cover.

### Run it

```sh
hmz exec -f watched -a agent=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "add a subtract function to calc.py"
```

A real run:

```text
● agent is working
● Read(/home/you/calc/calc.py)
● Read(/home/you/calc/check.py)
● Edit(/home/you/calc/calc.py)
● Bash(cd /home/you/calc && python3 check.py)
● I added `subtract(a, b)` to `calc.py`, and `python3 check.py` prints `ok`. …
✻ input 6 · output 396 · cache_read 44.6k · cache_write 5.8k · $0.03 · claude-sonnet-5-5 · agent
  → Read: {'file_path': '/home/you/calc/calc.py'}
  → Read: {'file_path': '/home/you/calc/check.py'}
  → Edit: {'file_path': '/home/you/calc/calc.py', 'old_string': '    return
  → Bash: {'command': 'python3 check.py', 'description': 'Run check sc
I added `subtract(a, b)` to `calc.py`, and `python3 check.py` prints `ok`. …
✻ Worked for 6s · agent
```

- **The `→` lines** are `seen`'s `print`s, one per tool, cut at 60 characters. A flow's own
  output can land a few lines away from the turn it belongs to.
- **The agent ran `python3 check.py`** without being asked in the task: that is `remind`'s
  context at work.

## Example: refuse a command

Every flow's agents run with approvals bypassed. A permission hook puts the flow back in the
loop: whatever the CLI asks about is allowed unless the hook says no. `gated` refuses any
command that deletes:

```python
# .hmz/flows/gated/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookParams,
    PermissionRequestHookResult,
    flow,
)


class Builder(Agent, PermissionRequestHookAgentMixin):  # ①
    """Every command it asks to run is put to the flow first."""


class Agents(AgentCollection):
    builder: Builder


class Envs(EnvCollection):
    workspace: LocalEnv


async def no_deleting(params: PermissionRequestHookParams) -> PermissionRequestHookResult:  # ②
    command = str(params.input.get("command", ""))  # ③
    if params.tool in ("Bash", "shell") and "rm " in command:
        print(f"  refused: {command}")
        return PermissionRequestHookResult(allow=False, reason="nothing is deleted here")  # ④
    return PermissionRequestHookResult()  # ⑤


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def gated(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Do the task, with every deletion refused."""
    builder = agents["builder"]
    builder.on_permission_request(no_deleting)  # ⑥
    session = await builder.spawn()
    await builder.run(task, session=session, env=envs["workspace"])
```

### What each part does

1. **`PermissionRequestHookAgentMixin`** on the role's type says the flow will answer
   permission requests. Only a CLI that asks them can fill the role, and a role without it
   cannot hang the hook at all.
2. **`no_deleting`** is called each time the CLI asks whether a tool may run.
3. **`params.input`** is the tool's input as the CLI gave it. For a shell tool, `command` is
   the command line.
4. **`allow=False`** refuses the tool, and the agent is told `reason`, so it can try something
   else or explain.
5. **An empty result allows it.**
6. **`on_permission_request`** is a method only a role declaring the mixin has.

### Run it

```sh
hmz exec -f gated -a builder=claude/claude-sonnet-5-5:high -p budget.cost=1 \
    "Delete check.py with rm, then say what happened. Do not try any other way."
```

```text
● builder is working
● Bash(rm check.py)
● I ran `rm check.py` in `/home/you/calc`, and it failed. The tool returned the error "nothing is deleted here", so `check.py` was not deleted. …
✻ input 4 · output 151 · cache_read 29.2k · cache_write 3.9k · $0.02 · claude-sonnet-5-5 · builder
  refused: rm check.py
…
✻ Worked for 4s · builder
```

The agent reached for `rm`, the hook refused it, and the agent was told why. `check.py` is
still there.

**Each CLI decides which calls it asks about.** The same run on Codex deletes the file: Codex
did not ask permission to run `rm` in its own working directory, so the hook never heard of it.
Kimi Code asks only about what it deems risky. To keep an agent from touching something on
every CLI, narrow its role's [permission](/user/permissions) instead.

### Check it worked

A fake session reaches the hooks from a reply function: `session.tool(…)` fires
`on_pre_tool_use`, then `on_permission_request` where the CLI serves it, and answers whether
the tool would run:

```python
# tests/test_hooks.py
import pytest

from hmz.flows import CapabilityMissing
from hmz.sdk import fakes

RM = {"command": "rm check.py"}
LS = {"command": "ls"}


async def reaches_for_tools(prompt: str, *, session: fakes.FakeSession, **_: object) -> str:
    await session.tool("Bash", LS)  # ①
    deleted = await session.tool("Bash", RM)
    return "deleted" if deleted else "refused"


async def test_every_tool_is_said(capsys: pytest.CaptureFixture[str]) -> None:
    agent = fakes.FakeAgentDriver(reply=reaches_for_tools)

    await fakes.run_fake("watched", "tidy up", agents={"agent": agent})

    assert "  → Bash: {'command': 'ls'}" in capsys.readouterr().out  # ②
    assert "Run python3 check.py before you finish." in agent.prompts[0]  # ③


async def test_a_deletion_is_refused() -> None:
    builder = fakes.FakeAgentDriver(reply=reaches_for_tools)

    await fakes.run_fake("gated", "tidy up", agents={"builder": builder})

    assert builder.sessions[0].tools == [("Bash", LS, True), ("Bash", RM, False)]  # ④


async def test_a_cli_that_never_asks_is_refused() -> None:
    with pytest.raises(CapabilityMissing):  # ⑤
        await fakes.run_fake("gated", "x", agents={"builder": fakes.FakeAgentDriver("mcode")})
```

```text
...                                                                      [100%]
3 passed in 0.09s
```

1. **`session.tool(name, input)`** is the fake agent reaching for a tool. The flow's hooks are
   called exactly as they would be on a real turn.
2. **`capsys`** is pytest's capture of what was printed: `seen`'s line for the `ls`.
3. **`agent.prompts`** records each prompt with what hooks added to it, so `remind`'s context
   is there.
4. **`session.tools`** records each tool, its input, and whether it was let run: `ls` was,
   `rm` was not.
5. **A fake MiniMax Code** asks no permission questions, so `gated` is refused before its
   first turn, as `hmz exec` refuses it.

## Hang, replace, take down

```python
agent.on_stop(keep_going)  # hung
agent.on_stop(other)  # replaced: one hook per moment per agent
agent.on_stop(None)  # taken down
```

A hook is hung on the **agent**, so it covers every session that agent opens. An agent
`derive`d from it shares its hooks. A flow you call is handed an agent of its own, so its hooks
and yours never hear each other's sessions. Hanging one mid-run is fine: it hears every moment
after that, in the turn under way too.

## Keep a turn going

An `on_stop` hook that blocks keeps the turn open until it lets go. `params.again` counts how
many times it has already kept this turn going, so it can give up:

```python
from hmz.flows import StopHookParams, StopHookResult


async def keep_going(params: StopHookParams) -> StopHookResult:
    if params.again < 3 and b"TODO" in await workspace.read("TASK.md"):
        return StopHookResult(block=True, reason="There is still a TODO in TASK.md.")
    return StopHookResult()
```

A `block` with an empty `reason` does not block.
[Goals](/weaver/goals#when-your-code-should-decide-instead) has this hook in a complete flow,
run for real. It is one of three ways to keep an agent going:

| | Decides it is done | Works on |
| --- | --- | --- |
| a `while` loop in the flow | your code, between turns | every CLI |
| a blocking `on_stop` hook | your code, inside the turn | every CLI |
| a [`/goal`](/weaver/goals) | the **model**, against the objective | `claude`, `codex`, `dsh`, `kimi` |

## Stopping a tool

There are two moments to stop a tool at, and whether a refusal stops it depends on the CLI:

| Refuse in | Stops the tool on | Elsewhere |
| --- | --- | --- |
| `on_pre_tool_use` | `claude`, `qwen` | <Badge type="warning" text="watch only" /> the hook hears of the tool, which may already be running |
| `on_permission_request` | `claude`, `codex`, `kimi`, for what each asks about | <Badge type="info" text="not served" /> a role that [declares it](#declaring-a-mixin) is never given these CLIs |

On Claude Code, where both moments can stop a tool, `on_pre_tool_use` answers first, and a tool
it refuses is never put to `on_permission_request`. [`humanize1`](/flows/humanize1) guards its
builder with both.

::: tip Hang these before the turn they should cover
`on_pre_tool_use` on Claude Code and Qwen Code, and `on_permission_request` or `on_ask_user` on
Codex and Kimi Code, change how the CLI is started. Hung mid-turn, they take hold from the next
turn.
:::

## Declaring a mixin

A role that hangs a hook on a moment only some CLIs reach says so on its type, as `gated`'s
`Builder` does. A CLI that does not reach the moment is refused before the first turn, and
`/flow` does not offer it for that role:

```sh
hmz exec -f gated -a builder=mcode/MiniMax-M3:high -p budget.cost=1 "fix the build"
```

```text
hmz exec: error: gated: 'builder' needs PermissionRequestHookAgentMixin, which mcode does not support
```

A role that did not declare it cannot hang one: `on_permission_request` on a plain `Agent` is a
type error, and raises `CapabilityNotGranted` if it runs anyway, whatever the CLI underneath
could do.

| CLI (`-a`) | `on_permission_request` | `on_subagent_start`, `_stop` | `on_ask_user` |
| --- | :---: | :---: | :---: |
| `claude`, `codex` | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> |
| `kimi` | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> | <Badge type="tip" text="yes" /> |
| `cursor-agent`, `mcode` | <Badge type="info" text="no" /> | <Badge type="tip" text="yes" /> | <Badge type="info" text="no" /> |
| `pi` | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> | <Badge type="tip" text="yes" /> |
| `agy`, `dsh`, `grok`, `mimo`, `opencode`, `qwen`, an ACP CLI | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> | <Badge type="info" text="no" /> |

Every mixin a role declares narrows the CLIs that can fill it, goals and steering included.
Combine them here:

<RoleFit />

## Pitfalls

- **A hook that raises fails the turn it arrived in.** The turn is interrupted, and the `run`
  the flow is waiting on raises what the hook raised, as if the flow's own code had raised it.
  Catch inside the hook whatever it should survive.
- **A hook runs as the flow the agent belongs to.** `params.ctx` is that flow's context, and
  the hook may take a turn of another agent, read the environment or call a flow. The CLI waits
  meanwhile. A hook that keeps it waiting for 15 minutes is answered as if nothing were hung, so
  a stuck hook cannot stall the run. `on_ask_user` is the exception: a question waits for its
  answer. See [The agent asking the flow](/weaver/tools).
- **One hook per moment per agent.** Hanging a second replaces the first. To do two things at
  one moment, write one hook that does both.
- **A refusal is not a sandbox.** A hook sees what the CLI tells it about, and an agent refused
  one command may reach the same end another way. What a role may touch at all is its
  [permission](/user/permissions).

## Next steps

- [Goals](/weaver/goals): the same shape as a blocking `on_stop`, decided by the model
- [The agent asking the flow](/weaver/tools): `on_ask_user`, answered by the flow's code
- [Permissions](/user/permissions)
- [The moments of a turn](/features/hooks): a hook hung and a turn run, drawn
- [Reference › Hooks](/reference/flows#hooks-in-a-flow)
