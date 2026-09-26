---
pageClass: hmz-feature
---

# One timeline

Any run can become one trace: every agent, every session and every tool call on one timeline,
whichever CLIs did the work. You open it in [Perfetto](https://ui.perfetto.dev). It is a file
on your machine, and nothing is uploaded.

<HmzTimeline />

<p class="hmz-note">
Point at or tap a slice to see what it carries. Switch the programs off to see a run from a
directory that is not profiled.
</p>

## Reading one

| In the trace | Is |
| --- | --- |
| a **process** | one agent, named by its role in the flow, with every session it opened. In a profiled run, also one program an agent ran. |
| a **track** | one row of that agent's sessions. Sub-agents a turn reached for get rows of their own. For a program, one of its threads. |
| a **slice** | one action: a message, a tool call, or time spent reasoning. It carries as much as the CLI wrote down: the prompt, the reasoning, the tool's input and output. |

## Every agent under its own name

A CLI logs a session under an id and never says whose it was, so two agents on the same CLI and
model look like one. The run writes down which agent each session belonged to, which CLI took
its turns and which account they ran as. So a trace shows `actor` and `reviewer`, not a
directory of ids.

It also holds only that run's sessions. A directory you have run in fifty times has fifty runs,
and none of their traces holds another's work.

## The programs underneath

A turn is mostly other programs: the tests, the build, the searches. A CLI's log records the
tool call, not what it ran. Turn profiling on for a directory, and every run there draws each
program an agent starts under the tool call that started it, thread by thread.

Profiling watches from the side. It never gets between an agent and what it runs, and nothing
it fails at can stop a run.

## Which backends can be read back

Every backend humanize ships with, except one:

<Badge type="tip" text="agy" /> <Badge type="tip" text="claude" /> <Badge type="tip" text="codex" />
<Badge type="tip" text="dsh" /> <Badge type="tip" text="grok" /> <Badge type="tip" text="kimi" />
<Badge type="tip" text="mimo" /> <Badge type="tip" text="opencode" /> <Badge type="tip" text="pi" />
<Badge type="tip" text="qwen" /> <Badge type="tip" text="zcode" />
<Badge type="warning" text="cursor-agent: nothing to read" />

Cursor Agent keeps its chats in a store of its own rather than a log per session, so a trace
has nothing to gather from it. The same goes for an ACP CLI you add yourself.

## It stays on your machine

A trace can hold prompts, answers and tool output, because it is the record you asked to read.
Opening it in Perfetto sends nothing anywhere. Reporting humanize's own failures is a separate
thing, off until you say yes. See [Reporting](/user/reporting).

## Where the detail is

- [Tracing](/user/tracing): making one, and what to look for in your first
- [Exporting a run](/user/export): the run as one archive, with its trace in it
- [Tracing reference](/reference/tracing): what a run writes down, and every field of a slice
