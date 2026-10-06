# Your first patch

In this tutorial you clone humanize, change one small thing, pass the checks, and open a pull
request CI agrees with. It takes **half an hour**, most of it the first `uv sync` and the test
run. Every command is written out, in order.

::: info Before you start
`git`, [`uv`](https://docs.astral.sh/uv/), and the [GitHub CLI](https://cli.github.com/)
(`gh`) signed in, for the last step. Nothing else: `uv sync` brings Python with it.
:::

## Step 1: clone it and install the hooks

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync
uv run pre-commit install
```

- **`uv sync`** makes the environment in `.venv`, exactly as `uv.lock` pins it.
- **`pre-commit install`** runs the checks on every commit from now on, before it is made.

Run tools through `uv run`, not `uvx`, so you get the versions `uv.lock` pins.

## Step 2: find something small

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

## Step 3: test it while you write

Run the unit tests of the package you changed, here `coganchor`:

```sh
uv run pytest tests/unit/coganchor
```

Seconds, and the loop worth having. If your change needs a new test, it most likely goes in
`tests/unit/<package>/`: it calls the package's public names and mocks every other `hmz`
package. A test that wires packages together against a fake goes in `tests/integration/`.
[Where a test goes](/contributing/#where-a-test-goes) has the rules.

## Step 4: run the checks

```sh
uv run pre-commit run --all-files
```

::: code-group

```text [All passed]
check for added large files..............................................Passed
check for case conflicts.................................................Passed
check for merge conflicts................................................Passed
check toml...............................................................Passed
check yaml...............................................................Passed
fix end of files.........................................................Passed
mixed line ending........................................................Passed
trim trailing whitespace.................................................Passed
Lint GitHub Actions workflow files.......................................Passed
zizmor...................................................................Passed
uv lock --check..........................................................Passed
ruff check...............................................................Passed
ruff format..............................................................Passed
pyright (strict).........................................................Passed
```

```text [ruff fixed something]
ruff check...............................................................Failed
- hook id: ruff-check
- files were modified by this hook

Found 1 error (1 fixed, 0 remaining).
```

:::

- **A hook that fixed something reports `Failed`.** `ruff check`, `ruff format` and the
  whitespace hooks fix what they can. Read what they changed, `git add` it, and run the checks
  again.
- **`pyright` checks the whole project**, so an error can show up in a file you did not touch
  but that imports one you did.

Then the tests, unit and integration, as CI runs them:

```sh
uv run pytest
```

Minutes. It leaves `tests/system` out: those tests drive real coding agent CLIs on real tasks
for 5 to 30 minutes each, and spend real tokens. Your first patch does not need them.

## Step 5: commit it

```sh
git add -A
git commit -m "fix(agents): say what to do when a turn is refused"
```

The hooks run again as you commit, and a commit they fix is not made: `git add` what they
changed and commit again.

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `feat`, `fix`, `docs`,
`refactor`, `test`, `perf`, `style`, `build`, `ci`, `chore` or `revert`, then the package or
docs section as the scope. A `!`
before the colon marks a breaking change. The change and its tests go in one commit.

## Step 6: open the pull request

```sh
git push -u origin fix/say-what-to-do
gh pr create --fill
```

Without push access, run `gh repo fork --remote` first and push to your fork. `gh pr create`
opens the pull request across it either way.

CI then runs `ci.yml`, the same jobs for every pull request:

| | |
| --- | --- |
| `lint` | Every pre-commit hook over every file, as in Step 4 |
| `unit (<os>, <package>)` | `tests/unit/<package>`, a job per package, on Linux and macOS |
| `integration (<os>, <topic>)` | `tests/integration/test_<topic>_*.py`, a job per topic, on Linux and macOS |
| `ci-ok` | Green when every job above passed |

A change to `docs/` also runs `build-docs` from `build-docs.yml`.

## Check it worked

`gh pr checks` shows every job on your pull request, and waits with `--watch`. The one to wait
for is `ci-ok`; [CI](/contributing/ci) has what each job checks:

```sh
gh pr checks --watch
```

When a hook fails in CI, the log prints the diff that would fix it. Run the same hook locally,
commit what it changed, and push again.

## Next steps

A branch that passes the checks, and a pull request that says what it changed and why. From
here:

- If the change needs explaining too, [Add a page to these
  docs](/contributing/tutorials/a-page-of-docs) is the other half of it.
- For a change bigger than a screen, [Architecture](/contributing/architecture) shows where it
  goes.
- For a change to how a coding agent CLI is driven, run the system test that covers it: see
  [Where a test goes](/contributing/#where-a-test-goes).
