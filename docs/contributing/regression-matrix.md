# The regression matrix

In this guide you run the regression matrix, read its grid, and add a row of your own. The
matrix runs every feature humanize offers through every coding agent CLI it drives, on the real
CLIs signed in on your machine, and prints one grid: a row per feature, a column per CLI.

Run it before a release, and after any change that could reach more than one CLI. Add a row
whenever you add a feature.

::: info Before you start
- A checkout set up as in [Contributing](/contributing/): `uv sync` done.
- At least one coding agent CLI installed and signed in. Each CLI you have is a column; one you
  do not have skips, and says so.
- Money to spend: the matrix drives real models. [What it costs](#what-it-costs) has the
  figures.
:::

## How it works

Each **cell** is one feature through one CLI: a pytest test called `test_<feature>[<cli>]`,
which drives humanize the way a person or a program would and checks what they would see. A
feature that is about no one CLI, such as a page of `/settings`, is a row run once, in a last
column called `any`.

Each CLI's column runs at one **place**: an account, a model and an effort. The cheapest model
the CLI takes, as you signed it in, comes first.
[Where each column runs](#where-each-column-runs) has the rest.

It spends real tokens, so CI never runs it and nothing else will run it for you.

## Run it

Start with two cells, to see the shape of a run for a few cents:

```sh
uv run pytest tests/system/matrix --run-agents -m matrix -k "test_plain_turn and (claude or codex)"
```

```text
32 workers [2 items]

..                                                                       [100%]
======================= regression matrix: feature x CLI =======================
| feature | claude | codex |
|---|:-:|:-:|
| plain_turn | pass | pass |

Cells: 2 pass.
Spent: $0.0104 and 73 output tokens, as priced by this machine's price list (unpriced models count as $0).

Where each column ran:

- `claude`: `claude/claude-haiku-4-5-20251001:low (as local)`
- `codex`: `codex/gpt-5.5:low (as local)`
============================== 2 passed in 14.94s ==============================
```

- **`--run-agents`** lets the cells drive real CLIs. Without it every cell skips, and no grid
  is drawn.
- **`-m matrix`** selects the matrix's cells and nothing else in `tests/system/matrix`.
- **`-k`** narrows it, by the cell's name.
- **The grid** is drawn at the foot of the run, then the cells' tally, what they spent, and
  the place each column ran at.

Then the whole of it, or a slice:

::: code-group

```sh [All of it]
uv run pytest tests/system/matrix --run-agents -m matrix
```

```sh [One CLI]
uv run pytest tests/system/matrix --run-agents -m matrix -k claude
```

```sh [One feature]
uv run pytest tests/system/matrix --run-agents -m matrix -k steer
```

```sh [Keep the grid]
uv run pytest tests/system/matrix --run-agents -m matrix --matrix-report=matrix.md
```

:::

`--matrix-report` writes the grid as markdown, or as JSON for a path ending `.json`.

## Read the grid

A full run draws every row and column:

```text
======================= regression matrix: feature x CLI =======================
| feature | claude | agy | codex | dsh | grok | kimi | pi | qwen | opencode | mimo | cursor-agent | mcode | any |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| plain_turn | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass | pass | - |
| steer | pass | n/a | pass | n/a | n/a | pass | pass | n/a | n/a | n/a | n/a | n/a | - |
...
| settings_accounts | - | - | - | - | - | - | - | - | - | - | - | - | pass |
```

| Mark | Means | What to do |
| --- | --- | --- |
| `pass` | it passed | nothing |
| `FAIL` | it failed | fix humanize, or mark it as a known bug |
| `xfail` | a known bug, written on the feature, is still there | nothing, until it is fixed |
| `XPASS` | a known bug has gone | take the mark off |
| `n/a` | the CLI cannot do this at all | nothing |
| `skip` | this machine could not give the cell what it needs | read the reason |
| `-` | not run | nothing |

Under the grid the run lists why each cell that did not pass did not. A `skip` names what was
missing: a CLI that is not installed, an account that would not take a turn, a provider that
refused or throttled one, no docker for the ssh row.

::: warning A refused file or socket is never a skip
A turn the kernel refused a file or a socket (`EACCES`, `EPERM`, `permission denied`) fails,
whatever its CLI's error was taken for: that is a fence held too tightly, and humanize's.
:::

## Where each column runs

The first cell of a column asks the candidates in `tests/matrix/places.py` for one word each,
in order, and every cell of the column runs at the first that answers:

1. **As local**, the CLI as you signed it in, at the cheapest model it takes.
2. **An account this machine keeps**, where as local does not answer. The account is copied out
   of `~/.humanize/providers` into the test's own home, through `hmz.sdk.Hmz().accounts`, and
   removed when the cell ends. Nothing in `~/.humanize` is written. An account signed in with a
   login whose token refreshes itself (a file holding a refresh token) is never copied: it is
   passed over with `signs in with a token that refreshes itself`, since a copy refreshing
   apart from it would get the original revoked.

A column with no place that answers skips, cell by cell, and says what each candidate said.
The `named_account` row always runs under an account made the second way.

## What it costs

A cell takes one to three turns of a few words each, on the cheapest model its CLI takes, under
`-b cost=0.5,output_tokens=40000`. The whole matrix is 423 cells: 35 rows for each of twelve
CLIs, and 3 rows run once. A run of all of it spent about 29,000 output tokens, a dollar of it
priced, and took under half an hour, as it did inside a whole `uv run pytest --run-agents`:
the slowest column sets the time. The run prints what it spent, priced from the list your
machine last fetched; a model nobody lists a price for counts as $0.

Under `--run-agents`, xdist runs one CLI's cells one after another on one worker, and the CLIs
side by side. Two turns into one CLI's local store at once can lose a write, and a provider
can refuse the second. Pass another `--dist`, such as `--dist worksteal`, to choose otherwise.

## Add a feature

A feature is one test function in `tests/system/matrix/`, decorated with `feature`. It is run
for every CLI. This is the matrix's first row, `plain_turn`, as it is:

```python
@feature()  # ①
def test_plain_turn(cell: Cell) -> None:  # ②
    """One turn of `chat` through `hmz exec --json`: the answer, in a stream a program reads."""
    word = _word()  # ③

    ran = cell.exec(  # ④
        "chat",
        f"Reply with exactly one word, {word}, and nothing else.",
        agents=[cell.agent("assistant")],
        budget="",
    )

    assert _says(ran.answer, word), ran  # ⑤
    assert ran.said("result"), f"no turn ended in a result\n{ran}"
```

1. **`feature()`** makes the function a row: parametrized over every CLI, gated behind
   `--run-agents`, grouped by CLI for xdist, and selectable with `-m matrix`. It is imported
   from `tests.matrix.cells`.
2. **The name** is the row: `test_plain_turn` is `plain_turn`. **`cell`** is the CLI and its
   place.
3. **`_word()`** makes a word no model would say unprompted, such as `KIWI4821`, so an answer
   that contains it was not a guess.
4. **`cell.exec(...)`** runs `hmz exec` as a process and reads its `--json` stream.
   `cell.agent("assistant")` is the `-a` for this cell's place. `budget=""` runs `chat` with no
   budget, as it may. `cell.run(...)` runs a flow through `hmz.sdk.Hmz` instead,
   `cell.flow(name, source)` writes a flow a few lines long outside the workspace the agent
   sees, and `cell.hmz.epics` reads back what a run left.
5. **Check what a person or a program would see**: an answer, a file on disk, an event in the
   stream, a run's record read through `hmz.sdk`. Never a driver's insides.

Keep it cheap: a prompt of a few words, and a word to check for.

### Say what a CLI must be able to do

A CLI that cannot is `n/a` before anything starts:

```python
@feature(mixin(SteeringAgentMixin))
def test_steer(cell: Cell) -> None:
    """A word put into a turn that is running is what the turn goes on from."""
```

| `feature(...)` | A CLI that cannot is `n/a` |
| --- | --- |
| `mixin(GoalCommandAgentMixin)` | its harness serves no such mixin |
| `forks` | its profile says it cannot fork a conversation |
| `mounts` | it reads no skill a flow brings |
| `read_only` | its driver can hold it to nothing narrower than bypass |
| `limits={"agy": "why, and where that is written"}` | a limitation no table in humanize says |

### Mark a known bug

A failure that is humanize's and is not fixed yet is marked on the feature, with the bug:

```python
@feature(xfail={"codex": "fork into another workdir loses the session: #123"})
```

The mark is strict. When the bug is fixed the cell reads `XPASS` and fails until the mark comes
off. A bug that bites some runs and not others, or whose fix is another pull request not yet
merged, is `Unsettled` instead: the cell reads `XPASS` without failing on a run it does not
bite, so neither a lucky run nor the order two changes land in turns the grid red.

```python
@feature(xfail={"dsh": Unsettled("the SDK spawns into a mirror not made yet: #456")})
```

### A row run once

A feature that is about no one CLI, such as a page of `/settings` or two interfaces sharing a
run, is run once rather than once per CLI, and drawn in the column `any`. Its function takes no
`cell`, and settles for itself whatever it needs; `billed` gives it this machine's prices and
puts what it spent on the bill. One that takes turns of one CLI all the same names it as its
`group`, and runs among that CLI's cells rather than beside them:

```python
@feature(once=True, group="dsh", timeout=600)
async def test_settings_accounts(asking: None) -> None:
    """An account added on the one form of `/settings accounts` is one a real turn runs as."""
```

A scenario that needs something more of the machine takes a fixture for it, as `test_ssh_env`
takes `ssh_box`. It skips, saying what was missing, where the machine has none.

### Check it worked

Run your row alone, on the CLIs you have:

```sh
uv run pytest tests/system/matrix --run-agents -m matrix -k <feature>
```

Every column should read `pass`, `n/a` or a `skip` whose reason is this machine's, not
humanize's.

## Add a CLI

A CLI humanize drives is a column as soon as it is in `PROFILES` in `coganchor/backends.py`.
Give it candidates in
`tests/matrix/places.py`: its cheapest model as local, then an account. [Adding a
backend](/contributing/architecture#adding-a-backend) has the rest of what a new CLI takes.

## Pitfalls

::: details The fence rows write outside the test's own directory
Five rows hold an agent to a `Permission` and check each scope on disk: `fence_default`,
`fence_system_none`, `fence_user_none`, `fence_offline` and `fence_open`. The agent runs one
script the row wrote into its workdir, and each row checks what landed on disk rather than
what the agent said. To have something to refuse, they write outside the test's directory:
a file in your home directory named `.hmz-fence-<cli>-<random>`, one of the same name under
`/var/tmp`, and a `hmz-matrix-<cli>-*` directory in the system's temporary directory. Every
cell has its own names, and removes them when it ends. `fence_open` also writes such a file
to your home directory, as an agent granted everything may. `fence_offline` asks the agent's
web tool for a page on `api.github.com` that no model knows by heart. If the answer quotes
that page, the network was not cut. It is `n/a` for `cursor-agent` and `mcode`, which are
refused a cut network: their web search runs on their vendor's own servers.
:::

::: details The rows about other machines need docker
`test_ssh_env` and `test_ssh_provider` run their agent on another machine: an `sshd` in a
container, built from `python:3.12-slim` the first time it is asked for (`ssh_box` in
`tests/flows/sshd.py`). Pull that image once with `docker pull python:3.12-slim`; without
docker, or without the image, the rows skip and say so. A loopback `sshd` will not do here: an
agent's copy of a host's directory sits at the host's own path on this machine, so on a
loopback host the copy and the host's directory are one directory, and the agent's writes land
on the file they were read from.

`test_docker_env`, `test_harness_placement`, `test_fence_docker` and `test_docker_gpu` put the
agent's environment in a container of `python:3.12-slim` on docker's default here; the GPU row
skips where that daemon lists no NVIDIA GPU by its CDI name. `test_docker_env_remote` puts it
on a daemon somewhere else: docker's own daemon in a privileged container, `docker:dind` with
an `sshd` added (`docker_box`), reached through a saved ssh provider, with `python:3.12-slim`
loaded into it from here. Pull that one too with `docker pull docker:dind`. Its directories
are not this machine's, so the row can tell a workdir that was mounted there from one that
was not.

`test_frontends_tui` drives two `hmz` interfaces in a tmux of its own, and skips without
`tmux`. `test_settings_accounts` fills the accounts form in with the `dsh` gateway account in
`~/.humanize/providers`, read and never written, and takes the new account off disk after.
:::

- **A skipped column is not a passed one.** Read the reasons under the grid before you call a
  change safe for a CLI.
- **Two runs at once share your CLIs' stores.** Run one matrix at a time on a machine.

## Next steps

- [Adding a backend](/contributing/architecture#adding-a-backend)
- [Contributing › The checks](/contributing/#the-checks), for the tiers the matrix sits beside
