# Your first patch

**Half an hour**, most of it the first `uv sync` and the test run. You will clone humanize,
change one small thing, pass the checks, and open a pull request CI agrees with.

::: tip Before you start
`git` and [`uv`](https://docs.astral.sh/uv/). Nothing else: `uv sync` brings Python with it.
:::

## 1. Clone it and install the hooks

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync
uv run pre-commit install
```

From now on every commit is checked before it is made. Run tools through `uv run`, not `uvx`,
so you get the versions `uv.lock` pins.

## 2. Find something small

A good first patch is one screen of diff:

- an error message that says what went wrong but not what to do about it;
- a docstring that no longer describes its function;
- a `--help` line that is out of date;
- a test for a branch that has none.

[Architecture](/contributing/architecture) shows which directory under `src/hmz/` holds what.
Branch, then make the change:

```sh
git switch -c fix/say-what-to-do
```

## 3. Test it while you write

```sh
uv run pytest tests/unit
```

Seconds, and the loop worth having. If your change needs a new test, file it by what is on
the other side of it: `tests/unit/` when it calls `hmz` and nothing else,
`tests/integration/` when it talks to something this repository wrote, `tests/system/` when it
needs the real thing. [Where a test goes](/contributing/#where-a-test-goes) has the table.

## 4. Run the checks

```sh
uv run pre-commit run --all-files
```

::: code-group

```text [All passed]
check for added large files.............................Passed
check for case conflicts................................Passed
check for merge conflicts...............................Passed
check toml..............................................Passed
check yaml..............................................Passed
fix end of files........................................Passed
mixed line ending.......................................Passed
trim trailing whitespace................................Passed
uv lock --check.........................................Passed
ruff check..............................................Passed
ruff format.............................................Passed
pyright (strict)........................................Passed
```

```text [ruff fixed something]
ruff check..............................................Failed
- hook id: ruff-check
- files were modified by this hook

Found 1 error (1 fixed, 0 remaining).
```

:::

**`ruff check` fixes what it can**, and a run that fixed something reports `Failed`. Read what
it changed, `git add` it, and run the checks again. `pyright` checks the whole project, so an
error can show up in a file you did not touch but that imports one you did.

Then the tests, all three tiers:

```sh
uv run pytest
```

Minutes. The summary names every test that skipped and why. Tests that need something your
machine lacks, like docker or a real `node`, skip. So do the ones that drive a real coding
agent CLI, until you ask for them:

```text
SKIPPED [1] tests/system/agents/test_steering.py:30: needs --run-agents (drives real agents, costs tokens)
```

Your first patch rarely needs them. When a change touches what the system tier drives for
real, a backend's driver or the anchor say, run it by hand:

```sh
uv run pytest tests/system --run-agents
```

::: warning This spends real tokens
It drives the coding agent CLIs installed on your machine, signed in as you.
:::

## 5. Commit it

```sh
git add -A
git commit -m "fix(agents): say what to do when a turn is refused"
```

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat`, `fix`, `docs`,
`refactor`, `test`, `chore` or `ci`, then the package or docs section as the scope. A `!`
before the colon marks a breaking change. The change and its tests go in one commit.

## 6. Open the pull request

```sh
git push -u origin fix/say-what-to-do
gh pr create --fill
```

Without push access, run `gh repo fork --remote` first and push to your fork. `gh pr create`
opens the pull request across it either way.

Two workflows then run:

| | |
| --- | --- |
| `ci.yml` | `uv lock --check`, the same hooks over every file, `uv build`, and a start with no extras installed. Then `uv run pytest --ignore=tests/system`, on Python 3.12 on Linux |
| `build-docs.yml` | Only when `docs/` changed: `pnpm build`, then `pnpm check:anchors` |

When a hook fails in CI, the log prints the diff that would fix it.

## What you have now

A branch that passes the checks, and a pull request that says what it changed and why. If the
change needs explaining too, [Add a page to these docs](/contributing/tutorials/a-page-of-docs)
is the other half of it. For a change bigger than a screen,
[Architecture](/contributing/architecture) shows where it goes.
