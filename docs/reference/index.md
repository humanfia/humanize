---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Reference

The complete technical specification of humanize as built: every command, option, grammar,
key, screen, setting, protocol message, file, environment variable, Python symbol, default,
limit and error. Each page states behaviour; tasks and explanations are in the
[User Guide](/user/), [Weaver Guide](/weaver/) and [Features](/features/).

## Pages {#pages}

| Page | Covers | Package |
| --- | --- | --- |
| [CLI](/reference/cli) | `hmz`, `hmz exec`, `hmz internal …`: synopsis, options, the `-f`/`-a`/`-e`/`-p` grammars, refusals, output and NDJSON schema, signals, exit statuses | `hmz.cli` |
| [TUI](/reference/tui) | The interface `hmz` opens: views, status line, commands, keys, menus, `/settings`, the monitor, completion, history | `hmz.tui` |
| [Daemon](/reference/daemon) | The machine's daemon and its per-workspace host processes, their files, lifecycle, frame protocol, requests, messages and multi-frontend rules | `hmz.daemon` |
| [SDK](/reference/sdk) | `hmz.sdk`: every exported class, method, parameter, return type and exception | `hmz.sdk` |
| [Flows](/reference/flows) | The flow API: `@flow`, roles, params, budgets, context, errors, testing | `hmz.flows` |
| [Agents](/reference/agents) | Coding-agent drivers below the flow API: backends, sessions, hooks, fences | `hmz.coganchor` |
| [Machines](/reference/machines) | Environments: local, ssh, docker; runtimes | `hmz.coganchor` |
| [Providers](/reference/providers) | Accounts an agent runs as, ways in | `hmz.coganchor` |
| [Remote execution](/reference/remote-execution) | `hmz internal anchor`: harness placement, targets, mirrors | `hmz.coganchor` |
| [Tracing](/reference/tracing) | Epics, journals, traces, profiling, export | `hmz.runtime` |
| [Files](/reference/files) | Everything under `$HUMANIZE_HOME` and a workspace's `.hmz/` | — |
| [Environment variables](/reference/environment) | Every variable any part of humanize reads or sets | — |
| [Settings](/reference/settings) | Every key of `settings.yaml` and the other stores the interface writes | — |

## Lookup {#find-it}

| Looking for | Section |
| --- | --- |
| an `hmz exec` option | [CLI › Options](/reference/cli#exec-options) |
| the grammar of `-a`, `-e`, `-p` | [CLI › Grammar](/reference/cli#grammar) |
| why `hmz exec` refused a line | [CLI › What is refused](/reference/cli#what-is-refused-before-anything-runs) |
| what `hmz exec --json` writes | [CLI › `--json`](/reference/cli#ndjson) |
| an exit status | [CLI › Exit statuses](/reference/cli#exit-statuses) |
| a process named `hmz internal …` | [CLI › `hmz internal`](/reference/cli#hmz-internal) |
| a slash command, and when it is refused | [TUI › Commands](/reference/tui#commands) |
| a key | [TUI › Keys](/reference/tui#keys) |
| a menu, sheet or form | [TUI › Menus](/reference/tui#menus), [`/settings`](/reference/tui#what-humanize-remembers) |
| the monitor | [TUI › Monitor](/reference/tui#watching-the-run) |
| a daemon request or message | [Daemon › Requests](/reference/daemon#requests), [Messages](/reference/daemon#messages) |
| a Python class or method | [SDK](/reference/sdk) |
| a file under `~/.hmz` | [Files](/reference/files) |
| an environment variable | [Environment variables](/reference/environment) |

## Conventions {#conventions}

| Notation | Meaning |
| --- | --- |
| `monospace` | Literal text: typed, printed or stored exactly as shown. |
| `<name>` | A placeholder for a value described alongside. |
| `[x]` | Optional. |
| `x…`, `x [x …]` | One or more. |
| `a \| b` | One of the alternatives. |
| `{a, b}` | Every combination, as a shell brace expansion. |
| EBNF blocks | `=` defines, `,` concatenates, `\|` alternates, `[ ]` optional, `{ }` zero or more, `( )` groups, `" "` terminal, `? ?` prose. |
| `~/.hmz` | `$HUMANIZE_HOME` where set and non-empty. |
| `hmz: …` | Text as printed; a leading `hmz: ` or `hmz exec: error: ` is part of the message. |
| Types | Python annotations as written in the source (`str \| None`, `tuple[str, ...]`). |
| *as local* | A CLI running as this machine's own login, with no humanize account. |
| workspace | The directory a run or an interface is started in (resolved path). |
| run | One execution of one flow; recorded as one epic. |
| role | A name a flow declares for an agent, an environment or an outworlder. |
| frontend | An interface or program attached to a [host](/reference/daemon). |

Where behaviour and a spec under `specs/` differ, these pages describe the behaviour of the
code.
