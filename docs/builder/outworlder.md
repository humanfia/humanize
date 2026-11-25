---
title: The person as an agent
description: Give a flow a role that a person fills, ask it questions as text or as a form, show it diffs and tables, handle nobody being there, and answer for it from another flow.
---

# The person as an agent

An `Outworlder` role represents the person running the flow. Your flow gives this role turns like any agent: each turn asks a question, and `run` returns the person's answer.

![A turn of an outworlder is one ask of prompt, context and schema, answered by a person, by nobody, by a hook of the calling flow or by an SDK driver](/diagrams/builder-outworlder-1.svg)

## Declare the role

Type a role as `Outworlder` in the flow's `AgentCollection`. Humanize fills it automatically; naming it with `-a` is an error.

```python
# .hmz/flows/approve/__init__.py
"""Approve: an agent does the task, and a person decides whether to keep it."""

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    Diff,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Markdown,
    Outworlder,
    ShellEnvMixin,
    Table,
    flow,
)


class Review(BaseModel):
    keep: bool = Field(False, description="Keep the change.")
    notes: str = Field("", description="What to change, if anything.")


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def approve(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """An agent does the task, and a person decides whether to keep it."""
    coder, human = agents["coder"], agents["human"]
    workspace = envs["workspace"]
    work = await coder.spawn()
    asking = await human.spawn()
    said = await coder.run(task, session=work, env=workspace)
    await human.show(
        (Markdown(text="The coder is done. Running the checks."),), session=asking
    )
    _, patch, _ = await workspace.exec(["git", "diff"])
    code, _, _ = await workspace.exec(["python", "-m", "compileall", "-q", "."])
    review = await human.run(
        "Keep this change?",
        session=asking,
        output_schema=Review,
        context=(
            Markdown(title="What the coder says", text=said),
            Diff(patch=patch),
            Table(
                title="Checks",
                columns=("check", "result"),
                rows=(("compiles", "yes" if code == 0 else "no"),),
            ),
        ),
    )
    if review.keep:
        title = await human.run("What should the commit say?", session=asking)
        await coder.run(f"Commit the change as: {title or task}", session=work, env=workspace)
    else:
        await coder.run(f"Undo the change. {review.notes}", session=work, env=workspace)
    return review.keep
```

You can declare multiple `Outworlder` roles, such as `author` and `approver`. Each role is asked, claimed, and set away by its own name.

## Ask a question

Call `spawn` to open a session, then call `run` to ask a question. A session groups its questions into one conversation.

| Call | The person gets | `run` returns |
| --- | --- | --- |
| `await human.run("What should the commit say?", session=asking)` | A box to type in | The text, a `str` |
| `await human.run("Keep this change?", session=asking, output_schema=Review)` | One form with every field of `Review` | A `Review` |

Humanize presents a schema as a single form, never one field at a time. Field types, defaults, and descriptions determine the form controls; see [Typed answers](/builder/shapes).

![The question card of the approve flow: Keep this change?, three context blocks, a Keep choice marked Suggested, a Notes box and Send answer](/shots/builder-outworlder-card.svg)

The daemon validates answers against the model. Invalid answers are rejected with field errors, keeping the question open until the answer fits. While a question waits, the epic status is `waiting`.

Pass `spawn(face=...)` to replace the standard form with a custom HTML page; see [Faces](/builder/faces).

## Show context and messages

Pass a sequence of blocks to `context` in `run` to display them in order beneath the prompt. Context blocks work with both text questions and forms.

| Block | Fields | Drawn as |
| --- | --- | --- |
| `Markdown` | `text` | Formatted text |
| `Code` | `text`, `language=""` | Highlighted source |
| `Diff` | `patch` | A unified diff, file by file; it may span files |
| `Table` | `columns`, `rows` | A table; a row that is not as wide as `columns` raises `ValueError` |
| `Image` | `data`, `mime`, `alt=""` | A picture; at most 4 MiB, and `mime` must start with `image/`, else `ValueError` |
| `Json` | `value` | A tree that folds |
| `Chart` | `spec` | A Vega-Lite chart; put its data inline in `data.values` |

Every block accepts `title=""`. All fields are keyword-only.

Call `show` with the same blocks to send a message without asking a question:

```python
await human.show((Markdown(text="The coder is done. Running the checks."),), session=asking)
```

`show` records the blocks in the epic history and returns immediately without waiting.

