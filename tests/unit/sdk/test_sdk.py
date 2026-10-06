"""`hmz.sdk`: what a tool outside humanize reaches it through, handed through as itself."""

from __future__ import annotations

import pytest

import hmz.daemon
import hmz.runtime
import hmz.runtime.flowing.fakes
import hmz.sdk
import hmz.sdk.daemons


@pytest.mark.parametrize(
    ("name", "layer"),
    [
        ("Accounts", hmz.runtime),
        ("Epics", hmz.runtime),
        ("Fallbacks", hmz.runtime),
        ("Flows", hmz.runtime),
        ("Flowverses", hmz.runtime),
        ("Hmz", hmz.runtime),
        ("Host", hmz.runtime),
        ("Refused", hmz.runtime),
        ("Run", hmz.runtime),
        ("Runtimes", hmz.runtime),
        ("Daemon", hmz.daemon),
        ("Link", hmz.daemon),
        ("Daemons", hmz.sdk.daemons),
    ],
)
def test_each_name_is_the_object_its_layer_holds(name: str, layer: object) -> None:
    assert getattr(hmz.sdk, name) is getattr(layer, name)


def test_fakes_is_the_runtimes_kit_as_a_module() -> None:
    assert hmz.sdk.fakes is hmz.runtime.flowing.fakes


def test_everything_in_all_is_there() -> None:
    assert sorted(hmz.sdk.__all__) == hmz.sdk.__all__
    for name in hmz.sdk.__all__:
        assert getattr(hmz.sdk, name) is not None


def test_from_import_takes_every_name() -> None:
    namespace: dict[str, object] = {}
    exec("from hmz.sdk import *", namespace)  # noqa: S102
    assert set(hmz.sdk.__all__) <= set(namespace)


@pytest.mark.parametrize("name", ["Nothing", "_WRITTEN_NOT", "daemons_"])
def test_a_name_nobody_has_is_an_attribute_error(name: str) -> None:
    with pytest.raises(AttributeError, match=f"no attribute {name!r}"):
        getattr(hmz.sdk, name)
