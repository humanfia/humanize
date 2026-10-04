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
| a pull request into `main`, the merge queue, a push to `main`, nightly, or a run by hand | and `system`, `build`, `smoke`, `docs`, `coverage`, `dependency-review`, and `unit + integration` on macOS | Linux and macOS, Python 3.12, 3.13 and 3.14 |

A job runs only when the change touched what it checks. A change to `docs/` alone runs `lint`
and `docs` and nothing in Python, and a change to Python alone does not build the site. The
nightly run and a run by hand check everything.

The tests wait for `lint` and `typecheck`, so a change that fails either never takes a runner
for its tests. Past those two, the tiers start together, and none of them waits on another:

```text
plan ─▶ changes ─┬─▶ lint ──────┬─▶ typecheck ─┬─▶ unit ─────────────┬─▶ coverage
                 ├─▶ workflows ─┘              ├─▶ integration 1/2 ─┤
                 │                             ├─▶ integration 2/2 ─┤
                 │                             ├─▶ system ──────────┘
                 │                             └─▶ unit + integration on macOS
                 ├─▶ lint ─▶ build ─▶ smoke
                 └─▶ docs
plan ─▶ dependency-review
every job ─▶ ci-ok
```

A push's run has no `typecheck`, and its `unit` starts as soon as `lint` has passed.

| Job | Checks | Run it yourself |
| --- | --- | --- |
| `lint` | Every pre-commit hook but `actionlint`, `zizmor` and `pyright`, which are the next two jobs | `uv run pre-commit run --all-files` |
| `workflows` | `actionlint` and `zizmor` over `.github/` | `uv run pre-commit run actionlint --all-files`, and the same for `zizmor` |
| `typecheck` | `pyright`, strict | `uv run pyright` |
| `unit` | `tests/unit`, on Linux | `uv run pytest tests/unit` |
| `integration` | `tests/integration` on Linux, in two halves that take the same time | `uv run pytest tests/integration` |
| `unit + integration` | On macOS, `tests/unit` and then `tests/integration`, in one job per Python | The two above, on a Mac |
| `system` | `tests/system`, on Linux, without `--run-agents` | `uv run pytest tests/system` |
| `coverage` | The coverage of every tier on Linux and Python 3.12, added up | |
| `build`, `smoke` | The package builds and PyPI would take it; the wheel, with no extras, starts on each system and Python | `uv build` |
| `docs` | The site builds, every `#fragment` resolves, every word is legible on a phone. A push to `main` builds and deploys it from `build-docs.yml` instead | [Working on these docs](/contributing/docs) |
| `dependency-review` | No dependency the pull request adds has a known vulnerability | |

The `system` runner has docker, a docker swarm and `ssh localhost`, and no coding agent CLI. A
test that needs a real CLI skips there, and every test that waits for `--run-agents` does too:
those, and [the regression matrix](/contributing/regression-matrix), are yours to run.

## How long it takes

The full tier takes eight to nine minutes from `plan` to `ci-ok` when GitHub has runners free
for it, and the macOS jobs are what it waits on last. What each job took, in October 2026:

| Job | Takes |
| --- | --- |
| `plan` to the end of `typecheck` | 1 min 15 s |
| `unit` | 40 s to 1 min |
| `integration`, each half | 2 to 2.5 min |
| `system` | 3 min |
| `unit + integration` on macOS | 6.5 to 7 min |
| `docs`, which starts after `changes` | 5 to 7 min |
| `coverage`, once the Linux tests are done | 25 s |

Three things keep it there:

- **Two workers a vCPU for `tests/integration`.** Its tests spend most of their time waiting on
  a subprocess, a socket or a pseudoterminal. `-n auto` counts physical cores, which gives a
  four-vCPU runner two workers, so the jobs set `PYTEST_XDIST_AUTO_NUM_WORKERS` to twice the
  runner's vCPUs for that tier. `tests/unit` computes rather than waits, and keeps `auto`.
- **Coverage on one configuration.** Only the Linux jobs on Python 3.12 count it, every tier
  of them, through `sys.monitoring` (`COVERAGE_CORE=sysmon`), which costs a run next to
  nothing. A line only macOS or a newer Python reaches goes uncounted, and is still tested
  there.
- **`integration` in halves**, by how long each test took: see the next section.

GitHub's free plan runs twenty jobs at once, five of them on macOS, and the full tier is shaped
to fit. At its widest it runs sixteen, `codeql.yml`'s two among them, and three of those on
macOS. That is why macOS takes both tiers in one job per Python, and why `integration` is split
in two and not three. Two full tiers at once, such as a pull request's beside a push to
`main`'s, do not fit, and whichever starts second waits for runners.

## How `integration` is split

[pytest-split](https://github.com/jerry-git/pytest-split) reads how long each test took from
`.test_durations`, at the root of the repository, and deals `tests/integration` into two halves
that take the same time. Every test runs in exactly one half, and `tests/test_tiers.py` checks
the whole tree in whichever half it lands in.

A test the file does not name counts as the average, so a file that has fallen behind still
splits every test, only less evenly. When the two halves of a run drift a minute apart, write
it again and commit it:

```sh
uv run pytest tests/integration tests/test_tiers.py --store-durations --clean-durations
```

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
- **A test fails in one half of `integration` and passes alone.** It leans on another test in
  that half. Run the half as CI does:
  `uv run pytest tests/integration tests/test_tiers.py --splits 2 --group 1 --splitting-algorithm least_duration`.
- **`system` skips a test that runs on your machine.** It needs something that runner has not
  got, and the summary at the end of the job's log says what. A skip is not a failure.
- **A pull request has no `ci-ok` after you moved it onto `main`.** The tier is read when a
  run starts, and the last one ran for the old base. Push again to start one for `main`.

## Other workflows

None of these reports to `ci-ok`. On a pull request, wait for `title` from `title.yml` too.

| Workflow | Runs on | Does |
| --- | --- | --- |
| `build-docs.yml` | a push to `main` that changed `docs/` | Builds the site and deploys it. Every other run reaches it as `ci.yml`'s `docs` job |
| `title.yml` | every pull request | `title` checks the title is a Conventional Commit |
| `codeql.yml` | a pull request into `main`, a push to it, and weekly | Scans the Python and the workflows, into the repository's Security tab |
| `scorecard.yml` | a push to `main`, and weekly | Scores the repository against the [OpenSSF Scorecard](https://scorecard.dev) checks, into the Security tab |
| `publish.yaml` | a published release, or a dry run by hand | Builds the package and publishes it to PyPI: [Releasing](/contributing/releasing) |

## Next steps

- [Contributing](/contributing/), for the checks to run before you push
- [Your first patch](/contributing/tutorials/first-patch), a change taken all the way through CI
- [The regression matrix](/contributing/regression-matrix), for what CI never runs
