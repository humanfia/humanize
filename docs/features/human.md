---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# You, as one of the agents

A flow can ask **you** something the way it asks an agent: put a question at the prompt, wait
for your answer, and carry on with it. When it wants a decision rather than a line of text, it
asks for a [shape](/features/shapes), and you get one short question per field. Your answers
come back as the same fields a model would have filled in.

<HmzPerson />

## How a shape becomes questions

| In the flow's shape | At the prompt |
| --- | --- |
| a field's description | the question itself, or the field's name where it has none |
| one of a few words | those words, listed under the question |
| yes or no | `yes` and `no` |
| a number | `(a number)` after the question |
| a list | `(several, separated by commas)`, typed on one line |
| a default | ``-- or `-` for …`` after the question: a dash takes the default |

You can type anything. The answers are checked together once every field has one, and a field
the flow's shape will not take is asked again, with the reason above it. Keep typing what it
will not take and the flow carries on as if nobody were there.

## When nobody is there

You count as away for every run of `hmz exec`, and whenever [`/afk`](/user/afk) is on. The flow
is then answered at once instead of waiting:

- a question asked for text gets an empty answer;
- a shape with a default for every field gets those defaults;
- any other shape fails, and the flow has to handle that.

So a flow meant to run unattended gives its questions defaults. Going away in the middle of a
questionnaire is answered the same way.

## Filled in for you

The flow's person is never an agent you choose: when you start a flow that has one, you give
agents for its other roles, and humanize puts you in this one. A flow that calls another can
answer that flow's questions itself, by a rule or by asking another agent, instead of passing
them on to you.

An agent that stops mid-turn to ask you something reaches you the same way, at the same prompt.
[Questions](/user/questions) covers answering either.

## Go further

<div class="hmz-paths by-three">
  <a :href="withBase('/user/questions')">
    <strong>Answer one</strong>
    <span>What a question looks like at the prompt, and how to answer it.</span>
  </a>
  <a :href="withBase('/weaver/human-agent')">
    <strong>Ask one</strong>
    <span>Driving the person from a flow, and standing in for them.</span>
  </a>
  <a :href="withBase('/user/afk')">
    <strong>Step away</strong>
    <span>What <code>/afk</code> does to questions while a run goes on.</span>
  </a>
</div>
