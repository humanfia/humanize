"""The settings family of daemon methods, served by a `Dispatcher` over a real socket pair.

Every method of `settings.*`, `accounts.*`, `nous.*`, `runtimes.*` and `easytier.*` called
once from a client `Peer`, in a temporary `HUMANIZE_HOME`, with what each writes read back out
of the settings file and what each refuses refused with the protocol's code.
"""

from __future__ import annotations

import contextlib
import json
import socket
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from hmz import home
from hmz.daemon.api import accounts, easytier, nous, runtimes, settings
from hmz.rpc import PROTOCOL, Call, Dispatcher, Peer, RpcError, admit, document, hello
from tests.integration.doubles_easytier import kuma

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: Every family this suite serves.
_FAMILIES = (settings, accounts, nous, runtimes, easytier)

#: A secret of the kind that must never come back out.
_SECRET = "an easytier secret of many bytes"
_KEY = "sk-never-shown-0123"
_TURN = "turn-credential-hunter2"


class _Shut(socket.socket):
    """A stream socket shut down before it is closed, so that closing it wakes its reader."""

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.shutdown(socket.SHUT_RDWR)
        super().close()


def _hello(call: Call) -> dict[str, Any]:
    admit(call.params["protocol"])
    return {"daemon_id": "d", "protocol": PROTOCOL, "paired": True}


@pytest.fixture
def client() -> Iterator[Peer]:
    """A client's end of a session whose daemon end serves the settings family."""
    serving = Dispatcher()
    serving.register("session.hello", _hello)
    for family in _FAMILIES:
        for name, handler in family.METHODS.items():
            serving.register(name, handler)
    daemon_end, client_end = socket.socketpair()
    daemon = Peer(_Shut(fileno=daemon_end.detach()), serving, name="daemon")
    there = Peer(client_end, Dispatcher(), name="client")
    hello(there, "test", "cli", timeout=5)
    yield there
    there.close()
    daemon.close()


def _call(client: Peer, method: str, **params: Any) -> Any:
    return client.call(method, params, timeout=30)


def _refused(client: Peer, code: int, method: str, **params: Any) -> str:
    with pytest.raises(RpcError) as refused:
        _call(client, method, **params)
    assert refused.value.code == code, refused.value.message
    return refused.value.message


def _file() -> dict[str, Any]:
    return yaml.safe_load((home() / "settings.yaml").read_text())


def test_each_family_names_every_method_of_its_namespace() -> None:
    listed = {one["name"] for one in document()["methods"]}
    for family in _FAMILIES:
        prefix = f"{family.__name__.rsplit('.', 1)[1]}."
        assert set(family.METHODS) == {n for n in listed if n.startswith(prefix)}


