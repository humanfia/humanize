"""`hmz fence`: its help, what it reports, and what it answers for a path."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

import hmz.cli.fence
import hmz.coganchor.fence
from hmz.cli import main

#: What `coganchor internal able` says of a machine that can do both.
TOLD: dict[str, Any] = {
    "fs": True,
    "net": True,
    "backend": {"fs": "landlock", "net": "landlock"},
    "landlock": {"abi": 6, "network": True, "scope": True},
    "seccomp": {"notify": True},
    "loopback": {"pidfd_getfd": True, "ptrace_scope": 1},
    "bubblewrap": {"fs": False, "net": False},
}


def test_help_names_both_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["fence", "--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert "check" in out
    assert "explain" in out

    for argv in (["fence", "check", "--help"], ["fence", "explain", "--help"]):
        with pytest.raises(SystemExit) as raised:
            main(argv)
        assert raised.value.code == 0
    out = capsys.readouterr().out
    for option in ("-f", "-a", "--json"):
        assert option in out
    assert "PATH" in out


def _facts() -> dict[str, Any]:
    return dict(TOLD)


def _chosen() -> str:
    return "auto"


def test_check_reports_what_the_machine_can_hold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.cli.fence, "_facts", _facts)
    monkeypatch.setattr(hmz.coganchor.fence, "chosen", _chosen)

    assert main(["fence", "check"]) == 0
    out = capsys.readouterr().out
    assert "sandbox        auto -> landlock" in out
    assert "landlock       ABI 6; paths and TCP" in out
    assert "seccomp        user notification available" in out
    assert "loopback       pidfd_getfd available; ptrace_scope 1" in out


def _nothing() -> dict[str, Any]:
    return {"fs": False, "net": False, "backend": {"fs": None, "net": None}}


def test_check_says_one_when_the_fence_cannot_be_put_up(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.cli.fence, "_facts", _nothing)
    monkeypatch.setattr(hmz.coganchor.fence, "chosen", _chosen)

    assert main(["fence", "check"]) == 1
    assert "sandbox        auto -> none" in capsys.readouterr().out


def test_check_writes_one_object_to_a_program(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.cli.fence, "_facts", _facts)
    monkeypatch.setattr(hmz.coganchor.fence, "chosen", _chosen)

    assert main(["fence", "check", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["fs"] is True
    assert said["net"] is True
    assert said["sandbox"] == "auto"
    assert said["fence"] is None
    assert said["unheld"] is None
    assert said["landlock"]["abi"] == 6


def _facts_of(told: dict[str, Any]) -> Any:
    def facts() -> dict[str, Any]:
        return dict(told)

    return facts


def test_check_names_a_missing_landlock_seccomp_and_ptrace_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        hmz.cli.fence,
        "_facts",
        _facts_of(
            {
                "fs": False,
                "net": False,
                "backend": {"fs": None, "net": None},
                "landlock": {"abi": 0, "network": False, "scope": False},
                "seccomp": {"notify": False},
                "loopback": {"pidfd_getfd": False, "ptrace_scope": 2},
            }
        ),
    )
    monkeypatch.setattr(hmz.coganchor.fence, "chosen", _chosen)

    assert main(["fence", "check"]) == 1
    out = capsys.readouterr().out
    assert "missing: no Landlock" in out
    assert "user notification missing (the network cut needs it)" in out
    assert "restricted: a supervisor needs it below 2" in out


def test_check_names_the_abis_a_lower_kernel_lacks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        hmz.cli.fence,
        "_facts",
        _facts_of(
            {
                "fs": True,
                "net": False,
                "backend": {"fs": "landlock", "net": None},
                "landlock": {"abi": 3, "network": False, "scope": False},
                "seccomp": {"notify": True},
                "loopback": {"pidfd_getfd": True, "ptrace_scope": 1},
            }
        ),
    )
    monkeypatch.setattr(hmz.coganchor.fence, "chosen", _chosen)

    assert main(["fence", "check"]) == 0
    out = capsys.readouterr().out
    assert "network cut unavailable (needs ABI 4)" in out
    assert "socket scoping unavailable (needs ABI 6)" in out


class _Fence:
    """What `Fence.explain` is asked, without a policy or a machine."""

    def explain(self, path: str) -> tuple[str, str]:
        return "read", "read /etc"


def _no_agent(name: str) -> None:
    return None


def _declaration(*names: str) -> SimpleNamespace:
    return SimpleNamespace(
        agents=[
            SimpleNamespace(name=name, auto=False, harness=None, permission=None)
            for name in names
        ],
        agent=_no_agent,
    )


def _worker(parser: Any, name: str) -> SimpleNamespace:
    return _declaration("worker")


def _two(parser: Any, name: str) -> SimpleNamespace:
    return _declaration("first", "second")


def _a_fence(role: Any, spec: Any) -> _Fence:
    return _Fence()


def test_explain_says_what_a_path_is_under_the_fence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.cli.fence, "_resolved", _worker)
    monkeypatch.setattr(hmz.cli.fence, "_fence", _a_fence)

    assert main(["fence", "explain", "/etc/hosts", "-f", "chat"]) == 0
    assert "/etc/hosts: read (read /etc)" in capsys.readouterr().out


def test_explain_json_is_one_object(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.cli.fence, "_resolved", _worker)
    monkeypatch.setattr(hmz.cli.fence, "_fence", _a_fence)

    assert main(["fence", "explain", "/etc/hosts", "-f", "chat", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["path"] == "/etc/hosts"
    assert said["level"] == "read"
    assert said["why"] == "read /etc"


def test_explain_without_a_flow_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["fence", "explain", "/etc/hosts"])
    assert raised.value.code == 2


def test_a_flow_with_several_roles_asks_for_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.cli.fence, "_resolved", _two)
    monkeypatch.setattr(hmz.cli.fence, "_fence", _a_fence)

    with pytest.raises(SystemExit) as raised:
        main(["fence", "explain", "/etc/hosts", "-f", "chat"])
    assert raised.value.code == 2
    assert "first, second" in capsys.readouterr().err
