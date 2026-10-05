<script setup>
import PersonTurn from '../.vitepress/theme/components/weaver-person/PersonTurn.vue'
</script>

# The person as an agent

In this guide you make the person running a flow one of its agents. You build `talk`, a
conversation where every line the person types is the next turn, then `settle`, which asks the
person a short questionnaire before an agent starts, and finally `scripted`, which stands in
for the person with code.

Reach for this when a decision in the flow belongs to a person: how to build something, whether
to go on, what to say next. It is not [steering](/user/steering): steering is you putting words
into an agent's turn, while an agent of this kind takes turns of its own.

::: info Before you start
- A flow of your own running: [Your first flow](/weaver/writing-a-flow).
- [Answers in a shape](/weaver/shapes), for the questionnaire.
- For the last example, [A flow that calls a flow](/weaver/calling-flows).
:::

## How it works

<PersonTurn />

An **outworlder** is whoever is outside the run: the person at the prompt, or whatever stands in
for them. A flow declares one as a role typed `Outworlder`, and drives it the way it drives a
coding agent: `spawn` a session, then `run` in it. `run` shows the person the prompt and
returns what they typed.

Three things set it apart from a coding agent:

- **Nobody picks what it runs.** humanize fills an `Outworlder` role itself, and `-a` never
  does. Naming it with `-a` is refused.
- **It can be away.** `human.away` says whether anybody is there to answer. A run of `hmz exec`
  is always away, since nobody is at a prompt, and so is a run in the interface while
  [`/afk`](/user/afk) is on for that role. An outworlder that is away answers at once, without
  asking anybody.
- **It runs no model and spends nothing.**

## Example: a conversation

`talk` is the shape of [`chat`](/flows/chat), the flow the interface opens on:

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

Give the person an [`output_schema`](/weaver/shapes), and they are asked **a question per
field** instead of being shown a schema. `settle` asks how to build something, then has the
builder build it that way:

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

1. **`Settled`** is the questionnaire. Each field is one question, and its `description` is the
   question's wording. Every field has a default, which is what the flow does when nobody is
   there to say.
2. **`human.run(…, output_schema=Settled)`** asks the fields one by one and returns a
   `Settled` built from the answers. What the model refuses is asked again on that field, with
   the model's own message.
3. **The answers steer the flow** as typed values, never by parsing a sentence.

At the prompt, the person sees:

<pre class="asking-tty" aria-label="The questionnaire at the prompt, drawn after the interface"><span class="said">●</span> How should I do this: add a subtract function to calc.py?

Which way should this be built? -- or `-` for careful
<span class="dim">      · fast
      · careful
   type an answer, or /afk to stop being asked</span>
<span class="you">❯</span> fast
<span class="said">●</span> Write tests for it? -- or `-` for yes
<span class="dim">      · yes
      · no
   type an answer, or /afk to stop being asked</span>
<span class="you">❯</span> -
</pre>
<p class="asking-tty-note">Drawn after the interface, not recorded. <code>settled</code> is
<code>Settled(approach='fast', tests=True)</code>.</p>

| In the model | What they are asked |
| --- | --- |
| `description=` | the question, or the field's name where there is none |
| `Literal[…]` | those words, offered as the answers |
| `bool` | `yes` or `no` |
| `int`, `float` | the question, with "(a number)" |
| `list[str]` | one line, "(several, separated by commas)" |
| a default | "-- or `-` for careful", and a dash takes the default |

Each question takes the road [a coding agent's own question](/user/questions) takes.

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

Turning `/afk` on while a question is up answers it as nobody. So does a person who keeps
typing what the model refuses.

## Stand in for the person

Sometimes a flow means to answer for the person itself: running `talk` with a script of lines,
or a supervisor that answers a callee's questions with a model of its own.
`Outworlder.new()` makes an outworlder the caller answers for, through `on_outworlder_run`:

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
   person was shown, and `params.output_schema`, the schema asked for or `None` for text.
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
answer, schema and all:

```python
async def answered(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
    thinking = await supervisor.spawn()
    if params.output_schema is None:
        said = await supervisor.run(params.prompt, session=thinking, env=workspace)
    else:
        said = await supervisor.run(
            params.prompt,
            session=thinking,
            env=workspace,
            output_schema=params.output_schema,
        )
    return OutworlderRunHookResult(output=said)
```

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
4. **`person.asked`** is every prompt put to the person.
5. **Away, the defaults decide**, exactly as in the real run above.
6. **The run's own person is never asked** when the stand-in answers for them.

## Variations

**Call a flow and leave the person out.** A flow calling one with an `Outworlder` role may leave
the role out, and the callee is handed the run's own: whoever is at the prompt, or nobody. It
may also pass on the outworlder it was handed, which is the same person.

```python
await talk(task, agents={"assistant": agents["assistant"]}, envs=envs, params=FlowParams())
```

**Unattended and attended alike.** Give every field of a questionnaire a default, and the same
flow runs from `hmz exec` or a CI job, deciding by its defaults, and asks when somebody is
there.

## Pitfalls

- **A field without a default** raises `OutworlderAway` when nobody is there. Catch it, or give
  the field a default, if the flow should run unattended.
- **`on_outworlder_run` only works on `Outworlder.new()`.** On the run's own outworlder it
  raises `CapabilityNotGranted`: the person at the prompt answers for themselves.
- **It reaches none of a CLI's moments.** `on_stop` and the rest are there, since every agent
  has them, but a hook hung on one is never called.
- **It cannot be forked, and carries no skills.** `fork` raises `UnsupportedOperation`, and
  `derive` with `skills=` raises `CapabilityNotGranted`.

## Next steps

- [You, as one of the agents](/features/human): the questionnaire, to click through
- [Questions](/user/questions) and [Being away (/afk)](/user/afk)
- [Answers in a shape](/weaver/shapes)
- [The agent asking the flow](/weaver/tools): questions an agent puts to the flow
- [Reference › `Outworlder`](/reference/flows#outworlder) and [The person at the
  prompt](/reference/flows#the-person-at-the-prompt)

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
