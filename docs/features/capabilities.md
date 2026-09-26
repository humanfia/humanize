---
pageClass: hmz-feature
---

# Everything it does

Find the thing you want to do and go straight to the page that does it. Where a feature page
shows what you get from it, it is the smaller link underneath.

<HmzMap />

## Run it your way

| You can | Go to |
| --- | --- |
| **Ready-made loops.** Pick a loop somebody already wrote: a Ralph loop, a reviewer loop, three lanes at once. | [Flows](/flows/) |
| **Any coding agent.** Claude Code, Codex, Cursor, Kimi and eight more, most under the login they already have. Add any Agent Client Protocol CLI yourself. | [Providers](/user/providers)<br><small>[Every coding agent you have](/features/backends)</small> |
| **Model and effort.** Choose each agent's model and how hard it thinks. | [Efforts](/user/efforts) |
| **Two accounts of one CLI.** A subscription and a gateway of the same CLI, side by side, each with its own login. | [Providers](/user/providers)<br><small>[Two accounts of one CLI](/features/accounts)</small> |
| **Fall back.** When an account runs out, another takes the conversation on. When a CLI is gone, the turn moves where you said. | [Falling back](/user/fallback)<br><small>[Two accounts of one CLI](/features/accounts)</small> |
| **Skills.** See which skills each agent loads. A flow can bring its own. | [Skills](/user/skills) |
| **From a script.** Run a flow from a shell script or a cron job, with no interface. | [Run it unattended](/user/unattended)<br><small>[Prompt, script or Python](/features/surfaces)</small> |
| **In CI.** Run a flow on a schedule and open a pull request with what it did. | [humanize in CI](/user/ci) |
| **From Python.** Drive humanize from a Python program of your own. | [SDK reference](/reference/sdk)<br><small>[Prompt, script or Python](/features/surfaces)</small> |

## While it runs

| You can | Go to |
| --- | --- |
| **Talk into a turn.** Correct an agent mid-turn without stopping it. On Claude Code, Codex, Kimi and pi. | [Talking to a running turn](/user/steering)<br><small>[Talk into a running turn](/features/steering)</small> |
| **Side questions.** Ask what a running flow is up to without interrupting it. | [Side questions](/user/btw) |
| **Watch every agent.** See who is working, for how long, and who handed over to whom. | [Watching a run](/user/monitor) |
| **Answer, or step away.** Answer when an agent or the flow asks you, or say you are away so nothing waits. | [Questions](/user/questions), [Being away](/user/afk)<br><small>[When a flow asks you](/features/human)</small> |
| **What it costs.** Tokens, money and rate for every agent, while it runs. | [Cost and rate](/user/tally) |
| **A budget on every run.** Cap a run's time, cost or output tokens. The first limit it reaches stops it. | [Run it unattended](/user/unattended)<br><small>[A budget on every run](/features/allowances)</small> |
| **Stop it.** Stop the run from the keyboard, and force it if it will not stop. | [Stopping](/user/stopping) |
| **Leave it running.** Close the terminal or lose the connection. Open humanize in the same directory to find the run again. | [Daemon reference](/reference/daemon)<br><small>[Close the terminal, keep the run](/features/daemon)</small> |

## Where the work lands

| You can | Go to |
| --- | --- |
| **In a container.** Give an agent a toolchain you have not got, with your project at the path it already has. | [Containers](/user/containers) |
| **On another machine.** The commands run on the build box. The agent and its login stay on your machine. | [Remote execution](/user/remote-execution)<br><small>[Work on another machine](/features/anchor)</small> |
| **What an agent may touch.** See what a flow lets each agent do. Nothing is put to you for approval. | [Permissions](/user/permissions), [Security](/user/security) |

## After a run

