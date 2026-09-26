<script setup>
import ForkHistory from '../.vitepress/theme/components/weaver-compose/ForkHistory.vue'
</script>

# Branching a conversation

`fork` makes a second conversation that starts out knowing everything the first one knows, and
goes its own way from there. Reach for it when a conversation has got somewhere expensive, such
as an hour of reading the code, and you want to try more than one way on from it.

## Try it

```python{4-5}
session = await agent.spawn(env=workspace)
await agent.run("read src/ and say what this does", session=session)

careful = await agent.fork(session, env=workspace)  # knows it all
quick = await agent.fork(session, env=workspace)    # so does this
await asyncio.gather(                               # both at once
    agent.run("now fix the retry logic, carefully", session=careful),
    agent.run("now fix the retry logic, quickly", session=quick),
)
```

The reading is paid for once. Everything said after the fork belongs to one branch only:
`session` is untouched, and `careful` and `quick` never see each other's turns. Take turns
below and watch who knows what:

<ForkHistory />

A fork is a session like any other. It has its own `usage`, which starts at nothing. It belongs
to the same agent, with the same model, permission and [hooks](/weaver/hooks). It is closed the
way every session is, when the flow call that opened it ends or nothing holds it any more.

## Take the child's first turn before the parent moves on

A fork is cut at **its own first turn**, not at the call to `fork`. If the parent takes a turn
in between, the child's first turn is refused rather than quietly branching from a later point:

```python
child = await agent.fork(session, env=workspace)
await agent.run("carry on here", session=session)  # parent moves on
await agent.run("and here", session=child)  # [!code error] SessionError
```

Fork again when you want the newer point. Turns on a child never move its parent, so the
two-branch pattern above is safe.

A session that has taken no turn has nothing to carry, and forking it raises `SessionError`.
`spawn` a fresh one instead.

## Fork into another directory

The `env` you pass to `fork` is where the child works, and it need not be the parent's. A
conversation that has read the repository can carry on in a
[worktree](/weaver/worktrees) of its own, so the two branches do not write over each other:

```python{2,5-6}
# The role may derive worktrees:
class Workspace(LocalEnv, GitWorktreeEnvMixin): ...


trying = await workspace.derive_worktree(ref="main")  # a new checkout
elsewhere = await agent.fork(session, env=trying)     # it works there
await agent.run("try the rewrite here", session=elsewhere)
```

Four CLIs can do this, as [the table below](#which-clis-can-fork) shows.

## Which CLIs can fork

`fork` is on every agent and needs no mixin. A CLI that cannot make the fork you ask for raises
`UnsupportedOperation`, at the call.

| CLI, as `-a` names it | Forks | Into another directory |
| --- | --- | --- |
| `claude`, `codex`, `kimi`, `zcode` | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> |
| `grok`, `mimo`, `opencode`, `pi`, `qwen`, an ACP CLI | <Badge type="tip" text="yes" /> | <Badge type="warning" text="same directory only" /> |
| `agy`, `cursor-agent`, `dsh` | <Badge type="danger" text="no" /> | <Badge type="danger" text="no" /> |

No CLI forks onto another machine. A flow meant to run on any CLI can fall back to a fresh
session:

```python
from hmz.flows import UnsupportedOperation

try:
    other = await agent.fork(session, env=workspace)
except UnsupportedOperation:
    other = await agent.spawn(env=workspace)  # starts from nothing
```

## Fork or derive?

They sound alike and do opposite things:

| | Gives you | Carries the history? |
| --- | --- | --- |
| `agent.fork(session, env=…)` | another **conversation** of the same agent | yes |
| `agent.derive(permission=…)` | the same **agent** under a narrower grant | no: it holds no conversation |

`derive` is covered in [A flow that calls a
flow](/weaver/calling-flows#narrow-what-you-hand-on).

## See also

- [Many turns at once](/weaver/async-flows), for driving the branches together
- [Worktrees, copies and scratch](/weaver/worktrees), for branching the files rather than the
  conversation
- [Many conversations at once](/user/conversations), for reading the branches at the prompt
