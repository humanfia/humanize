"""Collector for opencode sessions, which are rows rather than lines.

opencode keeps everything it records in one SQLite database under its share
directory rather than a file per session, which is why what reads it is a query.
The reading itself is :mod:`hmz.runtime.tracing.readers._rows`, shared with
mimocode, which keeps the same three tables because it is a fork of this.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.runtime.tracing.readers import _rows

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Session

#: What the database is called under opencode's share directory.
DATABASE = "opencode.db"


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the opencode sessions asked for, as :func:`_rows.collect` does."""
    return _rows.collect(
        home, workspace, sessions, window, backend="opencode", database=DATABASE
    )
