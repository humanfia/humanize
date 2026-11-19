<script setup>
import PersonTurn from '../.vitepress/theme/components/weaver-person/PersonTurn.vue'
</script>

# The person as an agent

In this guide you make the person running a flow one of its agents. You build `talk`, a
conversation where every line the person types is the next turn, then `settle`, which asks the
person one short form before an agent starts, and finally `scripted`, which stands in for the
person with code. On the way you show the person what they are deciding on: a diff, a table, a
chart.

Reach for this when a decision in the flow belongs to a person: how to build something, whether
to go on, what to say next. It is not [steering](/user/steering): steering is you putting words
into an agent's turn, while an agent of this kind takes turns of its own.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- [Answers in a shape](/weaver/shapes), for the form.
- For the last example, [A flow that calls a flow](/weaver/calling-flows).
:::

## How it works

<PersonTurn />

An **outworlder** is whoever is outside the run: the person at the prompt, or whatever stands in
for them. A flow declares one as a role typed `Outworlder`, and drives it the way it drives a
coding agent: `spawn` a session, then `run` in it. `run` shows the person the prompt, and
anything you pass as `context` with it, and returns their answer: what they typed, or a value of
the `output_schema` you asked for.

Whoever answers, a person in the web page, a person at the prompt, a calling flow or a program,
gets the same question: a prompt, its context and, for a shape, its JSON Schema. Every answer
is checked against the schema in one place before the flow sees it.

Three things set it apart from a coding agent:

- **Nobody picks what it runs.** Humanize fills an `Outworlder` role itself, and `-a` never
  does. Naming it with `-a` is refused.
- **It can be away.** `human.away` says whether anybody is there to answer. A run of `hmz exec`
  is always away, since nobody is at a prompt, and so is a run in the interface while
  [`/afk`](/user/afk) is on for that role. An outworlder that is away answers at once, without
  asking anybody.
- **It runs no model and spends nothing.**

## Example: a conversation

`talk` is one person and one agent taking turns, written as a flow. It is not a
[chat](/user/chat), which the interface opens on: a chat is a session of its own, no epic, with no
flow and no outworlder, and takes the agent's own `/` commands and skills. A flow like `talk`
is for when the conversation needs a budget, params, or code between its turns; each line you
type in it answers the outworlder's question.

```python
# .hmz/flows/talk/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Agents(AgentCollection):
    assistant: Agent
    human: Outworlder  # ①


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def talk(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> int:
    """One conversation, and every line the person types is a turn of it."""
    assistant, human = agents["assistant"], agents["human"]
    workspace = envs["workspace"]
    conversation = await assistant.spawn()
    listening = await human.spawn()  # ②
    said, turns = task, 0
    while said:  # ③
        answered = await assistant.run(said, session=conversation, env=workspace)
        turns += 1
        said = await human.run(answered, session=listening)  # ④
    print(f"talk: {turns} turns, away={human.away}")  # ⑤
    return turns
```

### What each part does

1. **`human: Outworlder`** declares the person as a role. The runtime fills it with whoever
   started the run.
2. **`human.spawn()`** opens the person's session, as for any agent. It is where their turns
   are recorded.
3. **`while said:`** ends the conversation when the person answers with nothing. An empty line,
   or being away, is how they say they are done.
4. **`human.run(answered, …)`** shows the person what the assistant said and waits for what
   they type, which becomes the assistant's next prompt.
5. **`human.away`** is `True` when nobody is there to answer. The flow prints it to show which
   case it ran in.

### Run it

At the prompt, `$@local/talk Read calc.py and tell me in one sentence what it is.` runs it with
you as `human`: every line you type goes to the assistant, and an empty line ends it.

From a command line, nobody is at a prompt, so the person is away. Name the assistant only:

```sh
hmz exec -f talk -a assistant=claude/claude-sonnet-5-5:low -p budget.cost=1 \
    "Read calc.py and tell me in one sentence what it is."
```

