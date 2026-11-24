"""`hmz runtimes`, `hmz easytier` and `hmz daemons` against real daemons, and `--daemon`.

This machine's daemon is the test's own, started by the first command that asks it. The other
machine is `hmz daemon serve` under a home of its own, listening on a TCP port of loopback:
paired from the code its `hmz devices pair` prints, kept in the registry under a name, and
asked by that name with `--daemon` and with `Client.named`.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli
from hmz.sdk import Client
from tests.conftest import places
from tests.integration.doubles_daemon import hosting, project

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.timeout(180)]

SECRET = "a secret of sixteen bytes and more"


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    with hosting():
        yield at


def _said(capsys: pytest.CaptureFixture[str], *line: str) -> Any:
    """What one command answers under `--json`, having done what it was asked."""
    capsys.readouterr()
    assert cli.main([*line, "--json"]) == 0, capsys.readouterr()
    return json.loads(capsys.readouterr().out)


def test_a_runtime_is_written_shown_changed_and_removed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _said(capsys, "runtimes", "list")["runtimes"] == []
    line = ["runtimes", "set", "ssh", "box", "--set", "host=10.0.0.7"]
    line += ["--set", "port=2222", "--set", "options=Compression=yes"]

    assert cli.main(line) == 0
    assert capsys.readouterr().out == "Saved\n"

    shown = _said(capsys, "runtimes", "show", "ssh", "box")
    assert (shown["backend"], shown["name"], shown["made"]) == ("ssh", "box", "typed")
    assert shown["fields"]["host"] == "10.0.0.7"
    assert shown["fields"]["port"] == 2222
    assert shown["fields"]["options"] == {"Compression": "yes"}
    assert cli.main(["runtimes", "list"]) == 0
    assert capsys.readouterr().out.splitlines()[1].split() == ["ssh", "box", "typed"]

    # Written again it is refused, in the daemon's words; replaced, it keeps what was unsaid.
    assert cli.main(line) == 1
    assert "box" in capsys.readouterr().err
    after = _said(
        capsys, "runtimes", "set", "ssh", "box", "--replace", "--set", "user=me"
    )
    fields = after["runtimes"][0]["fields"]
    assert (fields["host"], fields["port"], fields["user"]) == ("10.0.0.7", 2222, "me")

    assert cli.main(["runtimes", "set", "ssh", "bad", "--set", "port=many"]) == 1
    assert "port cannot be 'many'" in capsys.readouterr().err
    assert cli.main(["runtimes", "set", "ssh", "bad", "--set", "colour=red"]) == 1
    assert "colour" in capsys.readouterr().err

    assert _said(capsys, "runtimes", "remove", "ssh", "box") == {"runtimes": []}
    assert cli.main(["runtimes", "remove", "ssh", "box"]) == 1
    assert capsys.readouterr().err == (
        "hmz runtimes remove: There is no ssh runtime called box.\n"
    )
    assert cli.main(["runtimes", "check", "ssh", "box"]) == 1
    capsys.readouterr()


def test_the_hosts_of_the_ssh_config_are_listed_and_imported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = Path.home() / ".ssh" / "config"
    config.parent.mkdir(exist_ok=True)
    config.write_text("Host gpu-box\n  User me\n  Port 2222\n", encoding="utf-8")

    # Each resolved by `ssh` itself, which reads the login's own configuration beside this.
    hosts = _said(capsys, "runtimes", "hosts")["hosts"]
    assert [(one["alias"], one["saved"]) for one in hosts] == [("gpu-box", False)]

    assert cli.main(["runtimes", "import", "gpu-box"]) == 0
    assert capsys.readouterr().out == "Imported\n"
    listed = _said(capsys, "runtimes", "list")["runtimes"]
    assert [(one["backend"], one["name"], one["made"]) for one in listed] == [
        ("ssh", "gpu-box", "imported")
    ]
    assert _said(capsys, "runtimes", "hosts")["hosts"][0]["saved"] is True
    assert cli.main(["runtimes", "import", "nowhere"]) == 1
    assert "nowhere" in capsys.readouterr().err


def test_an_easytier_entry_is_written_with_a_secret_that_is_never_said(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LAB_SECRET", SECRET)
    line = ["easytier", "set", "lab", "--node", "tcp://a.example:11010"]

    # Without a secret, a new entry is refused in the daemon's words.
    assert cli.main(line) == 1
    assert capsys.readouterr().err.startswith("hmz easytier set: ")

    assert cli.main([*line, "--secret-env", "LAB_SECRET"]) == 0
    said = capsys.readouterr()
    assert said.out == "Saved\n"
    assert _said(capsys, "easytier", "list") == {
        "networks": [
            {"name": "lab", "nodes": ["tcp://a.example:11010"], "secret": True}
        ]
    }

    # Written again with a node alone, it keeps its secret.
    after = _said(capsys, "easytier", "set", "lab", "--node", "udp://b.example:11010")
    assert after["networks"][0] == {
        "name": "lab",
        "nodes": ["udp://b.example:11010"],
        "secret": True,
    }
    assert cli.main(["easytier", "list"]) == 0
    said = capsys.readouterr()
    assert said.out == "lab  true  udp://b.example:11010\n"
    assert SECRET not in said.out + said.err

    with Client.local() as client:
        assert [one.name for one in client.easytier.list()] == ["lab"]

    assert _said(capsys, "easytier", "remove", "lab") == {"networks": []}
    assert cli.main(["easytier", "remove", "lab"]) == 1
    assert capsys.readouterr().err == (
        "hmz easytier remove: There is no EasyTier entry lab.\n"
    )


@dataclasses.dataclass(frozen=True)
class _Served:
    """`hmz daemon serve` under a home of its own: its environment and the TCP port it took."""

    env: dict[str, str]
    port: int

    def code(self) -> str:
        """A pairing code it makes over its listener, as `hmz devices pair` prints it."""
        return subprocess.run(
            [sys.executable, "-m", "hmz", "devices", "pair"],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]


@pytest.fixture
def served(tmp_path: Path) -> Iterator[_Served]:
    """The daemon of another machine: one under a home of its own, listening on loopback."""
    there = dict(
        os.environ,
        **places(tmp_path / "served"),
        # Short, as a socket's path under it must be.
        TMPDIR=tempfile.mkdtemp(prefix="s", dir=os.environ["TMPDIR"]),
    )
    serving = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hmz",
            "daemon",
            "serve",
            "--listen",
            "tcp://127.0.0.1:0",
        ],
        env=there,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert serving.stdout is not None
        said = serving.stdout.readline()
        assert "listening on tcp://" in said
        yield _Served(there, int(said.strip().rsplit(":", 1)[1]))
    finally:
        serving.terminate()
        serving.wait(10)


def test_another_daemon_is_paired_kept_and_asked_by_its_name(
    served: _Served, capsys: pytest.CaptureFixture[str]
) -> None:
    route = f"tcp://127.0.0.1:{served.port}"
    assert _said(capsys, "daemons", "list") == {
        "daemons": [{"name": "local", "id": "", "routes": ["unix:"]}]
    }
    assert cli.main(["devices", "list", "--daemon", "lab"]) == 1
    assert capsys.readouterr().err == (
        "hmz devices list: No daemon is kept under the name lab.\n"
    )

    assert cli.main(["daemons", "pair", "lab", "hmz-pair:nope"]) == 1
    assert "not a pairing code" in capsys.readouterr().err
    paired = _said(
        capsys, "daemons", "pair", "lab", served.code(), "--device", "laptop"
    )
    assert (paired["name"], paired["routes"]) == ("lab", [route])
    assert _said(capsys, "daemons", "list")["daemons"][1] == paired
    assert _said(capsys, "daemons", "show", "lab") == paired | {
        "state": None,
        "version": None,
    }

    # The other daemon knows this machine as the device it was paired as; this one's knows none.
    there = _said(capsys, "devices", "list", "--daemon", "lab")["devices"]
    assert [one["name"] for one in there] == ["laptop"]
    assert _said(capsys, "devices", "list", "--daemon", "local") == {"devices": []}
    assert _said(capsys, "devices", "list") == {"devices": []}

    # What is written there is written there alone.
    line = ["runtimes", "set", "ssh", "far-box", "--set", "host=10.0.0.9"]
    assert cli.main([*line, "--daemon", "lab"]) == 0
    capsys.readouterr()
    assert [
        one["name"]
        for one in _said(capsys, "runtimes", "list", "--daemon", "lab")["runtimes"]
    ] == ["far-box"]
    assert _said(capsys, "runtimes", "list")["runtimes"] == []

    shown = _said(capsys, "daemons", "show", "lab", "--connect")
    assert (shown["state"], shown["id"]) == ("up", paired["id"])
    assert shown["version"]

    with Client.named("lab") as client:
        assert client.daemon_id == paired["id"]
        assert client.device == "laptop"
        assert [one.name for one in client.devices.list()] == ["laptop"]
        assert [one.name for one in client.runtimes.list().runtimes] == ["far-box"]
    with pytest.raises(LookupError):
        Client.named("nowhere")

    # A name taken is kept as it is; removed, it names nothing.
    assert cli.main(["daemons", "add", "lab", "stdio:ssh://elsewhere"]) == 1
    assert (
        capsys.readouterr().err == "hmz daemons add: There is already a daemon lab.\n"
    )
    assert _said(capsys, "daemons", "remove", "lab") == {"name": "lab"}
    assert cli.main(["devices", "list", "--daemon", "lab"]) == 1
    capsys.readouterr()


def test_a_daemon_added_by_a_route_that_reaches_nothing_cannot_be_reached(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["daemons", "add", "far", "tcp://127.0.0.1:1"]) == 1
    assert "needs the id" in capsys.readouterr().err

    identity = "abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrst"
    assert (
        cli.main(["daemons", "add", "far", "tcp://127.0.0.1:1", "--id", identity]) == 0
    )
    assert capsys.readouterr().out == "Added\n"

    assert cli.main(["devices", "list", "--daemon", "far", "--json"]) == 3
    said = capsys.readouterr()
    assert json.loads(said.out)["error"]["code"] == 503
    assert said.err == ""
