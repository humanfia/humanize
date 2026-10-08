# AGENTS.md

For implementation:

- MUST pass all tests and linters before merging a PR or claiming the task is done.
- MUST ensure CI is green before merging a PR or claiming the task is done.
- PREFER use popular and well-maintained libraries rather than custom implementations.

For tests:

- MUST put a test in exactly one of `tests/unit/`, `tests/integration/`, `tests/system/`.
- `tests/unit/<package>/`, one directory per `src/hmz` top-level package: MUST test only that package's public names (no `_private` names or modules), MUST mock other `hmz` packages, MUST NOT start a subprocess or open a socket.
- `tests/integration/test_<topic>_*.py`, flat: packages wired together against fakes this repo writes; CI runs one job per topic (`core`, `agents`, `tui`, `daemon`, `anchor`, `web`).
- `uv run pytest` runs unit and integration, which is what CI runs.
- `tests/system/` is OPTIONAL: real agents on real tasks, 5–30 minutes and real tokens per test, never in CI. Do NOT run it on every change; run only the file that covers an end-to-end path you changed, e.g. `uv run pytest tests/system/test_flows_ralph.py`.

For `specs/*.md`:

- MUST strictly adhere to specs at `specs/`.
- MUST NOT modify any SPEC UNLESS explicitly instructed to do so.
- MUST ensure code is minimal and any further simplification will lead to dissatisfaction of the spec.

For version control:

- MUST adhere to [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
- MUST delete local branches or worktrees and remote branches once merged.

For docs:

- MUST update docs once any impl changes to avoid misalignment between code and docs.
- MUST adhere to the minimal spec of [Standard Readme](https://raw.githubusercontent.com/RichardLitt/standard-readme/refs/heads/main/spec.md) for `README.md`.
