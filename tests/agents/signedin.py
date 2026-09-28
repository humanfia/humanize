"""What a CLI signed in on this machine as itself -- as local -- can run, for the tests needing it.

A real-agent test that names a model is a test of this machine's sign-in as much as of the
driver: a CLI never logged in, or logged in to an account that does not serve the model, fails
the first turn for a reason that is this machine's rather than humanize's. Those are skipped,
saying which, rather than failed.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def kimi_runs(model: str) -> bool:
    """Whether Kimi Code as signed in here has a model configured, which its login writes."""
    try:
        written = (Path.home() / ".kimi-code" / "config.toml").read_text(
            encoding="utf-8"
        )
    except OSError:
        return False
    return f'"{model}"' in written or f"'{model}'" in written


def kimi_defaults() -> bool:
    """Whether Kimi Code as signed in here has a model to run when it is named none."""
    try:
        written = (Path.home() / ".kimi-code" / "config.toml").read_text(
            encoding="utf-8"
        )
    except OSError:
        return False
    return any(
        line.strip().startswith("default_model") for line in written.splitlines()
    )


#: For a test of Kimi Code as local at `kimi-code/k3`.
KIMI_K3 = pytest.mark.skipif(
    not kimi_runs("kimi-code/k3"),
    reason="kimi as signed in here has no kimi-code/k3 configured: its login writes the "
    "models into ~/.kimi-code/config.toml, and this one has none",
)

#: For a test of Kimi Code as local that names no model, and runs whatever it defaults to.
KIMI_DEFAULT = pytest.mark.skipif(
    not kimi_defaults(),
    reason="kimi as signed in here has no default_model, so `kimi -p` says 'no model "
    "configured': its login writes one into ~/.kimi-code/config.toml, and this one has none",
)
