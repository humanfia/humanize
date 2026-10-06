"""The runtime's front door: one name apiece, fetched from the module it is written in."""

from __future__ import annotations

import importlib

import pytest

import hmz.runtime

WRITTEN = {
    "Accounts": "hmz.runtime.doing.accounts",
    "Epics": "hmz.runtime.doing.epics",
    "Fallbacks": "hmz.runtime.doing.fallbacks",
    "Flows": "hmz.runtime.doing.flows",
    "Flowverses": "hmz.runtime.doing.flows",
    "Hmz": "hmz.runtime.doing.core",
    "Host": "hmz.runtime.doing.hosting",
    "Refused": "hmz.runtime.runner",
    "Run": "hmz.runtime.doing.running",
    "Runtimes": "hmz.runtime.doing.runtimes",
}


def test_the_front_door_offers_exactly_these() -> None:
    assert sorted(hmz.runtime.__all__) == sorted(WRITTEN)


@pytest.mark.parametrize(("name", "module"), sorted(WRITTEN.items()))
def test_each_is_the_one_object_its_module_holds(name: str, module: str) -> None:
    assert getattr(hmz.runtime, name) is getattr(importlib.import_module(module), name)


def test_a_name_it_does_not_offer_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no attribute 'Nothing'"):
        _ = hmz.runtime.Nothing


def test_a_module_beside_it_is_still_that_module() -> None:
    from hmz.runtime import settings, telemetry

    assert telemetry.__name__ == "hmz.runtime.telemetry"
    assert settings.__name__ == "hmz.runtime.settings"


def test_refused_is_a_value_error() -> None:
    from hmz.runtime import Refused

    assert issubclass(Refused, ValueError)
