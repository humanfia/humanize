<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Falling back — `/fallback`

When a turn cannot run where it is (the model was retired, the CLI will not start, the whole
account is rate-limited), `/fallback` sends it somewhere else: another CLI, another account,
or another model. Each of those places is written `CLI[@ACCOUNT]/MODEL`, for example
`claude@work/claude-opus-5`.

It is the second of two fallbacks, and the one that costs the conversation:

| | Another account of the same CLI | Another place |
| --- | --- | --- |
| **Set in** | [`/providers`](/user/providers) | `/fallback` |
| **Answers** | a subscription used up, a key refused | a model retired, a CLI missing, a whole account throttled |
| **The conversation** | carries on where it was | starts over, in a new session at the new place |
| **Tried** | first | once no account of that CLI is left to try |

## Try it

```
/fallback
```

<Term title="/fallback">

<pre><span class="p b">Fallback</span>
<span class="m">Where a turn goes when the place taking it cannot take it at all.
A place is a CLI, an account and a model.</span>

<span class="p">❯</span> <span class="d">1.</span> <span class="p">claude@work/claude-opus-5</span>  <span class="m">2 more tries, linear · falls back to codex/gpt-5.6</span>
  <span class="d">2.</span> <span class="p">codex/gpt-5.6</span>              <span class="m">falls back to dsh/deepseek-v4-flash</span>

     <span class="p">add</span>                        <span class="m">a step</span>
     <span class="p">save</span>                       <span class="m">these steps</span>

<span class="d">enter what happens · a add · shift+enter/ctrl+j save · esc close · s search</span></pre>

</Term>

1. Press <kbd>a</kbd>, or choose **add**. Pick the place that fails: its CLI, then one of its
   accounts, then one of the models it runs.
2. Pick the place that takes its turns, the same way.
3. Save: choose **save**, or press <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd>. Leaving with
   <kbd>esc</kbd> asks whether to save or discard.

<kbd>enter</kbd> on a step asks three things about it: where it **falls back to**, how often
a failed turn is **taken again** there first, and whether to **take it away**.

Steps chain. Above, a turn that fails at `claude@work/claude-opus-5` is tried twice more
there, then moves to `codex/gpt-5.6`, and if it fails there too, on to
`dsh/deepseek-v4-flash`.

## Trying again

**taken again** sets how a failed turn is retried at this place before it moves on. Step
each value with <kbd>←</kbd> <kbd>→</kbd> or <kbd>space</kbd>:

| Setting | Choices | What it is |
| --- | --- | --- |
| tries | none, 1, 2, 3, 5, 8, 13, 21 | how many more times a failed turn is taken here |
| policy | the six below | how long to wait between tries |
| timeout | as long as it takes, 30s, 1m, 5m, 15m, 60m | the longest the retrying may go on |

Nothing is retried unless you set **tries**: a prompt the model refused is refused every time,
and only you know which of your places fail the other way. The exceptions are the failures in
the next section where another go is the answer.

| Policy | Waits before the 2nd, 3rd, 4th… try |
| --- | --- |
| `none` | no wait at all |
| `constant` | 1s, 1s, 1s |
| `linear` | 1s, 2s, 3s |
| `exponential` | 1s, 2s, 4s, 8s |
| `exponential-jitter` <Badge type="tip" text="default" /> | anywhere from 0 up to the exponential wait. Use it when several agents fail at once, so they do not all retry on the same second. |
| `fibonacci` | 1s, 1s, 2s, 3s, 5s |

No wait is ever longer than 60 seconds. The timeout is checked before each wait, so a retry
never starts once its time is up.

## What went wrong

A failed turn first works out what kind of failure it was, from what the CLI said and how it
exited. Each kind gets its own answer:

