# humanize

Flows of coding agents, and the runs of them. This is the contract for the tree itself: what
each package is answerable for, how they may name one another, and what the top of the
package offers. Each package has a spec of its own under the path it is written at; a package
no file is named for is bound by the nearest one above it.

## API

```python
# __init__.py
def home() -> pathlib.Path: ...
```

- `home` MUST answer where humanize keeps what outlives one run of one flow, MUST be
  overridable per machine by `HUMANIZE_HOME`, and MUST NOT create the directory.
- The top of the package MUST expose `home` and nothing else.

## Packages

| Package | Answerable for | Spec |
| --- | --- | --- |
| `coganchor` | Everything humanize knows about driving a coding agent CLI, and the anchor that puts its work on another machine | [coganchor/SPEC.md](coganchor/SPEC.md) |
| `flows` | The whole of what a flow imports, and nothing besides | [flows.md](flows.md) |
| `runtime` | What a run is: finding the flow, driving it, writing it down, reading it back | [runtime/SPEC.md](runtime/SPEC.md) |
| `cli` | The command line | [cli.md](cli.md) |
| `daemon` | Holding a run where a terminal closing cannot end it | [daemon.md](daemon.md) |
| `tui` | The terminal interface | [tui.md](tui.md) |
| `sdk` | The way in from outside | [sdk.md](sdk.md) |

## Requirements

### The tree

- Nothing but `__init__.py` and `__main__.py` MUST sit at the top of the package; everything
  else MUST be inside the package whose question it answers.
- Every module MUST be named for what it holds.
- No package below the ways in MUST have a command line of its own. `cli` MUST be the whole
  of it, one module per command.
- `python -m hmz` MUST be `hmz`.

### What each layer is

- `coganchor` MUST be the whole of what humanize knows about driving a coding agent CLI —
  what each one is, driving it, which account it runs as, which machine its turns land on,
  where a turn goes when the place taking it cannot, what its tokens cost, and the anchor
  that puts its work on another machine — and MUST offer that as one capability. No layer
  above it MUST reach past it to a driver.
- `runtime` MUST be what a run is, MUST drive no coding agent itself, and MUST offer the
  whole of what humanize can be asked to do in a workspace as one object.
- `flows` MUST be the whole of what a flow imports and nothing besides, and MUST be types:
  the protocols a flow's agents, environments, sessions and context answer to, and the values
  a flow writes or catches. The objects a flow is handed MUST be the runtime's, answering to
  those protocols structurally. Everything humanize does *to* a flow MUST be `runtime/flowing`
  instead.
- `cli`, `daemon` and `tui` MUST each be a way of reaching the runtime's one object rather
  than a second copy of what it does. Anything two of them would otherwise each have written
  MUST be written in `runtime` instead, so that a thing which can be done one way can be done
  every way and is refused the same way whichever way it was asked.
- `sdk` MUST be the way in from outside, MUST offer both ways of reaching a run, and MUST
  compose nothing.

### How layers may name one another

- Each layer MUST import only its own subtree, `hmz` itself, and the layers listed for it in
  `tests/integration/layering/test_layering.py`, which MUST hold the table.
- No two layers MUST name each other, but for one pair: `flows` MAY hand `flow`, `load` and
  `Outworlder.new` to `runtime/flowing`, importing it inside the call and never at import.
  `flows` MUST import nothing else of humanize, and MUST be checked to do so rather than taken
  on trust.
- `_legacy_flows` is the previous flow API, kept whole until every way in has moved to
  `flows`. It MAY go on naming `coganchor`, and pairing with `runtime/flowing`, as it did
  under the old name; nothing new MUST import it, and it MUST go when nothing does.
- `cli` MUST reach `runtime` by name. `tui` MUST reach it through `daemon`, and `daemon` MUST
  offer it. `sdk` MUST be named by no layer.
- `coganchor/serve` — the half that ships to a target of any architecture — MUST name the
  wire protocol and nothing else of `coganchor`.
- Any layer MAY name `runtime/telemetry`, which MUST name nothing above itself.
- Everything MUST be reached from inside the call that needs it rather than at the top of a
  module, so that a way in pays for the layers it asks and not the ones beside them.

### What ships to a target

- What the anchor carries MUST be the serving half alone. The drivers, the facts about them,
  the accounts and the prices MUST NOT be in the bundle.
