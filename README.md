# Humanize _(hmz)_

![Humanize](https://socialify.git.ci/humanfia/humanize/image?description=1&font=Raleway&forks=1&issues=1&logo=https%3A%2F%2Fraw.githubusercontent.com%2Fhumanfia%2Fhumanize%2Frefs%2Fheads%2Fmain%2Fdocs%2Fpublic%2Flogo.svg&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Auto)

The agent flow system for token maxxing.

## Install

### Humanize Desktop

Humanize Desktop puts `hmz web` in a window of its own, and installs `hmz` itself. Download it
from the [latest release](https://github.com/humanfia/humanize/releases/latest):
`humanize-<version>-macos-universal.dmg` on macOS, or
`humanize-<version>-windows-x64-setup.exe` on Windows, where `hmz` runs in WSL 2
(`wsl --install`). [Installation](https://docs.humanfia.ai/humanize/user/installation#desktop)
says how to open it the first time.

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

Open the terminal interface in a repository:

```sh
hmz
```

Or open every epic on this machine in a browser:

```sh
hmz web
```

Or run a flow from your shell:

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high "What does this repository do?"
```

Agents run with approvals bypassed, so start in a scratch repository. The
[documentation](https://docs.humanfia.ai/humanize/) walks through a first run.

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
