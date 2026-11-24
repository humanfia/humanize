"""The port the last `hmz web` of a home listened on, as `<home>/web-port` keeps it."""

from __future__ import annotations

import pytest

from hmz import state
from hmz.web import kept_port


def test_no_port_is_kept_where_nothing_was_written() -> None:
    assert kept_port() == 0


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("8123", 8123),
        ("1", 1),
        ("65535", 65535),
        ("0", 0),
        ("65536", 0),
        ("-1", 0),
        ("80 ", 0),
        ("eighty", 0),
        ("", 0),
    ],
)
def test_only_a_port_from_1_to_65535_is_read_as_one(written: str, read: int) -> None:
    state().mkdir(parents=True, exist_ok=True)
    (state() / "web-port").write_text(written)

    assert kept_port() == read