```text
● assistant is working
● Read(/home/you/calc/calc.py)
● `calc.py` is a tiny module that defines a single `add(a, b)` function, which returns the sum of its two arguments.
✻ input 4 · output 104 · cache_read 27.8k · cache_write 5.3k · $0.02 · claude-sonnet-5-5 · assistant
`calc.py` is a tiny module that defines a single `add(a, b)` function, which returns the sum of its two arguments.
✻ Worked for 3s · assistant
talk: 1 turns, away=True
```

The away person answered `""` at once, so `talk` took one turn and ended: it did the one thing
it was given. Naming the person is refused before anything runs:

```sh
hmz exec -f talk -a assistant=claude/claude-sonnet-5-5:low,human=claude/claude-sonnet-5-5:low \
    -p budget.cost=1 "hello"
```

```text
hmz exec: error: talk: 'human' is assigned automatically by the runtime and cannot be set with -a
```

## Example: ask for a shape

Give the person an [`output_schema`](/weaver/shapes), and they are asked the whole of it at
once, as one form drawn from the model, never a field at a time. `settle` asks how to build
something, then has the builder build it that way:

```python
# .hmz/flows/settle/__init__.py
from typing import Literal

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Settled(BaseModel):  # ①
    approach: Literal["fast", "careful"] = Field(
        default="careful", description="Which way should this be built?"
    )
    tests: bool = Field(default=True, description="Write tests for it?")


class Agents(AgentCollection):
    builder: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def settle(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """Ask the person how to build it, then have the builder build it that way."""
    builder, human = agents["builder"], agents["human"]
    workspace = envs["workspace"]
    listening = await human.spawn()
    settled = await human.run(  # ②
        f"How should I do this: {task}?", session=listening, output_schema=Settled
    )
    print(f"settled: {settled!r}")
    prompt = f"{task}\n\nBuild it the {settled.approach} way."  # ③
    prompt += " Write tests for it." if settled.tests else " Write no tests."
    session = await builder.spawn()
    return await builder.run(prompt, session=session, env=workspace)
```

1. **`Settled`** is the form. Each field is one input, and its `description` is the input's
   label. Every field has a default, which is what the form suggests and what the flow does
   when nobody is there to say.
2. **`human.run(…, output_schema=Settled)`** asks the whole form at once and returns a
   `Settled`. An answer the model refuses never reaches the flow: the person is shown why,
   beside the field, and answers again.
3. **The answers steer the flow** as typed values, never by parsing a sentence.

### What the person sees

In the [web page](/user/web), the question is one card under the graph: the prompt as its
headline, then the form, then **Send answer**.

<pre class="asking-tty" aria-label="The form in the web page, drawn after the interface"><span class="said">How should I do this: add a subtract function to calc.py?</span>

Approach  <span class="dim">suggested</span>
<span class="you">[&nbsp;1&nbsp;fast&nbsp;]  [&nbsp;2&nbsp;careful&nbsp;•&nbsp;]</span>
<span class="dim">Which way should this be built?</span>

Tests  <span class="dim">suggested</span>
<span class="you">[&nbsp;Yes,&nbsp;tests&nbsp;•&nbsp;]  [&nbsp;No&nbsp;]</span>
<span class="dim">Write tests for it?</span>

<span class="you">[&nbsp;Send&nbsp;answer&nbsp;]</span>  <span class="dim">Ctrl+↵</span>
</pre>
<p class="asking-tty-note">Drawn after the web page, not recorded. Pressing <strong>fast</strong>,
then <strong>Send answer</strong>, makes <code>settled</code>
<code>Settled(approach='fast', tests=True)</code>.</p>

The defaults are already picked and marked `suggested`, so a person who agrees presses
**Send answer**, or <kbd>⌘</kbd>/<kbd>Ctrl</kbd>+<kbd>Enter</kbd>, and is done. At the prompt
in a terminal, the same question is a line in the transcript, `form · 2 fields — press Enter to
open`, and <kbd>enter</kbd> opens the same form as a sheet. See [Questions](/user/questions).

