# CI

In this guide you read what CI ran on your change, and why, and fix what it failed. Every push
and pull request runs `.github/workflows/ci.yml`, and how much of it runs grows with how close
the change is to `main`.

Wait for one check: **`ci-ok`**. It is green when every job that ran passed. A job the change
did not need is skipped, and a skipped job does not count against it. Only a run headed for
`main` reports `ci-ok`; the others report `ci-ok (push tier)` or `ci-ok (pr tier)`, so the
quick run a push to your branch starts can never pass for the one your pull request needs.

## How it works

Three things decide which jobs run: where the change is going, what it touched, and whether
the jobs before it passed.

| The change is | Runs | On |
| --- | --- | --- |
| a push to a branch | `lint`, `unit` | Linux, Python 3.12 |
| a pull request into a branch other than `main` | and `workflows`, `typecheck`, `integration` | Linux, Python 3.12 |
| a pull request into `main`, the merge queue, a push to `main`, nightly, or a run by hand | and `system`, `build`, `smoke`, `docs`, `coverage`, `dependency-review` | Linux and macOS, Python 3.12, 3.13 and 3.14 |

A job runs only when the change touched what it checks. A change to `docs/` alone runs `lint`
and `docs` and nothing in Python, and a change to Python alone does not build the site. The
nightly run and a run by hand check everything.

Each job waits for the ones it hangs off, so a change that fails to lint never takes a runner
for its tests:

```text
plan ─▶ changes ─┬─▶ lint ────────┬─▶ typecheck ─▶ unit ─▶ integration ─▶ system ─▶ coverage
                 ├─▶ workflows ───┘
                 ├─▶ lint ─▶ build ─▶ smoke
                 └─▶ docs
plan ─▶ dependency-review
every job ─▶ ci-ok
```

| Job | Checks | Run it yourself |
| --- | --- | --- |
| `lint` | Every pre-commit hook but `actionlint`, `zizmor` and `pyright`, which are the next two jobs | `uv run pre-commit run --all-files` |
| `workflows` | `actionlint` and `zizmor` over `.github/` | `uv run pre-commit run actionlint --all-files`, and the same for `zizmor` |
| `typecheck` | `pyright`, strict | `uv run pyright` |
| `unit` | `tests/unit` | `uv run pytest tests/unit` |
| `integration` | `tests/integration` | `uv run pytest tests/integration` |
| `system` | `tests/system`, on Linux, without `--run-agents` | `uv run pytest tests/system` |
| `coverage` | Every test job's coverage, added up | |
| `build`, `smoke` | The package builds and PyPI would take it; the wheel, with no extras, starts on each system and Python | `uv build` |
| `docs` | The site builds, every `#fragment` resolves, every word is legible on a phone. A push to `main` builds and deploys it from `build-docs.yml` instead | [Working on these docs](/contributing/docs) |
| `dependency-review` | No dependency the pull request adds has a known vulnerability | |

The `system` runner has docker, a docker swarm and `ssh localhost`, and no coding agent CLI. A
test that needs a real CLI skips there, and every test that waits for `--run-agents` does too:
those, and [the regression matrix](/contributing/regression-matrix), are yours to run.

## Read a run

```sh
gh pr checks --watch        # every job on your pull request, until they finish
gh run view --log-failed    # the log of what failed, from the last run
```

The run's summary page on GitHub says which tier it ran as, and, in the full tier, the total
coverage with a table by file. The whole report is the run's `coverage` artifact.

## Fix what failed

- **`lint`** prints the diff each hook wants. Run `uv run pre-commit run --all-files`, commit
  what it changed, and push.
- **A test that passes here fails on another Python.** Run the tier on that Python, in an
  environment of its own: `uv run --isolated --all-extras --python 3.14 pytest tests/unit`.
- **A test fails on macOS alone.** Run it on a Mac, or ask on the pull request for somebody
  who has one.
- **`system` skips a test that runs on your machine.** It needs something that runner has not
  got, and the summary at the end of the job's log says what. A skip is not a failure.
- **A pull request has no `ci-ok` after you moved it onto `main`.** The tier is read when a
  run starts, and the last one ran for the old base. Push again to start one for `main`.

## Other workflows

None of these reports to `ci-ok`. On a pull request, wait for `title` from `triage.yml` too.

| Workflow | Runs on | Does |
| --- | --- | --- |
| `build-docs.yml` | a push to `main` that changed `docs/` | Builds the site and deploys it. Every other run reaches it as `ci.yml`'s `docs` job |
| `triage.yml` | every pull request, and a push to `main` that changed `labels.yml` | `title` checks the title is a Conventional Commit, `label` labels the pull request from it and from its paths, and `labels` syncs `labels.yml` to the repository |
| `codeql.yml` | a pull request into `main`, a push to it, and weekly | Scans the Python and the workflows, into the repository's Security tab |
| `scorecard.yml` | a push to `main`, and weekly | Scores the repository against the [OpenSSF Scorecard](https://scorecard.dev) checks, into the Security tab |
| `publish.yaml` | a published release, or a dry run by hand | Builds the package and publishes it to PyPI: [Releasing](/contributing/releasing) |

## Next steps

- [Contributing](/contributing/), for the checks to run before you push
- [Your first patch](/contributing/tutorials/first-patch), a change taken all the way through CI
- [The regression matrix](/contributing/regression-matrix), for what CI never runs
