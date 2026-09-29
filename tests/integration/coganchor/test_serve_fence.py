"""The target half fencing the commands a fenced agent has run on it, over a loopback link.

Both halves in this process, joined by a `socketpair` (`link`), with `hmz internal fence` the
stand-in `tests/fencing.py` puts in its place for this tier: what is read back is the policy
the target would have walled each command in with, drawn around the target's own paths. The
wall itself going up on a target is `tests/system/coganchor/test_fence_abroad.py`.
"""

from __future__ import annotations

import errno
import json
import threading
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.fence import ALL, NONE, READ, Fence
from hmz.coganchor.fence.abroad import told
from hmz.coganchor.proto import hello_fences
from tests import fencing
from tests.coganchor.fixtures import VIRTUAL_EXPORT

if TYPE_CHECKING:
    from pathlib import Path

    from tests.coganchor.fixtures import Link


def _ran(
    link: Link, argv: list[str], fence: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, OSError | None, bytes]:
    """Runs one command on the target, and waits for what it said and how it ended."""
    ended = threading.Event()
    said: list[bytes] = []
    held: dict[str, Any] = {}

    def over(result: dict[str, Any] | None, error: OSError | None) -> None:
        held.update(result=result, error=error)
        ended.set()

    link.client.start_exec(
        argv,
        cwd=VIRTUAL_EXPORT,
        env={},
        on_output=lambda _stream, data: said.append(data),
        on_exit=over,
        fence=fence,
    ).close_stdin()
    assert ended.wait(timeout=30)
    return held["result"], held["error"], b"".join(said)


def _levels(local: str, user: str, system: str, *, online: bool) -> dict[str, Any]:
    fence = Fence.of(
        local=local, user=user, system=system, online=online, workdir="/w", home="/h"
    )
    return told(fence, home="/h", native=False)


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where the stand-in writes each policy down, and a home of the target's own."""
    at = tmp_path / "policies.jsonl"
    monkeypatch.setenv(fencing.LOG, str(at))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return at


@pytest.mark.timeout(60)
def test_the_target_says_at_the_handshake_that_it_can_fence(link: Link) -> None:
    assert hello_fences(link.client.info, net=True)


@pytest.mark.timeout(60)
def test_a_fenced_command_is_walled_in_around_the_targets_own_paths(
    link: Link, log: Path, tmp_path: Path
) -> None:
    result, error, said = _ran(
        link, ["sh", "-c", "echo ran"], _levels(ALL, READ, READ, online=False)
    )

    assert error is None, error
    assert result == {"exit_code": 0}
    assert said.strip() == b"ran"
    (policy,) = fencing.policies(log)
    fence = Fence.loads(json.dumps(policy))
    # The workdir is the directory the target exports, not the path the client names.
    assert fence.allows(link.target / "a.txt", write=True)
    assert not fence.allows(f"{VIRTUAL_EXPORT}/a.txt", write=True)
    # The home is the target's own, and READ there.
    assert fence.allows(tmp_path / "home" / ".bashrc")
    assert not fence.allows(tmp_path / "home" / ".bashrc", write=True)
    assert not fence.allows("/h/.bashrc", write=True)
    # A command run for a supervised agent reaches no host at all.
    assert not fence.online
    assert fence.hosts == ()
    assert fence.scopes == (ALL, READ, READ)


@pytest.mark.timeout(60)
def test_a_native_cli_keeps_its_state_under_the_targets_home(
    link: Link, log: Path, tmp_path: Path
) -> None:
    fence = Fence.of(
        local=ALL,
        user=READ,
        system=NONE,
        online=False,
        workdir="/w",
        home="/h",
        hosts=["api.example.com"],
        write=["/h/.cli", "/elsewhere/state"],
    )
    said = told(fence, home="/h", native=True)

    # Behind the `env` a native CLI is started with, which is not the program it runs.
    result, error, _ = _ran(link, ["env", "-u", "X", "A=b", "sh", "-c", "true"], said)

    assert error is None, error
    assert result == {"exit_code": 0}
    (policy,) = fencing.policies(log)
    held = Fence.loads(json.dumps(policy))
    assert held.allows(tmp_path / "home" / ".cli" / "state.json", write=True)
    # And made, a grant of a path that is not there being none.
    assert (tmp_path / "home" / ".cli").is_dir()
    assert not held.allows("/elsewhere/state")
    assert held.hosts == ("api.example.com",)
    # Its own program is let be read, wherever it was installed.
    assert any(one.endswith("/sh") for one in held.read)


@pytest.mark.timeout(60)
def test_an_unfenced_command_runs_as_it_always_did(link: Link, log: Path) -> None:
    result, error, _ = _ran(link, ["sh", "-c", "true"], None)

    assert error is None
    assert result == {"exit_code": 0}
    assert fencing.policies(log) == []


@pytest.mark.timeout(60)
def test_a_target_that_cannot_fence_refuses_the_command(
    link: Link, log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = link.target / "ran"
    def only_the_filesystem(*, net: bool) -> bool:
        return not net

    monkeypatch.setattr("hmz.coganchor.fence.enforceable", only_the_filesystem)

    _, error, _ = _ran(
        link, ["sh", "-c", f"touch {ran}"], _levels(ALL, READ, READ, online=False)
    )

    assert isinstance(error, OSError)
    assert error.errno == errno.EPERM
    assert "Landlock ABI 4" in str(error)
    assert not ran.exists()
    assert fencing.policies(log) == []


@pytest.mark.timeout(60)
def test_levels_that_are_not_a_fences_are_refused(link: Link, log: Path) -> None:
    _, error, _ = _ran(
        link, ["true"], {"local": "most", "user": READ, "system": READ, "online": True}
    )

    assert isinstance(error, OSError)
    assert fencing.policies(log) == []