![The person's log in the app: a line reading shown to human, with the note The coder is done. Running the checks.](/shots/builder-outworlder-shown.svg)

*Click the person in the app's graph to view messages sent with `show`.*

## See the question

Start the flow in the app or `hmz` to see questions appear as the flow runs. See [Answer a flow's questions](/user/questions) for how to respond.

### In the app

![Humanize Desktop with the approve epic waiting: the graph shows the coder and the person, and the card under it asks Keep this change?](/shots/builder-outworlder-asked.svg)

### In the terminal

![The terminal interface with the same question: the coder's note, the diff, the Checks table and the line saying it is a form of 2 fields that Enter opens](/shots/builder-outworlder-terminal.svg)

## Handle nobody being there

Check `human.away` to see if no person is present to answer. This state can change during a run. A role is away when the epic runs via `hmz exec`, when the person enables `/afk` in the terminal or clicks **Away** on the **People** tab, or when the run starts from the SDK without an outworlder driver or from `run_fake` without `outworlder`.

When the role is away, `run` returns immediately:

| Asked for | `run` |
| --- | --- |
| Text | Returns `""` |
| A model whose every field has a default | Returns the model built from its defaults |
| A model with a field that has no default, or whose defaults fail its own validators | Raises `OutworlderAway` |

While the role is away, `show` does nothing. If the person goes away while a question is open, Humanize withdraws the question and resolves `run` using the table above.

Give every field a safe default for unattended runs. In `approve`, `keep` defaults to `False`, so an unattended run undoes the change:

```sh
hmz exec -f approve -a coder=claude/claude-haiku-4-5 -p budget.duration=10m "Add a discount code"
```

![hmz exec of the approve flow: the coder works, nobody is asked, and the coder's second turn says Undid the change](/shots/builder-outworlder-exec-away.svg)

To handle away states yourself, check `human.away` before asking or catch `OutworlderAway`.

### Claims

A person can claim a role so only their window or terminal can answer it. Claims are invisible to the flow. Any attached interface can answer an unclaimed role, and the first answer wins.

## Answer from another flow

When your flow calls another flow, you control who fills the callee's `Outworlder` role:

| The caller passes | The callee's questions go to |
| --- | --- |
| Nothing for that role | The epic's own person |
| Its own outworlder | The same person |
| `Outworlder.new()` | A hook of the caller |

Call `Outworlder.new()` to create an outworlder that the caller answers, then attach a hook with `on_outworlder_run`. Every `run` calls the hook. Until you attach a hook, the outworlder is away.

The hook receives `OutworlderRunHookParams`:

| Field | Holds |
| --- | --- |
| `prompt` | What was asked |
| `output_schema` | The model to answer with, or `None` for text |
| `context` | The blocks passed with the question |
| `face` | The face the session was spawned with, or `None` |

Like every hook, it also gets `ctx` and `session`. Return `OutworlderRunHookResult(output=...)` with text or a model instance. An invalid `output` raises `OutputSchemaError` in the callee.

This flow calls `approve` and uses a second agent to answer the form:

```python
# .hmz/flows/judged/__init__.py
"""Judged: run approve, with an agent answering in the person's place."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Diff,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
    ShellEnvMixin,
    flow,
    load,
)

approve = load("approve")


class Agents(AgentCollection):
    coder: Agent
    judge: Agent


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def judged(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """Run approve, with an agent answering in the person's place."""
    judge = agents["judge"]
    judging = await judge.spawn()

    async def answer(asked: OutworlderRunHookParams) -> OutworlderRunHookResult:
        if asked.output_schema is None:
            return OutworlderRunHookResult(output="")
        patch = "".join(b.patch for b in asked.context if isinstance(b, Diff))
        verdict = await judge.run(
            f"{asked.prompt}\n\n{patch}",
            session=judging,
            env=envs["workspace"],
            output_schema=asked.output_schema,
        )
        return OutworlderRunHookResult(output=verdict)

    stand_in = Outworlder.new()
    stand_in.on_outworlder_run(answer)
    return await approve(
        task,
        agents={"coder": agents["coder"], "human": stand_in},
        envs=envs,
        params=FlowParams(),
    )
```

```sh
hmz exec -f judged -a coder=claude/claude-haiku-4-5 -a judge=claude/claude-haiku-4-5 \
    -p budget.duration=10m "Add a discount code"
```

![hmz exec of the judged flow: the coder works, the judge answers keep true as JSON, and the coder commits the change](/shots/builder-outworlder-exec-judged.svg)

Even under `hmz exec`, where the epic's person is away, the judge answers the form. See [Call another flow](/builder/calling-flows) for `load` and flow calling.

## Test and drive from code

In tests, script the person's responses with `FakeOutworlder` (`from hmz.sdk import fakes`): `fakes.run_fake("approve", ..., outworlder=fakes.FakeOutworlder(reply=[{"keep": True}, "Add discount codes"]))`. See [Test a flow](/builder/testing).

Pass an outworlder driver to `Hmz().run(..., outworlder=...)` to receive each question as an `Ask` and return the answer from Python. See [The Python SDK](/builder/sdk). Both receive the same prompt, context, and schema as a person.

## Good to know

- An outworlder is distinct from steering: steering injects text into an agent's turn, while an outworlder takes its own turns.
- `run` accepts `env` and ignores it. Calling `fork` on an outworlder raises `UnsupportedOperation`, and calling `derive` with skills raises `CapabilityNotGranted`. Calling `show` with another agent's session raises `SessionError`. Agent hooks such as `on_stop` can be attached to an outworlder but are never called.
- `on_outworlder_run` works only on an `Outworlder.new()` instance; calling it on the epic's own outworlder raises `CapabilityNotGranted`. `show` does nothing on an `Outworlder.new()` instance.
- A caller can pass an outworlder to a callee role typed as a plain `Agent`, but roles with a mixin or harness reject it with `CapabilityMissing`. An agent passed for an `Outworlder` role is rejected the same way.
- The context of one `run` or `show` may come to at most 16 MiB as JSON, else `ValueError`. Text passed as `context` in place of a sequence of blocks raises `TypeError`.
- In the terminal, image and chart blocks render as a single line linking to the web page.
