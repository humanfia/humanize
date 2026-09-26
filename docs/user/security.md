# Security

Three things about humanize are load-bearing and surprising. Read them before you point one at
a repository you care about.

## The flow decides what its agents may do to your workspace

humanize drives coding agents unattended, as
[flowbench](https://humanfia.ai/projects/flowbench) does, and the only thing between an agent
and your workspace is the flow driving it. **Nothing a flow's agent does is put to anybody for
approval**: every session runs at its CLI's nothing-asked mode. What limits it is the
[permission](/user/permissions) its flow declares on the role, and the hooks the flow hangs on
it:

```python
from hmz.flows import Agent, Permission, PermissionKind


class Builder(Agent): ...                                           # may change its workdir


class Reviewer(Agent):
    _permission = Permission(local=PermissionKind.READ)              # may only read
```

The default — what a role that says nothing gets — is an agent that edits files, runs commands
and makes commits in its workdir without asking, and **a flow you did not read declares it by
saying nothing**. It is the flow's to say and not the line's: what an agent may do is a thing
about the work, so read a flow before you run it.

**`user` and `system` are not fenced.** An agent that may write its workdir may write anywhere
its user can, whatever the rest of its permission says: the sandboxes that could fence it cannot
start in most containers, so humanize does not use them. A flow calling another can only narrow
what it hands on — the called flow gets exactly what it declared, and an agent held narrower
than a role needs is refused rather than widened.

[`/afk`](/user/afk) governs whether you are there to answer a *question*. It does not govern
whether the agent may act — the permission its flow declared does.

Drive a flow only in a workspace you are willing to have rewritten.

## A flow is Python, and reading one means running it

Choosing a flow is running it: humanize imports the flow's `__init__.py` to find the `@flow`
in it, whether the flow was chosen at [`/flow`](/reference/tui#choosing-a-flow) or named on an
`hmz exec -f` line. Listing what a [flowverse](/weaver/flowverses) holds imports **every** file
in its `flows/`.

So adding a flowverse trusts that git repository with this machine, exactly as installing a
package does. Add the ones you would clone and run.

`official` is always there — `chat` ships with the package, and the rest is
[humanfia/flowverse](https://github.com/humanfia/flowverse). The interface fetches it, as it
fetches every flowverse, in the background each time it opens.

## An `hmz internal anchor` port is equivalent to a shell on that machine

[Remote execution](/user/remote-execution) has three transports. Two of them need no open port
at all:

| Transport | What it is |
| --- | --- |
| `ssh://host` | bootstrapped over your own ssh. Nothing listens. |
| `docker://container` | over `docker exec`. Nothing listens. |
| `tcp://host:port` | an `hmz internal anchor serve` listening there. |

For the third, `--export` bounds which files a request may *name*. It does **not** confine the
commands that request can run. Anyone who can reach the port can run anything on that machine
as the user serving it.

- Give `--token` a real secret.
- humanize refuses outright to listen on anything but loopback without a token.
- Prefer `ssh://` or `docker://`.

```sh
hmz internal anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

## What humanize does not hold

- **No API key.** humanize drives the CLI you already logged in. The credential goes from that
  CLI to its own provider.
- **No transcript of its own.** The backends write their own logs. An
  [epic](/user/concepts#epic) records only which sessions belonged to which agent.
- **No values from a provider.** [`/providers`](/reference/tui#the-accounts-themselves) draws
  every account under the CLI it is for, with the way it was made by and the names of the
  variables it sets. It never draws what those variables are. A secret you type at the prompt
  appears as bullets and never shows again.

Provider credentials are copies of the CLI's own credential files. humanize keeps them at
`0600` in a directory at `0700` under `~/.humanize/providers/`. A turn under a provider runs
with the *other* accounts' variables unset. So an `ANTHROPIC_API_KEY` left in a shell profile
cannot silently outrank the account the agent was told to run as.

While a turn is running, the credential it reads is also held in memory — a directory of that
turn's own under `/dev/shm`, at `0700`, holding files at `0600`, under a name that cannot be
guessed. `/dev/shm` is shared between everyone on the machine, so the directory is made rather
than opened: a name somebody else got in first with is refused and another taken, and nobody
else can list it or read what is in it. It is unlinked when the turn ends — by the turn itself
where it exits, and by whoever ended it where it was killed, since a killed process runs no
teardown of its own. Anything a killed *driver* leaves behind is swept away by the next turn on
that machine, and `/dev/shm` is empty again after a reboot either way.

## Reporting something

Open an issue at [humanfia/humanize](https://github.com/humanfia/humanize/issues). If it is a
vulnerability rather than a bug, say so in the title. Leave the details out of the public
thread.
