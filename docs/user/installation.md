# Installation

## What you need

| | |
| --- | --- |
| **Python 3.12 or newer** | 3.12, 3.13 and 3.14 are the ones CI runs the tests on, on Linux and macOS. |
| **At least one supported backend** | `agy`, `claude`, `codex`, `cursor-agent`, `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen` or `zcode` on your `PATH` — or nothing on it at all, if you take the [`[dsh]` extra](#the-two-backends-that-are-extras) instead: DeepSeek Harness is a Python package, and wants only a DeepSeek API key. |
| **A project you are willing to have rewritten** | Read [Security](/user/security) first. |

Nothing else, and no tutorial needs more. Two features do: [a container of the agent's
own](/user/containers) wants `docker`, and [remote execution](/user/remote-execution) wants
Linux on x86-64 or aarch64 here plus `python3` on the far machine.

## Install humanize

::: code-group

```sh [pip]
pip install git+https://github.com/humanfia/humanize.git
```

```sh [pipx]
pipx install git+https://github.com/humanfia/humanize.git
```

```sh [uv tool]
uv tool install git+https://github.com/humanfia/humanize.git
```

```sh [from a checkout]
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync
```

:::

We recommend `pipx` or `uv tool`: both give `hmz` an isolated environment of its own and put
it on your `PATH` from every directory, whereas `pip` installs into whichever environment is
active at the time.

Whichever way, the command is `hmz`:

```sh
hmz --version
```

```console
hmz 0.1.0
```

![hmz --version, and hmz --help: the one command there is, and what naming no command
opens](/demo/cli.gif)

From a checkout with `uv sync`, the command lives in that checkout's environment. Run `uv run
hmz`, or activate `.venv` first.

### The two backends that are extras

Every backend but two is a CLI you install yourself, and humanize carries nothing for it. These
two also want a package in humanize's own environment, so each is an extra and an install that
drives neither carries neither:

| | |
| --- | --- |
| `[dsh]` | DeepSeek Harness' Python SDK and the runtime its turns are taken on. There is no CLI to install; it still needs an API key — see [Signing each backend in](#signing-each-backend-in). |
| `[kimi]` | The websocket client Kimi Code's app server is read over. The `kimi` CLI is still yours to install. |
| `[all]` | Both of them. |

::: code-group

```sh [pip]
pip install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

```sh [pipx]
pipx install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

```sh [uv tool]
uv tool install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

```sh [from a checkout]
uv sync --all-extras
```

:::

Neither has to be decided now. A backend whose extra is missing stays in the agent picker with
the line that adds it written on its row, and that line installs the package into whichever
environment humanize is running in — so adding one later is not reinstalling humanize.

## Check what you have

humanize can run the backends installed in its environment. Check the CLI backends with:

```sh
command -v agy claude codex cursor-agent grok kimi pi qwen opencode mimo zcode
```

A CLI backend humanize cannot find is not offered. It looks on your `PATH` first, then where an
installer would have put one — `~/.local/bin`, `/usr/local/bin`, `/opt/homebrew/bin`,
`/usr/bin`, `/bin` — so a backend installed on this machine is offered even when whatever
started `hmz` handed it a `PATH` of its own, as a notebook kernel, a service or a runtime
platform's launcher does.

### ZCode wants a launcher of its own

ZCode's Linux package is the desktop app, and the command line is bundled inside it with no
launcher. Installing the package puts the **Electron app** on your `PATH` as `zcode`, which on
a machine with no display exits before it draws anything — so a third step is needed before
`zcode` is the CLI humanize drives:

```sh
curl -fsSLO https://cdn-zcode.z.ai/zcode/electron/releases/3.11.2/linux-x64/ZCode-3.11.2-linux-x64.deb
sudo apt install -y ./ZCode-3.11.2-linux-x64.deb
printf '#!/bin/sh\nELECTRON_RUN_AS_NODE=1 exec /opt/ZCode/zcode /opt/ZCode/resources/glm/zcode.cjs "$@"\n' \
  | sudo tee /usr/local/bin/zcode >/dev/null
sudo chmod +x /usr/local/bin/zcode
```

The launcher runs the bundled command line through the app's own Electron binary in Node mode,
so it wants no system `node` and moves with the package it came from. `/usr/local/bin` comes
before `/usr/bin`, so that is the `zcode` a shell finds, for any user; the desktop app is still
`/opt/ZCode/zcode` for anyone with a screen to run it on. Check it with `zcode --version`.

The vendor publishes no `latest` URL: a newer release is the same path with the number changed,
and the `.rpm`, the `.AppImage` and the arm64 builds sit in that same directory under their own
names. On a distribution without `apt`, install the `.rpm` or unpack the `.AppImage` and point
the launcher at wherever `resources/glm/zcode.cjs` landed.

The two backends behind extras stay in the list of CLIs an agent may be set to when their extra
is missing, so that each can show the line that adds it — DeepSeek Harness always, Kimi Code
once its CLI is here. Each becomes selectable when its import succeeds:

```sh
python -c 'import deepseek_harness; print("[dsh] installed")'
python -c 'import websockets; print("[kimi] installed")'
```

If none of the CLI backends and neither extra is installed, `hmz` says `no coding agent is
installed here` and does nothing else — see
[Troubleshooting](/user/troubleshooting#no-coding-agent-is-installed-here).

## Signing each backend in

Each CLI logs in its own way. humanize never sees the credential:

| Backend | Signing in |
| --- | --- |
| Claude Code | `claude auth login` |
| Codex | `codex login` |
| Kimi Code | `kimi login` |
| pi | `/login`, inside `pi` |
| opencode | `opencode auth login` |
| mimocode | `mimo auth login` |
| ZCode | `zcode login` |
| DeepSeek Harness | a DeepSeek API key saved by dsh, stored from an agent's `provider` row, or supplied as `DEEPSEEK_API_KEY` |

DeepSeek Harness is a developer preview and comes as the **`[dsh]` extra**:
`deepseek-harness-sdk>=0.1.1rc1,<0.1.2` and its bundled runtime, whose wheels are published
for Linux on x86-64 or arm64 and macOS on arm64 and nowhere else — an ordinary dependency
would be a machine humanize could not be installed on at all, for the sake of a backend
nobody there runs. The ceiling is not caution about a preview but a wall: 0.1.2a3 redesigned
the configuration this driver is written against, and the class it replaced it with refuses a
keyword it does not know. The `dsh` CLI is not required.

It signs in with a key rather than a login, and there are two places to keep that key. For
dsh's own credential store, run `dsh web`, open **Settings -> Models**, enter the DeepSeek key
and save it; then set an agent's `cli` row to `dsh` and leave its `provider` row on `as local`.
That reads dsh's normal configuration sources — the saved key and any `llm-deepseek.baseURL` in
`$DSH_HOME/settings.yaml`, then its environment layers. `$DSH_HOME` defaults to `~/.dsh`.

For a separate key in humanize's provider store, choose `dsh` on the `cli` row, press enter on
the `provider` row and **a** in the list of accounts, choose `key`, and enter an account name
and the key. The same account is made from the prompt at
[`/providers`](/reference/tui#the-accounts-themselves), where **a** asks which CLI it is for
before the same walk — `key`, then a name and the key. Either way the key is asked for rather
than typed on a line: it is drawn as bullets as you enter it, goes straight into a credential
store, and is never shown back.

Choose `gateway` instead of `key` where the key belongs to a proxy, a router or another vendor
rather than to DeepSeek: it asks for that endpoint as well as the key, and the account then
carries both. A `key` account is sent to `https://api.deepseek.com`, which is the adapter's own
default and refuses every key but DeepSeek's own, so a gateway key stored as a `key` account is
a turn that fails to authenticate. The account's own endpoint is also what its model list comes
from, so the names offered are the ones that endpoint actually serves.

An agent that uses that stored account is written with `@deepseek`:

```sh
hmz exec -f chat -a dsh@deepseek/deepseek-v4-flash:high "hello"
```

Alternatively, set the key and optional endpoint in the environment before starting `hmz`:

```sh
export DEEPSEEK_API_KEY=sk-…
export DEEPSEEK_BASE_URL=https://api.deepseek.com
hmz
```

Use either official model id at one of its three efforts:

```sh
DEEPSEEK_API_KEY=sk-… hmz exec -f ralph_loop \
    -a dsh/deepseek-v4-flash:high "fix the failing tests"
```

The other official model is `deepseek-v4-pro`. The efforts are `max`, `high` and `off`. The
current SDK exposes no per-session permission or skill controls, so DeepSeek Harness can only
fill a place the flow declared `bypass` for, or declared no rung for at all.

To run one CLI as **more than one** account at a time, use [providers](/user/providers). It is
a separate store, made at [`/providers`](/reference/tui#the-accounts-themselves) rather than by
signing the CLI in twice.

## Where humanize keeps things

Nothing is written until something needs it.

| Path | |
| --- | --- |
| `~/.humanize/epics/` | one directory per run: the flow, the agents, every session opened, and the [trace](/user/tracing) gathered of it afterwards |
| `~/.humanize/settings.yaml` | what each project was last set up to run |
| `~/.humanize/history.jsonl` | what has been typed at the prompt |
| `~/.humanize/flowverses/` | the [flowverses](/weaver/flowverses) fetched here |
| `~/.humanize/providers/` | the [accounts](/user/providers), `0600` in a `0700` directory |
| `.humanize/` in a project | exported transcripts, and this project's own flows |

`HUMANIZE_HOME` moves the first five somewhere else. The full list is in the [CLI
reference](/reference/cli#files).

## Uninstall

```sh
pip uninstall hmz          # or: uv tool uninstall hmz
rm -rf ~/.humanize         # everything it remembered, accounts included
```

Removing `~/.humanize` removes the provider credential stores with it. It does not touch the
coding agent CLIs or their own logins.

## Next

The [quickstart](/#run-a-flow) goes from here to a run you can read back.
