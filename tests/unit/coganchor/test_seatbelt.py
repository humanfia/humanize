"""Seatbelt: the profile a fence comes to on a Mac, and the command it is applied with.

Read off the profile's text and the command line, with nothing run: what a profile grants, and
what `hmz internal fence` spawns on a Mac. The profile applied by the kernel is
`tests/system/coganchor/test_fence.py`, which runs there on a Mac.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from typing import TYPE_CHECKING

from hmz.coganchor.darwin import seatbelt
from hmz.coganchor.fence import ALL, READ, Fence

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    import pytest


def test_only_what_is_granted_is_read_written_or_run() -> None:
    profile, params = seatbelt.Profile(read=("/usr",), write=("/work",)).rules()

    assert "(deny file-read* file-write* process-exec)" in profile
    assert "(allow file-read-metadata)" in profile
    assert '(allow file-read* process-exec (subpath (param "R0")))' in profile
    assert (
        '(allow file-read* file-write* process-exec (subpath (param "W0")))' in profile
    )
    assert params["R0"] == "/usr"
    assert params["W0"] == "/work"


def test_a_path_is_granted_as_given_and_as_it_resolves() -> None:
    _, params = seatbelt.Profile(write=("/tmp/scratch",)).rules()

    # A link is followed where Seatbelt matches it: `/tmp` is `/private/tmp` on a Mac.
    assert set(params.values()) == {
        "/tmp/scratch",
        os.path.realpath("/tmp/scratch"),
    }


def test_a_path_that_would_end_a_string_is_only_a_parameter() -> None:
    profile, params = seatbelt.Profile(read=('/odd/"quoted\\path',)).rules()

    assert "quoted" not in profile
    assert params["R0"] == '/odd/"quoted\\path'


def test_the_network_is_left_as_it_is_unless_a_port_is_named() -> None:
    profile, _ = seatbelt.Profile(read=("/usr",)).rules()

    assert "network" not in profile


def test_a_cut_network_connects_only_to_the_proxy_on_loopback() -> None:
    profile, _ = seatbelt.Profile(read=("/usr",), port=41234).rules()

    assert "(deny network*)" in profile
    assert '(allow network-outbound (remote tcp "localhost:41234"))' in profile
    # The resolver is a Unix socket, shut so that no name is sent out one word at a time.
    assert (
        '(remote unix-socket (path-literal "/private/var/run/mDNSResponder"))'
        in profile
    )


def test_the_command_runs_the_program_after_its_profile() -> None:
    command = seatbelt.Profile(read=("/usr",)).command(["-starts-like-a-flag", "x"])

    assert command[0] == seatbelt.SANDBOX_EXEC
    assert "-DR0=/usr" in command
    assert command[command.index("-p") + 1].startswith("(version 1)")
    assert command[command.index("--") + 1 :] == ["-starts-like-a-flag", "x"]


def test_there_is_no_seatbelt_off_a_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seatbelt.sys, "platform", "linux")
    assert seatbelt.available.__wrapped__() is False


def test_on_a_mac_the_wrapper_runs_the_program_under_sandbox_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.coganchor.fence import wrap

    spawned: list[tuple[str, list[str], dict[str, str]]] = []

    def spawn(path: str, argv: Sequence[str], env: Mapping[str, str]) -> int:
        spawned.append((path, list(argv), dict(env)))
        return 4242

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(seatbelt, "available", lambda: True)
    monkeypatch.setattr(os, "posix_spawn", spawn)
    monkeypatch.setattr(wrap, "_waited", _exited_3)
    monkeypatch.setattr(wrap, "_swept", _swept)
    scratch = tmp_path / "scratch"
    fence = dataclasses.replace(
        Fence.of(
            local=ALL,
            user=READ,
            system=READ,
            online=True,
            workdir=tmp_path / "work",
            home=tmp_path,
        ),
        tmp=str(scratch),
    )

    assert wrap.run(fence, ["claude", "--print"]) == 3

    ((path, argv, env),) = spawned
    assert path == seatbelt.SANDBOX_EXEC
    assert argv[argv.index("--") + 1 :] == ["claude", "--print"]
    # The scratch is written as the fence's own, and is the temporary directory.
    assert any(one.startswith("-DW") and one.endswith(f"={scratch}") for one in argv)
    assert env["TMPDIR"] == str(scratch)
    # The network is not cut, so no proxy is put in its way.
    assert "(deny network*)" not in argv[argv.index("-p") + 1]


def _exited_3(pid: int) -> int:
    return 3 << 8 if pid == 4242 else 0


def _swept(pid: int) -> None:
    del pid
