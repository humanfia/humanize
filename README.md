# Humanize _(hmz)_

![Humanize](https://socialify.git.ci/humanfia/humanize/image?description=1&font=Raleway&forks=1&issues=1&logo=https%3A%2F%2Fraw.githubusercontent.com%2Fhumanfia%2Fhumanize%2Frefs%2Fheads%2Fmain%2Fdocs%2Fpublic%2Flogo.svg&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Auto)

The agent flow system for token maxxing.

Humanize is infrastructure, not a flow. A flow is a Python program that says what to ask and of
whom; Humanize is what it runs on. It schedules the many different nous a flow asks for -- a
nous is a harness, an account, a model and an effort -- gives each agent an environment to work
in, on this machine, over SSH, in a container or on a cluster, holds the whole run to one
budget, and keeps the record it can be resumed and traced from.

## Background

Where Humanize is going, which is not a measurement of where it is: one flow driving a million
agents in a million environments for a month, on one task. A task of that size is not
done by one model in one session, so what Humanize is built around is the scheduling: many
different nous, with retries and fallback from one to the next, on as many machines as the work
needs. It ships no flow of its own.

## Install

### Humanize Desktop

Humanize Desktop is the page of `hmz web` in a window of its own. Download it from the
[latest release](https://github.com/humanfia/humanize/releases/latest):
`humanize-<version>-macos-universal.dmg` on macOS, where you install Humanize CLI as below
too, or `humanize-<version>-windows-x64-setup.exe` on Windows, where the app installs `hmz`
itself, in WSL 2 (`wsl --install`).
[Install and update](https://humanfia.ai/humanize/user/install) says how to open it the
first time.

### Humanize CLI

Humanize CLI needs Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and a coding agent
CLI you are signed in to, such as Claude Code or Codex.

```sh
uv tool install hmz
```

Three backends need a package of their own: `[dsh]` for DeepSeek Harness, `[kimi]` for Kimi
Code, `[litellm]` for litellm, `[all]` for all three.

```sh
uv tool install 'hmz[all]'
```

`hmz update` moves it to the newest release, keeping the extras it was installed with.

Or run it without installing, from a copy uv caches -- `@latest` asks for the newest release:

```sh
uvx hmz@latest
uvx --from 'hmz[all]' hmz web
```

## Usage

Open the terminal interface in a repository, on a chat with your coding agent; `$<flow>` or
`/flow <flow> <task>` starts a flow from there, and `/chat` comes back to the chat:

```sh
hmz
```

Or open every epic on this machine in a browser:

```sh
hmz web
```

Or say one thing to an agent from your shell:

```sh
hmz chat -a claude/claude-opus-5:high "What does this repository do?"
```

Humanize ships no flow: install one from the official
[flowverse](https://github.com/humanfia/flowverse) in `/flow`, under **Flowverses**, or write
your own. Then run it from your shell, under a budget:

```sh
hmz exec -f ralph_loop -a agent=claude/claude-opus-5:high -p budget.cost=5 "Make the tests pass"
```

Or name a release by its repository, with nothing installed:

```sh
hmz exec -f git+https://github.com/humanfia/ralph-loop-flow@v0.1.0#ralph_loop \
    -a agent=claude/claude-opus-5:high -p budget.cost=5 "Make the tests pass"
```

Or teach your coding agents the `hmz` command line, as a skill in each one's own folder:

```sh
hmz skills add
```

Agents run with approvals bypassed, so start in a scratch repository. The
[documentation](https://humanfia.ai/humanize/) starts with a
[first task in the terminal](https://humanfia.ai/humanize/tutorials/first-task-terminal).

## Contributing

Pull requests are welcome:
[CONTRIBUTING.md](https://github.com/humanfia/humanize/blob/main/CONTRIBUTING.md) says how to
propose one. Report a bug or request a feature through the
[issue forms](https://github.com/humanfia/humanize/issues/new/choose), and report a
vulnerability privately, as [SECURITY.md](https://github.com/humanfia/humanize/blob/main/SECURITY.md)
says. Everyone taking part follows the
[Code of Conduct](https://github.com/humanfia/.github/blob/main/CODE_OF_CONDUCT.md).

## License

Apache-2.0 &copy; Humanfia
