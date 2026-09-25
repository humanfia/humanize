# Weaver Guide

A **weaver** is whoever — or whatever — writes a flow: the directory of Python that says which
agents are driven, what each is asked, in what order, and when to stop. This section is
everything that role needs. The [User Guide](/user/) is for whoever runs what a weaver made.

If you have not run humanize at all yet, the front page has a quickstart per role: [run a
flow](/#run-a-flow) is the basics of running one, and [weave a flow](/#weave-a-flow) is the
shortest flow there is.

## Tutorials

A whole flow written from scratch, run, and tested.

| | |
| --- | --- |
| [Build under test](/weaver/tutorials/build-under-test) | The shortest useful flow there is: a writer, `pytest` between turns, a reviewer — and a test of it that spends nothing |

## Writing a flow

| | |
| --- | --- |
| [Writing a flow](/weaver/writing-a-flow) | An `async def`, the roles it drives, the directory it works in |
| [Loops](/weaver/loops) | Ralph, stateful ralph, and the shapes a loop takes |
| [Params of its own](/weaver/flow-settings) | A `FlowParams` model that becomes `-p` and a form at the prompt |
| [Many turns at once](/weaver/async-flows) | `gather`, `TaskGroup`, and a session apiece |
| [A flow that calls a flow](/weaver/calling-flows) | Refs, what the called flow is handed, its budget, and picking it up |

## What an agent can be asked

| | |
| --- | --- |
| [Goals](/weaver/goals) | The CLI's own goal feature: it decides when it is done |
| [Answers in a shape](/weaver/shapes) | A turn that answers with a pydantic model instead of prose |
| [Hooks](/weaver/hooks) | Async functions hung on the moments of a session |
| [The agent asking the flow](/weaver/tools) | A question mid-turn, answered by the flow's own code |
| [The person as an agent](/weaver/human-agent) | You, driven by a flow like any other agent — or somebody standing in for you |
| [Branching a conversation](/weaver/branching) | Two ways out of one conversation, paid for once |
| [Worktrees, copies and scratch](/weaver/worktrees) | One agent working in several directories at once |

## Testing and publishing

| | |
| --- | --- |
| [Testing a flow](/weaver/testing-flows) | The fake kit: the flow, run exactly as it runs, on agents that answer from a script |
| [Flowverses](/weaver/flowverses) | A git repository of flows, offered by name and callable by ref |

## From the User Guide

A flow declares what the agents it drives may do, so five pages written for whoever runs one
are pages a weaver writes against.

| | |
| --- | --- |
| [Concepts](/user/concepts) | The vocabulary the rest of this uses |
| [Security](/user/security) | A flow is Python, and reading one means running it |
| [Skills](/user/skills) | What an agent carries: its CLI's own, and the ones the flow brings |
| [Permissions](/user/permissions) | What each role may touch — yours to declare |
| [Efforts](/user/efforts) | How hard to think |

---

The official flowverse is the shortest way to see what a flow of your own could be: reading one
is [Flows](/flows/). For the contract in full — every argument, every refusal, every return —
[Reference › Flows](/reference/flows).
