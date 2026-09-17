# AGENTS.md

For code:

- MUST pass `uv run pre-commit run --all-files` and `uv run pytest`. That second one is all
  three tiers: CI leaves the system tier out with `--ignore=tests/system`, your own run does
  not, and each test there says for itself what this machine could not give it.
- MUST file a new test by what is on the other side of it: `tests/unit/` calls `hmz` and
  nothing else, `tests/integration/` may talk to anything this repository wrote — a stand-in
  CLI, a fake app server, a loopback socket, the mock LLM service — and `tests/system/` needs
  the real thing.
- MUST run the system tier by hand when the change is one it covers: `uv run pytest
  tests/system --run-agents`. It drives real CLIs as `as local` and spends real tokens, so CI
  will not run it and nothing else will run it for you.
- PREFER use popular and well-maintained libraries rather than custom implementations.
- MUST also update `humanfia/flowverse` to ensure them working if any changes affect flow impl.

For `specs/*.md`:

- MUST strictly adhere to specs at `specs/`.
- MUST NOT modify any SPEC UNLESS explicitly instructed to do so.
- MUST keep code minimal while strictly adhering to the SPEC.

For version control:

- MUST adhere to [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
- MUST delete local branches or worktrees once merged.

For docs:

- MUST update docs once any impl changes to avoid misalignment between code and docs.
- MUST adhere to the minimal spec of [Standard Readme](https://raw.githubusercontent.com/RichardLitt/standard-readme/refs/heads/main/spec.md) for `README.md`.