| What happened | Tried again here | Then goes to |
| --- | --- | --- |
| **Too many requests**: 429, a quota spent, `RESOURCE_EXHAUSTED`, `overloaded` | at least once, after 30 s or more | account → place |
| **Credentials refused**: 401, an expired login, a revoked key | never | account → place |
| **Model refused** for this account: `key not allowed to access model` | never | account → place |
| **No such model**: 404, a retired model | never | **place** |
| **CLI not installed** | never | **place** |
| **Sandbox would not start**: `bwrap: setting up uid map: Permission denied` | never | **place** |
| **Its own store was busy**: opencode's `database is locked` | at least 3 times, 1 s apart | account → place |
| **Lost the connection**: `ECONNRESET`, 502, 503, a timeout | at least once, in the same conversation | account → place |
| **Killed**: out of memory, `SIGKILL` | at least once, after 1 s | account → place |
| **Anything else** | as the step says | account → place |

"At least" because a step that asks for more tries gets them; "never" holds whatever the
step asks. **account** is the next [account](/user/providers) of the same CLI, in the same
conversation. **place** is the next place on the chain, in a new conversation, once no account
is left or none would help. An agent that has moved to another account stays there for its
later turns. If there is nowhere left, the turn fails as it would with no step written.

Each move shows in the transcript as it happens, even with [`/details`](/user/details) off, so
a run that is recovering does not look hung:

```
claude is rate-limited (this account has spent its quota; another one, or a wait, is what answers it); trying again in 30s (1 of 1)
claude is rate-limited (this account has spent its quota; another one, or a wait, is what answers it); carrying on as work
```

Where there is something to do about it, the line says so in brackets: an account that needs
signing in again, a CLI to install, or a model list to refresh with <kbd>r</kbd>. Under
`hmz exec --json`, these lines are `notice` events.

::: details Antigravity (agy) fails with nothing said
agy exits with `Agent execution terminated due to error` and writes the real status only to
its own log, `~/.gemini/antigravity-cli/cli.log` or `~/.gemini/antigravity-cli/log/cli-*.log`.
humanize reads the end of that log when the output says nothing, so a rate-limited agy turn is
still treated as one. Look there yourself when an agy turn fails with no reason given.
:::

## What comes across the step

The step decides three things: the CLI, the account and the model. Everything else about the
agent comes along unchanged:

- its effort, on the nearest rung the new CLI has;
- its permission level, and whether it may search the web;
- the skills and callbacks the flow gave it;
- the run's budget, which goes on counting.

Settings that only one CLI understands come along when the step stays on the same CLI, and
are left behind when it moves to another.

## What it will not do

- **Carry the conversation.** The next place starts a new conversation and reads the
  repository, not the history. That conversation is then kept for the rest of the run, so a
  loop that moved is one conversation there, not a new one every round.
- **Go round in circles.** A chain stops at the first place it has already visited, and a
  place cannot fall back to itself.
- **Fork.** A place has one next place. Writing a new step for it replaces the old one.
- **Drop a setting quietly.** If the next CLI cannot be told something this agent was told,
  such as web search off, or cannot take the flow's callbacks, the turn fails where it is
  rather than move.
- **Retry what no retry can fix.** A prompt longer than the model's context window fails
  once, whatever the chain says.

::: details From Python
The steps you save at the prompt are the ones `Hmz().fallbacks` reads and writes:

```python
from hmz.sdk import Hmz

falls = Hmz().fallbacks
falls.points("claude@work/claude-opus-5", "codex/gpt-5.6")
falls.points("codex/gpt-5.6", "dsh/deepseek-v4-flash")
falls.retrying("claude@work/claude-opus-5", 2, "linear", 0)  # tries, policy, timeout in s
falls.chain("claude@work/claude-opus-5")
# ['claude@work/claude-opus-5', 'codex/gpt-5.6', 'dsh/deepseek-v4-flash']
falls.clear("claude@work/claude-opus-5")
```

The rest is in the [SDK reference](/reference/sdk).
:::

## See also

- [Providers](/user/providers): the accounts an agent runs as, and the chain between them
- [Accounts, drawn](/features/accounts): the account chain and its waits, step by step
- [Unattended runs](/user/unattended): where a place to fall back to earns its keep
- [TUI reference](/reference/tui): the `/fallback` menu, row by row

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
