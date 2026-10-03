# Flowverses

In this guide you publish a flow so that other people can install it and run it by name, and
install somebody else's. You put a `review` flow in a repository of its own, test it, tag a
release, list it in a flowverse, install it, run it, and call it from another flow.

Publish a flow when it is useful beyond the project you wrote it in. Install one when somebody
else has written the flow you need.

::: info Before you start
- A flow of your own, tested: [Your first flow](/weaver/writing-a-flow) and [Testing a
  flow](/weaver/testing-flows).
- A public GitHub repository you can push to. The official flowverse lists flows on GitHub; a
  flowverse of your own can name any URL `git clone` takes, a path on this machine included.
:::

## How it works

A **flowverse** is an index: a git repository of manifests, one per release of a flow, at
`flows/<flow>/<version>/flow.yaml`. It holds no code. Each manifest says which repository the
release lives in and the exact commit it is, the way
[winget-pkgs](https://github.com/microsoft/winget-pkgs) does for winget. The official one is
[humanfia/flowverse](https://github.com/humanfia/flowverse), and you can add your own.

A flow an index lists is a flow to **install**. Installing one copies that release, at its
commit, into `~/.hmz/installed/<flowverse>/<flow>/`, along with any flows it needs. What runs is
what is built in, what you installed, and your own flows:

| Place | Holds | Run as |
| --- | --- | --- |
| built in | `chat`, `ralph_loop`, `goal`, `flame_chase`, `stateful_ralph`, `continue_loop`, `rlar` | `rlar` |
| `official` | the flows you installed from [humanfia/flowverse](https://github.com/humanfia/flowverse) | `review` |
| a flowverse you added | the flows you installed from it | `yours/review` |
| `local` | this project's `.hmz/flows/` | `local/review`, or `review` |
| `user` | your `~/.hmz/flows/`, for every project | `user/review`, or `review` |

`hmz` fetches every index in the background as it opens, and never touches what is installed.
When an index lists a newer release of a flow you installed, the transcript says so once:

```text
updates available: yours/review 0.1.0 ↑ 0.2.0; update from /flow
```

`hmz exec` fetches nothing and installs nothing.

## Example: publish a review flow

### 1. Lay out the repository

One repository per flow, with the flow in a directory named after it and everything else
beside that directory:

```text
flow-review/
├── review/                →  the flow: what is installed
│   ├── __init__.py
│   └── skills/            →  skills its agents are given, if any
├── tests/
│   └── test_review.py     →  not installed
├── README.md
└── LICENSE
```

### 2. Write the flow

```python
# review/__init__.py
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
   repository. An installed flow works where it is run.
2. **The function is named after its directory**, `review` in `review/`, so that `review` means
   it once it is installed.
3. **The docstring's first line** is what somebody sees beside the flow's name before they run
   anything, in `/flow`. Make it say what the flow does and what it writes.

### 3. Test it

The fake kit takes a flow by path as well as by name, so the repository tests its flow without
installing it:

```python
# tests/test_review.py
from hmz.sdk import fakes


async def test_review_asks_for_review_md() -> None:
    reviewer = fakes.FakeAgentDriver()  # ①

    await fakes.run_fake(
        "./review",  # ②
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
2. **`"./review"`** is a path, relative to the repository root pytest runs in.
3. **The prompt** carries the fixed instruction and then the task, in that order.

[Run the tests in CI](/weaver/testing-flows#run-the-tests-in-ci) has the `pyproject.toml` and
the workflow that run this on every push. `hmz exec -f ./review …` runs it for real, from the
same directory.

### 4. Tag a release

Push the repository, then tag a [SemVer](https://semver.org) version and push the tag:

```sh
cd flow-review
git init -q -b main && git add -A && git commit -qm "a review flow"
git remote add origin git@github.com:you/flow-review.git
git push -u origin main
git tag v0.1.0 && git push origin v0.1.0
git rev-parse 'v0.1.0^{commit}'   # the commit a manifest pins
```

The release runs at once, by URL, with nothing installed:

```sh
hmz exec -f 'git+https://github.com/you/flow-review@v0.1.0#review' \
    -a reviewer=claude/claude-sonnet-5-5:high -b cost=1 "the calc module"
```

### 5. List it

A release is listed by its manifest, `flows/review/0.1.0/flow.yaml`:

```yaml
name: review
version: 0.1.0
description: Review the current diff and write the findings to REVIEW.md.
repo: you/flow-review
ref: v0.1.0
commit: 4b1f0c9e2d7a83f5c6e0b9a1d2c3e4f5a6b7c8d9
subdir: review
license: Apache-2.0
```

| Key | |
| --- | --- |
| `name` | The flow: the `<flow>` directory it is in, `[a-z][a-z0-9_]*`. |
| `version` | The release, as [SemVer 2.0.0](https://semver.org): the `<version>` directory it is in. |
| `description` | One line, shown beside the flow before anybody installs it. |
| `repo` | Where the release lives: `owner/repo` on GitHub, or any URL git fetches (`https://`, `ssh://`, `file://`…). |
| `ref` | The tag or branch it was cut from, for whoever reads the index. |
| `commit` | What `ref` resolved to, all 40 hex digits. This is what is installed. |
| `subdir` | The directory holding the flow: its `__init__.py`, or `<name>.py`. Left out, the repository's root. |
| `license` | Its licence, as [SPDX](https://spdx.org/licenses/) names it. |
| `dependencies` | Optional: other flows of the same flowverse it calls, each with a version range. See [Dependencies](#dependencies). |

Keys humanize does not know are ignored, so an index written for a later humanize still lists.

**In the official flowverse.** Fork [humanfia/flowverse](https://github.com/humanfia/flowverse),
add the manifest, and open a pull request. Its
[CONTRIBUTING.md](https://github.com/humanfia/flowverse/blob/main/CONTRIBUTING.md) is the whole
guide: naming, what CI checks, review, new versions and withdrawals. Once it is merged, every
`hmz` lists `review` under `official` after its next fetch, and it installs and runs as
`review`.

**In a flowverse of your own.** A repository laid out the same way, for flows you keep to
yourself or want to try before the pull request is merged:

```sh
mkdir -p my-flowverse/flows/review/0.1.0 && cd my-flowverse
$EDITOR flows/review/0.1.0/flow.yaml     # the manifest above
git init -q -b main && git add -A && git commit -qm "review 0.1.0"
git remote add origin git@github.com:you/my-flowverse.git
git push -u origin main
```

The rest of this example uses this one.

### 6. Add it, and install the flow

::: code-group

```text [At the prompt]
/flow → Install more… → Add flowverse…
  repository   you/my-flowverse
  name         yours
then  yours › review › Install 0.1.0
```

```python [From a script]
from hmz.sdk import Hmz

verses = Hmz().verses
verses.add("you/my-flowverse", "yours")
for one in verses.install("yours/review"):
    print(one.called, one.version, one.at)
```

:::

At the prompt, `/flow` opens on what is installed, and **Install more…** goes to the
flowverses. **Add flowverse…** asks for the repository, as a URL or `owner/repo` for one on
GitHub, and a name to keep it under; leave the name blank for the repository's own. Confirming
clones its index. <kbd>enter</kbd> on `yours` lists its flows, <kbd>enter</kbd> on `review`
its releases, and **Install 0.1.0** fetches `you/flow-review` at the commit and installs it,
at once. From a script, `add` returns once the index is cloned, and `install` once the flow is
in place:

```text
yours/review 0.1.0 /home/you/.hmz/installed/yours/review
```

### 7. Run it

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
the run may spend, and starts it once you save. Anybody else adds `you/my-flowverse` and
installs `review` the same way, under whatever name they chose for it.

## Check it worked

- **It is installed.** `/flow` lists `review` under `yours`, with `0.1.0` at the far end of its
  row.
- **It ran where you are.** The review is in the project you ran it in: `cat REVIEW.md`.
- **It runs by URL.** With nothing installed, the same release runs from its repository:
  `-f 'git+https://github.com/you/flow-review@v0.1.0#review'`.

## What goes in the repository

| Rule | |
| --- | --- |
| One flow per repository | Its variants included: see below |
| The flow in a directory named after it | `review/`, holding the `__init__.py` with the `async` function marked `@flow`. Only this directory is installed, so the repository can hold tests, a README and a `pyproject.toml` beside it |
| Or a single `.py` file | `review.py`, for a flow with nothing to bring along. It is installed as a directory of its own |
| A name humanize does not ship | `[a-z][a-z0-9_]*`, and not `chat`, `ralph_loop`, `goal`, `flame_chase`, `stateful_ralph`, `continue_loop` or `rlar`: a manifest naming one of those is skipped |
| A name starting with `_` | Is not a flow |

**Variants are subflows of one module.** Two takes on one flow go in one directory as two
`@flow`s, released together, not in two repositories or two manifests. The one named after the
directory is `review`, and each other is `review:<name>`, such as `review:quick`.
`parallel_flame_chase` and `parallel_flame_chase:git_pr` are one release of
[humanfia/flow-parallel-flame-chase](https://github.com/humanfia/flow-parallel-flame-chase);
`agent_cleanup:ralph_loop` and `agent_cleanup:flame_chase` are one of
[humanfia/flow-agent-cleanup](https://github.com/humanfia/flow-agent-cleanup).

**Keep a flow's own code in its own directory.** Besides installed packages, a flow can import
only what sits beside its `__init__.py`, and that directory is all that is installed, so a
`_shared.py` at the top of the repository is not there to import:
`ModuleNotFoundError: No module named '_shared'`. Put the helpers in a package named after the
flow. Every flow a run loads shares one set of module names, so a generic name such as `utils`
clashes with the next flow that picks it.

```text
review/
├── __init__.py            from _review import prompts
├── _review/               this flow's helpers
│   ├── __init__.py
│   └── prompts.py
└── skills/                skills its agents are given
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

## Dependencies

A flow that calls another flow of the same flowverse names it in its manifest, with the
versions it works with:

```yaml
dependencies:
  humanize1: ">=0.1.0,<0.2.0"
```

A range is comparisons (`<`, `<=`, `>`, `>=`, `==`, `!=`) joined by `,`, all of which must hold;
a bare version means `==`. Installing the flow installs the newest release of each dependency
in range, a prerelease only where nothing else is, unless one already installed is in range.
humanize refuses, saying why, an install with a cycle in it, one whose ranges no release
satisfies, and one that would take another installed flow's dependency out of its range.
Uninstalling a flow that another installed flow needs is refused too. The flows built into
humanize are always there: never list them.

The flows installed from one flowverse sit side by side, so `load("humanize1:rlcr")` inside an
installed `recursive_lean_prover` finds the `humanize1` installed beside it.

## Managing flowverses

`/flow` is where flows are installed, as well as chosen. It opens on **Installed**; <kbd>←</kbd>
goes out to its first screen, with **Installed** and **Flowverses** as two cards:

<HmzCast name="flowverses" alt="/flow: from Installed out to its first screen, into Flowverses, then into official to read the flows its index lists" />

| Page | Shows | Buttons |
| --- | --- | --- |
| **Installed** | built-in flows, then every flow by where it came from, each with its release and `↑ 0.2.0` where a newer one is listed | Install more…, Update, Uninstall, Copy here, Search…, Save |
| **Flowverses** | a card per index: fetched, not fetched or edited; its URL; how many flows it lists, how many are installed, how many have updates | Add flowverse…, Fetch again, Remove, Search… |
| a flowverse | each flow it lists, with its newest release, `✔ 0.1.0 installed` or `✔ 0.1.0 ↑ 0.2.0`; manifests that did not read, under the list | Install 0.1.0 or Update to 0.2.0, Uninstall, Fetch again, Search… |
| a flow | its releases, newest first: prereleases marked, the installed one ticked, each with its ref, commit, licence and what it needs | Install 0.1.0 or Switch to 0.1.0, Uninstall, Search… |

Installing, updating, fetching and removing happen at once, and are said under the list and,
once the menu closes, in the transcript. **Remove** asks first, and takes away the flowverse's
index and every flow installed from it. `official` cannot be removed.

From a script, [`Hmz().verses`](/reference/sdk#flowverses) does the same with nothing open:

```python
from hmz.sdk import Hmz

verses = Hmz().verses
verses.add("you/my-flowverse", "yours")  # clone its index
verses.index("yours").flows()            # what it lists: ['review']
verses.install("yours/review", "0.1.0")  # a release, and what it needs
verses.updates()                         # installed flows with a newer release listed
verses.uninstall("yours/review")
verses.fetch("yours")                    # its index, again
verses.remove("yours")                   # its index, and every flow installed from it
```

A flow installed from a script can be run with `-f` at once.

**To change somebody else's flow**, walk to it on **Installed** and press **Copy here**, or call
`Hmz().flows.fork("yours/review")`. Either copies it into this project's `.hmz/flows/review`,
where your edits are yours to keep, and from then on `review` in that project means your copy.
An installed flow is replaced whole by the next update.

::: danger Installing a flow is trusting its repository with this machine
A flow is Python. Once it is installed, humanize imports it whenever it lists flows, and every
agent it drives runs with approvals bypassed. Review in the official flowverse lowers the risk;
it does not remove it. Adding a flowverse runs nothing: an index holds no code. Read
[Security](/user/security) first.
:::

## What a flow is called

| You type | Runs |
| --- | --- |
| `rlar` | the nearest flow called `rlar`: this project's or yours if you have one, else the one built in |
| `review` | the nearest flow called `review`: this project's, yours, or the one installed from `official` |
| `yours/review` | `review` installed from the flowverse you added as `yours`, and nothing else |
| `local/review` | `review` in this project's `.hmz/flows` |
| `user/review` | `review` in your `~/.hmz/flows`, for every project |
| `./review` | the flow at that path |
| `git+<url>[@<rev>][#<subdir>][:<name>]` | the flow in `<subdir>` of a repository (its root when left out), at `<rev>` if given, fetched for the run |

A bare name is looked for **nearest first**: this project's `.hmz/flows`, then
`~/.hmz/flows`, then the rest. So a flow of your own can stand in for one of humanize's by
taking its name: `.hmz/flows/chat/` is what `-f chat` runs in that project. A name nothing
installed answers to is refused, saying where it could be installed from. `yours/review` names
one place, so nothing can stand in for it.

## Calling it from another flow

A flow can [call another](/weaver/calling-flows) by the same names. A flow installed from a
flowverse calls the others installed from it by name, as `review` or `humanize1:gen-plan`: list
them under `dependencies` so that they are installed with it. Any release of any repository is
called by URL, whether or not anybody has installed it:

```python
from hmz.flows import load

review = load("git+https://github.com/you/flow-review@v0.1.0#review")
```

The `@v0.1.0` holds the caller to one version of the flow: a tag, a branch or a commit. This is
a reason to publish two small flows rather than one large one: another weaver can call a phase,
but can only run a pipeline whole.

## Variations

**Run without installing.** `-f 'git+https://github.com/you/flow-review@v0.1.0#review'`
fetches that release for the run and installs nothing. A ref with no `#` is the flow at the
repository's root.

**Pin a version.** An install is pinned already: it is the manifest's `commit`, whatever later
happens to the tag. Choose another release on the flow's page to switch to it.

**Check your own flowverse as the official one is checked.** Copy `schema/` and `.github/`
from [humanfia/flowverse](https://github.com/humanfia/flowverse) into it.

**Start from somebody else's.** **Copy here** brings their flow into your project. Change it,
then move the directory into a repository of its own to publish it.

## Pitfalls

- **Not installed.** A flow an index lists runs only once it is installed, and `hmz exec`
  installs nothing:

  ```text
  hmz exec: error: yours/review: not installed -- install it from /flow (flowverse yours)
  ```

  Install it from `/flow`, or in CI call `Hmz().verses.install("yours/review")` first.
- **Not fetched yet.** On a fresh machine no index has been fetched, so a name only an index
  could answer to is refused:

  ```text
  hmz exec: error: review: the official flowverse has not been fetched yet -- fetch it from /flow
  ```

  Open `hmz` once, or in CI call `Hmz().verses.fetch("official")` first.
- **A manifest that does not read is skipped.** A wrong key, a short commit, a name or version
  that is not its directory's, or a built-in flow's name: the flowverse's page names it under
  the list, with why, and lists the rest.
- **Do nothing at import time** beyond defining things: no network calls, no files written.
  humanize imports every flow it lists, in `/flow` and as `$` completes a name, so a flow that
  acts on import acts for somebody who was only looking.
- **Edits inside an installed flow go away** at the next update. Copy the flow here first.
- **A name that is not there** is refused before anything runs:
  `hmz exec: error: yours/nope: no flow is called 'yours/nope', and it is not a path`.

## Next steps

- [Flows](/flows/): every flow humanize offers, with the shape of each drawn
- [humanfia/flowverse's CONTRIBUTING.md](https://github.com/humanfia/flowverse/blob/main/CONTRIBUTING.md):
  listing a flow in the official flowverse
- [Testing a flow](/weaver/testing-flows)
- [A flow that calls a flow](/weaver/calling-flows)
- [Reference › Flows › Flowverses](/reference/flows#flowverses)
- [SDK reference › Flowverses](/reference/sdk#flowverses)
