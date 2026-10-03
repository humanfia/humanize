# Contributing to humanize

Thank you for helping. This file is how a change gets from an idea to `main`: where to raise
it, what a pull request needs, and how it is reviewed. How to set up a checkout, run the
checks and find your way around the code is the
[contributing guide](https://docs.humanfia.ai/humanize/contributing/), whose source is
[`docs/contributing/`](docs/contributing/).

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

| To | Do this |
| --- | --- |
| report a bug | open a [bug report](https://github.com/humanfia/humanize/issues/new?template=bug_report.yml) |
| report a vulnerability | follow [SECURITY.md](SECURITY.md), never a public issue |
| suggest a feature | open a [feature request](https://github.com/humanfia/humanize/issues/new?template=feature_request.yml) |
| fix the docs | open a [docs issue](https://github.com/humanfia/humanize/issues/new?template=docs.yml), or a pull request straight away |
| ask a question | see [SUPPORT.md](SUPPORT.md) |
| fix or build something | a pull request, as below |
| share a flow you wrote | keep it in a repository of your own, and list it in [humanfia/flowverse](https://github.com/humanfia/flowverse) with a pull request there |

Issues labelled
[`good first issue`](https://github.com/humanfia/humanize/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
and [`help wanted`](https://github.com/humanfia/humanize/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22)
are ready to pick up. Say so on the issue before you start, so that two people do not do the
same work.

## Before you write code

- **A small fix** (a bug, a typo, a missing test): open the pull request.
- **Anything larger** (a feature, a backend, a new flag, a change to the flow API, anything
  that breaks what works today): open an issue first, and agree the approach with a maintainer
  before you build it. A large pull request nobody asked for may be closed, however good it is.
- **`specs/` is the contract.** Change the code to match a spec. A pull request that changes a
  spec links the issue where a maintainer asked for that change.

## Pull requests

1. Branch from `main`, on a fork unless you have push access. Name the branch
   `<type>/<short-slug>`, such as `fix/say-what-to-do`.
2. Make the change, with its tests in the
   [tier they belong to](https://docs.humanfia.ai/humanize/contributing/#where-a-test-goes), and
   with the docs that describe it, in the same pull request.
3. Run [the checks](https://docs.humanfia.ai/humanize/contributing/#the-checks) until they pass.
4. Open the pull request against `main`, and fill in the template.

[Your first patch](https://docs.humanfia.ai/humanize/contributing/tutorials/first-patch) does
all of this once, with every command written out.

### Title and commits

The pull request's title is a [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/):
`type(scope): what it does`, in the imperative, with `!` before the colon if it breaks
something. For example, `fix(tui): keep the cursor on the row it was on`.

- **Types:** `feat`, `fix`, `docs`, `perf`, `refactor`, `test`, `ci`, `build`, `chore`,
  `style`, `revert`.
- **Scope:** the package or the docs section it changes, such as `agents`, `tui`, `flows` or
  `contributing`. Optional.

Commits follow the same form: see
[Commits](https://docs.humanfia.ai/humanize/contributing/#commits). A pull request of one
commit has that commit checked too, because squashing it writes the commit's message to `main`
rather than the title.

You do not label anything yourself. The `triage` workflow checks the title, labels the pull
request `type/<type>` from it, and `breaking` for a `!`, and adds an `area/*` label for each
part of the repository it touches. Edit the title and the labels follow.

No sign-off or CLA is asked for. What you contribute is under the project's
[Apache-2.0 license](LICENSE), as its section 5 says.

## Review

- GitHub asks the [code owners](.github/CODEOWNERS) of what you changed to review it.
- A pull request merges once a maintainer approves it and CI passes. A maintainer merges it.
  [GOVERNANCE.md](GOVERNANCE.md#conflicts-of-interest) covers a maintainer's own pull requests.
- Expect a first answer within a week. If a week passes without one, comment on the pull
  request to ask.
- Answer each comment, by a change or a reply. Push fixes as new commits rather than rewriting
  what was reviewed, so the reviewer sees what changed.
- A pull request that waits on its author for a month may be closed. Reopen it when you come
  back to it.

## Working with coding agents

humanize is built with coding agents, and you may use them too. [AGENTS.md](AGENTS.md) is the
rules they work under in this repository, and the rules are the same for people. You are the
author of what you send: read it, run it, and be ready to answer for every line.

## More

- [The contributing guide](https://docs.humanfia.ai/humanize/contributing/): set up, the
  checks, where a test goes, what the code is held to.
- [Architecture](https://docs.humanfia.ai/humanize/contributing/architecture): which layer a
  change belongs in.
- [GOVERNANCE.md](GOVERNANCE.md): who decides, and how to become a reviewer or maintainer.
- [SUPPORT.md](SUPPORT.md): where to ask.
