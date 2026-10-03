<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Completion

Type `/` or `$` at the prompt, and a list above it offers ways to finish the word. Take one
with <kbd>tab</kbd> and keep typing.

::: info At a glance
- **You will** find a command or a flow without remembering its exact name, and see what a
  command takes before you send it.
- **Use it when** you are not sure what you can do right now, or which flows this directory
  can run.
- **You need** `hmz` open. Nothing else: completion is on from the start.
:::

## Try it

```text
❯ /
❯ /s        then tab: /settings
❯ $ra       then tab: $ralph_loop
```

<HmzCast name="completion" alt="hmz: typing / lists every command that works now with what it takes; /s narrows it to /settings; tab takes it; /afk shows what it takes; $ lists the flows, $lo narrows them to the project's own, and tab finishes the name" />

## How it works

The prompt watches the word under the cursor. When that word starts with `/` or `$`, a list
opens between the transcript and the prompt, and narrows as you type. Each row is one way to
finish the word: a command with what it takes and what it is for, or a flow by the name you
would run it under.

The list is built from **what can happen now**. A command that would do nothing in the state
the run is in is left out, and the list changes the moment that state does, even while it is
open. So the list is also a quick answer to "what can I do here?".

## Example: find a command, then read what it takes

With no flow running, type `/`:

<Term title="hmz · the list /  opens">

<pre>  <span class="p">/afk</span> <span class="m">[on|off]</span>      <span class="p">Toggle whether an agent may ask you</span><span class="n">1</span>
  <span class="p">/btw</span> <span class="m">[question]</span>    <span class="p">Ask side questions; press esc or /btw to stop</span>
  <span class="p">/clear</span>             <span class="p">Clear the screen</span>
  <span class="p">/epics</span>             <span class="p">View and manage runs in this directory</span>
  <span class="p">/exit</span>              <span class="p">Exit</span>
  <span class="p">/flow</span> <span class="m">[flow]</span>       <span class="p">Switch flow</span>
  <span class="p">/resume</span>            <span class="p">Resume the last run in this directory</span><span class="n">2</span>
  <span class="p">/settings</span> <span class="m">[page]</span>   <span class="p">Every setting: general, accounts, fallback, runtimes, flowverses, workspace</span>
<span class="d">────────────────────────────────────────────────────────────</span>
<span class="d">❯</span> /
<span class="d">────────────────────────────────────────────────────────────</span>
<span class="a">◉</span> <span class="d">ralph_loop · ~/tmp/humanize-demo        ↑↓ move · tab select · esc cancel</span><span class="n">3</span></pre>

</Term>

Now type `s`, press <kbd>tab</kbd>, delete back to `/`, and type `afk`:

<Term title="hmz · a complete command">

<pre>  <span class="p">/afk</span> <span class="m">[on|off]</span>      <span class="p">Toggle whether an agent may ask you</span><span class="n">4</span>
<span class="d">────────────────────────────────────────────────────────────</span>
<span class="d">❯</span> /afk
<span class="d">────────────────────────────────────────────────────────────</span>
<span class="a">◉</span> <span class="d">ralph_loop · ~/tmp/humanize-demo   enter run · / commands · shift+enter newline · ctrl+c clear</span><span class="n">5</span></pre>

</Term>

What to look at, by number:

1. **What a command takes.** `[on|off]` after `/afk` is its argument, in brackets because it is
   optional. The words after that say what it does.
2. **Only what works now.** `/resume` is listed because a run here can be carried on. `/stop` is
   not, because nothing is running. Start a flow and the list changes: `/stop` appears, `/resume`
   goes, and `/flow` reads `Set up the running flow's agents`.
3. **The list's keys.** While the list is open, the status line says what the keys do to it:
   <kbd>↑</kbd> <kbd>↓</kbd> move, <kbd>tab</kbd> takes the highlighted row, <kbd>esc</kbd>
   puts the list away.
4. **The hint.** Once a word is complete, the list gives way to a single line above the prompt
   saying what the command takes. It stays while you type the argument.
