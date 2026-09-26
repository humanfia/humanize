# User Guide

For the person who runs flows. Nothing here asks you to write Python; writing flows is the
[Weaver Guide](/weaver/).

## Start here

<div class="u7-path">

1. **[Installation](/user/installation)**
   humanize, and one coding agent CLI signed in.
2. **[Your first run](/user/first-run)**
   Choose a flow, give it an agent and a budget, and watch it work.
3. **[Security](/user/security)**
   What to check before a flow touches work you care about.

</div>

Then take a whole piece of work start to finish:
[Beat a benchmark](/user/tutorials/take-home),
[Port a project](/user/tutorials/port-a-project), or
[Build a coding agent](/user/tutorials/build-an-agent).

## Everything else

<div class="u7-groups">
<div>

**While it runs**

- [Talking to a running turn](/user/steering)
- [Side questions (/btw)](/user/btw)
- [Many conversations at once](/user/conversations)
- [Showing the working (/details)](/user/details)
- [Watching a run (/monitor)](/user/monitor)
- [Being away (/afk)](/user/afk)
- [Stopping](/user/stopping)
- [Leaving it running](/user/leaving)
- [The mission board](/user/board)

</div>
<div>

**At the prompt**

- [Completion](/user/completion)
- [History](/user/history)
- [What a project remembers](/user/settings)

**Where the work lands**

- [Containers](/user/containers)
- [Remote execution](/user/remote-execution)

</div>
<div>

**Agents and accounts**

- [Providers](/user/providers)
- [Efforts](/user/efforts)
- [Falling back (/fallback)](/user/fallback)
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
