---
pageClass: hmz-feature
---

# Two accounts of one CLI

A coding agent CLI signs in once per machine. humanize lets each agent run as an **account** of
its own: a subscription, an API key, or somebody's gateway. Two agents of one CLI can run as two
accounts at once, and the sign-in you use yourself is never touched. When an account runs out,
the turn carries on under the next one, in the same conversation.

<HmzAccounts />

## An account is the CLI's own sign-in, kept apart

Signing an account in runs the CLI's own login, on your terminal. What that login writes *is*
the account, kept by humanize apart from yours. humanize does not reimplement anyone's login.

A turn under the account gets that account's credentials and nothing else of it. Its sessions,
settings and installed skills are the ones the CLI already has. So the turn still leaves a
[trace](/features/tracing), still counts what it spends, and still loads your skills.

An account can also be just a key, or a gateway's address and token. Which kinds each backend
offers is on [Providers](/user/providers).

## Keys in your shell stay out of it

A CLI reads keys, tokens and endpoints from the environment, whoever set them. An
`ANTHROPIC_API_KEY` left in your shell profile would outrank the account you chose, and nothing
would look wrong until the bill came.

So a turn under an account runs with every such variable unset, unless the account itself set
it. A turn with no account runs exactly as the CLI does when you start it yourself: nothing
added and nothing taken away.

## One key, several CLIs

A vendor's key belongs to the vendor, not to one CLI. An Anthropic key works in Claude Code,
pi, opencode, mimocode and ZCode alike, so an account made for one of them can be copied to the
others. humanize spells it the way each one reads it. A subscription cannot travel: it lives in
one CLI's own credential store, in that CLI's own format.

## When an account goes down

Each account can name the account to carry on under when it fails. That makes a **chain**: a
subscription that runs out falls to a key, and a key that is refused falls to a gateway.

- **The conversation carries on.** The chain is walked inside the session that was running, so
  the agent keeps everything said so far.
- **An agent that has moved stays moved.** Its next turn starts on the account that worked.
- **A chain that loops ends** the second time it reaches an account.
- **The account this machine is signed into** can start a chain, but no chain falls back to
  it.

What happens next depends on what went wrong:

| What went wrong | What the turn does |
| --- | --- |
| Rate limit or spent quota | Retries at least once, waiting at least 30 seconds each time, then moves to the next account |
| Credentials refused | Moves to the next account at once. The one it left needs signing in again. |
| Model not on this account | Moves to the next account at once, which may have it |
| No such model | Skips the other accounts, since none of them has it, and goes to the next place |
| Connection dropped | Reconnects and retries at least once, in the same conversation |
| The CLI is not installed | Skips the other accounts and goes to the next place |

A failure humanize does not recognise gets only the tries you set for that place, then the next
account.

## When no account is left

Some failures no account can answer: a model retired this morning, a CLI that will not start.
What answers those is another **place**: another CLI, another account, another model, set as
the step after this one.

A turn that moves to another place starts a new conversation there, because no backend can take
another backend's session. That is why the account chain comes first. The agent's effort and
what it may do come across unchanged, and the flow still sees one turn.

## How it waits

You set how a place retries, and how it waits in between, in [Falling back](/user/fallback).

- **Out of the box, a place does not retry**, beyond what the table above builds in.
- **The waits are the standard ones**: constant, linear, exponential, exponential with jitter,
  and Fibonacci. The default is exponential with jitter, which keeps a flow's agents from all
  retrying on the same second.
- **No single wait is longer than a minute.**
- **A place can be given a time limit for its retries.** It is checked before each wait, so no
  retry starts once the time is spent.

## Where the detail is

- [Providers](/user/providers): making an account, signing it in, pointing it somewhere
- [Falling back](/user/fallback): the chain, the next place, and the waits
- [Providers reference](/reference/providers): every way in, every field, and adding a CLI
