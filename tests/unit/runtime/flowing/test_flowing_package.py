"""`hmz.runtime.flowing` itself: every name it offers, fetched from where it is written."""

from __future__ import annotations

import importlib

import pytest

from hmz.runtime import flowing

MODULES = (
    "affinity",
    "declaring",
    "engine",
    "environments",
    "fakes",
    "finding",
    "harnesses",
    "index",
    "journaling",
    "loading",
    "skills",
    "specs",
    "spi",
    "verses",
    "viewing",
)


@pytest.mark.parametrize("name", flowing.__all__)
def test_every_name_offered_is_the_one_its_module_holds(name: str) -> None:
    offered = getattr(flowing, name)
    holders = [
        module
        for module in (
            importlib.import_module(f"hmz.runtime.flowing.{one}") for one in MODULES
        )
        if getattr(module, name, None) is offered
    ]
    assert holders, f"{name} is offered and no module of the package holds it"


@pytest.mark.parametrize("name", flowing.__all__)
def test_every_name_offered_is_one_its_module_offers(name: str) -> None:
    offering = [
        one
        for one in MODULES
        if name in importlib.import_module(f"hmz.runtime.flowing.{one}").__all__
    ]
    assert offering, f"{name} is offered and no module of the package offers it"


def test_each_name_is_offered_once() -> None:
    assert len(set(flowing.__all__)) == len(flowing.__all__)


def test_a_name_not_offered_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'nothing_here'"):
        _ = flowing.nothing_here


def test_a_module_of_the_package_is_still_reached_as_a_module() -> None:
    from hmz.runtime.flowing import engine

    assert engine is importlib.import_module("hmz.runtime.flowing.engine")
    assert flowing.run_flow is engine.run_flow
