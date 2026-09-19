"""The recorded agent homes these tests read, borrowed from where they are written.

The fixtures themselves stay in :mod:`tests.tracing.fixtures`, which is under no one tier.
All three name it by path -- the tests here, `tests/integration/tracing/conftest.py` for
`sandbox`, and both copies of `test_together.py` for `labels`, in `tests/integration/runtime`
and `tests/system/runtime` -- so moving it would be one tier's refactor breaking another
tier's imports.

`sandbox` is re-exported alongside them, and it is the one that must not be forgotten. It is
autouse, and autouse is a property of the fixture rather than of the file it was named in, so
importing it here puts it back over every test in this directory. What it does is set `HOME`
inside `tmp_path` and unset every variable a backend lets its home be moved by, which the home
fixtures below then set one at a time as a test asks for them. Drop it and only the homes a
test named are redirected: `tracing.collect` looks for every backend there is, so a test that
asked for `claude_home` alone would go on to read the real Codex, DSH, Grok Build, Kimi, Qwen
Code and ZCode logs of whoever ran the suite -- and still pass, off somebody else's
transcripts. ZCode and Antigravity are the two with no variable of their own: what moves their
homes is `HOME` itself, so setting that is the whole of what keeps this off the developer's.
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
    zcode_home,
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
    "zcode_home",
]
