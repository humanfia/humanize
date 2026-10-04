# Port a project

In this tutorial you move one module of a real C# project to Python. One agent does the porting
in a single long conversation, and a fresh reviewer checks what actually landed after every
round, until it is willing to say the port is done.

::: info At a glance
- **You will learn** how an actor and a reviewer split a job, why a reviewer that has never
  seen the actor's reasoning catches what the actor misses, how to close the shortcuts a
  literal port invites, and how a run ends on a reviewer's `done`.
- **You will end with** the three things in the table below.
- **Time:** about an hour, most of it waiting.
- **You need** humanize and one signed-in coding agent CLI. Any backend works, DeepSeek
  Harness included, which needs only an API key and an extra.
:::

| You end with | Where |
| --- | --- |
| a Python port of two C# files, the methods the C# never finished included | `python/golang_x_mod/` |
| every case in the C# test tables, ported and passing | `python/tests/` |
| the reviewer's sign-off, which is what ended the run | printed as the run ends |

## Before you start

- **Install humanize and sign in to a coding agent CLI.** See
  [Installation](/user/installation).
- **Make one run first.** [Your first run](/user/first-run), or the
  [quickstart on the home page](/#run-a-flow), shows a flow working in a scratch repository.
- **Open `hmz` once.** `rlar` comes from the official [flowverse](/weaver/flowverses), and
  opening `hmz` in any directory is what fetches it. `hmz exec` does not. Leave with `/exit`.
- **Have Python 3 with pytest, and git.** The port is checked with `python -m pytest`. You do
  not need .NET: nothing here builds the C#.

## Step 1: Get the project

[lip](https://github.com/futrime/lip) is a package installer written in C#. You port one
project out of it, `src/Golang.Org.X.Mod/`, which is itself a C# port of Go's
`golang.org/x/mod` (semantic versions and module paths).

```sh
git clone https://github.com/futrime/lip
cd lip
wc -l src/Golang.Org.X.Mod/*.cs tests/Golang.Org.X.Mod.Tests/*.cs
```

```console
  227 src/Golang.Org.X.Mod/Semver.cs
  408 src/Golang.Org.X.Mod/Module.cs
   68 tests/Golang.Org.X.Mod.Tests/SemverTests.cs
  198 tests/Golang.Org.X.Mod.Tests/ModuleTests.cs
```

**What just happened.** It makes a good first slice. It does no I/O, it has tables of test
cases, and the original Go is there as a second opinion wherever the C# is unclear. It also
has a trap:

```sh
grep -c NotImplementedException src/Golang.Org.X.Mod/*.cs
```

```console
src/Golang.Org.X.Mod/Module.cs:18
src/Golang.Org.X.Mod/Semver.cs:7
```

That is twenty-five unfinished methods. A literal port would give you twenty-five Python
functions that raise `NotImplementedError`, and a suite that carefully never calls them. The
task has to rule that out.

::: tip Checkpoint
The same four line counts, and 25 `NotImplementedException`s between the two files.
:::

## Step 2: Write the task down

```sh{15-17,24-25}
cat > TASK.md <<'EOF'
Migrate this repository's `Golang.Org.X.Mod` project from C# to Python, as the
first slice of moving lip to Python.

Make a Python package at `python/golang_x_mod/` with:

- `semver.py`, the port of `src/Golang.Org.X.Mod/Semver.cs`
- `module.py`, the port of `src/Golang.Org.X.Mod/Module.cs`

and a pytest suite at `python/tests/` ported from
`tests/Golang.Org.X.Mod.Tests/`, keeping every case in the xunit tables.

Rules:

- The C# leaves some methods as `throw new NotImplementedException()`. The
  Python port must implement them, matching `golang.org/x/mod`, which is what
  the C# is a port of. Do not port the stub.
- Python names are snake_case; C# `Semver.MajorMinor` becomes
  `semver.major_minor`. Keep the behaviour identical, including what the Go
  original returns for malformed input (the empty string, not an exception).
- Where the C# returns an `Exception` rather than raising it, the Python
  returns `None` or an exception instance the same way — a caller must still
  be able to tell "this path is fine" from "this path is not".
- Do not weaken, delete or special-case a test to make it pass.
- `cd python && python -m pytest` must pass, and must be the check you run.

Set the package up so `python -m pytest` works from `python/` with no
installation: a `pyproject.toml` and a `conftest.py` if you need one.
EOF
git add -A && git commit -qm "the task"
```

**What just happened.** Most of the file says what to build. The highlighted rules close the
two shortcuts:

1. **Implement the stubs.** A port that copies `throw new NotImplementedException()` as
   `raise NotImplementedError` would pass a suite that never calls it. Naming the Go original
   gives the agent something to implement them from.
2. **Do not weaken the tests, and run this one command.** A suite can be made green by
   deleting its hard cases. Naming the command means the reviewer runs the same check as the
   actor.

::: tip Checkpoint
`git log --oneline -1` shows `the task`.
:::

## Step 3: Run it

The flow is [`rlar`](/flows/rlar), a Ralph loop with an actor and a reviewer. The **actor**
keeps one conversation for the whole run, so it remembers every decision it made. Each time it
finishes a turn, the **reviewer** opens a fresh one, reads the repository with `git diff` and
the tests, and answers two things: `done`, true or false, and `notes`. The notes become the
actor's next prompt, word for word.

<HmzFlow flow="rlar" />

Using DeepSeek Harness? Add humanize's `[dsh]` extra first, with the line for the way you
installed humanize:

::: code-group

```sh [pip]
pip install 'hmz[dsh]'
```

```sh [pipx]
pipx install --force 'hmz[dsh]'
```

```sh [uv tool]
uv tool install 'hmz[dsh]'
```

:::

Then pick the tab for the backends you have, and run it:

::: code-group

```sh [DeepSeek Harness]
export DEEPSEEK_API_KEY=sk-…
hmz exec -f rlar \
    -a actor=dsh/deepseek-v4-pro:high \
    -a reviewer=dsh/deepseek-v4-pro:high \
    -b duration=3h,cost=30 \
    "$(cat TASK.md)"
```

```sh [Claude Code + Codex]
hmz exec -f rlar \
    -a actor=claude/claude-opus-5-5:high \
    -a reviewer=codex/gpt-5.6-sol:high \
    -b duration=3h,cost=30 \
    "$(cat TASK.md)"
```

```sh [Claude Code only]
hmz exec -f rlar \
    -a actor=claude/claude-opus-5-5:high \
    -a reviewer=claude/claude-opus-5-5:high \
    -b duration=3h,cost=30 \
    "$(cat TASK.md)"
```

:::

```console
● actor is working
  …
✻ Worked for 1210s · actor
● reviewer is working
  …
✻ Worked for 95s · reviewer
● actor is working
```

**What just happened.**

1. **`-f rlar`** names the flow.
2. **`-a actor=…` and `-a reviewer=…`** give each role an agent. The same model in both is
   fine: the reviewer is independent because its conversation has never seen the actor's, not
   because it runs a different model.
3. **`-b duration=3h,cost=30`** caps the run. The reviewer usually ends it sooner.
4. **The output** is one long actor turn followed by a short reviewer turn: a round. Then the
   actor goes again, told what the reviewer found.

::: tip Checkpoint
You see `● actor is working`. If the run is refused instead, `hmz exec: error: …` names the
part of the line it could not use; see [Troubleshooting](#troubleshooting).
:::

## Step 4: Watch a round go by

From another terminal:

```sh
cd lip/python && python -m pytest -q
```

Early on this fails, because nothing is there yet. Then it passes, and the interesting part
starts: the reviewer keeps answering `done: false` even with a green suite, because a green
suite is not what it was asked about. In the run this page was written from, it sent the actor
to check the port against the upstream Go test vectors, which the C# tests do not all cover:

```console
match_path_major fails 0
match_prefix_patterns fails 0
checkpath family fails 0
```

**What just happened.** The actor checked its own work against a third source because a
reviewer that had never seen its reasoning asked it to. That is what the second role is for.

::: tip Checkpoint
The suite goes from failing to passing, and the run carries on anyway. That is expected.
:::

## Step 5: See where it stopped

The run ends by itself when the reviewer answers `done: true`, and prints the reviewer's final
`notes`:

```console
Port is complete and correct. python/golang_x_mod/semver.py
implements build/canonical/compare/is_valid/major/major_minor/max/
prerelease/sort with golang.org/x/mod semantics (invalid versions
return "", comparisons follow Go precedence).
python/golang_x_mod/module.py implements every NotImplementedException
stub … python/tests/test_module.py contains all 105 CheckPathTests
rows plus the 2 EscapePath and 8 SplitPathVersion InlineData cases,
with the same assertions as the C# xunit methods (I diffed the tables
against the C# sources; they match exactly, and no test was deleted,
weakened or special-cased). … I additionally ran the Python
semver/module/pseudo functions against the upstream golang.org/x/mod
test vectors … and they all pass.
```

**What just happened.** Read the sign-off for what it cites:

1. **Row counts** for each table it ported.
2. **How it checked** that no table was quietly shortened: it diffed them against the C#.
3. **A third source** it checked against, the upstream Go test vectors.

None of that was in the prompt. The loop got it by refusing to say `done` until it was true.

Check it yourself:

```sh
cd python && python -m pytest -q
```

```console
.........................................................    [100%]
389 passed in 0.47s
```

```sh
wc -l golang_x_mod/*.py tests/*.py
```

```console
    5 golang_x_mod/__init__.py
  846 golang_x_mod/module.py
  313 golang_x_mod/semver.py
  177 tests/test_module.py
   58 tests/test_semver.py
```

::: tip Checkpoint
389 passing cases, from 635 lines of C# and 266 of xunit, with all twenty-five stubs
implemented. Before you trust the number, open `tests/test_module.py` beside
`../tests/Golang.Org.X.Mod.Tests/ModuleTests.cs`: the tables should hold the same rows.
:::

## Troubleshooting

### It says the official flowverse has not been fetched yet

```console
hmz exec: error: rlar: the official flowverse has not been fetched yet -- open the flowverses page of /settings and fetch it from its own sheet
```

Run `hmz` once, wait a moment, and run the line again. If it is still refused, type
`/settings flowverses` in `hmz`, open `official`, and choose `fetch`.

### `dsh` is not offered, or its turns fail with no key

DeepSeek Harness needs the `[dsh]` extra in humanize's own environment and a key. See
[Installation](/user/installation).

### It ran out of budget before the reviewer said `done`

The loop is resumable: run the same line with `--resume` and a fresh `-b`. A fresh actor is
handed the last review to pick up from. See [Picking a run up](/user/resuming).

## What you learned

- An actor that keeps one conversation remembers its decisions; a reviewer that starts fresh
  every round judges only what is in the repository.
- A task file has to close the shortcuts a job invites, here porting stubs as stubs and
  weakening the suite.
- `rlar` ends on a structured answer, `done`, so the run stops when the reviewer is satisfied
  rather than when the budget runs out.
- A green suite is where the reviewer's questions start, not where they end.

## Next steps

- **Port the next slice.** `src/Lip.Core/` is the rest of the migration. Use the same `TASK.md`
  with the new slice named in it, and the same command. The technique is landing a migration
  one verifiable project at a time; the flow only runs it.
- **Give the reviewer a different model.** Its job is to disagree, and two models that fail
  differently disagree more usefully than one model twice.
- **Change what "done" means.** Walk to `rlar` in `/flow` and choose `copy rlar here` to copy
  it into this project. `-f rlar` then runs your copy. The run ends on the reviewer's `done`,
  and the field's `description` says when it may be true, so adding "and `ruff check` passes"
  there changes what ends the run. See [Answers in a shape](/weaver/shapes).
- **Change how reviews are written.** The reviewer carries a [skill](/user/skills),
  `skills/review-notes/SKILL.md` in the flow's directory, which your copy lets you edit.
  DeepSeek Harness loads no skills, so on it the reviewer works from the prompt alone.
- **See the flow's shape in a trace.** `/epics` in `hmz`, then **export run**, as in
  [Tracing](/user/tracing). The actor shows one session and the reviewer one per round.
- **Next tutorial:** [Build a coding agent](/user/tutorials/build-an-agent), which starts from
  nothing but a sentence.
