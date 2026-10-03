<!--
The title is a Conventional Commit, `type(scope): what it does`, with `!` before the colon if
it breaks something. The triage workflow checks it and labels the pull request from it.
CONTRIBUTING.md has the rest: https://github.com/humanfia/humanize/blob/main/CONTRIBUTING.md
-->

## What and why

<!-- What this changes, and why. "Closes #123" closes the issue it fixes when this merges. -->

## How it was tested

<!-- The tests you added or ran, and anything you checked by hand: the command and what it printed. -->

## Checklist

- [ ] The title is a [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/), with `!` if it breaks something.
- [ ] New and changed tests are in the right tier: `tests/unit/`, `tests/integration/` or `tests/system/` ([where a test goes](https://docs.humanfia.ai/humanize/contributing/#where-a-test-goes)).
- [ ] The docs say what the code now does, and the code matches `specs/`. A spec changed only where an issue asked for it.
- [ ] `uv run pre-commit run --all-files` and `uv run pytest` pass.
