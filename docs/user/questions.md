# Questions

An agent can stop in the middle of a turn to ask you something, and a flow can ask you
directly. Either way the question appears in the transcript, and the next line you type is the
answer.

## Try it

Start the interface, which opens on [`chat`](/flows/chat) with one agent, and ask for a
question:

```sh
hmz
```

```text{3-4}
❯ Before you change anything, ask me whether to keep the old API.

● Should I keep the /v1 endpoints working beside /v2?
   type an answer, or /afk to stop being asked

────────────────────────────────────────────────────────────────────────────────
❯ yes, until the next release
────────────────────────────────────────────────────────────────────────────────
  enter answer · / commands · shift+enter newline · esc monitor · ctrl+c clear
```

The `●` line, yellow on screen, is the agent's question. While it is up, the status line
offers <kbd>enter</kbd> **answer**: what you type goes back as the answer rather than into the
turn.

## Answering

- **Any answer goes.** If the agent offered choices, they are listed with the question, but you
  can type something else.
- **Nothing times out.** The agent waits for as long as you take.
- **Stopping wins.** A question still up when the flow ends or is stopped ends with it.

## Which agents ask

An agent asks only if its CLI can, and only if the flow passes its questions on to you. `chat`
passes every one on.

| `claude` | `codex` | `kimi` | `pi` | `zcode` | every other |
| --- | --- | --- | --- | --- | --- |
| <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="tip" text="asks" /> | <Badge type="info" text="never stops to ask" /> |

A flow may also answer an agent's question itself, without asking you. When it does neither,
the agent is told nobody answered, and carries on.

## When the flow asks you

A flow can put a question to you directly. `chat` does it after every answer, by waiting for
what you say next. A flow that needs several answers asks for them one at a time:

```text
● Which way should this be built?
      · fast
      · careful
   type an answer, or /afk to stop being asked
```

| The question reads | Type |
| --- | --- |
| a list of choices under it | one of them |
| `yes` and `no` under it | `yes` or `no` |
| `(a number)` | a number |
| `(several, separated by commas)` | a list on one line: `api, cli, docs` |
| ``-- or `-` for 3`` | `-` to keep the flow's default |

If an answer is not one the flow can take, the question comes back with what was wrong.

## When nobody is there

`/afk on` tells humanize you are away, and the status line starts with `afk` until you turn it
off. `hmz exec` always runs this way, since nobody is at a prompt.

| | While you are away |
| --- | --- |
| An agent's question | shown, and the agent is told nobody answered; it carries on |
| A flow's question | answered with nothing, or with the flow's defaults; `chat` ends there |
| A flow's question that has no default | the flow fails with `nobody is there to answer …`, unless it handles that |
| A question already up | answered by nobody, at once |

Under `hmz exec`, an agent's question is still printed, in yellow, and with `--json` it is an
object of kind `asks`, so a script can count them. See [Being away](/user/afk).

## See also

- [Being away](/user/afk): the `/afk` switch
- [Side questions](/user/btw): asking an agent something without stopping it
- [The person as an agent](/weaver/human-agent): how a flow asks you, for whoever writes one
