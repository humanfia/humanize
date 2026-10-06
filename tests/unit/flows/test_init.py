"""`hmz.flows`: the whole of what a flow imports, gathered from its four modules."""

from __future__ import annotations

import hmz.flows
from hmz.flows import agents, defining, envs, errors, hooks

MODULES = (agents, defining, envs, errors, hooks)


def test_the_package_offers_exactly_what_its_modules_do() -> None:
    offered = {name for module in MODULES for name in module.__all__}
    assert set(hmz.flows.__all__) == offered
    assert len(hmz.flows.__all__) == len(offered)


def test_each_name_offered_is_the_modules_own() -> None:
    for module in MODULES:
        for name in module.__all__:
            assert getattr(hmz.flows, name) is getattr(module, name), name
