"""The git repositories epics are backed up to, as every way in asks after them.

Which repositories there are is settings' to keep (:meth:`hmz.runtime.settings.Settings.backups`);
backing an epic up, and how each backup went, is :mod:`hmz.runtime.backing`. An epic is backed
up as its targets' policies say without anybody asking; this is the rest -- backing one up by
hand, out of the epics menu or `hmz backup`, and reading back how it went.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hmz.runtime.epic import Ran
    from hmz.runtime.settings import Target

__all__ = ["Backups"]


class Backups:
    """Every backup target, and the backups of each epic to them."""

    def targets(self) -> tuple[Target, ...]:
        """Every backup target in settings, in the order written."""
        from hmz.runtime.backing import configured

        return configured()[0]

    def defaults(self) -> tuple[str, ...]:
        """The targets a new epic is backed up to unless it is told otherwise, by name."""
        from hmz.runtime.backing import configured

        return configured()[1]

    def push(
        self, ran: Ran | Path, names: Iterable[str] | None = None
    ) -> tuple[str, ...]:
        """Backs one epic up to some targets, on threads of their own, and returns at once.

        Args:
          ran: The epic, read or by its directory.
          names: The targets, by name, or None for those the epic was started with -- or,
            where it was started with none, the defaults.

        Returns:
          The targets it was queued for, which is nothing where there are none to name.

        Raises:
          ValueError: For a name no target in settings has.
        """
        from hmz.runtime.backing import chosen, push
        from hmz.runtime.epic import read

        at = Path(ran) if isinstance(ran, Path) else ran.at
        if names is None:
            read_ = read(at) if isinstance(ran, Path) else ran
            names = read_.backup if read_ is not None and read_.backup else None
        picked = chosen(names)
        push(at, picked, "manual")
        return picked

    def state(self, ran: Ran | Path) -> dict[str, dict[str, Any]]:
        """How the last backup of one epic to each target went: `at`, `ok`, `error`, `why`.

        Args:
          ran: The epic, read or by its directory.

        Returns:
          One entry per target it was ever backed up to, by name, read off the epic as it is
          now; nothing for one never backed up, or one still being backed up the first time.
        """
        from hmz.runtime.epic import read

        read_ = read(Path(ran) if isinstance(ran, Path) else ran.at)
        return dict(read_.backed) if read_ is not None else {}

    def where(self, ran: Ran | Path) -> str:
        """Where in a target's repository one epic goes: `<machine>/<workspace>/<epic>`."""
        from hmz.runtime.backing import where

        return where(Path(ran) if isinstance(ran, Path) else ran.at)

    def wait(self, seconds: float | None = None) -> bool:
        """Waits for every backup this process has queued, for so long at most.

        Args:
          seconds: How long, or None for as long as they take.

        Returns:
          Whether none is left.
        """
        from hmz.runtime.backing import wait

        return wait(seconds)
