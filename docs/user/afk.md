# Being away — `/afk`

`/afk` tells humanize that nobody is there to answer. Turn it on for long or unattended runs,
so a question put to you is answered at once instead of waiting for a reply that will not come:
the run's [outworlder](/weaver/human-agent) — you, as the flow sees you — is **away**. A flow
asking you something is answered with nothing, and an agent whose question was put to you is
told **nobody answered** and carries on.

## Try it

At the prompt, type:

```
/afk on
```

## What it is not

`/afk` controls whether you are there to answer a **question**. It does not control whether an
agent may **act**: that is the permission its flow declared, and nothing an agent does is put to
anybody for approval whether you are here or not. See [Security](/user/security) and
[Permissions](/user/permissions).

## At the prompt

```
/afk            flips it
/afk on         you are not here
/afk off        you are
```

Asking starts **allowed**. An agent that really needs a person gets one, unless you have said
that nobody is there.

**You can see which way it is set.** While it is on, the status line under the editor says
`afk`, in the colour of a warning, in front of everything else on that line:

```
afk · ◉ chat · ~/work/api                         / commands · esc monitor · ctrl+c exit
```

The line the switch writes in the transcript has scrolled away by the time an agent wants to
ask you something, and nothing else on the screen changes — so without the marker the first
sign that a question went unanswered would be a run that finished early. It is in front of the
flow and the directory rather than beside them because that is the one part of the row a narrow
terminal cannot push off the end.

While a question is up, the status line shows `enter answer`. The next line you type becomes
the answer, rather than a word in the turn. The agent's offer appears with it, but an answer is
not limited to those options — every backend that offers them also takes something else.

A question still up when the flow ends or is stopped ends with it, so stopping a flow is never
blocked on a question. One still up when you turn `/afk` on is answered by nobody at all, which
the flow hears as `OutworlderAway`.

## On a command line

You do not switch anything. `hmz exec` has nobody at a prompt, so it always behaves as `/afk
on`.

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -b cost=5 "$(cat TASK.md)"
```

This is the whole reason the setting exists. A nine-hour unattended loop that blocked forever
on `Which approach would you prefer?` is a run that did nothing.

The question is still shown, in yellow, so that a run read back afterwards says what the agent
wanted to ask and what it did instead — and it is an `asks` object under
[`--json`](/user/unattended#read-it-with-a-program), for a job that wants to count them.

## From a flow

The flow sees it as `human.away`, on its `Outworlder` role, and an away outworlder answers every
`run` at once: `""` for text, the answer a schema's defaults make where every field has one,
and `OutworlderAway` raised where the schema has a field with no default. A flow that has to
run unattended too asks for shapes whose fields all have defaults, or catches that. See
[The person as an agent](/weaver/human-agent).

Underneath, the question an agent stops to ask reaches the flow's `on_ask_user` hook, which is
what decides whether it is put to you at all. Either way, it also reaches anything
[watching](/reference/agents#watching-a-turn-as-it-happens) the agent, as an `asks` event, so a
run can log what its agent wanted to ask without answering it.

## When to turn it on

- Overnight, or over a weekend.
- Any run started from a script, a cron entry or CI — there it is already the case.
- When you are watching the transcript but do not want to be interrupted. The agent gets on
  with it, and you read what it decided afterwards.

## When to leave it off

- The [`chat`](/flows/chat) flow, where a question is the point.
- A flow that drives [the person as an agent](/weaver/human-agent). That side of it is you, and
  `/afk` makes it answer nothing, which ends the conversation.
- Any flow that asks you for [an answer in a shape](/weaver/shapes). A questionnaire nobody
  filled in comes back as its defaults, or raises `OutworlderAway` where there are none.

## See also

- [Questions](/user/questions) — what an agent asking actually looks like
- [Picking a run up](/user/resuming) — `/resume`, for the run that stopped while you were away
- [The person as an agent](/weaver/human-agent)
- [TUI › Questions, and being away](/reference/tui#questions-and-being-away)
