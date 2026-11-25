# Contributing to Humanize

Thank you for helping. This file is how a change gets from an idea to `main`: where to raise
it, how to set up a checkout, the checks it must pass, and how it is reviewed.
[ARCHITECTURE.md](ARCHITECTURE.md) says which layer a change belongs in, and
[RELEASING.md](RELEASING.md) how a maintainer cuts a release.

Everyone taking part follows the
[Code of Conduct](https://github.com/humanfia/.github/blob/main/CODE_OF_CONDUCT.md), which every
humanfia repository shares.

## Ways to help

| To | Do this |
| --- | --- |
| report a bug | open a [bug report](https://github.com/humanfia/humanize/issues/new?template=bug_report.yml) |
| report a vulnerability | follow [SECURITY.md](SECURITY.md), never a public issue |
| suggest a feature | open a [feature request](https://github.com/humanfia/humanize/issues/new?template=feature_request.yml) |
| fix the docs | a pull request straight away, or a [bug report](https://github.com/humanfia/humanize/issues/new?template=bug_report.yml) for a page that is wrong |
| ask a question | read [the documentation](https://humanfia.ai/humanize/) and [Troubleshooting](https://humanfia.ai/humanize/user/troubleshooting) first; a question they leave unanswered is a gap in the docs, so open a bug report |
| fix or build something | a pull request, as below |
| share a flow you wrote | keep it in a repository of your own, and list it in [humanfia/flowverse](https://github.com/humanfia/flowverse) with a pull request there |

Say so on an issue before you start on it, so that two people do not do the same work.

## Before you write code

- **A small fix** (a bug, a typo, a missing test): open the pull request.
- **Anything larger** (a feature, a backend, a new flag, a change to the flow API, anything
  that breaks what works today): open an issue first, and agree the approach with a maintainer
  before you build it. A large pull request nobody asked for may be closed, however good it is.
- **`protocol/` is the contract.** Change the code to match it. A pull request that changes a
  protocol document links the issue where a maintainer asked for that change.

## Set up a checkout

You need `git`, [`uv`](https://docs.astral.sh/uv/) and [Rust](https://rustup.rs/).

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync --all-extras
cargo build --manifest-path crates/coganchor/Cargo.toml
uv run pre-commit install
```

- `uv sync --all-extras` makes `.venv` as `uv.lock` pins it, Python included. The tests import
  the extras; a plain `uv sync` removes them.
- `cargo build` builds `coganchor`, which every agent's turn runs through. The tests find it
  in `crates/coganchor/target/{release,debug}` and fail without it; `HUMANIZE_COGANCHOR` names
  a build elsewhere. Build it again after changing the crate. A new `git worktree` has no build
  of its own: build one there, or point `HUMANIZE_COGANCHOR` at another checkout's where the
  worktree leaves the crate as it is. `pytest` says so over its run where it finds none.
- `pre-commit install` runs the hooks on each commit.

Run tools through `uv run`, not `uvx`, so that you get the versions `uv.lock` pins. Check the
setup with `uv run pytest tests/unit/flows`.

## The checks

Both must pass before you push. They are what CI runs:

```sh
uv run pre-commit run --all-files   # format, lint, types, workflows: seconds
uv run pytest                       # tests/unit and tests/integration: minutes
```

While you write, `uv run pytest tests/unit/<package>` is the fast loop. Then, for what you
changed:

| You changed | Also run |
| --- | --- |
| `crates/coganchor/` | in it: `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`, `cargo test --locked` |
| `desktop/` | in `desktop/src-tauri`: the same three; then in `desktop/`: `pnpm install` and `pnpm tauri build --debug --bundles app,dmg` (`--bundles nsis` on Windows) |
| `src/hmz/web/static/` | `node --test 'tests/unit/web/js/*.test.mjs'`, and the files of `tests/system/web/` that cover it |
| `src/hmz/web/vendor/` | in it: `pnpm install && pnpm build`, and commit what it wrote to `src/hmz/web/static/vendor/` |
| `docs/` | in it: `pnpm check:pictures && pnpm check:words && pnpm build && pnpm check:anchors && pnpm check:phone` |
| packaging or `README.md` | `uv build --no-sources && uvx twine check --strict dist/*` |
| a path a system test covers | that one file, such as `uv run pytest tests/system/test_flows_ralph.py` |

Much of `coganchor` (the supervisor, Landlock, seccomp) runs only on Linux. From a Mac, or any
machine with Docker, `crates/coganchor/dev/linux-test.sh [pytest arguments]` runs the crate's
checks in a Linux container, then pytest against the binary it built.

To open the desktop app from a checkout, with this checkout's `hmz`:

```sh
cd desktop && pnpm install
HUMANIZE_HMZ="$PWD/../.venv/bin/hmz" pnpm dev
```

## What the code is held to

- `pyright` in strict mode over `src` and `tests`. `# type: ignore` is switched off: a
  suppression names a pyright rule.
- `ruff` with every rule on, less the ones `pyproject.toml` gives a written reason for.
- Google-style docstrings, and type annotations everywhere.
- Popular, well-maintained libraries before a custom implementation.
- Each layer imports only what [ARCHITECTURE.md](ARCHITECTURE.md) gives it.
- A change to how flows run keeps the flows
  [humanfia/flowverse](https://github.com/humanfia/flowverse) lists working.
- A change to behaviour updates the docs in the same pull request.

## Where a test goes

A Python test goes in exactly one of three directories. The directory decides when it runs;
there is no marker to write.

| Directory | Holds | Rules |
| --- | --- | --- |
| `tests/unit/<package>/` | one top-level package of `src/hmz` alone, in the directory named for it | only the package's public names, never a `_private` name or module; every other `hmz` package mocked; no subprocess, no socket. Its tests finish in 3 minutes |
| `tests/integration/test_<topic>_*.py` | packages wired together against fakes this repository writes | flat; the topic is one of `core`, `agents`, `tui`, `daemon`, `anchor`, `web`, `reach`, `relay`, and CI runs each alone. A topic finishes in 10 minutes. No browser |
| `tests/system/` | real agents on real tasks; in `tests/system/web/`, the web page driven in real browsers through Playwright; in `tests/system/docs/`, the scenes that make the docs' pictures | never in CI. 5 to 30 minutes and real tokens a test outside `web/` and `docs/`. Run only the file that covers a path you changed |

- `uv run pytest` runs unit and integration and leaves `tests/system` out. Name a file to run
  a system test. It skips, saying why, when this machine lacks what it needs.
- `tests/system/web/` and `tests/system/docs/` need browsers:
  `uv run playwright install chromium webkit`.
- The Rust crate's tests are in `crates/coganchor`, in-file `#[cfg(test)]` modules and
  `crates/coganchor/tests/`, and run with `cargo test`.
- A new directory under `tests/unit/` needs a `unit-<package>` filter in the `changes` job of
  `.github/workflows/ci.yml`. A new topic needs a filter there and its name in the `tests`
  job's list of topics. `tests/integration/test_core_ci_filters.py` fails when a topic's
  filter leaves out a package its tests import.
- Every test runs with its own `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`,
  `XDG_CACHE_HOME`, `HOME` and `TMPDIR`. A test that writes into your real Humanize directories
  or `~/.hmz` fails the run. A scratch script outside `tests/` sets them itself.
- **Never copy a sign-in into a test's home.** Codex's and Claude Code's logins renew
  themselves, and a renewal cancels every other copy of the token: a copy of
  `~/.codex/auth.json` or `~/.claude/.credentials.json` in a container or temporary home signs
  your machine out. Run the CLI as local, or mount its own home where it is. The run fails if
  a temporary directory holds such a token.

## Pull requests

1. Branch from `main`, on a fork unless you have push access. Name the branch
   `<type>/<short-slug>`, such as `fix/say-what-to-do`.
2. Make the change, with its tests in [the directory they belong in](#where-a-test-goes) and
   the docs that describe it, in the same pull request.
3. Run [the checks](#the-checks) until they pass.
4. Open the pull request against `main`, and fill in the template.

### Title and commits

The pull request's title is a [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/):
`type(scope): what it does`, in the imperative, with `!` before the colon if it breaks
something. For example, `fix(tui): keep the cursor on the row it was on`.

- **Types:** `feat`, `fix`, `docs`, `perf`, `refactor`, `test`, `ci`, `build`, `chore`,
  `style`, `revert`.
- **Scope:** the package it changes, such as `agents`, `tui` or `flows`, or `desktop` for the
  app. Optional.

The `title` check fails until it is one; edit the title and it checks again. Commits follow
the same form, and a change and its tests go in one commit.

A pull request is squashed into one commit titled with it, and a release's changelog is
written from those titles, so the title is what somebody upgrading reads about your change, and
its `feat` or `!` is what puts it under Features or Breaking changes.

No sign-off or CLA is asked for. What you contribute is under the project's
[Apache-2.0 license](LICENSE), as its section 5 says.

## Review

- A pull request merges once a maintainer approves it and CI passes. A maintainer adds it to
  the merge queue, which merges it once CI passes again on it as `main` will be.
  [Conflicts of interest](https://github.com/humanfia/.github/blob/main/GOVERNANCE.md#conflicts-of-interest),
  in the organization's governance, covers a maintainer's own pull requests.
- Expect a first answer within a week. If a week passes without one, comment on the pull
  request to ask.
- Answer each comment, by a change or a reply. Push fixes as new commits rather than rewriting
  what was reviewed, so the reviewer sees what changed.
- A pull request that waits on its author for a month may be closed. Reopen it when you come
  back to it.

## CI

`.github/workflows/ci.yml` runs on every push to a pull request and again in the merge queue.
Two checks gate a merge: **`ci-ok`**, green when every job of the run passed or was skipped,
and **`title`**.

| Job | Runs | When the change touched |
| --- | --- | --- |
| `static` | every pre-commit hook, then the wheel and sdist built and checked with `twine` | always |
| `tests (<os>)` | on Linux and macOS: `coganchor` built, then `tests/unit/<package>` a package at a time, `tests/integration/test_<topic>_*.py` a topic at a time, and the page's `node --test` | that package, or what that topic's tests import |
| `vendor` | `src/hmz/web/static/vendor/` is what `src/hmz/web/vendor/` builds, byte for byte | either, or `ci.yml` |
| `coganchor (<os>)` | `cargo fmt`, `clippy`, `test` on Linux and macOS, and a static musl build on Linux | `crates/coganchor/` |
| `desktop`, `desktop-windows` | `cargo fmt`, `clippy`, `test` and an unoptimised build of the app | `desktop/` or `src/hmz/web/static/` |

The `changes` job decides what runs, from the filters written in `ci.yml`. `pyproject.toml`,
`uv.lock`, a file directly in `src/hmz/`, the shared `conftest.py` files or `ci.yml` itself
run everything.

- CI runs each package and topic alone, so a test that leans on another's passes in a plain
  `uv run pytest` and fails there. Run the one command: `uv run pytest tests/unit/<package>`
  or `uv run pytest tests/integration/test_<topic>_*.py`.
- `static` prints the diff each hook wants: run `uv run pre-commit run --all-files`, commit
  what it changed, and push.
- `gh pr checks --watch` follows a run, and `gh run view --log-failed` prints what failed. In
  a `tests` log each package and topic is a group of its own, `unit tui` or `integration core`.
- `build-docs.yml` builds the site on a change to `docs/`, runs its `check:` scripts, and
  deploys it from `main`. `cache.yml` saves the caches `ci.yml` restores. Neither reports to
  `ci-ok`.

## Working on the docs

The site is [VitePress](https://vitepress.dev/), in `docs/`. It needs Node and pnpm.

```sh
cd docs
pnpm install
pnpm dev             # the site, reloading as you write
pnpm build           # fails on a dead internal link
pnpm check:anchors   # after a build: fails on a dead #fragment
pnpm check:pictures  # every picture is an SVG, light and dark; no video, no cast
pnpm check:words     # the home page's banner is the repository's description; its words keep to their rules
pnpm check:phone     # after a build: fails on a page that scrolls sideways on a phone
```

`check:phone` drives Chromium: `pnpm exec playwright install chromium` once.

### Pages

Each section answers one kind of question. A page that answers two is two pages.

| Directory | Section | A page there |
| --- | --- | --- |
| `docs/tutorials/` | Tutorials | one lesson taken in order, every command written out |
| `docs/user/` | User Guide | one task for the person running Humanize. No Python |
| `docs/builder/` | Builder Guide | one task for whoever writes a flow or drives Humanize from code |
| `docs/reference/` | Reference | exact, complete and scannable: every flag, key, argument and return |

- **A new page is one line** in `docs/.vitepress/sidebar.ts`, under its section.
- **A moved or removed page leaves a redirect**: an entry from its old path to its new one in
  `MOVED_NOW` in `docs/.vitepress/config.mts`. The build writes a redirect file for each.
- **Match the code.** Check every command, flag, key, path, name and error string against
  `src/hmz`.
- **Stay at the reader's altitude.** Outside Reference, show no internal module paths and
  describe no mechanism the reader does not need in order to decide something. Write no
  history: say what is.
- **Every example runs.** Run each one as the page says before you push, and paste what it
  really printed.
- Wrap prose at 95 columns. The first `#` heading is the page's title.

### Pictures

- **No video and no recorded cast.** Every picture is an SVG file, still or animated, shown
  with `![what it shows](/path.svg)`.
- **Every picture is two files**, side by side: `<name>.svg` for the light page and
  `<name>.dark.svg` for the dark one, the same size and the same frames. A page names the
  light file; the site shows the one that fits the theme the reader chose.
- **A picture of an interface is never drawn by hand.** It is captured from the real
  interface by a scene under `tests/system/docs/`, which writes both files to
  `docs/public/shots/` from one run: the page as it draws light and as it draws dark, a
  terminal in a light profile and in a dark one. Commit both with the scene that made them.
- **A concept diagram is a hand-written SVG** in `docs/public/diagrams/`, drawn light with
  the diagrams' palette. Its dark twin is written from it, colour by colour: run
  `pnpm diagrams` in `docs/` after you edit one, and commit both. A colour outside the
  palette (`docs/.vitepress/diagrams.mjs`) is an error.
- **Nothing private.** A picture shows no real account, machine, path or name: only what the
  scene's made-up world holds.

A scene is a test in `tests/system/docs/test_docs_<page>.py`, one file per docs page. It asks
for the `world` fixture, which stages a made-up person (`alex`), machine (`studio`) and project
(`shop`) with stand-in agents and flows; drives the interface as a person would; and takes its
pictures with `tests/system/docs/shots.py`:

| Call | Takes |
| --- | --- |
| `shots.web(page, name, clip=, window=)` | the web page or one part of it; `window="desktop"` draws the desktop app's window around it, `"browser"` a browser's |
| `shots.tui(app, name)` | the terminal interface's screen |
| `shots.cli(argv, name)` | a command run in a real terminal, and what it printed |
| `shots.splash(state, detail, name)` | Humanize Desktop's launch window in one of its states |
| `shots.Reel(name)`, then `.web`, `.type`, `.tui`, `.cli`, `.splash` a frame at a time, then `.save()` | an animated SVG: frames looped by CSS inside the file, still under reduced motion |

```sh
uv run playwright install chromium
uv run pytest tests/system/docs/test_docs_<page>.py
```

Name a picture `<page>-<what>`, lower case with dashes, such as `chat-new`. A still is held to
200 kB and a reel to 500 kB, the most the commit hook lets a file be, each of its two files by
itself: crop it, or take fewer frames. The docstrings of `shots.py` and of `conftest.py` beside it have the whole API and
what `world` can stage.

## Releasing

Releases are cut by maintainers from `release/X.Y` branches, never from `main`:
[RELEASING.md](RELEASING.md).

## Working with coding agents

Humanize is built with coding agents, and you may use them too. [AGENTS.md](AGENTS.md) is the
rules they work under in this repository, and the rules are the same for people. You are the
author of what you send: read it, run it, and be ready to answer for every line.

## Licence and governance

Humanize is under the [Apache-2.0 license](LICENSE). The organization's
[GOVERNANCE.md](https://github.com/humanfia/.github/blob/main/GOVERNANCE.md) says who decides,
and how to become a reviewer or maintainer.
