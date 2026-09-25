# Branching a conversation

A session can be **forked**: a second conversation carrying this one's history, going its own
way from the moment it was made. Reach for it when a conversation has got somewhere expensive
and you want to try more than one way out of it.

## Try it

```python
session = await agent.spawn(env=workspace)
await agent.run("read src/ and tell me what this service does", session=session)

careful = await agent.fork(session, env=workspace)
quick = await agent.fork(session, env=workspace)
await asyncio.gather(
    agent.run("now rewrite the retry logic, and mind the timeouts", session=careful),
    agent.run("now rewrite the retry logic, fastest thing that works", session=quick),
)
```

Both children start out knowing everything `session` knew — the hour of reading is paid for
once. What either of them is told afterwards is its own: the original is untouched, and the two
never see each other's turns. They are two sessions, so they may take their turns at once.

`fork` is on every agent. It needs no mixin, because it is not something a flow can be refused
for asking: it is something some CLIs cannot do, and those [say so](#which-clis-can) when they
are asked.

## Fork into another directory

The `env` a fork is given is where the child works, and it need not be where the parent did. A
conversation that has read the repository can carry on in a worktree of its own, so the two
ways out of it do not write over each other:

```python
class Workspace(LocalEnv, GitWorktreeEnvMixin): ...


trying = await workspace.derive_worktree(ref="main")
elsewhere = await agent.fork(session, env=trying)
await agent.run("try the rewrite here, on a clean checkout", session=elsewhere)
```

Claude Code, Codex, Kimi Code and ZCode carry a conversation into another directory: the child
is told where it now is, and on Claude Code its transcript is copied to where the CLI resumes
from. Every other CLI that forks does so only into the directory the conversation is already
in. No CLI forks onto another machine.

## What the child is

The CLI's own fork does the carrying. There is no transcript replayed into a fresh session and
no context handed between two processes: the CLI loads the conversation it already has and
calls what follows a session of its own.

So the child is a conversation in every way a run counts one:

| | |
| --- | --- |
| **Its own id** | the CLI's id for the new conversation, not the old one |
| **Its own spending** | `child.usage` starts at nothing; nothing spent on the parent counts twice |
| **Its own place** | it is a session of its own in the run's record |
| **Its own future** | turns of one are not turns of the other |

It belongs to the same agent as the parent — the same CLI, model and grant, and the same
[hooks](/weaver/hooks) — and is closed like any session: as soon as nothing holds it, or when
the flow call that opened it ends, whichever comes first.

## Use the child before the parent moves on

A fork is cut where the child takes its first turn, so the branch point is where you called
`fork` only if the parent has not taken another turn in between:

```python
child = await agent.fork(session, env=workspace)
await agent.run("carry on here", session=session)    # the parent moves on
await agent.run("and here", session=child)           # SessionError: fork it again
```

That is refused rather than done, because the alternative is a child branched from somewhere
nobody chose which reads exactly like the branch that was asked for. Fork again when you want
the newer boundary. Driving one child does not move the parent, so the two-children pattern
above is unaffected.

## When there is nothing to fork

A conversation that has taken no turn has no history to carry, so forking one raises
`SessionError`: it is one to open rather than one to fork. `spawn` a second session instead —
the same agent, a conversation of its own, remembering nothing:

```python
first = await agent.spawn(env=workspace)
second = await agent.spawn(env=workspace)   # independent: neither knows the other
```

## Which CLIs can

| CLI | Forks | Into another directory |
| --- | --- | --- |
| Claude Code | yes | yes |
| Codex | yes | yes |
| Kimi Code | yes | yes |
| ZCode | yes | yes |
| Grok Build, opencode, MiMo Code, pi, Qwen Code, an ACP CLI | yes | no |
| cursor-agent, Antigravity, DeepSeek Harness | no | no |

A fork a CLI cannot make raises `UnsupportedOperation`, where it is asked for. It is not
answered with a second handle on the same conversation: two loops each continuing what they
take to be their own is a run nothing downstream could explain. A flow that wants to fork on
any CLI catches it, and spawns instead:

```python
from hmz.flows import UnsupportedOperation

try:
    other = await agent.fork(session, env=workspace)
except UnsupportedOperation:
    other = await agent.spawn(env=workspace)
```

## Not `derive`

The two are halves of one idea, which is why they are not one word:

| | |
| --- | --- |
| `agent.derive(...)` | the same **agent** under a narrower grant, which holds no conversation of its own |
| `agent.fork(session, env=...)` | another **conversation** of this one agent, which knows what this one knows |

An agent is structure, so deriving one narrows the structure and carries none of the history.
A session is history, so forking one copies the history and none of the structure. See
[Concepts › Agent](/user/concepts#agent).

## See also

- [Many conversations at once](/user/conversations)
- [Many turns at once](/weaver/async-flows), for driving both branches together
- [Worktrees, copies and scratch](/weaver/worktrees), for branching the files rather than the
  conversation