| In the model | What they get on the page | At the prompt |
| --- | --- | --- |
| `description=` | the hint under the field's title | the same |
| `Literal[…]`, an `Enum` | up to five values: a row of large buttons; more: a list to search | side by side, picked by number; more: a list |
| `bool` | two buttons worded from the description, or the title where it is a question, as `Yes, tests` and `No`; never a bare checkbox | two, `Yes, <description>` and `No` |
| `int`, `float` | a number field | a number |
| `str` | a text field | a line, or several for Markdown or code |
| `list[…]` | a row per item, with add and remove | one per line for words and numbers, else JSON |
| a nested model | its fields, grouped under its name | JSON |
| a default | prefilled and marked `suggested`; required fields come first | the same, folded under **More options** |

A field that does not fit, a word where a number goes, is said beside the field when the
person leaves it or presses **Send answer**, never while they type. Every answer goes through the
same check, the one the host makes, whoever answers it.

Run from a command line, the person is away and the defaults decide. A real run:

```sh
hmz exec -f settle -a builder=claude/claude-sonnet-5-5:low -p budget.cost=1 \
    "add a subtract function to calc.py"
```

```text
● builder is working
● Bash(cd /home/you/calc && ls && cat calc.py && cat check.py; ls test* 2>/dev/null)
● Bash(cd /home/you/calc && cat >> calc.py <<'EOF' …)
● I added `subtract(a, b)` to `calc.py`, which returns `a - b`, and put its tests in a new `test_calc.py`. …
✻ input 6 · output 800 · cache_read 45.9k · cache_write 4.8k · $0.03 · claude-sonnet-5-5 · builder
settled: Settled(approach='careful', tests=True)
…
✻ Worked for 8s · builder
```

`settled:` shows the defaults, and the builder wrote tests because `tests` defaulted to `True`.
The line lands among the builder's, because a flow's output is not held back for a turn.

### What an away person answers

| Asked for | Answers |
| --- | --- |
| text | `""` |
| an `output_schema` whose fields all have defaults | the model built from its defaults |
| an `output_schema` with a field that has none | raises `OutworlderAway` |

Turning `/afk` on while a question is up answers it as nobody.

## Show them what they decide on {#context}

A question rarely stands alone: the person approves a diff, picks from a table, reads a plan.
Hand it over as `context`, and it is drawn under the prompt and above the form:

```python
from hmz.flows import Diff, Markdown, Table

_, patch, _ = await workspace.exec(["git", "diff"])  # ①
review = await human.run(
    "Ship this?",
    session=listening,
    output_schema=Review,
    context=[  # ②
        Markdown(text="The builder says **all checks pass**."),
        Diff(patch=patch, title="The change"),
        Table(columns=("check", "result"), rows=(("check.py", "ok"),), title="Checks"),
    ],
)
await human.show([Markdown(text="Thanks. The builder is on it.")], session=listening)  # ③
```

