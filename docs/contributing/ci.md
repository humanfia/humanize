# CI

In this guide you read what CI ran on your change, and fix what it failed. Every pull request
runs `.github/workflows/ci.yml` on each push to it, and once more in the merge queue, on `main`
with the pull requests ahead of yours merged and then yours: what merges is what was tested.
So a push to `main`, tested there already, runs none of it: `cache.yml` saves the caches the
runs restore, and `build-docs.yml` deploys the site. A push to a `release/*` branch runs it
too, since a release is built from there. A push to any other branch runs nothing until it has
a pull request. The release pull request is the exception that proves it: `release.yml` starts
its run itself, since a pull request a workflow opened starts none of its own.

Wait for **`ci-ok`**. It is green when every other job in the run passed, and it is the check
a branch rule needs. `title.yml` checks the pull request's title apart, as **`title`**, so
editing the title runs it alone; `main` needs it too.

## How it works

Every job starts at once. The organisation runs at most 20 jobs at a time, 5 of them on macOS,
shared by every pull request and every run of the merge queue, and a job's setup outlasts most
packages' tests. So the jobs are few: on each system one runs every package's unit tests and
every topic's integration tests. And each runs
only for what your change touched, which `changes` finds first: against the pull request's
base, in the merge queue against `main`, and on a push to a release branch against the commit
before it.

```text
static      every hook, then the package ───────────────────────┐
changes ─┬▶ tests    unit, a package at a time, then            │
         │           integration, a topic at a time             ├─▶ ci-ok
         │                                     × Linux, macOS ──┤
         ├▶ vendor  the page's third-party code, rebuilt ───────┤
         ├▶ coganchor  the anchor's Rust × Linux, macOS ────────┤
         ├▶ desktop  the macOS app, on macOS ───────────────────┤
         └▶ desktop-windows  the Windows app, on Windows ───────┘
```

| Runs | When the change touched |
| --- | --- |
| everything | `pyproject.toml`, `uv.lock`, a file directly in `src/hmz/`, `tests/conftest.py`, `tests/integration/conftest.py`, the stand-in loops in `tests/integration/flows/` or `ci.yml` |
| `tests/unit/<package>` | `src/hmz/<package>/` or `tests/unit/<package>/`: unit tests mock every other package |
| the `agents` topic | `runtime`, `flows`, `coganchor` or `cli` |
| the `daemon` topic | those, `daemon`, `reach`, `relay`, `rpc`, `sdk`, `trust` or `web` |
| the `tui` topic | those of `agents`, `daemon`, `reach`, `rpc`, `trust` or `tui` |
| the `core`, `anchor` and `web` topics | anything in `src/hmz/`: they run `hmz` whole; the `anchor` topic also `crates/coganchor/` |
| the `reach` topic | those of `agents`, `daemon`, `reach`, `rpc`, `rtc` or `trust` |
| the `relay` topic | `cli`, `reach`, `relay`, `rpc`, `rtc` or `trust` |
| `tests/unit/rpc` | also anything in `protocol/`: it holds `protocol/openrpc.json` to the protocol's text |
| `node --test 'tests/unit/web/js/*.test.mjs'` | `src/hmz/web/static/`, `tests/unit/web/js/` or `ci.yml` |
| a topic | also its own files in `tests/integration/`, and the doubles its tests import: `doubles_core.py` counts for `core`, `daemon`, `anchor` and `web`, `doubles_daemon.py` for `daemon`, `core`, `tui` and `web`, `doubles_ssh.py` for `daemon`, `tui`, `web` and `reach`, `doubles_easytier.py` for `daemon`, `anchor` and `reach` |
| `vendor` | `src/hmz/web/vendor/`, `src/hmz/web/static/vendor/` or `ci.yml` |
| `coganchor` | `crates/coganchor/` or `ci.yml` |
| `desktop` and `desktop-windows` | `desktop/`, the page it carries in `src/hmz/web/static/`, or `ci.yml` |

`runtime`, `flows` and `coganchor` import each other, so a topic that runs one runs all three.
The other topics' rows follow what their tests import, and `hmz`, which loads a package only
when a command needs it. A test that comes to run a package or a double its row leaves out
takes it into the row in `ci.yml`'s `changes`: `tests/integration/test_core_ci_filters.py`
fails until it does.

