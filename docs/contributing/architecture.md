---
pageClass: hmz-feature
---

# Architecture

`src/hmz/` is a stack of layers, and code in each layer may import only the layers the table
below gives it. Pick the layer your change belongs in and see what it may import. A test
holds the same table, so an import that breaks it fails the run.

<HmzStack />

## Where a change goes

| You are changing | Put it in |
| --- | --- |
| how a coding agent CLI is driven, or its accounts, models, fallbacks or prices | `coganchor/` |
| the machine an agent's turns land on | `coganchor/machines/`, per [Machines](/reference/machines#writing-a-machine-of-your-own) |
| a type, mixin, hook or error a flow imports | `flows/`, then check [humanfia/flowverse](https://github.com/humanfia/flowverse) still works |
| how a flow runs: the engine, budgets, resuming, the harness and environment drivers | `runtime/flowing/`, then check humanfia/flowverse too |
| the `hmz exec` line: a flag, a refusal | `runtime/runner.py` |
| what a run writes down | `runtime/epic.py` |
| reading a backend's logs back as a trace | `runtime/tracing/` |
| anything two of `cli`, `tui` and `daemon` would each need | `runtime/doing/`, once |
| a slash command, a key, a menu | `tui/` |
| a run kept going after the terminal closes | `daemon/` |
| a new command | `cli/` |
| the Python API another tool calls | `sdk/` |
| a flow humanize offers | [humanfia/flowverse](https://github.com/humanfia/flowverse). `flows/builtin/` holds `chat` alone |

Nothing sits at the top of `src/hmz/` but `__init__.py` and `__main__.py`. Name a module for
what it holds, in the words `hmz` and these docs use.

## The rules the test checks

`tests/integration/layering/test_layering.py` holds the table the diagram draws. The run fails
when:

- **A module imports what its layer may not.** Relative imports count the same as absolute
  ones. `from hmz.runtime import telemetry` names `telemetry`, not the whole of `runtime`.
- **Two layers name each other.** One pair may: `flows` calls into `runtime/flowing` from inside
  `flow`, `load` and `Outworlder.new`, and never at import. Importing `hmz.flows` must load
  nothing else of humanize, and that is checked too.
- **A top-level package is missing from the table.** `cli` is the one exemption.
- **The anchor's target half loads more than it may.** `coganchor/serve/` runs on the target
  machine, which may be any architecture, so it may import `coganchor.proto` and nothing else.

To add a layer or an edge, edit `ALLOWED` in that test. The diagram above copies it, so change
`docs/.vitepress/theme/components/HmzStack.vue` in the same commit.

One rule no test checks: **import another layer inside the function that needs it**, not at
the top of the module, so `hmz exec` pays only for what it uses. Ruff's `PLC0415` is off for
this.

## Adding a backend

::: tip An ACP CLI needs no code
A CLI that speaks the Agent Client Protocol can be added from the interface, at `/providers`.
:::

1. A `Profile` in `coganchor/backends.py`: its names, efforts, homes, log globs, credential
   paths, ways in and skill directories.
2. A driver in `coganchor/agents/`. Subclass `CommandSessionBase` when a turn is one run of a
   command, or `StreamSessionBase` when it is one long-lived process spoken to a line at a
   time. `specs/coganchor/agents.md` says which.
3. A row of `DRIVEN` in `coganchor/agents/__init__.py`.
4. A way of asking which models it runs, in `_READING` in `coganchor/models.py`.
5. Its state paths in `coganchor/statepaths.py`.
6. Its usage under the names in `KINDS` in `coganchor/agents/event.py`, with the ones it
   reports declared on the agent class as `counts`.
7. For flows to use it: a `HarnessKind`, a protocol in `flows/agents.py` carrying the mixins
   it serves, and a row of `HARNESS_AGENTS`. `tests/flows/contracts.py` holds its driver to
   what the engine expects.
8. Where its logs allow: a reader in `runtime/tracing/readers/`, and a branch in `_spent` in
   `tui/tally.py` so the tally moves during a turn.
9. A stand-in for the integration tier: its flag table in `tests/agents/standins.py`, read off
   the real CLI's `--help`.
10. The docs pages that list or count the backends.

## Adding a command

A module under `cli/` if it takes a parser of its own, a thin wrapper in `cli/__init__.py`,
and an entry in `COMMANDS`. A line humanize runs for itself, rather than one a person types,
goes in `INTERNAL`, which `hmz internal` routes. Where the command has a `--json`, write
through `cli/output.py`, so a stray `print` never lands in the stream a program reads.

## SPECs

`specs/` mirrors `src/hmz/`, and the file for your layer is its contract, in MUST and MUST NOT
terms. Pick a layer in the diagram to open its SPEC. Change the code to match the SPEC, and do
not edit a SPEC unless you were asked to. Propose a SPEC change separately.

::: details Every SPEC
| | |
| --- | --- |
| `specs/SPEC.md` | The tree, what each layer is, and how layers may name one another |
| `specs/cli.md` | Every command line |
| `specs/tui.md` | Every behaviour the interface must have |
| `specs/sdk.md` | How a tool that is not humanize reaches humanize |
| `specs/daemon.md` | Holding a run apart from a terminal, and the terminals that read one |
| `specs/runtime/SPEC.md` | What a run is, and what humanize remembers of one |
| `specs/runtime/doing.md` | humanize as one object: a workspace and everything doable in it |
| `specs/runtime/flowing.md` | What humanize does to a flow: the engine, the drivers, refs, resuming |
| `specs/runtime/tracing.md` | The collect API and what a trace must hold |
| `specs/flows.md` | The flow API: what a flow imports, declares and is handed |
| `specs/coganchor/SPEC.md` | Driving a coding agent CLI, and what an anchor entitles you to |
| `specs/coganchor/agents.md` | The agent and session contract every backend keeps |
| `specs/coganchor/providers.md` | Which account an agent runs as |
| `specs/coganchor/machines.md` | What a machine is |
| `specs/coganchor/serve.md` | The half that ships to a target |
| `specs/coganchor/linux.md` | What the anchor intercepts on the target |
:::
