<script setup>
import { withBase } from 'vitepress'
</script>

# Reference

Every command, flag, key, argument and return, for a reader who knows what they are looking
for. New to humanize? Start with the [User Guide](/user/) or the [Weaver Guide](/weaver/).

## Find it

| You are looking for | It is in |
| --- | --- |
| a flag of `hmz exec`, or how to write `-a`, `-e`, `-p`, `-b` | [CLI › `hmz exec`](/reference/cli#hmz-exec) |
| what `hmz exec --json` writes | [CLI › Watching a run](/reference/cli#watching-a-run) |
| why `hmz exec` refused a line | [CLI › What is refused](/reference/cli#what-is-refused-before-anything-runs) |
| an environment variable | [CLI › Environment variables](/reference/cli#environment-variables) |
| a file under `~/.humanize` | [CLI › Files](/reference/cli#files) |
| an exit status | [CLI › Exit statuses](/reference/cli#exit-statuses) |
| a process named `hmz internal …` | [CLI › `hmz internal`](/reference/cli#hmz-internal) |
| a key, at the prompt or in a menu | [TUI › Keys](/reference/tui#keys) |
| a slash command | [TUI › Slash commands](/reference/tui#commands) |
| a menu: `/flow`, `/providers`, `/fallback`, `/epics`, `/settings`, `/monitor` | [TUI › Menus](/reference/tui#menus) |
| a run left going after `/exit` | [Daemon](/reference/daemon) |
| the API a flow is written against | [Flows](/reference/flows) |
| driving humanize from another program | [SDK](/reference/sdk) |
| an agent, a session, a hook, below the flow API | [Agents](/reference/agents) |
| where an agent's work lands | [Machines](/reference/machines), [Remote execution](/reference/remote-execution) |
| an account an agent runs as | [Providers](/reference/providers) |
| a trace, or what a run wrote down | [Tracing](/reference/tracing) |

## Command line

<div class="hmz-paths by-three">
  <a :href="withBase('/reference/cli')">
    <strong>CLI</strong>
    <span><code>hmz</code>, <code>hmz exec</code> and <code>hmz internal</code>: every flag,
    the environment variables, the files and the exit statuses.</span>
  </a>
  <a :href="withBase('/reference/tui')">
    <strong>TUI</strong>
    <span>The screen <code>hmz</code> opens: every key, every slash command, and each
    menu.</span>
  </a>
  <a :href="withBase('/reference/daemon')">
    <strong>Daemon</strong>
    <span>The process holding a run so a terminal can leave, and how to reach it from
    Python.</span>
  </a>
</div>

## Python

| Page | |
| --- | --- |
| [SDK](/reference/sdk) | How a tool that is not humanize reaches it: `Hmz` straight at the runtime, `Daemons` over a held run. |
| [Flows](/reference/flows) | The flow API: what `@flow` declares, and the agents, environments and params a flow is handed. |
| [Agents](/reference/agents) | Driving a coding agent from Python: an agent is settings, a session is memory. |
| [Machines](/reference/machines) | Where an agent's turns land: here, a container, or a machine already running. |
| [Providers](/reference/providers) | Which account an agent runs as, kept apart from the CLI's own. |
| [Remote execution](/reference/remote-execution) | `hmz internal anchor`: an agent on this machine whose work lands on another. |
| [Tracing](/reference/tracing) | The sessions and programs a run left behind, gathered into one timeline. |
