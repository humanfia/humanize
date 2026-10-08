# Questions

An agent can stop in the middle of a turn to ask you something, and a flow can ask you
directly. Either way the question appears in the transcript, and the next line you type is the
answer. Use this page to answer a question at the prompt, to know what happens to one when
nobody is there, and to count them from a script.

## Try it

Start the interface, which opens on [`chat`](https://humanfia.ai/flows/chat) with one agent, and ask for a
question:

```sh
hmz
```

```text
❯ Before you do anything else, use your question tool to ask me whether to keep the old /v1 API
beside /v2, offering the choices keep and drop. Then reply with one sentence.
```

The agent stops, the question comes up in yellow, and whatever you type next is the answer.

## Before you start

- A coding agent CLI that can stop to ask: Claude Code, Codex, Kimi Code, pi or Oh My Pi. See
  [Which agents ask](#which-agents-ask).
- A flow that passes its agents' questions on to you. `chat`, the flow `hmz` opens on, passes
  every one on.

## Two kinds of question

- **An agent's question** comes from the coding agent itself, part-way through a turn: its CLI
  has a tool for asking its user something. The turn waits for your answer, then carries on
  with it.
- **A flow's question** comes from the flow, between turns: `chat` asks what to say next after
  every answer, and a flow that needs a setting from you asks for it. The flow waits, then goes
  on with what you said.

Both are shown the same way, a `●` line in yellow with `type an answer, or /afk to stop being
asked` under it, and both are answered the same way: type a line and press <kbd>enter</kbd>.
Nothing times out. A question is put to **you** as the flow's `human` role, its
[outworlder](/user/concepts), which is why the transcript heads it `outworlder human`.

## Example: answer an agent's question at the prompt

Type the line from [Try it](#try-it) into `hmz`, with Claude Code as the agent. The turn
stops on the question:

```text
── assistant

● assistant is working

● Should the old /v1 API be kept alongside the new /v2, or should it be dropped entirely?   ①

── outworlder human

● Should the old /v1 API be kept alongside the new /v2, or should it be dropped entirely? (Keep /v1 / Drop /v1)   ②
   type an answer, or /afk to stop being asked                                              ③

                                        assistant · claude/claude-haiku-4-5-20251001:low · ● 1
                                                           human · outworlder · asking   ④
                                    input 20 · output 620 · cache_read 27.7k · cache_write 13.9k
                                                                           $0.02 · 118 out/s
─────────────────────────────────────────────────────────────────────────────────────────────
❯ keep, until the next release                                                              ⑤
─────────────────────────────────────────────────────────────────────────────────────────────
  ·\· assistant… (9s · ctrl+c twice to stop)    enter answer · shift+tab switch view · / commands · …   ⑥
```

Press <kbd>enter</kbd>, and the same turn goes on with your answer:

```text
❯ keep, until the next release

── assistant

● I'll keep both /v1 and /v2 APIs available until the next release, then deprecate /v1.   ⑦

✻ Worked for 14s · assistant

── outworlder human
   type an answer, or /afk to stop being asked                                              ⑧
```

### What each part means

1. **The question in the agent's own words**, where the agent asked it.
2. **The same question put to you**, under `outworlder human`. The choices the agent offered
   follow it in brackets. They are suggestions: type one, or anything else.
3. **`type an answer, or /afk to stop being asked`** marks a question that is waiting.
4. **`human · outworlder · asking`** on the agent lines above the prompt says a question is up,
   even when it has scrolled out of sight.
5. **Your answer**, typed at the prompt like any other line.
6. **`enter answer`** on the status line says what <kbd>enter</kbd> will do: it answers
   the question rather than steering the turn. On a narrow terminal the status line drops its
   leftmost keys first, so this one may not be shown.
7. **The turn carries on** with your answer, in the same session.
8. **`chat` asking what next**: a flow's question with no words, since the prompt is what asks
   it. Type the next thing to say, or leave it for as long as you like.

## Example: a flow's question with choices

A flow that needs a setting from you asks for it with the choices under it, numbered:

```text
● Which way should this be built?
      1. fast
      2. careful
   type an answer, or /afk to stop being asked
```

Type `careful`, or just `2`. What the question looks like tells you what it takes:

| The question reads | Type |
| --- | --- |
| a list of choices under it | one of them, or its number |
| `yes` and `no` under it | `yes` or `no` |
| `(a number)` | a number |
| `(several, separated by commas)` | a list on one line: `api, cli, docs` |
| ``-- or `-` for 3`` | `-` to keep the flow's default |

If an answer is not one the flow can take, the question comes back with what was wrong, up to
three times.

## Example: the same question under `hmz exec`

Under `hmz exec` nobody is at a prompt, so every question is answered by nobody. Run the same
task:

```sh
hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:low \
    "Before anything else, use your question tool to ask me whether to keep the old /v1 API beside /v2, offering keep and drop. Then reply with one sentence."
```

```text
● assistant is working
● AskUserQuestion()
● Should we keep the old /v1 API alongside /v2, or drop it?                             ①
The error indicates "nobody to ask" - this likely means the user isn't available to answer the question in the current mode. …   ②
● Should we keep the old /v1 API alongside /v2 for backwards compatibility, or drop it entirely?
✻ input 18 · output 332 · cache_read 41.6k · cache_write 271 · $0.0062 · claude-haiku-4-5-20251001 · assistant
✻ Worked for 5s · assistant
```

With `--json`, the question is an object of kind `asks`, so a script can count them:

```sh
hmz exec -f chat -a assistant=claude/claude-haiku-4-5-20251001:low --json "…" \
    | jq -c 'select(.kind == "asks")'
```

```json
{"at":1790746636.0548427,"agent":"assistant","cli":"claude","model":"claude-haiku-4-5-20251001","session":"","kind":"asks","text":"Should we keep the old /v1 API alongside /v2, or deprecate it completely?","whose":"","tokens":{},"spent":{}}
```

### What each part means

1. **The question is still printed**, in yellow, so a log shows what the agent wanted to know.
2. **The agent is told nobody answered**, and carries on as best it can: here it wrote the
   question into its answer instead. `chat` then ends, since nobody is there to say what next.
   The command exits `0`.

## Check that it worked

- At the prompt, the `●` question and its `type an answer` line are followed by your line, and
  the agent's next words take your answer into account.
- `human · outworlder · asking` is gone from the agent lines once nothing is waiting.
- Under `hmz exec --json`, count the `asks` objects to see how often a run wanted you.

## Answering, in detail

- **Where you answer.** A question is shown on the transcript every agent is on and on the
  asking outworlder's own, which <kbd>shift+tab</kbd> reaches and which holds nothing but what
  it asks you. A line typed on either answers it: the oldest question up on the first, the
  oldest that outworlder asks on the second. On one agent's transcript a line goes to the
  agent instead. See [Many conversations at once](/user/conversations).
- **Somebody else's.** Where [another interface](/features/daemon#several-people-on-one-run)
  reads the same run, a question nobody has claimed goes to whoever answers first, and an
  answer from somebody else shows ` · by <name>`. One whose outworlder another has claimed
  with `/claim` says `<name>'s to answer` under it, and is not yours to answer.
- **Stopping wins.** A question still up when the flow ends or is stopped ends with it.

## Which agents ask

An agent asks only if its CLI can, and only if the flow passes its questions on to you. `chat`
passes every one on.

| `claude` | `codex` | `kimi` | `pi` | `omp` | every other |
| --- | --- | --- | --- | --- | --- |
| <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="info" text="never stops to ask" /> |

A flow may also answer an agent's question itself, without asking you. When it does neither,
the agent is told nobody answered, and carries on.

## Variations

### Being away: `/afk` {#when-nobody-is-there}

`/afk on` tells humanize you are away, and the status line starts with `afk` until you turn it
off with `/afk off`. On an outworlder's own transcript it says so for that outworlder alone.
`hmz exec` always runs this way, since nobody is at a prompt.

```text
❯ /afk on
away: agents that ask are told nobody is here
— the flow is done —
```

Here `chat` was waiting for the next thing to say, so being away ended it.

| | While you are away |
| --- | --- |
| An agent's question | shown, and the agent is told nobody answered; it carries on |
| A flow's question | answered with nothing, or with the flow's defaults; `chat` ends there |
| A flow's question that has no default | the flow fails with `nobody is there to answer …`, unless it handles that |
| A question already up | answered by nobody, at once |

See [Being away](/user/afk).

## Pitfalls

- **Your line went to the agent, not the question.** You were on one agent's own transcript,
  where a line is said to that agent. Press <kbd>shift+tab</kbd> back to the view of every
  agent or the outworlder's own, and look for `enter answer` on the status line.
- **`reviewer is bob@tui's to answer, not yours`.** Somebody else has claimed that outworlder.
  See [Troubleshooting](/user/troubleshooting).
- **`already answered by alice@tui`.** Somebody else answered first; their answer is in the
  transcript.
- **A run under `hmz exec` fails with `nobody is there to answer …`.** The flow asked for
  something it has no default for. Pass it with `-p`, or run it at the prompt.
- **Your agent never asks.** Its CLI cannot, or the flow does not pass its questions on. Use
  one of the four CLIs above in `chat`.

## Next steps

- [Being away](/user/afk): the `/afk` switch
- [Side questions](/user/btw): asking an agent something without stopping it
- [Run it unattended](/user/unattended): questions under `hmz exec`
- [The person as an agent](/weaver/human-agent): how a flow asks you, for whoever writes one
- [TUI reference](/reference/tui): every key and command at the prompt
