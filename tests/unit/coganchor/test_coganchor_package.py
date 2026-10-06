"""The front door of `hmz.coganchor`: what it offers, fetched when it is named."""

from __future__ import annotations

import importlib.metadata

import pytest

import hmz.coganchor
from hmz.coganchor import anchor


def test_it_offers_the_anchor_and_the_version() -> None:
    assert sorted(hmz.coganchor.__all__) == [
        "AnchorConfig",
        "__version__",
        "check",
        "connect",
        "drive",
    ]


@pytest.mark.parametrize("name", ["AnchorConfig", "check", "connect", "drive"])
def test_each_name_is_the_one_the_anchor_holds(name: str) -> None:
    assert getattr(hmz.coganchor, name) is getattr(anchor, name)


def test_the_version_is_the_installed_one() -> None:
    assert hmz.coganchor.__version__ == importlib.metadata.version("hmz")


def test_the_version_is_unknown_where_nothing_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    # Set and taken away again through the monkeypatch, so that whatever was read here is
    # gone by the next test and the real version is read again.
    monkeypatch.setattr(hmz.coganchor, "__version__", "held", raising=False)
    monkeypatch.delattr(hmz.coganchor, "__version__")
    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert hmz.coganchor.__version__ == "unknown"


def test_a_name_it_does_not_offer_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no attribute 'nothing'"):
        _ = hmz.coganchor.nothing
