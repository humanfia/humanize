# Skills

An agent in a flow carries two sets of skills: the ones you installed for its CLI, and the ones
the flow brings. Neither is a setting of the agent, and humanize never changes what you
installed.

| | Yours | The flow's |
| --- | --- | --- |
| **Where they live** | where that CLI keeps skills, for you and for this project | in the flow's own `skills/` directory, or a git repository it names |
| **Which agents carry them** | every agent of that CLI | the roles the flow gives them to |
| **Turned on and off** | the way that CLI turns one off | by the flow alone |

## Try it

See what a Claude Code agent will carry of yours and of this project:

```sh
ls ~/.claude/skills .claude/skills
```

Now run a flow that brings a skill, such as [`rlar`](/flows/rlar) with Claude Code as its
reviewer, and list `.claude/skills` again while the reviewer works. `review-notes` is there, the
flow's own, until the reviewer's session ends.

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
| `mimo` | `~/.config/mimocode/skill(s)/`, `~/.agents/skills/`, `~/.claude/skills/`, `~/.codex/skills/` | `.mimocode/skill(s)/`, `.agents/skills/`, `.claude/skills/`, `.codex/skills/` |
| `opencode` | `~/.config/opencode/skill(s)/`, `~/.agents/skills/`, `~/.claude/skills/` | `.opencode/skill(s)/`, `.agents/skills/`, `.claude/skills/` |
| `pi` | `~/.pi/agent/skills/`, `~/.agents/skills/` | <Badge type="warning" text="only in a project you trusted in pi" /> |
| `qwen` | `~/.qwen/skills/`, `~/.agents/skills/` | `.qwen/skills/`, `.agents/skills/` |
| `zcode` | `~/.zcode/skills/`, `~/.agents/skills/` | `.zcode/skills/`, `.agents/skills/` |
| `dsh` | <Badge type="danger" text="none" /> | <Badge type="danger" text="none" /> |

Each directory holds one skill per subdirectory, as `<name>/SKILL.md`. A CLI's home moves with
its own variable, such as `CODEX_HOME`, `KIMI_CODE_HOME` or `GROK_HOME`, and opencode's and
MiMo Code's move with `XDG_CONFIG_HOME`.

DeepSeek Harness loads no skills at all when humanize drives it. pi reads a project's own
skills only in a project you have trusted in pi, and humanize does not trust one for you.

## The flow's skills

A flow brings skills for some of its roles. For as long as a session of that role is open,
each of them is copied into your workspace, where that CLI reads a project's own skills:

| Backend | Copied into |
| --- | --- |
| `claude` | `.claude/skills/` |
| `cursor-agent` | `.cursor/skills/` |
| `agy`, `codex`, `grok`, `kimi`, `mimo`, `opencode`, `qwen`, `zcode` | `.agents/skills/` |
| `dsh`, `pi` | <Badge type="danger" text="none" /> they carry only what you installed |

When the last session using a skill ends, the copy goes, along with any directory that was made
to hold it. Nothing of yours is overwritten: if your project already has a skill of that name,
that one is what the agent loads. An agent whose turns run on
[another machine](/user/remote-execution) gets them there.

A flow may also name skills from a git repository. Those are cloned into `~/.humanize/skills/`
and fetched again each time a run needs them, so they keep up with the repository.

## Changing what a flow brings

Copy the flow into your project: press <kbd>f</kbd> on it in `/flow`. The copy lands in
`.humanize/flows/`, skills and all, and is yours to edit: its `skills/`, and which roles carry
them, as [Writing a flow](/weaver/writing-a-flow) shows.

## See also

- [Permissions](/user/permissions): the other thing a role brings with it
- [Flows › The skills a flow brings](/reference/flows#the-skills-a-flow-brings)
- [Agents › The skills an agent carries](/reference/agents#the-skills-an-agent-carries)