| You can | Go to |
| --- | --- |
| **Pick it up.** Carry a stopped run on from where it stood, if its flow can be picked up. | [Picking a run up](/user/resuming)<br><small>[Pick up where it stopped](/features/resuming)</small> |
| **One timeline.** Every agent and sub-agent of a run on one clock in Perfetto, and the programs they ran if you profiled it. | [Tracing](/user/tracing)<br><small>[Every agent on one timeline](/features/tracing)</small> |
| **Hand it to somebody.** Pack a whole run into one archive somebody else can open. | [Exporting a run](/user/export) |
| **Crash reports.** Send crash reports and feedback, or never. You are asked once. | [Reporting](/user/reporting) |

## Writing a flow

Everything here is Python, for the weaver: whoever writes the flow.

| You can | Go to |
| --- | --- |
| **A loop in plain Python.** Write the loop as an async function and declare the agents it needs by role. | [Writing a flow](/weaver/writing-a-flow)<br><small>[A loop in plain Python](/features/flows)</small> |
| **Params of its own.** Typed settings that the prompt and the command line both fill in. | [Params of its own](/weaver/flow-settings) |
| **Many conversations at once.** Fan out across as many conversations as the work needs. | [Many turns at once](/weaver/async-flows)<br><small>[Many conversations at once](/features/concurrency)</small> |
| **Answers as typed data.** Ask for a pydantic model and read a field, not a paragraph. | [Answers in a shape](/weaver/shapes)<br><small>[Answers as typed data](/features/shapes)</small> |
| **The agent decides it is done.** Give an agent a goal and let it keep going until it judges the goal met. | [Goals](/weaver/goals)<br><small>[The agent decides it is done](/features/goals)</small> |
| **React to each moment.** Run your own code before a tool, on a prompt, or when a turn stops. | [Hooks](/weaver/hooks)<br><small>[React to each moment of a turn](/features/hooks)</small> |
| **Tools that call the flow.** Let the agent reach the flow mid-turn, and answer with the flow's own code. | [The agent asking the flow](/weaver/tools) |
| **Ask the person.** Put a question to whoever is at the prompt, as one of the flow's agents. | [The person as an agent](/weaver/human-agent)<br><small>[When a flow asks you](/features/human)</small> |
| **Cap a single turn.** Stop one turn once it has spent enough time, money or output tokens. | [Flows reference](/reference/flows)<br><small>[Cap a single turn](/features/budgets)</small> |
| **Call another flow.** Use another flow as a step, under what is left of your budget. | [A flow that calls a flow](/weaver/calling-flows) |
| **Branch a conversation.** Fork a conversation and try more than one way on from the same point. | [Branching a conversation](/weaver/branching) |
| **Worktrees and copies.** A worktree per task, a throwaway copy, or an empty scratch directory. | [Worktrees, copies and scratch](/weaver/worktrees) |
| **Test without a model.** Run a flow against scripted agents: milliseconds a test, and nothing spent. | [Testing a flow](/weaver/testing-flows) |
| **Publish it.** Put flows in a git repository that anybody can add and run by name. | [Flowverses](/weaver/flowverses) |

::: details Which CLI does what
Most of the map works the same on every CLI. Three things do not:

| CLI | Talk into a turn | Goals | Trace |
| --- | :---: | :---: | :---: |
| Claude Code | ✓ | ✓ | ✓ |
| Codex | ✓ | ✓ | ✓ |
| Kimi Code | ✓ | ✓ | ✓ |
| pi | ✓ | | ✓ |
| ZCode | | ✓ | ✓ |
| DeepSeek Harness | | ✓ | ✓ |
| Antigravity, Grok Build, MiMo Code, opencode, Qwen Code | | | ✓ |
| Cursor Agent | | | |
| a CLI you added yourself | | | |

On a CLI that cannot be talked to mid-turn, what you type is taken as the next turn. Everything
a flow can ask of each CLI is in the [agents reference](/reference/agents).
:::

<style scoped>
.vp-doc td small {
  display: block;
  margin-top: 2px;
  line-height: 1.5;
}

.vp-doc td small::before {
  content: '↳ ';
  color: var(--vp-c-text-3);
}
</style>
