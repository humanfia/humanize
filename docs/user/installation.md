<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
</script>

# Installation

Install humanize, sign in to one coding agent CLI, and check that humanize can see it. It takes
a few minutes, most of it the CLI's own sign-in.

::: info At a glance
- **You will** have the `hmz` command on your `PATH`, and at least one coding agent it can
  drive.
- **Use it when** you are setting humanize up on a machine for the first time, or adding a
  backend to one that has it.
- **You need** **Python 3.12 or newer**, and `npm` for most of the coding agent CLIs.
:::

## Try it

With Claude Code, the whole thing is:

```sh
uv tool install git+https://github.com/humanfia/humanize.git
npm i -g @anthropic-ai/claude-code && claude auth login
hmz --version
```

The steps below say what each line does, give the other ways to install, and show every
backend's sign-in.

## How it works

humanize does not talk to a model itself. It drives **coding agent CLIs** that you already use,
such as Claude Code or Codex, the way a person would: it starts them, gives them a task, and
reads what they do. Each CLI humanize can drive is a **backend**.

So there are two installs, and they are independent:

| You install | Who signs it in | What it gives you |
| --- | --- | --- |
| humanize, once | nobody: it holds no account of its own | the `hmz` command |
| one or more coding agent CLIs | you, with the CLI's own login | the agents a flow runs |

humanize runs each CLI **as you signed it in**. The agent menu calls that `as local`. Nothing
is copied: your login stays where the CLI keeps it. To run a CLI as another account, see
[Accounts](/user/settings#accounts).

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

Each one gives you the `hmz` command, built from the latest `main` on GitHub: humanize has no
release yet. `uv tool` and `pipx` put it in an environment of its own, on your `PATH` from
every directory. `pip` installs into whichever environment is active, so `hmz` is there only
while that environment is.

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

## Example: the first time `hmz` opens

The first time, humanize asks each CLI it found which models it runs. That can take a minute.
It then asks one question of its own. Here it is on a machine with Claude Code, Codex and
Qwen Code signed in:

<Term title="hmz · the first launch">

<pre>  <span class="p">╭────────────────────────────────────────────────────────────────╮</span>
  <span class="p">│</span>                                                                <span class="p">│</span>
  <span class="p">│</span>  <span class="p b">Report errors to humanize?</span>                                    <span class="p">│</span> <span class="n">1</span>
  <span class="p">│</span>  <span class="m">Send error reports to help fix bugs. Sent: the error and</span>      <span class="p">│</span>
  <span class="p">│</span>  <span class="m">where in humanize it occurred; … Never sent: nothing you</span>      <span class="p">│</span>
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
  <span class="a">◉</span> chat · ~/src/demo <span class="n">3</span>   <span class="d">/ commands · shift+enter newline · ← monitor · ctrl+c exit</span></pre>

</Term>

What to look at, by number:

1. **The reporting question**, a box over the screen. It says in full what a report carries
   and what it never does. Its answers are the two buttons: **Yes** has the focus, so
   <kbd>enter</kbd> says yes, and <kbd>→</kbd> moves to **No**. Answer either way:
   `/settings` changes it later, and <kbd>esc</kbd> asks again next time. See
   [Reporting](/user/reporting).
2. **The line above the prompt** names the agent humanize would start:
   `role · cli/model:effort`. Here the role is `assistant`, and the CLI is the first one
   humanize found that could say what it runs. Seeing a CLI and a model here is the proof that
   humanize can drive it.
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

Until it has a key, humanize lists `dsh` but does not pick it for you. Its models are
`deepseek-v4-flash` and `deepseek-v4-pro`, at the efforts `max`, `high`, `low` and `off`:

```sh
hmz exec -f chat -a assistant=dsh/deepseek-v4-flash:high "say hello"
```

`chat` and the six loops [FlowBench scores](/flows/#the-loops-side-by-side) ship with
humanize. A flow from a flowverse, such as `parallel_flame_chase`, runs once you install it
from `/flow`; `hmz exec` installs nothing.

A `dsh` agent works with full access whatever its flow declares. See
[Security](/user/security).
:::

::: details Any other CLI that speaks the Agent Client Protocol
Add it on the Accounts page of [`/settings`](/user/settings#accounts), and it is offered beside
the twelve above. See [Many backends, one agent](/features/backends).
:::

## Where humanize keeps things

Everything humanize remembers is under `~/.hmz/`: your runs, what each directory was set
up to run, your accounts, the flowverses it fetched and the flows you installed. Set
`HUMANIZE_HOME` to keep it somewhere else. A project's own flows, and the runs you export from it, are in `.hmz/` in
that project. The full list is in the [CLI reference](/reference/cli).

Older versions used `~/.humanize/` and `.humanize/`. You don't have to do anything about
them: humanize renames each one to `.hmz` the first time it looks there. If both are there,
it uses `.hmz` and leaves the old one alone. With `HUMANIZE_HOME` set, `~/.humanize` is left
where it is, so move any flows of your own in `~/.humanize/flows` to `~/.hmz/flows` yourself.
See [Files](/reference/files#moved-from-humanize).

## Troubleshooting

### The line above the prompt reads only `assistant`

No CLI has answered: humanize found none, or the one it found is not signed in and cannot say
what it runs. Typing a task then says `hmz: no coding agent is installed`.

humanize looks on your `PATH`, then in `~/.local/bin`, `/usr/local/bin`, `/opt/homebrew/bin`,
`/usr/bin` and `/bin`. See which ones a shell finds:

```sh
command -v agy claude codex cursor-agent grok kimi mcode mimo opencode pi qwen
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

### `dsh` or `kimi` is listed with an install command

Its extra is missing. Run the command on its row, or reinstall with the extra from
[Two backends need an extra](#the-two-backends-that-are-extras).

## Upgrade

::: code-group

```sh [uv tool]
uv tool upgrade hmz
```

```sh [pipx]
pipx reinstall hmz
```

```sh [pip]
pip install --force-reinstall git+https://github.com/humanfia/humanize.git
```

:::

`uv tool upgrade` and `pipx reinstall` move humanize to the latest `main`, with the extras it
was installed with. `pipx upgrade` and `pip install --upgrade` do not: `main` keeps one version
number from commit to commit, and they leave a version they already have alone, so `pip` needs
`--force-reinstall`. Name an extra
again: `pip install --force-reinstall 'hmz[all] @ git+https://github.com/humanfia/humanize.git'`.

What changed is in the [commits on `main`](https://github.com/humanfia/humanize/commits/main).

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

To also forget everything humanize remembered, your accounts included, remove `~/.hmz`,
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
