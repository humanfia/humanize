---
pageClass: hmz-feature
---

# Every run has a budget

Every run is given a **budget**: how long it may take, how much it may cost, how many output
tokens its agents may write. Whichever limit is reached first stops the run. A run will not
start without one, except [`chat`](/flows/chat), a conversation that ends when you stop typing.

<div class="limits">
  <div class="limit">
    <strong>duration</strong>
    <span class="counts">wall clock, from the start of the run</span>
    <p>The one that stops a loop whose every turn is failing. A turn that cannot run spends no
    tokens and no money, but it still spends time.</p>
  </div>
  <div class="limit">
    <strong>output tokens</strong>
    <span class="counts">what the agents write</span>
    <p>The work itself. What a turn reads is mostly the conversation so far, sent again and
    served from a cache; what the agents write is what you are paying for.</p>
  </div>
  <div class="limit">
    <strong>cost</strong>
    <span class="counts">US dollars, priced from what each CLI reports</span>
    <p>What you actually pay. A model nobody lists a price for counts as free, so set a
    duration or token limit beside it.</p>
  </div>
</div>

You give it when you start the run: with `-b` on a [command line](/reference/cli), or in the
flow menu, which asks for it with the rest of the run and remembers it for that flow.

## Graceful, or not

A budget is **graceful** unless you say otherwise.

| | When a limit is reached mid-turn |
| --- | --- |
| **Graceful** (the default) | The turn that spent the last of it runs to its end and answers. Its edits are on disk and its conversation is open. The next turn is refused, and the run stops there. |
| **Not graceful** | The turn is cut off where it stands, and the CLI stops spending. Use it where overrunning is worse than stopping mid-sentence. |

A run stopped by its budget ends with a budget error, and exits with status 0.

## Budgets nest

A flow can call another flow with a budget of its own. The called flow runs under **the tighter
of its own budget and what its caller has left**. A review held to $2 inside a run with $1 left
gets $1.

<div class="nest" role="img" aria-label="A run with a $50 budget contains a review flow called with $2, which contains its turns">
  <div class="box run">
    <span class="tag">the run · $50 · 6 h</span>
    <div class="inner">
      <div class="box call">
        <span class="tag">review · called with $2</span>
        <div class="turns"><span>turn</span><span>turn</span><span>turn</span></div>
      </div>
      <div class="box call">
        <span class="tag">review · called with $2</span>
        <div class="turns"><span>turn</span><span>turn</span></div>
      </div>
    </div>
  </div>
</div>

- **Cost and tokens roll up.** What a turn spends counts against its own call and every call
  above it. Ten reviews spend ten reviews' worth of the run's budget.
- **Duration is a deadline.** It counts from when each call started, and is not added up over
  its children. Ten reviews run at once under a one-hour deadline have one hour between them,
  not ten.
- **A spent budget stays spent.** Every later turn under it, in that flow and in every flow it
  calls, is refused.

A single turn can have a budget of its own, too. See [A turn can be cut off](/features/budgets).

## humanize holds it, not the flow

The budget is whoever started the run's to set, and humanize holds every turn of every agent to
it. A flow cannot opt out, and a hook cannot talk a spent budget into another turn. A flow can
read what it may still spend, and what it has spent so far.

## Per run, not across runs

The budget belongs to this run. A run you [pick up again](/features/resuming) is a new run, with
the budget its own command line gives it. So a run stopped by its budget is one to pick up, not
one that is over.

## Where the detail is

- [A turn can be cut off](/features/budgets): a limit on one turn rather than on the run
- [Cost and rate](/user/tally): what the readings are made of
- [Stopping](/user/stopping): ending a run by hand
- [CLI reference](/reference/cli): how `-b` is written

<style>
.limits {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 20px 0 24px;
}

.limits .limit {
  padding: 14px 16px;
  border: 1px solid var(--vp-c-divider);
  border-top: 3px solid var(--hmz-accent);
  border-radius: 12px;
  background: var(--vp-c-bg-soft);
}

.limits .limit:nth-child(2) {
  border-top-color: var(--hmz-lane-3);
}

.limits .limit:nth-child(3) {
  border-top-color: var(--hmz-warm);
}

.limits strong {
  display: block;
  font-family: var(--vp-font-family-mono);
  font-size: 15px;
}

.limits .counts {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.limits p {
  margin: 10px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--vp-c-text-2);
}

.nest {
  margin: 18px 0 20px;
  font-size: 12px;
}

.nest .box {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 10px 12px 12px;
}

.nest .run {
  border-color: var(--hmz-accent);
  background: var(--vp-c-bg-soft);
}

.nest .call {
  flex: 1 1 200px;
  border-style: dashed;
  border-color: var(--hmz-lane-3);
  background: var(--vp-c-bg);
}

.nest .tag {
  display: block;
  margin-bottom: 8px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
}

.nest .inner {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.nest .turns {
  display: flex;
  gap: 6px;
}

.nest .turns span {
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-2);
}

@media (max-width: 720px) {
  .limits {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
