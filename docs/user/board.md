# The mission board

Asking somebody something **stops the turn**: the agent says what it wants, and nothing happens
until an answer comes back. That is right for a question and wrong for everything else a run
needs from you — what there is to do next, how far through it is, the thing you thought of
while it was running.

The board was the other shape: a handful of named lines, kept beside the run and shown on
[`/monitor`](/user/monitor), that the flow and you both wrote on and **neither waited at**.

::: warning The flow API has no board
A flow written against `hmz.flows` has no way to read or write the board: the
[outworlder](/weaver/human-agent) it talks to you through takes turns, and a turn is a question.
So a run of such a flow has nothing of the flow's on the board, and nothing you put there reaches
the flow. What is below is what is left: the board on `/monitor`, and the same board from Python
for a person-shaped agent you drive yourself.
:::

## A queue a flow does read

What the board was for is still a small thing to build, and the flow API's own way is a file.
A flow whose [environment](/reference/flows#where-each-agent-works) it may read reads a list
between rounds — `TODO.md`, one thing a line — and you add a line to it while the loop is working
through the first; the next round picks it up, and nothing was interrupted and nothing waited.

```python
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Workspace(LocalEnv, FilesEnvMixin): ...


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def todo(task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext):
    """Works through TODO.md a line at a time, however long it gets."""
    builder, workspace = agents["builder"], envs["workspace"]
    while lines := (await workspace.read("TODO.md")).decode().split("\n"):
        first = next((one for one in lines if one.strip()), None)
        if first is None:
            return
        session = await builder.spawn(env=workspace)
        await builder.run(first, session=session)
        now = (await workspace.read("TODO.md")).decode().split("\n")
        await workspace.write("TODO.md", "\n".join(one for one in now if one != first).encode())
```

## From the prompt

Where a run has a board it is drawn under the diagram on `/monitor`, beside how far through the
run is, rather than behind a command of its own:

```
  Board · what you and the flow both write on
    ◈ todo          write the parser
    ◈ doing         write the parser · flow's

      add           a line
```

| key | |
| --- | --- |
| `a` | put a line up: type a name, enter, then what it says. The `add` row below the lines does the same |
| enter | change the line under the cursor |
| `d` twice | take it off the board |

The board is the one place taking something away is still a key pressed twice. Everywhere else
in the interface a row opens onto a menu about itself, and being rid of it is a row in there;
enter on a line of the board opens the words of that line, which has no room for one. And it
lands the moment it is pressed — there is no menu to save and no walk out to change your mind on
— so the first press says what the second will do, and moving the cursor puts it down again.

## From Python

The board belongs to coganchor's person-shaped agent, `HumanAgent`, and is there for whoever
drives one of those themselves:

```python
from hmz.coganchor.agents import HumanAgent

board = HumanAgent().board

board.put("todo", "fix the build")           # write one, making it if it is not there
board.put("notes", "", about="what to know", whose="flow")
board.get("todo")                            # what it says now, or ""
board.get("nothing", "-")                    # what to answer when there is no such line
board.held("todo")                           # the whole Item, or None
board.items()                                # every line, in the order they went up
board.drop("todo")                           # take one off
board.moves("todo", to="done")               # rename it, keeping everything else
board.watch(lambda one: ...)                 # told whenever a line moves
```

An `Item` is `key`, `value`, `about`, `whose`, `at` — a monotonic moment, so a reader can tell a
line that moved from one that came back the same — and `by`, which is the side that wrote what
it says now. Writing a value keeps what the line is *for*: `about` is said once. A line says
whose it is — `"both"`, `"user"` or `"flow"` — and the other side is **refused where it
writes**, with a `Refused`.

Everything is under one lock and what is read out is a copy, so a reader reading the board while
somebody types on it reads one moment of it rather than four moments of four lines.

## See also

- [Watching a run](/user/monitor) — where the board is drawn
- [Questions](/user/questions) — the half that does stop the turn
- [The person as an agent](/weaver/human-agent)
