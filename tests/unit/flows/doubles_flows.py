"""The double the `hmz.flows` unit tests stand in for the runtime.

`hmz.flows` names one thing outside itself, `hmz.runtime.flowing.engine`, and only when
`flow`, `load` or `Outworlder.new` is called. `engine` puts a mock in its place.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest import mock

if TYPE_CHECKING:
    import pytest

#: The module `flow`, `load` and `Outworlder.new` hand their calls to.
ENGINE = "hmz.runtime.flowing.engine"


@dataclass
class Defined:
    """What the stand-in `define_flow` answers: the function, and what it was declared with."""

    fn: Any
    declared: dict[str, Any]


def engine(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Puts a mock engine in the runtime's place; its `define_flow` answers a `Defined`."""
    double = mock.Mock(spec=["define_flow", "load_flow", "new_outworlder"])

    def define_flow(fn: Any, **declared: Any) -> Defined:
        return Defined(fn, declared)

    double.define_flow.side_effect = define_flow
    monkeypatch.setitem(sys.modules, ENGINE, double)
    return double
