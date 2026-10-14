<script setup>
import SkillTrip from '../.vitepress/theme/components/user-skills/SkillTrip.vue'
</script>

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

Then run a flow that brings a skill, such as [`rlar`](https://humanfia.ai/flows/rlar), and watch its reviewer
read `review-notes`, the flow's own, out of a skills directory beside yours. Neither directory
above changes.

## Before you start

- A coding agent CLI that loads skills. Every built-in CLI does but DeepSeek Harness (`dsh`).
- For the flow's skills: a flow whose roles bring some. [`rlar`](https://humanfia.ai/flows/rlar)'s reviewer and
  both roles of [`aot`](https://humanfia.ai/flows/aot) do; a flow's page says which.

## Yours and the flow's

Neither set is a setting of the agent, and humanize never changes what you installed.

| | Yours | The flow's |
| --- | --- | --- |
| **Where they live** | where that CLI keeps skills, for you and for this project | in the flow's own `skills/` directory, or a git repository it names |
| **Which agents carry them** | every agent of that CLI | the roles the flow gives them to |
| **Turned on and off** | the way that CLI turns one off | by the flow alone |

A flow's skill is how a flow teaches one role something the others need not know: `rlar`'s
reviewer carries `review-notes`, which says how to read a change and write the review the actor
is handed next. Most CLIs are started in a home of their own for each process: your skills are
linked into its `skills/`, and the flow's go beside them. opencode and MiMo Code are told where
the flow's skills are instead. Nothing is put in your workspace for any of these.

<SkillTrip />

## Example: watch a flow's skill arrive and leave

A scratch project with one bug in it, and `rlar` with Claude Code acting and Codex reviewing:

```sh
mkdir -p /tmp/skills-demo && cd /tmp/skills-demo
printf 'def add(a, b):\n    return a - b\n' > calc.py

hmz exec -f rlar \
    -a actor=claude/claude-haiku-4-5:low \
    -a reviewer=codex/gpt-6-luna:low \
    -p budget.cost=0.3 "fix add() in calc.py"          # ①

ls -A                                            # ②, once the run has ended
```

The run, on stderr, shows the reviewer reading the skill out of its own home:

```text
● Golem99 is working
● Bash(/bin/zsh -lc "cat /var/folders/…/hmz-home-…/hmz-home-…/skills/review-notes/SKILL.md")   ③
…
```

```text
calc.py                                                                            ②
```

### What each part means

1. **`reviewer=codex/…`** puts Codex in the role that brings `review-notes`. Codex is started in
   a home of its own, made for that one app server: a copy of your `config.toml`, links to the
   rest of `~/.codex`, and a `skills/` holding links to yours and `review-notes` beside them.
   Claude Code in that role gets the same, under `$CLAUDE_CONFIG_DIR`.
2. **Once the run has ended**, the project holds only what the agents wrote. No skill was
   copied into it, and the reviewer's home is gone with its server, together with whatever
   Codex wrote into its copy of `config.toml`, such as that it trusts this directory.
3. **The reviewer reads the skill** as part of its turn. What it says, `review-notes` in this
   case, is how the reviewer goes about its work: read the repository, not the summary. The
   actor, given no skills, has none of them in its home.

## Check that it worked

- **Yours:** list the directories for that CLI in the table below. A skill is a subdirectory
  holding a `SKILL.md`.
- **The flow's:** a CLI that uses a skill says so when the turn reaches for it, as the
  reviewer's `cat …/hmz-home-…/skills/review-notes/SKILL.md` in the example. After the run,
  nothing of it is left behind.

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
| `omp` | `~/.omp/agent/skills/`, `~/.agents/skills/` | `.omp/skills/`, `.agents/skills/` |
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

A flow brings skills for some of its roles. Every CLI but opencode, MiMo Code and dsh is started,
a process at a time, in a home of their own -- copies of the settings they rewrite as they run,
links to the rest of yours -- whose user-level `skills/` holds links to yours with the flow's
beside them. That home goes when the process stops; nothing of yours, and nothing of the
project's, is written. opencode and MiMo Code are told where the flow's skills are, in the
configuration humanize hands each run, and read them after their own. Nothing goes in your
workspace:

| Backend | Put into |
| --- | --- |
| `claude` | its own home's `skills/` (`$CLAUDE_CONFIG_DIR/skills/`) |
| `codex` | its own home's `skills/` (`$CODEX_HOME/skills/`) |
| `grok` | its own home's `skills/` (`$GROK_HOME/skills/`) |
| `qwen` | its own home's `skills/` (`$QWEN_HOME/skills/`) |
| `pi`, `omp` | its own home's `skills/` (`$PI_CODING_AGENT_DIR/skills/`) |
| `agy` | its own home's `skills/` (named with `--app_data_dir`) |
| `cursor-agent` | its own home's `skills/` (`$CURSOR_CONFIG_DIR/skills/`) |
| `kimi` | its own home's `skills/` (`$KIMI_CODE_HOME/skills/`) |
| `mcode` | its own home's `skills/` (`$MINIMAX_DATA_DIR/skills/`) |
| `opencode`, `mimo` | named under `skills.paths` in the configuration of each run |
| `dsh` | <Badge type="danger" text="none" /> it carries only what you installed |

An agent whose turns run on [another machine](/user/remote-execution) gets them in the home
built for it there.

A flow may also name skills from a git repository. Installing the flow fetches them into its
own `skills/`, so they travel with it like the rest of it and update when the flow does. A flow
you never installed, such as one in `.hmz/flows/`, fetches them into a cache in your temporary
directory each time a run needs them, so they keep up with the repository.

## Variations

### Change what a flow brings

Copy the flow into your project: in `/flow`, put the cursor on it and press **Copy here** under
the list. The copy lands in `.hmz/flows/`, skills and all, and is yours to edit: its
`skills/`, and which roles carry them, as [Writing a flow](/weaver/writing-a-flow) shows.

### Keep one of yours in place of the flow's

Nothing of yours is overwritten. The flow's skill takes the place of a skill of yours of the
same name at the user level, and yours stays where it is. A project skill of the same name is
read by the CLI as it reads any project skill. To use yours in place of the flow's, copy the flow
and edit its skill.

## Pitfalls

- **An agent ignores your skill.** Check it is in a directory that CLI reads (the table above),
  as `<name>/SKILL.md`, and that the CLI's home variable points where you think.
- **`dsh` in a role that brings skills.** It does not get the flow's copy. The role runs
  without it; give it another CLI if the skill matters.
- **A skill from a git repository cannot be fetched.** The run is refused before it starts,
  naming the skill. Check the network, or the repository's address in the flow.

## Next steps

- [Permissions](/user/permissions): the other thing a role brings with it
- [Writing a flow](/weaver/writing-a-flow): giving a role a skill of your own
- [Flows › The skills a flow brings](/reference/flows#the-skills-a-flow-brings)
- [Agents › The skills an agent carries](/reference/agents#the-skills-an-agent-carries)
