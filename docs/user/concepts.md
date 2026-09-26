# Glossary

The words the rest of these docs use, one entry each, with where to read more.

```text
epic ─── one run of a flow, written down
 │
flow ─── the loop: who is asked what, and until when
 │
 ├── role "builder" ─── agent: backend, model, effort
 │                       └── session ─── turn, turn, turn …
 │
 └── role "reviewer" ── agent: …
                         └── session ─── turn …
```

## Agent

What fills one role of a flow: a [backend](#backend), a model and an [effort](#effort), and
optionally the [provider](#provider) it runs as. On a command line it is written after the role
it fills:

```text
reviewer=claude@work/claude-opus-4-8:high
   │       │     │         │           └── effort
   │       │     │         └── model
   │       │     └── provider; left out, as you signed in
   │       └── backend
   └── role
```

An agent holds no conversation of its own: it is the settings every [session](#session) it
opens runs at. Two agents set up alike are still two agents. Set one up in `/flow`:
[Your first run](/user/first-run).

## Backend

A coding agent CLI that humanize drives: `agy`, `claude`, `codex`, `cursor-agent`, `dsh`,
`grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen` or `zcode`. It is the `cli` row of an agent.
See [Installation](/user/installation) and [Many backends, one agent](/features/backends).

## Budget

What a run may spend before it is stopped: a `duration`, a `cost` in US dollars, or a number of
`output_tokens`. Every flow except `chat` needs one. See [Every run has a
budget](/features/allowances). A single turn can also have a budget of its own, set by the
flow: [A turn can be cut off](/features/budgets).

## Effort

How hard the model thinks, in the backend's own words: `high`, `max`, `off` and so on. Each
model has its own list. See [Efforts](/user/efforts).

## Environment

Where a session's work lands: this directory, another directory, or a directory on another
machine. A flow declares the ones it needs, and most need only this directory. See
[Remote execution](/user/remote-execution) and [Containers](/user/containers).

## Epic

One run of one flow, written down as it happens: the flow, its agents, and every session they
opened. `/epics` lists the runs of this directory. See [Tracing](/user/tracing) and
[Picking a run up](/user/resuming).

## Flow

The loop: Python that says which agent is asked what, in what order, and when to stop. You
choose one at `/flow` or name it with `$`. See [Your first run](/user/first-run) and
[Flows](/flows/).

## Flowverse

A git repository of flows. `official` is humanize's own; add others at `/flowverses`. Its flows
are named `<flowverse>/<flow>`, and humanize's own by their bare names. See
[Flowverses](/weaver/flowverses).

## Outworlder

You, as a flow sees you: whoever is at the prompt, when the flow asks something. `/afk` says
you are away. See [Being away](/user/afk).

## Permission

What an agent may touch, declared by the flow for each role: its working directory, the rest
of the home directory, the machine, and the web. See [Permissions](/user/permissions) and
[Security](/user/security).

## Provider

A named account for one backend, kept apart from the CLI's own login: a login, an API key, or a
gateway. It is the `provider` row of an agent, where `as local` means the CLI as you signed it
in. See [Providers](/user/providers).

## Role

A named slot a flow declares, such as `agent`, `builder` or `reviewer`. You give each agent
role an agent; the flow says what the role is for and what it may touch. See [Your first
run](/user/first-run).

## Session

One conversation with one agent, kept across its turns. When to start a fresh one is the
biggest choice a flow makes, because it decides what the agent remembers: a Ralph loop starts a
new session every round, so the agent starts from the task each time. See
[Many conversations at once](/user/conversations).

## Trace

A whole run as one timeline, which you open in Perfetto. See [Tracing](/user/tracing).

## Turn

One exchange with the model: it is told something, works with its tools, and answers. A line
you type while a turn is running goes into that turn. See [Talking to a running
turn](/user/steering).

## Weaver

Whoever writes a flow. The [Weaver Guide](/weaver/) is for them; the User Guide never asks for
Python.

## Workspace

The directory `hmz` runs in. What is remembered, the run you can leave and come back to, and
the runs `/epics` lists all belong to one workspace. See
[What a project remembers](/user/settings).

---

Writing a flow of your own? The [flow API](/reference/flows) has the Python.
