---
title: User Guide
description: Find the page for any feature of Humanize Desktop, the browser page, the terminal interface and the command line.
---

# User Guide

Use this guide to run Humanize in Humanize Desktop, the browser page, the terminal or the command line. Each page covers one feature across every interface that supports it. If you are new to Humanize, start with a [tutorial](/tutorials/); to write flows in Python, read the [Builder Guide](/builder/).

![Humanize Desktop, the browser page, the terminal interface and the command line all talk to one daemon, which runs the coding agents](/diagrams/user-index-1.svg)

*Four interfaces, one daemon. What you start in one appears in the others.*

## Get set up

- [Install and update](/user/install): install, update and uninstall the app or CLI.
- [Concepts](/user/concepts): learn core terms like flow, epic, chat and nous.
- [Humanize Desktop](/user/desktop): use the desktop window, menus, tray and notifications.
- [The browser page](/user/web): open the web interface with `hmz web` and navigate it.
- [The terminal interface](/user/terminal): use the prompt, slash commands, views and keys of `hmz`.
- [The command line](/user/command-line): run flows and chats from scripts with `hmz exec` and `hmz chat`.
- [Security](/user/security): control agent actions, store credentials and pair devices.

## Chat

- [Chat with an agent](/user/chat): start a chat, send messages, stop a turn and continue a session.
- [Commands, skills and files in a chat](/user/chat-input): use `/`, `$`, `!` and `@` in the message box.
- [Organise chats](/user/manage-chats): rename, fork, pin, archive, delete, group and search chats.
- [Continue sessions from other CLIs](/user/harness-sessions): read and continue standalone coding agent sessions.
- [Ask a side question](/user/side-questions): ask about a running chat or epic without interrupting it.
- [Ai-chan](/user/ai-chan): use the operator agent to control Humanize for you.

## Run flows

- [Find and install flows](/user/flows): add a flowverse to install, update and remove flows.
- [Start an epic](/user/epics): assign a task, agents, environments and a budget to a flow.
- [Budgets](/user/budgets): cap a run by time, cost or output tokens.
- [Watch a run](/user/watch-a-run): track agents, turns and cost while a flow runs.
- [Talk to a running flow](/user/steering): send a message to a running turn and use the board.
- [Answer a flow's questions](/user/questions): reply to a flow, claim a role or mark yourself away.
- [Stop a run](/user/stopping): stop or force stop a run and see the resulting state.
- [Leave it running and come back](/user/leaving): close the terminal or window and reattach later.
- [Resume a run](/user/resuming): pick up an epic that ended or was stopped.
- [Notifications](/user/notifications): see what triggers a notice and where it appears.

## Agents and models

- [Coding agents](/user/agents): see supported coding agents, their capabilities and how to reference them.
- [Accounts](/user/accounts): manage multiple named credentials for each coding agent.
- [Nous: models, retries and fallback](/user/nous): select a model and configure retries and fallbacks.
- [Effort and swarm mode](/user/efforts): set reasoning effort or run a turn as a fleet of subagents.
- [Gateways, LiteLLM and custom CLIs](/user/gateways): connect third-party endpoints, a local LiteLLM gateway or your own CLI.
- [Permissions](/user/permissions): control what an agent can read, modify and reach.
- [Skills](/user/skills): find where skills live and how agents load them.
- [Cost and usage](/user/usage): track run costs and view usage by day and by flow.

## Where the work runs

- [Environments](/user/environments): pick the folder and the machine a chat or epic works in, and move a chat between turns.
- [Files, changes and terminal](/user/environment-panels): browse and edit files, review and commit changes and open a shell.
- [Snapshots and rewind](/user/snapshots): restore a snapshot taken during a flow run.
- [Runtimes: servers, containers and clusters](/user/runtimes): run agents over SSH, in Docker, in an Apple container or on Slurm.
- [The sandbox](/user/sandbox): see how an agent is held to its permission and choose what enforces it.

## Machines and devices

- [The daemon](/user/daemon): manage the background process that runs your chats and epics.
- [Connect to other machines](/user/daemons): connect remote daemons and pair or revoke devices.
- [Relays and WebRTC](/user/relay): reach your daemon from any browser.

## After a run

- [History and search](/user/history): open past epics and search across chats and epics.
- [Trace a run with Exomyth](/user/tracing): profile a run and inspect its timeline and flame graph.
- [Export and import a run](/user/export): save and open `.hmzepic` archives.
- [Back up to git](/user/backups): push epics and chats to git repositories and pull them back.

## Make it yours

- [Settings](/user/settings): configure Humanize and see where settings are stored.
- [Themes and language](/user/themes): change the appearance, edit a theme and pick a language.

## Help

- [Troubleshooting](/user/troubleshooting): fix common failures and find the logs.
- [Report a problem](/user/reporting): see what error reports contain and file an issue.
