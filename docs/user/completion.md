<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Completion

Type `/` or `$` at the prompt, and a list under it offers ways to finish the word. Take one
with <kbd>tab</kbd> and keep typing.

![hmz: typing / lists every command with what it takes; /fl narrows it to /flow and
/flowverses; tab takes one; /afk shows what it takes; $ lists the flows, $lo narrows them to
the project's own, and tab finishes the name](/demo/completion.gif)

## What is offered

| You type | The list offers |
| --- | --- |
| `/` | every command, with what it takes after its name and what it is for |
| `/flow ` | every flow you can run here, by the name it is offered under |
| `$` | the same flows, as `$name`. `$ralph_loop fix the build` starts that flow on that task. |

The flows are the ones humanize ships, the ones in every [flowverse](/weaver/flowverses)
fetched here, and your own. Each is offered under one name:

| Where the flow comes from | Offered as |
| --- | --- |
| humanize itself, or the official flowverse | a bare name: `chat`, `ralph_loop` |
| this project's `.humanize/flows/` | `local/twice` |
| `~/.humanize/flows/` | `user/twice` |
| any other flowverse | `<flowverse>/<flow>` |

## The keys

<Term>

<pre><span class="p">/flow [flow]</span>       <span class="p">Switch flow</span>
/flowverses        <span class="m">Manage the places flows come from</span>
<span class="d">────────────────────────────────────────────────────────────</span>
<span class="d">❯</span> /fl
<span class="d">────────────────────────────────────────────────────────────</span>
<span class="a">◉</span> <span class="d">twice · ~/code/app       ↑↓ move · tab take · esc dismiss</span></pre>

</Term>

While the list is open:

| Key | Does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move through the list. |
| <kbd>tab</kbd> or <kbd>enter</kbd> | Take the highlighted offer. It replaces the word you were typing. |
| <kbd>esc</kbd> | Put the list away. Press it again with no list open to open [`/monitor`](/user/monitor). |

Once a word is complete, the list goes away, so <kbd>enter</kbd> sends the line. A complete
command shows a **hint** instead, with what it takes: type `/afk` and the line under the prompt
reads `/afk [on|off]  Toggle whether an agent may ask you`.

The list follows the cursor. It is offered only at the end of the line, and not over a line
you brought back from [history](/user/history).

## What is not offered

- **A flow anywhere else.** A flow outside the places above is a path, and you type it:
  `/flow ./flows/mine`.
- **The task.** Everything after `$name ` is yours to write.
- **Models and accounts.** Those are chosen from lists inside `/flow`, when you set up each
  agent.

## Narrowing a long list

The menus behind the commands list flows, models, accounts, runs and fallbacks, and those
lists get long. Press <kbd>s</kbd> and type: a row stays if the letters you type appear in its
name in that order, so `o5` finds `claude-opus-5`. <kbd>esc</kbd> leaves the search first, then
the menu.

## See also

- [History](/user/history): bringing back a line you already sent
- [TUI reference](/reference/tui): every command and key

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
