# User Guide

For the person who runs flows: you give coding agents a task, a loop to work in and a budget,
and humanize drives them until the work is done or the budget is spent. Nothing here asks you
to write Python; writing flows is the [Weaver Guide](/weaver/).

::: info How this guide is built
- **Start here** and the **Tutorials** are lessons: follow them in order, every command written
  out, every step checked before the next.
- **Everything else** is a guide to one task: what it is for and what you need, a *Try it*
  short enough to paste, how the thing works, a worked example with every part of it
  explained, how to check it worked, what to do when it does not, and where to go next.
- **Look-up** pages, and the [Reference](/reference/), are for when you know what you want.
:::

## Start here

<div class="u7-path">

1. **[Installation](/user/installation)**
   humanize, and one coding agent CLI signed in. About five minutes.
2. **[Your first run](/user/first-run)**
   Choose a flow, give it an agent and a budget, watch it fix a bug, and stop it.
3. **[Security](/user/security)**
   What to check before a flow touches work you care about.

</div>

## Tutorials

Then take a whole piece of work start to finish. Each is one path, with real output at every
step:

| Tutorial | You learn | Takes |
| --- | --- | --- |
| [Beat a benchmark](/user/tutorials/take-home) | two agents taking turns, a task file, checking a result against cheating | an hour of you, hours of the machine |
| [Port a project](/user/tutorials/port-a-project) | an actor and a reviewer, a run that ends itself | about an hour |
| [Build a coding agent](/user/tutorials/build-an-agent) | three flows in a row: idea, plan, build | an afternoon |

## Everything else

<div class="u7-groups">
<div>

**While it runs**

- [Talking to a running turn](/user/steering)
- [Side questions (/btw)](/user/btw)
- [Many conversations at once](/user/conversations)
- [Showing the working](/user/settings#details)
- [Watching a run (the monitor)](/user/monitor)
- [Being away (/afk)](/user/afk)
- [Stopping](/user/stopping)
- [Leaving it running](/user/leaving)
- [In a browser (hmz web)](/user/web)
- [The mission board](/user/board)

</div>
<div>

**At the prompt**

- [Completion](/user/completion)
- [History](/user/history)
- [Settings (/settings)](/user/settings)

**Where the work lands**

- [Containers](/user/containers)
- [Remote execution](/user/remote-execution)

</div>
<div>

**Agents and accounts**

- [Accounts](/user/settings#accounts)
- [Efforts](/user/efforts)
- [Falling back](/user/settings#fallback)
- [Cost and rate](/user/tally)
- [Permissions](/user/permissions)
- [Skills](/user/skills)
- [Questions](/user/questions)

</div>
<div>

**After a run**

- [Picking a run up](/user/resuming)
- [Exporting a run](/user/export)
- [Tracing](/user/tracing)

**Without the interface**

- [Run it unattended](/user/unattended)
- [humanize in CI](/user/ci)

</div>
<div>

**Look-up**

- [Troubleshooting](/user/troubleshooting)
- [Reporting](/user/reporting)
- [Glossary](/user/concepts)
- [CLI reference](/reference/cli)
- [TUI reference](/reference/tui)
- [Web reference](/reference/web)

</div>
</div>

<style scoped>
.u7-path ol {
  list-style: none;
  counter-reset: step;
  padding-left: 0;
  display: grid;
  gap: 12px;
}
.u7-path li {
  counter-increment: step;
  position: relative;
  margin: 0;
  padding: 14px 16px 14px 60px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-2);
}
.u7-path li::before {
  content: counter(step);
  position: absolute;
  left: 16px;
  top: 14px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-weight: 600;
  color: var(--vp-c-white);
  background: var(--vp-c-brand-1);
}
.u7-path li strong {
  display: block;
  font-size: 1.05em;
}
.u7-groups {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 4px 24px;
  margin-top: 16px;
}
.u7-groups ul {
  list-style: none;
  padding-left: 0;
  margin: 4px 0 16px;
}
.u7-groups li {
  margin: 2px 0;
}
.u7-groups a,
.u7-path a {
  text-decoration: none;
}
.u7-groups a:hover,
.u7-path a:hover {
  text-decoration: underline;
}
.u7-groups p {
  margin: 8px 0 0;
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--vp-c-text-2);
}
</style>
