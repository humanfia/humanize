# Agents

<script setup>
import AgentMatrix from '../.vitepress/theme/components/ref-agents/AgentMatrix.vue'
</script>

::: info The agent layer, underneath flows
This page documents `hmz.coganchor.agents`: the Python classes that drive each coding-agent
CLI. **Writing a flow? Read [Flows](/reference/flows) instead.** A flow never imports this
module; the `Agent` and `Session` it is handed are views the runtime makes of the agents
described here. Come here to drive agents from a script or a test, or to see what a flow's
agent does underneath.
:::

An agent is settings: a backend, a model, an effort. A [session](/user/concepts) is one
conversation with it. Call the agent for a turn nothing remembers, or a session for a turn in
that conversation:

```python
from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"))

agent("Summarise README.md.")              # one turn, in a session nobody keeps
session = agent.new()
session("Read TASK.md and get started.")   # opens the conversation
session("continue")                        # resumes it, the task still in context
```

## What each backend can do

<AgentMatrix />

A dash is a backend that cannot; under Moments it means the base six only. Each column head
links to where the feature is described.

::: details What each column means
| Column | What it answers |
| --- | --- |
| **Steers** | Whether [`session.interject()`](#talking-to-a-turn-already-running) reaches a turn already running. |
| **Goal** | Whether [`pursue()`](#goals) runs the backend's own goal feature. |
| **Schema** | `held`: the CLI itself is held to the [pydantic schema](#answering-in-a-shape). `prompt`: the schema is asked for in the prompt and the answer validated after. |
| **Fork** | Whether [`session.fork()`](#a-conversation-that-goes-two-ways) branches the conversation. An ACP CLI's `yes` is marked because it forks only where the agent serves `session/fork`. |
| **Web search** | Whether [`web_search=False`](#whether-an-agent-may-search-the-web) can be said. Where it cannot, it is refused. |
| **Rungs** | Which of the four [permission rungs](#what-an-agent-may-do) the backend takes: all four, or only `bypass`. |
| **Moments** | The [hook moments](#not-every-backend-runs-every-moment) beyond the six every backend runs. `Permission` is `PermissionRequest`; `Subagent` is `SubagentStart` and `SubagentStop`. |
| **Fast tier** | Whether [`service_tier="fast"`](#the-service-tier) is served. |
| **Trace** | Whether `Hmz().epics.trace()` has a reader for the backend's logs. |
:::

`HumanAgent`, [the person as an agent](#the-person-as-an-agent), runs no moment and does none
of these. How each backend does what it does is in [Backend notes](#backend-notes).

## Making one

Each backend has an agent class, a config class and a session class. A backend is named by the
command it is installed as, which is also what `-a` takes.

| Backend | Agent | Config | Session |
| --- | --- | --- | --- |
| `agy` | `AntigravityCLIAgent` | `AntigravityCLIAgentConfig` | `AntigravityCLISession` |
| `claude` | `ClaudeCodeAgent` | `ClaudeCodeAgentConfig` | `ClaudeCodeSession` |
| `codex` | `CodexAgent` | `CodexAgentConfig` | `CodexSession` |
| `cursor-agent` | `CursorAgent` | `CursorAgentConfig` | `CursorSession` |
| `dsh` | `DshAgent` | `DshAgentConfig` | `DshSession` |
| `grok` | `GrokBuildAgent` | `GrokBuildAgentConfig` | `GrokBuildSession` |
| `kimi` | `KimiCodeCLIAgent` | `KimiCodeCLIAgentConfig` | `KimiCodeCLISession` |
| `mimo` | `MimoCodeAgent` | `MimoCodeAgentConfig` | `MimoCodeSession` |
| `opencode` | `OpencodeAgent` | `OpencodeAgentConfig` | `OpencodeSession` |
| `pi` | `PiAgent` | `PiAgentConfig` | `PiSession` |
| `qwen` | `QwenCodeAgent` | `QwenCodeAgentConfig` | `QwenCodeSession` |
| `zcode` | `ZcodeAgent` | `ZcodeAgentConfig` | `ZcodeSession` |
| an [ACP CLI](#a-cli-of-your-own) | `AcpAgent` | `AcpAgentConfig` | `AcpSession` |
| you | `HumanAgent` | none: it takes only `name=` | `HumanSession` |

`hmz.coganchor.agents.DRIVEN` maps each built-in backend name to its agent and config class.

Every config takes these fields. Each backend's config adds fields of its own, listed under
[Backend notes](#backend-notes).

| Field | Default | What it is |
| --- | --- | --- |
| `model` | required | The model, in the backend's own spelling. See [How a model is named](#how-a-model-is-named). |
| `effort` | required | A rung of the backend's [effort ladder](#efforts), or `""` (or `"auto"`) for none. |
| `service_tier` | `"default"` | `"fast"` where the backend serves it. See [The service tier](#the-service-tier). |
| `machine` | `None` | Where the turns land. See [Where the turns land](#where-the-turns-land). |
| `permission` | `""` | A [permission rung](#what-an-agent-may-do), or `""` to say nothing about it. |
| `provider` | `""` | The [account](#which-account-it-runs-as) to run as, or `""` for the CLI as you already run it. |
| `goals` | `True` | Whether [goals](#goals) are available to the agent. |
| `web_search` | `None` | `True`, `False`, or `None` to say nothing. See [Whether an agent may search the web](#whether-an-agent-may-search-the-web). |
| `budget` | `None` | What each turn may spend. See [Cutting a turn off](#cutting-a-turn-off-and-what-one-turn-may-spend). |

```python
actor = ClaudeCodeAgent(config, name="actor")   # name= is optional on every agent
```

A config is frozen: a session resumes under the settings it opened with. The agent refuses a
config its backend cannot carry, with `hmz.coganchor.agents.Unserved` (a `ValueError`):

- an effort that is not on the backend's ladder (an ACP CLI checks none);
- a rung the backend does not take;
- a service tier it cannot send;
- `web_search=False` on a backend that cannot be told;
- a combination one backend cannot carry: Antigravity's `disable_slash_commands=True` at
  `read-only`, a Cursor model the account lists at no such rung or tier, or opencode's and
  mimocode's `permission_table=False` beside a rung that withholds anything or
  `web_search=False`.

The refusal comes where the agent is made, and again wherever a config or an effort is changed
on an agent already running.

### How a model is named

`model` goes to the CLI in that CLI's own spelling.

| Backend | A model is | For example |
| --- | --- | --- |
| `agy`, `claude`, `codex`, `dsh`, `grok`, `qwen` | the id the CLI, or the endpoint behind it, serves | `claude-opus-5`, `gpt-5.6-sol`, `deepseek-v4-flash` |
| `kimi` | Kimi Code's own `provider/id` | `kimi-code/k3` |
| `pi`, `opencode`, `mimo` | `provider/id` | `openai-codex/gpt-5.5`, `opencode/big-pickle`, `xiaomi/mimo-v2.5` |
| `zcode` | `provider/id`, and `gw/<id>` on a gateway account | `zai/glm-5.3`, `gw/vendor/some-model` |
| `cursor-agent` | an id out of `cursor-agent models`, with the effort and tier written into it | `composer-2.5-high-fast` |
| an ACP CLI | `as configured` | |

On `pi`, name the provider: its `--provider` defaults to `google`, so a bare id is looked for
among Gemini models. `grok models` lists Grok Build's catalogue.

**An account that names an endpoint is asked what that endpoint serves.** Eight backends route
their turns by one base-URL variable. Where an account sets it, `GET {base}/v1/models` (or
`{base}/models` when the base already ends in a version) is the list a turn picks from:

| Backend | Variable |
| --- | --- |
| `agy` | `GOOGLE_GEMINI_BASE_URL` |
| `claude` | `ANTHROPIC_BASE_URL` |
| `codex` | `CODEX_PROVIDER_URL` |
| `dsh` | `DEEPSEEK_BASE_URL` |
| `grok` | `GROK_XAI_API_BASE_URL` |
| `kimi` | `KIMI_MODEL_BASE_URL` |
| `qwen` | `OPENAI_BASE_URL` |
| `zcode` | `ZCODE_BASE_URL`, each id listed as `gw/<id>` |

`pi`, `opencode` and `mimo` are not asked this way: an endpoint's ids carry no provider, and
these CLIs name a model by one. `cursor-agent` is not either: `cursor-agent models` is already
the account's answer. See [Backends](/features/backends) for how the catalogue is kept.

## Turns

```python
agent("Read TASK.md and get started.")    # a turn in a session of its own: nothing carries over
session = agent.new()
session("Read TASK.md and get started.")  # opens the session
session("continue")                       # resumes it
```

Both return what the agent answered, stripped.

A turn that fails raises `hmz.coganchor.agents.Failed`, a `subprocess.CalledProcessError`, and
leaves the session unopened, so the next call retries the turn rather than resuming something
that may not exist. Its message ends with what the CLI said and, where the failure was
recognised, its kind and what to do about it:

```console
Command '['claude', …]' returned non-zero exit status 1. 429 rate limit exceeded (throttled: this account has spent its quota; another one, or a wait, is what answers it)
```

`Failed.fault` is that kind: `contended`, `throttled`, `refused`, `unlisted`, `retired`,
`missing`, `sandboxed`, `killed` or `dropped`, or `""` for a failure nobody classified.
`Failed.fix` is the advice. [Falling back](/user/fallback) has what each kind is answered with.

`suppress=True` turns a failed turn into `""`, or `None` with a
[schema](#answering-in-a-shape):

```python
agent(task, suppress=True)   # "" if it failed, and the loop goes round again
```

It catches a failed turn and, with a schema, an answer that is not the shape, and nothing else.
These go through it:

| Raised | When |
| --- | --- |
| `Unrecoverable` | A `Failed` no other try could change: a conversation longer than the context window, a session id the backend will not answer under, a budget spent with `then="fail"`. Never retried and never carried to another account. |
| `Stopped` | The agent was [stopped](#stopping). Not a `CalledProcessError`. |
| `NotImplementedError` | The backend has no such feature, such as `pursue` without a [goal](#goals). |

## Sessions

```python
session = agent.new()        # nothing has been opened with the backend yet
session("first turn")        # now it has
session.id                   # the backend's id for it, e.g. "0a1b2c3d-…"
session.named                # the same id, or None before the backend has said one
session.close()              # ends whatever it was holding
```

- `id` raises `RuntimeError` before a turn has landed. `named` answers `None` instead. On
  `claude`, `codex`, `dsh`, `kimi`, `pi` and `zcode` it is set as soon as the backend names the
  session, during the first turn; on the rest it is set when that turn lands, as `id` is.
- A session runs one turn at a time. Two threads calling one session hold one conversation.
- The agent holds its sessions weakly, so a Ralph loop running for days does not grow.
  Discarding a session is how a flow forgets.

### A conversation that goes two ways

`fork` branches a conversation: a second one carrying this one's history, its own from there
on.

```python
session("read src/ and tell me what this service does")
careful, quick = session.fork(), session.fork()   # both know what that turn found out

session.forks           # whether this backend has a fork of its own
agent.new().fork()      # RuntimeError: nothing has landed, so there is nothing to carry
```

- The CLI's own fork carries the history, so nothing is replayed.
- The child is unopened until its first turn, which is the turn that forks. It has its own
  `id`, `spent()` and place in `agent.opened`, and the run records which conversation it came
  from.
- Use the child before the parent's next turn. A child driven after the parent has moved on
  raises `RuntimeError`; fork again for the newer point.
- The child carries the session's effort, budget, skills and callbacks. What the *agent* was
  set up with was never the session's.
- On a backend with no fork, `fork` raises `NotImplementedError`.

The child may belong to **another agent** of the same backend, account and machine (set up
differently, at another rung or carrying other skills), and may work in **another directory**:

```python
reviewing = session.fork(into=reader, cwd="/work/review-tree")
```

`into=` of another backend, account or machine is a `ValueError`. `cwd=` elsewhere works on
Claude Code (its transcript is copied to where `--resume` looks), Codex, Kimi Code and ZCode,
and is `NotImplementedError` on the rest. A flow reaches this as `agent.fork(session, env=…)`.

`fork` is not [`agent.clone`](#an-agent-that-is-not-quite-the-one-you-were-handed): a clone
copies an agent's settings and no history; a fork copies a session's history. See [Branching a
conversation](/weaver/branching).

### The directory a session works in

A session is opened at a directory, and every turn of it runs there. Leave it out and the
session works in the directory the flow runs in.

```python
session = agent.new(worktree)
session.cwd                                  # where that is, as an absolute path

agent("fix the tests", cwd=worktree)         # one turn in a session of its own, there
agent.pursue(objective, cwd=worktree)
await agent.aturn(task, cwd=worktree)        # and await agent.apursue(objective, cwd=…)
agent.batch(prompts, cwd=worktree)           # every turn of the batch, there
agent.batch_new(200, worktree)               # two hundred conversations, all there
```

One agent working in several places at once is a session per directory, their turns gathered:

```python
held = [agent.new(worktree) for worktree in worktrees]
said = await asyncio.gather(*(one.aturn(task) for one in held))
```

For an agent whose turns land on [another machine](/reference/machines), the directory is
**that machine's** path, and must be inside the workspace the anchor names. Before the turn
runs, a local directory that is not there raises `ValueError`, and so does an anchored one
outside that workspace:

```text
/srv/nowhere: no directory to open a session in
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

## Awaiting a turn

Every call that runs a turn has an awaited twin, for a flow written as `async def run`:

```python
await agent.aturn(task)                  # agent(task)
await session.aturn("continue")          # session("continue")
await agent.apursue(objective)           # agent.pursue(objective)
await agent.abatch(prompts)              # agent.batch(prompts)
```

Same arguments and answers. The turn runs on a thread of its own and the event loop is free
meanwhile. A session is still a sequence: two turns awaited on one session run one after the
other, and two on two sessions run at once.

```python
acted, reviewed = await asyncio.gather(actor.aturn(task), reviewer.aturn(REVIEW + task))
```

## Many at once

`batch` calls the agent once per prompt, all at the same time, one session apiece and none
kept. Answers come back in the order asked:

```python
answers = agent.batch([f"Review {path}" for path in paths])
reviews = agent.batch(prompts, schema=Review, suppress=True)
agent.batch(prompts, at_once=32)          # thirty-two running; the rest queue behind them
```

`at_once=0`, the default, runs every prompt at once. Without `suppress`, a batch raises the
first failure once every turn of it has landed; with it, a failed prompt answers `""` (or
`None`) and the rest go through. An agent [stopped](#stopping) mid-batch raises `Stopped`.

`batch_new` opens sessions without running a turn. A session costs nothing until a turn lands
in it:

```python
sessions = agent.batch_new(10_000)
await asyncio.gather(*(one.aturn(f"shard {at}") for at, one in enumerate(sessions)))
```

## Answering in a shape

A turn given a `schema` answers with that pydantic model rather than text:

```python
from pydantic import BaseModel, Field

class Review(BaseModel):
    """What a review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, word for word.")

review = agent(asked, schema=Review)   # a Review, not a str
```

The model is the question: its fields, types, required keys and descriptions are what the
backend is given.

- Where the backend can be held to it (`SessionBase.shapes`), it is: `--json-schema` on `agy`,
  `claude`, `grok` and `qwen`, and the turn's `outputSchema` on `codex`.
- Elsewhere the schema is asked for in the prompt and the answer is validated after.
- An answer that is not the shape raises `ValueError`. `suppress=True` answers `None` for that
  and for a failed turn.
- The person is asked [a question per
  field](#asking-them-for-a-shape-which-is-a-questionnaire).

## Watching a turn as it happens

`stream` is the primitive; calling a session wraps it.

```python
for event in session.stream("write the tests"):
    print(event.kind, event.text)
```

An `Event` has `kind`, `text`, `whose`, and on a `result`, `tokens` (tokens per model) and
`spent` (a [`Usage`](#what-it-has-cost-and-how-fast)).

| `kind` | |
| --- | --- |
| `text` | The agent talking. One whole utterance, never a streamed fragment. |
| `reasoning` | The agent thinking aloud, where the backend says it. opencode and mimocode say it only with `thinking=True`. |
| `tool` | The agent reaching for a tool. Where the backend streams a call's arguments, it is sent at the first fragment that names the path or command, not once the whole file has been written. |
| `subagent`, `subagent-ends` | Bracket an agent this one started of its own; `whose` pairs them. |
| `took` | A word [put into the running turn](#talking-to-a-turn-already-running) is now in front of the model; the event carries the word. |
| `result` | The answer the turn ends on. **Exactly one closes a turn**, and it is what calling the session returns. |
| `failed` | The turn closed the other way, carrying what went wrong. |

A watcher sees the same, plus four kinds a stream does not carry:

| `kind` | |
| --- | --- |
| `begins`, `ends` | Bracket a turn. |
| `asks` | The agent stopped to [ask its user something](#questions). |
| `notice` | **humanize**, not the agent: a rate limit waited out, another account taken, a turn cut off, a wedged backend taken away. The interface shows it whatever `/details` says; with no watcher it goes to stderr. |

```python
def looking(agent, session, event):
    if event.kind in ("begins", "ends"):
        print(f"--- {agent.id} {session and session.named} {event.kind}")

agent.watch(looking)
```

The `session` is which conversation said it. It is `None` only for something the agent said
outside any one of them, such as a question put by a server serving every session at once.

A watcher that raises does not fail the flow; it is reported as a snag. The interface's status
column is built from these events.

### A turn narrated as it is written

Claude Code is the one backend that can say a tool call while the model is still writing it
(`session.narrates`). It is asked for `--include-partial-messages`. Without it, a large `Write`
is silent from the moment the model reaches for it until the whole file is written. Turn it off
with:

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", partial_messages=False)
```

Every backend says every reach exactly once either way. Off, Claude says each one whole, when
the call is complete. A flow asks for this as `narrate`.

## Talking to a turn already running

```python
session.steers                          # whether this backend can be talked to mid-turn
session.interject("actually, use pathlib")
```

The agent reads the word when it next looks, so the turn under way takes it into account. It
comes back as a `took` event once it is in front of the model.

- On a backend that cannot be talked to, `interject` raises `NotImplementedError`. Check
  `session.steers` first.
- On Codex and Kimi Code it raises `RuntimeError` when no turn is running.
- Claude Code and pi take a word whenever the session's process is up, during a turn or between
  turns, and raise `RuntimeError` before the first turn has started one. An
  [anchored](#where-the-turns-land) session's process ends with each turn, so there it hears
  you only during one.

How each backend takes the word is in [How each backend is
driven](#how-each-backend-is-driven).

## Goals

A session can be given a goal instead of a prompt. This is the backend's *own* goal feature
(the one its `/goal` command reaches), not a prompt asking for one:

```python
agent.pursue("the suite passes and nothing has been stubbed out")
```

The agent decides when the objective is met. Until then, a turn that would have ended starts
another; `pursue` follows the goal across all of them and answers with the last.

- Which backends have one is `type(agent).pursues`: Claude Code, Codex, DeepSeek Harness, Kimi
  Code and ZCode. The rest raise `NotImplementedError`, even under `suppress`.
- A flow reaches this as `/goal <objective>` on a role that declares `GoalCommandAgentMixin`.
  See [Goals](/weaver/goals).
- `goals=False` on the config makes `pursue` raise `RuntimeError`, and takes away the tools
  that carry work past the turn: Codex starts with `--disable goals`, and Claude Code is given
  `--disallowedTools` for `Agent`, `ScheduleWakeup`, `CronCreate`, `CronDelete`, `CronList` and
  `Workflow`.
- A budget and `interrupt` do not reach a goal; `agent.stop()` ends one, and so does
  [`cut`](#interrupting-by-hand) on the backends it takes the transport down for.

## Hooks

A turn passes through **moments**, and a hook is a Python callable hung on one:

```python
from hmz.coganchor.agents import Moment, Occasion, Verdict

def no_force_push(occasion: Occasion) -> Verdict | None:
    if "push --force" in occasion.about:
        return Verdict(refused=True, because="not on this branch")
    return None

agent.hooks.on(Moment.PERMISSION_REQUEST, no_force_push, tool="Bash")
```

`on` answers with a `Hung` handle, which is also a context manager:

```python
with agent.hooks.on(Moment.STOP, keep_going):
    agent(task)              # and it is down again after the block
```

`hung.off()` takes one down; taking down what is already down is not an error. Hooks are on the
**agent**, so one covers every session it holds, and may be hung or taken down mid-run.

A flow does not hang these directly. It hangs async functions with `agent.on_stop(fn)`,
`agent.on_permission_request(fn)` and the rest, and the harness driver carries each moment
here. See [Flows](/reference/flows).

### The moments

| Moment | When | What a `Verdict` does |
| --- | --- | --- |
| `SESSION_START` | a session is about to take its first turn | nothing |
| `USER_PROMPT_SUBMIT` | a prompt is about to go to the agent | skips the turn; `adds` goes into the prompt |
| `PRE_TOOL_USE` | the agent has reached for a tool | stops the tool where the CLI [takes a hook table](#refusing-a-tool); nothing elsewhere |
| `SUBAGENT_START` | the agent has started an agent of its own | nothing |
| `SUBAGENT_STOP` | one of those has come back | nothing |
| `PERMISSION_REQUEST` | the backend is asking whether a tool may run | denies it, with `because` as the reason |
| `NOTIFICATION` | the agent has stopped to ask its user something | nothing |
| `STOP` | a turn has ended | sends the agent on, with `because` as the next prompt |
| `SESSION_END` | a session has been closed | nothing |

A hook is told an `Occasion` (`moment`, `agent`, `session`, `prompt`, `tool`, `about`, `under`,
`input`, `said`, `again`) and answers with a `Verdict` (`refused`, `because`, `adds`) or
`None`. Two hooks on one moment are one verdict: refused if either refused, adding everything
either added.

A refused `STOP` is a [goal](#goals) written by hand. `occasion.again` counts how many times
this turn has been sent on:

```python
def keep_going(occasion: Occasion) -> Verdict | None:
    if occasion.again < 3 and "TODO" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="There is still a TODO in TASK.md.")
    return None
```

For the two subagent moments, `tool` is what the started agent is called, `about` is what it
was asked, and `under` is the backend's id for it, which pairs a start with its stop. Nothing
waits on them, so a refusal there does nothing. Watchers see them as `subagent` and
`subagent-ends`.

A hook that raises has said nothing. The exception is `Stopped`, from a hook that drove an
agent which has been [stopped](#stopping): it gets out, so a run ended by hand reads as one.

### Not every backend runs every moment

`agent.moments` is what one runs, and `hooks.on` raises `Unhooked` (a `ValueError`) for a
moment outside it, where the hook is hung. Every backend runs the six moments that are not
`PERMISSION_REQUEST`, `SUBAGENT_START` or `SUBAGENT_STOP`.

| Backend | the other six | `PERMISSION_REQUEST` | `SUBAGENT_START`, `SUBAGENT_STOP` |
| --- | :-: | :-: | :-: |
| `claude`, `codex` | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> |
| `cursor-agent` | <Badge type="tip" text="yes" /> | — | <Badge type="tip" text="yes" /> |
| `grok`, `kimi`, `zcode` | <Badge type="tip" text="yes" /> | <Badge type="tip" text="yes" /> | — |
| `agy`, `dsh`, `mimo`, `opencode`, `pi`, `qwen`, an ACP CLI | <Badge type="tip" text="yes" /> | — | — |
| `HumanAgent` | — | — | — |

A flow says which moments it needs where it declares its agents, and is refused before its
first turn if given an agent that cannot run them. Under a flow,
`PermissionRequestHookAgentMixin` is served on Claude Code, Codex, Kimi Code and ZCode; Grok
Build's moment is reachable from Python only.

### When a PermissionRequest refusal reaches the agent

These five backends ask before a tool runs and wait for the answer, so a hook's refusal is the
agent being told no. Whether they ask at all depends on the [rung](#what-an-agent-may-do):

| Backend | Asks | Answered, where no hook refuses |
| --- | --- | --- |
| `claude` | Over the stream the turn is read from, at `bypass`: `--permission-prompt-tool stdio` routes every tool that would change something here. | yes; a request arriving at `read-only` is answered no |
| `codex` | Through its app server: at `auto` (approval policy `on-request`), and at any rung given [`approvals`](#codex). | yes at every rung; no with no rung |
| `grok` | As `session/request_permission`, on the held-open transport only. | yes at every rung; no with no rung |
| `kimi` | Each approval read off the daemon's `/approvals`: at `auto` (Kimi's `yolo`), and at `read-only` or no rung (Kimi's `manual`). At `workspace-write` and `bypass` (Kimi's `auto`) nothing is asked. | yes at `auto`; no at `read-only` and with no rung |
| `zcode` | Through its app server, before a high-risk tool: at `workspace-write` (`edit`), `auto` (`build`) and with no rung. `bypass` (`yolo`) asks nothing. | yes at `auto`; no at `workspace-write` and with no rung |

A hook can turn a yes into a no, never a no into a yes. A config that names no rung routes
nothing to a hook on Claude Code.

### Refusing a tool

`PRE_TOOL_USE` is in every backend's `moments`, but a CLI says what it reached for and then
runs it, so a refusal read off the stream would describe a tool that already ran. It stops the
tool only on a CLI that takes a hook table for a single run (`Profile.hooks`):

| Backend | Seam |
| --- | --- |
| `claude` | `--settings`, the whole settings file as a literal on the command line |
| `qwen` | a settings file of humanize's own, named by `QWEN_CODE_SYSTEM_SETTINGS_PATH` |

```python
def no_shell(occasion: Occasion) -> Verdict | None:
    if occasion.tool == "Bash":
        return Verdict(refused=True, because="this flow does not shell out")
    return None

with agent.hooks.on(Moment.PRE_TOOL_USE, no_shell):
    agent(task)
```

The table points at `hmz internal hook`, a relay that carries the call to a socket this process
serves and the verdict back. The CLI waits for it, and a refusal means the tool does not run.

- Nothing of your own configuration is read, written or replaced.
- The table is installed only while something is hung on the moment: the CLI runs it before
  every tool, so an empty one would slow every file read.
- A hook hung or taken down between turns takes effect from the next turn. One hung during a
  turn is read off that turn's stream instead, which watches rather than gates.
- The table fires before the CLI decides whether a tool is permitted, so a refusal here means
  `PERMISSION_REQUEST` is never asked.
- An [anchored](#where-the-turns-land) turn gets no table: its CLI runs on another machine,
  where neither the relay nor the socket is. There, and on every other backend, the moment is
  read off the stream.

### What the runtime says the turn did

`kimi`, `qwen`, `pi` and `mimo` are Node programs, and read `NODE_OPTIONS` (their
`Profile.preloads`) before they read the CLI. Hang a hook on `PRE_TOOL_USE` and humanize
preloads a file there that reports what the runtime did, as more occasions on the same moment:

```python
def watched(occasion: Occasion) -> None:
    if occasion.tool == "spawn":
        print("the turn ran:", occasion.about)

agent.hooks.on(Moment.PRE_TOOL_USE, watched, tool="spawn")
```

`occasion.tool` is `spawn`, `read`, `write`, `connect`, or `quiet` for a process that has said
all it will; `occasion.about` is the command line, the path or the `host:port`.

- **Told, not asked.** The report comes after the call, so a verdict does nothing. To stop an
  agent doing something, hang the hook on
  [`PERMISSION_REQUEST`](#not-every-backend-runs-every-moment).
- **Hang it before the first turn.** `qwen`, `pi` and `mimo` pick a hook hung later up on their
  next turn. `kimi` runs one daemon for every session of an agent, started once, so a hook hung
  after that gets nothing from it.
- **Filter it.** A turn reads a couple of thousand files. Say `tool=` for what you want.
- **It arrives on another thread**, the one reading the socket. A hook that writes to something
  the flow also touches must be thread-safe.
- Nothing is switched on unless a hook is hung, and nothing for a turn that [lands on another
  machine](#where-the-turns-land).

| | `kimi` | `qwen` | `pi` | `mimo` |
| --- | --- | --- | --- | --- |
| What is watched | the daemon every session of the agent runs in | the launcher, and the bundle it re-execs itself as | the process the session is held open in | its launcher only; what that starts is a native binary |

A Node program the agent itself runs reports nothing: the `spawn` that ran it already did. The
CLI's reads of its own install, and calls on a file descriptor rather than a path, are not
reported. The preload fails open and never holds a turn up: a report it cannot deliver is
dropped. A process that has made a hundred thousand reports says `quiet` once and stops;
reports dropped because this process read too slowly are counted and said the same way, so a
gap reads as a gap. Every other backend has no preload variable, and a hook there sees only the
CLI's own tools.

## Questions

An agent may stop mid-turn to ask its user something. Set `ask` and it reaches you:

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

A `Question` has `text` and `options`, the answers the agent offered. An answer is not held to
them.

- With `ask` unset, the backend is told **nobody answered**, rather than left waiting.
- Under a flow, the question goes to the flow's `on_ask_user` hook where the role declares
  `AskUserHookAgentMixin`, and is otherwise told nobody answered.
- A [watcher](#watching-a-turn-as-it-happens) sees it as an `asks` event either way.

Two more callbacks, set by whatever drives the agent:

| | |
| --- | --- |
| `agent.waiting` | Asked as each turn starts for anything said to this agent while no turn was open. What it returns goes into that turn. |
| `agent.prompting` | Asked between turns for the next thing to say, so a flow can be a conversation. `None` once there will be nothing more. |

`agent.prompted()` is the call that asks `prompting`; it raises [`Stopped`](#stopping) for an
agent stopped while it waited.

## Stopping

```python
agent.stop()      # take no further turn, and end the one being taken
agent.stopped     # whether that has happened
```

The turn under way is closed out and every later call raises `Stopped`. The CLI process the
turn ran in ends, with whatever it started. What the turn changed stays where it got to.
`Stopped` is not a `CalledProcessError`, so loops that carry on past a failed turn do not carry
on past this. To end one turn rather than the agent, use
[`session.interrupt`](#interrupting-by-hand) or a
[budget](#cutting-a-turn-off-and-what-one-turn-may-spend).

## Cutting a turn off, and what one turn may spend

A turn can be given a **budget**; when it is spent, the turn running now stops.

```python
from hmz.coganchor.agents import Budget

session.budget = Budget(output=4_000, seconds=300, when="immediately", then="end")
```

| Field | Default | |
| --- | --- | --- |
| `output` | `0` | Output tokens one turn may write. `0` is no cap. |
| `seconds` | `0` | How long one turn may run, on the clock (time waiting on a tool counts). `0` is no cap. |
| `when` | `"next-response"` | `"next-response"` lets the answer in progress land, waiting a minute at most. `"immediately"` ends the turn where it stands. |
| `then` | `"end"` | `"end"` answers with what has been said. `"fail"` raises `Unrecoverable`. |

- **Per turn.** Every turn starts with the whole budget; what is measured is the rise across
  that turn. `Budget()` caps nothing, which is how one conversation opts out of its agent's
  budget.
- **Held to off the live meter**, which moves as each model request returns, so the turn is cut
  mid-turn. A cap on `seconds` bites even when nothing is arriving.
- **A turn ended by its budget landed.** Its edits are on disk and its conversation is open, so
  the next round carries on in the same session. It is never retried and never carried to
  another account.
- `then="fail"` raises `Unrecoverable`, which `suppress` does not catch.
- The budget is humanize's own, not a CLI flag, so it means the same on every backend whose
  driver feeds the meter. `agy`, `grok` and `qwen` do not, so an `output` cap never bites
  there; see [What it has cost](#what-it-has-cost-and-how-fast).

A budget is a setting of the agent and of one conversation. The turn under way keeps the budget
it started with:

```python
agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model=…, effort="high", budget=Budget(seconds=600)))
session = agent.new()
session.budget                       # Budget(seconds=600), the agent's
session.budget = Budget(output=800)  # this conversation's own, from its next turn
```

### Interrupting by hand

```python
session.interrupt(why="it has been reading the same file for four minutes")
session.cut(why="the flow's budget is spent")
```

`interrupt` ends the turn now running and leaves the session usable. With no turn running it
does nothing; to prevent a turn that has not started, use `agent.stop()`. A budget and the
[watchdog](#when-a-cli-stops-answering) both use it.

`cut` is `interrupt` for a caller that holds the agent for this one conversation, which is what
a flow's harness driver does. On a backend whose turns sit on a transport every session of the
agent shares (`cuts_transport`: Codex, Kimi Code, ZCode and DeepSeek Harness), it then puts
that transport down, ending the turn now and reaching a goal too. On an agent holding several
conversations that ends the turns of all of them. The conversation survives: the next turn
starts the transport again and resumes it by id.

| How the backend holds a turn | `interrupt` reaches | `cut` reaches |
| --- | --- | --- |
| One command per turn: `cursor-agent`, `opencode`, `mimo`, and the command-line turns of `agy`, `grok` and `qwen` | the command and its children | the same |
| One process held open: `claude`, `pi`, and the ordinary turns of `agy`, `grok` and `qwen` | that process; the next turn starts another and resumes | the same |
| A transport shared by the agent's sessions: `codex`, `kimi`, `zcode` (app server or daemon), `dsh` (SDK runtime) | nothing is taken down; the turn stops at the next thing the transport says | the transport, and every turn on it |
| An ACP CLI | `session/cancel` | the same |

`agent.stop()` closes every session of the agent, which lets go of whatever holds each
conversation open: it ends the turn under way as well as preventing the next.

A turn cut off still ends on **exactly one `result`**, carrying what the agent had said to
humanize by then. A CLI that sends a message only when it is complete has said nothing yet, so
a turn cut in its first paragraph answers `""`. A budget's cut-off also wins over a `STOP` hook
that would have sent the agent on.

**What that came to in money** is `hmz.coganchor.prices`, which prices a `Usage` kind by kind
against a list from [OpenLLMPrices](https://openllmprices.com/), kept at
`~/.humanize/prices.json`:

```python
from hmz.coganchor import prices

prices.cost(agent.spent(), agent.config.model)   # dollars, or None for an unlisted model
prices.price("claude-haiku-4-5-20251001")        # Price(model="claude-haiku-4.5", …)
```

Neither call touches the network, and both answer `None`, never `0.0`, for a model nobody
lists. See [Cost and rate](/user/tally).

## What a whole run may spend

A **flow** run is held to the `-b` it was started with by the flow runtime: it hands each turn
the limits that remain, which the harness driver holds with the per-turn budget above and
`cut`, and it refuses the next turn once one is spent. See [Every run has an
allowance](/features/allowances).

For agents driven by hand, a set of agents can share an **allowance**. When any cap is reached,
every agent of the set is stopped:

```python
from hmz.coganchor.agents import Allowance, Ledger

ledger = Ledger(Allowance(hours=6, tokens=10.0, dollars=50), agents)
for agent in agents:
    agent.allowance = ledger
```

::: warning `tokens` is in millions
`Allowance(tokens=2)` is two **million** output tokens. `Budget(output=2)` is two.
:::

| `Allowance` field | |
| --- | --- |
| `hours` | Wall clock. The only dimension that moves while nothing is spent, which is what stops a loop whose every turn fails. |
| `tokens` | Millions of output tokens. |
| `dollars` | US dollars. A model nobody prices counts as `None`, which never reaches the cap. |

Each is a non-negative float, and `0` is no cap. The allowance is checked at both edges of
every turn and as every session closes, by `SessionBase` itself, so no driver can opt out. A
turn asked for under a spent allowance raises `Stopped`; the turn that spends the last of it
still answers. Clones and stand-ins spend the run's allowance.

| Reading | What it says |
| --- | --- |
| `ledger.reads().seconds` | How long the run has been going |
| `ledger.reads().output` | Output tokens every agent of it has written |
| `ledger.reads().dollars` | What that came to, or `None` where nothing in the run is priced |
| `ledger.reads().floor` | Whether the money is short of the truth, part of the run being unpriced |
| `ledger.reads().blind` | Which caps nothing in this run can read |
| `ledger.over()` | Why the run is over its allowance, in words, or `""` |
| `ledger.spent` | Whether it has already been found to be over it |

## Efforts

`effort` goes to the backend in its own wording, and is checked against the backend's ladder
wherever it arrives: where the agent is made, and where a flow [moves it
mid-run](#moving-the-effort-while-it-runs). A word off the ladder raises `Unserved` there,
rather than failing on some later turn.

**`auto` is on no ladder and every backend takes it.** It means no rung: nothing is said to the
CLI about how hard to think. In Python it is `effort=""`, which is what `"auto"` becomes. A
model with no rungs, such as Cursor's `composer-2.5`, runs at `auto`. An [ACP
CLI](#a-cli-of-your-own) is checked against nothing: it runs as configured, under whatever word
you type.

| Backend | Ladder, hardest first |
| --- | --- |
| `agy` | `high`, `medium`, `low` |
| `claude` | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| `codex` | `ultra`, `max`, `xhigh`, `high`, `medium`, `low`; `ultra` and `max` only on the models that take them |
| `cursor-agent` | `max`, `xhigh`, `extra-high`, `high`, `medium`, `low`, `minimal`, `none`, where the account lists that model at that rung |
| `dsh` | `max`, `high`, `low`, `off` |
| `grok` | `xhigh`, `high`, `medium`, `low` |
| `kimi` | `max`, `high`, `medium`, `low`, each also as `swarm…` |
| `mimo`, `opencode` | `xhigh`, `high`, `medium`, `low`, `minimal` (the model variant) |
| `pi` | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| `qwen` | `max`, `xhigh`, `high`, `medium`, `low`, `none` |
| `zcode` | `max`, `xhigh`, `high`, `medium`, `low`, `enabled`, `nothink`, `disabled`, narrowed per model |

The interface offers each model only the efforts it takes, where the backend says.

| Backend | How the effort is said |
| --- | --- |
| `agy` | `--effort`, sent only where the model's name carries no rung. A name that does, such as `gemini-3.7-flash-high`, runs at that rung, and the configured or moved effort is not sent: the CLI refuses the flag beside such a name, and refuses a bare name without it. |
| `claude` | `--effort`. `ultracode` is `xhigh` thinking with the turn opted into orchestrating a fleet of its own, which is why it sits above `max`. |
| `codex` | Per turn, on the app server. `gpt-5.6-sol` takes `ultra`; `gpt-5.5` does not. |
| `cursor-agent` | Written into the model id: `<model>-<rung>` where the account lists that id. See [Cursor Agent](#cursor-agent). |
| `grok` | `--effort`. `grok agent` accepts any word, so a word off the four is refused where the agent is made rather than failing on the first command-line turn. |
| `kimi` | Per turn. The `swarm` prefix runs the same thinking as a fleet of subagents: `swarmmax` is `max` wide. The prefix is `hmz.coganchor.agents.SWARM`. |
| `pi` | `--thinking`. pi clamps a rung the model cannot serve to the nearest one it can, rather than refusing. |
| `qwen` | A settings file of humanize's own, named by `QWEN_CODE_SYSTEM_SETTINGS_PATH`, one per effort. See [Qwen Code](#qwen-code). |
| `zcode` | A call on the session. GLM 5.3 and Kimi K3 take `low`, `high`, `max`; Claude and GPT take `low` to `xhigh`, and Opus 4.7 `max` on top; DeepSeek V4 takes `high`, `max`; GLM 5.2 takes `max`, `high`, `nothink`; models that only think or not take `enabled`, `disabled`. ZCode states which on the session, and humanize narrows the ladder to them. |

## Moving the effort while it runs

The effort is the one setting a flow may move as it goes:

```python
agent.effort = "low"       # every session of this agent, from its next turn
session.effort = "max"     # this conversation alone
session.effort = ""        # back to whatever the agent runs at
```

`agent.config.effort` stays what the agent was configured with; `agent.effort` is what its
turns run at. The change takes hold on the **next** turn; the turn under way keeps its effort.

| Backend | How a moved effort takes hold |
| --- | --- |
| `codex`, `kimi`, `opencode`, `mimo`, `cursor-agent` | Sent with the next turn. |
| `claude`, `dsh`, `agy`, `grok`, `qwen` | The process or runtime restarts and resumes the same conversation. On `agy` a model whose name carries a rung stays at it. |
| `pi` | A command to the held process, between turns. |
| `zcode` | A call on the session, between turns. |

On Kimi Code a `swarm` prefix moves with it: `agent.effort = "swarmmax"`.

## What it has cost, and how fast

```python
session.spent()          # Usage(input=41230, output=2180, cache_read=980100)
session.rate()           # tokens a second, by kind, over the last five minutes
session.rate(over=60)    # over the last minute
session.juice(over=60)   # output tokens an average model request came out with
agent.spent()            # every session this agent opened, dropped ones included
agent.rate(over=60)
agent.juice()
```

A `Usage` is a **mapping of kind to tokens**. `input`, `output` and `total` are attributes; the
rest differ by backend, so a missing kind is one the backend does not report:

```python
spent = session.spent()
spent.input, spent.output, spent.total       # always
spent.get("cache_read", 0)                   # for a backend that counts one
dict(spent)                                  # everything it does count
```

The five kinds are `hmz.coganchor.agents.KINDS`: `input`, `output`, `cache_read`,
`cache_write`, `reasoning`. Every driver reports under these names, and they add up to what
crossed the wire and no more. Which a backend reports is declared on the agent class as
`counts`:

| `counts` | Backends |
| --- | --- |
| `input`, `output` | `codex` (cached reads are inside the input), `zcode` |
| `input`, `output`, `cache_read`, `reasoning` | `agy` |
| `input`, `output`, `cache_read`, `cache_write` | `claude`, `cursor-agent`, `dsh`, `grok`, `kimi`, `pi`, `qwen` |
| all five | `opencode`, `mimo` |
| none | an ACP CLI |

- **A rate is tokens a second over time on the clock**, including the time a flow spends
  between turns. The window defaults to five minutes, `hmz.coganchor.agents.WINDOW`, the same
  one the interface reads over. A run younger than the window is measured over the run.
- **`juice()` is output per model request**, not per flow turn. It is what an effort moves, so
  it is the number to steer by when what matters is how hard the model thinks. A window with no
  request in it reads `0.0`.
- **The `result` event carries the same reckoning** as `spent`, beside the per-model `tokens`,
  and `result.spent.total` is what `result.tokens` comes to.

The meter behind `spent()`, `rate()` and `juice()` moves while the turn runs on most backends:

| Backend | The meter moves |
| --- | --- |
| `claude` | on each message it answers with |
| `codex` | on `thread/tokenUsage/updated` |
| `dsh`, `pi` | on each finalised assistant message |
| `opencode`, `mimo` | on each step |
| `kimi` | on each `turn.step.completed` notification |
| `zcode` | on each row its log gains per model request |
| `cursor-agent` | once, on the closing `result`, so its rate moves a turn at a time |
| `agy`, `grok`, `qwen` | never: their usage is on the closing `result` event only |

::: warning agy, grok and qwen do not feed the meter
Their drivers put a turn's usage on the `result` event's `spent` and `tokens` and nowhere else.
So `spent()`, `rate()` and `juice()` read zero for them, a `Budget(output=…)` never bites, and
an `Allowance` counts none of their tokens or dollars. Read the `result` event instead.
:::

A backend that states a whole turn's cost after saying what each request cost is settling up,
and that is not counted as another request.

## What an agent may do

A config's `permission` is one rung of a four-rung ladder, loosest last, or `""`, which is no
rung at all:

| Rung | What it means |
| --- | --- |
| `read-only` | It may look at anything and change nothing: no edits, no commands. |
| `workspace-write` | It may change the workspace it was given, and is stopped at the edge of it. |
| `auto` | It may reach for anything, and what it asks for is granted. |
| `bypass` | Nothing is asked and nothing is checked. |

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", permission="read-only")
```

- **`""` says nothing to the CLI**: no mode, no sandbox, no approval policy. The turn is the
  one the CLI takes when a person runs it headless, and that is looser than every rung. A
  flow's agent never runs this way.
- **`bypass`** is the rung an unattended flow reaches for.
- **Under a flow**, the rung is not set directly. The role declares a `Permission` and the
  harness driver reads it into a rung, as [below](#the-flow-api-s-permission-on-each-cli). `-a`
  has no permission setting, and a line that writes `permission=` is refused.

Every backend has a ladder of its own, so each driver reaches for whichever of its settings
says the same thing. **A dash is the rung above it, run again.** "Refused" means the config is
refused with `Unserved`, so a flow declaring that rung is refused the backend before its first
turn.

| Backend | `read-only` | `workspace-write` | `auto` | `bypass` |
| --- | --- | --- | --- | --- |
| `agy` | `plan` mode | `accept-edits` mode | skip permissions | — |
| `claude` | `plan` mode | `acceptEdits` mode | `auto` mode | `manual` mode, answered here |
| `codex` | `read-only` sandbox | `workspace-write` sandbox | `workspace-write`, `on-request` | `danger-full-access` |
| `cursor-agent` | `plan` mode | sandbox on | `--auto-review` | sandbox off |
| `dsh` | refused | refused | refused | taken |
| `grok` | three read tools | web search off | every tool | — |
| `kimi` | `manual` and plan mode | `auto` mode | `yolo` mode | `auto` mode |
| `mimo`, `opencode` | `edit`, `bash` denied | web tools denied | nothing denied | — |
| `pi` | four tools withheld | nothing withheld | — | — |
| `qwen` | five tools withheld | `web_fetch` withheld | nothing withheld | — |
| `zcode` | `plan` mode | `edit` mode | `build` mode | `yolo` mode |
| an ACP CLI | refused | refused | refused | taken |

How each backend says it, and what to know:

- **Antigravity**: `--mode plan`, `--mode accept-edits`, and `--dangerously-skip-permissions`
  for both `auto` and `bypass`. At `workspace-write` edits pass and commands are denied: a
  print-mode run soft-denies what it was not permitted and names it under `denied_actions`.
- **Claude Code**: `--permission-mode`. **Its `bypass` is humanize answering, not Claude
  skipping.** An account's managed settings can carry
  `"disableBypassPermissionsMode": "disable"`, and then `--dangerously-skip-permissions`
  quietly declines every edit. So `bypass` runs at `manual` mode with
  `--permission-prompt-tool stdio` and answers each request `allow`. An organisation's hard
  `deny` list is still enforced by the CLI.
- **Codex** is the one backend with a sandbox of its own, so its rungs are the real thing. The
  approval policy is `never` at every rung but `auto`. On a machine whose requirements forbid
  `danger-full-access`, a `bypass` agent runs at `auto` instead (the same freedom, with every
  ask granted) and says so once, on stderr when nothing is watching:

  ```
  codex: this machine will not run an agent at bypass, so it runs at auto, where what it asks
  for is granted
  ```

- **Cursor Agent**: `--mode plan`, `--force --sandbox enabled`, `--auto-review` (its own
  classifier) and `--force --sandbox disabled`.
- **Grok Build's rung is the tools it is started with**, every rung under `--always-approve`:
  `--tools read_file,grep,list_dir` at `read-only` and `--disable-web-search` at
  `workspace-write`. On 1.0.24 its `--permission-mode` made no difference headless, so humanize
  sends none, and there is no workspace sandbox to map `workspace-write` onto.
- **Kimi Code's `read-only` refuses commands too.** Plan mode vetoes `Write`, `Edit`,
  `TaskStop` and the cron tools; `manual` turns everything else, `Bash` included, into an
  approval, which the driver answers no. The model cannot leave plan mode either:
  `ExitPlanMode` is an approval too. Kimi's own modes read loosest last as `manual`, `yolo`,
  `auto`, so its `yolo` is humanize's `auto`. Its `auto` mode denies `AskUserQuestion`, so at
  `workspace-write` and `bypass` the agent never stops to ask and `NOTIFICATION` does not fire.
- **opencode and mimocode**: the rung goes in the turn's permission table. Any rung also adds
  the CLI's yes-to-everything-left flag: `--auto` on opencode, `--dangerously-skip-permissions`
  on mimo.
- **pi has no permission gate and no sandbox.** `read-only` is
  `--exclude-tools bash,edit,write,powershell`, and the other three rungs are one agent.
- **Qwen Code runs at `--approval-mode yolo` on every rung**, and the rung is the tools taken
  off its command line: `edit`, `write_file`, `notebook_edit`, `run_shell_command` and
  `monitor` at `read-only`. Its asking modes leave a held-open session waiting on an approval
  nothing can answer. Nothing confines an edit to the workspace, so `workspace-write` withholds
  the fetch, not a boundary.
- **ZCode has a mode for each rung.** Its own `auto` mode refuses every tool ("reserved but not
  implemented yet") and is nobody's rung.
- **DeepSeek Harness and ACP CLIs** take `bypass` or no rung. dsh's SDK exposes no per-session
  sandbox or approval control, and its default composition mounts the unconfined
  `dsh-bash-local` and `dsh-fs-local`. An ACP CLI's only word about permission is a per-call
  question, which humanize grants.

No rung sends nothing, on every backend.

### The flow API's permission on each CLI

A flow's role declares a `Permission`: `local`, `user` and `system`, each `NONE`, `READ` or
`ALL`, and `online`, `NONE` or `ALL`. See [Flows](/reference/flows). Whatever it declares,
**nothing is put to anybody for approval**: every session runs at its CLI's nothing-asked mode,
with every request approved. What limits a flow's agent is its `Permission` and the hooks the
flow hangs.

| `local` | every harness but `dsh` and ACP CLIs | `dsh`, ACP CLIs |
| --- | --- | --- |
| `READ` or `NONE` | `read-only` | `bypass` |
| `ALL` | `bypass` | `bypass` |

- **`local` `ALL` fences nothing else.** `user` and `system` are not held to `READ` or `NONE`:
  a session that may write its workdir may write anywhere its user can. Codex's
  `workspace-write` and cursor-agent's `--sandbox enabled` could fence it but are not used:
  both are bubblewrap, which cannot start without a user namespace, as in many containers.
- **`local` `READ` is the CLI's own read-only rung.** It reads outside the workdir too, which
  is wider than a `user` or `system` of `NONE`. `local` `NONE` is the same rung.
- **`dsh` and ACP CLIs run at `bypass`**, wider than any permission below `ALL`.
- **`auto` is used only on Kimi Code and ZCode, and only while a hook is hung** on
  `PERMISSION_REQUEST` or `ASK_USER`. There `auto` (Kimi's `yolo`, ZCode's `build`) is the mode
  where the CLI asks about what it deems risky, and on Kimi the mode where its agent may ask
  its user at all. humanize answers yes unless the hook says no. `auto` is never used for
  Claude Code or cursor-agent, whose `auto` is the model reviewing itself.
- **Codex, while a `PERMISSION_REQUEST` hook is hung**, keeps its rung's sandbox and runs with
  approval policy `untrusted`. An `ASK_USER` hook turns on Codex's
  `default_mode_request_user_input` feature, without which its agent cannot ask anything
  outside plan mode. Either takes hold from the session's next turn.
- **`online` is the CLI's own web tools**: on for `ALL`, off for `NONE` where the CLI can be
  told, and left as the CLI has it where it cannot (cursor-agent, pi, agy, ACP CLIs), which may
  be wider. A shell command reaches the network whatever this says.

## Whether an agent may search the web

`web_search` has three values:

| Value | Meaning |
| --- | --- |
| `None` (default) | Nothing said. The agent searches or not exactly as its CLI does when you run it yourself. |
| `True` | On, sent even to a CLI that ships with search off. |
| `False` | Off. Refused with `Unserved` on a backend that cannot be told. |

```python
config = ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", web_search=False)
```

A stated answer is sent in both directions where the CLI needs it, so `True` means the same
everywhere:

| Backend | How it is said |
| --- | --- |
| `claude` | `--disallowedTools WebSearch,WebFetch` when off |
| `codex` | `-c tools.web_search=true\|false`, both ways |
| `dsh` | the `dsh-web` plugin, its search and fetch providers and `dsh-tool-web` mounted when on; the bundled composition has no web |
| `grok` | `--disable-web-search` when off |
| `kimi` | `disabled_tools` on the prompt: `WebSearch` and `FetchURL` when off, empty when on |
| `qwen` | `--exclude-tools web_search,web_fetch` when off |
| `opencode` | `webfetch: deny` and `websearch: deny` in its permission table when off |
| `mimo` | the same two and `codesearch: deny` |
| `zcode` | `WebSearch` and `WebFetch` in the session's `toolDenylist` when off |
| `agy`, `cursor-agent`, `pi`, an ACP CLI | no way of being told: off is refused |

- The refusal comes where the config arrives: where the agent is made, and where one already
  running is reconfigured. `None` is refused nowhere.
- It composes with the [rung](#what-an-agent-may-do): a rung that already withholds the web
  tools goes on withholding them.
- Under a flow, a role's `online` scope says it: `ALL` is on, `NONE` (the default) is off. On a
  backend that cannot be told, the flow's agent is left as its CLI has it, which may be wider.
- A shell command the agent runs reaches the network whatever this says.

## The service tier

`service_tier` is `"default"` unless you ask for `"fast"`, which buys lower latency, not less
reasoning. It does not lower the effort or choose a smaller model.

| Backend | `fast` is |
| --- | --- |
| `claude` | `fastMode: true` in its `--settings`. At `default` nothing is sent, so your own `fastMode` setting stands. |
| `codex` | its native `priority` service tier |
| `cursor-agent` | the `-fast` id the account lists for that model, such as `composer-2.5-fast`; refused where none is listed |
| every other backend | refused with `Unserved` before the first turn |

The field records the tier asked for; the provider decides the tier served. Claude subscription
sessions need usage credits for fast mode and may report standard service. Provider usage
records are authoritative.

## The skills an agent carries

**A skill installed on this machine is its CLI's own.** humanize does not switch one off, write
the CLI's settings, or keep a per-agent list of them. You can read the list:

```python
from hmz.coganchor.agents.skills import skills

skills("claude")   # what it would load here: yours, and this project's

agent.loaded       # the skills whoever drives it brings, mounted onto every session
agent.loads(loaded)  # replace them
```

Under a flow these are the skills the role names in `_skills`, and a flow narrows them only
with `derive(skills=…)`. See [Flows](/reference/flows).

Which of the brought skills **one conversation** carries is its own, and may change while it
runs:

```python
session = agent.new()
session.skills             # every one the flow brought, until told otherwise
session.loads(["writing"]) # from its next turn on
session.loads(None)        # all of them again
```

What lands where the backend reads it is settled as a turn opens, not when `loads` is called. A
name the flow does not bring is ignored.

A flow's skills are copied where the backend reads a project's own skills for as long as the
session lives, then taken away:

| Backend | Where a flow's skills are mounted |
| --- | --- |
| `claude` | `.claude/skills/` in the workspace |
| `agy`, `codex`, `grok`, `kimi`, `mimo`, `opencode`, `qwen`, `zcode` | `.agents/skills/`, which several of these read |
| `cursor-agent` | `.cursor/skills/` in the workspace |
| `dsh`, `pi` | none |

- A project's own skill of the same name wins.
- **pi** reads workspace skill directories only for a trusted project, and a headless run has
  nobody to trust it. Hand it a skill by path instead:
  `PiAgentConfig(skill_paths=("/where/it/is",))`.
- An agent [whose turns land elsewhere](#where-the-turns-land) gets them only where that
  machine reads this workspace: a container handed it does, a host across a network does not.

## Callbacks as tools

Something that drives an agent can put a function in front of it. The agent calling that tool
runs the driver's own code, in its process, and reads back what it answers.

This is for agents driven from Python. **The flow API has no tools**: a flow reaches back into
its own code through [hooks](/weaver/tools) instead.

```python
from pydantic import BaseModel, Field
from hmz.coganchor.agents import Tool


class Reviewing(BaseModel):
    path: str = Field(description="the file to have read")


session = agent.new()
session.offers(
    [
        Tool(
            name="review",
            about="have the reviewer read a file and say what is wrong with it",
            takes=Reviewing,
            call=lambda said: reviewer(f"review {said.path}"),
        )
    ]
)
session("write the parser, and have your work reviewed before you stop")
```

| `Tool` field | |
| --- | --- |
| `name` | What the agent calls it. |
| `about` | What it is for, said to the model; the whole of what it knows about when to reach for it. |
| `takes` | A pydantic model of its arguments, or `None` (the default) for a tool that takes none. |
| `call` | What to run, given the model (nothing where `takes` is `None`). What it returns goes back as text; `None` is a tool that did something. |

- `session.offers(None)` takes them back.
- A CLI learns its tools where it starts, and some start once per agent, so what is offered is
  the agent's: two conversations offering a tool of one name offer one tool.
- The road is the Model Context Protocol. The backend is handed
  `hmz internal tools --at <socket>`, which relays back to the offering process. Nothing starts
  until something is offered.
- **A callback that raises is the tool failing.** The model is told what went wrong and may
  call it again.
- `session.takes_tools` is `True` on Claude Code (`--mcp-config`) and Codex
  (`-c mcp_servers…`). Elsewhere `offers` raises `NotImplementedError`.

## Where the turns land

A config's `machine` says where an agent's work goes. `None`, the default, is this machine.

```python
from hmz.coganchor.machines import DockerConfig

ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

`agent.anchor` is where its turns land, and brings the machine up the first time it is asked
for, which is the first turn. Constructing an agent pulls no image and starts no container. See
[Machines](/reference/machines).

Under a flow, a session's turns land in the environment it was spawned in. An environment on a
host reached with ssh (`-e repo=ssh@gpu-box/home/me/repo`) gives the agent an anchored
`machine`; one on this machine gives it none.

## Which account it runs as

A config's `provider` names one of the [providers](/reference/providers) made for its CLI.
`""`, the default, is the CLI as you already run it.

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="max", provider="deepseek")
```

A turn of such an agent gets that provider's variables and reads its credentials from that
provider's own directory. Two agents of one backend can be two accounts at once. Only the
credential files move: sessions, settings and skills are the CLI's own.

```python
agent.provider       # Provider | None: the account, read once and kept; None is your own login
agent.node()         # the same as an account, never None, which is where a chain starts
agent.walks()        # that account and whatever it falls back to, in the order tried
agent.environment()  # what its turns run with, on top of what they inherit
```

`agent.provider` raises `ValueError` the first time a turn needs an account that is not there.
An agent that cannot find its account does not quietly run as yours.

## When an account goes down

A key is revoked, a gateway refuses, a subscription runs out. Before the flow sees a failed
turn, three things are tried, in order: **retries** at the same place, the **account chain**,
and a **fallback place**.

### Retries

How many times a failed turn is taken again is said about the **place**: CLI, account and
model.

```python
from hmz.sdk import Hmz

Hmz().fallbacks.retrying("claude@mine/claude-opus-5", 3, "exponential-jitter", 120)
```

The arguments are the place, the tries beyond the first, the wait policy, and a cap on the
whole of it in seconds (`0` for none). `/fallback` at the prompt says the same. **Nothing is
retried by default**: a prompt the model refused is the same refusal every time.

| Policy | Waits |
| --- | --- |
| `none` | no wait |
| `constant` | 1s, 1s, 1s |
| `linear` | 1s, 2s, 3s |
| `exponential` | 1s, 2s, 4s, 8s |
| `exponential-jitter` | exponential, each wait anywhere up to it, so agents failing at once do not retry together. The default policy. |
| `fibonacci` | 1s, 1s, 2s, 3s, 5s |

**Each kind of failure gets its own answer.** The kind (`Failed.fault`) is worked out from what
the CLI said, how it exited and, for Antigravity, its own log. It decides how many tries a
failure is worth, the shortest wait, and whether another account can answer it at all. A 429
waits half a minute and then moves account; a 401 moves account at once and says the one it
left needs signing in; a model the account may not name moves account; a retired model skips
the accounts entirely. The full table is in [Falling back](/user/fallback). An unclassified
failure is retried as the step says. An `Unrecoverable` is never retried or carried.

### The account chain

Each account names the one to carry on under when it fails:

```python
Hmz().accounts.points("claude", "subscription", "key")
Hmz().accounts.points("claude", "key", "gateway")
Hmz().accounts.points("claude", "", "spare")   # your own login, then `spare`
```

`/providers`, cursor on the account, then <kbd>enter</kbd>: *falls back to* says the same.

- `""` is the login this machine already has (`claude/`). A chain may start there, and nothing
  may fall back to it. humanize keeps no credentials for it, and a turn under it is the CLI's
  own.
- The **same conversation** continues: the session id is the backend's own, so the next account
  resumes it. The agent stays on the account it moved to for every later turn.
- Whatever the agent held open (a Claude process, a Codex server, a DeepSeek Harness runtime)
  is let go and reopened as the new account.
- A model belongs to its account. An account whose catalogue lacks the model fails for that
  reason.
- The last account's failure is what the turn raises. A chain that loops ends at the second
  sight of an account.
- Failed attempts stay on the transcript, so a reader can see where the turn went.

## When the place has nowhere left to run

Some failures no account answers: a retired model, a CLI that will not start, a region gone
dark. What answers those is another **place**, written down [between the two](/user/fallback):

```python
Hmz().fallbacks.points("claude@work/claude-opus-5", "codex@key/gpt-5.6-sol")

agent.spec          # 'claude@work/claude-opus-5', the place it runs at
agent.stands_in()   # the agent that takes its turns, or None where nothing was written down
```

- It is tried last, after the retries and the account chain.
- No backend takes another's session id, so the turn is taken in a **new session** at the new
  place, by an agent configured as the one it left (effort, rung, skills) and answering through
  the session that asked. Settings that were measurements of the old model (`of_model` on the
  config, such as Codex's `overrides`) are dropped when the model changes.
- That session is held as long as the one that asked. The conversation is lost at the move
  only: a stateful loop that moved is one conversation on the other side.
- The stand-in is built the first time a turn has nowhere left to go, and kept.
- An `Unrecoverable` is not carried here either.

## When a CLI stops answering

A CLI can keep its stream open and never say another word. Nothing fails, so nothing is
retried. Every read a turn blocks on runs under a clock that restarts whenever the backend says
anything: a token of reasoning, a tool call, a line of protocol nobody shows.

| Setting | Value |
| --- | --- |
| Silence allowed | 900 s; 360 s for `dsh` (`Profile.silence`) |
| Override | `HUMANIZE_WATCHDOG=<seconds>`; `0` or less turns the watchdog off |
| Paused | while the turn waits on **you**: a permission prompt, a watcher or hook that pauses |

```sh
HUMANIZE_WATCHDOG=3600 hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 "…"
HUMANIZE_WATCHDOG=0    hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 "…"
```

When the clock runs out, a ladder is climbed, gentlest first:

1. **Look.** A process burning CPU, itself or under something it started, is given up to four
   more windows: a turn running `pytest` for twenty minutes is working. A suspended or defunct
   process gets none.
2. **Ask it to stop**, with [`interrupt`](#interrupting-by-hand). The conversation is
   untouched.
3. **Put the transport down.** The process is signalled, with everything it started. On
   `codex`, `kimi` and `zcode` the shared server goes instead, ending the agent's other turns
   too, and that is said before it happens.
4. **Kill what is left**, and wait on it.

Every rung says so as a `notice`:

```
claude is idle and has said nothing for 903s
claude was asked to stop: no output for 903s
claude is not answering; ending it; 4e0d…c1 is picked back up on the next try
```

The turn then fails with what happened, not `exit status -9`. It is an ordinary `Failed`, so
the [retries](#retries) take it, against the same conversation.

## Names, and what a run left behind

```python
agent.id       # the name you gave it, the name the flow calls it, or a codename
agent.backend  # "agy", "claude", "codex", "cursor-agent", "dsh", "grok", "kimi", "mimo",
               # "opencode", "pi", "qwen", "zcode", or the name an ACP CLI was added under
agent.opened   # the backend's id for every session this agent ever opened, oldest first
agent.sessions # the ones somebody still holds
agent.config   # what it runs at
```

Two agents at one model and effort are still two agents, and `id` tells them apart. `opened` is
a list of ids rather than sessions, so a flow running for days keeps only strings. A trace is
handed it to say which trajectories were this agent's:

```python
from hmz.runtime.tracing import collect

collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

A [flow](/reference/flows) names its agents by their roles and writes all of this into its
[epic](/reference/tracing), so this is only needed for agents driven by hand.

### The name nobody gave it

An agent nobody named gets a codename out of Amphoreus, from *Honkai: Star Rail*:

```text
NeiKos496   PhiLia093   Golem99   Utop13   ScreW   KykLos204   MetaKratos881
```

- Twenty-nine are designations the story says out loud. While any is free, one comes up half
  the time, copied verbatim in whatever shape the story spells it.
- The rest are built by the same rule: morphemes joined at a capital (`Meta` and `Kratos` are
  `MetaKratos`), then digits. Longer words are built when the short ones run out, so there is
  no last code and never a hex tail.
- No code is handed out twice in one process.

Name the agents whose roles matter, and let the rest draw.

## An agent that is not quite the one you were handed

What an agent is is settled where it is made. The one way to have an agent that differs is to
make another:

```python
from dataclasses import replace

careful = agent.clone(config=replace(agent.config, effort="max"))
```

`clone(*, config=None, name=None, skills=None)` keeps everything not named, the skills
included. Nothing a run put on the agent comes across: the clone has opened no conversation,
spent nothing, is watched by nobody, has no hooks hung, and gets a codename unless you give a
`name`. It is not stopped for its original having been. It does spend the run's
[allowance](#what-a-whole-run-may-spend).

`reconfigure`, `runs_on`, `loads`, `rename` and `disable_goals` change an agent in place, for
whoever drives it from Python. A flow reaches none of them: it has `derive`, which narrows what
an agent may touch and which skills it carries, and never widens either. See
[Flows](/reference/flows).

## The person as an agent

A flow that is a conversation has two sides, and the second is you:

```python
from hmz.coganchor.agents import HumanAgent

person = HumanAgent()                      # name= is optional, defaulting to "human"
person("Here is what I did. What next?")   # asks, and answers with what was typed
```

It runs no model, spends nothing and runs no moment, and its turns are not bracketed by
`begins`/`ends`. In a flow the person is an `Outworlder` role filled by the runtime, not an
agent `-a` names. See [Flows](/reference/flows).

### Asking them for a shape, which is a questionnaire

Given a [`schema`](#answering-in-a-shape), the person is asked **a question per field**, and
the model is built from their answers:

```python
class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")

settled = person("How should I do this?", schema=Settled, suppress=True)
```

| In the model | What they are asked |
| --- | --- |
| `description=` | the question itself, or the field's name where it has none |
| `Literal[…]` | those words, as the answers offered |
| `bool` | `yes` and `no` |
| a default | "or `-` for 3", and a dash takes it |
| `list[str]` | one line, separated by commas |

Each question goes through `AgentBase.asked`, which the interface shows and answers, so `/afk`
or a command line answers it the way it answers any question: nobody is there. A refused value
is put back on its field, in the model's own words, a bounded number of times. A questionnaire
nobody filled in answers `None` under `suppress`. A flow asks it as
`await human.run(question, session=…, output_schema=Settled)`; an away outworlder answers with
the model built from its defaults, and raises `OutworlderAway` for a model with a field that
has none.

## Backend notes

What each backend adds to the common config, and how it is driven.

### How each backend is driven

| Backend | Driven through | `interject` | Fork | Trace |
| --- | --- | --- | --- | --- |
| `agy` | a held-open process; a print command for shapes and slash commands | — | — | yes, with sub-agents |
| `claude` | a held-open process | written on its stream | `--fork-session` | yes, with sub-agents |
| `codex` | an app server shared by the agent's sessions | `turn/steer` | `thread/fork` | yes, with sub-agents |
| `cursor-agent` | a command per turn | — | — | — |
| `dsh` | its Python SDK, in this process | — | — | yes, with sub-agents |
| `grok` | a held-open process; `grok -p` for shapes, forks, withheld tools and its own settings | — | `--fork-session` | yes, with sub-agents |
| `kimi` | a daemon shared by the agent's sessions | queued, then steered in | `kimi fork` | yes, with sub-agents |
| `mimo`, `opencode` | a command per turn | — | `run --fork` | yes, with sub-agents |
| `pi` | a held-open process | a `steer` command | `--fork` | yes |
| `qwen` | a held-open process; a command per turn for shapes | — | `--fork-session` | yes |
| `zcode` | an app server shared by the agent's sessions | — | `session/fork` | yes, with sub-agents |
| an ACP CLI | a held-open process | — | `session/fork`, if served | — |

A backend is driven through its command line where that can express what the agent is
configured with, and through the server it serves its own client from where it cannot. A turn
that must stay open to be talked to is such a case. The commands each one runs are in its note
below.

**Trace** is what `Hmz().epics.trace()` reads: every backend but `cursor-agent` and ACP CLIs,
and on some of them the sub-agents a turn started, each under the session that started it.
opencode and mimocode keep their sessions in SQLite, which the trace reads with a query; they
leave no log for the interface's running cost, so their cost reaches a flow as each turn lands.

### Antigravity

`agy`. Ordinary turns reuse one official CLI process through stream-json input. Slash commands
and shaped answers use separate print commands, then resume the same conversation. A slash
command is a whole first word (`/help`, `/plugin:install`); a task that merely opens with a
path is ordinary. Changed configuration, native customisations or flow resources restart the
process; an anchored turn always ends it, for filesystem synchronisation.

| Field | Default | |
| --- | --- | --- |
| `add_workspace` | `True` | Pin the session's directory with `--add-dir`, so the CLI does not pick a scratch project of its own. |
| `print_timeout` | `86400.0` | `--print-timeout`, in seconds. Since 1.1.28 a turn that reaches that clock exits successfully with a partial answer, so the CLI's own five minutes is raised to a day; humanize's [watchdog](#when-a-cli-stops-answering) and budget are the clocks that decide. |
| `disable_slash_commands` | `False` | `--disable-slash-commands`: a prompt opening with `/deploy` reaches the model as words. |
| `sandbox` | `False` | `--sandbox`: the CLI's own terminal restrictions. |

Native usage is cumulative across a conversation; each result reports its own turn's increment.
Shaped answers validate the native final `structured_output`.

### Claude Code

`claude`. One `claude --print` held open for the session. An [anchored](#where-the-turns-land)
session's process ends with each turn, so the work is pushed back when the turn ends.

| Field | Default | |
| --- | --- | --- |
| `allowed_tools` | `()` | Exact `--allowedTools` rules, for a bounded unattended flow. They do not widen the rung. |
| `partial_messages` | `True` | `--include-partial-messages`. See [A turn narrated as it is written](#a-turn-narrated-as-it-is-written). |

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="max", allowed_tools=("Bash(git diff *)",))
```

- Every turn runs with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, so Claude cannot send a
  subagent or command to the background and end the turn early. Subagents still run, several at
  once, and the turn ends when they have.
- `--json-schema` is an argument of the process, so asking a session for a shape it was not
  started with restarts the process and resumes the conversation.
- `bypass` is `manual` mode with `--permission-prompt-tool stdio`; see [What an agent may
  do](#what-an-agent-may-do).

### Codex

`codex`. One `codex app-server` per agent, serving every session of it. Every field defaults to
what a bare `codex app-server` does, and `~/.codex/config.toml` is left as it is.

| Field | Default | |
| --- | --- | --- |
| `overrides` | `()` | Native `-c` overrides, as `(key, value)` pairs. Only `model_context_window` and `model_auto_compact_token_limit`, each a positive integer, the second below the first. Dropped when a fallback changes the model. |
| `features` | `()` | `--enable`/`--disable`, as `(name, on)` pairs by the names `codex features list` prints. `goals` and anything starting `browser_use`, `computer_use`, `standalone_web_search` or `web_search` is refused: say those with `goals`, `web_search` and `permission`. |
| `strict_config` | `False` | `--strict-config`: refuse an unrecognised setting, yours included. |
| `approvals` | `""` | Codex's approval policy in place of the rung's: `untrusted`, `on-request`, `on-failure` or `never`. `untrusted` at `bypass` is full access with everything but a known-safe read asked about, and granted unless a `PERMISSION_REQUEST` hook refuses. |

```python
CodexAgentConfig(
    model="gpt-5.6-sol",
    effort="max",
    service_tier="fast",
    overrides=(("model_context_window", "1000000"), ("model_auto_compact_token_limit", "900000")),
    features=(("multi_agent_v2", True),),
    strict_config=True,
)
```

`-a` names only the place, model and effort, so these are set where an agent is made, from
Python. `-p/--profile` and `--add-dir` are not offered: `codex app-server` does not take them.

### Cursor Agent

`cursor-agent`. One run per turn.

| Field | Default | |
| --- | --- | --- |
| `trust` | `True` | Tell `cursor-agent` the workspace is trusted rather than let it ask. A headless turn has nobody to answer. `False` hands the question back. |
| `partial_output` | `False` | `--stream-partial-output`: words arrive as they are written. The gathered message Cursor also sends is dropped, so nothing is said twice. |
| `approve_mcps` | `False` | `--approve-mcps`: every MCP server the workspace names, approved. |
| `add_dirs` | `()` | `--add-dir`, once apiece: more workspace roots. |

**The effort and tier are written into the model id.** `cursor-agent models` lists `gpt-5.2`,
`gpt-5.2-low`, `gpt-5.2-high` and `gpt-5.2-xhigh` side by side, and `composer-2.5-fast` is that
model on the faster service. So `composer-2.5` at `high` is `composer-2.5-high`, and
`composer-2.5-high-fast` at the `fast` tier. A name that already carries a rung is used as it
stands.

- The id is checked against [what the account last listed](/features/backends): `gpt-5.2` at
  `medium` is refused, naming the three it does list. A model with no rung forms, such as
  `composer-2.5`, `auto` or `gemini-3.1-pro`, is offered at no effort. An account never asked
  refuses nothing.
- No bracket syntax is built: a signed-in account answers `Cannot use this model` to
  `gpt-5.2[effort=low]`. A model you write with brackets is passed as written.
- The separately distributed `cursor-agent-local` runtime, pointed at an OpenAI-compatible
  endpoint with `CURSOR_LOCAL_AGENT_BASE_URL`, `CURSOR_LOCAL_AGENT_API_KEY` and
  `CURSOR_ENABLE_AUTHLESS=1`, takes the id it serves. A turn under an hmz provider runs without
  `CURSOR_LOCAL_AGENT_API_KEY` unless the provider sets it; the endpoint and the authless
  switch are left alone.

### DeepSeek Harness

`dsh`. Driven through its Python SDK, the `[dsh]` [extra](/user/installation); there is no CLI
to install. humanize supports `deepseek-harness-sdk>=0.1.1rc1,<0.1.2`, a developer preview;
0.1.2a3 changed the configuration this driver is written against.

```python
from hmz.coganchor.agents import DshAgent, DshAgentConfig

agent = DshAgent(DshAgentConfig(model="deepseek-v4-flash", effort="high"))
```

It also offers `deepseek-v4-pro`. Leave `provider` empty to use the credentials and base URL
dsh saved (or its environment), or make a `key` account at `/providers`, or a `gateway` account
where the key belongs to somebody's endpoint.

Every session starts from the composition the SDK applies when given none (the installed
runtime's `runtime/cordis.yml`). humanize writes the effort onto it, and:

| Field | Default | |
| --- | --- | --- |
| `compaction` | `True` | Mounts `dsh-token-meter` and `dsh-compaction-basic`, compacting at 0.8 of the context window. Without it, a long conversation reaches a turn the model refuses for length, and every later turn is the same refusal. `False` is the SDK's own composition. |
| `session_compression` | `"none"` | How the session JSONL log is written: `none` or `zstd`. humanize reads that log for what a turn spent; under `zstd` it counts nothing from it. |

`goals` is read here too: it mounts the goal service, the `create_goal` tool and the round
driver. All three are read again every turn, so a reconfigured agent gets a runtime built the
new way and keeps its conversation. A turn that fails without taking its runtime down leaves it
up.

- Its `Unrecoverable` failures are the length refusal and a session id the runtime will not
  answer under.
- It takes only `bypass` or no rung; see [What an agent may do](#what-an-agent-may-do).
- `interject` is unsupported: the SDK's `session/prompt` queues a turn behind the running one,
  and the runtime's `steer` is not on the SDK's JSON-RPC surface.

### Grok Build

`grok`. Ordinary turns are `session/prompt` on a held-open `grok agent stdio`. That transport
takes a model, an effort, an approval, an agent profile, a plugin directory and the leader, and
nothing else. So a rung that takes tools away, `web_search=False`, a shaped turn, a fork, and
any field below except `leader` set away from its default send the turn to
`grok -p --output-format streaming-json`, resuming the same conversation. The session id is
Grok Build's own on both transports.

| Field | Default | |
| --- | --- | --- |
| `leader` | `False` | `False` starts a process for this conversation; `True` joins the backend shared by every client that asks; `None` leaves it to `[cli] use_leader` in your `config.toml`. |
| `sandbox` | `""` | The `--sandbox` profile a turn is confined by, by name. |
| `max_turns` | `0` | `--max-turns`; `0` is uncapped. Not the same as a [budget](#cutting-a-turn-off-and-what-one-turn-may-spend). |
| `subagents` | `True` | `False` is `--no-subagents`. |
| `rules` | `""` | `--rules`, appended to Grok Build's own system prompt. |

Every field but `leader` defaults to the flag not written at all. `leader` defaults to `False`
so that a `use_leader = true` in your config cannot put every session of a flow on one process.

- On the command line the prompt is one argument, `--single=…`. Linux caps one argument at 32
  pages, which leaves 131062 bytes of prompt (about 32 thousand tokens); a longer prompt raises
  before the process starts.
- `--include-partial-messages`, `--agent-profile` and `--plugin-dir` are not fields: the first
  only affects an output format these turns do not use, and the other two exist only on
  `grok agent`, so shaped, forked and tool-withheld turns would silently lose them.

### Kimi Code {#the-daemon-kimi-is-driven-through}

`kimi`. Turns go to a `kimi web` daemon of its own, one per agent, rather than to
`kimi -p --output-format stream-json`: only the daemon has a route into a running turn, a
per-turn body for the rung, thinking level and swarm width, and questions with ids. It needs
the `[kimi]` [extra](/user/installation) for the notification client.

| Field | Default here | `kimi web`'s own | |
| --- | --- | --- | --- |
| `port` | `0` | `58627` | A flow with two Kimi agents starts two daemons, so the system picks a free port. |
| `open_browser` | `False` | opens one | `True` is for watching a flow work: the web UI is a client of the same session. |
| `log_level` | `error` | `silent` | At `silent` the daemon prints a banner instead of the `Kimi server: <url>/#token=<token>` line humanize reads its port and token from. `silent` is refused. |
| `web_title` | `None` | `<workspace dir> \| Kimi Code` | `None` is the CLI's own. Useful when several agents' tabs are open side by side. |

`--add-dir`, `--skills-dir`, `--agent` and `--agent-file` are top-level `kimi` options that
`kimi web` accepts and ignores, so they are not offered. A flow's skills reach the session
through the directories Kimi discovers.

How a turn is followed:

- The daemon's WebSocket notifications wake the driver's REST polling; the driver answers the
  daemon's heartbeat so long turns keep receiving them. Without notifications it polls every
  second.
- Spending comes off the `turn.step.completed` notifications (`inputOther`, `output`,
  `inputCacheRead`, `inputCacheCreation`, mapped kind for kind), because Kimi 0.42.0's session
  route reports usage as zeros. The larger of the steps' sum and the session aggregate wins,
  kind by kind.
- Pending questions are read with `status=pending`, and without the filter where a daemon
  refuses it. A daemon that refuses both for a whole recovery interval fails the turn.
- A turn is over when the session has been seen to stop twice, a wait apart, after it was seen
  to start.
- Session settings are set once rather than before every turn. A goal is set going each time it
  is asked for.

### pi

`pi`. One `pi --mode rpc` held open for the session. It is started with `--session-id`
(`--continue` would resume whichever session in the directory is newest), `--thinking` for the
effort, and `--exclude-tools` at `read-only`.

| Field | Default | |
| --- | --- | --- |
| `compiled` | `True` | Point `NODE_COMPILE_CACHE` at humanize's home (`compiled/pi`), so sessions after the first read pi's compiled bundle back. A value already set is left alone, and an anchored turn gets none. `False` leaves the variable as found. |
| `context_files` | `True` | Discover `AGENTS.md` and `CLAUDE.md`. `False` is `--no-context-files`. |
| `extensions` | `True` | Load the extensions installed here. `False` is `--no-extensions`. |
| `offline` | `False` | `--offline`: its startup network work switched off. |
| `append_system_prompt` | `()` | `--append-system-prompt`, once per entry: text, or a file by path. |
| `skill_paths` | `()` | `--skill`, once per entry: a skill file or directory. Not gated by project trust. |

pi has no permission gate and no sandbox: `--no-approve` is a project-trust guard, and a turn
under it still runs `bash`. See [What an agent may do](#what-an-agent-may-do).

### Qwen Code

`qwen`. Ordinary turns in one session reuse the CLI process through its stream-json input.
Changing its settings, native skills or flow skills restarts it and resumes the conversation.
Shaped turns use a separate command, because Qwen refuses `--json-schema` with stream-json
input; anchored turns end their process so the workspace is synchronised.

| Field | Default | |
| --- | --- | --- |
| `headless_defaults` | `True` | Write Qwen's lowest settings layer (the system defaults, which it reads under yours) with `general.preventSystemSleep: false` and `general.enableAutoUpdate: false`. Nobody is watching a terminal, and an update mid-flow would put a new CLI under a running conversation. Set either yourself, at any layer, and yours wins. `False` writes no layer. |
| `compile_cache` | `True` | Keep Node's compiled bundle under humanize's home (`compiled/qwen`) through `NODE_COMPILE_CACHE`. A value already set is left alone, and an anchored turn gets none. |
| `partial_messages` | `False` | `--include-partial-messages`: words arrive as they are written. |

- **The effort has no flag.** A turn is pointed at a settings file of humanize's own through
  `QWEN_CODE_SYSTEM_SETTINGS_PATH`, one per effort, shared by concurrent sessions at that
  effort. Both generated files carry the settings format version, so Qwen does not rewrite
  them. They are excluded from the restart check; a `QWEN_CODE_SYSTEM_DEFAULTS_PATH` you name
  is watched like any settings file. Settings the driver cannot read, such as JSON with
  comments, keep a fresh process per turn.
- **It names its conversation up front**: the opening turn is given `--session-id` with a fresh
  UUID, and a fork resumes its parent with `--fork-session`. Qwen refuses an id already used in
  the project, so a failed opening turn is retried under a new one.
- **Usage** counts each assistant message once. The terminal summary includes earlier requests,
  so only fields missing from the messages use its increment.

### opencode and mimocode {#what-opencode-and-mimocode-add-to-a-bare-run}

`opencode` and `mimo`. A turn is one `opencode run` (or `mimo run`, the same program under
another name) with `--format json` and `--dir` for the session's directory; neither can be
turned off.

| Field | Default | |
| --- | --- | --- |
| `cli_agent` | `""` | `--agent NAME`: run the turn as one of the CLI's own agents. |
| `thinking` | `False` | `--thinking`: the reasoning streamed as `reasoning` events. The reasoning tokens are counted either way. |
| `pure` | `False` | `--pure`: run without the plugins installed around the CLI. |
| `unattended` | `None` | `--auto` (opencode) or `--dangerously-skip-permissions` (mimo). `None`: on where a rung is named, off where none is. |
| `permission_table` | `None` | `OPENCODE_PERMISSION` / `MIMOCODE_PERMISSION`, carrying the rung and the web answer. `None`: written where there is a rung or a web answer, absent otherwise. `False` is refused beside a rung that withholds anything, or beside `web_search=False`. |

```python
from hmz.coganchor.agents import OpencodeAgent, OpencodeAgentConfig

agent = OpencodeAgent(
    OpencodeAgentConfig(model="opencode/big-pickle", effort="high", cli_agent="plan", thinking=True)
)
```

The table is written for the turn, never into your settings file.

### ZCode

`zcode`. Every turn is a session on `zcode app-server --stdio`, one server per agent.

| Field | Default | |
| --- | --- | --- |
| `titles` | `True` | Whether `session/create` asks ZCode to title the session, which is a model request of its own. Turn it off for a run that reads no title. |
| `native_search` | `True` | What the server is told about ZCode's own file search. Off takes `find` and `grep` away. The server asks once per agent. |
| `delivery` | `desktop-continuous` | The delivery kind a session's stream is subscribed under. `web-remote-replayable` replays for a client that missed some. |
| `protocol` | `openai-compatible` | The protocol a gateway account's endpoint speaks: `anthropic`, `openai` or `openai-compatible`. Read only for an account that names an endpoint. |

Each default is what ZCode 0.16.5 does for a client that says nothing.

**Which provider a turn runs on.** ZCode resolves providers from `~/.zcode/cli/config.json`,
which humanize never writes. An agent on a `gateway` [account](#which-account-it-runs-as) hands
ZCode that account on the session instead (`session/create`, `session/resume` and the two
settling calls), held only as long as the server runs. An agent on no such account runs on
whatever that file says.

On a gateway account the model is `gw/<what the gateway calls it>`, and the catalogue lists the
endpoint's ids that way:

```sh
hmz exec -f ralph_loop -a 'agent=zcode@work/gw/vendor/some-model:high' -b cost=5 "…"
```

The first segment is the name the session declares the endpoint under, and `gw` is the one the
catalogue uses; `vendor/some-model` is sent to the endpoint as it stands.

### A CLI of your own

Any coding agent that speaks the [Agent Client Protocol](https://agentclientprotocol.com) can
be driven without humanize knowing anything else about it. Add one at `/providers`: press
<kbd>a</kbd>, then pick *a CLI of your own*, the last row of the backends list, and give the
command that starts it, such as `my-agent --acp` or `gemini --experimental-acp`. It is written
down under humanize's home, and is a backend from the next prompt on, in every workspace:
`-a my-agent/...` names it.

- It is called what it runs: `my-agent --acp` and `/opt/my-agent/bin/my-agent acp` are both
  added as `my-agent`. A name that is not the command's is refused, naming the one to use.
- A CLI humanize already drives cannot be added under any name. `qwen` speaks ACP and is
  `qwen`.

humanize spawns the command and speaks JSON-RPC over its stdin and stdout: `session/new` opens
a conversation, `session/prompt` takes each turn, and `session/update` notifications carry what
the agent says. It picks a conversation back up with `session/resume` or `session/load`,
whichever the agent offers at the handshake, forks with `session/fork`, and cancels a turn with
`session/cancel`.

- It sends no model, effort or mode (`session/set_model`, `session/set_config_option`,
  `session/set_mode`): model and effort both read `as configured`, and the agent runs as it was
  set up.
- Every tool call it asks permission for is granted, by the **kind** of option offered rather
  than its id. So it runs at `bypass` or no rung, which come to the same thing; a tighter rung
  is refused.
- It cannot be steered, has no goal, reports no usage, and has no logs for a trace.

Of what a client may offer the agent, humanize offers nothing unasked. Each is a field of
`AcpAgentConfig`, off by default:

```python
from hmz.coganchor.agents import AcpAgent, AcpAgentConfig, McpServer

agent = AcpAgent(
    AcpAgentConfig(
        cli="my-agent",
        command=("my-agent", "--acp"),
        model="as configured",
        effort="as configured",
        reads_files=True,   # `acp:read`, served from this machine
        writes_files=True,  # `acp:write`
        terminals=True,     # `acp:terminal`: a command started, read, waited for, killed
        mcp_servers=(McpServer(name="tools", command="serve-me"),),  # `acp:mcp`
    )
)
```

`cli` is the name it was added under and `command` overrides how it starts. The MCP servers are
added to whatever the CLI already has, and started by the agent, so for an agent whose turns
land [elsewhere](#where-the-turns-land) they are named on that machine. The first three are
refused for an agent reached through an anchor that drives the target's own CLI, since what
this client reads and runs is this machine.

## Reaching into a bundled CLI

Claude Code and opencode each ship as one [Bun](https://bun.sh) standalone executable: the
whole CLI, minified and packed behind a `---- Bun! ----` trailer. Where no shallower way
reaches something they do, `hmz.coganchor.agents.patching` rewrites a copy of that bundle. It
reaches these two backends and no other: native binaries carry no bundle, and Node scripts are
reached by [preload](#what-the-runtime-says-the-turn-did) instead. No capability names it, and
whether a patch applies is decided by the bytes installed on this machine.

```python
from pathlib import Path

from hmz.coganchor.agents.patching import Patch, patched
from hmz.coganchor.backends import named, program

claude, where = named("claude"), program("claude")
copy = None
if claude is not None and where is not None:
    copy = patched(claude, Path(where), [Patch(find=b"...", into=b"...")])   # or None
```

- **Never the installed binary.** A patch is applied to a copy in a directory of humanize's
  own, run for one session and removed after.
- **Fingerprinted first**, against `Profile.bundles`: a pattern that must pick out one module
  of the bundle, and an optional digest. A pattern survives releases where a literal would stop
  matching. `tests/system/agents/test_patching.py`, under `--run-agents`, checks every
  fingerprint against the installed binary.
- **Falls back on any mismatch or failure**: an unknown bundle, a changed digest, a moved site,
  a copy that will not start. Each returns `None`, is logged, and the run reaches the CLI a
  shallower way.
- **Same length in place.** Every rewrite is the length of what it replaces, and the patched
  module's precompiled bytecode is cleared so the new source runs.

## API summary

```python
type Where = str | os.PathLike[str] | None   # a directory, or None for the one the flow is in

class AgentBase:
    moments: ClassVar[frozenset[Moment]]    # the ones a hook may be hung on here
    pursues: ClassVar[bool]                 # whether pursue() has a goal feature to reach
    service_tiers: ClassVar[tuple[str, ...]]
    rungs: ClassVar[tuple[str, ...]]        # the permission rungs it takes
    counts: ClassVar[frozenset[str]]        # the usage kinds it reports

    id: str                 # what this agent is called
    backend: str            # "claude", "codex", "kimi", "pi", …
    config: AgentConfig
    effort: str             # what its turns run at; settable
    spec: str               # CLI[@ACCOUNT]/MODEL
    opened: list[str]       # the backend's id for every session it ever opened
    sessions: list[SessionBase]
    stopped: bool
    anchor: AnchorConfig | None
    provider: Provider | None
    hooks: Hooks            # what is hung on its moments
    loaded: tuple[Loaded, ...]
    allowance: Ledger | None

    def __call__(prompt: str, *, suppress: bool = False, schema: type[T] = …, cwd: Where = None) -> str | T | None
    def pursue(objective: str, *, suppress: bool = False, cwd: Where = None) -> str
    def new(cwd: Where = None) -> SessionBase

    async def aturn(prompt: str, *, suppress: bool = False, schema: type[T] = …, cwd: Where = None) -> str | T | None
    async def apursue(objective: str, *, suppress: bool = False, cwd: Where = None) -> str

    def batch_new(count: int, cwd: Where = None) -> list[SessionBase]
    def batch(prompts, *, suppress: bool = False, schema: type[T] = …, at_once: int = 0, cwd: Where = None) -> list[...]
    async def abatch(prompts, *, suppress: bool = False, schema: type[T] = …, at_once: int = 0, cwd: Where = None) -> list[...]

    def spent() -> Usage
    def rate(over: float = WINDOW) -> Usage
    def juice(over: float = WINDOW) -> float

    def clone(*, config: AgentConfig | None = None, name: str | None = None, skills: Iterable[Loaded] | None = None) -> Self
    def reconfigure(config: AgentConfig) -> None
    def runs_on(machine: MachineConfig | None) -> None
    def loads(skills: Iterable[Loaded]) -> None
    def rename(name: str) -> None
    def disable_goals() -> None
    def stop() -> None
    def watch(listener: Callable[[AgentBase, SessionBase | None, Event], None]) -> None
    def asked(question: Question) -> str | None
    def prompted() -> str | None
    def stands_in() -> AgentBase | None
    def node() -> Provider
    def walks() -> tuple[Provider, ...]
    def environment() -> Mapping[str, str]

    ask: Callable[[Question], str | None] | None
    waiting: Callable[[], list[str]] | None
    prompting: Callable[[], str | None] | None

class SessionBase:
    shapes: ClassVar[bool]           # held to a schema by the CLI
    steers: ClassVar[bool]           # interject reaches a running turn
    takes_tools: ClassVar[bool]      # offers() works
    narrates: ClassVar[bool]         # a reach can be said as it happens
    forks_elsewhere: ClassVar[bool]  # fork(cwd=) may name another directory
    cuts_transport: ClassVar[bool]   # cut() puts a shared transport down

    id: str                 # raises until a turn has landed
    named: str | None       # the same, or None
    cwd: str                # where this conversation works, as the machine it lands on names it
    forks: bool             # whether the backend can fork this conversation
    effort: str             # settable; "" for the agent's
    budget: Budget | None   # settable; what each of its turns may spend
    skills: tuple[str, ...]
    tools: tuple[Tool, ...]

    def __call__(prompt: str, *, suppress: bool = False, schema: type[T] = …) -> str | T | None
    def stream(prompt: str, *, schema: type[BaseModel] | None = None) -> Iterator[Event]
    def pursue(objective: str, *, suppress: bool = False) -> str
    def fork(*, into: AgentBase | None = None, cwd: Where = None) -> SessionBase

    async def aturn(prompt: str, *, suppress: bool = False, schema: type[T] = …) -> str | T | None
    async def apursue(objective: str, *, suppress: bool = False) -> str

    def interject(text: str) -> None
    def interrupt(*, why: str) -> None  # end the running turn, wherever it has got to
    def cut(*, why: str) -> None        # the same, and a shared transport put down too
    def loads(skills: Iterable[str] | None) -> None
    def offers(tools: Iterable[Tool] | None) -> None
    def spent() -> Usage
    def rate(over: float = WINDOW) -> Usage
    def juice(over: float = WINDOW) -> float
    def close() -> None

@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    model: str
    effort: str
    service_tier: str = "default"
    machine: MachineConfig | None = None
    permission: str = ""
    provider: str = ""
    goals: bool = True
    web_search: bool | None = None
    budget: Budget | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Budget:
    output: float = 0.0            # output tokens one turn may write, 0 for no cap
    seconds: float = 0.0           # how long one turn may run, 0 for no cap
    when: str = "next-response"    # next-response | immediately
    then: str = "end"              # end | fail

    bounded: bool                  # whether it caps anything at all
    def over(*, output: float = 0.0, seconds: float = 0.0) -> str

@dataclass(frozen=True, slots=True)
class Event:
    kind: str               # text | reasoning | tool | subagent | subagent-ends | took | result
                            # | failed, and to a watcher also: begins | ends | asks | notice
    text: str
    whose: str = ""         # the backend's id for a subagent, pairing its start and end
    tokens: Mapping[str, int] = {}   # on a result: tokens per model
    spent: Usage = Usage()           # on a result: tokens per kind

@dataclass(frozen=True, slots=True)
class Question:
    text: str
    options: tuple[str, ...] = ()

class Failed(subprocess.CalledProcessError):
    fault: str              # the kind of failure, or ""
    fix: str                # what to do about it, or ""

class Unrecoverable(Failed): ...
class Stopped(Exception): ...
class Unserved(ValueError): ...   # a setting this backend cannot carry

class Hooks:
    moments: frozenset[Moment]

    def on(moment: Moment, hook: Hook, *, tool: str = "") -> Hung
    def off(hung: Hung) -> None
    def hooked(moment: Moment) -> bool
    def fire(occasion: Occasion) -> Verdict

class Hung:                 # what `on` answers with, and a context manager
    def off() -> None

@dataclass(frozen=True, slots=True)
class Occasion:
    moment: Moment
    agent: str
    session: str = ""
    prompt: str = ""
    tool: str = ""
    about: str = ""
    under: str = ""         # the backend's id for a subagent
    input: Mapping[str, Any] = {}
    said: str = ""
    again: int = 0

@dataclass(frozen=True, slots=True)
class Verdict:
    refused: bool = False
    because: str = ""
    adds: str = ""

class Unhooked(ValueError): ...   # a moment this backend does not run
```

`CommandSessionBase` and `StreamSessionBase` are the two shapes a backend is driven in: one
command per turn, or one long-lived process spoken to a line at a time. Subclass them to add a
backend; `specs/coganchor/agents.md` is the contract they keep.
