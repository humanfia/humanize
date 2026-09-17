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
| `uv run pytest` | The tests, against [stand-in agents](/reference/flows#testing-a-flow) |
| `uv run pytest --run-agents` | Also the `agent`-marked tests, which drive the real coding agent CLIs and spend real tokens |

Both of the first two have to pass. CI runs them over every file, on each Python the package
claims and on both Linux and macOS, and never runs the third. What a machine cannot do it says
so and skips: running an agent under an anchor is a seccomp filter and a ptrace supervisor, so
those tests are Linux on x86-64's and aarch64's, and everything above them is held to both
systems. The handful that run a real `node` — the preload layer patches a Node runtime from
inside, and only Node can confirm it did — carry the `node` mark, which says why in the summary
where there is none and takes them out of a run with `-m "not node"`.
`ruff` and `pyright` come from this project's own environment rather than one
pre-commit builds, so bump them with `uv lock --upgrade-package ruff` rather than by editing a
second pin.

The second gate drives each coding-agent backend against a stand-in CLI written onto `PATH`,
which is what makes it runnable on a machine with nothing installed. A stand-in prints what the
real CLI prints **and refuses what the real CLI refuses**: every one of them opens with the
command line its CLI would turn down, out of the flag tables in `tests/agents/standins.py`,
which are read off the `--help` of the version named beside each. Change a driver's command line
and that table is what says whether the CLI still takes it — so when a real CLI drops a flag,
move the table with it and let the suite go red where the driver still says the old word. The
third gate is the half no stand-in can stand in for: an account that has lapsed, a model it may
not name, a service withdrawn. Those are about the machine rather than the driver, and every
backend there skips with what the CLI itself said rather than failing.

## Where a test lives

A test's tier is the directory it is in. Each of the three trees marks everything beneath it
from its own `conftest.py`, so filing a test is moving it -- there is no decorator to remember,
and nothing to keep in step with a list.

| | |
| --- | --- |
| `tests/unit` | Imports `hmz`, calls it, asserts. No subprocess, no socket, no network, nothing written anywhere but `tmp_path` |
| `tests/integration` | Several parts together, but everything they talk to is a fake this repo wrote -- a stand-in CLI on `PATH`, a fake app server, a loopback socket, the interface under a Textual pilot. Deterministic and offline |
| `tests/system` | The real thing -- an installed coding agent, real ptrace and seccomp, docker, ssh, a daemon fork, a real `node`. Never run by CI |

The question that sorts one from another is *does it need something CI cannot be relied on to
have?* A loopback socket does not, so it is an integration test; a real coding agent does.
`agent` is a second gate inside `tests/system` rather than a fourth tier, because a system test
that spends real tokens has to be asked for and one that only needs `node` does not.

```sh
uv run pytest -m unit                  # one tier, on a machine that has everything
uv run pytest --ignore=tests/system    # everything CI can be relied on to run
```

CI names the directory rather than `-m "not system"`, and the two are not two spellings of one
thing: a deselected test has been imported already, and importing a system test is where a
module that probes the machine as it loads does the probing. `-m` is for choosing what to run;
the directory is for not looking.

`tests/test_tiers.py` fails the run if a marker and a directory ever disagree, which is what
makes the split true rather than aspirational. The helpers and a subsystem's fixtures --
`tests/stubs.py`, `tests/agents/standins.py`, `tests/tui/fixtures.py` and the rest -- stay where
they are, and a test that has moved takes the fixtures it needs back by name in a `conftest.py`
beside it: an autouse fixture nobody re-exported is a test that passes while checking nothing,
so that is checked too. A directory under a tier is named for the subsystem it mirrors --
`tests/integration/tui` holds what was written in `tests/tui` -- which is how a run can tell
what a moved test used to be given. `tests/tiers.py` has the whole of it.

A subsystem's fixtures are a `fixtures.py` rather than a `conftest.py`, because no test is
under those directories any more. A conftest over no tests is loaded by a run that walks past
it and not by one that names a tier, so a hook written there would fire for `uv run pytest` and
silently not for `uv run pytest tests/integration` -- and a plain module cannot be loaded as a
plugin at all. A `pytest_*` belongs in `tests/conftest.py` or in a tier's own conftest, which
is checked as well.

Splitting one file across two tiers is the common case, and what the two halves share goes into
a helper module that never moves -- `tests/logins.py`, `tests/composing.py`,
`tests/agents/homes.py` and the rest -- rather than being copied into both. That holds for a
fixture too: its body goes in the helper and a three-line fixture calling it stays in each half,
because pytest finds a fixture by name and a test that names one shadows an import of it. A
copied *autouse* fixture is the one worth the trouble: nobody asks for it, so the copy that
falls behind the other is a half that goes on passing while checking less, and nothing reports
it.

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
