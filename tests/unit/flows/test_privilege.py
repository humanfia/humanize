"""What shipping with humanize earns a flow, which is nothing: `chat` alone is trusted.

Every flow in the package is :func:`builtin`, and only `chat` is :func:`privileged` -- handed
every capability of its harness, and run with no budget of its own -- because it talks to
whichever agent it is given and stops when the person does. The loops beside it declare what
they ask of their agents and spend under a budget, like a flow of anybody's.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.flowing import BUILTIN_AT, builtin, offered, privileged, resolved
from tests.flows.kit import SHIPPED, shipped

if TYPE_CHECKING:
    from pathlib import Path

#: The loops humanize ships beside `chat`.
LOOPS = tuple(one for one in SHIPPED if one != "chat")


def test_the_package_holds_chat_and_the_loops() -> None:
    assert offered(BUILTIN_AT) == list(SHIPPED)


def test_chat_is_shipped_and_trusted() -> None:
    flow = shipped("chat")

    assert builtin(flow)
    assert privileged(flow)
    assert flow._full


@pytest.mark.parametrize("name", LOOPS)
def test_a_loop_humanize_ships_is_shipped_and_nothing_more(name: str) -> None:
    flow = shipped(name)

    assert builtin(flow)
    assert not privileged(flow)
    assert not flow._full


def test_a_chat_of_your_own_earns_none_of_it(tmp_path: Path) -> None:
    """Trust is where a flow is rather than what it is called, which anybody can take."""
    shutil.copytree(BUILTIN_AT / "chat", tmp_path / "chat")

    flow = resolved(str(tmp_path / "chat"))

    assert flow.name == "chat"
    assert not builtin(flow)
    assert not privileged(flow)
    assert not flow._full
