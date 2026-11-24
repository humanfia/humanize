"""`hmz devices`, asked of a real daemon over its socket: nothing paired, and a refusal."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz import cli
from hmz.sdk import Client, Refused
from tests.integration.doubles_daemon import hosting, project

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.timeout(90)]


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    with hosting():
        yield at


def test_no_device_is_paired_with_a_daemon_just_started(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["devices", "list"]) == 0
    assert capsys.readouterr().out == ""

    assert cli.main(["devices", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"devices": []}


def test_revoking_a_device_that_is_not_paired_is_refused_in_the_daemons_words(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["devices", "revoke", "nobody"]) == 1
    assert capsys.readouterr().err == "hmz devices revoke: There is no device nobody.\n"

    assert cli.main(["devices", "revoke", "nobody", "--json"]) == 1
    said = capsys.readouterr()
    assert json.loads(said.out) == {
        "error": {"code": 404, "message": "There is no device nobody."}
    }
    assert said.err == ""


def test_a_daemon_listening_nowhere_has_no_route_to_pair_over(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["devices", "pair"]) == 1

    assert "There is no route to pair over" in capsys.readouterr().err


def test_the_same_is_asked_through_the_sdk() -> None:
    with Client.local() as client:
        assert client.devices.list() == []
        with pytest.raises(Refused, match="There is no device nobody") as refused:
            client.devices.revoke("nobody")
        assert refused.value.code == 404
        code = client.devices.pair(routes=["tcp:127.0.0.1:1"], seconds=60)
        assert code.code
        assert code.expires > 0
