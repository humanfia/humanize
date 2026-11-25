---
title: Branch a conversation
description: Fork a session so several attempts start from the same point in one conversation, each knowing everything said before it.
---

# Branch a conversation

Call `await agent.fork(session)` to create a new session that keeps the original conversation and branches off on its own. Use it to try several approaches after an expensive step, such as reading a codebase.

![One session reads the code once; two forks carry that reading on, and each takes its first turn in a worktree of its own](/diagrams/builder-branching-1.svg)

## Fork a session

This flow has a coder read the code once, then forks the session twice. Both forks run at the same time, each trying a different approach in its own git worktree.

```python
# .hmz/flows/two_ways/__init__.py
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    LocalEnv,
    flow,
)

WAYS = ("as a percentage off the total", "as a fixed amount off the total")


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, GitWorktreeEnvMixin):
    """The project. The flow may add worktrees of it."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def two_ways(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """Read the code once, then try the task two ways, each in its own worktree."""
    coder, workspace = agents["coder"], envs["workspace"]
    base = await coder.spawn()
    await coder.run(
        f"Read the code this needs. Change nothing yet.\n\n{task}",
        session=base,
        env=workspace,
    )

    async def attempt(way: str) -> str:
        tree = await workspace.derive_worktree()
        branch = await coder.fork(base)
        return await coder.run(f"Now do it {way}.", session=branch, env=tree)

    return await asyncio.gather(*(attempt(way) for way in WAYS))
```

`fork` returns a new session of the same agent. The original session is unchanged, and forks never see each other's turns. The session you fork must have taken at least one turn.

Calling `fork` sends nothing on its own. The fork is cut on its first turn, and that turn's `env` sets where the fork works. Each fork inherits the conversation history, effort, skills and tools, and tracks its own `usage`.

Call `derive_worktree` to give each attempt its own checkout so they do not overwrite each other's files. See [Worktrees, clones and scratch](/builder/worktrees).

Run the flow in a git repository with at least one commit:

```sh
hmz exec -f @local/two_ways -a coder=claude/claude-haiku-4-5 \
    -p budget.output_tokens=20000 "Add a discount code to checkout"
```

![The command's output: the agent reads two files and answers, then two conversations work at once, each editing and testing, and each gives its own answer](/shots/builder-branching-exec.svg)

*One reading, followed by conversations 2 and 3 running at once as the two forks.*

In Humanize Desktop, the epic lists three sessions under the agent. Select a fork to see the inherited reading followed by its own turn.

![Humanize Desktop with the epic open on the second session: the reading prompt and its answer, then the fork's own prompt, its edit, its test run and its answer; the sidebar lists three sessions](/shots/builder-branching-epic.svg)

*A fork's thread starts with the turns it was forked from.*

## Fork in the same directory

If your branches only answer questions and write no files, run their first turns in the original session's environment. More harnesses support forking in the same directory.

```python
careful = await coder.fork(base)
quick = await coder.fork(base)
plans = await asyncio.gather(
    coder.run("How would you fix it carefully?", session=careful, env=workspace),
    coder.run("How would you fix it quickly?", session=quick, env=workspace),
)
```

## Check harness support

Every agent has `fork` without needing a mixin. What a fork can do depends on the harness filling the role.

| Harness | Forks |
| --- | --- |
| `claude`, `codex`, `kimi`, `litellm` | Into any directory on the same machine. |
| `pi`, `omp`, `grok`, `opencode`, `mimo`, `qwen`, `acp` | Only into the directory the session last worked in. An `acp` CLI forks only if it offers forking. |
| `cursor-agent`, `mcode`, `agy`, `dsh` | Not at all. |

No harness forks onto another machine.

## Handle a refused fork

Humanize raises an error either when you call `fork` or on the fork's first `run`.

| Raised by | Error | When |
| --- | --- | --- |
| `fork` | `SessionError` | The session is not this agent's, is closed, or has taken no turn. |
| `fork` | `UnsupportedOperation` | The agent is an outworlder. |
| The fork's first `run` | `UnsupportedOperation` | The harness does not fork, the turn's `env` is on another machine, or it is another directory on a harness that forks only in place. |
| The fork's first `run` | `SessionError` | The session it was forked from has taken a turn since the fork, or the harness could not cut the fork. |
| The fork's first `run` | `HarnessUnrecoverable` | The harness is `grok` and the role offers fake tools. |

Catch `UnsupportedOperation` and spawn a fresh session to keep a flow running on harnesses that cannot fork. The fresh session starts without the conversation history.

```python
from hmz.flows import UnsupportedOperation

branch = await coder.fork(base)
try:
    answer = await coder.run(prompt, session=branch, env=tree)
except UnsupportedOperation:
    answer = await coder.run(prompt, session=await coder.spawn(), env=tree)
```

## Test a branching flow

A fake agent records the parent of each forked session. `FakeAgentDriver` forks like its target harness; pass `forks=False` to simulate a harness that cannot fork. See [Test a flow](/builder/testing).

```python
# tests/test_two_ways.py
import asyncio

from hmz.sdk import fakes


def test_both_ways_carry_the_reading() -> None:
    coder = fakes.FakeAgentDriver()
    asyncio.run(fakes.run_fake("two_ways", "Add a discount", agents={"coder": coder}))

    reading, *branches = coder.sessions
    assert [branch.forked_from for branch in branches] == [reading, reading]
    assert len(reading.prompts) == 1  # the parent took no further turn
    assert all(branch.prompts[0] == reading.prompts[0] for branch in branches)
```

## Good to know

- Run a fork's first turn before the parent session takes another turn, or the fork's first turn raises `SessionError`. Call `fork` again to branch from the newer point. Turns in a fork never advance the parent session.
- You can fork a fork after it takes at least one turn.
- A `litellm` agent has no directory. Pass `env=None` for its turns and its forks' turns.
- `fork` copies a conversation. `derive` narrows an agent's permissions and holds no conversation. See [Agent roles](/builder/agents).
- `fork` branches from a session in the current run. To branch from an earlier run, save the session in a resumable flow's state. See [Resumable flows](/builder/resumable).
- To move a session to another directory without branching, pass a different `env` to its next turn. See [Machines and moving sessions](/builder/machines).
