---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Everything it does

<p class="hmz-tagline">Find what you want to do, and go straight to the page that does it.</p>

<HmzMap />

## Run it your way

| You can | Go to |
| --- | --- |
| **Ready-made loops.** A Ralph loop, a reviewer loop, three lanes at once. | [Flows](https://humanfia.ai/flows/) |
| **Any coding agent.** Claude Code, Codex, Cursor, Kimi and more, most on the login they have. Add any Agent Client Protocol CLI. | [Accounts](/user/settings#accounts)<br><small>[Every coding agent you have](/features/backends)</small> |
| **Model and effort.** Each agent's model, and how hard it thinks. | [Efforts](/user/efforts) |
| **Two accounts of one CLI.** A subscription and a gateway side by side, each with its own login. | [Accounts](/user/settings#accounts)<br><small>[Two accounts of one CLI](/features/accounts)</small> |
| **Fall back.** A failed turn is tried again, then handed along a chain of other accounts, CLIs or models. | [Falling back](/user/settings#fallback)<br><small>[Two accounts of one CLI](/features/accounts)</small> |
| **Skills.** The skills each agent loads. A flow can bring its own. | [Skills](/user/skills) |
| **In a browser.** The run going, every run before it, starting one and what they spent, on a page. | [In a browser](/user/web)<br><small>[Prompt, browser, script or Python](/features/surfaces)</small> |
| **From a script.** A flow from a shell script or a cron job, no interface. | [Run it unattended](/user/unattended)<br><small>[Prompt, browser, script or Python](/features/surfaces)</small> |
| **In CI.** A flow on a schedule that opens a pull request. | [humanize in CI](/user/ci) |
| **From Python.** humanize driven by a program of your own. | [SDK reference](/reference/sdk)<br><small>[Prompt, browser, script or Python](/features/surfaces)</small> |

## While it runs

| You can | Go to |
| --- | --- |
| **Talk into a turn.** Correct an agent mid-turn without stopping it. | [Talking to a running turn](/user/steering)<br><small>[Talk into a running turn](/features/steering)</small> |
| **Side questions.** Ask a running flow what it is up to, without interrupting. | [Side questions](/user/btw) |
| **Watch every agent.** Who is working, for how long, and who handed over to whom. | [Watching a run](/user/monitor) |
| **Answer, or step away.** Answer when asked, or say you are away so nothing waits. | [Questions](/user/questions), [Being away](/user/afk)<br><small>[When a flow asks you](/features/human)</small> |
| **What it costs.** Tokens, money and rate for every agent, live. | [Cost and rate](/user/tally) |
| **A budget on every run.** Time, cost or output tokens; the first limit reached stops it. | [Run it unattended](/user/unattended)<br><small>[A budget on every run](/features/allowances)</small> |
| **Stop it.** From the keyboard, and by force if it will not stop. | [Stopping](/user/stopping) |
| **Leave it running.** Close the terminal; open humanize in the same directory to find it again. | [Daemon reference](/reference/daemon)<br><small>[Close the terminal, keep the run](/features/daemon)</small> |

## Where the work lands

| You can | Go to |
| --- | --- |
| **In a container.** A toolchain you have not got, with your project at the same path. | [Containers](/user/containers) |
| **On another machine.** Commands run on the build box; the agent and its login stay here. | [Remote execution](/user/remote-execution)<br><small>[Work on another machine](/features/anchor)</small> |
| **What an agent may touch.** What a flow lets each agent do. Nothing is put to you. | [Permissions](/user/permissions), [Security](/user/security) |

## After a run

| You can | Go to |
| --- | --- |
| **Pick it up.** Carry a stopped run on from where it stood. | [Picking a run up](/user/resuming)<br><small>[Pick up where it stopped](/features/resuming)</small> |
| **One timeline.** Every agent and sub-agent on one clock in Perfetto, programs too if profiled. | [Tracing](/user/tracing)<br><small>[Every agent on one timeline](/features/tracing)</small> |
| **Hand it to somebody.** A whole run packed into one archive. | [Exporting a run](/user/export) |
| **Crash reports.** Send them and feedback, or never. You are asked once. | [Reporting](/user/reporting) |

## Writing a flow

Python, for the weaver: whoever writes the flow.

| You can | Go to |
| --- | --- |
| **A loop in plain Python.** An async function, with its agents declared by role. | [Writing a flow](/weaver/writing-a-flow)<br><small>[A loop in plain Python](/features/flows)</small> |
| **Params of its own.** Typed settings the prompt and the command line both fill in. | [Params of its own](/weaver/flow-settings) |
| **Many conversations at once.** Fan out as wide as the work needs. | [Many turns at once](/weaver/async-flows)<br><small>[Many conversations at once](/features/concurrency)</small> |
| **Answers as typed data.** A pydantic model back, not a paragraph. | [Answers in a shape](/weaver/shapes)<br><small>[Answers as typed data](/features/shapes)</small> |
| **The agent decides it is done.** A goal it keeps at until it judges it met. | [Goals](/weaver/goals)<br><small>[The agent decides it is done](/features/goals)</small> |
| **React to each moment.** Your code before a tool, on a prompt, as a turn stops. | [Hooks](/weaver/hooks)<br><small>[React to each moment of a turn](/features/hooks)</small> |
| **Tools that call the flow.** The agent reaches the flow mid-turn; the flow's code answers. | [The agent asking the flow](/weaver/tools) |
| **Ask the person.** A question to whoever is at the prompt, as one of the flow's agents. | [The person as an agent](/weaver/human-agent)<br><small>[When a flow asks you](/features/human)</small> |
| **Cap a single turn.** Stop one turn at a time, money or token limit. | [Flows reference](/reference/flows)<br><small>[Cap a single turn](/features/budgets)</small> |
| **Call another flow.** Another flow as a step, under what is left of your budget. | [A flow that calls a flow](/weaver/calling-flows) |
| **Branch a conversation.** Fork it and try more than one way on. | [Branching a conversation](/weaver/branching) |
| **Worktrees and copies.** A worktree per task, a throwaway copy, or a scratch directory. | [Worktrees, copies and scratch](/weaver/worktrees) |
| **Test without a model.** Scripted agents: milliseconds a test, nothing spent. | [Testing a flow](/weaver/testing-flows) |
| **Publish it.** A flow in a repository of its own, listed in a flowverse anybody can install it from. | [Flowverses](/weaver/flowverses) |

::: details Which CLI does what
Most of the map works the same on every CLI. Three things do not:

| CLI | Talk into a turn | Goals | Trace |
| --- | :---: | :---: | :---: |
| Claude Code | ✓ | ✓ | ✓ |
| Codex | ✓ | ✓ | ✓ |
| Kimi Code | ✓ | ✓ | ✓ |
| pi, Oh My Pi | ✓ | | ✓ |
| DeepSeek Harness | | ✓ | ✓ |
| Antigravity, Grok Build, MiMo Code, MiniMax Code, opencode, Qwen Code | | | ✓ |
| Cursor Agent | | | |
| a CLI you added yourself | | | |

Elsewhere, what you type mid-turn is taken as the next turn. Everything a flow can ask of each
CLI is in the [agents reference](/reference/agents).
:::

<div class="hmz-paths by-three">
  <a :href="withBase('/user/')">
    <strong>User Guide</strong>
    <span>Running flows: settings, watching, stopping, picking up.</span>
  </a>
  <a :href="withBase('/weaver/')">
    <strong>Weaver Guide</strong>
    <span>Writing flows of your own, in Python.</span>
  </a>
  <a :href="withBase('/reference/')">
    <strong>Reference</strong>
    <span>Every command, setting and flow API, in full.</span>
  </a>
</div>

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
