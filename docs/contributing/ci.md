# CI

In this guide you read what CI ran on your change, and fix what it failed. Every push to `main`
and every pull request runs `.github/workflows/ci.yml`, again whenever the pull request's title
is edited, and it runs the same jobs every time.

Wait for one check: **`ci-ok`**. It is green when every other job in the run passed, and it is
the one check a branch rule needs.

## How it works

`title`, `lint`, `package` and the tests start together. The tests are two matrices, each a job per part
and per system, so no job waits on another and each stays short:

```text
title ─────────────────────────────────────────┐
lint ──────────────────────────────────────────┤
package ───────────────────────────────────────┤
unit         7 packages × Linux, macOS ────────┼─▶ ci-ok
integration  5 topics   × Linux, macOS ────────┘
```

| Job | Checks | Run it yourself |
| --- | --- | --- |
| `title` | The pull request's title is a [Conventional Commit](/contributing/#commits): squashing writes it to `main`, and a release's notes are those titles. Skipped on a push, which has no pull request | |
| `package` | The wheel and the sdist build, and PyPI would render `README.md`, so any commit can be [released](/contributing/releasing) | `uv build --no-sources && uvx twine check --strict dist/*` |
| `lint` | Every pre-commit hook: `ruff`, `pyright` strict, `actionlint` and `zizmor` over `.github/`, and the file hygiene | `uv run pre-commit run --all-files` |
| `unit (<os>, <package>)` | `tests/unit/<package>`, for each of `cli`, `coganchor`, `daemon`, `flows`, `runtime`, `sdk` and `tui` | `uv run pytest tests/unit/<package>` |
| `integration (<os>, <topic>)` | `tests/integration/test_<topic>_*.py`, for each of `core`, `agents`, `tui`, `daemon` and `anchor` | `uv run pytest tests/integration/test_<topic>_*.py` |
| `ci-ok` | Every job above passed, or `title` was skipped | |

Every job runs on Python 3.12, from the environment `uv.lock` pins with every extra; the tests
run on Linux and macOS. `tests/system` is never run here: it drives real agents for minutes a
test and spends real tokens, so it is yours to run when your change needs it. [Where a test
goes](/contributing/#where-a-test-goes) says when.

A new package under `src/hmz/` takes a row in `unit`'s matrix, and a new topic a row in
`integration`'s. A file named for no topic in the matrix runs in no job.

## How long it takes

Each job has a budget for its tests alone, not counting setup:

| Job | Budget |
| --- | --- |
| `unit`, each package | 3 minutes |
| `integration`, each topic | 10 minutes |

Each job prints its slowest tests at the end of its log (`--durations`). A package or topic
past its budget is split, or its slowest tests made faster, before more is added to it.

The tests run in parallel inside a job too, through `pytest-xdist`. `tests/unit` computes, and
takes a worker per core (`-n auto`). `tests/integration` mostly waits on a subprocess, a socket
or a pseudoterminal, so its jobs set `PYTEST_XDIST_AUTO_NUM_WORKERS` to twice the runner's
vCPUs. To run a topic as CI does on a machine like yours:

```sh
PYTEST_XDIST_AUTO_NUM_WORKERS=$((2 * $(getconf _NPROCESSORS_ONLN))) \
  uv run pytest tests/integration/test_agents_*.py
```

## Read a run

```sh
gh pr checks --watch        # every job on your pull request, until they finish
gh run view --log-failed    # the log of what failed, from the last run
```

A job's name says what it ran: `unit (macos-latest, tui)` is `tests/unit/tui` on macOS.

## Fix what failed

- **`title`** says what is wrong with the title. Edit the pull request's title, and the run
  starts again.
- **`lint`** prints the diff each hook wants. Run `uv run pre-commit run --all-files`, commit
  what it changed, and push.
- **A `unit` or `integration` job.** Run the same command from the table above. Only that
  job's tests ran, so a test that leans on another package's or topic's tests fails here and
  not in a plain `uv run pytest`: make it stand alone.
- **A test fails on macOS alone.** Run it on a Mac, or ask on the pull request for somebody
  who has one.

## Other workflows

Neither reports to `ci-ok`.

| Workflow | Runs on | Does |
| --- | --- | --- |
| `build-docs.yml` | a pull request or a push to `main` that changed `docs/` | Builds the site, checks every `#fragment` resolves and every word is legible on a phone, and on `main` deploys it: [Working on these docs](/contributing/docs) |
| `publish.yml` | a maintainer publishing a GitHub release | Checks the tag, builds the wheel and sdist with its version, and publishes them to PyPI: [Releasing](/contributing/releasing) |

## Next steps

- [Contributing](/contributing/), for the checks to run before you push and where a test goes
- [Your first patch](/contributing/tutorials/first-patch), a change taken all the way through CI
