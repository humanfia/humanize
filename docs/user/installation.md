# Installation

Three steps: install humanize, sign in to one coding agent CLI, and check that humanize can see
it. You need **Python 3.12 or newer**.

## 1. Install humanize

::: code-group

```sh [uv tool]
uv tool install git+https://github.com/humanfia/humanize.git
```

```sh [pipx]
pipx install git+https://github.com/humanfia/humanize.git
```

```sh [pip]
pip install git+https://github.com/humanfia/humanize.git
```

:::

Each one gives you the `hmz` command. `uv tool` and `pipx` put it in an environment of its own,
on your `PATH` from every directory. `pip` installs into whichever environment is active.

### Two backends need an extra {#the-two-backends-that-are-extras}

Skip this unless you want DeepSeek Harness or Kimi Code. Each needs a Python package in
humanize's own environment:

| Extra | For |
| --- | --- |
| `hmz[dsh]` | DeepSeek Harness (`dsh`). It has no CLI to install. |
| `hmz[kimi]` | Kimi Code (`kimi`), alongside its CLI. |
| `hmz[all]` | Both. |

::: code-group

```sh [uv tool]
uv tool install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

```sh [pipx]
pipx install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

```sh [pip]
pip install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

:::

You can add one later without reinstalling humanize. The agent menu lists a backend that is
missing its extra, with the install command on its row.

## 2. Sign in to a coding agent {#signing-each-backend-in}

humanize drives a coding agent CLI that you install and sign in to yourself. One is enough.
Pick yours:

::: code-group

```sh [Claude Code]
npm i -g @anthropic-ai/claude-code
claude auth login
```

```sh [Codex]
npm i -g @openai/codex
codex login                    # no browser here? codex login --device-auth
```

```sh [Cursor Agent]
curl https://cursor.com/install -fsS | bash
cursor-agent login
```

```sh [Antigravity]
# install Google's Antigravity CLI so that `agy` is on your PATH, then:
agy                            # it asks you to sign in to a Google account
```

```sh [Grok Build]
npm i -g @xai-official/grok
grok login                     # no browser here? grok login --device-auth
```

```sh [Kimi Code]
npm i -g @moonshot-ai/kimi-code
kimi login                     # and the [kimi] extra, above
```

```sh [Qwen Code]
npm i -g @qwen-code/qwen-code
qwen                           # then /auth, and /quit once you are signed in
```

```sh [opencode]
npm i -g opencode-ai
opencode auth login
```

```sh [mimocode]
npm i -g @mimo-ai/cli
mimo auth login
```

```sh [pi]
npm i -g @earendil-works/pi-coding-agent
pi                             # then /login, and /exit once you are signed in
```

```sh [ZCode]
# Linux: install the package and add a launcher, as in "ZCode" below. Then:
zcode login                    # no browser here? zcode login --no-browser
```

```sh [DeepSeek Harness]
# no CLI: install the [dsh] extra, above, and give it a DeepSeek API key
export DEEPSEEK_API_KEY=sk-…
```

:::

If you are already signed in, there is nothing to do. humanize runs each CLI as you signed it
in, which the agent menu calls `as local`.

::: tip An API key, or two accounts of one CLI
Make an account at [`/providers`](/user/providers) inside `hmz`. It can hold a login, an API
key, or a gateway of your own, and one flow can run two accounts of the same CLI at once.
:::

## 3. Check it works {#check-what-you-have}

```sh
hmz --version
```

```console
hmz 0.1.0
```

Then open the interface in any directory:

```sh
hmz
```

The first time, humanize asks each CLI it found which models it runs. That can take a minute.
Once one has answered, the line above the prompt names the agent it would start:

```text
                  assistant · claude/claude-opus-4-8:high
─────────────────────────────────────────────────────────
❯
─────────────────────────────────────────────────────────
 ◉ chat · ~/src/demo      esc monitor · ctrl+c exit
```

If that line still reads only `assistant`, no CLI has answered: humanize found none, or the one
it found is not signed in and cannot say what it runs. Typing a task then says
`hmz: no coding agent is installed here`. humanize looks on your `PATH`, then in
`~/.local/bin`, `/usr/local/bin`, `/opt/homebrew/bin`, `/usr/bin` and `/bin`. See which ones a
shell finds:

```sh
command -v agy claude codex cursor-agent grok kimi mimo opencode pi qwen zcode
```

Leave with `/exit`. Now make your [first run](/user/first-run).

## Notes on particular backends

<div id="zcode-wants-a-launcher-of-its-own"></div>

::: details ZCode: the command line needs a launcher
ZCode's Linux package installs the desktop app. The command line is bundled inside it, so add
a launcher that runs it:

```sh
curl -fsSLO https://cdn-zcode.z.ai/zcode/electron/releases/3.11.2/linux-x64/ZCode-3.11.2-linux-x64.deb
sudo apt install -y ./ZCode-3.11.2-linux-x64.deb
printf '#!/bin/sh\nELECTRON_RUN_AS_NODE=1 exec /opt/ZCode/zcode /opt/ZCode/resources/glm/zcode.cjs "$@"\n' \
  | sudo tee /usr/local/bin/zcode >/dev/null
sudo chmod +x /usr/local/bin/zcode
zcode --version
```

A newer release is the same URL with the version changed. The `.rpm`, the `.AppImage` and the
arm64 builds are in the same directory. Without `apt`, install one of those and point the
launcher at wherever `resources/glm/zcode.cjs` landed.
:::

::: details DeepSeek Harness: the key, the models and the platforms
The `[dsh]` extra installs on Linux (x86-64 and arm64) and on macOS (arm64).

Give it a key in any one of these ways:

- `DEEPSEEK_API_KEY` in the environment, or in a `.env` file in the project.
  `DEEPSEEK_BASE_URL` points it at another endpoint.
- The key saved by dsh's own CLI, if you also have it: `dsh web`, then **Settings → Models**.
- An account at [`/providers`](/user/providers): `key` for a DeepSeek key, or `gateway` for a
  key that belongs to a proxy or another vendor, which also asks for its URL.

Until it has a key, humanize lists `dsh` but does not pick it for you. Its models are
`deepseek-v4-flash` and `deepseek-v4-pro`, at the efforts `max`, `high`, `low` and `off`:

```sh
hmz exec -f chat -a assistant=dsh/deepseek-v4-flash:high "say hello"
```

`chat` ships with humanize. A flow from a flowverse, such as `ralph_loop`, needs `hmz` opened
once first: that is what fetches flowverses, and `hmz exec` does not.

A `dsh` agent works with full access whatever its flow declares. See
[Security](/user/security).
:::

::: details Any other CLI that speaks the Agent Client Protocol
Add it at `/providers`, and it is offered beside the twelve above. See
[Many backends, one agent](/features/backends).
:::

## Where humanize keeps things

Everything humanize remembers is under `~/.humanize/`: your runs, what each directory was set
up to run, your accounts, and the flowverses it fetched. Set `HUMANIZE_HOME` to keep it
somewhere else. A project's own flows, and the runs you export from it, are in `.humanize/` in
that project. The full list is in the [CLI reference](/reference/cli).

## Uninstall

Stop any run you left running first: `hmz` in its directory, then `/exit`.

::: code-group

```sh [uv tool]
uv tool uninstall hmz
```

```sh [pipx]
pipx uninstall hmz
```

```sh [pip]
pip uninstall hmz
```

:::

To also forget everything humanize remembered, your accounts included, remove `~/.humanize`,
or wherever `HUMANIZE_HOME` points:

```sh
rm -rf ~/.humanize
```

The coding agent CLIs and their own logins stay as they are.
