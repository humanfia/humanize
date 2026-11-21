---
title: Run two coding agents with a fallback
description: Make a virtual nous that tries Codex first and falls back to Claude Code, give each role of a flow its own model and effort, and see which model took each turn and what it cost.
---

# Run two coding agents with a fallback

Give two coding agents a single name, `careful`, that sends each turn to Codex first and moves to Claude Code if Codex fails. You will run a flow with it, watch a turn fall back, and see what each model cost.

![The virtual nous careful: a turn goes to Codex first, moves to Claude Code on any fault, and the graph is walked once more if both fail](/diagrams/tutorials-two-agents-with-fallback-1.svg)

## What you need

- Humanize Desktop, set up as in [Finish your first task in Humanize Desktop](/tutorials/first-task-desktop).
- Two coding agents installed and signed in on this machine: Claude Code (`claude`) and Codex (`codex`).
- The `rlar` flow installed. See [Find and install flows](/user/flows).
- A project folder (`shop`).

::: tip Two accounts of one CLI
You can build the same graph with two accounts of one CLI, such as `claude@work/claude-opus-4-1` then `claude@personal/claude-opus-4-1`. Add them in **Settings**, **Accounts**; see [Accounts](/user/accounts). On macOS, Humanize refuses turns under a named account of Claude Code or Codex because the credential supervisor needs Linux. This tutorial uses two CLIs on their own sign-ins instead.
:::

## 1. Check that both agents are found

1. Click the gear, **Settings**, at the bottom left.
2. Open **Nous**.
3. Click **Scan**.

A nous is a model choice: a harness, an account, a model, and an effort. **Concrete** lists one group per harness and the models it runs. Confirm that both agents appear.

![Settings, Nous: Claude Code lists two models and Codex lists one](/shots/tutorials-two-agents-with-fallback-found.svg)

## 2. Make a virtual nous

A virtual nous is a name for a graph of other nous. Use that name anywhere you pick a model.

1. Click **New virtual nous**.
2. In **Name**, type `careful`. Set **Tries** to `1`. Leave **Wait** and **Limit, s** as they are.
3. Under **Graph**, click **Add use node**. This creates the start node, `n1`. Click its chip and pick the **Harness** Codex, a **Model**, and the **Effort** High.
4. Click **Add use node** again. On `n2`, pick Claude Code, a model, and the effort High.
5. On `n1`, click **Add edge**. It reads `On * (any other) go to n2`.
6. Click **Save**.

![Reel: a virtual nous is named, given a Codex node and a Claude Code node, joined by an edge, and saved](/shots/tutorials-two-agents-with-fallback-nous.svg)

`careful` now appears under **Virtual**.

![The row of careful: 1 more go, n1 is Codex and goes to n2 on any fault, n2 is Claude Code](/shots/tutorials-two-agents-with-fallback-listed.svg)

Each use node runs the turn on one nous. An edge routes the turn when its node fails: pick a fault such as `throttled` or `refused`, or `*` for any other. **Tries** sets how many more times Humanize walks the whole graph after it fails, and **Wait** sets how long it waits before each of those retries.

## 3. Give each role its own nous

The `rlar` flow has two roles: `actor` does the work and `reviewer` checks it.

1. Click **New epic** and choose the flow `rlar`.
2. Under **Agents**, click the chip of `actor`. Under **Virtual**, pick `careful`.

![The chip menu of the actor role: careful is listed under Virtual, above Harness, Model and Effort](/shots/tutorials-two-agents-with-fallback-pick.svg)

3. Click the chip of `reviewer`. Pick Claude Code, a cheaper model, and the **Effort** High.
4. Under **Budget**, type `5` in **Cost, $**.
5. Type the task and press <kbd>enter</kbd>.

![The New epic form: actor is careful, reviewer is Claude Code Haiku 4.5 High, the cost limit is 5 dollars](/shots/tutorials-two-agents-with-fallback-roles.svg)

## 4. Watch a turn fall back

Click the session under the actor on the epic graph to read its turn.

If Codex answers, the turn finishes there. Here, Codex hits its usage limit. Humanize reports the rate limit, waits 30 seconds, and tries Codex once more. Every rate-limited model gets this one retry by itself; it is not the **Tries** of `careful`, which count only after the whole graph has failed.

![The actor's session while running: codex is rate-limited, trying again in 30s, 1 of 1](/shots/tutorials-two-agents-with-fallback-waiting.svg)

Codex fails again, so the turn follows the edge to `n2`. The log prints `carrying on as claude/claude-opus-4-1:high`, and Claude Code completes the task.

![The finished epic: two rate-limit lines, then Claude Code's tool calls and answer, and the Spending table on the right](/shots/tutorials-two-agents-with-fallback-done.svg)

## 5. See what each model cost

Check the right panel of the epic. **Figures** shows **Spent**, the total for the epic. **Spending** lists one row per model that answered, with input and output tokens, cache reads and writes, **Cost**, and **Out/s**.

Opus 4.1 took the actor's turn and Haiku 4.5 took the review. Codex has no row because it never answered. Models without a listed price show tokens and no cost.

## 6. Run it from the command line

Pass the virtual nous name where a model name goes. In the project folder, run:

```sh
hmz exec -f rlar -a actor=careful,reviewer=claude/claude-haiku-4-5:high -p budget.cost=5 "Add a discount code to checkout"
```

Each turn ends with a line showing its tokens, its cost, and the model that answered.

![hmz exec prints the rate limit, the fallback to claude/claude-opus-4-1:high, the tool calls, and a cost line per turn naming the model](/shots/tutorials-two-agents-with-fallback-exec.svg)

## What you did

- You verified that Humanize found both coding agents.
- You created the `careful` virtual nous to fall back from Codex to Claude Code.
- You ran `rlar` with separate models per role.
- When Codex hit a rate limit, you watched the turn retry and switch to Claude Code.
- You checked the cost per model in the app and on the command line.

## Next

- [Nous: models, retries and fallback](/user/nous)
- [Accounts](/user/accounts)
- [Effort and swarm mode](/user/efforts)
- [Cost and usage](/user/usage)