| Job | Checks | Run it yourself |
| --- | --- | --- |
| `static` | Every pre-commit hook: `ruff`, `pyright` strict, `actionlint` and `zizmor` over `.github/`, and the file hygiene. Then the wheel and the sdist build, and PyPI would render `README.md`, so any commit on a `release/*` branch can be [released](/contributing/releasing) | `uv run pre-commit run --all-files`, then `uv build --no-sources && uvx twine check --strict dist/*` |
| `tests (<os>)` | `coganchor` built from `crates/coganchor/` with `cargo build`, which the tests run; then `tests/unit/<package>`, each directory under `tests/unit/` on its own; then `tests/integration/test_<topic>_*.py`, each of `core`, `agents`, `tui`, `daemon`, `anchor`, `web`, `reach` and `relay` on its own, a topic with no tests yet skipped; then the page's modules with `node --test 'tests/unit/web/js/*.test.mjs'`; each that the change touched. Skipped when the change touched none | `cargo build --manifest-path crates/coganchor/Cargo.toml`, then `uv run pytest tests/unit/<package>`, `uv run pytest tests/integration/test_<topic>_*.py`, `node --test 'tests/unit/web/js/*.test.mjs'` |
| `changes` | What the change touched, by the table above. Skipped on `release.yml`'s run, which runs everything | |
| `vendor` | The page's [vendored third-party code](/contributing/architecture#vendored-web-code) in `src/hmz/web/static/vendor/` is what `src/hmz/web/vendor/` builds from its lockfile, byte for byte. Skipped when neither changed | `pnpm install --frozen-lockfile && pnpm build` in `src/hmz/web/vendor/`, then `git diff src/hmz/web/static/vendor` |
| `coganchor (<os>)` | [`coganchor`](/contributing/#coganchor) in `crates/coganchor/`, on Linux and macOS: `cargo fmt --check`, `cargo clippy` with warnings as errors, `cargo test`; on Linux, also a static build against musl, checked to be statically linked. Skipped when `crates/coganchor/` is unchanged | the commands in [`coganchor`](/contributing/#coganchor) |
| `desktop` | [The macOS app](/contributing/#the-macos-app) in `desktop/`: `cargo fmt --check`, `cargo clippy` with warnings as errors, `cargo test`, and the app and its disk image built unoptimised, the disk image checked to be laid out by Finder. Skipped when neither `desktop/` nor the page it carries changed | the commands in [The macOS app](/contributing/#the-macos-app) |
| `desktop-windows` | The same app on Windows, whose hmz runs in WSL: `cargo fmt --check`, `cargo clippy` with warnings as errors, `cargo test`, and its NSIS installer built unoptimised. Skipped when neither `desktop/` nor the page it carries changed | the same commands on Windows, with `pnpm tauri build --debug --bundles nsis` |
| `ci-ok` | Every job above passed, or was skipped as it says | |
| `title`, in `title.yml` | The pull request's title is a [Conventional Commit](/contributing/#commits): squashing writes it to the branch, and a release's changelog is written from those titles. Skipped in the merge queue, whose pull requests had theirs checked before they queued. The release pull request has none: release-please writes its title | |

Every job but `coganchor`, `desktop` and `desktop-windows` runs on Python 3.12, from the environment `uv.lock` pins with every extra; the tests
run on Linux and macOS. `tests/system` is never run here: it drives real agents for minutes a
test and spends real tokens, and `hmz web`'s page in real browsers, so it is yours to run when
your change needs it. [Where a test goes](/contributing/#where-a-test-goes) says when.

The `web` topic speaks HTTP and WebSockets to `hmz web` as a browser does -- JSON-RPC over `/rpc` and `/dial` -- and opens no browser.
`tests/system/web/` draws the page in headless Chromium and in WebKit, the engine the macOS
app's window draws it with: fetch both with `uv run playwright install chromium webkit` before
running it.

A new package's directory under `tests/unit/` takes a `unit-<package>` filter in `changes`,
and `tests` fails until it has one. A new topic takes a filter and a word in the `tests` job's
list of topics; a file named for no topic in it runs in no job.

## How long it takes

Each package and topic has a budget for its tests alone, not counting setup:

| Tests | Budget |
| --- | --- |
| `tests/unit/<package>` | 3 minutes |
| `tests/integration/test_<topic>_*.py` | 10 minutes |

Each package and topic prints its slowest tests at the end of its group in the log
(`--durations`). A package or topic
past its budget is split, or its slowest tests made faster, before more is added to it.

The tests run in parallel inside a job, through `pytest-xdist`. `tests/unit` computes, and
takes a worker per core (`-n auto`). `tests/integration` mostly waits on a subprocess, a socket
or a pseudoterminal, so CI sets `PYTEST_XDIST_AUTO_NUM_WORKERS` to twice the runner's
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

A job's name says where it ran: `tests (macos-latest)` is on macOS. In its log each package
and topic is a group of its own, `unit tui` or `integration core`, and one that failed says so
in an error on the run's summary.

## Fix what failed

- **`title`** says what is wrong with the title. Edit the pull request's title, and it checks
  again.
- **`static`** prints the diff each hook wants. Run `uv run pre-commit run --all-files`, commit
  what it changed, and push.
- **A package or topic in `tests`.** Run the same command from the table above.
  Only that package's or topic's tests ran, so a test that leans on another's fails here and
  not in a plain `uv run pytest`: make it stand alone.
- **A test fails on macOS alone.** Run it on a Mac, or ask on the pull request for somebody
  who has one.

## Other workflows

None of them reports to `ci-ok`.

| Workflow | Runs on | Does |
| --- | --- | --- |
| `title.yml` | a pull request, its title edited, and the merge queue | `title`, above, which `main` needs besides `ci-ok` |
| `cache.yml` | a push to `main` that changed what a cache is made from, once a week, and by hand | Saves the caches `ci.yml`'s jobs restore: Python's environment on Linux and macOS, pre-commit's hooks, `coganchor`'s Rust on Linux and macOS, and the desktop app's Rust and pnpm on macOS and Windows. Only `main`'s caches can be read by every pull request and the merge queue, so `ci.yml` itself writes none |
| `build-docs.yml` | a pull request or a push to `main` that changed `docs/` | Builds the site, checks every `#fragment` resolves and every word is legible on a phone, and on `main` deploys it: [Working on these docs](/contributing/docs) |
| `release.yml` | a maintainer, by hand on `main`, with a version | Checks it, cuts `release/X.Y` from `main` for a new line, and has release-please open the release pull request against it: [Releasing](/contributing/releasing) |
| `publish.yml` | a push to a `release/*` branch | Once a release pull request merges, tags it, builds the wheel and sdist, the macOS app's disk image and the Windows app's installer, publishes the package to PyPI, then publishes the GitHub release with the app's files: [Releasing](/contributing/releasing) |

## Next steps

- [Contributing](/contributing/), for the checks to run before you push and where a test goes
- [Your first patch](/contributing/tutorials/first-patch), a change taken all the way through CI
