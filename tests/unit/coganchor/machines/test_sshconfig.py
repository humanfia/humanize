from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines.sshconfig import SSHHost, aliases, default, hosts, resolve

if TYPE_CHECKING:
    from pathlib import Path

    from tests.unit.coganchor.machines.conftest import Runs


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    at = tmp_path / "home"
    (at / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(at))
    return at


def test_the_users_own_config_is_under_their_home(home: Path) -> None:
    assert default() == home / ".ssh" / "config"


def test_no_config_names_no_hosts(home: Path) -> None:
    assert aliases() == []


def test_every_host_is_named_once_in_order_and_patterns_are_not_hosts(
    tmp_path: Path,
) -> None:
    at = tmp_path / "config"
    at.write_text(
        "# hosts\n"
        "Host a b\n"
        "  HostName 10.0.0.1\n"
        "Host *.lan !c d?\n"
        "Host=e a # trailing comment\n"
        'Host "unclosed\n'
        "Host\n"
    )

    assert aliases(at) == ["a", "b", "e"]


def test_includes_are_followed_as_ssh_follows_them(home: Path) -> None:
    (home / ".ssh" / "config").write_text("Host first\nInclude conf.d/*\n")
    (home / ".ssh" / "conf.d").mkdir()
    (home / ".ssh" / "conf.d" / "b").write_text("Host second\n")
    (home / ".ssh" / "conf.d" / "a").write_text(f"Include {home}/abs\n")
    (home / "abs").write_text("Host third\n")

    assert aliases() == ["first", "third", "second"]


def test_an_include_that_includes_itself_stops(home: Path) -> None:
    (home / ".ssh" / "config").write_text("Host loop\nInclude config\n")

    assert aliases() == ["loop"]


def test_a_destination_is_what_ssh_makes_of_it(runs: Runs) -> None:
    runs.on(
        "ssh",
        out=(
            "hostname 10.0.0.1\nuser me\nport 2222\n"
            "identityfile ~/.ssh/work\nproxyjump bastion\nhostname ignored\n"
        ),
    )

    said = resolve("gpu", ("-F", "/cfg"), alias="g")

    assert said == SSHHost(
        alias="g",
        host="10.0.0.1",
        user="me",
        port=2222,
        identity_files=("~/.ssh/work",),
        proxy_jump="bastion",
    )
    assert runs.calls == [["ssh", "-G", "-F", "/cfg", "--", "gpu"]]


def test_the_keys_ssh_tries_on_its_own_are_no_key_anybody_chose(runs: Runs) -> None:
    runs.on(
        "ssh",
        out=(
            "identityfile ~/.ssh/id_rsa\nidentityfile ~/.ssh/id_ecdsa\n"
            "identityfile ~/.ssh/id_ed25519\nproxyjump none\nport x\n"
        ),
    )

    said = resolve("box")

    assert said == SSHHost(alias="box", host="box", user="", port=22)


def test_a_config_ssh_cannot_read_is_an_error(runs: Runs) -> None:
    runs.on("ssh", status=255, err="bad configuration option")

    with pytest.raises(OSError, match="bad configuration option"):
        resolve("box")


def test_an_ssh_that_does_not_answer_in_time_is_an_error(runs: Runs) -> None:
    runs.on("ssh", timeout=True)

    with pytest.raises(TimeoutError, match="timed out after 1s"):
        resolve("box", seconds=1)


def test_every_host_of_a_config_is_resolved_under_that_config(
    runs: Runs, tmp_path: Path
) -> None:
    at = tmp_path / "config"
    at.write_text("Host a b\n")

    found = hosts(at)

    assert [one.alias for one in found] == ["a", "b"]
    assert runs.calls == [
        ["ssh", "-G", "-F", str(at), "--", "a"],
        ["ssh", "-G", "-F", str(at), "--", "b"],
    ]
