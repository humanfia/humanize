<script setup>
import ChangePath from '../.vitepress/theme/components/contributing-index/ChangePath.vue'
</script>

# Contributing

Pull requests are welcome. This page gets a checkout of humanize ready to change: installed,
checked the way CI checks it, and with the rules every change is held to. Bugs and feature
requests go through the [issue forms](https://github.com/humanfia/humanize/issues/new/choose);
for a large change, open a feature request first.

How a pull request is proposed and reviewed is in
[CONTRIBUTING.md](https://github.com/humanfia/humanize/blob/main/CONTRIBUTING.md), and who
decides, and how to become a reviewer or maintainer, in the organization's
[GOVERNANCE.md](https://github.com/humanfia/.github/blob/main/GOVERNANCE.md). Everyone taking
part follows the [Code of Conduct](https://github.com/humanfia/.github/blob/main/CODE_OF_CONDUCT.md).

<ChangePath />

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
setup, run one package's unit tests:

```sh
uv run pytest tests/unit/flows
```

## The checks

::: code-group

```sh [Before you push]
uv run pre-commit run --all-files   # format, lint, types: seconds
uv run pytest                       # unit and integration: minutes
```

```sh [While you write]
uv run pytest tests/unit/<package>  # the fast loop
```

```sh [When a system test covers it]
uv run pytest tests/system/test_flows_ralph.py   # real agents, real tokens
```

:::

Both commands under **Before you push** must pass, and they are what CI runs. `uv run pytest`
runs `tests/unit` and `tests/integration`, and leaves `tests/system` out.

| | Your machine | CI |
| --- | --- | --- |
| the pre-commit hooks | ✓ | ✓ `lint`, every push and pull request |
| `tests/unit/` | ✓ | ✓ a job per package, on Linux and macOS |
| `tests/integration/` | ✓ | ✓ a job per topic, on Linux and macOS |
| `tests/system/` | ✓ by hand, a file at a time, when your change needs it | never |

[CI](/contributing/ci) has every job, and how to read a run.

## Where a test goes

A test goes in exactly one of three directories, by how much of humanize it puts together. Its
directory is what decides when it runs: no marker to write.

| | Holds | Rules |
| --- | --- | --- |
| `tests/unit/<package>/` <Badge type="tip" text="CI" /> | One package of `src/hmz/` alone, in the directory named for it: `cli`, `coganchor`, `daemon`, `flows`, `runtime`, `sdk` or `tui` | Only the package's public names, never a `_private` name or module. Every other `hmz` package mocked. No subprocess, socket or network. A job of its own must finish in 3 minutes |
| `tests/integration/test_<topic>_*.py` <Badge type="tip" text="CI" /> | Packages wired together against fakes this repository wrote: a stand-in CLI, a fake app server, a loopback socket, the mock LLM service | Flat, no subdirectories. The topic is one of `core`, `agents`, `tui`, `daemon` and `anchor`, a job each, which must finish in 10 minutes |
| `tests/system/` <Badge type="warning" text="you" /> | Real agents on real tasks: an installed coding agent CLI, signed in, working on `tests/system/sample/`, with docker or ssh where the test needs them | 5 to 30 minutes and real tokens a test. Never in CI |

`ruff`'s `SLF001` and `pyright`'s `reportPrivateUsage` fail a test that reaches a private name.
Mock another package where the test imports it, so the test holds this package to what it
promises rather than to what the others happen to do.

**Run a system test only when your change touches the path it covers**, such as a backend's
driver, a built-in flow or a machine, and before a release. Never all of them on every change:
they take hours together and spend real money. Name the file, as under **When a system test
covers it** above; each is named `test_<area>_<what>.py`, for `flows`, `harness`, `machines`
or `tui`. A test skips, saying why, where what it needs is not on this machine: a CLI, its sign-in,
docker, ssh.

::: danger Never copy a sign-in into a test's home
Codex's ChatGPT login and Claude Code's subscription login renew themselves, and a renewal
cancels the token the other copies hold: a container or temporary home signed in with a copy of
`~/.codex/auth.json` or `~/.claude/.credentials.json` signs your machine out. A test that needs
one runs the CLI as local, or mounts the CLI's own home where it is (`--volume=DIR:DIR`). The
run fails if any file under pytest's temporary directories holds one of those refresh tokens
(`_copies_no_sign_in` in `tests/conftest.py`).
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
- **A change to how flows run** also keeps the flows
  [humanfia/flowverse](https://github.com/humanfia/flowverse) lists working.
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
| hold a page to the rules | [Working on these docs](/contributing/docs) |