def test_settings_are_read_and_forgotten_where_no_directory_is_left(
    client: Peer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, started = tmp_path / "workspace", tmp_path / "started"
    for one in (workspace, started):
        one.mkdir()
    chat = _call(client, "settings.set", workspace=str(workspace), chat="claude/opus")[
        "chat"
    ]
    assert chat
    assert str(workspace.resolve()) in _file()["workspaces"]
    # The daemon outlives the directory it was started in, and a workspace its directory.
    monkeypatch.chdir(started)
    for one in (workspace, started):
        one.rmdir()

    assert _call(client, "settings.get")["chat"] == ""
    assert _call(client, "settings.get", workspace=str(workspace))["chat"] == chat
    for method in ("accounts.list", "nous.list", "runtimes.list"):
        assert _call(client, method)
    forgot = _call(client, "settings.forget", workspace=str(workspace))
    assert (forgot["forgot"], forgot["chat"]) == (True, "")
    assert str(workspace.resolve()) not in (_file().get("workspaces") or {})
    assert _refused(client, 404, "settings.set", workspace=str(workspace)) == (
        f"There is no directory {workspace}."
    )


def test_settings_are_written_read_back_and_never_echo_a_secret(
    client: Peer, tmp_path: Path
) -> None:
    workspace = str(tmp_path)
    assert _call(client, "easytier.list") == {"networks": []}
    made = _call(
        client, "easytier.set", name="lab", secret=_SECRET, nodes=["tcp://n.lab:11010"]
    )
    assert made == {
        "networks": [{"name": "lab", "nodes": ["tcp://n.lab:11010"], "secret": True}]
    }
    turn = {"urls": ["turn:t.lab:3478"], "username": "me", "credential": _TURN}

    said = _call(
        client,
        "settings.set",
        workspace=workspace,
        ai_chan="claude/opus",
        details=True,
        reports=False,
        backup={"targets": [{"name": "t", "url": "https://me:pw@x.lab/e.git"}]},
        listen=["tcp://127.0.0.1:0", "easytier:lab"],
        ice_servers=[turn],
        idem="once",
    )

    file = _file()
    assert (file["ai_chan"], file["details"], file["enable_sentry"]) == (
        "claude/opus",
        True,
        False,
    )
    assert file["listen"] == ["tcp://127.0.0.1:0", "easytier:lab"]
    assert file["ice_servers"] == [turn]
    assert file["easytier"]["lab"]["secret"] == _SECRET
    assert file["backup"]["targets"][0]["url"] == "https://me:pw@x.lab/e.git"
    assert said["ice_servers"] == [turn | {"credential": True}]
    assert said["backup"]["targets"][0]["url"] == "https://***@x.lab/e.git"
    assert _call(client, "settings.get", workspace=workspace) == said
    shown = json.dumps(said) + json.dumps(_call(client, "easytier.list"))
    assert [one for one in (_SECRET, _TURN, "pw@") if one in shown] == []

    # Sent back as it was shown, a credential is the one written.
    _call(client, "settings.set", workspace=workspace, ice_servers=said["ice_servers"])
    assert _file()["ice_servers"] == [turn]
    assert _refused(client, 400, "settings.set", listen=["unix:/x"]) == (
        "unix:/x is not a listener."
    )
    assert _refused(client, 400, "settings.set", workspace="here") == (
        "Say the workspace as a whole path, not here."
    )
    assert _refused(client, 409, "easytier.remove", name="lab") == "lab is listened on."
    assert _refused(
        client, 400, "easytier.set", name="x", secret="short", nodes=["tcp://n:1"]
    ) == ("A secret must be at least 16 bytes.")
    _refused(client, -32602, "settings.set", details="yes")
    assert _call(client, "settings.forget", workspace=workspace)["forgot"] is False
    _call(client, "settings.set", workspace=workspace, listen=[])
    assert _call(client, "easytier.remove", name="lab") == {"networks": []}
    assert _refused(client, 404, "easytier.remove", name="lab") == (
        "There is no EasyTier entry lab."
    )


def test_accounts_are_made_corrected_and_removed_without_their_values(
    client: Peer,
) -> None:
    backends = _call(client, "accounts.list")["backends"]
    claude = next(one for one in backends if one["cli"] == "claude")
    way = next(one for one in claude["ways"] if not one["terminal"] and one["asks"])
    asks = {one["env"]: _KEY for one in way["asks"] if not one["fixed"]}

    made = _call(
        client,
        "accounts.create",
        cli="claude",
        name="work",
        way=way["name"],
        answers=asks,
    )

    assert _KEY not in json.dumps(made)
    assert ("claude", "work") in {(one["cli"], one["name"]) for one in made["accounts"]}
    _refused(
        client,
        409,
        "accounts.create",
        cli="claude",
        name="work",
        way=way["name"],
        answers=asks,
    )
    corrected = _call(client, "accounts.correct", cli="claude", name="work", answers={})
    assert _KEY not in json.dumps(corrected)
    _refused(
        client,
        400,
        "accounts.correct",
        cli="claude",
        name="work",
        answers={"NOT_ASKED": "x"},
    )
    _refused(client, 404, "accounts.correct", cli="claude", name="nobody")
    _refused(client, 404, "accounts.models", cli="claude", name="nobody")
    _refused(client, 404, "accounts.copy", cli="claude", name="nobody", into="codex")
    copied = _call(client, "accounts.copy", cli="claude", name="work", into="claude")
    assert _KEY not in json.dumps(copied)
    removed = _call(client, "accounts.remove", cli="claude", name="work")
    assert ("claude", "work") not in {
        (o["cli"], o["name"]) for o in removed["accounts"]
    }
    _refused(client, 404, "accounts.remove", cli="claude", name="work")


def test_nous_and_runtimes_are_written_into_the_settings_file(
    client: Peer, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = _call(client, "nous.list")
    assert listed["default"] in {one["name"] for one in listed["policies"]}
    assert "shuffle" in {one["name"] for one in listed["strategies"]}
    assert "*" in listed["faults"]
    written = _call(
        client, "nous.set", name="claude/opus", then=["codex/gpt"], tries=2, timeout=5
    )
    assert written["nous"][0]["then"]["nodes"][0]["use"] == "codex/gpt"
    assert "nous" in _file()
    graph = {
        "start": "p",
        "nodes": [
            {
                "id": "p",
                "balance": "round-robin",
                "among": [{"nous": "claude/opus", "weight": 2}, {"nous": "codex/gpt"}],
                "on": {"throttled": "q"},
            },
            {"id": "q", "use": "grok/g"},
        ],
    }
    made = _call(client, "nous.set", name="smart", graph=graph)
    assert [one["name"] for one in made["nous"]] == ["claude/opus", "smart"]
    _refused(client, 400, "nous.set", name="opus")
    _refused(client, 400, "nous.set", name="smart", graph={"start": "x", "nodes": []})
    _refused(client, 400, "nous.set", name="claude/opus", then=["smart", "claude/opus"])
    renamed = _call(client, "nous.rename", name="smart", to="clever")
    assert [one["name"] for one in renamed["nous"]] == ["claude/opus", "clever"]
    _refused(client, 400, "nous.rename", name="ghost", to="other")
    assert [
        one["name"] for one in _call(client, "nous.clear", name="clever")["nous"]
    ] == ["claude/opus"]
    assert _call(client, "nous.clear", name="claude/opus")["nous"] == []
    _refused(client, 404, "nous.clear", name="claude/opus")

    assert _call(client, "runtimes.list")["runtimes"] == []
    made = _call(
        client, "runtimes.set", backend="ssh", name="gpu", fields={"host": "gpu.lab"}
    )
    assert made["runtimes"][0]["host"] == "gpu.lab"
    assert "runtimes" in _file()
    _refused(
        client, 400, "runtimes.set", backend="ssh", name="gpu", fields={"name": "x"}
    )
    _refused(client, 404, "runtimes.check", backend="ssh", name="nowhere")
    assert "hosts" in _call(client, "runtimes.hosts")
    _refused(client, 400, "runtimes.import", names=[])
    assert _call(client, "runtimes.remove", backend="ssh", name="gpu")["runtimes"] == []
    _refused(client, 404, "runtimes.remove", backend="ssh", name="gpu")

    with kuma({"publicGroupList": []}, {}, monkeypatch):
        assert _call(client, "easytier.nodes") == {"nodes": []}
    assert "could not be read" in _refused(client, 503, "easytier.nodes")
