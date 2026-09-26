<script setup>
import SignInWays from '../.vitepress/theme/components/user-places/SignInWays.vue'
</script>

# Providers

An **account**, or [provider](/user/concepts), is one named sign-in for one coding agent CLI,
kept apart from the CLI's own sign-in and from every other account. You make one at
`/providers`, then name it after an `@` when you pick an agent. Reach for one when an agent
should run on another subscription, key or gateway than the one you are signed in with, or
when two agents of one CLI should run as two accounts in the same run.

## Try it

In `hmz`:

1. Type `/providers`, then press <kbd>a</kbd>.
2. Choose the CLI. Each row lists the ways that CLI can be signed in:

   ![a at /providers asks which coding agent the account is for, and lists each CLI's ways
   in beside it, with a CLI of your own last](/demo/account-backends.png)

3. Choose a way, say `gateway`. Give the account a name, `deepseek`, and answer what the way
   asks. A secret shows as bullets. A way that is a login hands the terminal to the CLI's own
   login until it is done.
4. Name the account after the CLI in `-a`:

```sh{3}
hmz exec -f flame_chase \
    -a first_chaser=claude/claude-opus-5:max \
    -a second_chaser=claude@deepseek/deepseek-chat:high \
    -b cost=20 "fix the build"
```

`flame_chase` has two agents take turns on one task. Here both run the same Claude Code: the
first as you are signed in, the second as `deepseek`.

## Choosing one for an agent

::: code-group

```text [hmz exec]
-a builder=claude@work/claude-opus-5:max
           ^^^^^^ ^^^^ ^^^^^^^^^^^^^ ^^^
           CLI    account  model     effort
```

```text [at the prompt]
/flow, choose the flow, enter on a role, then its provider row:

   Select the account its turns run as

   ❯ 1. as local                  signed in as you signed it in
     2. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     3. work                      login

        add                       an account
```

:::

- An agent with no account runs **`as local`**: the CLI signed in the way you signed it in
  yourself.
- At the prompt, <kbd>a</kbd> on that list, or its `add` row, makes an account without leaving
  it. It is the same walk as `/providers`, without the question of which CLI, and the new
  account comes back chosen.
- An account belongs to one CLI. What signs in to Claude Code is not what signs in to codex, so
  the list only offers that CLI's accounts.

An agent never quietly runs as you instead. An account that is not there fails every turn of
that agent, naming it, and a bare `@` is refused before anything runs:

```console
$ hmz exec -f ralph_loop -b duration=1h \
    -a agent=claude@gone/claude-opus-5:max "…"
round 1
round 1 failed: agent: no claude provider called 'gone'
…
stopping: 3 rounds in a row answered with nothing
```

## The ways in

A **way** is one kind of sign-in: the CLI's own login, an API key, a gateway, a cloud account.
Pick a CLI to see what each of its ways asks for.

<SignInWays />

A way that runs a command hands it the terminal: its browser or device code owns the screen
until it is done, and what it writes lands in the account rather than in the CLI's own sign-in.
A way that only asks keeps your answers as the variables the CLI reads. `env` takes whichever
variables you type, one `NAME=VALUE` per line.

## Managing accounts

`/providers` lists every account under a heading per CLI: its name, the way it was made by,
and the names of the variables it sets. It never shows a value.

![/providers listing a claude account and as local, enter opening what can be done with the
account, and a asking which CLI a new account is for](/demo/accounts.gif)

<kbd>enter</kbd> on an account opens what you can do with it:

| On the menu | What it does |
| --- | --- |
| **correct what it holds** | Asks its way's questions again. Secrets are never shown back, so you type them again. |
| **sign in again** | Runs its login again. It owns the terminal while it does. |
| **falls back to** | The account a turn carries on under when this one fails. |
| **take it away** | The account and its credentials. |

Making an account and signing one in happen at once. Correcting, falling back and taking away
land when you save the menu: its `save` row, or <kbd>shift+enter</kbd> or <kbd>ctrl+j</kbd>.

Under a CLI that has accounts, the last row is `as local`: the CLI as you signed it in
yourself. humanize keeps no credentials for it, so the only thing it offers is **falls back
to**.

## One account, several CLIs

An API key belongs to the vendor, not to the CLI. An Anthropic key works in Claude Code, pi,
opencode, mimocode and ZCode alike. So when you make an account that other CLIs could run as,
humanize asks which of them to copy it to:

![after claude/shared is made: pi, opencode, mimo and zcode, each marked not installed here
yet and switched off](/demo/alike.png)

- CLIs installed here start ticked; <kbd>space</kbd> or <kbd>←</kbd>/<kbd>→</kbd> changes one.
- A copy takes **the same name**, so `claude/shared` becomes `pi/shared` and
  `opencode/shared` too, and it replaces a copy already there.
- Correcting the account asks again, so a rotated key is typed once and written over every
  copy you tick.
- Only variables travel. An account made by a login stays with its CLI.

::: tip Before you trust a rotation
The ticks follow which CLIs are installed, not which ones already hold a copy. A copy on a CLI
you did not tick keeps the old key. `/providers` shows the copies: the same name under another
CLI's heading.
:::

## Which models an account can run

Which models a turn may name depends on the subscription, key or gateway behind it, so a new
account is asked what it runs as soon as it is made. A gateway account lists what the gateway
itself serves.

The list is what the `model` row offers at `/flow`. <kbd>r</kbd> there asks again: do it when
the model you want is missing, or when a failed turn says the list is out of date. Nothing asks
again on its own.

## When an account fails

Each account can name another account of the same CLI to carry on under: **falls back to**, on
its menu. A turn that fails on one walks that chain and keeps its conversation.

```text
claude/subscription ──fails──▶ claude/key ──fails──▶ claude/gateway
```

`as local` can start a chain, but nothing falls back *to* it. How many times a failed turn is
tried again first, and moving on to another CLI or another model, are set at
[`/fallback`](/user/fallback).

## Good to know

- **Only the credentials belong to the account.** Sessions, settings and skills stay the CLI's
  own, so a turn under an account still shows up in a [trace](/user/tracing), still counts
  towards the [cost readout](/user/tally), and still has your skills.
- **Other accounts' variables are unset.** A turn under an account runs without every variable
  that CLI would read an account from, unless this account set it. An `ANTHROPIC_API_KEY` left
  in your shell profile cannot quietly win over the account you chose.

::: details From Python
Every step of the walk is a call on `Hmz().accounts`:

```python
from hmz.sdk import Hmz

accounts = Hmz().accounts
shared = accounts.make("claude", "shared", accounts.way("claude", "key"), {
    "ANTHROPIC_API_KEY": key,
})

accounts.serves(shared)                     # ('pi', 'opencode', 'mimo', 'zcode')
accounts.copies(shared, "pi")               # pi/shared, holding the same key
accounts.points("claude", "work", "shared")  # work falls back to shared
```

`make` writes an account down. For a way that runs a login, `sign_in(account, way)` runs it.
See [SDK › Accounts](/reference/sdk#accounts).
:::

## See also

- [Falling back](/user/fallback): another CLI or model when a place fails
- [Providers reference](/reference/providers)
- [TUI › The accounts themselves](/reference/tui#the-accounts-themselves)
- [SDK › Accounts](/reference/sdk#accounts)
