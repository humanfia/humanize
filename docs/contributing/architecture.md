---
pageClass: hmz-feature
---

# Architecture

This page is where you find out where a change goes before you write it: which layer of
`src/hmz/` it belongs in, what that layer may import, and, for the two changes that touch many
layers at once, a backend and a command, every file to visit in order.

::: info Before you start
- A checkout set up as in [Contributing](/contributing/).
- For a first, small change, [Your first patch](/contributing/tutorials/first-patch) is the
  gentler way in.
:::

## How the layers work

`src/hmz/` is a stack of layers, and code in each layer may import only the layers the table
below gives it. Pick a layer to see what it may import and open its SPEC. A test holds the
same table, so an import that breaks it fails the run.

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
| who is outside a run: claims, away, questions, lines said to agents, asides | `runtime/doing/hosting.py` |
| a slash command, a key, a menu; what the interface draws of a message | `tui/` |
| runs kept going after the terminal closes, and the socket frontends reach them over | `daemon/` |
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
  machine, which may be any architecture, so it may import `coganchor.proto`, and
  `coganchor.fence` with the `coganchor.linux` bindings it is put up with, and nothing else.

To add a layer or an edge, edit `ALLOWED` in that test. The diagram above copies it, so change
`docs/.vitepress/theme/components/HmzStack.vue` in the same commit.

One rule no test checks: **import another layer inside the function that needs it**, not at
the top of the module, so `hmz exec` pays only for what it uses. Ruff's `PLC0415` is off for
this.

## Adding a backend

A backend is one coding agent CLI humanize drives. Adding one touches most layers, so do it in
the order below, with a test run after each group. The walk-through follows how MiniMax Code,
`mcode`, was added, in one commit: `git show --stat c3c1e6a` lists every file it touched.

::: tip An ACP CLI needs no code
A CLI that speaks the Agent Client Protocol can be added from the interface, on the Accounts
page of `/settings`.
:::

**You need:** the CLI installed and signed in, so the system tier can drive it; its `--help`
and a turn or two of its own logs, since several steps copy what it really writes; and which
kind of driver it needs, which `specs/coganchor/agents.md` says.

### 1. Describe it, in `coganchor/`

1. **A `Profile` in `coganchor/backends.py`**: its name and `aliases`, its home (`home_var`,
   `home_dir`), the `logs` one session writes as globs taking `{ident}`, its `efforts`, the
   `sessions` paths a turn keeps, `skills`, `creds`, the `ways` in, the `hosts` it must reach,
   and the line that `installs` it. Add it to `PROFILES`.

   ```python
   Profile(
       name="mcode",
       aliases=("mcode", "minimax", "minimax-code"),
       home_var="MINIMAX_DATA_DIR",
       home_dir=".minimax",
       logs=("v2/sessions/*/*/*/*-session_{ident}/messages.jsonl",),
       encodes=True,  # [!code highlight]
       ...
   )
   ```

   Set `encodes=True` when the CLI names a session's files by its id in URL-safe base64
   rather than by the id itself, as MiniMax Code does. Whatever looks for a session's logs
   asks `profile.logged(ident)`, which answers the globs with the id spelled the way the CLI
   spells it, and never formats `logs` itself.
2. **A driver in `coganchor/agents/<name>.py`.** Subclass `CommandSessionBase` when a turn is
   one run of a command (`mcode exec` is), or `StreamSessionBase` when it is one long-lived
   process spoken to a line at a time. Declare on the agent class, as `counts`, the kinds of
   token it reports, named as `KINDS` in `coganchor/agents/event.py` names them.
3. **A row of `DRIVEN` in `coganchor/agents/__init__.py`**, and the driver's classes in its
   `__all__`:

   ```python
   "mcode": (MiniMaxCodeAgent, MiniMaxCodeAgentConfig),
   ```

4. **A way of asking which models it runs**: a function in `_READING` in `coganchor/models.py`.
   `mcode`'s reads `mcode provider list --json`.
