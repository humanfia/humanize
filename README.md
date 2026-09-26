# humanize

![humanize](https://socialify.git.ci/humanfia/humanize/image?description=1&font=Raleway&forks=1&issues=1&logo=https%3A%2F%2Fraw.githubusercontent.com%2Fhumanfia%2Fhumanize%2Frefs%2Fheads%2Fmain%2Fdocs%2Fpublic%2Flogo.svg&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Auto)

Orchestrate, execute, and observe agent flows.

## Install

Needs Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and a coding agent CLI you are
signed in to, such as Claude Code or Codex.

```sh
uv tool install git+https://github.com/humanfia/humanize.git
```

Two backends need a package of their own: `[dsh]` for DeepSeek Harness, `[kimi]` for Kimi
Code, `[all]` for both.

```sh
uv tool install 'hmz[all] @ git+https://github.com/humanfia/humanize.git'
```

## Usage

Open the terminal interface in a repository:

```sh
hmz
```

Or run a flow from your shell:

```sh
hmz exec -f chat -a assistant=claude/claude-opus-5:high "What does this repository do?"
```

Agents run with approvals bypassed, so start in a scratch repository. The
[documentation](https://docs.humanfia.ai/humanize/) opens with a quickstart.

## Contributing

Request features in the [wishlist](https://github.com/humanfia/humanize/issues/26), report bugs
in the [issues](https://github.com/humanfia/humanize/issues), or open a pull request. See
[Contributing](https://docs.humanfia.ai/humanize/contributing/) for how to set up and check a
change.

## License

Apache-2.0 &copy; Humanfia
