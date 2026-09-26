<script setup>
import { withBase } from 'vitepress'
</script>

# Weaver Guide

A **weaver** writes flows: the Python that says which agents are driven, what each is asked, in
what order, and when to stop. You have run a flow; this is where you write one. If you have
not, start with the [User Guide](/user/).

## Start here

Four pages, in order. The first has a flow of your own running in five minutes; the rest grow
it.

<div class="hmz-paths">
  <a :href="withBase('/weaver/writing-a-flow')">
    <strong>1 · Your first flow</strong>
    <span>A directory, a decorator, one role. Write it, run it.</span>
  </a>
  <a :href="withBase('/weaver/tutorials/build-under-test')">
    <strong>2 · Build under test</strong>
    <span>A tutorial: one agent writes, pytest judges, a second agent reviews.</span>
  </a>
  <a :href="withBase('/weaver/loops')">
    <strong>3 · Loops</strong>
    <span>What the next turn remembers, and what ends the loop.</span>
  </a>
  <a :href="withBase('/weaver/flow-settings')">
    <strong>4 · Params of its own</strong>
    <span>A pydantic model that becomes <code>-p</code> and a form at the prompt.</span>
  </a>
</div>

## Growing a flow

| | |
| --- | --- |
| [Many turns at once](/weaver/async-flows) | `gather`, `TaskGroup`, and a session apiece |
| [A flow that calls a flow](/weaver/calling-flows) | Build on a flow somebody else wrote |
| [Branching a conversation](/weaver/branching) | Two ways out of one conversation, paid for once |
| [Worktrees, copies and scratch](/weaver/worktrees) | One agent working in several directories at once |

## What an agent can be asked

| | |
| --- | --- |
| [Goals](/weaver/goals) | The CLI's own goal: it decides when it is done |
| [Answers in a shape](/weaver/shapes) | A turn that answers with a pydantic model instead of prose |
| [Hooks](/weaver/hooks) | Your code, run at the moments of a session |
| [The agent asking the flow](/weaver/tools) | A question mid-turn, answered by the flow's own code |
| [The person as an agent](/weaver/human-agent) | You, driven by a flow like any other agent |

What an agent may touch and what it carries are declared by the flow too:
[Permissions](/user/permissions) and [Skills](/user/skills) are written for you.

## When it is ready

| | |
| --- | --- |
| [Testing a flow](/weaver/testing-flows) | The flow run on scripted agents: milliseconds, and nothing spent |
| [Flowverses](/weaver/flowverses) | A git repository of flows, offered by name and callable by ref |

---

Real flows to read are in [Flows](/flows/). Every argument, refusal and return of the flow API
is in [Reference › Flows](/reference/flows).
