"""What a program inside a fence is run with, and what is refused before anything runs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from hmz.coganchor import fence as fencing
from hmz.coganchor.darwin.seatbelt import SANDBOX_EXEC
from hmz.coganchor.fence import Fence, wrap
from hmz.coganchor.fence.wrap import CACHES, PROXIES, environ, run
from hmz.coganchor.providers import redirect

TMP = "/tmp/hmz-fence-scratch"


def test_environ_points_every_temporary_directory_at_the_scratch() -> None:
    held = environ(Fence(write=("/",)), {"TMPDIR": "/elsewhere"}, tmp=TMP, port=None)

    assert held["TMPDIR"] == held["TMP"] == held["TEMP"] == TMP


def test_environ_leaves_the_caches_where_the_fence_lets_them_be_written() -> None:
    given = {name: f"/caches/{name}" for name in CACHES}

    held = environ(Fence(write=("/caches",)), given, tmp=TMP, port=None)

    assert {name: held[name] for name in CACHES} == given


def test_environ_moves_the_caches_the_fence_would_not_let_be_written() -> None:
    given = {"XDG_CACHE_HOME": "/caches/xdg", "UV_CACHE_DIR": "relative"}

    held = environ(Fence(write=("/elsewhere",)), given, tmp=TMP, port=None)

    assert {name: held[name] for name in CACHES} == {
        name: str(Path(TMP, "cache", name.lower())) for name in CACHES
    }


def test_environ_without_a_proxy_leaves_the_network_as_it_was() -> None:
    given = {"NO_PROXY": "internal", "HTTPS_PROXY": "http://corp:3128"}

    held = environ(Fence(write=("/",)), given, tmp=TMP, port=None)

    assert held["NO_PROXY"] == "internal"
    assert held["HTTPS_PROXY"] == "http://corp:3128"
    assert "NODE_USE_ENV_PROXY" not in held


def test_environ_with_a_proxy_sends_every_client_through_it() -> None:
    given = {"NO_PROXY": "internal", "no_proxy": "internal", "KEEP": "me"}

    held = environ(Fence(write=("/",)), given, tmp=TMP, port=4321)

    assert {name: held[name] for name in PROXIES} == dict.fromkeys(
        PROXIES, "http://127.0.0.1:4321"
    )
    assert held["NO_PROXY"] == held["no_proxy"] == ""
    assert held["NODE_USE_ENV_PROXY"] == "1"
    assert held["KEEP"] == "me"
    assert given == {"NO_PROXY": "internal", "no_proxy": "internal", "KEEP": "me"}


def test_run_refuses_no_program() -> None:
    with pytest.raises(ValueError, match="no program"):
        run(Fence(), [])


@pytest.mark.parametrize("online", [True, False])
def test_run_refuses_a_host_that_cannot_fence(
    monkeypatch: pytest.MonkeyPatch, online: bool
) -> None:
    asked: list[bool] = []

    def enforceable(*, net: bool) -> bool:
        asked.append(net)
        return False

    monkeypatch.setattr(fencing, "enforceable", enforceable)

    with pytest.raises(RuntimeError, match="cannot fence"):
        run(Fence(online=online), ["true"])
    assert asked == [not online]


@pytest.mark.parametrize(
    "cache", ["available", None, OSError("no cache"), ValueError("unknown")]
)
def test_a_mac_run_keeps_only_its_security_cache_writable_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cache: str | Exception | None
) -> None:
    cache_dir = str(tmp_path.resolve() / "system-cache")
    scratch = str(tmp_path.resolve() / "scratch")
    commands: list[list[str]] = []
    asked: list[int] = []

    def confstr(name: int) -> str | None:
        asked.append(name)
        if isinstance(cache, Exception):
            raise cache
        return cache_dir if cache else None

    def spawn(path: str, argv: list[str], env: dict[str, str]) -> int:
        assert path == SANDBOX_EXEC
        assert env["TMPDIR"] == scratch
        commands.append(argv)
        return 123

    def enforceable(*, net: bool) -> bool:
        assert not net
        return True

    def waited(pid: int, options: int) -> tuple[int, int]:
        assert (pid, options) == (-1, 0)
        return 123, 7 << 8

    def swept(pid: int) -> None:
        assert pid == 123

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(fencing, "enforceable", enforceable)
    monkeypatch.setattr(os, "confstr", confstr, raising=False)
    monkeypatch.setattr(os, "posix_spawn", spawn, raising=False)
    monkeypatch.setattr(os, "waitpid", waited, raising=False)
    monkeypatch.setattr(redirect, "swept", swept)

    assert run(Fence(read=("/r",), write=("/w",), tmp=scratch), ["prog", "arg"]) == 7
    assert asked == [65538]
    (command,) = commands
    assert command[-2:] == ["prog", "arg"]
    writes = {one.partition("=")[2] for one in command if one.startswith("-DW")}
    assert writes == {"/w", scratch} | (
        {str(Path(cache_dir, "mds"))} if cache == "available" else set()
    )


def test_main_runs_the_policy_it_was_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fence = Fence(read=("/r",), online=False)
    ran: list[tuple[Fence, list[str]]] = []

    def running(given: Fence, argv: list[str]) -> int:
        ran.append((given, list(argv)))
        return 7

    monkeypatch.setattr(wrap, "run", running)
    policy = tmp_path / "policy.json"
    policy.write_text(fence.dumps())

    assert wrap.main(fence.dumps(), ["prog", "arg"]) == 7
    assert wrap.main(f"@{policy}", ["prog"]) == 7
    assert ran == [(fence, ["prog", "arg"]), (fence, ["prog"])]


@pytest.mark.parametrize("error", [OSError("no"), RuntimeError("no"), ValueError("no")])
def test_main_says_why_and_never_runs_unfenced(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def running(given: Fence, argv: list[str]) -> int:
        raise error

    monkeypatch.setattr(wrap, "run", running)

    assert wrap.main("{}", ["prog"]) == 126
    assert "hmz internal fence: no" in capsys.readouterr().err


@pytest.mark.parametrize("policy", ["not json", '{"bogus": 1}', "@/no/such/policy"])
def test_main_refuses_a_policy_it_cannot_read(
    capsys: pytest.CaptureFixture[str], policy: str
) -> None:
    assert wrap.main(policy, [sys.executable]) == 126
    assert capsys.readouterr().err.startswith("hmz internal fence: ")
