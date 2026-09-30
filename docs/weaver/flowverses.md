# Flowverses

In this guide you publish a flow so that other people can run it by name, and add somebody
else's flows to your own humanize. You build `my-flowverse`, a git repository holding one
`review` flow, test it, add it under the name `yours`, run it as `yours/review`, and call it
from another flow by URL.

Publish a flowverse when a flow is useful beyond the project you wrote it in. Add one when
somebody else has written the flow you need.

::: info Before you start
- A flow of your own, tested: [Your first flow](/weaver/writing-a-flow) and [Testing a
  flow](/weaver/testing-flows).
- A git host you can push to, such as GitHub. Any URL `git clone` takes works, and so does a
  path on this machine.
:::

## How it works

A **flowverse** is a git repository with a `flows/` directory in it. There is no manifest and
nothing to register: every flow under `flows/` is offered as `<flowverse>/<flow>`, where
`<flowverse>` is the name you added the repository under.

humanize keeps a clone of each flowverse you add, and reads flows from these places:

| Place | Holds | Run as |
| --- | --- | --- |
| `local` | this project's `.humanize/flows/` | `local/review`, or `review` |
| `user` | your `~/.humanize/flows/`, for every project | `user/review`, or `review` |
| each flowverse you added | its `flows/` | `yours/review` |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse), and the `chat` flow humanize ships | `rlar`, or `official/rlar` |

`official`, `local` and `user` are always there and cannot be taken away. A flowverse is
fetched when you add it, when you ask, and in the background when you open `hmz`. `hmz exec`
fetches nothing.

## Example: publish a review flow

### 1. Lay out the repository

```text
my-flowverse/
├── flows/
│   └── review/
│       └── __init__.py    →  offered as yours/review
├── tests/
│   └── test_review.py     →  not read by humanize: only flows/ is
└── README.md
```

### 2. Write the flow

```python
# flows/review/__init__.py
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv  # ①


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def review(  # ②
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Review the current diff and write the findings to REVIEW.md."""  # ③
    reviewer = agents["reviewer"]
    session = await reviewer.spawn(env=envs["workspace"])
    await reviewer.run(
        f"Write what is wrong with the diff to REVIEW.md.\n\n{task}",
        session=session,
    )
```

1. **`LocalEnv`** is the directory whoever runs the flow starts it in: their project, not your
   repository. A flow from a flowverse works where it is run.
2. **The function is named after its directory**, `review` in `flows/review/`, so that
   `yours/review` means it.
3. **The docstring's first line** is what somebody sees beside the flow's name before they run
   anything, in `/flow`, on the Flowverses page and in `holds` below. Make it say what the flow
   does and what it writes.

### 3. Test it

The fake kit takes a flow by path as well as by name, so the repository tests its own flows
without adding itself anywhere:

```python
# tests/test_review.py
from hmz.sdk import fakes


async def test_review_asks_for_review_md() -> None:
    reviewer = fakes.FakeAgentDriver()  # ①

    await fakes.run_fake(
        "flows/review",  # ②
        "the payments module",
        agents={"reviewer": reviewer},
    )

    assert reviewer.prompts == [  # ③
        "Write what is wrong with the diff to REVIEW.md.\n\nthe payments module"
    ]
```

```sh
uvx --with 'hmz @ git+https://github.com/humanfia/humanize.git' \
    --with pytest-asyncio pytest -q -o asyncio_mode=auto
```

```text
.                                                                        [100%]
1 passed in 0.09s
```

1. **A fake reviewer** answers `"ok"` and records what it was asked.
2. **`"flows/review"`** is a path, relative to the repository root pytest runs in.
3. **The prompt** carries the fixed instruction and then the task, in that order.

