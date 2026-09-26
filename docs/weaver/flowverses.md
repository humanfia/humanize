# Flowverses

A **flowverse** is a git repository with a `flows/` directory in it. Add one, and every flow in
it is offered by name, as `<flowverse>/<flow>`. Publish your flows in one to share them, and
add somebody else's to run theirs.

## Try it

Publish a flow, add the repository, and run the flow by name.

**1. Lay out the repository.** There is no manifest and nothing to register:

```
my-flowverse/
├── flows/
│   └── review/
│       └── __init__.py    →  offered as yours/review
├── tests/                 →  not read: only flows/ is
└── README.md
```

```python
# flows/review/__init__.py
"""Review the current diff and write the findings to REVIEW.md."""

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
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def review(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Review the current diff and write the findings to REVIEW.md."""
    reviewer = agents["reviewer"]
    session = await reviewer.spawn(env=envs["workspace"])
    await reviewer.run(
        f"Write what is wrong with the diff to REVIEW.md.\n\n{task}",
        session=session,
    )
```

**2. Push it.**

```sh
cd my-flowverse
git init -q -b main && git add -A && git commit -qm "a review flow"
git remote add origin git@github.com:you/my-flowverse.git
git push -u origin main
```

**3. Add it** under the name `yours`:

::: code-group

```text [At the prompt]
> /flowverses
  a             add a flowverse
  repository    you/my-flowverse
  name          yours
  enter         clone it
```

```python [From a script]
from hmz.sdk import Hmz

Hmz().verses.add("you/my-flowverse", "yours")
```

:::

**4. Run it.**

::: code-group

```text [At the prompt]
$yours/review the payments module
```

```sh [hmz exec]
hmz exec -f yours/review -a reviewer=claude/claude-opus-5:high \
    -b cost=5 "the payments module"
```

:::

The first time at the prompt, `/flow` opens on the flow to ask what runs `reviewer` and what
the run may spend, and starts it once you save. Anybody else adds `you/my-flowverse` the same
way and runs `review` under the name they chose. To run it without adding anything, name it by
URL: `-f 'git+https://github.com/you/my-flowverse#review'`.

## What goes in the repository

| Rule | |
| --- | --- |
| Flows go in `flows/` | Nothing outside it is read or run, so the repository can hold tests, a README and a `pyproject.toml` |
| One directory per flow | Its `__init__.py` holds the `async` function marked `@flow` |
| Name the flow after its directory | `review` in `review/`, so that `yours/review` means it |
| Or a single `.py` file | For a flow with nothing to bring along |
| Several flows in one directory | Each `@flow` is a flow of its own, offered as `yours/<flow>:<name>` |
| The docstring's first line | Is shown beside the flow's name wherever flows are listed |
| A name starting with `_` | Is not a flow |

The docstring's first line is what somebody sees before they run anything:

![what a flowverse holds in /flowverses: each flow's name, beside the first line of its
docstring](/demo/flowverse-holds.png)

**Keep a flow's own code in its own directory.** Besides installed packages, a flow can import
only what sits beside its `__init__.py`, so a `_shared.py` at the top of `flows/` cannot be
imported. Put the helpers in a package named after the flow, as the official flowverse does:
every flow a run loads shares one set of module names, so a generic name such as `utils`
clashes with the next flow that picks it.

```
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

**Do nothing at import time** beyond defining things: no network calls, no files written.
humanize imports every flow it lists, in `/flow`, in `/flowverses` and as `$` completes a name,
so a flow that acts on import acts for somebody who was only looking.

**Write the README for somebody deciding whether to trust it.** For each flow, say:

- the roles it drives, and what each is for;
- which CLIs it runs on, where a role asks for something only some serve, such as a
  [hook](/weaver/hooks) or a [goal](/weaver/goals). `hmz exec` refuses the others before the
  first turn, but the README saves somebody the attempt;
- its params, and what each does;
- what it writes: files, branches, commits, pushes;
- the `hmz exec` line that starts it, word for word.

## Adding one

The `/flowverses` command, or <kbd>v</kbd> in `/flow`, lists every place flows come from:

![/flowverses: every place flows come from, then enter on one to read what it
holds](/demo/flowverses.gif)

| Key | |
| --- | --- |
| <kbd>a</kbd> | Add one: a URL or an `owner/repo`, and a name to keep it under. Leave the name blank for the repository's own |
| <kbd>enter</kbd> | What the flowverse under the cursor holds. The last row takes the whole flowverse away |
| <kbd>r</kbd> | Fetch the one under the cursor again, or for the first time |

`official`, `local` and `user` are always listed, and none of them can be taken away.

Opening `hmz` fetches every flowverse again in the background, so an added one follows what
its repository says, and edits made inside the clone do not keep. To change somebody else's
flow, press <kbd>f</kbd> on it in `/flow`: that copies it into `.humanize/flows/`, where your
edits are yours to keep.

From a script, [`Hmz().verses`](/reference/sdk#flowverses) does the same, with nothing open:

```python
from hmz.sdk import Hmz

verses = Hmz().verses
verses.all()                        # every flowverse, as listed
verses.add("you/my-flowverse", "yours")
verses.holds(verses.find("yours"))  # its flows, as -f names them
verses.fetch("yours")               # again, or for the first time
verses.remove("yours")              # flows and all
```

`holds` names each flow as `-f` takes it: `yours/review`, or `yours/review:quick` for one of
several flows in one directory. A flowverse added from a script can be run with `-f` at once.

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

`official` follows the default branch of
[humanfia/flowverse](https://github.com/humanfia/flowverse). To hold a run to one version of a
flow, name it by commit: `-f 'git+https://github.com/humanfia/flowverse@<sha>#rlar'`.

If a flowverse has not been fetched yet, the error says so: open `/flowverses` and press
<kbd>r</kbd> on it. `hmz exec` fetches nothing, so a fresh CI runner calls
`Hmz().verses.fetch("official")` first.

## Calling it from another flow

A flow can [call another](/weaver/calling-flows) by the same names. Inside one flowverse, a
flow calls its neighbours by directory, as `review` or `humanize1:gen-plan`. A flow from
another flowverse is called by URL, whether or not anybody has added it:

```python
from hmz.flows import load

review = load("git+https://github.com/you/my-flowverse@v1.2#review")
```

This is a reason to publish two small flows rather than one large one: another weaver can call
a phase, but can only run a pipeline whole.

## Test it in CI

The [fake kit](/weaver/testing-flows) runs each flow the way `-f` does, with no agent and no
tokens. A flow that stops loading, or stops doing what it says, fails the build:

```python
# tests/test_review.py
from hmz.sdk import fakes


async def test_review_asks_for_the_diff() -> None:
    reviewer = fakes.FakeAgentDriver()
    await fakes.run_fake(
        "flows/review",
        "the payments module",
        agents={"reviewer": reviewer},
    )
    assert "REVIEW.md" in reviewer.prompts[0]
```

[Run the tests in CI](/weaver/testing-flows#run-the-tests-in-ci) has the `pyproject.toml` and
the workflow.

## See also

- [Flows](/flows/): every flow humanize offers, with the shape of each drawn
- [Testing a flow](/weaver/testing-flows)
- [A flow that calls a flow](/weaver/calling-flows)
- [Reference › Flows › Flowverses](/reference/flows#flowverses)
- [SDK reference › Flowverses](/reference/sdk#flowverses)
