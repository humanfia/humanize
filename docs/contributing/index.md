# Contributing

PRs accepted. Ask a question or discuss a substantial change first in
[issues](https://github.com/humanfia/humanize/issues).

## Tutorials

| | |
| --- | --- |
| [Your first patch](/contributing/tutorials/first-patch) | Clone it, change one thing, both gates, a pull request |
| [Add a page to these docs](/contributing/tutorials/a-page-of-docs) | Write it, put it in the sidebar, prove the links resolve |

## Set up

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync
uv run pre-commit install
```

Installing the hooks once means every commit is checked before it is made.

## The two gates

| | |
| --- | --- |
| `uv run pre-commit run --all-files` | The file-hygiene hooks, the formatter, the linter and the type checker — everything that answers in seconds |
| `uv run pytest` | The tests, less the ones that need a real coding agent |

Both have to pass. CI runs them over every file, on each Python the package claims and on both
Linux and macOS. `ruff` and `pyright` come from this project's own environment rather than one
pre-commit builds, so bump them with `uv lock --upgrade-package ruff` rather than by editing a
second pin.

This table used to have a third row, under a heading that said two — the kind of thing that is
read past for a year. That row was never a gate. A gate is something a change has to pass; what
it was is a run somebody makes on purpose, on a machine that has the thing. So the two words
have been separated: there are **two gates**, and the tests behind the second are sorted into
**three tiers** by what is on the other side of them.

## The three tiers

| | | |
| --- | --- | --- |
| `tests/unit/` | Imports `hmz`, calls it, asserts. No subprocess, no socket, no network | Milliseconds |
| `tests/integration/` | Everything on the far side is something this repository wrote: a [stand-in CLI](/reference/flows#testing-a-flow) on `PATH`, a fake app server, a loopback socket, a `ShellAgent`, the mock LLM service | Seconds |
| `tests/system/` | The real thing: a coding agent CLI signed in as you signed it in, real ptrace and seccomp, real docker, real ssh, a real daemon fork, real `node` | Minutes, and real tokens |

One directory each, and each tier's `conftest.py` puts the marker on — so a test is in the tier
its path says it is in, and there is no second place to keep that true.

```sh
uv run pytest tests/unit     # the fast loop, while you are still writing it
uv run pytest                # the gate: unit and integration
uv run pytest --run-agents   # also the system tier, which spends real tokens
```

**CI runs the first two tiers and never the third.** It passes `--ignore=tests/system`, so that
tier is not collected there at all rather than collected and thrown away: collecting is
importing, and those modules import things a hosted runner has no reason to have. A collection
error about a tier a job was never going to run is a red CI that says nothing about the change.

That is not the only thing holding real agents out of CI, and it is not meant to be. A test
marked `agent` is skipped unless `--run-agents` is passed, and CI never passes it — which covers
an agent test wherever it sits, including one that has not reached `tests/system/` yet. The
directory is where it belongs; the marker is what catches it in the meantime.

Locally it is the other way round, and deliberately: run the whole suite and the system tier is
collected, so `-ra` — set in `pyproject.toml` — names every one of them and the reason each sat
out. A test that quietly stops running says so. That is also why the `agent` gate skips rather
than deselects.

What a machine cannot do it says so and skips: running an agent under an anchor is a seccomp
filter and a ptrace supervisor, so those tests are Linux on x86-64's and aarch64's, and
everything above them is held to both systems.

**"End-to-end" is not one of these three words, and that is on purpose.** It has been used here
for two different things — *drives a real agent binary*, which is what the `agent` marker still
calls itself, and *out of process, a real anchor across three directories, no agent at all*,
which is what the anchor tests call themselves. Those are two different tiers: the first is
`tests/system/`, and the second is `tests/integration/`, because everything on the far side of it
is still this repository's own. Name the tier and the ambiguity does not arise.

### What a stand-in is for

The integration tier drives each coding-agent backend against a stand-in CLI written onto
`PATH`, which is what makes it runnable on a machine with nothing installed. A stand-in prints
what the real CLI prints **and refuses what the real CLI refuses**: every one of them opens with
the command line its CLI would turn down, out of the flag tables in `standins.py`, which sits
beside the backend tests and is read off the `--help` of the version named next to each entry.
Change a driver's command line and that table is what says whether the CLI still takes it — so
when a real CLI drops a flag, move the table with it and let the suite go red where the driver
still says the old word.

The system tier is the half no stand-in can stand in for: an account that has lapsed, a model it
may not name, a service withdrawn. Those are about the machine rather than the driver, and every
backend there skips with what the CLI itself said rather than failing. Run it when the change is
a driver under `coganchor/agents/`, or an anchor, or the daemon — nobody else will.

## What the code is held to

- **`pyright` in strict mode**, over `src` and `tests`. `# type: ignore` comments are switched
  off; a suppression names a pyright rule.
- **`ruff` with every rule on**, less the ones this codebase has a written reason to be without —
  each is annotated in `pyproject.toml`.
- **Google-style docstrings.**
- **Popular, well-maintained libraries** in preference to a custom implementation.
- **Each package depends only downwards**, which is checked by a test.
  [Architecture](/contributing/architecture) has the layers and the rules that keep them.
- **Most packages have a SPEC under `specs/`**, in a file named for the package. Do not modify
  one unless you were asked to — it is the contract, and the code is what has to move.

## Documentation

- `README.md` follows [standard-readme](https://github.com/RichardLitt/standard-readme), and
  says what humanize does and how to use it — never how it works.
- Everything else is this site, under `docs/`. See
  [Working on these docs](/contributing/docs) for running it locally and for how the terminal
  demos are recorded.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `fix(agents): …`,
`docs(contributing): …`, with a `!` before the colon for a breaking change. Keep a change and
its tests in the same commit.
