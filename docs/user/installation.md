<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Installation

Humanize comes two ways. **Humanize Desktop** is an app for macOS and Windows: download it,
open it, and it sets up everything else itself. **Humanize CLI** is the `hmz` command, for
macOS, Linux, and Windows through WSL: the terminal interface, `hmz web` and `hmz exec`. The app
runs the CLI underneath, so with the app you get both.

Either way, Humanize drives a coding agent CLI you already use, such as Claude Code or Codex,
under your own login, so you also [sign in to one](#signing-each-backend-in).

::: info At a glance
- **You will** have Humanize Desktop or the `hmz` command, and at least one coding agent it can
  drive.
- **Use it when** you are setting Humanize up on a machine for the first time, or adding a
  backend to one that has it.
- **You need** macOS 11 or newer, Windows 10 or 11 with WSL 2, or Linux; and `npm` for most of
  the coding agent CLIs. The CLI on its own needs Python 3.12 or newer, which uv fetches for you.
:::

| | Humanize Desktop | Humanize CLI |
| --- | --- | --- |
| **Platforms** | macOS, Windows (with WSL) | macOS, Linux, Windows (in WSL) |
| **You get** | every epic in an app window, notifications, self-updates | `hmz`, `hmz web` and `hmz exec` in a terminal |
| **Install** | [download the app](#desktop) | [`uv tool install hmz`](#cli) |

## Humanize Desktop {#desktop}

Download the installer for your platform from the
[latest release](https://github.com/humanfia/humanize/releases/latest), or from
[humanfia.ai](https://humanfia.ai/projects/humanize#get-started), which picks it for you.

### macOS {#macos}

1. Download `humanize-<version>-macos-universal.dmg`. It runs on Apple silicon and Intel, on
   macOS 11 or newer.
2. Open it, and drag **Humanize Desktop** onto **Applications**.
3. Open Humanize Desktop from Applications. The first time, macOS stops it: see
   [The first time it opens](#the-first-time-it-opens).

#### The first time it opens {#the-first-time-it-opens}

Humanize Desktop is not yet signed with an Apple Developer ID, so the first time you open it,
macOS says it cannot check it and offers only **Done** or **Move to Trash**. Choose **Done**,
then either:

- open **System Settings → Privacy & Security**, scroll to the message about Humanize Desktop,
  and click **Open Anyway**; or
- in a terminal, take the quarantine off the app:

  ```sh
  xattr -dr com.apple.quarantine "/Applications/Humanize Desktop.app"
  ```

Either is once: macOS remembers it, until you install the app again.

### Windows {#windows}

On Windows, Humanize runs in [WSL](https://learn.microsoft.com/windows/wsl/), and so do your
repositories and coding agent CLIs. The app is the window onto it.

1. Install WSL, if you have not. In PowerShell:

   ```powershell
   wsl --install
   ```

   This installs WSL 2 and Ubuntu; restart when it asks, and make your Linux user. Any
   distribution will do, as long as it is the default one: `wsl --list --verbose` marks it with
   `*` and shows its version as `2`. `wsl --set-default <distro>` changes it.
2. Download `humanize-<version>-windows-x64-setup.exe` and run it. It installs Humanize Desktop
   for you alone, so it asks for no administrator rights, and puts it in the Start menu.
3. Open Humanize Desktop from the Start menu.
4. Inside WSL, [sign in to a coding agent](#signing-each-backend-in), as on any Linux machine. A
   CLI installed on Windows is not seen.

### What the first launch does

The first time, the app says **Installing Humanize CLI**, with each step, while it installs uv
and `hmz` -- in WSL, on Windows. From then on it shows its mark while `hmz web` starts, then
the page, with the sidebar of your epics. It keeps `hmz` at its own version, so with the app,
update the app rather than `hmz`. What else it does is on [Humanize Desktop](/user/desktop).

Now [sign in to a coding agent](#signing-each-backend-in), if you have not.

## Humanize CLI {#cli}

On macOS and Linux, in a terminal; on Windows, in a WSL terminal (`wsl --install` first, as
[above](#windows)):

::: code-group

```sh [uv tool]
uv tool install hmz
```

```sh [pipx]
pipx install hmz
```

```sh [pip]
pip install hmz
```

:::

Each one gives you the `hmz` command, from [PyPI](https://pypi.org/project/hmz/). `uv tool` and
`pipx` put it in an environment of its own, on your `PATH` from every directory. `pip` installs
into whichever environment is active, so `hmz` is there only while that environment is. No uv
yet? `curl -LsSf https://astral.sh/uv/install.sh | sh` installs it, and uv fetches the Python
`hmz` needs.

### Or run it without installing {#uvx}

`uvx` runs `hmz` from an environment uv makes and caches, with nothing put on your `PATH`.
Every argument after `hmz` goes to it:

```sh
uvx hmz                          # the terminal interface, in this repository
uvx hmz web                      # every epic on this machine, in a browser
uvx hmz@latest                   # the newest release, rather than the one uv cached
uvx --from 'hmz[all]' hmz        # with the extras below
```

Each line is a whole `hmz` command, so type `uvx hmz` wherever these pages say `hmz`. `hmz
update` does not apply here: `uvx hmz@latest` is how this way moves to a new release.

### Three backends need an extra {#the-two-backends-that-are-extras}

Skip this unless you want DeepSeek Harness, Kimi Code or litellm. Each needs a Python package in
Humanize's own environment:

| Extra | For |
| --- | --- |
| `hmz[dsh]` | DeepSeek Harness (`dsh`). It has no CLI to install. |
| `hmz[kimi]` | Kimi Code (`kimi`), alongside its CLI. |
| `hmz[litellm]` | litellm (`litellm`): a model called directly, with no CLI to install. And its gateway, which runs most CLIs as any account litellm can reach ([which](/reference/providers#through-litellm)). |
| `hmz[all]` | All three. |

::: code-group

```sh [uv tool]
uv tool install 'hmz[all]'
```

```sh [pipx]
pipx install 'hmz[all]'
```

```sh [pip]
pip install 'hmz[all]'
```

:::

You can add one later without reinstalling Humanize. The agent menu lists a backend that is
missing its extra, with the install command on its row. With Humanize Desktop, add an extra
with `uv tool install` as above; the app keeps it when it updates `hmz`.

## Sign in to a coding agent {#signing-each-backend-in}

Humanize does not talk to a model itself: it drives a coding agent CLI that you install and
sign in to yourself, and runs it **as you signed it in** -- nothing is copied. One is enough.
On Windows, do this in WSL. Pick yours:

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
qwen                           # then /auth for a plan or a key, and /quit once it is set
```

```sh [opencode]
npm i -g opencode-ai
opencode auth login
```

```sh [mimocode]
npm i -g @mimo-ai/cli
mimo auth login
```

```sh [MiniMax Code]
npm i -g @minimax-ai/code
mcode login                    # or a MiniMax API key: mcode provider set-minimax-key
```

```sh [pi]
npm i -g @earendil-works/pi-coding-agent
pi                             # then /login, and /exit once you are signed in
```

```sh [Oh My Pi]
curl -fsSL https://omp.sh/install | sh
omp                            # then /login, and /exit once you are signed in
```

```sh [DeepSeek Harness]
# no CLI: install the [dsh] extra, above, and give it a DeepSeek API key
export DEEPSEEK_API_KEY=sk-…
```

:::

If you are already signed in, there is nothing to do.

::: tip An API key, or two accounts of one CLI
Make an account on [the Accounts page of `/settings`](/user/settings#accounts) inside `hmz`. It
can hold a login, an API key, or a gateway of your own, and one flow can run two accounts of
the same CLI at once.
:::

## Check it works {#check-what-you-have}

```sh
hmz --version
```

```console
hmz 0.1.0
```

With Humanize Desktop, the window opens on the sidebar of your epics instead. With the CLI,
open the terminal interface in any directory:

```sh
hmz
```

## Example: the first time `hmz` opens

The first time, Humanize asks each CLI it found which models it runs. That can take a minute.
It then asks one question of its own. Here it is on a machine with Claude Code, Codex and
Qwen Code signed in:

<Term title="hmz · the first launch">

<pre>  <span class="p">╭────────────────────────────────────────────────────────────────╮</span>
  <span class="p">│</span>                                                                <span class="p">│</span>
  <span class="p">│</span>  <span class="p b">Report errors to Humanize?</span>                                    <span class="p">│</span> <span class="n">1</span>
  <span class="p">│</span>  <span class="m">Send error reports to help fix bugs. Sent: the error and</span>      <span class="p">│</span>
  <span class="p">│</span>  <span class="m">where in Humanize it occurred; … Never sent: nothing you</span>      <span class="p">│</span>
  <span class="p">│</span>  <span class="m">typed: no task, prompt, or command; … You can change this</span>     <span class="p">│</span>
  <span class="p">│</span>  <span class="m">later in /settings.</span>                                           <span class="p">│</span>
  <span class="p">│</span>                                                                <span class="p">│</span>
  <span class="p">│</span>  <span class="sel"> Yes </span>  <span class="btn"> No </span>                                                   <span class="p">│</span>
  <span class="p">│</span>                                                                <span class="p">│</span>
  <span class="p">│</span>  <b>enter</b> yes   <b>esc</b> ask again next time                           <span class="p">│</span>
  <span class="p">│</span>                                                                <span class="p">│</span>
  <span class="p">╰────────────────────────────────────────────────────────────────╯</span>

                                  <span class="m">assistant · qwen/qwen3-coder-plus:high</span> <span class="n">2</span>
<span class="d">──────────────────────────────────────────────────────────────────────</span>
<span class="p">❯</span>
<span class="d">──────────────────────────────────────────────────────────────────────</span>
  <span class="a">◉</span> chat · ~/src/demo <span class="n">3</span>   <span class="d">/ commands · shift+enter newline · ctrl+c exit</span></pre>

</Term>

What to look at, by number:

1. **The reporting question**, a box over the screen. It says in full what a report carries
   and what it never does. Its answers are the two buttons: **Yes** has the focus, so
   <kbd>enter</kbd> says yes, and <kbd>→</kbd> moves to **No**. Answer either way:
   `/settings` changes it later, and <kbd>esc</kbd> asks again next time. See
   [Reporting](/user/reporting).
2. **The line above the prompt** names the agent Humanize would start:
   `role · cli/model:effort`. Here the role is `assistant`, and the CLI is the first one
   Humanize found that could say what it runs. Seeing a CLI and a model here is the proof that
   Humanize can drive it.
3. **The status line** says which [flow](/user/concepts#flow) is chosen, `chat`, and the
   directory. On the right are the keys that work right now.

### Check it worked

- `hmz --version` prints a version.
- The line above the prompt reads `assistant · <cli>/<model>:<effort>`, not only `assistant`.
- `/flow`, then <kbd>enter</kbd> on a role, lists your CLI on its `cli` row.

Leave with `/exit`. Now make your [first run](/user/first-run).

## Notes on particular backends

::: details DeepSeek Harness: the key, the models and the platforms
The `[dsh]` extra installs on Linux (x86-64 and arm64) and on macOS (arm64).

Give it a key in any one of these ways:

- `DEEPSEEK_API_KEY` in the environment, or in a `.env` file in the project.
  `DEEPSEEK_BASE_URL` points it at another endpoint.
- The key saved by dsh's own CLI, if you also have it: `dsh web`, then **Settings → Models**.
- An account on [the Accounts page of `/settings`](/user/settings#accounts): `key` for a
  DeepSeek key, or a gateway for a key that belongs to a proxy or another vendor, which also
  asks for its URL: `openai-gateway` (OpenAI's Chat Completions or Responses API, URL ending
  in `/v1`), `anthropic-gateway` (Anthropic's Messages API, URL without `/v1`) or
  `gemini-gateway` (Gemini's API, URL ending in `/v1beta`). A gateway runs at the endpoint's
  own effort, and an agent that may search there can fetch pages but not search.

Until it has a key, Humanize lists `dsh` but does not pick it for you. Its models are
`deepseek-v4-flash` and `deepseek-v4-pro`, at the efforts `max`, `high`, `low` and `off`:

```sh
hmz exec -f chat -a assistant=dsh/deepseek-v4-flash:high "say hello"
```

`chat` and the six loops [FlowBench scores](https://humanfia.ai/flows/) ship with
Humanize. A flow from a flowverse, such as `flame_chasoid:parallel_git_pr`, runs once you install it
from `/flow`; `hmz exec` installs nothing.

A `dsh` agent works with full access whatever its flow declares. See
[Security](/user/security).
:::

::: details Any other CLI that speaks the Agent Client Protocol
Add it on the Accounts page of [`/settings`](/user/settings#accounts), and it is offered beside
the thirteen above. See [Many backends, one agent](/features/backends).
:::

## Where Humanize keeps things

Everything Humanize remembers is under `~/.hmz/`: your runs, what each directory was set
up to run, your accounts, the flowverses it fetched and the flows you installed. Set
`HUMANIZE_HOME` to keep it somewhere else. A project's own flows, and the runs you export from it, are in `.hmz/` in
that project. The full list is in the [CLI reference](/reference/cli).

Older versions used `~/.humanize/` and `.humanize/`. You don't have to do anything about
them: Humanize renames each one to `.hmz` the first time it looks there. If both are there,
it uses `.hmz` and leaves the old one alone. With `HUMANIZE_HOME` set, `~/.humanize` is left
where it is, so move any flows of your own in `~/.humanize/flows` to `~/.hmz/flows` yourself.
See [Files](/reference/files#moved-from-humanize).

## Troubleshooting

### The line above the prompt reads only `assistant`

No CLI has answered: Humanize found none, or the one it found is not signed in and cannot say
what it runs. Typing a task then says `hmz: no coding agent is installed`.

Humanize looks on your `PATH`, then in `~/.local/bin`, `/usr/local/bin`, `/opt/homebrew/bin`,
`/usr/bin` and `/bin`. See which ones a shell finds:

```sh
command -v agy claude codex cursor-agent grok kimi mcode mimo omp opencode pi qwen
```

A CLI that is listed but still not offered is usually not signed in: run its sign-in from
[step 2](#signing-each-backend-in) again, then open `hmz` again.

### `hmz: command not found`

`pip` installed into an environment that is not active, or `uv tool`'s and `pipx`'s directory
is not on your `PATH`. Run `uv tool update-shell` or `pipx ensurepath`, and open a new shell.

### A model I expected is missing

What a CLI runs is asked once and remembered for a week, then asked again in the background. To
ask now, open `/flow`, <kbd>enter</kbd> on a role, then on its `model` row, and press
**Check again** under the list.

### `dsh`, `kimi` or `litellm` is listed with an install command

Its extra is missing. Run the command on its row, or reinstall with the extra from
[Three backends need an extra](#the-two-backends-that-are-extras).

## Upgrade

```sh
hmz update
```

`hmz update` asks PyPI for the newest release and has whatever installed `hmz` install it --
`uv tool`, `pipx`, or `pip` in an environment you made -- keeping the extras it was installed
with; in a terminal a spinner shows while PyPI is asked. `hmz` and `hmz web` say when a newer release is out. An install from a checkout is
updated there, with `git pull`. By hand, the same is:

::: code-group

```sh [uv tool]
uv tool upgrade hmz
```

```sh [pipx]
pipx install --force hmz
```

```sh [pip]
pip install --upgrade hmz
```

:::

Each moves Humanize to the newest release. `uv tool upgrade` keeps the extras it was installed
with; `pipx` and `pip` install again, so name an extra again: `pip install --upgrade 'hmz[all]'`.

With [Humanize Desktop](/user/desktop), update the app instead: it puts the `uv tool` `hmz` back at its own version the next time it opens with no
epics running, older or newer, keeping its extras.

What changed is in each release's notes, on
[GitHub Releases](https://github.com/humanfia/humanize/releases).

## Uninstall

Stop any run you left running first: `hmz` in its directory, then `/exit`. To remove Humanize
Desktop, see [its page](/user/desktop#uninstall). For the CLI:

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

To also forget everything Humanize remembered, your accounts included, remove `~/.hmz`,
or wherever `HUMANIZE_HOME` points:

```sh
rm -rf ~/.hmz
```

The coding agent CLIs and their own logins stay as they are.

## Next steps

- [Your first run](/user/first-run): choose a flow, give it an agent and a budget, and watch it
  work.
- [Security](/user/security): what to check before a flow touches work you care about.
- [Accounts](/user/settings#accounts): run a CLI as an API key, a gateway or a second login.
- [Many backends, one agent](/features/backends): what each backend can and cannot do.
