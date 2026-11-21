---
title: Builder Guide
description: Find the page for the part of a flow you are writing in Python.
---

# Builder Guide

Write flows in Python with this guide. A flow is an `async def` function decorated with `@flow` that runs agents in environments, can ask the person, and can call other flows. If you are new to flows, start with [Write your first flow](/tutorials/first-flow).

![A flow is a Python function that drives agents, environments, the person and other flows](/diagrams/builder-index-1.svg)

## A flow

- [Anatomy of a flow](/builder/flow): use `@flow`, define arguments, store flows, and run them.
- [Agent roles](/builder/agents): declare agents, compare harnesses, and scope an agent to one job.
- [Sessions and turns](/builder/turns): start a session, run and steer a turn, read its output, and handle errors.
- [Loops](/builder/loops): loop in Python with fresh or persistent sessions, and decide when to stop.
- [Params](/builder/params): declare typed parameters that render as a form in the app and `-p` flags on the CLI.
- [Context, errors and cleanup](/builder/context): read `ctx`, catch errors, and clean up when a run stops.
- [Budgets in a flow](/builder/budgets): read the epic budget, set call or turn budgets, and stop cleanly.

## What you can ask an agent

- [Goals](/builder/goals): give the agent a goal and let it decide when it is done.
- [Typed answers](/builder/shapes): request structured answers with validation and retries.
- [Hooks](/builder/hooks): handle turn events like permission requests and agent questions.
- [Tools the agent can call](/builder/tools): expose flow functions as tools or add commands to `PATH`.
- [Skills and permissions](/builder/skills): attach skills and control what each role can read, write, and reach.

## People

- [The person as an agent](/builder/outworlder): ask the person a question, show context, or stand in for them.
- [Faces](/builder/faces): render a question on a custom page.

## Composing

- [Concurrent turns](/builder/async): run turns and calls in parallel and gather their results.
- [Call another flow](/builder/calling-flows): load a flow by reference and run it with its own budget.
- [Branch a conversation](/builder/branching): fork a session to try alternatives from one point.
- [Resumable flows](/builder/resumable): save state so a flow resumes where it stopped.

## Environments

- [Environment roles](/builder/environments): declare environments, run commands, and read and write files.
- [Worktrees, clones and scratch](/builder/worktrees): isolate an agent in a worktree, clone, or scratch directory, and take snapshots.
- [Machines and moving sessions](/builder/machines): specify machine requirements and move sessions between environments.

## Ship it

- [Test a flow](/builder/testing): test a flow against scripted fake agents and assert on what it did.
- [Publish and version a flow](/builder/publishing): add a manifest, cut releases, and list the flow in a flowverse.
- [The Python SDK](/builder/sdk): start and track runs from your own Python code.

## Next

- [Tutorials](/tutorials/): follow a complete job from nothing to a finished result.
- [Flow API](/reference/flows): look up every public name of `hmz.flows`.
- [User Guide](/user/): learn how to run and manage flows in Humanize.
