# Build a coding agent

In this tutorial you take one loose sentence, "a small terminal coding agent for
`deepseek-v4-flash`", through the three phases of [`humanize1`](https://humanfia.ai/flows/humanize1). Each phase
is a flow of its own, and each hands the next a file you can read and edit.

::: info At a glance
- **You will learn** how to run a job in phases, reading and editing what each phase hands the
  next; how a flow's params change what it does; and how a builder is kept to a plan under
  review.
- **You will end with** a draft, a plan and a working coding agent, as in the table below.
- **Time:** an afternoon.
- **You need** humanize and one signed-in coding agent CLI. Phase 3's builder must be Claude
  Code, Codex, Grok Build or Kimi Code; every other role runs on any backend, DeepSeek Harness
  included.
:::

| Phase | You end with |
| --- | --- |
| 1&nbsp;·&nbsp;idea | a draft: the idea opened into several directions, each checked against the repository |
| 2&nbsp;·&nbsp;plan | `docs/plan.md`: a plan two agents argued over, with acceptance criteria |
| 3&nbsp;·&nbsp;build | a working coding agent, built round by round under review, with its tests |

## Before you start

- **Install humanize and sign in to a coding agent CLI.** See
  [Installation](/user/installation).
- **Make one run first.** [Your first run](/user/first-run), or the
  [quickstart on the home page](/#run-a-flow), shows a flow working in a scratch repository.
- **Install `humanize1`.** It is not built in: it comes from the official
  [flowverse](/weaver/flowverses). Open `hmz`, type `/flow`, press **Install more…**, open
  `official` and install `humanize1`. `hmz exec` installs nothing. Leave with `/exit`.

Using DeepSeek Harness? Add humanize's `[dsh]` extra, with the line for the way you installed
humanize, and export your key before step 2:

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

## Step 1: Make a repository

```sh
mkdir -p ~/tmp/flashagent && cd ~/tmp/flashagent
git init -q
echo "# flash-agent" > README.md
printf '.hmz/\ndocs/plan.md\n' > .gitignore
git add -A && git commit -qm "init"
```

**What just happened.**

1. **A git repository.** Phase 3 reads every review against the commit the plan was fixed in,
   so it has to be one.
2. **The `.gitignore`.** It keeps the flows' own files (`.hmz/`) and the plan
   (`docs/plan.md`) out of the commits, which phase 3 insists on.

::: tip Checkpoint
`git log --oneline` shows one commit, `init`.
:::

## Step 2: Open the idea

Keep the sentence in a shell variable, since phase 2 is given it too:

```sh
IDEA="A small terminal coding agent for deepseek-v4-flash. One Python
package, one entry point, no framework. It talks to the DeepSeek API
with the OpenAI-compatible chat completions endpoint, holds a message
list, and offers the model three tools: read a file, write a file, run
a shell command. It loops until the model answers without asking for a
tool. It is meant for a fast, cheap model, so it must keep the context
small and the tool schemas short."
```

Then run phase 1:

::: code-group

```sh [DeepSeek Harness]
export DEEPSEEK_API_KEY=sk-…
hmz exec -f humanize1:gen-idea \
    -a drafter=dsh/deepseek-v4-pro:high \
    -p budget.cost=5 "$IDEA"
```

```sh [Claude Code]
hmz exec -f humanize1:gen-idea \
    -a drafter=claude/claude-opus-5-5:high \
    -p budget.cost=5 "$IDEA"
```

```sh [Codex]
hmz exec -f humanize1:gen-idea \
    -a drafter=codex/gpt-5.6-sol:high \
    -p budget.cost=5 "$IDEA"
```

:::

When it ends, read what it wrote:

```sh
ls .hmz/ideas/
head -20 .hmz/ideas/*.md
```

```console
a-small-terminal-coding-agent-for-20260817-020714.md
# Stdlib OpenAI-Compatible DeepSeek Chat Client

## Original Idea

A small terminal coding agent for deepseek-v4-flash. …

## Primary Direction: Stdlib HTTP client

### Objective Evidence

- Import checks confirm `openai`, `httpx`, and `requests` are all MISSING in this
  environment, while `urllib.request` is present in Python 3.12.13 stdlib — stdlib is
  both necessary and sufficient for a zero-dependency client.
…
```

**What just happened.**

1. **`-f humanize1:gen-idea`** names one flow of the `humanize1` module: `<flow>:<name>`.
2. **`-a drafter=…`** gives its one role, the **drafter**, an agent.
3. **`-p budget.cost=5`** caps it at five dollars.
4. **The draft** is in `.hmz/ideas/`. The drafter picked six different directions the idea
   could go, explored each against this repository and this machine, and wrote up one as the
   primary with the others as alternatives.
5. **"Objective Evidence"**: every direction has to be justified by something the agent checked
   here, not by what usually makes a good design.

::: tip Checkpoint: read the draft
It is a file, and editing it is expected. If it picked the wrong primary direction, promote one
of the alternatives yourself. That is far cheaper here than after the plan is written.
:::

## Step 3: Argue it into a plan

In the same terminal as step 2, so `$IDEA` and your key are still set:

::: code-group

```sh [DeepSeek Harness]
hmz exec -f humanize1:gen-plan \
    -a planner=dsh/deepseek-v4-pro:high \
    -a analyst=dsh/deepseek-v4-pro:high \
    -p budget.cost=10 "$IDEA"
```

```sh [Claude Code + Codex]
hmz exec -f humanize1:gen-plan \
    -a planner=claude/claude-opus-5-5:high \
    -a analyst=codex/gpt-5.6-sol:high \
    -p budget.cost=10 "$IDEA"
```

```sh [Claude Code only]
hmz exec -f humanize1:gen-plan \
    -a planner=claude/claude-opus-5-5:high \
    -a analyst=claude/claude-opus-5-5:high \
    -p budget.cost=10 "$IDEA"
```

:::

This phase takes a while, and what it writes is long:

```sh
wc -l docs/plan.md
```

```console
478 docs/plan.md
```

It is not prose. It is an issue map, numbered acceptance criteria, and decisions with their
alternatives recorded:

```console
| ID | Finding | Dimension | Severity | Resolution in this plan |
|----|---------|-----------|----------|-------------------------|
| I-2 | Draft assumes OpenAI-identical `tool_calls`; DeepSeek adds `reasoning_content`,
  non-OpenAI `finish_reason` values, and documents `function.arguments` as "not always
  valid JSON". | Functionality | High | Full `finish_reason` set, `reasoning_content`/
  `usage` surfaced, tolerant multi-tool parsing (AC-2/AC-6/AC-10). |
| I-10 | `thinking` defaults to `enabled`; hidden reasoning tokens undermine the "fast,
  cheap, small context" premise. | Functionality | High | Explicit `thinking` toggle,
  candidate default `disabled` … |
```

**What just happened.**

1. **It planned from the newest draft** in `.hmz/ideas/`, the one you may have edited.
2. **Two agents this time.** The **planner** writes the plan and keeps one conversation
   throughout, so it remembers how the plan got where it is. The **analyst** comes fresh to
   each reading and says what is wrong. They go up to three rounds, until the analyst has
   nothing required left.
3. **The findings** did not come from your sentence. They came from an analyst reading the
   draft and checking what the DeepSeek API actually returns.

::: tip Checkpoint: read `docs/plan.md` now
This is the last cheap moment. From here the plan is the contract: phase 3 builds against it
and does not let the builder edit it.
:::

## Step 4: Build it under review

::: code-group

```sh [Claude Code + Codex]
hmz exec -f humanize1:rlcr \
    -a builder=claude/claude-opus-5-5:high \
    -a reviewer=codex/gpt-5.6-sol:high \
    -p budget.duration=12h,budget.cost=100 \
    "build it"
```

```sh [Claude Code only]
hmz exec -f humanize1:rlcr \
    -a builder=claude/claude-opus-5-5:high \
    -a reviewer=claude/claude-opus-5-5:high \
    -p budget.duration=12h,budget.cost=100 \
    "build it"
```

```sh [Codex only]
hmz exec -f humanize1:rlcr \
    -a builder=codex/gpt-5.6-sol:high \
    -a reviewer=codex/gpt-5.6-sol:high \
    -p budget.duration=12h,budget.cost=100 \
    "build it"
```

:::

**What just happened.**

1. **The plan is the task here.** `"build it"` is only the name the run goes by.
2. **The builder** works until it believes the plan is done and tries to stop. Instead of
   stopping, it hears the **reviewer**'s reading of the round against the plan.
3. **Every fifth round** the reviewer is asked a different question: does what has been built
   still match the plan at all?
4. **Once the reviewer calls the plan complete**, it reviews the code itself, and the builder
   fixes whatever it marks `[P0]` to `[P9]`. The loop ends when a code review finds nothing, or
   after 42 rounds (`-p max=` changes that).
5. **The flow guards the builder** while it works, keeping the plan fixed and the loop's own
   files out of its hands. That is why the builder must be Claude Code, Codex, Grok Build or
   Kimi Code.
6. **The third role, `human`, is you.** It is never given with `-a`. Under `hmz exec` nobody is
   at a prompt, so the flow asks you nothing and carries on.

::: tip Checkpoint
The loop keeps a summary per round. Watch them appear from another terminal:

```sh
ls -1 .hmz/rlcr/*/
```

```console
goal-tracker.md
plan.md
round-0-contract.md
round-0-prompt.md
round-0-summary.md
state.md
```

Check the work against the plan's acceptance criteria, since those are what the reviewer checks
it against.
:::

## Step 5: See what it built

Every round commits, so you can read the work a round at a time. In the run this page was
written from, which was still going at this point:

```sh
git log --oneline
```

```console
f835006 Round 1: close reviewer P1 contract gaps across the agent
e21d3a7 Implement end-to-end flash_agent DeepSeek coding agent (Round 0)
f0e8d2d init
```

Round 0 built the whole thing, and round 1 closed what the reviewer marked `P1`.

```sh
python -m pytest -q
```

```console
........................................................................ [100%]
72 passed in 0.35s
```

By the end of round 1 that was 118 tests, which is what a reviewer that will not say "done"
does to a suite. Your names and numbers will differ.

Now use what it built:

```sh
mkdir -p /tmp/flashtry && printf 'def add(a, b):\n    return a - b\n' > /tmp/flashtry/calc.py
python -m flash_agent --workdir /tmp/flashtry --allow-shell \
    "Read calc.py, fix the bug in it, and say what you changed."
cat /tmp/flashtry/calc.py
```

```console
Fixed. **What changed:** In `add()`, changed `return a - b` to
`return a + b`. The function was subtracting instead of adding.
def add(a, b):
    return a + b
```

**What just happened.** A coding agent, built from one sentence, has just fixed a bug. Look at
`--allow-shell`: you never asked for it. It started as the draft's fifth direction, "guarded
shell execution", became a decision in the plan, and ended as a gate the builder implemented.
That is the two planning phases earning their time.

::: tip Checkpoint
`calc.py` in `/tmp/flashtry` now returns `a + b`.
:::

## Troubleshooting

### It says `humanize1` is not installed

```console
hmz exec: error: humanize1:gen-idea: not installed -- install it from /flow (flowverse official)
```

Install it from `/flow`, as in [Before you start](#before-you-start). If the message says the
official flowverse has not been fetched yet instead, open `hmz` and wait a moment: it fetches
the flowverses in the background each time it opens.

### `'builder' needs PermissionRequestHookAgentMixin`

```console
hmz exec: error: humanize1:rlcr: 'builder' needs PermissionRequestHookAgentMixin, which dsh does not support
```

The builder is on a backend the flow cannot guard. Give `builder` Claude Code, Codex, Grok
Build or Kimi Code. The reviewer may stay where it is.

### It stopped on "`PENDING` still stands on DEC-…"

The plan is written, but it has decisions only you can make, and nobody was at a prompt to ask.
Open `docs/plan.md`, answer each `Decision Status` under `## Pending User Decisions`, and go on
to step 4.

### It stopped on "output file already exists"

`gen-plan` never overwrites a plan. To plan again, delete `docs/plan.md` first.

## What you learned

- A big job can run as phases, each a flow of its own, each leaving a file you read and edit
  before the next one starts.
- `-f module:flow` names one flow of several in a module, and `-p` sets a flow's params.
- A planner that keeps its conversation and an analyst that starts fresh argue a plan into
  shape before any code is written.
- A builder held to a plan under review, with the plan out of its reach, builds what was
  planned.

## Next steps

- **Run the phases on different models.** Plan on the strongest model you have, build on a
  cheaper one, review on a third.
- **Explore more or fewer directions.** `-p n=3` or `-p n=10` on phase 1. `n` is 6 unless
  given, and goes from 2 to 10.
- **Stop between phases and edit the file.** The draft and the plan are both meant to be read,
  and a text editor is the refinement step.
- **Build from a plan you wrote.** Phase 3 needs a plan, not the first two phases:
  `-p plan_file=…` names it. The [`humanize1`](https://humanfia.ai/flows/humanize1) page has more of the
  phases' params.
- **Read it back.** `/epics` in `hmz` lists the three runs, one per phase. **Export run** on
  any of them gives you its trace. See [Tracing](/user/tracing).
- **Write a flow of your own.** You have now run three that somebody else wrote. Whoever writes
  one is a **weaver**, and the [Weaver Guide](/weaver/) starts with [Build under
  test](/weaver/tutorials/build-under-test).
