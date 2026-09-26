# Contributing

Pull requests are welcome. For a large change, open an
[issue](https://github.com/humanfia/humanize/issues) first.

::: tip First time here?
[Your first patch](/contributing/tutorials/first-patch) takes one small change from clone to
pull request, with every command written out.
:::

## Set up

You need `git` and [`uv`](https://docs.astral.sh/uv/). `uv sync` brings Python with it.

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync                    # the environment, from uv.lock
uv run pre-commit install  # check each commit before it is made
```

Run tools through `uv run`, not `uvx`, so you get the versions `uv.lock` pins.

## The checks

::: code-group

```sh [Before you push]
uv run pre-commit run --all-files   # format, lint, types: seconds
uv run pytest                       # every tier: minutes
```

```sh [While you write]
uv run pytest tests/unit            # the fast loop
```

```sh [When the system tier covers it]
uv run pytest tests/system --run-agents   # real tokens
```

:::

Both commands under **Before you push** must pass. `uv run pytest` runs every tier. A system
test this machine cannot serve skips and says why in the summary, and the ones that drive a
real coding agent CLI wait for `--run-agents`.

Run the system tier by hand when your change is one it covers. Its directories name the parts
it drives for real: `agents/`, `coganchor/`, `machines/`, `providers/` and the rest. It drives
the CLIs signed in on your machine and spends real tokens, so nothing else runs it for you.

| | Your machine | CI |
| --- | --- | --- |
| the pre-commit hooks | ✓ | ✓ |
| `tests/unit/`, `tests/integration/` | ✓ | ✓ Python 3.12, Linux |
| `tests/system/` | ✓ with `--run-agents` for the real CLIs | never |

## Where a test goes

File a test by what is on the other side of it. Its directory is its tier: no marker to write.

| | The test talks to |
| --- | --- |
| `tests/unit/` <Badge type="tip" text="CI" /> | `hmz`, and nothing else |
| `tests/integration/` <Badge type="tip" text="CI" /> | Anything this repository wrote: a stand-in CLI, a fake app server, a loopback socket, the mock LLM service |
| `tests/system/` <Badge type="warning" text="you" /> | The real thing: an installed coding agent CLI, ptrace, docker, ssh, a real `node` |

`tests/test_tiers.py` fails the run if a test's marker and its directory disagree.

::: details Splitting a test file across two tiers
Helpers and a subsystem's fixtures stay where they are: `tests/stubs.py`,
`tests/agents/standins.py`, `tests/tui/fixtures.py` and the rest. A test that moves into a
tier takes the fixtures it needs back by name, in a `conftest.py` beside it. Re-export the
autouse ones too: nobody asks for those by name, so a missing one fails green. What two halves
of a split file share goes in a helper module that never moves. `tests/tiers.py` has the
whole of it.
:::

## What the code is held to

- **`pyright` in strict mode**, over `src` and `tests`. `# type: ignore` is switched off: a
  suppression names a pyright rule.
- **`ruff` with every rule on**, less the ones `pyproject.toml` gives a written reason for.
- **Google-style docstrings**, and type annotations everywhere.
- **Popular, well-maintained libraries** before a custom implementation.
- **Each layer imports only what the layering table gives it.** See
  [Architecture](/contributing/architecture).
- **`specs/` is the contract.** Change the code to match a SPEC. Do not edit one unless you
  were asked to.
- **A change to how flows run** also keeps
  [humanfia/flowverse](https://github.com/humanfia/flowverse) working.
- **A change to behaviour updates the docs** in the same pull request.
  [Working on these docs](/contributing/docs) has the rules.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `fix(agents): …`,
`docs(contributing): …`, with a `!` before the colon for a breaking change. A change and its
tests go in one commit.
