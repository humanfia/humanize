"""The sandbox these tests run in, borrowed from where the recorded homes are written.

Neither test here reads a recorded home -- one profiles a subprocess of its own, the other
drives a flow against `ShellAgent` -- so `sandbox` is taken and the homes are not. It came
with the directory these two were moved out of, and it is re-exported rather than dropped so
that the move changes where the files are and nothing else: it is autouse, and autouse
travels with the fixture rather than with the file it was named in.

What it leaves is a `HOME` inside `tmp_path` and no `CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
`DSH_HOME` or `KIMI_CODE_HOME` -- unset rather than redirected, so every backend falls back
to a home directory with nothing in it. The next test written beside these two inherits that
without having to know to ask.
"""

from __future__ import annotations

from tests.tracing.fixtures import sandbox

__all__ = ["sandbox"]
