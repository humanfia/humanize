# Skills

A **skill** is a folder of instructions a coding agent loads when a task calls for it, written
as a `SKILL.md`. An agent in a flow carries two sets: the ones you installed for its CLI, and
the ones the flow brings for its role. Use this page to find out what an agent will carry into
a run, to watch a flow's skill arrive and leave, and to change what a flow brings.

## Try it

See what a Claude Code agent will carry of yours and of this project:

```sh
ls ~/.claude/skills .claude/skills
```

Then run a flow that brings a skill, such as [`rlar`](/flows/rlar), and list `.claude/skills`
again while its reviewer works: `review-notes` is there, the flow's own, until the reviewer's
session ends.

## Before you start

- A coding agent CLI that loads skills. Every built-in CLI does but DeepSeek Harness (`dsh`).
- For the flow's skills: a flow whose roles bring some. [`rlar`](/flows/rlar)'s reviewer and
  both roles of [`aot`](/flows/aot) do; a flow's page says which.

## Yours and the flow's

Neither set is a setting of the agent, and humanize never changes what you installed.

| | Yours | The flow's |
| --- | --- | --- |
| **Where they live** | where that CLI keeps skills, for you and for this project | in the flow's own `skills/` directory, or a git repository it names |
| **Which agents carry them** | every agent of that CLI | the roles the flow gives them to |
| **Turned on and off** | the way that CLI turns one off | by the flow alone |

A flow's skill is how a flow teaches one role something the others need not know: `rlar`'s
reviewer carries `review-notes`, which says how to read a change and write the review the actor
is handed next. For as long as a session of that role is open, the skill is copied into your
workspace, where the CLI reads a project's own skills, and it goes again when the last such
session ends.

## Example: watch a flow's skill arrive and leave

A scratch project with one bug in it, and `rlar` with Claude Code in both roles:

```sh
mkdir -p /tmp/skills-demo && cd /tmp/skills-demo
printf 'def add(a, b):\n    return a - b\n' > calc.py
ls .claude/skills                                # ①

hmz exec -f rlar \
    -a actor=claude/claude-haiku-4-5-20251001:low \
    -a reviewer=claude/claude-haiku-4-5-20251001:low \
    -p budget.cost=0.3 "fix add() in calc.py" &         # ②

find .claude                                     # ③, once the reviewer has started
wait; ls .claude                                 # ④, once the run has ended
```

```text
ls: cannot access '.claude/skills': No such file or directory                      ①
.claude                                                                            ③
.claude/skills
.claude/skills/review-notes
.claude/skills/review-notes/SKILL.md
ls: cannot access '.claude': No such file or directory                             ④
```

The run itself, on stderr, shows the reviewer finding the skill and reading it:

```text
● reviewer is working
● I'll review the task and check what has been done.
● Read(/tmp/skills-demo/TASK.md)
● Bash(ls -la /tmp/skills-demo)
● Read(/tmp/skills-demo/calc.py)
● Bash(cd /tmp/skills-demo && git status 2>&1 || echo "Not a git repo")
● Bash(find /tmp/skills-demo/.claude -type f 2>/dev/null)
● Read(/tmp/skills-demo/.claude/skills/review-notes/SKILL.md)                      ⑤
…
✻ input 76 · output 1.8k · cache_read 191.6k · cache_write 9.6k · $0.04 · claude-haiku-4-5-20251001 · reviewer
```

### What each part means

1. **Before the run** the project has no skills of its own, so a Claude Code agent here would
   carry only yours, from `~/.claude/skills/`.
