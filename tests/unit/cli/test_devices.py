"""`hmz devices`: the paired devices listed and revoked, and a pairing code made."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from hmz.cli import main, tree


@pytest.fixture
def devices(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The devices family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    return client.devices


def test_the_devices_are_listed_in_columns(
    devices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    devices.list.return_value = [
        mock.Mock(fingerprint="ab:cd", added="2026-01-01", seen=None),
        mock.Mock(fingerprint="ef", added="2026-01-02", seen="2026-01-03"),
    ]
    devices.list.return_value[0].name = "phone"
    devices.list.return_value[1].name = "a"

    assert main(["devices", "list"]) == 0

    assert capsys.readouterr().out == (
        "phone  ab:cd  2026-01-01\na      ef     2026-01-02  2026-01-03\n"
    )


def test_revoking_says_how_many_sessions_closed(
    devices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    devices.revoke.return_value = 1

    assert main(["devices", "revoke", "phone"]) == 0
    assert capsys.readouterr().out == "Device revoked (1 session closed).\n"
    devices.revoke.assert_called_once_with("phone")

    assert main(["devices", "revoke", "phone", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"dropped": 1}


def test_a_code_is_printed_alone_and_its_end_beside_it(
    devices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    devices.pair.return_value = mock.Mock(code="hmz-1", expires=0)

    assert main(["devices", "pair", "--route", "tcp:h:1", "--seconds", "60"]) == 0

    said = capsys.readouterr()
    assert said.out == "hmz-1\n"
    assert said.err.startswith("Claim this code on the device before 19")
    devices.pair.assert_called_once_with(routes=["tcp:h:1"], seconds=60)

    assert main(["devices", "pair", "--json"]) == 0
    said = capsys.readouterr()
    assert json.loads(said.out) == {"code": "hmz-1", "expires": 0}
    assert said.err == ""