5. **Its state paths**: an `AgentProfile` in `coganchor/statepaths.py`.

   ```python
   AgentProfile(
       name="mcode",
       state_paths=("~/.minimax", "~/.mavis"),
   ),
   ```

### 2. Offer it to flows, in `flows/`

6. **A `HarnessKind`, a protocol and a row of `HARNESS_AGENTS`** in `flows/agents.py`. The
   protocol carries exactly the mixins the CLI serves, and is exported from `flows/agents.py`
   and `flows/__init__.py`:

   ```python
   class HarnessKind(StrEnum):
       ...
       MCODE = "mcode"


   class MiniMaxCodeAgent(
       Agent, SubagentStartHookAgentMixin, SubagentStopHookAgentMixin, Protocol
   ):
       """MiniMax Code, with everything it can do."""
   ```

   `tests/unit/flows/test_harness_table.py` and `tests/unit/flows/test_harness_mapping.py`
   each want a row for it, and `tests/flows/contracts.py` holds its driver to what the engine
   expects. A change here also checks
   [humanfia/flowverse](https://github.com/humanfia/flowverse) still works.

### 3. Read it back, in `runtime/tracing/` and `tui/`

7. **A trace reader** in `runtime/tracing/readers/<name>.py`, and its row in
   `runtime/tracing/collector.py`.
8. **The live tally**: what its log calls each kind of token, as a row of `_KINDS` in
   `tui/tally.py`, and a branch in `_spent` there, so the tally moves during a turn. The same
   kinds are listed per backend in `tests/unit/backends/test_catalogue.py`.

### 4. Test it

9. **A stand-in for the integration tier**: its flag table in `tests/agents/standins.py`, read
   off the real CLI's `--help`, then `tests/integration/agents/test_<name>.py`.
10. **The system tier**: `tests/system/agents/test_<name>.py`, driving the real CLI.
11. **The regression matrix**: its places in `tests/matrix/places.py`. See [The regression
    matrix](/contributing/regression-matrix#add-a-cli).

### 5. Say so

12. **The docs pages and components that list or count the backends.** Search for an existing
    backend's name and add yours beside it:

    ```sh
    grep -rln mimo docs --include='*.md' --include='*.vue' --exclude-dir=node_modules
    ```

    Where a SPEC lists the backends too, propose the change: do not edit a SPEC unless you were
    asked to.

### Check it worked

```sh
uv run pytest tests/unit/flows/test_harness_table.py tests/unit/flows/test_harness_mapping.py \
    tests/unit/backends/test_catalogue.py tests/integration/agents/test_minimax.py \
    tests/integration/layering
```

```text
213 passed in 3.46s
```

`tests/integration/layering` is the one that fails when a step imported across a layer it may
not. Then the real thing, which spends tokens:

```sh
uv run pytest tests/system/agents/test_minimax.py --run-agents
uv run pytest tests/system/matrix --run-agents -m matrix -k mcode
```

## Adding a command

1. **A module under `cli/`** if it takes a parser of its own, and a thin wrapper in
   `cli/__init__.py`.
2. **An entry in `COMMANDS`.** A line humanize runs for itself, rather than one a person types,
   goes in `INTERNAL` instead, which `hmz internal` routes.
3. **Its output through `cli/output.py`** where the command has a `--json`, so a stray `print`
   never lands in the stream a program reads.

Check it with `uv run hmz --help`, which lists every entry of `COMMANDS`, and with
`uv run hmz <command> --help`.

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
| `specs/daemon.md` | Holding every workspace's runs on a machine apart from a terminal, for the frontends that read them |
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

## Next steps

- [The regression matrix](/contributing/regression-matrix), after a change that reaches more
  than one CLI
- [Working on these docs](/contributing/docs), for the pages a change updates
- [Reference › Agents](/reference/agents), for what each backend does, as users read it
