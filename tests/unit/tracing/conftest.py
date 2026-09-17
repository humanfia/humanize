"""The recorded agent homes these tests read, borrowed from where they are written.

The fixtures themselves stay in :mod:`tests.tracing.fixtures`, which is under no one tier.
All three name it by path -- the tests here, `tests/integration/tracing/conftest.py` for
`sandbox`, and both copies of `test_together.py` for `labels`, in `tests/integration/runtime`
and `tests/system/runtime` -- so moving it would be one tier's refactor breaking another
tier's imports.

`sandbox` is re-exported alongside them, and it is the one that must not be forgotten. It is
autouse, and autouse is a property of the fixture rather than of the file it was named in, so
importing it here puts it back over every test in this directory. What it does is set `HOME`
inside `tmp_path` and unset `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `DSH_HOME` and
`KIMI_CODE_HOME`, which the home fixtures below then set one at a time as a test asks for
them. Drop it and only the homes a test named are redirected: `tracing.collect` looks for
every backend, so a test that asked for `claude_home` alone would go on to read the real
Codex, DSH and Kimi logs of whoever ran the suite -- and still pass, off somebody else's
transcripts.
"""

from __future__ import annotations

from tests.tracing.fixtures import (
    claude_home,
    codex_home,
    dsh_home,
    elsewhere,
    homes,
    kimi_home,
    sandbox,
    workspace,
)

__all__ = [
    "claude_home",
    "codex_home",
    "dsh_home",
    "elsewhere",
    "homes",
    "kimi_home",
    "sandbox",
    "workspace",
]
