"""The fence: what a permission's scopes come to, and what a turn held to one is spawned as.

Read off objects in this process, with nothing spawned and no ruleset applied: which paths a
fence grants and at what, what it is written down as for `hmz internal fence`, what the program
inside it is run with, and where an agent puts the wrapper on its command line -- or refuses to
be built, where nothing here could hold it. The wall itself going up is
`tests/system/coganchor/test_fence.py`.
"""

from __future__ import annotations

import dataclasses
import itertools
import os
import sys
from pathlib import Path

import pytest

from hmz.coganchor.agents import (
    KEEPING,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Unfenced,
)
from hmz.coganchor.fence import (
    ALL,
    DEVICES,
    LEVELS,
    NONE,
    READ,
    SYSTEM,
    Fence,
    wrapper,
)
from hmz.coganchor.fence.wrap import CACHES, PROXIES, environ
from hmz.coganchor.linux import landlock

HOME = "/home/someone"
WORK = "/home/someone/work"

#: Every way three scopes can nest, `local >= user >= system`.
NESTED = [
    (local, user, system)
    for local, user, system in itertools.product(LEVELS, repeat=3)
    if LEVELS.index(local) >= LEVELS.index(user) >= LEVELS.index(system)
]


def _of(local: str, user: str, system: str, *, online: bool = True) -> Fence:
    return Fence.of(
        local=local, user=user, system=system, online=online, workdir=WORK, home=HOME
    )


def _level(fence: Fence, path: str) -> str:
    if fence.allows(path, write=True):
        return ALL
    return READ if fence.allows(path) else NONE


@pytest.mark.parametrize(("local", "user", "system"), NESTED, ids=str)
def test_each_scope_is_granted_at_its_level(local: str, user: str, system: str) -> None:
    fence = _of(local, user, system)

    assert _level(fence, f"{WORK}/src/a.py") == local
    assert _level(fence, f"{HOME}/.bashrc") == user
    assert _level(fence, "/etc/machine-id") == system
    # The network is on, so it is open exactly where `/` may be written.
    assert fence.open is (system == ALL)


@pytest.mark.parametrize(("local", "user", "system"), NESTED, ids=str)
def test_the_minimum_is_granted_whatever_the_scopes(
    local: str, user: str, system: str
) -> None:
    fence = _of(local, user, system, online=False)

    for path in (
        "/usr/lib/libc.so",
        "/etc/ssl/certs/ca.pem",
        "/etc/resolv.conf",
        "/proc",
    ):
        assert fence.allows(path), path
    for path in DEVICES:
        assert fence.allows(path, write=True), path
    # The Python humanize runs on, whose supervisors run inside the fence.
    assert fence.allows(sys.executable)
    assert fence.allows(Path(landlock.__file__))


def test_scopes_that_do_not_nest_are_refused() -> None:
    with pytest.raises(ValueError, match="nest"):
        _of(READ, ALL, READ)
    with pytest.raises(ValueError, match="scope"):
        _of("some", READ, READ)


def test_a_session_working_outside_its_workdir_is_granted_there_as_the_workdir_is() -> (
    None
):
    fence = Fence.of(
        local=ALL,
        user=READ,
        system=NONE,
        online=True,
        workdir=WORK,
        home=HOME,
        cwd="/srv/elsewhere",
    )
    assert fence.allows("/srv/elsewhere/x", write=True)


def test_a_path_both_read_and_written_is_written() -> None:
    fence = Fence(read=("/a", "/b"), write=("/a/",))
    assert fence.read == ("/b",)
    assert fence.write == ("/a",)
    assert fence.allows("/a/x", write=True)


def test_a_fence_that_grants_everything_is_open() -> None:
    everything = _of(ALL, ALL, ALL)
    assert everything.open
    assert everything.everything
    assert not dataclasses.replace(everything, online=False).open
    narrow = _of(ALL, READ, READ, online=False)
    assert not narrow.open
    assert narrow.without(network=True).online
    assert not narrow.without(network=True).open
    assert narrow.without(filesystem=True, network=True).open
    assert narrow.without().read == narrow.read


def test_granting_only_widens() -> None:
    fence = _of(ALL, READ, NONE, online=False)
    wider = fence.granting(read=["/opt/tool"], write=["/var/cache/x"], hosts=["a.b"])
    assert set(fence.read) <= set(wider.read) | set(wider.write)
    assert set(fence.write) <= set(wider.write)
    assert wider.allows("/opt/tool/bin/x")
    assert wider.allows("/var/cache/x/y", write=True)
    assert wider.hosts == (*fence.hosts, "a.b")


