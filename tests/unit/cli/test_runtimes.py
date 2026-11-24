"""`hmz runtimes`: runtimes listed, shown, written a field at a time, checked and imported."""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from hmz.cli import main, tree
from hmz.sdk.families.runtimes import Checked, Host, Listed, Runtime
from hmz.words import t

BLANKS: dict[str, dict[str, Any]] = {
    "ssh": {"host": "", "port": 0, "options": {}, "fallback": []},
    "docker": {"endpoint": "local", "cpus": 0.0, "gpus": []},
}


def _listed(*runtimes: Runtime) -> Listed:
    return Listed({"host": "here", "cpus": 8}, runtimes, BLANKS)


BOX = Runtime("ssh", "box", "typed", {"host": "h", "port": 22, "options": {"A": "b"}})


@pytest.fixture
def runtimes(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The runtimes family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    client.runtimes.list.return_value = _listed(BOX)
    client.runtimes.set.return_value = _listed(BOX)
    return client.runtimes


def test_the_runtimes_are_listed_under_this_machine(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["runtimes", "list"]) == 0
    assert capsys.readouterr().out == "local  here\nssh    box   typed\n"

    assert main(["runtimes", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "local": {"host": "here", "cpus": 8},
        "runtimes": [
            {"backend": "ssh", "name": "box", "made": "typed", "fields": BOX.fields}
        ],
        "blanks": BLANKS,
    }
    del runtimes


def test_a_runtime_is_shown_as_the_lines_set_takes(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["runtimes", "show", "ssh", "box"]) == 0
    assert capsys.readouterr().out == (
        'host=h\nport=22\noptions={"A": "b"}\nfallback=[]\n'
    )

    assert main(["runtimes", "show", "docker", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "backend": "docker",
        "name": None,
        "made": None,
        "fields": BLANKS["docker"],
    }
    del runtimes


def test_showing_what_is_not_there_is_refused(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["runtimes", "show", "ssh", "far"]) == 1
    assert capsys.readouterr().err == (
        "hmz runtimes show: There is no ssh runtime called far.\n"
    )

    assert main(["runtimes", "show", "vm", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": {
            "code": 400,
            "message": "vm is not a runtime backend; the backends are ssh, docker.",
        }
    }
    del runtimes


def test_a_field_is_read_as_its_blank_holds_it(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    line = ["runtimes", "set", "ssh", "new"]
    for said in (
        "host=10.0.0.7",
        "port=2222",
        "options=Compression=yes",
        "options=ProxyJump=a=b",
        "fallback=docker:lab",
        "fallback=local",
        "unknown=7",
    ):
        line += ["--set", said]

    assert main(line) == 0

    assert capsys.readouterr().out == "Saved\n"
    runtimes.set.assert_called_once_with(
        "ssh",
        "new",
        {
            "host": "10.0.0.7",
            "port": 2222,
            "options": {"Compression": "yes", "ProxyJump": "a=b"},
            "fallback": ["docker:lab", "local"],
            "unknown": "7",
        },
        replace=False,
    )


def test_many_values_are_given_as_json_or_cleared(runtimes: mock.Mock) -> None:
    line = ["runtimes", "set", "docker", "lab", "--set", 'gpus=["0", "1"]']
    line += ["--set", "cpus=1.5", "--set", "endpoint=", "--json"]

    assert main(line) == 0

    runtimes.set.assert_called_once_with(
        "docker",
        "lab",
        {"gpus": ["0", "1"], "cpus": 1.5, "endpoint": ""},
        replace=False,
    )

    runtimes.set.reset_mock()
    assert main(["runtimes", "set", "ssh", "x", "--set", "port=many"]) == 0
    runtimes.set.assert_called_once_with("ssh", "x", {"port": "many"}, replace=False)


def test_replacing_keeps_what_the_line_does_not_set(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    line = ["runtimes", "set", "ssh", "box", "--replace", "--set", "port=23"]
    line += ["--set", "options=", "--json"]

    assert main(line) == 0

    runtimes.set.assert_called_once_with(
        "ssh", "box", {"host": "h", "port": 23, "options": {}}, replace=True
    )
    assert json.loads(capsys.readouterr().out) == {
        "runtimes": [
            {"backend": "ssh", "name": "box", "made": "typed", "fields": BOX.fields}
        ]
    }


def test_a_set_that_names_no_field_is_a_line_that_cannot_be_read(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["runtimes", "set", "ssh", "box", "--set", "host"])

    assert raised.value.code == tree.UNREAD
    assert "host is not FIELD=VALUE." in capsys.readouterr().err
    runtimes.set.assert_not_called()


def test_a_runtime_is_removed(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    runtimes.remove.return_value = _listed()

    assert main(["runtimes", "remove", "ssh", "box"]) == 0
    assert capsys.readouterr().out == "Removed\n"
    runtimes.remove.assert_called_once_with("ssh", "box")

    assert main(["runtimes", "remove", "ssh", "box", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"runtimes": []}


def test_a_check_prints_what_was_answered_and_ends_4_where_nothing_was(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    said: dict[str, Any] = {"reached": True, "said": "", "cpus": 8.0, "gpus": ["0"]}
    runtimes.check.return_value = Checked(True, "", 8.0, 0, ("0",), (), said)

    assert main(["runtimes", "check", "ssh", "box"]) == 0
    assert capsys.readouterr().out == (
        'reached  true\nsaid\ncpus     8.0\ngpus     ["0"]\n'
    )
    runtimes.check.assert_called_once_with("ssh", "box")

    said = {"reached": False, "said": "no route"}
    runtimes.check.return_value = Checked(False, "no route", 0.0, 0, (), (), said)

    assert main(["runtimes", "check", "ssh", "box", "--json"]) == 4
    assert json.loads(capsys.readouterr().out) == said


def test_the_hosts_of_the_ssh_config_are_listed_and_imported(
    runtimes: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    one = {"alias": "box", "host": "10.0.0.7", "user": "me", "port": 22, "saved": True}
    two = {"alias": "b", "host": "b", "user": "", "port": 22, "saved": False}
    runtimes.hosts.return_value = (
        Host("box", "10.0.0.7", "me", 22, True, one),
        Host("b", "b", "", 22, False, two),
    )

    assert main(["runtimes", "hosts"]) == 0
    assert (
        capsys.readouterr().out
        == "box  10.0.0.7  me  22  Saved\nb    b             22\n"
    )

    assert main(["runtimes", "hosts", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"hosts": [one, two]}

    runtimes.import_.return_value = _listed(BOX)
    assert main(["runtimes", "import", "box", "b", "--update"]) == 0
    assert capsys.readouterr().out == "Imported\n"
    runtimes.import_.assert_called_once_with(["box", "b"], update=True)


def test_no_text_of_its_help_is_longer_than_thirty_words() -> None:
    """Section 3.3.2 of cli.md, which Section 3.3.4 holds a declared command to."""
    for text in tree.commands()["runtimes"].texts():
        assert len(t(text).split()) <= 30, text
