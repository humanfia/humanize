---
pageClass: hmz-feature
---

# A line typed mid-turn

Type while an agent is working, and your line goes **into the turn it is running**. The agent
takes your words into account and carries on, rather than starting over. That is the difference
between saying "actually, use pathlib" four minutes into a refactor and saying it after.

<HmzSteer />

## Which backends take it

<div class="steer-split">
  <div class="side yes">
    <strong>Into the running turn</strong>
    <p>
      <Badge type="tip" text="Claude Code" /> <Badge type="tip" text="Codex" />
      <Badge type="tip" text="Kimi Code" /> <Badge type="tip" text="pi" />
    </p>
    <span>The agent takes your line while it works.</span>
  </div>
  <div class="side later">
    <strong>Into the next turn</strong>
    <p><Badge type="warning" text="every other backend" /></p>
    <span>They are handed a turn's whole prompt at the start, so the line waits, and goes into
    whichever turn starts next. The prompt says so when it happens.</span>
  </div>
</div>

An agent working on [another machine](/features/anchor) takes a line the same way.

## It goes to the agent you are reading

A flow drives several agents, and a line said to one you are not looking at would be said to
somebody else. So your line goes to the agent on your screen. When you are reading all of them
at once, it goes to whichever one has a turn open. See
[Many conversations at once](/user/conversations).

## One line at a time

Everything you type joins one queue. The next line goes only once the agent has said it has the
one before, so three lines typed in a row are three things said, and get three answers.

Until the agent has it, your line stays pinned above the prompt, marked with the agent it was
handed to. It reaches the transcript only once the agent has it. If no turn is open, the line waits for the
next one: a line typed at a running flow is never dropped.

## From a flow

A flow can say something into a running turn too, on a role declared to take one. It can leave
the line for the agent to pick up as it works, or interrupt the turn and have it carry on from
the new words. A role that asks for this is refused a backend that cannot do it before the run
starts. See [Sessions and turns](/reference/flows#sessions-and-turns).

## Where the detail is

- [Talking to a running turn](/user/steering): the pin, and what each backend does
- [Many conversations at once](/user/conversations): which agent a line reaches
- [Stopping](/user/stopping): when a line is not enough

<style>
.steer-split {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0 20px;
}

.steer-split .side {
  padding: 14px 16px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg-soft);
}

.steer-split .side.yes {
  border-color: var(--hmz-accent);
}

.steer-split .side strong {
  display: block;
  font-size: 14px;
}

.steer-split .side p {
  margin: 8px 0;
  line-height: 2;
}

.steer-split .side span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .steer-split {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
