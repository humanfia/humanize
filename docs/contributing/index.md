# Contributing

Pull requests are welcome. This page gets a checkout of humanize ready to change: installed,
checked the way CI checks it, and with the rules every change is held to. Bugs and feature
requests go through the [issue forms](https://github.com/humanfia/humanize/issues/new/choose);
for a large change, open a feature request first.

How a pull request is proposed and reviewed is in
[CONTRIBUTING.md](https://github.com/humanfia/humanize/blob/main/CONTRIBUTING.md), and who
decides, and how to become a reviewer or maintainer, in
[GOVERNANCE.md](https://github.com/humanfia/humanize/blob/main/GOVERNANCE.md). Everyone taking
part follows the [Code of Conduct](https://github.com/humanfia/humanize/blob/main/CODE_OF_CONDUCT.md).

::: tip First time here?
[Your first patch](/contributing/tutorials/first-patch) takes one small change from clone to
pull request, with every command written out.
:::

::: info Before you start
`git` and [`uv`](https://docs.astral.sh/uv/). Nothing else: `uv sync` brings Python with it.
:::

## Set up

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync                    # ①
uv run pre-commit install  # ②
```

1. **`uv sync`** makes the project's environment in `.venv`, exactly as `uv.lock` pins it,
   Python included.
2. **`pre-commit install`** checks each commit before it is made, with the hooks CI runs.

Run tools through `uv run`, not `uvx`, so you get the versions `uv.lock` pins. To check the
setup, run the fast tier:

```sh
uv run pytest tests/unit
```

```text
2405 passed in 15.51s
```

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
it drives for real: `agents/`, `coganchor/`, `machines/`, `providers/` and the rest. CI runs it
too, on Linux with docker and no coding agent CLI, so the tests that drive the CLIs signed in
on your machine, and spend real tokens, are yours alone to run. Before a release, or after a
change that could reach more than one CLI, run
[the regression matrix](/contributing/regression-matrix): every feature through every CLI.

| | Your machine | CI |
| --- | --- | --- |
| the pre-commit hooks | ✓ | ✓ every push; `pyright` and the workflow linters from a pull request on |
| `tests/unit/` | ✓ | ✓ every push |
| `tests/integration/` | ✓ | ✓ every pull request |
| `tests/system/` | ✓ with `--run-agents` for the real CLIs | ✓ on the way to `main`: Linux, no CLIs |

On the way to `main`, the tests run on Linux and macOS, on Python 3.12, 3.13 and 3.14.
[CI](/contributing/ci) has which job runs when, and how to read a run.

## Where a test goes

File a test by what is on the other side of it. Its directory is its tier: no marker to write.

| | The test talks to |
| --- | --- |
| `tests/unit/` <Badge type="tip" text="CI" /> | `hmz`, and nothing else |
| `tests/integration/` <Badge type="tip" text="CI" /> | Anything this repository wrote: a stand-in CLI, a fake app server, a loopback socket, the mock LLM service |
| `tests/system/` <Badge type="tip" text="CI" /> <Badge type="warning" text="you" /> | The real thing: an installed coding agent CLI, ptrace, docker, ssh, a real `node` |

`tests/test_tiers.py` fails the run if a test's marker and its directory disagree.

::: danger Never copy a sign-in into a test's home
Codex's ChatGPT login and Claude Code's subscription login renew themselves, and a renewal
cancels the token the other copies hold: a container or temporary home signed in with a copy of
`~/.codex/auth.json` or `~/.claude/.credentials.json` signs your machine out. A test that needs
one runs the CLI as local, or mounts the CLI's own home where it is (`--volume=DIR:DIR`). The
run fails if any file under pytest's temporary directories holds one of those refresh tokens
(`_copies_no_sign_in` in `tests/conftest.py`).
:::

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
- **`specs/` is the contract.** Change the code to match a SPEC. Do not edit one unless you were
  asked to.
- **A change to how flows run** also keeps
  [humanfia/flowverse](https://github.com/humanfia/flowverse) working.
- **A change to behaviour updates the docs** in the same pull request.
  [Working on these docs](/contributing/docs) has the rules.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `fix(agents): …`,
`docs(contributing): …`, with a `!` before the colon for a breaking change. A change and its
tests go in one commit.

## Next steps

| To | Read |
| --- | --- |
| make a first, small change end to end | [Your first patch](/contributing/tutorials/first-patch) |
| add or change a page of these docs | [Add a page to these docs](/contributing/tutorials/a-page-of-docs) |
| find where a change goes, or add a backend or a command | [Architecture](/contributing/architecture) |
| read what CI ran on a change, and why | [CI](/contributing/ci) |
| run every feature through every CLI | [The regression matrix](/contributing/regression-matrix) |
| hold a page to the rules | [Working on these docs](/contributing/docs) |
