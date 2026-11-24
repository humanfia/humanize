"""`hmz daemons`: the daemons of other machines listed, added, shown, paired and removed."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest import mock

import pytest

import hmz.runtime.doing.daemons
from hmz.cli import main, tree
from hmz.words import t

ID = "abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrst"
GPU: dict[str, Any] = {"name": "gpu", "id": "", "routes": ["stdio:ssh://gpu-box"]}
LOCAL: dict[str, Any] = {"name": "local", "id": "", "routes": ["unix:"]}


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The registry of other machines' daemons, stood in: `gpu` is kept in it."""
    held = mock.Mock()
    held.all.return_value = [GPU]

    def find(name: str) -> dict[str, Any] | None:
        return dict(GPU) if name == "gpu" else None

    def write(
        name: str, fields: dict[str, Any], *, replace: bool = False
    ) -> dict[str, Any]:
        if find(name) is not None and not replace:
            raise FileExistsError(name)
        return {"name": name, **fields}

    held.find.side_effect = find
    held.write.side_effect = write
    monkeypatch.setattr(
        hmz.runtime.doing.daemons, "Daemons", mock.Mock(return_value=held)
    )
    return held


def test_the_daemons_are_listed_under_this_machines(
    registry: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["daemons", "list"]) == 0
    assert capsys.readouterr().out == "local    unix:\ngpu      stdio:ssh://gpu-box\n"

    assert main(["daemons", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"daemons": [LOCAL, GPU]}
    del registry


def test_a_daemon_is_added_by_its_routes(
    registry: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    line = ["daemons", "add", "lab", "tcp://h:1", "ws://h:2", "--id", ID]

    assert main(line) == 0
    assert capsys.readouterr().out == "Added\n"
    registry.write.assert_called_once_with(
        "lab", {"id": ID, "routes": ["tcp://h:1", "ws://h:2"]}, replace=False
    )

    assert main(["daemons", "add", "far", "stdio:ssh://far", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "name": "far",
        "id": "",
        "routes": ["stdio:ssh://far"],
    }


def test_a_name_taken_is_refused_unless_it_is_to_be_replaced(
    registry: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["daemons", "add", "gpu", "stdio:ssh://other"]) == 1
    assert (
        capsys.readouterr().err == "hmz daemons add: There is already a daemon gpu.\n"
    )
    registry.write.reset_mock()

    assert main(["daemons", "add", "gpu", "stdio:ssh://other", "--replace"]) == 0
    assert capsys.readouterr().out == "Saved\n"
    registry.write.assert_called_once_with(
        "gpu", {"id": "", "routes": ["stdio:ssh://other"]}, replace=True
    )


def test_a_daemon_that_cannot_be_one_is_refused_in_the_registrys_words(
    registry: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["daemons", "add", "lab"]) == 1
    assert capsys.readouterr().err == (
        "hmz daemons add: A daemon needs at least one route.\n"
    )

    registry.write.side_effect = ValueError("tcp://h:1 needs the id of the daemon.")
    assert main(["daemons", "add", "lab", "tcp://h:1", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 400, "message": "tcp://h:1 needs the id of the daemon."}
    }


def test_a_daemon_is_removed(
    registry: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["daemons", "remove", "gpu"]) == 0
    assert capsys.readouterr().out == "Removed\n"
    registry.remove.assert_called_once_with("gpu")

    assert main(["daemons", "remove", "far"]) == 1
    assert capsys.readouterr().err == "hmz daemons remove: There is no daemon far.\n"

    registry.remove.side_effect = ValueError("Local is always there.")
    assert main(["daemons", "remove", "local", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 400, "message": "Local is always there."}
    }


def test_a_daemon_is_shown_as_it_is_kept(
    registry: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["daemons", "show", "gpu"]) == 0
    assert capsys.readouterr().out == ("name    gpu\nid\nroutes  stdio:ssh://gpu-box\n")

    assert main(["daemons", "show", "gpu", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == GPU | {"state": None, "version": None}

    assert main(["daemons", "show", "far"]) == 1
    assert capsys.readouterr().err == "hmz daemons show: There is no daemon far.\n"
    del registry


def test_a_daemon_shown_connected_is_reached_as_the_daemon_option_reaches_it(
    registry: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = mock.MagicMock(version="1.2.3", daemon_id=ID)
    client.__enter__.return_value = client
    reach = mock.Mock(return_value=client)
    monkeypatch.setattr(tree, "reach", reach)

    assert main(["daemons", "show", "gpu", "--connect", "--json"]) == 0

    reach.assert_called_once_with("gpu")
    assert json.loads(capsys.readouterr().out) == {
        "name": "gpu",
        "id": ID,
        "routes": ["stdio:ssh://gpu-box"],
        "state": "up",
        "version": "1.2.3",
    }

    reach.side_effect = ConnectionError("gpu is not reached yet.")
    assert main(["daemons", "show", "gpu", "--connect"]) == tree.UNREACHED
    assert capsys.readouterr().err == (
        "hmz daemons show: the daemon cannot be reached: gpu is not reached yet.\n"
    )
    del registry


def test_a_pairing_code_is_claimed_and_its_daemon_kept(
    registry: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    remotes = registry.remotes.return_value
    remotes.pair.return_value = {"name": "lab", "id": ID, "routes": ["tcp://h:1"]}

    assert main(["daemons", "pair", "lab", "hmz-pair:abc", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == remotes.pair.return_value
    remotes.pair.assert_called_once_with("lab", "hmz-pair:abc", device=None)
    remotes.close.assert_called_once_with()

    monkeypatch.setattr("sys.stdin", io.StringIO("hmz-pair:xyz\n"))
    assert main(["daemons", "pair", "lab", "-", "--device", "laptop"]) == 0
    assert capsys.readouterr().out == "Added\n"
    remotes.pair.assert_called_with("lab", "hmz-pair:xyz", device="laptop")


def test_a_code_refused_or_carried_nowhere_is_said_so(
    registry: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    remotes = registry.remotes.return_value
    unreached = hmz.runtime.doing.daemons.Unreached

    assert main(["daemons", "pair", "gpu", "hmz-pair:abc"]) == 1
    assert capsys.readouterr().err == (
        "hmz daemons pair: There is already a daemon gpu.\n"
    )
    remotes.pair.assert_not_called()

    remotes.pair.side_effect = ValueError("That is not a pairing code.")
    assert main(["daemons", "pair", "lab", "nope"]) == 1
    assert capsys.readouterr().err == "hmz daemons pair: That is not a pairing code.\n"

    remotes.pair.side_effect = unreached("That pairing code is not valid.", status=403)
    assert main(["daemons", "pair", "gpu", "hmz-pair:abc", "--replace", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": 403, "message": "That pairing code is not valid."}
    }

    remotes.pair.side_effect = OSError("the settings file cannot be written")
    assert main(["daemons", "pair", "lab", "hmz-pair:abc", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == 500

    remotes.pair.side_effect = unreached("No route opened.")
    assert main(["daemons", "pair", "lab", "hmz-pair:abc"]) == tree.UNREACHED
    assert capsys.readouterr().err == (
        "hmz daemons pair: the daemon cannot be reached: No route opened.\n"
    )
    assert remotes.close.call_count == 4


def test_no_text_of_its_help_is_longer_than_thirty_words() -> None:
    """Section 3.3.2 of cli.md, which Section 3.3.4 holds a declared command to."""
    for text in tree.commands()["daemons"].texts():
        assert len(t(text).split()) <= 30, text
