"""What the flow engine's tests share: nothing of one test's flows left for the next.

A flow directory a test loads is imported into `sys.modules`, with its directory on
`sys.path`, and stays there once its run is over -- which is right for a process that runs
the same flows again, and wrong for a suite whose tests each write a flowverse of their own
under a temporary directory and may name their flows alike.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.runtime.flowing import loading

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _forgets_flow_modules() -> Iterator[None]:
    yield
    loading.forget()
