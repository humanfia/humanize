---
layout: home
---

<script setup>
import { withBase } from 'vitepress'
</script>

<HmzHero />

## What you get {#what-you-get}

<div class="hmz-paths by-three">
  <a :href="withBase('/features/backends')">
    <strong>The agents you already have</strong>
    <span>Claude Code, Codex and eleven more, under your own logins and subscriptions. Mix them
    in one run.</span>
  </a>
  <a href="https://humanfia.ai/flows/">
    <strong>A proven loop for every task</strong>
    <span>Pick a flow that suits the work, or write your own in a few lines of Python.</span>
  </a>
  <a :href="withBase('/user/steering')">
    <strong>Watch and steer as it works</strong>
    <span>Every turn shows live. Talk to a running agent, or answer when a flow asks you.</span>
  </a>
  <a :href="withBase('/features/allowances')">
    <strong>A budget on every run</strong>
    <span>Cap time, tokens or dollars. A run stops when it is spent, never after.</span>
  </a>
  <a :href="withBase('/user/leaving')">
    <strong>Close the laptop, keep the run</strong>
    <span>Runs keep going in the background, on this machine or on your servers, and pick up
    where they stopped.</span>
  </a>
  <a :href="withBase('/user/tracing')">
    <strong>See everything it did</strong>
    <span>Every agent, command and cost on one timeline you can replay, export and share.</span>
  </a>
</div>

## Install

**Humanize Desktop**, for macOS and Windows, sets everything up itself: download it from the
[latest release](https://github.com/humanfia/humanize/releases/latest), or see
[Installation](/user/installation#desktop). **Humanize CLI** is one command:

::: code-group

```sh [macOS and Linux]
uv tool install hmz
```

```powershell [Windows]
wsl --install            # once, then in a WSL terminal:
uv tool install hmz
```

:::

Then sign in to a coding agent you use, such as `claude auth login`, and make
[your first run](/user/first-run).

::: warning Agents here act without asking
Every flow's agents run with approvals bypassed: they edit files, run commands and make commits
on their own. Use a scratch repository, and read [Security](/user/security) before you point
one at work you care about.
:::

## Where to go next

<div class="hmz-paths by-three">
  <a :href="withBase('/user/')">
    <strong>User Guide</strong>
    <span>Running flows: the app, the terminal and the browser, agents and accounts, and
    reading a run back.</span>
  </a>
  <a href="https://humanfia.ai/flows/">
    <strong>Flows</strong>
    <span>Every flow there is to run, each with its loop played, on humanfia.ai.</span>
  </a>
  <a :href="withBase('/weaver/')">
    <strong>Writing Flows</strong>
    <span>Your own flow, in Python: loops, goals, hooks and worktrees, and how to test one.</span>
  </a>
  <a :href="withBase('/features/')">
    <strong>Features</strong>
    <span>How Humanize works, drawn: one diagram per capability.</span>
  </a>
  <a :href="withBase('/reference/')">
    <strong>Reference</strong>
    <span>Every command, key, flag and Python call, spelled out.</span>
  </a>
  <a :href="withBase('/contributing/')">
    <strong>Contributing</strong>
    <span>Working on Humanize itself: the layers, the checks, and these docs.</span>
  </a>
</div>
