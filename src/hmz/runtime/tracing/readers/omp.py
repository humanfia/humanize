"""Collector for omp sessions, which are pi's sessions under omp's own home.

omp is a fork of pi and keeps pi's log, line for line in every record this reads: so the
reading is :mod:`hmz.runtime.tracing.readers.pi` and what is here is which backend it is.
Checked against `omp 18.2.8` (`"version": 3`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.runtime.tracing.readers import pi

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Session


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the omp sessions asked for, as :func:`pi.collect` does."""
    return pi.collect(home, workspace, sessions, window, backend="omp")