2. **`reviewer=claude/…`** puts Claude Code in the role that brings `review-notes`. With Codex
   there instead, the same skill would land in `.agents/skills/`: see the table under
   [The flow's skills](#the-flow-s-skills).
3. **While the run is on**, `.claude/skills/review-notes/SKILL.md` is in your workspace. Claude
   Code reads a project's skills from there, so the reviewer loads it with yours. The actor, a
   Claude Code agent in the same directory, can see it too while it is there; a flow gives a
   skill to a role, not a fence round it.
4. **Once the run has ended**, the copy is gone, and so is the `.claude` directory that was
   made to hold it. A directory that was already yours stays.
5. **The reviewer reads the skill** as part of its turn. What it says, `review-notes` in this
   case, is how the reviewer goes about its work: read the repository, not the summary.

## Check that it worked

- **Yours:** list the directories for that CLI in the table below. A skill is a subdirectory
  holding a `SKILL.md`.
- **The flow's:** list the copy's directory while a session of that role is open, as in the
  example. After the run, nothing of it is left behind.
- **In the transcript:** a CLI that uses a skill says so when the turn reaches for it, such as
  Claude Code's `Read(…/.claude/skills/review-notes/SKILL.md)` in the example.

## Your skills, CLI by CLI

A skill you installed loads for every agent of that CLI, in every flow. These are the places
each CLI reads:

| Backend | Yours | This project's |
| --- | --- | --- |
| `agy` | `~/.gemini/antigravity-cli/skills/` | `.agents/skills/` |
| `claude` | `~/.claude/skills/` | `.claude/skills/` |
| `codex` | `~/.codex/skills/`, `~/.agents/skills/` | `.agents/skills/`, `.codex/skills/` |
| `cursor-agent` | `~/.cursor/skills/`, `~/.config/cursor/skills/` | `.cursor/skills/` |
| `grok` | `~/.grok/skills/`, `~/.agents/skills/`, `~/.claude/skills/`, `~/.cursor/skills/` | `.grok/skills/`, `.agents/skills/`, `.claude/skills/`, `.cursor/skills/` |
| `kimi` | `~/.kimi-code/skills/`, `~/.agents/skills/` | `.kimi-code/skills/`, `.agents/skills/` |
| `mcode` | `~/.minimax/skills/`, `~/.agents/skills/`, `~/.claude/skills/`, `~/.codex/skills/` | `.minimax/skills/`, `.claude/skills/`, `.agents/skills/` |
| `mimo` | `~/.config/mimocode/skill(s)/`, `~/.agents/skills/`, `~/.claude/skills/`, `~/.codex/skills/` | `.mimocode/skill(s)/`, `.agents/skills/`, `.claude/skills/`, `.codex/skills/` |
| `opencode` | `~/.config/opencode/skill(s)/`, `~/.agents/skills/`, `~/.claude/skills/` | `.opencode/skill(s)/`, `.agents/skills/`, `.claude/skills/` |
| `pi` | `~/.pi/agent/skills/`, `~/.agents/skills/` | <Badge type="warning" text="only in a project you trusted in pi" /> |
| `qwen` | `~/.qwen/skills/`, `~/.agents/skills/` | `.qwen/skills/`, `.agents/skills/` |
| `dsh` | <Badge type="danger" text="none" /> | <Badge type="danger" text="none" /> |

Each directory holds one skill per subdirectory, as `<name>/SKILL.md`. A CLI's home moves with
its own variable, such as `CODEX_HOME`, `KIMI_CODE_HOME`, `GROK_HOME` or `MINIMAX_DATA_DIR`,
and opencode's and MiMo Code's move with `XDG_CONFIG_HOME`.

DeepSeek Harness loads no skills at all when humanize drives it. pi reads a project's own
skills only in a project you have trusted in pi, and humanize does not trust one for you.

## The flow's skills

A flow brings skills for some of its roles. For as long as a session of that role is open,
each of them is copied into your workspace, where that CLI reads a project's own skills:

| Backend | Copied into |
| --- | --- |
| `claude` | `.claude/skills/` |
| `cursor-agent` | `.cursor/skills/` |
| `agy`, `codex`, `grok`, `kimi`, `mcode`, `mimo`, `opencode`, `qwen` | `.agents/skills/` |
| `dsh`, `pi` | <Badge type="danger" text="none" /> they carry only what you installed |

When the last session using a skill ends, the copy goes, along with any directory that was made
to hold it. An agent whose turns run on [another machine](/user/remote-execution) gets them
there.

A flow may also name skills from a git repository. Those are cloned into `~/.humanize/skills/`
and fetched again each time a run needs them, so they keep up with the repository.

## Variations

### Change what a flow brings

Copy the flow into your project: in `/flow`, put the cursor on it and press **Copy here** under
the list. The copy lands in `.humanize/flows/`, skills and all, and is yours to edit: its
`skills/`, and which roles carry them, as [Writing a flow](/weaver/writing-a-flow) shows.

### Keep one of yours in place of the flow's

Nothing of yours is overwritten. If your project already has a skill of the same name where the
CLI reads them, that one is what the agent loads, and the flow's copy is not made. Put your own
`review-notes/SKILL.md` in `.claude/skills/` and `rlar`'s Claude Code reviewer reads yours.

## Pitfalls

- **A skill of yours shadows the flow's.** A skill of the same name already in the project
  wins, so a flow can run without the instructions it was written for. Rename yours, or
  remove it for the run.
- **An agent ignores your skill.** Check it is in a directory that CLI reads (the table above),
  as `<name>/SKILL.md`, and that the CLI's home variable points where you think.
- **`dsh` or `pi` in a role that brings skills.** Neither gets the flow's copy. The role runs
  without it; give it another CLI if the skill matters.
- **A skill from a git repository cannot be fetched.** The run is refused before it starts,
  naming the skill. Check the network, or the repository's address in the flow.

## Next steps

- [Permissions](/user/permissions): the other thing a role brings with it
- [Writing a flow](/weaver/writing-a-flow): giving a role a skill of your own
- [Flows › The skills a flow brings](/reference/flows#the-skills-a-flow-brings)
- [Agents › The skills an agent carries](/reference/agents#the-skills-an-agent-carries)