def test_a_fence_survives_being_written_down() -> None:
    fence = Fence.of(
        local=ALL,
        user=READ,
        system=NONE,
        online=False,
        workdir=WORK,
        home=HOME,
        hosts=["api.anthropic.com", "*.example.com", "gw.example:8443"],
    )
    fence = dataclasses.replace(fence, tmp="/tmp/scratch")
    assert Fence.loads(fence.dumps()) == fence


@pytest.mark.parametrize(
    "said",
    [
        "[]",
        '{"read": "/"}',
        '{"read": [1]}',
        '{"online": "no"}',
        '{"tmp": 3}',
        '{"elsewhere": []}',
        "not json",
    ],
)
def test_what_is_not_a_fence_is_refused(said: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 -- json's own error is one too
        Fence.loads(said)


def test_the_wrapper_is_humanize_itself_with_the_policy_on_the_line() -> None:
    fence = _of(ALL, READ, READ)
    said = wrapper(fence)
    assert said[:5] == [sys.executable, "-m", "hmz", "internal", "fence"]
    assert said[-1] == "--"
    assert Fence.loads(said[5].removeprefix("--policy=")) == fence


def test_inside_a_fence_scratch_and_caches_go_to_its_own_directory() -> None:
    fence = _of(ALL, READ, READ)
    held = environ(fence, {"PATH": "/usr/bin", "NO_PROXY": "x"}, tmp="/t", port=None)
    assert (held["TMPDIR"], held["TMP"], held["TEMP"]) == ("/t", "/t", "/t")
    for name in CACHES:
        assert held[name].startswith("/t/"), name
    assert (
        held["NO_PROXY"] == "x"
    )  # the network is not cut, so nothing about it changes
    assert not any(name in held for name in PROXIES)


def test_a_cache_already_somewhere_the_fence_lets_be_written_is_left_there() -> None:
    fence = _of(ALL, ALL, READ)
    held = environ(fence, {"UV_CACHE_DIR": f"{WORK}/.uv"}, tmp="/t", port=None)
    assert held["UV_CACHE_DIR"] == f"{WORK}/.uv"
    elsewhere = environ(
        _of(ALL, READ, READ), {"UV_CACHE_DIR": "/var/uv"}, tmp="/t", port=None
    )
    assert elsewhere["UV_CACHE_DIR"].startswith("/t/")


def test_a_cut_network_has_the_proxy_as_every_clients_and_exempts_nothing() -> None:
    fence = _of(ALL, READ, READ, online=False)
    held = environ(
        fence, {"NO_PROXY": "internal", "no_proxy": "x"}, tmp="/t", port=4242
    )
    for name in PROXIES:
        assert held[name] == "http://127.0.0.1:4242"
    assert (held["NO_PROXY"], held["no_proxy"], held["NODE_USE_ENV_PROXY"]) == (
        "",
        "",
        "1",
    )


def test_the_minimum_names_what_a_resolver_and_a_tls_stack_read() -> None:
    for path in ("/etc/ssl", "/etc/resolv.conf", "/etc/hosts", "/etc/passwd", "/usr"):
        assert path in SYSTEM
    assert "/opt" not in SYSTEM


# ------------------------------------------------------------------------ the agent's side


def _able(*, net: bool) -> bool:
    del net
    return True


def _holds_everything(self: object, fence: Fence) -> Fence:
    del self
    return fence.without(filesystem=True, network=True)


def _cuts_its_network(self: object, fence: Fence) -> Fence:
    del self
    return fence.without(network=True)


@pytest.fixture
def enforceable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Takes this machine to be one that can fence a process, whatever machine it is.

    With a home of the test's own, since a fenced turn makes the directories its CLI keeps
    its state in before spawning it.
    """
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def _agent(fence: Fence | None, **config: object) -> ClaudeCodeAgent:
    return ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", fence=fence, **config)  # pyright: ignore[reportArgumentType]
    )


def _fence(tmp_path: Path, *, online: bool = False) -> Fence:
    return dataclasses.replace(
        Fence.of(
            local=ALL,
            user=READ,
            system=READ,
            online=online,
            workdir=tmp_path / "work",
            home=tmp_path,
        ),
        tmp=str(tmp_path / "scratch"),
    )


def _policy(argv: list[str]) -> Fence:
    return Fence.loads(argv[5].removeprefix("--policy="))


@pytest.mark.usefixtures("enforceable")
def test_a_fenced_turn_is_spawned_inside_the_wrapper(tmp_path: Path) -> None:
    agent = _agent(_fence(tmp_path))

    argv = agent.spawned(["claude", "--print"])

    assert argv[:5] == [sys.executable, "-m", "hmz", "internal", "fence"]
    rest = argv[argv.index("--") + 1 :]
    assert rest[1:] == ["--print"]
    policy = _policy(argv)
    assert not policy.online
    assert "api.anthropic.com" in policy.hosts
    assert policy.tmp == str(tmp_path / "scratch")
    # What the agent needs besides its scopes: its state, and its sessions' directory.
    assert policy.allows(Path("~/.claude/settings.json").expanduser(), write=True)
    assert policy.allows(agent.keeps / "claude", write=True)


@pytest.mark.usefixtures("enforceable")
def test_the_fence_is_outside_the_supervisor_that_keeps_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(KEEPING, raising=False)
    monkeypatch.setattr("hmz.coganchor.providers.redirect.supervises", lambda: True)
    agent = _agent(_fence(tmp_path))

    argv = agent.spawned(["claude", "--print"])

    assert argv[:5] == [sys.executable, "-m", "hmz", "internal", "fence"]
    inner = argv[argv.index("--") + 1 :]
    assert inner[:5] == [sys.executable, "-m", "hmz", "internal", "cred"]
    assert _policy(argv).allows(agent.keeps / "claude", write=True)
    assert not _policy(argv).allows(agent.keeps / "codex", write=True)


@pytest.mark.usefixtures("enforceable")
def test_a_fence_that_fences_nothing_puts_nothing_around_the_cli(
    tmp_path: Path,
) -> None:
    fence = Fence.of(
        local=ALL, user=ALL, system=ALL, online=True, workdir=tmp_path, home=tmp_path
    )
    assert _agent(fence).spawned(["claude"])[:1] != [sys.executable]
    assert _agent(None).spawned(["claude"])[:1] != [sys.executable]


def test_by_default_a_cli_enforces_none_of_its_fence_itself(tmp_path: Path) -> None:
    fence = _fence(tmp_path)
    assert _agent(None).natively(fence) is fence


@pytest.mark.usefixtures("enforceable")
def test_a_cli_that_enforces_its_whole_fence_is_spawned_bare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ClaudeCodeAgent,
        "natively",
        _holds_everything,
    )
    assert _agent(_fence(tmp_path)).spawned(["claude"])[:1] != [sys.executable]


@pytest.mark.usefixtures("enforceable")
def test_a_cli_that_cuts_its_own_network_leaves_the_paths_to_the_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ClaudeCodeAgent, "natively", _cuts_its_network)
    argv = _agent(_fence(tmp_path)).spawned(["claude"])
    assert argv[:5] == [sys.executable, "-m", "hmz", "internal", "fence"]
    assert _policy(argv).online


def test_without_landlock_a_fenced_agent_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(landlock, "available", lambda net=False: False)
    with pytest.raises(Unfenced, match="Landlock"):
        _agent(_fence(tmp_path, online=True))


def test_a_kernel_that_cannot_cut_the_network_refuses_only_a_cut_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: landlock.NET_ABI - 1)
    _agent(_fence(tmp_path, online=True))
    with pytest.raises(Unfenced, match="network"):
        _agent(_fence(tmp_path, online=False))


def test_without_landlock_a_cli_that_enforces_everything_itself_is_still_served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(landlock, "available", lambda net=False: False)
    monkeypatch.setattr(
        ClaudeCodeAgent,
        "natively",
        _holds_everything,
    )
    _agent(_fence(tmp_path))


@pytest.mark.usefixtures("enforceable")
def test_a_fence_is_refused_where_the_work_lands_on_another_machine(
    tmp_path: Path,
) -> None:
    from hmz.coganchor.agents.config import anchored

    with pytest.raises(Unfenced, match="another machine"):
        _agent(_fence(tmp_path), machine=anchored("ssh://somewhere"))
    everything = Fence.of(
        local=ALL, user=ALL, system=ALL, online=True, workdir=tmp_path, home=tmp_path
    )
    _agent(everything, machine=anchored("ssh://somewhere"))


def test_a_config_refused_its_fence_leaves_the_agent_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = _agent(None)
    was = agent.config
    monkeypatch.setattr(landlock, "available", lambda net=False: False)
    with pytest.raises(Unfenced):
        agent.reconfigure(dataclasses.replace(was, fence=_fence(tmp_path)))
    assert agent.config is was


def test_the_program_the_cli_is_is_read_with_its_install_tree(tmp_path: Path) -> None:
    from hmz.coganchor.agents.base import _programs

    package = tmp_path / "lib" / "node_modules" / "@scope" / "cli"
    package.mkdir(parents=True)
    script = package / "cli.js"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    held = _programs(str(script))
    assert str(package) in held
    assert str(script) in held
    assert os.sep not in held
    assert str(Path.home()) not in held
