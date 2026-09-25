---
pageClass: hmz-feature
---

# You, as one of the agents

A flow can drive the person at the prompt the way it drives a model: ask them something, wait
for the answer, and carry on. The person is a role a weaver declares in the flow — typed
`Outworlder`, whoever is outside the run — and given a [shape](/features/shapes) they are asked a
question per field, out of which the model is built.

```python
class Agents(AgentCollection):
    builder: Agent
    human: Outworlder
```

<HmzPerson />

## The person is handed over, not chosen

They are filled in by the runtime rather than by whoever runs the flow — nobody chooses what
the person runs, and `-a human=…` is refused. A flow that talks to a person is a flow with one
fewer agent to pick. A flow calling another that declares one hands it its own, or leaves the
role out and the called flow gets the run's.

They are driven like any agent — `spawn` a session, `run` a prompt in it — but their turn is not
a turn of a model, and is not bracketed by the moments a model's turn passes through: counting
it would put them in the graph of who handed to whom and spin a clock at them while they
thought.

## A schema is not a question

Shown a JSON Schema, a person is being asked to be a parser. So they are asked a question per
field instead, and the field is what makes the question:

| In the model | What they are asked |
| --- | --- |
| the line the field was declared with | the question itself, or the field's name where it has none |
| a fixed few possibilities | those words, as the answers it offers |
| a true-or-false | yes and no |
| a default | "or a dash for that" — and a dash takes it |
| a list | one line, separated by commas |

**What the model refuses is put back on the field it was refused for, in the model's own
words** — the flow that declared the field is the only thing that knows what it will take. It
is put back a bounded number of times: a person who keeps typing something the model will not
accept ends the questionnaire rather than living in it.

Each question goes the road [a coding agent's own question](/user/questions) goes, so it is a
real question wherever the run is being watched, options and all.

## Nobody there is an answer too

The person may be **away**: always, for a run of `hmz exec`, where nobody is at a prompt; and
whenever `/afk` says so in the interface. The flow can read it — `human.away` — and an away
person answers at once rather than leaving a run waiting on an answer that is not coming:

- a question asked for text is answered `""`;
- a question asked for a shape every field of which has a default is answered with those
  defaults;
- any other shape raises `OutworlderAway`, since there is nothing honest to answer it with.

So a flow written to be run unattended gives what it asks the person defaults, and takes the
branch its defaults lead to — which is also the branch a person who walked away mid-question
leads to.

## A flow can stand in for the person

A flow calling another that asks its person things may want to answer those itself — with a
rule, with another agent, with a flow of its own. `Outworlder.new()` makes a person the caller
answers for, through a hook:

```python
from hmz.flows import Outworlder, OutworlderRunHookParams, OutworlderRunHookResult


async def approve(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
    if params.output_schema is None:
        return OutworlderRunHookResult(output="yes, go ahead")
    return OutworlderRunHookResult(output=params.output_schema())


stand_in = Outworlder.new()
stand_in.on_outworlder_run(approve)
await rlcr(task, agents={"builder": builder, "reviewer": reviewer, "human": stand_in}, ...)
```

Every `run` of that person in the called flow is the hook's to answer, as the caller. One made
with `Outworlder.new()` and given no hook is away.

## Which is why it is one feature and not two

An agent stopping mid-turn to ask its user something and a flow asking a person something are
the same road: both are answered by whoever is at the prompt or by the flow, both say what was
asked to whatever is watching the agent, and both are answered for at once where nobody is
there. The difference is only that a flow states the shape of the whole answer once, in the
model it is about to use.

## Where the detail is

- [The person as an agent](/weaver/human-agent) — driving one from a flow
- [Questions](/user/questions) — an agent asking its user
- [Being away](/user/afk) — deciding what happens when nobody is at the prompt
- [Flows reference](/reference/flows#the-person-at-the-prompt)
