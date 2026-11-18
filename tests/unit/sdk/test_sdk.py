"""`hmz.sdk`: what a tool outside Humanize reaches it through, each name where it is written."""

from __future__ import annotations

import pytest

import hmz.daemon
import hmz.runtime
import hmz.runtime.flowing.fakes
import hmz.runtime.flowing.spi
import hmz.sdk
import hmz.sdk.client
import hmz.sdk.daemons
import hmz.sdk.running


@pytest.mark.parametrize(
    ("name", "layer"),
    [
        ("Accounts", hmz.runtime),
        ("Ask", hmz.runtime.flowing.spi),
        ("Epics", hmz.runtime),
        ("NousBook", hmz.runtime),
        ("Flows", hmz.runtime),
        ("Flowverses", hmz.runtime),
        ("Hmz", hmz.sdk.running),
        ("Refused", hmz.runtime),
        ("Run", hmz.sdk.running),
        ("Runtimes", hmz.runtime),
        ("Daemon", hmz.daemon),
        ("Link", hmz.daemon),
        ("Daemons", hmz.sdk.daemons),
        ("Client", hmz.sdk.client),
    ],
)
def test_each_name_is_the_object_its_layer_holds(name: str, layer: object) -> None:
    assert getattr(hmz.sdk, name) is getattr(layer, name)


def test_all_is_exactly_the_fifteen_names() -> None:
    assert hmz.sdk.__all__ == [
        "Accounts",
        "Ask",
        "Client",
        "Daemon",
        "Daemons",
        "Epics",
        "Flows",
        "Flowverses",
        "Hmz",
        "Link",
        "NousBook",
        "Refused",
        "Run",
        "Runtimes",
        "fakes",
    ]


def test_fakes_is_one_module_offering_the_runtimes_drivers() -> None:
    fakes = hmz.sdk.fakes
    assert fakes is hmz.sdk.fakes
    assert sorted(fakes.__all__) == [
        "Answer",
        "Command",
        "FakeAgentDriver",
        "FakeEnvDriver",
        "FakeOutworlder",
        "FakeSession",
        "Handler",
        "Reply",
        "run_fake",
    ]
    assert fakes.FakeAgentDriver is hmz.runtime.flowing.fakes.FakeAgentDriver


def test_fakes_is_reached_as_a_name_and_not_as_a_module() -> None:
    from hmz.sdk import fakes

    assert fakes is hmz.sdk.fakes
    with pytest.raises(ModuleNotFoundError):
        __import__("hmz.sdk.fakes")


def test_the_sdk_offers_no_host() -> None:
    assert not hasattr(hmz.sdk.Hmz, "host")
    with pytest.raises(AttributeError):
        getattr(hmz.sdk, "Host")  # noqa: B009


def test_everything_in_all_is_there() -> None:
    assert sorted(hmz.sdk.__all__) == hmz.sdk.__all__
    for name in hmz.sdk.__all__:
        assert getattr(hmz.sdk, name) is not None


def test_from_import_takes_every_name() -> None:
    namespace: dict[str, object] = {}
    exec("from hmz.sdk import *", namespace)  # noqa: S102
    assert set(hmz.sdk.__all__) <= set(namespace)


@pytest.mark.parametrize("name", ["Nothing", "_WRITTEN_NOT", "daemons_", "Host"])
def test_a_name_nobody_has_is_an_attribute_error(name: str) -> None:
    with pytest.raises(AttributeError, match=f"no attribute {name!r}"):
        getattr(hmz.sdk, name)
