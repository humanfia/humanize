# What a project remembers

Run `hmz` in a directory you have used before and it opens on the flow you last saved there,
with the agents you gave it. `/settings` shows what this directory remembers, and is where you
make it forget.

## Try it

```
/settings
```

![/settings opening on what is true of this machine, then tab to this directory: workspace,
flow, profile and forget](/demo/profiling.gif)

The menu has two pages. <kbd>tab</kbd> and <kbd>shift+tab</kbd> turn between them.

| Page | Row | What it is |
| --- | --- | --- |
| **Everywhere** | reports | whether humanize [reports what goes wrong](/user/reporting) to its developers, for every project on this machine |
| | sent | what a report carries and what it never does. <kbd>enter</kbd> reads it out. |
| **This directory** | workspace | the directory these settings belong to |
| | flow | the flow it opens on, and how many agents that flow was set up with |
| | profile | whether a run here [profiles](#whether-a-run-here-is-profiled) the programs it starts |
| | forget | forget everything this directory remembers |

<kbd>←</kbd> <kbd>→</kbd> or <kbd>space</kbd> flip the row under the cursor. Nothing changes
until you save: choose the **save** row, or press <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd>
anywhere in the menu. Leave with <kbd>esc</kbd> and unsaved changes, and it asks **save** or
**discard**; <kbd>esc</kbd> on that question takes you back into the menu.

**forget** clears this directory only. Every other directory, and the reporting answer, stay
as they were. The next `hmz` here opens as it did the first time.

## What a directory remembers

- **The flow** it last ran.
- **For each flow it has run:**
  - what each agent role runs: the CLI, the [account](/user/providers), the model and the
    effort;
  - where each environment role works;
  - how the flow itself was [set up](/reference/tui), and what a run of it may spend.
- **Whether its runs are profiled.**

Each flow's setup is kept under the name the flow is offered by: `ralph_loop` for one humanize
ships, `local/twice` for a project flow, `user/twice` for a personal one. Within a flow, each
agent is kept under its role name. A flow that gains a new role does not hand an existing
role's model to it.

When the flow changes, what was saved is checked against it again. A setting the flow has
since dropped or renamed is asked for again, rather than carried over.

## Changing it

Change it where you set it: in [`/flow`](/reference/tui). Choose the flow, set each agent and
environment and what a run may spend, and save. That save is what the next `hmz` here opens
on. It only opens there: nothing runs until you send the first line.

Saving checks the lot before any of it is kept. The flow is loaded, every role is checked
against what the flow declares, and a flow that refuses a combination of its own settings says
why. You fix it in the menu, not half an hour into a run.

## Whether a run here is profiled

The **profile** row on the second page adds the programs a run starts (the tests, the builds,
the greps) and how long each took to the run's [trace](/user/tracing), on the same timeline as
the agents. It is off until you turn it on, and it belongs to the directory: a repository
whose tests take an hour is a different question from one whose tests take a minute.

It takes effect from the next run, not the one under way. An `hmz exec` run in this
directory is profiled too. What is recorded, and how to read it, is
[Tracing](/user/tracing).

## `hmz exec` starts from none of this

What an `hmz exec` line runs is what the line says: `-f`, `-a`, `-e`, `-p` and `-b`. An
unattended run inherits nothing from how this directory was last set up. It reads only two
things from here:

- whether runs in this directory are profiled;
- whether you said yes to [reporting](/user/reporting).

## The first time

With nothing remembered, `hmz` opens on the [`chat`](/flows/chat) flow, with the first
installed CLI that can run without further setup, at the first model that CLI lists, at effort
`high` where the model offers it.

::: details Where it is kept
Everything above is one file, `~/.humanize/settings.yaml` (under `$HUMANIZE_HOME` if you set
that). Deleting it makes every directory start over, and asks the reporting question again.
:::

## See also

- [History](/user/history): the other thing kept between starts
- [Tracing](/user/tracing): what a profiled run is drawn into
- [TUI reference](/reference/tui): the `/settings` and `/flow` menus, row by row

<style scoped>
kbd {
  display: inline-block;
  min-width: 1.7em;
  padding: 0 0.45em;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-base);
  font-size: 0.85em;
  font-weight: 500;
  line-height: 1.6;
  text-align: center;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}
</style>
