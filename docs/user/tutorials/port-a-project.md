# Port a project

**About an hour, most of it waiting.** You move one module of a real C# project to Python. One
agent does the porting in a single long conversation, and a fresh reviewer checks what actually
landed after every round. At the end you have:

| You end with | Where |
| --- | --- |
| a Python port of two C# files, the methods the C# never finished included | `python/golang_x_mod/` |
| every case in the C# test tables, ported and passing | `python/tests/` |
| the reviewer's sign-off, which is what ended the run | printed as the run ends |

::: tip Before you start
Do the [quickstart on the home page](/#run-a-flow) first. Any backend works, DeepSeek Harness
included, which needs only an API key and an extra you add in step 3.
:::

## Step 1: get the project

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

It makes a good first slice. It does no I/O, it has tables of test cases, and the original Go
is there as a second opinion wherever the C# is unclear. It also has a trap:

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

## Step 2: write the task down

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

The highlighted rules close the two shortcuts: porting the stubs as stubs, and making the suite
pass by weakening it.

## Step 3: run it

The flow is [`rlar`](/flows/rlar), a Ralph loop with an actor and a reviewer. The **actor**
keeps one conversation for the whole run, so it remembers every decision it made. Each time it
finishes a turn, the **reviewer** opens a fresh one, reads the repository with `git diff` and
the tests, and answers two things: `done`, true or false, and `notes`. The notes become the
actor's next prompt, word for word.

<HmzFlowShape flow="rlar" />

Pick the tab for the backends you have:

:::: details Using DeepSeek Harness? Add humanize's `[dsh]` extra first
Run the line for the way you installed humanize:

::: code-group

```sh [pip]
pip install 'hmz[dsh] @ git+https://github.com/humanfia/humanize.git'
```

```sh [pipx]
pipx install --force 'hmz[dsh] @ git+https://github.com/humanfia/humanize.git'
```

```sh [uv tool]
uv tool install 'hmz[dsh] @ git+https://github.com/humanfia/humanize.git'
```

:::
::::

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
    -a actor=claude/claude-opus-5:high \
    -a reviewer=codex/gpt-5.6-sol:high \
    -b duration=3h,cost=30 \
    "$(cat TASK.md)"
```

```sh [Claude Code only]
hmz exec -f rlar \
    -a actor=claude/claude-opus-5:high \
    -a reviewer=claude/claude-opus-5:high \
    -b duration=3h,cost=30 \
    "$(cat TASK.md)"
```

:::

There is one `-a` per role. The same model in both is fine: the reviewer is independent because
its conversation has never seen the actor's, not because it runs a different model. `-b` caps
the run, and the reviewer usually ends it sooner.

```console
● actor is working
  …
✻ Worked for 1210s · actor
● reviewer is working
  …
✻ Worked for 95s · reviewer
● actor is working
```

::: tip Checkpoint
Each round is one long actor turn followed by a short reviewer turn. If the run is refused
instead, `hmz exec: error: …` names the part of the line it could not use.
:::

## Step 4: watch a round go by

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

The actor checked its own work against a third source because a reviewer that had never seen
its reasoning asked it to.

## Step 5: see where it stopped

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

It cites row counts, says how it checked that no table was quietly shortened, and names a third
source it checked against. None of that was in the prompt. The loop got it by refusing to say
`done` until it was true.

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

## Where next

- **Port the next slice.** `src/Lip.Core/` is the rest of the migration. Use the same `TASK.md`
  with the new slice named in it, and the same command. The technique is landing a migration
  one verifiable project at a time; the flow only runs it.
- **Give the reviewer a different model.** Its job is to disagree, and two models that fail
  differently disagree more usefully than one model twice.
- **Change what "done" means.** Press <kbd>f</kbd> on `rlar` in `/flow` to copy it into this
  project. `-f rlar` then runs your copy. The run ends on the reviewer's `done`, and the
  field's `description` says when it may be true, so adding "and `ruff check` passes" there
  changes what ends the run. See [Answers in a shape](/weaver/shapes).
- **Change how reviews are written.** The reviewer carries a [skill](/user/skills),
  `skills/review-notes/SKILL.md` in the flow's directory, which your copy lets you edit.
  DeepSeek Harness loads no skills, so on it the reviewer works from the prompt alone.
- **See the flow's shape in a trace.** `/epics` in `hmz`, then **export it**, as in
  [Tracing](/user/tracing). The actor shows one session and the reviewer one per round.
- **Next tutorial:** [Build a coding agent](/user/tutorials/build-an-agent), which starts from
  nothing but a sentence.