5. **`enter run`.** With a whole command typed, <kbd>enter</kbd> sends it. The list is closed, so
   <kbd>enter</kbd> no longer picks from it.

### Check it worked

- <kbd>tab</kbd> replaced the half-typed word with the whole one, and the cursor is after it.
- The status line's keys went back from the list's to the prompt's.

## What is offered

| You type | The list offers |
| --- | --- |
| `/` | every command that would do something now, with what it takes after its name and what it is for |
| `/flow ` | every flow you can run here, by the name it is offered under |
| `/settings ` | its six pages: `general`, `accounts`, `fallback`, `runtimes`, `flowverses`, `workspace` |
| `$` | the same flows, as `$name`. `$ralph_loop fix the build` starts that flow on that task. |

The commands follow what is going on. `/stop` is listed while a flow runs and not once it is
stopping; `/resume` only with nothing running and a run here to carry on; `/claim` only on an
outworlder's transcript that nobody else holds. While a flow runs, no flow is offered after
`/flow ` or `$`, and `/flow` reads `Set up the running flow's agents`. A command that is not
listed can still be typed, and says why it did nothing.

The flows are the ones humanize ships, the ones in every [flowverse](/weaver/flowverses)
fetched here, and your own. Each is offered under one name:

| Where the flow comes from | Offered as |
| --- | --- |
| humanize itself, or the official flowverse | a bare name: `chat`, `ralph_loop` |
| this project's `.humanize/flows/` | `local/twice` |
| `~/.humanize/flows/` | `user/twice` |
| any other flowverse | `<flowverse>/<flow>` |

## The keys

While the list is open:

| Key | Does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move through the list. |
| <kbd>tab</kbd> or <kbd>enter</kbd> | Take the highlighted offer. It replaces the word you were typing. |
| <kbd>esc</kbd> | Put the list away. |

The list follows the cursor. It is offered only at the end of the line, and not over a line
you brought back from [history](/user/history).

## Variations

- **Start a flow in one line.** `$` then <kbd>tab</kbd> on a flow, a space, and the task:
  `$ralph_loop fix the build`. A flow that is set up here starts at once; one that is not
  opens `/flow` on its roles, holding your line.
- **Go straight to a settings page.** `/settings ` offers its six pages: `/settings accounts`
  opens the Accounts page. See [Settings](/user/settings).
- **Narrow a long menu.** The menus behind the commands list flows, models, accounts, runs and
  fallbacks. Press <kbd>/</kbd> or **Search…** and type into the box above the list: a row
  stays if the letters you
  type appear in its name in that order, so `o5` finds `claude-opus-5-5`. On the menus of
  models, accounts and fallbacks, a name you type out whole, or the start of one, comes first:
  `claude-sonnet-5` lists `claude-sonnet-5` above `claude-sonnet-4-5`. <kbd>esc</kbd> leaves
  the search first, then the menu.

## What is not offered

- **A flow anywhere else.** A flow outside the places above is a path, and you type it:
  `/flow ./flows/mine`.
- **The task.** Everything after `$name ` is yours to write.
- **Models and accounts.** Those are chosen from lists inside `/flow`, when you set up each
  agent.

## Troubleshooting

### The command I want is not in the list

It would do nothing right now: `/stop` with nothing running, `/resume` while a flow runs. Type
it anyway and <kbd>enter</kbd> says why, such as `hmz: no flow is running`.

### <kbd>enter</kbd> took a suggestion instead of sending my line

The list was open and <kbd>enter</kbd> took its highlighted row. Press <kbd>esc</kbd> to put the
list away first, or finish the word so the list closes.

### No flows are offered after `$`

A flow is running, and another cannot be chosen until it stops. Or the flowverses have not been
fetched yet: open `/settings flowverses` and fetch `official`.

### No list appears at all

The cursor is not at the end of the line, or the line came back from [history](/user/history).
Move to the end, or type a character.

## Next steps

- [History](/user/history): bring back a line you already sent.
- [Your first run](/user/first-run): choose a flow with `/flow` and start it.
- [TUI reference](/reference/tui): every command and key.