1. **`workspace.exec`** needs `ShellEnvMixin` on the role. See
   [What an environment can do](/reference/flows#what-an-environment-can-do).
2. **`context=[…]`** is a list of blocks, drawn in order. Each long one is folded behind a line
   that sums it up, `+12 −3 in 2 files` or `table · 40 rows`, and the first is open.
3. **`human.show(…)`** puts blocks in front of the person with nothing to answer: progress, a
   result, a chart. It returns at once, and does nothing while the person is away.

| Block | Shows |
| --- | --- |
| `Markdown(text=…)` | formatted text |
| `Code(text=…, language="")` | code, highlighted |
| `Diff(patch=…)` | a unified diff, file by file |
| `Table(columns=…, rows=…)` | a table |
| `Image(data=…, mime=…, alt="")` | a picture, up to 4 MiB |
| `Json(value=…)` | any JSON value, as a tree to open |
| `Chart(spec=…)` | a [Vega-Lite](https://vega.github.io/vega-lite/) chart |

Every block takes a `title=`. At the prompt in a terminal, text, code, diffs and tables are
drawn in the transcript, and an image or a chart is a line pointing to the web page. Context
works with text questions too: `human.run("Anything to add?", session=…, context=[…])`.

For a decision the form does not serve well, give the session a [face](/weaver/faces): your
own HTML, handed the same prompt, context and schema.

## Stand in for the person

Sometimes code means to answer for the person: a flow running `talk` with a script of lines, a
supervisor that answers a callee's questions with a model of its own, a program driving a run
from outside. Each is a **caller**, and each gets exactly what a person gets: the prompt, its
context, and the schema to answer in.

### From a calling flow

`Outworlder.new()` makes an outworlder the calling flow answers for, through
`on_outworlder_run`:

```python
# .hmz/flows/scripted/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
    flow,
    load,
)

talk = load("talk")  # ①


class Agents(AgentCollection):
    assistant: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def scripted(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> int:
    """Run talk, with the person's lines typed from a script."""
    lines = iter(["Now in one word.", ""])  # ②

    async def typed(params: OutworlderRunHookParams) -> OutworlderRunHookResult:  # ③
        print(f"  the assistant said: {params.prompt[:60]}")
        return OutworlderRunHookResult(output=next(lines, ""))

    stand_in = Outworlder.new()  # ④
    stand_in.on_outworlder_run(typed)  # ⑤
    return await talk(  # ⑥
        task,
        agents={"assistant": agents["assistant"], "human": stand_in},
        envs=envs,
        params=FlowParams(),
    )
```

1. **`load("talk")`** is the `talk` flow beside this one, ready to call.
2. **The script** is what the person would type: one follow-up, then an empty line to end.
3. **`typed`** is an `on_outworlder_run` hook. It is called with `params.prompt`, what the
   person would have been shown, `params.output_schema`, the schema asked for or `None` for
   text, `params.context`, the blocks passed with it, and `params.face`, the session's
   [face](/weaver/faces) or `None`.
4. **`Outworlder.new()`** makes an outworlder for this flow to answer for. Until a hook is hung
   on it, it is away.
5. **`on_outworlder_run(typed)`** makes every `run` of it call `typed`. The hook answers with
   `output`: text, or an instance of the schema it was asked for.
6. **`talk` is handed the stand-in** as its `human`, and cannot tell it from a person.

```sh
hmz exec -f scripted -a assistant=claude/claude-sonnet-5-5:low -p budget.cost=1 \
    "Read calc.py and tell me in one sentence what it is."
```

```text
● assistant is working
● Read(/home/you/calc/calc.py)
● `calc.py` is a tiny calculator module that defines two functions, `add(a, b)` and `subtract(a, b)`.
✻ input 4 · output 106 · cache_read 29.2k · cache_write 4.0k · $0.02 · claude-sonnet-5-5 · assistant
…
✻ Worked for 4s · assistant
● assistant is working
● Calculator.
✻ input 2 · output 7 · cache_read 16.7k · cache_write 77 · $0.0036 · claude-sonnet-5-5 · assistant
  the assistant said: `calc.py` is a tiny calculator module that defines two funct
…
  the assistant said: Calculator.
talk: 2 turns, away=False
```

The script's first line became the second turn, and its empty line ended `talk`, which reports
the stand-in as not away.

The hook runs as the flow that hung it, so it may take a turn of one of the caller's agents to
answer, context, schema and all:

```python
import json


async def answered(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
    seen = [json.dumps(block.as_json()) for block in params.context]  # ①
    prompt = "\n\n".join([params.prompt, *seen])
    thinking = await supervisor.spawn()
    if params.output_schema is None:
        said = await supervisor.run(prompt, session=thinking, env=workspace)
    else:
        said = await supervisor.run(
            prompt,
            session=thinking,
            env=workspace,
            output_schema=params.output_schema,  # ②
        )
    return OutworlderRunHookResult(output=said)
```

1. **`block.as_json()`** is a block as the web page and a program receive it, here put in the
   supervisor's prompt.
2. **The same schema** the person would have filled in. The supervisor answers it as a whole.

`show` on an outworlder made with `Outworlder.new()` does nothing: there is nobody to show.

### From a program {#from-a-program}

A program running a flow through the [SDK](/reference/sdk#outworlderdriver) answers its
`Outworlder` roles with a driver: an object with `away_for` and `run`. `run` is handed an `Ask`,
the question as the web page receives it, and answers with text, or with a mapping for a
schema:

```python
# answer.py
from typing import Any

from hmz.sdk import Ask, Hmz


class Reviewer:
    def away_for(self, role: str) -> bool:  # ①
        return False

    async def run(self, ask: Ask, role: str) -> str | dict[str, Any]:  # ②
        print(f"{role} asked: {ask.prompt}")
        if ask.schema is None:
            return "looks good"
        if ask.errors:  # ③
            print(f"  refused: {ask.errors[0]['message']}")
        return {"approach": "fast", "tests": False}

    def show(self, context: tuple[dict[str, Any], ...], session: str, role: str) -> None:  # ④
        print(f"{role} was shown {[block['kind'] for block in context]}")


run = Hmz().run(
    "settle",
    "add a subtract function to calc.py",
    agents={"builder": "claude/claude-sonnet-5-5:low"},
    budget={"cost": 1},
    outworlder=Reviewer(),
)
print(run.run())
```

1. **`away_for(role)`** says whether to set that role away. An away role is never asked.
2. **`run(ask, role)`** is every question of that role: `ask.prompt`, `ask.context` (blocks as
   JSON), `ask.schema` (a JSON Schema, or `None` for text), `ask.face` (a face's hash, or `""`)
   and `ask.session` (`<role>/<n>`, the same for every question of one outworlder session).
3. **`ask.errors`** is set when the last answer did not fit: the same question comes back with
   each error's `path` and `message`, up to twice more. If the third answer does not fit
   either, the question is answered as nobody's, as it is when `run` raises or returns `""`.
4. **`show`** is optional. Leave it out and what the flow shows is not handed to the program.
   A program is never handed a face: `ask.face` is its hash, and the schema is what to answer.

## Check it worked

The fake kit scripts the person: give the `Outworlder` role a list of replies as though it
were an agent, or pass a `FakeOutworlder` as `outworlder=`. Left out, the person is away, as
under `hmz exec`:

```python
# tests/test_person.py
from hmz.sdk import fakes


async def test_talk_goes_on_until_the_person_says_nothing() -> None:
    assistant = fakes.FakeAgentDriver()

    turns = await fakes.run_fake(
        "talk",
        "hello",
        agents={"assistant": assistant, "human": ["more", "done", ""]},  # ①
    )

    assert turns == 3
    assert assistant.prompts == ["hello", "more", "done"]


async def test_talk_takes_one_turn_when_nobody_is_there() -> None:
    turns = await fakes.run_fake("talk", "hello")  # ②

    assert turns == 1


async def test_the_person_settles_how() -> None:
    person = fakes.FakeOutworlder({"approach": "fast", "tests": False})  # ③
    builder = fakes.FakeAgentDriver()

    await fakes.run_fake(
        "settle", "add subtract", agents={"builder": builder}, outworlder=person
    )

    assert person.asked == ["How should I do this: add subtract?"]  # ④
    assert person.asks[0].schema["properties"].keys() == {"approach", "tests"}
    assert builder.prompts == [
        "add subtract\n\nBuild it the fast way. Write no tests."
    ]


async def test_away_means_the_defaults() -> None:
    builder = fakes.FakeAgentDriver()

    await fakes.run_fake("settle", "add subtract", agents={"builder": builder})  # ⑤

    assert builder.prompts == [
        "add subtract\n\nBuild it the careful way. Write tests for it."
    ]


async def test_the_script_stands_in_for_the_person() -> None:
    assistant = fakes.FakeAgentDriver()
    person = fakes.FakeOutworlder()

    turns = await fakes.run_fake(
        "scripted", "hello", agents={"assistant": assistant}, outworlder=person
    )

    assert turns == 2
    assert assistant.prompts == ["hello", "Now in one word."]
    assert person.asked == []  # ⑥
```

```text
.....                                                                    [100%]
5 passed in 0.11s
```

1. **A list for the `human` role** is the person's lines, turn by turn. The `""` at the end is
   what ends `talk`. Without it, the person would answer `"ok"` from then on.
2. **No person given** is a person who is away, so `talk` takes one turn.
3. **`FakeOutworlder(reply)`** answers from a script, here a mapping read into `Settled`.
4. **`person.asked`** is every prompt put to the person, and **`person.asks`** every question
   whole, each an `Ask`: its `prompt`, the `schema` it was asked in, its `context` and `face`.
   **`person.shown`** is what the flow showed with nothing to answer, as `(session, context)`.
5. **Away, the defaults decide**, exactly as in the real run above.
6. **The run's own person is never asked** when the stand-in answers for them.

## Variations

**Call a flow and leave the person out.** A flow calling one with an `Outworlder` role may leave
the role out, and the callee is handed the run's own: whoever is at the prompt, or nobody. It
may also pass on the outworlder it was handed, which is the same person.

```python
await talk(task, agents={"assistant": agents["assistant"]}, envs=envs, params=FlowParams())
```

**Unattended and attended alike.** Give every field of a form a default, and the same flow
runs from `hmz exec` or a CI job, deciding by its defaults, and asks when somebody is there.

**A screen of its own.** Spawn the session with a [face](/weaver/faces), `human.spawn(face=…)`,
and the web page draws the question with your HTML instead of the form.

## Pitfalls

- **A field without a default** raises `OutworlderAway` when nobody is there. Catch it, or give
  the field a default, if the flow should run unattended.
- **`on_outworlder_run` only works on `Outworlder.new()`.** On the run's own outworlder it
  raises `CapabilityNotGranted`: the person at the prompt answers for themselves.
- **One form, not many questions.** Asking for each field with its own `run` makes the person
  wait between them and lose sight of the whole. Ask one model, and let the form group it.
- **`show` is not a question.** Nothing waits for the person to read it, and nobody sees it
  while they are away. Ask with `context` when the flow must wait.
- **It reaches none of a CLI's moments.** `on_stop` and the rest are there, since every agent
  has them, but a hook hung on one is never called.
- **It cannot be forked, and carries no skills.** `fork` raises `UnsupportedOperation`, and
  `derive` with `skills=` raises `CapabilityNotGranted`.

## Next steps

- [You, as one of the agents](/features/human): the form, to click through
- [A face for the person](/weaver/faces): your own HTML for a question
- [Questions](/user/questions) and [Being away (/afk)](/user/afk)
- [Answers in a shape](/weaver/shapes)
- [The agent asking the flow](/weaver/tools): questions an agent puts to the flow
- [Reference › `Outworlder`](/reference/flows#outworlder),
  [context blocks](/reference/flows#context-blocks) and
  [SDK › `OutworlderDriver`](/reference/sdk#outworlderdriver)

<style scoped>
.asking-tty {
  margin: 16px 0 4px;
  padding: 14px 18px;
  border-radius: 12px;
  border: 1px solid var(--hmz-panel-border);
  background: var(--vp-code-block-bg);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.asking-tty .said {
  color: var(--vp-c-warning-1);
}

.asking-tty .you {
  color: var(--vp-c-brand-1);
}

.asking-tty .dim {
  color: var(--vp-c-text-3);
}

.asking-tty-note {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--vp-c-text-3);
}
</style>
