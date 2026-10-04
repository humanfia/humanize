<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Security

What to check before you point a flow at work you care about, and what holds an agent back
while it works.

::: danger Nothing an agent does is put to you for approval
Every flow's agents run with approvals bypassed, whatever flow it is and whether or not you are
watching. They edit files, run commands and make commits on their own. What holds an agent back
is what its flow declares, below.
:::

::: info At a glance
- **You will** make a run you can undo, read what each role of a flow may touch, and know which
  account every turn is billed to.
- **Use it when** you are about to run a flow on a real repository, install a flow, or save
  an account.
- **You need** humanize installed, and git for the repository the flow works in.
:::

## Try it

The checklist, before a flow touches anything you care about:

<div class="u7-checklist">

- **The work can be undone.** Run in a git repository and tag where you started
  (`git tag start`): `git diff start` then shows everything the flow changed, committed or
  not, and `git reset --hard start` takes it back.
- **You have read what each role may touch.** It is in the flow's code, not in any menu.
- **You trust every flow you installed.** Listing a flow runs its code.
- **You know which account each agent runs as.** It is the `account` row of the agent, and
  every turn is billed to it.

</div>

## How it works

A flow runs its agents unattended, so the protection has to be decided before the run, not
during it. Three things decide it, and none of them is a prompt:

| What | Decided by | Where you check it |
| --- | --- | --- |
| what each agent may read, write and reach | the flow, one role at a time | the flow's code, or its page under [Flows](/flows/) |
| whose code runs at all | you, by installing a flow | `/flow`, on its Installed page |
| whose credentials a turn uses | you, on the agent's `account` row | `/flow`, and the Accounts page of `/settings` |

Git is what makes the rest safe to try: a tag before the run turns everything the agents did
into one diff you can read and one command that takes it back.

## Example: read a flow's grants before running it

You want to run [`aot`](/flows/aot), which writes a flow from a description, in a repository
you care about. First, make the run undoable:

```sh
cd ~/src/app
git status --short             # nothing uncommitted of yours to lose
git tag start
```

Then read what its roles may touch. In `hmz`, open `/flow`. If `aot` is not installed yet,
press **Install more…**, open `official` and install it, then come back to **Installed**. Put
the cursor on `aot`, <kbd>tab</kbd> to **Copy here**, and press <kbd>enter</kbd>:

<Term title="hmz · /flow">

<pre>  <span class="m">hmz › /flow ›</span> <span class="p b">Installed</span>
  <span class="m">…</span>
  <span class="p">╭────────────────────────────────────────────────────────────────────────╮</span>
   <span class="p">official</span>
   <b>aot</b>                                                               <span class="a">0.1.0</span>
     <span class="m">Writes a flow from a description: drafted, loaded, smoke-run, revie…</span>

   <span class="p">local</span> <span class="n">1</span>
   <b>@local/aot</b>
     <span class="m">Writes a flow from a description: drafted, loaded, smoke-run, revie…</span>
  <span class="p">╰────────────────────────────────────────────────────────────────────────╯</span>
   <span class="m">copied to .hmz/flows/aot -- you can edit it, and aot now points to it</span> <span class="n">2</span>

    Install more…   Update   Uninstall   <span class="sel"> Copy here </span>   Search…       Save

  <b>enter</b> copy   <b>←/→</b> move   <b>tab</b> list   <b>esc</b> back</pre>

</Term>

Now the flow is a directory in your project, and its grants are one search away:

```sh
grep -rn "_permission" .hmz/flows/aot
```

```console
.hmz/flows/aot/__init__.py:51:    _permission = Permission(local=PermissionKind.READ, online=PermissionKind.NONE)
```

What to look at, by number:

1. **`local`** appears under `official`: the copy is this project's own flow now, and no
   update to the installed `aot` changes what you run.
2. **`aot now points to it`**: `$aot` and `-f aot` in this directory run your copy, which is
   the code you just read.

And in the search result: one role, the critic, declares `local=READ` and `online=NONE`. It
reads the draft, never writes, and cannot reach the web. Every role that declares nothing, here
all the others, runs at the default in the table below: it writes this directory and nothing
else of yours.

### Check it worked

- `git tag --list start` prints `start`.
- After the run, `git diff start` shows everything the flow changed, and nothing outside the
  repository was written by a role at the default grant.
- On `/flow`, each role's `account` row reads the account you meant, `as local` or one of
  yours.

## What a flow lets its agents touch

A flow declares a permission on each role it drives. You don't choose it at the prompt, so
read it in the flow before you run the flow. It has four scopes:

| Scope | What it covers | A role that says nothing gets |
| --- | --- | --- |
| `local` | the working directory of the session | `ALL`: read and write |
| `user` | the rest of the home directory the agent runs as | `READ` |
| `system` | everything else on the machine | `READ` |
| `online` | the CLI's own web search and fetch | `ALL` |

What that comes to in practice:

- **Every scope is enforced** on the agent and on every command it runs, by Landlock on
  Linux and by Seatbelt on macOS. An agent at the default writes its working directory and nothing else of yours:
  its CLI's own settings, login and sessions, and a temporary directory of its own. On
  macOS its login includes the login keychain, which is where Claude Code keeps it.
- **A read-only role** (`local` of `READ` or `NONE`) also runs in its CLI's read-only mode.
- **`online` of `NONE`** cuts the network, except the hosts the agent's model and login are
  at. The CLI's web tools are switched off too, where it can be told.
- **Work in a container or on an ssh host is fenced there too.** Every command the agent
  runs on that machine is held by that machine's own Landlock or Seatbelt, around its own
  working directory and home.
- **A grant that cannot be held is refused, not widened.** On a Linux kernel without
  Landlock, on a Mac where humanize already runs inside another sandbox, and for work on a
  machine like either, a role runs only with `ALL` in every scope.
- **Some ways out remain.** Neither Landlock nor Seatbelt governs Unix sockets, so an agent
  can still talk to a socket another program listens on, a docker daemon's among them; on
  macOS a system service reached over Mach is the same. With `online` of `NONE` on macOS, a
  program the agent runs may serve on any address, not only loopback. And whatever an agent
  can write, a later run can read.

[Permissions](/user/permissions) lists what the official flows declare, and how each CLI holds
to it.

## Listing a flow runs its Python

A flow is a directory of Python, and humanize runs it to find out what it is. Opening `/flow`,
or naming a flow after `$` at the prompt, runs every flow humanize lists: the ones built in,
the ones you installed, this project's and yours.

Installing a flow from a [flowverse](/weaver/flowverses) therefore trusts the repository it
comes from with this machine, the way installing a package does: install only the flows you
would install as one. Adding a flowverse runs nothing: it is an index of releases, and holds no
code. `official` is always there: it is humanize's own, at
[humanfia/flowverse](https://github.com/humanfia/flowverse), and its maintainers review every
release it lists, which lowers the risk without removing it.

An installed flow is the exact commit its release names, and stays that commit until you update
it: `hmz` fetches the flowverses each time it opens, and only says when a newer release is
listed. To keep a flow as you read it whatever you install later, put the cursor on it in
`/flow` and press **Copy here**, as in the example: it is copied into this project's own flows,
and the flow's name here runs the copy.

## Where your credentials are

| An agent runs as | humanize keeps |
| --- | --- |
| `as local`, the default | nothing. The CLI reads its own login, where it always keeps it. |
| a login made on the Accounts page of `/settings` | the files that CLI wrote when it signed in, under `~/.hmz/providers/<cli>/<name>/` |
| a key or a gateway made on the Accounts page of `/settings` | what you typed, the key and a gateway's URL, in `provider.json` in that same directory |

- Those directories and files are readable by you alone.
- The Accounts page of `/settings` names the variables an account sets and never shows their
  values. A secret you type is drawn as bullets.
- A turn run as an account from `/settings` has the keys other accounts would use unset, so a
  key left in your shell profile cannot take its place.
- Removing `~/.hmz` removes every account. The CLIs' own logins stay where they are.

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
- **A `dsh` agent works with full access** whatever its flow declares.

## Troubleshooting

### A role is refused before the run starts

Its grant cannot be held here: on a kernel without Landlock, on a Mac where humanize runs
inside another sandbox, or on a machine like either, only a role with `ALL` in every scope
runs. And a `cursor-agent` role with `online` of `NONE` is refused on every machine, because
Cursor's web tools cannot be switched off. Run the flow on Linux with Landlock or on macOS
outside any other sandbox, or choose another CLI for the role. See
[Permissions](/user/permissions).

### The flow changed things I did not expect

Read them all with `git diff start`, and take them back with `git reset --hard start`. Commits
the agents made are undone too, since the tag is older. Files outside the repository are not
in git: a role at the default grant cannot write there, but one granted `user` or `system` of
`ALL` can.

### A flow I read last week behaves differently

It was updated: an update installs the newer release over the one you read. Choose the release
you read on the flow's page in `/flow` (**Switch to**), then **Copy here** to keep it as it
is.

### A turn was billed to the wrong account

The agent's `account` row decides it. Open `/flow`, <kbd>enter</kbd> on the role, and check
`account`. An account that does not exist fails every turn of that agent, naming it; it never
falls back to `as local` quietly.

## Reporting a vulnerability

Report it privately, never in a public issue:
[SECURITY.md](https://github.com/humanfia/humanize/blob/main/SECURITY.md) says how, what counts
as a vulnerability, and when you will hear back.

## Next steps

- [Permissions](/user/permissions): what each official flow grants, and how each CLI holds it.
- [Accounts](/user/settings#accounts): API keys, gateways and second logins, kept apart.
- [Flowverses](/weaver/flowverses): what installing a flow means, and publishing your own.
- [Containers](/user/containers): put the work somewhere a mistake cannot reach you.

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
