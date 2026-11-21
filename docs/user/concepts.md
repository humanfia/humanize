---
title: Concepts
description: Know what each word in Humanize means, and where you meet it in the app, the terminal and on the command line.
---

# Concepts

Humanize uses a small vocabulary. This page defines each word and shows where you find it.

![Four frontends attach to one daemon. The daemon holds an epic, one run of a flow. Each role of the flow is filled by a nous or by you, and turns work in an environment on a runtime.](/diagrams/user-concepts-1.svg)

*How the words fit together.*

## The work

| Word | Meaning |
| --- | --- |
| Flow | A Python program that decides what to ask each agent, in what order, and when to stop. Humanize ships no flows; you install them or write your own. See [Find and install flows](/user/flows). |
| Flowverse | A git repository that indexes flows. The `official` one lists `ralph_loop`, `stateful_ralph`, `continue_loop`, `goal`, `flame_chase` and `rlar` at [humanfia.ai/flows](https://humanfia.ai/flows/). Flows in your own project use the name `@local/<flow>`. |
| Epic | One recorded run of a flow on one task. Every epic has a budget. You cannot reopen an ended epic; running the flow again creates a new one, which a resumable flow can start from where the last one stopped. See [Start an epic](/user/epics), [Budgets](/user/budgets) and [Resume a run](/user/resuming). |
| Chat | A direct conversation with one agent, with no flow and no budget. A chat is not an epic and works with no flow installed. See [Chat with an agent](/user/chat). |

## Who does it

| Word | Meaning |
| --- | --- |
| Agent role | A named slot that a flow declares, such as `actor` or `reviewer`. You fill each agent role with a nous. |
| Harness | A coding agent CLI that Humanize drives, such as `claude` or `codex`. See [Coding agents](/user/agents). |
| Account | Named credentials for one harness. With no account, the harness uses your local sign-in on this machine, which the app calls `Local`. See [Accounts](/user/accounts). |
| Effort | How hard the model thinks, in the harness's own terms, such as `high` or `max`. Leave it blank to use the harness default. See [Effort and swarm mode](/user/efforts). |
| Nous | What an agent thinks with: a harness, an account, a model and an effort, written `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`. A virtual nous is a name, such as `careful`, that groups other nous with retries and fallback. See [Nous: models, retries and fallback](/user/nous). |
| Outworlder | You, acting as a role in a flow. The flow asks a question, and you answer in any frontend. You never assign this role yourself. See [Answer a flow's questions](/user/questions). |

## Where it runs

| Word | Meaning |
| --- | --- |
| Environment | The directory where a turn's work happens. By default, this is the folder you started in; pick **No folder** in the app and the epic or chat gets a temporary directory of its own. A flow can also declare environment roles, which you fill with `-e`. See [Environments](/user/environments). |
| Runtime | A saved machine: an ssh host, a Docker daemon, a Docker swarm, Apple containers on this Mac, or a Slurm cluster. An environment is a directory on a runtime. `This machine` is always available. See [Runtimes: servers, containers and clusters](/user/runtimes). |
| Daemon | One background process per machine and user. It starts automatically and holds every epic and chat so they keep running when you close the window. See [The daemon](/user/daemon). |
| Frontend | The interface you use to reach the daemon: Humanize Desktop, the browser page, the terminal interface or the command line. Several frontends can follow the same epic at once. |

## In the app

Click **New epic** in Humanize Desktop or the browser page (`hmz web`) to see these terms on one form.

![The New epic form in Humanize Desktop for the flow rlar, with the nous menu of the actor role open on Harness, Account, Model and Effort](/shots/user-concepts-app.svg)

*A flow, its two agent roles, and the four parts of a nous.*

**Flow** at the top names the flow. **Daemon** and **Folder** select the machine that holds the epic and its working directory. **Agents** lists one row per agent role; click a row to pick its **Harness**, **Account**, **Model** and **Effort**. **Budget** sets what the epic may spend.

See [Humanize Desktop](/user/desktop) and [The browser page](/user/web).

## In the terminal

Run `hmz`, type `/flow`, and open a flow. You see one row for each agent role, with its nous written as a single string.

![The terminal interface on the set-up sheet of the flow rlar: rows for actor, reviewer and budget](/shots/user-concepts-terminal.svg)

*The same flow in the terminal interface.*

See [The terminal interface](/user/terminal).

## From the command line

Run `hmz exec` to start an epic with one command:

```sh
hmz exec -f rlar -a actor=claude/claude-haiku-4-5:high -a reviewer=claude/claude-haiku-4-5 -p budget.output_tokens=20000 "Add a discount code to checkout"
```

| Part | Word |
| --- | --- |
| `-f rlar` | The flow |
| `-a actor=…` | An agent role and its nous |
| `-p budget.output_tokens=20000` | The budget of the epic |
| The quoted text | The task |

![The command hmz exec running the flow rlar: the actor answers, then the reviewer](/shots/user-concepts-cli.svg)

*One epic, run from the command line.*

See [The command line](/user/command-line).

## Good to know

- The terminal and `hmz exec --help` call a harness a `CLI`. `hmz exec --help` also calls an account a `PROVIDER`.
- In the app, an omitted effort appears as `Default`, and the working directory for an epic or chat is called **Folder**.
- You never pass an outworlder role with `-a`; under `hmz exec`, the flow treats you as away and does not wait for your answers.
