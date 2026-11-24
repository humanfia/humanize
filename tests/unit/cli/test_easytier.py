"""`hmz easytier`: entries listed, written with a secret that is never on the line, removed."""

from __future__ import annotations

import io
import json
from unittest import mock

import pytest

from hmz.cli import main, tree
from hmz.sdk.families.easytier import Network, Node
from hmz.words import t

LAB = Network("lab", ("tcp://a:1", "udp://b:2"), secret=True)
SAID = {
    "networks": [{"name": "lab", "nodes": ["tcp://a:1", "udp://b:2"], "secret": True}]
}


@pytest.fixture
def easytier(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The EasyTier family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    client.easytier.list.return_value = (LAB,)
    client.easytier.set.return_value = (LAB,)
    client.easytier.remove.return_value = ()
    return client.easytier


def test_the_entries_are_listed_without_their_secrets(
    easytier: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["easytier", "list"]) == 0
    assert capsys.readouterr().out == "lab  true  tcp://a:1 udp://b:2\n"

    assert main(["easytier", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == SAID
    del easytier


def test_a_secret_is_read_from_standard_input(
    easytier: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("sixteen bytes or more\n"))

    assert (
        main(["easytier", "set", "lab", "--node", "tcp://a:1", "--secret-stdin"]) == 0
    )

    said = capsys.readouterr()
    assert said.out == "Saved\n"
    assert "sixteen" not in said.out + said.err
    easytier.set.assert_called_once_with(
        "lab", ["tcp://a:1"], secret="sixteen bytes or more"
    )
    easytier.list.assert_not_called()


def test_a_secret_is_read_from_the_environment(
    easytier: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("LAB_SECRET", "a secret of the lab")
    line = ["easytier", "set", "lab", "--node", "tcp://a:1", "--secret-env"]

    assert main([*line, "LAB_SECRET", "--json"]) == 0
    easytier.set.assert_called_once_with(
        "lab", ["tcp://a:1"], secret="a secret of the lab"
    )
    assert json.loads(capsys.readouterr().out) == SAID

    assert main([*line, "NOT_SET_ANYWHERE"]) == 1
    assert capsys.readouterr().err == (
        "hmz easytier set: The environment variable NOT_SET_ANYWHERE is not set.\n"
    )

    assert main([*line, "LAB_SECRET", "--secret-stdin"]) == 1
    assert capsys.readouterr().err == (
        "hmz easytier set: Give `--secret-stdin` or `--secret-env`, not both.\n"
    )
    assert easytier.set.call_count == 1


def test_a_secret_that_cannot_be_read_is_refused_before_any_daemon_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reach = mock.Mock()
    monkeypatch.setattr(tree, "reach", reach)

    assert main(["easytier", "set", "lab", "--secret-env", "NOT_SET_ANYWHERE"]) == 1
    reach.assert_not_called()


def test_an_entry_written_again_keeps_what_the_line_does_not_say(
    easytier: mock.Mock,
) -> None:
    assert main(["easytier", "set", "lab"]) == 0
    easytier.set.assert_called_once_with("lab", LAB.nodes, secret=None)

    easytier.set.reset_mock()
    assert main(["easytier", "set", "new"]) == 0
    easytier.set.assert_called_once_with("new", (), secret=None)


def test_an_entry_is_removed(
    easytier: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["easytier", "remove", "lab"]) == 0
    assert capsys.readouterr().out == "Removed\n"
    easytier.remove.assert_called_once_with("lab")

    assert main(["easytier", "remove", "lab", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"networks": []}


def test_the_shared_nodes_are_listed_as_they_stand(
    easytier: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    easytier.nodes.return_value = (
        Node("tcp://a:1", "A", "2.4", up=True, uptime=0.5),
        Node("tcp://b:1", "", "", up=False, uptime=None),
        Node("tcp://c:1", "C", "", up=None, uptime=None),
    )

    assert main(["easytier", "nodes"]) == 0
    assert capsys.readouterr().out == (
        "tcp://a:1  up    50% up in 24h  2.4  A\n"
        "tcp://b:1  down\n"
        "tcp://c:1                            C\n"
    )

    assert main(["easytier", "nodes", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["nodes"][0] == {
        "url": "tcp://a:1",
        "name": "A",
        "version": "2.4",
        "up": True,
        "uptime": 0.5,
    }


def test_no_text_of_its_help_is_longer_than_thirty_words() -> None:
    """Section 3.3.2 of cli.md, which Section 3.3.4 holds a declared command to."""
    for text in tree.commands()["easytier"].texts():
        assert len(t(text).split()) <= 30, text
