---
title: "Nous: models, retries and fallback"
description: Pick the model an agent runs on, say how a failed turn is retried, and name a fallback that carries the turn to another model.
---

# Nous: models, retries and fallback

A nous is what an agent thinks with: a harness, an account, a model and an effort. Use this page to pick a nous, set how a failed turn retries, and build a virtual nous that falls back to another model.

![The Nous page of Settings in Humanize Desktop, listing two virtual nous and the concrete nous of each harness](/shots/user-nous-page.svg)

## Understand concrete and virtual nous

A concrete nous is one model: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`, such as `claude@work/claude-opus-4-1:high`. Omit `@ACCOUNT` to use this machine's sign-in. Omit `:EFFORT` to use the harness default.

A virtual nous is a short name, such as `careful`, that stands for a graph of other nous. Use it anywhere you name a concrete nous.

Every nous has four retry settings: extra tries on failure, wait time between tries, a time limit across all tries, and a `then` graph to run when the tries run out.

![A turn starts at node n1, is retried there, follows an edge to node n2 when it fails, and ends at the first answer](/diagrams/user-nous-1.svg)

## In the app

### Pick a nous

Click the nous chip under a chat box, on a role in **New epic**, for Ai-chan, or on a graph node. The menu lists virtual nous under **Virtual**. Under **Concrete**, pick **Harness**, **Account**, **Model** and **Effort** in order. Each step filters the next.

![The chip opens, then Harness, Model and Effort are picked one after another](/shots/user-nous-chip.svg)

- **Account** appears when a harness has an account besides **Local** (this machine's sign-in). Click **Add account…** to open [Accounts](/user/accounts).
- **Model** offers **Find a model** to search a list of more than ten models, **Other model** to enter an unlisted ID, and **Refresh models** to query the harness again.
- **Effort** lists the levels the model accepts. See [Effort and swarm mode](/user/efforts).

### View concrete nous

Open **Settings** and click **Nous**. You do not create concrete nous by hand. The daemon queries each installed harness at startup and when you click **Scan**. They appear under **Concrete**, grouped by harness. When there are more than 12, use **Find a nous** to filter the list; a harness with more than 12 models starts folded unless one of them has saved settings.

The line under the heading counts them, such as `3 concrete nous of 2 harnesses.`, or reads `No harness is installed on this daemon.`, and each harness fold shows `2 models`, `No models listed` or `Not asked yet`. After a **Scan**, a harness or account that did not answer is named on that line, as `Codex would not answer: <why>` or `Codex @work would not answer: <why>`. The other harnesses are still queried and listed.

Click **Edit** on a row to set its retries and `then` graph. A row with saved settings has **Reset**, which clears them and keeps the nous in the list.

### Create a virtual nous

1. Click **New virtual nous**.
2. Enter a **Name**. Start with a letter, use only letters, digits, `_`, `.` and `-`, and do not use a harness name.
3. Set the retries and build the **Graph**.
4. Click **Save**.

The new nous appears under **Virtual** with **Edit**, **Rename** and **Remove**. Renaming updates every graph that references it. You cannot remove a virtual nous while another graph references it.

### Set retries

![The Tries, Limit and Wait fields of a nous](/shots/user-nous-retries.svg)

| Field | What it sets | Default |
| --- | --- | --- |
| **Tries** | Extra attempts at this nous after a failed turn. | `0`: tried once |
| **Limit, s** | Seconds after which no further try starts. | `0`: no limit |
| **Wait** | Delay between tries. | **Exponential with jitter** |

| Wait | Waits |
| --- | --- |
| **No wait** | None. |
| **Constant** | 1s, 1s, 1s. |
| **Linear** | 1s, 2s, 3s. |
| **Exponential** | 1s, 2s, 4s, 8s. |
| **Exponential with jitter** | Random delay up to the exponential wait, so agents that fail together do not retry together. |
| **Fibonacci** | 1s, 1s, 2s, 3s, 5s. |

Single waits cap at 60 seconds.

### Build a graph

Click **Add use node** or **Add balance node** to add nodes, and set **Start** to choose where a turn begins.

![A graph of two use nodes: Codex first, and an edge that sends any fault to Claude Code](/shots/user-nous-graph.svg)

A use node runs the turn on the concrete or virtual nous picked on its chip.

When a node fails, it follows an edge. Once the graph has a second node, click **Add edge**, pick a fault after **On**, and pick a target node after **go to**. Name an edge for a specific fault (see the table below) or `* (any other)`. If a node has no matching edge, the graph fails.

A balance node picks among several nous. Click **Add member** for each nous and set its weight after `×`. When a member fails, the node tries another. Set **Spread** to cap how many members may fail before the node gives up; `0` tries all of them.

![A balance node: Round robin among two members with weights, and an edge on throttled](/shots/user-nous-balance.svg)

| Strategy | Picks |
| --- | --- |
| **Shuffle** | At random, weighted. |
| **Round robin** | In turn, weighted. |
| **Least busy** | Fewest active turns right now. |
| **Fastest** | Fastest recent turn responses. |
| **Least used** | Fewest tokens spent in the last minute. |
| **Cheapest** | Lowest model cost per token. |

**Then** is a second graph that runs when the nous exhausts its tries. Without **Then**, the nous fails with its last fault.

## In the terminal

Run `/settings nous` to list each nous you have written down, its retries and its fallback target.

![The Nous page of the terminal interface, a row per nous](/shots/user-nous-terminal.svg)

Press <kbd>enter</kbd> on a row to edit it, or select **Add nous**. **Search…** or <kbd>/</kbd> narrows the list. To configure a concrete nous, type its ID in `Name` or pick it with `Choose`. The form of a saved nous has **Remove**, and editing `Name` renames a virtual nous.

| Row | What it sets |
| --- | --- |
| `Name` | Concrete nous ID or virtual nous name. |
| `Choose` | Concrete nous from a list. Shown while adding. |
| `Effort` | Effort of a concrete nous. Shown while adding. |
| `Tries` | `none`, 1, 2, 3, 5, 8, 13 or 21. |
| `Wait` | Wait between tries. |
| `Limit` | `no limit`, or 30 seconds up to an hour. |
| `Graph` | Graph of a virtual nous. |
| `Then` | `then` graph. |

The graph form shows `Start`, one row per node, and `Add node`. Each node has `Node id` and `Kind`. A use node has `Nous` and `Choose`. A balance node has `Strategy`, `Among` (formatted as `claude/opus 2, codex/gpt-5 1`), `Choose` and `Spread`. Once the graph has another node, each node ends with one `On <fault>` row per fault.

![From a nous to its form, its graph and a balance node, in the terminal](/shots/user-nous-terminal-graph.svg)

Select **Save** on the Nous page to apply your changes.

## From the command line

Pass a concrete or virtual nous wherever a command accepts an agent:

```sh
hmz chat start -a careful "Add a discount code to checkout"
hmz exec -f rlar -a actor=careful,reviewer=claude/claude-haiku-4-5 -p budget.cost=5 "Add a discount code to checkout"
```

The CLI logs each wait and each fallback to another nous.

![hmz chat start with a virtual nous: Codex is rate-limited, the turn waits, then carries on as Claude Code](/shots/user-nous-chat.svg)

`hmz nous` lists and writes nous through the daemon:

```sh
hmz nous list --concrete              # every model an agent can be given
hmz nous scan                         # ask every installed harness again
hmz nous set claude/claude-opus-4-1 --tries 3 --timeout 600
hmz nous set careful --graph claude/claude-opus-4-1 --graph codex/gpt-6-sol
hmz nous set claude/claude-haiku-4-5 --then careful
hmz nous rename careful slow
hmz nous clear slow
```

`set` keeps what you do not give it. Repeat `--graph` or `--then` to try several nous in turn, or pass one JSON graph of `start` and `nodes` for a balance node or per-fault edges; `hmz nous list --json` prints graphs in that form. See the [CLI reference](/reference/cli#hmz-nous).

Humanize saves every nous in `~/.config/humanize/settings.toml` under `nous`. See [settings.toml](/reference/settings).

## How faults work

When a turn fails, Humanize reads the harness output and classifies the failure into one of twelve faults. The fault selects which edge a node follows, and sets a floor or a stop on the retries at that nous:

| Fault | What happened | At the same nous |
| --- | --- | --- |
| `throttled` | Service rate-limited the account. | At least 1 more try, after at least 30 seconds. |
| `spent` | Account quota or balance is exhausted. | At least 1 more try, after at least 30 seconds. |
| `contended` | Another turn holds the harness local store. | At least 3 more tries, at a constant wait. |
| `dropped` | Connection lost. | At least 1 more try, in a new harness process. |
| `killed` | Harness process died. | At least 1 more try, in a new harness process. |
| `refused` | Credentials refused. | Never retried. |
| `unlisted` | Account cannot use this model. | Never retried. |
| `retired` | Model does not exist. | Never retried. |
| `missing` | Harness is not installed. | Never retried. |
| `sandboxed` | Harness could not start its sandbox. | Never retried. |
| `unmirrored` | Local copy of a remote workspace could not be created. | Never retried. |
| `fenced` | Network fence blocked the harness from a host. | Never retried. |

A failure that matches no fault is retried as the nous says and follows the `* (any other)` edge. Faults that never retry skip the tries: the turn goes to **Then** if the nous has one, then to the node's edge. For a complete example, see [Run two coding agents with a fallback](/tutorials/two-agents-with-fallback).

## Good to know

- Switching to another concrete nous starts a new conversation because harnesses cannot share sessions. A nous exhausts its own tries before following an edge.
- For each conversation, a balance node remembers the last member that answered and tries it first on the next turn.
- Saving fails if a graph contains a cycle of nodes or virtual nous, or a node that no edge reaches from the start.
- Settings saved for a concrete nous without an effort, such as `claude/claude-opus-4-1`, apply to every effort of it that has none of its own.
- A concrete nous with `0` tries and no **Then** is not saved: it says nothing.
- A balance node tries members that were `throttled` or `spent` in the last minute only after the others.
- **Batch apply** on the Nous page copies your configured nous to other daemons without deleting any already there. See [Settings](/user/settings).
- While scanning harnesses for models, the page shows `Scanning the harnesses in the background…`.
