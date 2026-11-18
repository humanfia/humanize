"""`hmz.flows`: the whole of what a flow imports, gathered from its modules."""

from __future__ import annotations

import hmz.flows
from hmz.flows import agents, asking, defining, envs, errors, faces, hooks

MODULES = (agents, asking, defining, envs, errors, faces, hooks)

#: What it hands on from coganchor rather than writes: the fake tool and command line types.
FAKES = {"FakeCli", "FakeCommand", "FakeTool"}


def test_the_package_offers_exactly_what_its_modules_do() -> None:
    offered = FAKES | {name for module in MODULES for name in module.__all__}
    assert set(hmz.flows.__all__) == offered
    assert len(hmz.flows.__all__) == len(offered)


def test_each_name_offered_is_the_modules_own() -> None:
    for module in MODULES:
        for name in module.__all__:
            assert getattr(hmz.flows, name) is getattr(module, name), name
