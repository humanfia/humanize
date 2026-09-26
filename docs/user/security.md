# Security

What to check before you point a flow at work you care about.

::: danger Nothing an agent does is put to you for approval
Every flow's agents run with approvals bypassed, whatever flow it is and whether or not you are
watching. They edit files, run commands and make commits on their own. What holds an agent back
is what its flow declares, below.
:::

<div class="u7-checklist">

- **The work can be undone.** Run in a git repository and tag where you started
  (`git tag start`): `git diff start` then shows everything the flow changed, committed or
  not, and `git reset --hard start` takes it back.
- **You have read what each role may touch.** It is in the flow's code, not in any menu.
- **You trust every flowverse you added.** Listing a flow runs its code.
- **You know which account each agent runs as.** It is the `provider` row of the agent, and
  every turn is billed to it.

</div>

## What a flow lets its agents touch

A flow declares a permission on each role it drives. You don't choose it at the prompt, so
read it in the flow before you run the flow. It has four scopes:

| Scope | What it covers | A role that says nothing gets |
| --- | --- | --- |
| `local` | the working directory of the session | `ALL`: read and write |
| `user` | the rest of the home directory the agent runs as | `READ` |
| `system` | everything else on the machine | `READ` |
| `online` | the CLI's own web search and fetch | `NONE` |

What that comes to in practice:

- **An agent that may write its working directory may write anything its user can.** `user` and
  `system` are not enforced once `local` is `ALL`.
- **A read-only role** (`local` of `READ` or `NONE`) runs in its CLI's read-only mode. It can
  still read outside its working directory.
- **`online` of `NONE`** turns off the CLI's web tools where the CLI can be told to. It is
  ignored by cursor-agent, pi and agy, and a shell command the agent runs reaches the network
  either way.
- **DeepSeek Harness** (`dsh`) and CLIs added over the Agent Client Protocol run every role
  with full access, whatever the flow declares.

[Permissions](/user/permissions) shows how a flow declares one.

## Listing a flow runs its Python

A flow is a directory of Python, and humanize runs it to find out what it is. Opening `/flow`,
or naming a flow after `$` at the prompt, runs every flow humanize lists: this project's,
yours, and every flowverse's.

Adding a [flowverse](/weaver/flowverses) therefore trusts that git repository with this
machine, the way installing a package does. Add the ones you would clone and run. `official` is
always there: it is humanize's own, at
[humanfia/flowverse](https://github.com/humanfia/flowverse).

humanize fetches every flowverse again each time `hmz` opens, so a flow you read last week may
have changed. To keep one as it is, press <kbd>f</kbd> on it in `/flow`: it is copied into this
project's `.humanize/flows/`, where nothing fetches it, and runs as `$local/<flow>`.

## Where your credentials are

| An agent runs as | humanize keeps |
| --- | --- |
| `as local`, the default | nothing. The CLI reads its own login, where it always keeps it. |
| a login made at `/providers` | the files that CLI wrote when it signed in, under `~/.humanize/providers/<cli>/<name>/` |
| a key or a gateway made at `/providers` | what you typed, the key and a gateway's URL, in `provider.json` in that same directory |

- Those directories and files are readable by you alone.
- `/providers` names the variables an account sets and never shows their values. A secret you
  type is drawn as bullets.
- A turn run as an account from `/providers` has the keys other accounts would use unset, so a
  key left in your shell profile cannot take its place.
- Removing `~/.humanize` removes every account. The CLIs' own logins stay where they are.

How an account's credentials reach a turn is in the [Providers
reference](/reference/providers).

## Other things worth knowing

- **Reporting.** humanize reports what goes wrong to its developers only if you said yes when
  it first asked. A report carries more than a crash; [Reporting](/user/reporting) lists what
  is sent and what never is.
- **A remote target served over TCP** is a shell on that machine for anyone who can reach the
  port. Give it a real token, or prefer `ssh://` and `docker://`. See
  [Remote execution](/user/remote-execution).
- **`/afk` is about questions, not actions.** It decides whether a flow may ask you something.
  It never makes an agent ask before it acts.

## Reporting a vulnerability

Open an issue at [humanfia/humanize](https://github.com/humanfia/humanize/issues). Say in the
title that it is a vulnerability, and leave the details out of the public thread.

<style scoped>
kbd {
  display: inline-block;
  padding: 0 6px;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-mono);
  font-size: 0.85em;
  line-height: 1.6;
  white-space: nowrap;
}
.u7-checklist ul {
  list-style: none;
  padding-left: 0;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg-soft);
  padding: 12px 16px;
}
.u7-checklist li {
  position: relative;
  padding-left: 1.9em;
  margin: 8px 0;
}
.u7-checklist li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.3em;
  width: 1.05em;
  height: 1.05em;
  border: 2px solid var(--vp-c-brand-1);
  border-radius: 4px;
}
</style>