[Run the tests in CI](/weaver/testing-flows#run-the-tests-in-ci) has the `pyproject.toml` and
the workflow that run this on every push.

### 4. Push it

```sh
cd my-flowverse
git init -q -b main && git add -A && git commit -qm "a review flow"
git remote add origin git@github.com:you/my-flowverse.git
git push -u origin main
```

### 5. Add it

Add the repository under the name `yours`, in any project:

::: code-group

```text [At the prompt]
/settings flowverses
  add a flowverse     a git repository of flows
  repository          you/my-flowverse
  name                yours
```

```python [From a script]
from hmz.sdk import Hmz

verses = Hmz().verses
verses.add("you/my-flowverse", "yours")
print(verses.holds(verses.find("yours")))
```

:::

At the prompt, `add a flowverse` asks for the repository, as a URL or `owner/repo` for one on
GitHub, and a name to keep it under. Leave the name blank for the repository's own. Confirming
clones the repository and adds its flows. From a script, `add` does the same and returns once
it is cloned, and `holds` lists what it offers:

```text
[Offer(whose='yours', name='yours/review', about='Review the current diff and write the findings to REVIEW.md.')]
```

### 6. Run it

::: code-group

```text [At the prompt]
$yours/review the calc module
```

```sh [hmz exec]
hmz exec -f yours/review -a reviewer=claude/claude-sonnet-5-5:high -b cost=1 \
    "the calc module"
```

:::

A real run, in a project whose `add` was changed to subtract:

```text
● reviewer is working
● Bash(cd /home/you/calc && git diff && cat calc.py && ls)
● Bash(cd /home/you/calc && cat check.py)
● Write(/home/you/calc/REVIEW.md)
● I wrote the review to `/home/you/calc/REVIEW.md`. The diff changes `add(a, b)` in `calc.py` from `a + b` to `a - b`, so `add` now subtracts. …
✻ input 8 · output 563 · cache_read 61.5k · cache_write 5.9k · $0.03 · claude-sonnet-5-5 · reviewer
…
✻ Worked for 8s · reviewer
```

The first time at the prompt, `/flow` opens on the flow to ask what runs `reviewer` and what
the run may spend, and starts it once you save. Anybody else adds `you/my-flowverse` the same
way, and runs `review` under whatever name they chose.

## Check it worked

- **It is listed.** `/settings flowverses` shows `yours` beside `official`, `local` and
  `user`. Open it to see its flows, each beside its docstring's first line:

  ![what a flowverse holds, on the Flowverses page of /settings: each flow's name, beside the
  first line of its docstring](/demo/flowverse-holds.png)

- **It ran where you are.** The review is in the project you ran it in: `cat REVIEW.md`.
- **It runs by URL.** Nothing added, the same flow runs from its repository:
  `-f 'git+https://github.com/you/my-flowverse#review'`.

## What goes in the repository

| Rule | |
| --- | --- |
| Flows go in `flows/` | Nothing outside it is read or run, so the repository can hold tests, a README and a `pyproject.toml` |
| One directory per flow | Its `__init__.py` holds the `async` function marked `@flow` |
| Name the flow after its directory | `review` in `review/`, so that `yours/review` means it |
| Or a single `.py` file | For a flow with nothing to bring along |
| Several flows in one directory | Each `@flow` is a flow of its own. The one named after the directory is `yours/review`, and the others `yours/review:<name>`, such as `yours/review:quick` |
| A name starting with `_` | Is not a flow |

**Keep a flow's own code in its own directory.** Besides installed packages, a flow can import
only what sits beside its `__init__.py`, so a `_shared.py` at the top of `flows/` cannot be
imported: the import fails with `ModuleNotFoundError: No module named '_shared'`. Put the
helpers in a package named after the flow, as the official flowverse does. Every flow a run
loads shares one set of module names, so a generic name such as `utils` clashes with the next
flow that picks it.

```text
flows/
└── review/
    ├── __init__.py        from _review import prompts
    ├── _review/           this flow's helpers
    │   ├── __init__.py
    │   └── prompts.py
    └── skills/            skills its agents are given
        └── review-notes/SKILL.md
```

See [Skills](/user/skills) for what goes in `skills/`.

**Write the README for somebody deciding whether to trust it.** For each flow, say:

- the roles it drives, and what each is for;
- which CLIs it runs on, where a role asks for something only some serve, such as a
  [hook](/weaver/hooks) or a [goal](/weaver/goals). `hmz exec` refuses the others before the
  first turn, but the README saves somebody the attempt;
- its params, and what each does;
- what it writes: files, branches, commits, pushes;
- the `hmz exec` line that starts it, word for word.

## Managing flowverses

The Flowverses page of `/settings` (type `/settings flowverses`), or the `manage flowverses`
row in `/flow`, lists every place flows come from:

![the Flowverses page of /settings: every place flows come from, then enter on one to read
what it holds](/demo/flowverses.gif)

| Row | Does |
| --- | --- |
| `add a flowverse` | Asks for a repository and a name, then clones it |
| a flowverse | Opens what it holds. Above its flows, `fetch again` (or `fetch`, for one never fetched) fetches it from its repository, and `remove <name>` takes it away, flows and all |

From a script, [`Hmz().verses`](/reference/sdk#flowverses) does the same with nothing open:

```python
from hmz.sdk import Hmz

verses = Hmz().verses
verses.all()                        # every place, as listed
verses.add("you/my-flowverse", "yours")
verses.holds(verses.find("yours"))  # its flows, as -f names them
verses.fetch("yours")               # again, or for the first time
verses.remove("yours")              # flows and all
```

A flowverse added from a script can be run with `-f` at once.

**A fetch resets the clone** to what the repository says. Opening `hmz` fetches every
flowverse in the background, except one with edits made inside its clone, and a fetch you ask
for resets even that. To change somebody else's flow, walk to it in `/flow` and choose
`copy <flow> here`, or call `Hmz().flows.fork("yours/review")`. Either copies it into
`.humanize/flows/review`, where your edits are yours to keep, and from then on `review` in that
project means your copy.

::: danger Adding a flowverse is trusting that repository with this machine
A flow is Python. Once a flowverse is added, humanize imports its flows whenever it lists
flows, and every agent a flow drives runs with approvals bypassed. Add the repositories you
would install as a package, and read [Security](/user/security) first.
:::

## What a flow is called

| You type | Runs |
| --- | --- |
| `rlar` | the nearest flow called `rlar`: yours if you have one, else humanize's |
| `yours/review` | `review` from the flowverse you added as `yours`, and nothing else |
| `local/review` | `review` in this project's `.humanize/flows` |
| `user/review` | `review` in your `~/.humanize/flows`, for every project |
| `./flows/review` | the flow at that path |
| `git+…#review` | `review` from a repository by URL, at `@<rev>` if given, fetched for the run |

A bare name is looked for **nearest first**: this project's `.humanize/flows`, then
`~/.humanize/flows`, then the flowverses. So a flow of your own can stand in for one of
humanize's by taking its name: `.humanize/flows/chat/` is what `-f chat` runs in that project.
`yours/review` names one place, so nothing can stand in for it.

## Calling it from another flow

A flow can [call another](/weaver/calling-flows) by the same names. Inside one flowverse, a
flow calls its neighbours by directory, as `review` or `humanize1:gen-plan`. A flow from
another flowverse is called by URL, whether or not anybody has added it:

```python
from hmz.flows import load

review = load("git+https://github.com/you/my-flowverse@v1.2#review")
```

The `@v1.2` holds the caller to one version of the flow: a tag, a branch or a commit. This is a
reason to publish two small flows rather than one large one: another weaver can call a phase,
but can only run a pipeline whole.

## Variations

**Run without adding.** `-f 'git+https://github.com/you/my-flowverse#review'` fetches the
repository for the run and adds nothing.

**Pin a version.** `official` follows the default branch of
[humanfia/flowverse](https://github.com/humanfia/flowverse). To hold a run to one version of a
flow, name it by commit: `-f 'git+https://github.com/humanfia/flowverse@<sha>#rlar'`.

**Start from somebody else's.** Copy their flow into your project with `copy <flow> here`,
change it, then move the directory into your own flowverse's `flows/` to publish it.

## Pitfalls

- **Not fetched yet.** `hmz exec` fetches nothing, so on a fresh machine a flow from `official`
  is refused until it has been fetched:

  ```text
  hmz exec: error: rlar: the official flowverse has not been fetched yet -- open the flowverses page of /settings and fetch it from its own sheet
  ```

  Open `hmz` once, or in CI call `Hmz().verses.fetch("official")` first.
- **Do nothing at import time** beyond defining things: no network calls, no files written.
  humanize imports every flow it lists, in `/flow`, in `/settings` and as `$` completes a name,
  so a flow that acts on import acts for somebody who was only looking.
- **Edits inside a clone go away** at the next fetch you ask for. Copy the flow into your
  project first.
- **A name that is not there** is refused before anything runs:
  `hmz exec: error: yours/nope: no flow is called 'yours/nope', and it is not a path`.

## Next steps

- [Flows](/flows/): every flow humanize offers, with the shape of each drawn
- [Testing a flow](/weaver/testing-flows)
- [A flow that calls a flow](/weaver/calling-flows)
- [Reference › Flows › Flowverses](/reference/flows#flowverses)
- [SDK reference › Flowverses](/reference/sdk#flowverses)
