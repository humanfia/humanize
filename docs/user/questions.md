# Questions

An agent can stop in the middle of a turn to ask you something, and a flow can ask you
directly. Either way the question appears in the transcript. A question asking for text is
answered by the next line you type; a flow's form is answered by filling it in, at the prompt
or in the browser. Use this page to answer a question, to know what happens to one when nobody
is there, and to count them from a script.

## Try it

Start the interface, which opens on a [chat](/user/chat) with one agent, and ask for a
question:

```sh
hmz
```

```text
❯ Before you do anything else, use your question tool to ask me whether to keep the old /v1 API
beside /v2, offering the choices keep and drop. Then reply with one sentence.
```

The agent stops, the question comes up in yellow with the choices it offered, and whatever you
type next is the answer.

## Before you start

- A coding agent CLI that can stop to ask: Claude Code, Codex, Kimi Code, pi or Oh My Pi. See
  [Which agents ask](#which-agents-ask).
- A flow that passes its agents' questions on to you, or a [chat](/user/chat), which `hmz`
  opens on and which puts every one to you.

## Two kinds of question

- **An agent's question** comes from the coding agent itself, part-way through a turn: its CLI
  has a tool for asking its user something. The turn waits for your answer, then carries on
  with it.
- **A flow's question** comes from the flow, between turns: a flow that needs a decision from
  you asks for it, as a line of text or as one form, often with something to read with it, a
  diff or a table. The flow waits, then goes on with what you said.

A chat has no flow, so it has no second kind: after every answer it waits for your next
message, and whatever you type, a follow-up or a steer, is that message. Its wait is never
drawn as a question. The agent's own questions show in the conversation, with the choices it
offered, and your next line answers them.

Both are shown the same way, a `●` line in yellow. One asking for text has
`type an answer, or /afk to stop being asked` under it: type a line and press <kbd>enter</kbd>.
One asking for a form has `form · <n> fields — press enter to open` under it instead.
Nothing times out. In a flow, a question is put to **you** as the flow's `human` role, its
[outworlder](/user/concepts), which is why its own transcript is headed `outworlder human`. A
chat has no outworlder: its questions are put to you in its conversation.

## Example: answer an agent's question at the prompt

Type the line from [Try it](#try-it) into `hmz`, with Claude Code as the agent. The turn
stops on the question:

```text
── assistant

● assistant is working

● Should the old /v1 API be kept alongside the new /v2, or should it be dropped entirely?   ①
● Should the old /v1 API be kept alongside the new /v2, or should it be dropped entirely? (Keep /v1 / Drop /v1)   ②
   type an answer, or /afk to stop being asked                                              ③

                                    assistant · claude/claude-haiku-4-5-20251001:low · ● 1   ④
                                    input 20 · output 620 · cache_read 27.7k · cache_write 13.9k
                                                                           $0.02 · 118 out/s
─────────────────────────────────────────────────────────────────────────────────────────────
❯ keep, until the next release                                                              ⑤
─────────────────────────────────────────────────────────────────────────────────────────────
  ·\· running… (9s)                                       enter answer · / commands · …   ⑥
```

Press <kbd>enter</kbd>, and the same turn goes on with your answer:

```text
❯ keep, until the next release

● I'll keep both /v1 and /v2 APIs available until the next release, then deprecate /v1.   ⑦

✻ Worked for 14s · assistant                                                               ⑧
```

### What each part means

1. **The question in the agent's own words**, where the agent asked it.
2. **The same question put to you**, in the same conversation. The choices the agent offered
   follow it in brackets. They are suggestions: type one, or anything else.
3. **`type an answer, or /afk to stop being asked`** marks a question that is waiting.
4. **The agent line**, `●` while its turn is open, waiting on your answer. In a flow, an
   outworlder line under it, `human · outworlder · asking`, says a question is up even when
   it has scrolled out of sight; a chat has none.
5. **Your answer**, typed at the prompt like any other line.
6. **`enter answer`** on the status line says what <kbd>enter</kbd> will do: it answers
   the question rather than steering the turn. On a narrow terminal the status line drops its
   leftmost keys first, so this one may not be shown.
7. **The turn carries on** with your answer, in the same session.
8. **The chat waiting for your next message**: nothing more is shown. Type the next thing to
   say, and it is the next turn. Or leave it for as long as you like.

## Example: a flow's form

A flow that needs a decision from you asks for it as one form: every field at once, with what
it suggests already picked. At the prompt, the question comes up with what to read under it,
and a line to open the form:

```text
● How should I do this: add a subtract function to calc.py?                     ①
  ▾ The change · +12 −3 in 2 files                                              ②
    calc.py
    + def subtract(a, b):
    +     return a - b
  ▸ Checks · table · 1 row
  form · 2 fields — press enter to open                                         ③
```

Press <kbd>enter</kbd>, and the form opens as a sheet over the transcript:

```text
 How should I do this: add a subtract function to calc.py?

 Which way should this be built?    fast   [ careful · suggested ]              ④
 Write tests for it?                [ Yes, write tests · suggested ]   No tests

                                                       enter submit · esc later  ⑤
```

These two are drawn after the interface, not recorded.

### What each part means

1. **The prompt**, the headline of the question.
2. **What the flow handed you to read**: a diff, a table, text, code. Each long one is folded
   behind a line that sums it up, and the first is open. An image or a chart is a line saying
   it is in the web page.
3. **The form waiting.** It does not open by itself, so a question coming up never takes the
   line you are typing.
4. **One row per field.** A few choices are laid out side by side and a yes or no is two
   words, never a box to tick. What the flow suggests is already picked and marked
   `suggested`, so if you agree, <kbd>enter</kbd> is all it takes.
5. **The keys**, at the foot of the sheet. Closing it leaves the question up, to open again.

An answer that does not fit, a word where a number goes, is not sent on: what is wrong is said
under the field, and the sheet stays open with what you typed, until it fits.

| A field that is | Is |
| --- | --- |
| one of a few words | those words, side by side; one of many: a list to search |
| yes or no | two buttons, worded from the question |
| a number | a number field |
| text | a text field |
| a list | one row per item, to add to and remove from |
| given a default | already filled in, and marked `suggested` |

A question asking for text has no form: type a line and press <kbd>enter</kbd>, as for an
agent's question.

## Example: the same form in the browser {#in-the-browser}

In [the web page](/user/web), the question is one card under the epic's graph, laid out to be
read top to bottom: the prompt, then what to read, then the form, then **Submit**.

- **Few choices, large.** Up to five choices are a row of buttons; more are a list to search.
  <kbd>1</kbd>–<kbd>9</kbd> picks one while you are not typing in a field.
- **The suggested answer, ready.** Defaults are picked and marked `suggested`. Fields with no
  default come first, and those with one fold under **More options (n)**.
- **What is left, on the button.** **Submit** says what is still needed, `2 required left`,
  until nothing is. <kbd>⌘</kbd>/<kbd>Ctrl</kbd>+<kbd>Enter</kbd> submits from anywhere in
  the card.
- **Errors where you look.** A field is checked when you leave it and when you submit, never
  while you type. What does not fit is said beside the field, and the cursor goes to the first.
- **Nothing lost.** What you have typed is kept in this browser until you send it, so a reload
  brings it back. A question that goes away says why: `went away` when it was answered as
  nobody, `the run ended` when the run did.
- **A closing line.** Once sent, the card folds to one line of what you answered:
  `You answered: approve · 'LGTM'`.
- **Somebody else's.** A question another window holds is shown, but not to be answered:
  `Waiting for <name>`.

A flow may bring a [face](/weaver/faces) of its own for a question: a page made for that one
decision, a review of a diff file by file, say. It sits in the card where the form would be.
**Plain form**, above it, swaps it for the form at any time, and back. A face that fails to
load is replaced by the form by itself. At the prompt in a terminal there is no face: the
question says the web page has a richer view, and its form is the one shown here.

What a flow shows you without asking, its progress, a result, a chart, goes into the asking
outworlder's own transcript, in the terminal and in the browser alike.

## Example: the same question under `hmz exec`

Under `hmz exec` nobody is at a prompt, so every question is answered by nobody. Run the same
task:

```sh
hmz chat -a claude/claude-haiku-4-5-20251001:low \
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

Under `hmz exec`, with `--json`, the question is an object of kind `asks`, so a script can
count them:

```sh
hmz exec -f goal -a worker=claude/claude-haiku-4-5-20251001:low -p budget.cost=1 --json "…" \
    | jq -c 'select(.kind == "asks")'
```

```json
{"at":1790746636.0548427,"agent":"worker","cli":"claude","model":"claude-haiku-4-5-20251001","session":"","kind":"asks","text":"Should we keep the old /v1 API alongside /v2, or deprecate it completely?","whose":"","tokens":{},"spent":{}}
```

### What each part means

1. **The question is still printed**, in yellow, so a log shows what the agent wanted to know.
2. **The agent is told nobody answered**, and carries on as best it can: here it wrote the
   question into its answer instead. The `hmz chat` above then ends its chat, since nobody is
   there to send a next message, and exits `0`.

## Check that it worked

- At the prompt, the `●` question and its `type an answer` line are followed by your line, and
  the agent's next words take your answer into account.
- In a flow, `human · outworlder · asking` is gone from the agent lines once nothing is waiting.
- Under `hmz exec --json`, count the `asks` objects to see how often a run wanted you.

## Answering, in detail

- **Where you answer.** A question is shown on whichever transcript you are reading and on the
  asking outworlder's own, which <kbd>shift+tab</kbd> reaches and which holds nothing but what
  it asks you. A line typed on either answers it: the oldest question up on the first, the
  oldest that outworlder asks on the second. One the agent stopped mid-turn to ask, and every
  question in a [chat](/user/chat), are shown and answered in that agent's conversation instead. On one
  agent's transcript any other line goes to the agent. See [Many conversations at once](/user/conversations).
- **Somebody else's.** Where [another interface](/features/daemon#several-people-on-one-run)
  reads the same run, a question nobody has claimed goes to whoever answers first, and an
  answer from somebody else shows ` · by <name>`. One whose outworlder another has claimed
  with `/claim` says `<name>'s to answer` under it, and is not yours to answer.
- **Stopping wins.** A question still up when the flow ends or is stopped ends with it.

## Which agents ask

An agent asks only if its CLI can, and only if the flow passes its questions on to you. A chat
puts every one to you.

| `claude` | `codex` | `kimi` | `pi` | `omp` | every other |
| --- | --- | --- | --- | --- | --- |
| <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="info" text="never stops to ask" /> |

A flow may also answer an agent's question itself, without asking you. When it does neither,
the agent is told nobody answered, and carries on.

## Variations

### Being away: `/afk` {#when-nobody-is-there}

`/afk on` tells Humanize you are away, and the status line starts with `afk` until you turn it
off with `/afk off`. On an outworlder's own transcript it says so for that outworlder alone.
`hmz exec` always runs this way, since nobody is at a prompt.

```text
❯ /afk on
away: agents that ask are told nobody is here
```

`/afk` is about a flow's outworlders. A chat has none, so being away changes nothing in one:
it waits for your next message for as long as you leave it, and
[folds away](/user/chat#leaving-and-carrying-on) if nobody reads it.

| | While you are away |
| --- | --- |
| An agent's question | shown, and the agent is told nobody answered; it carries on |
| A flow's question | answered with nothing, or with the flow's defaults |
| What a flow shows you | not shown, and the flow is not held up |
| A flow's question that has no default | the flow fails with `nobody is there to answer …`, unless it handles that |
| A question already up | answered by nobody, at once, and its card says `went away` |

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
- **`the answer does not fit: …`.** Something in the form is not what the flow takes. The
  field it names says why; fix it and send again.
- **A form in the browser shows no face.** The face failed to load, or you pressed **Plain
  form**. The form asks the very same thing.
- **Your agent never asks.** Its CLI cannot, or the flow does not pass its questions on. Use
  one of the five CLIs above in a [chat](/user/chat).

## Next steps

- [Being away](/user/afk): the `/afk` switch
- [Side questions](/user/btw): asking an agent something without stopping it
- [Run it unattended](/user/unattended): questions under `hmz exec`
- [The person as an agent](/weaver/human-agent): how a flow asks you, for whoever writes one
- [A face for the person](/weaver/faces): a flow's own page for a question
- [TUI reference](/reference/tui): every key and command at the prompt
