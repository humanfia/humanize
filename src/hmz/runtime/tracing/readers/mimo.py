"""Collector for mimocode sessions, which are rows rather than lines.

mimocode is a fork of opencode and keeps the same three tables in a database of
its own name, so the reading is :mod:`hmz.runtime.tracing.readers._rows` and what
is here is which database and which backend. Two columns the original keeps on a
conversation are not here -- what it ran at, and which agent it ran as -- so what
a mimocode session was answered by is read off its first answer instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.runtime.tracing.readers import _rows

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Session

#: What the database is called under mimocode's share directory.
DATABASE = "mimocode.db"


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the mimocode sessions asked for, as :func:`_rows.collect` does."""
    return _rows.collect(
        home, workspace, sessions, window, backend="mimo", database=DATABASE
    )
