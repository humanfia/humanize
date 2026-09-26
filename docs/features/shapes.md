---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Answers in a shape

A flow can ask an agent for an answer with named, typed fields instead of a paragraph: `done`
and `notes`, or `approach` and `tests`. The flow then decides on a field, rather than on
whether some phrase turned up in the prose. The shape is written once, in the flow, and the
same shape can be put to a model or to you.

<HmzShape />

## What a shape is good for

Two or three fields usually make a whole decision. Each kind of field does one job in a loop:

| A field that is | Does this in the loop |
| --- | --- |
| **yes or no** | decides: is it finished, does it pass, go round again or stop |
| **one of a few words** | picks a branch, such as `fast` or `careful`, and never a third |
| **text** | carries: a reviewer's notes become the builder's next prompt, word for word |
| **a number** | bounds: how many rounds, how many files |

A shape with thirty fields is a form, and an agent busy filling in a form is not doing the
work.

## When the answer does not fit

An answer that is not in the shape fails the turn, however cleanly the agent finished. The
flow never gets half an answer to act on. It gets a failed turn, and the usual response is to
take that round again.

## The same decision, put to a person

Give [the person at the prompt](/features/human) the same shape and they get one short
question per field: the field's description is the question, `yes` and `no` for a switch, the
words on offer for a choice. Their answers come back as the same fields a model would have
filled in, so the flow reads them the same way.

## Which CLIs hold the shape themselves

Some CLIs take the shape as a setting of their own and keep the model to it. The rest are asked
for it in the prompt, and the answer is checked when it comes back. The flow gets the same
fields either way. The difference is that a model that was only asked is freer to miss, so on
those CLIs a loop's retry does more work.

| | CLIs |
| --- | --- |
| **Held by the CLI** | <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" /> <Badge type="tip" text="agy" /> <Badge type="tip" text="grok" /> <Badge type="tip" text="qwen" /> |
| **Asked in the prompt** | <Badge type="info" text="cursor-agent" /> <Badge type="info" text="dsh" /> <Badge type="info" text="kimi" /> <Badge type="info" text="mimo" /> <Badge type="info" text="opencode" /> <Badge type="info" text="pi" /> <Badge type="info" text="zcode" />, and any CLI you add at [`/providers`](/user/providers) |

## Go further

<div class="hmz-paths by-three">
  <a :href="withBase('/weaver/shapes')">
    <strong>Ask for one</strong>
    <span>Writing the shape in a flow, and the branch for a turn that misses it.</span>
  </a>
  <a :href="withBase('/features/human')">
    <strong>Put it to a person</strong>
    <span>The same shape as a short questionnaire at the prompt.</span>
  </a>
  <a :href="withBase('/reference/flows')">
    <strong>Flows reference</strong>
    <span>Every argument of a turn, and every error it can raise.</span>
  </a>
</div>
