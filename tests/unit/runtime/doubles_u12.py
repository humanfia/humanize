"""Doubles the unit tests of the runtime's top level and of `hmz.runtime.doing` share."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


class Store:
    """`hmz.coganchor.settings` held in memory: what `read` hands back and `changes` writes.

    Attributes:
      held: The file, as a mapping.
      writes: How many changes were written.
      fails: What `changes` raises instead of writing, or None to write.
    """

    def __init__(self, held: dict[str, Any] | None = None) -> None:
        self.held: dict[str, Any] = held if held is not None else {}
        self.writes = 0
        self.fails: BaseException | None = None

    def read(self) -> dict[str, Any]:
        return copy.deepcopy(self.held)

    def changes(self, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        if self.fails is not None:
            raise self.fails
        now = copy.deepcopy(self.held)
        change(now)
        self.held = now
        self.writes += 1
        return copy.deepcopy(now)


def store(monkeypatch: pytest.MonkeyPatch, held: dict[str, Any] | None = None) -> Store:
    """Puts a :class:`Store` where `hmz.coganchor.settings` is read and written."""
    from hmz.coganchor import settings

    made = Store(held)
    monkeypatch.setattr(settings, "read", made.read)
    monkeypatch.setattr(settings, "changes", made.changes)
    return made


@dataclass
class Asked:
    """A function stood in for: what it was called with, and what it hands back.

    Attributes:
      returns: What every call answers with.
      calls: Each call's positional and keyword arguments, in order.
    """

    returns: Any = None
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = field(
        default_factory=list[tuple[tuple[Any, ...], dict[str, Any]]]
    )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return self.returns


class Stands:
    """Puts an :class:`Asked` in place of one function of a module, for one test."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch

    def __call__(self, module: object, name: str, returns: Any = None) -> Asked:
        asked = Asked(returns if returns is not None else object())
        self._monkeypatch.setattr(module, name, asked, raising=False)
        return asked
