"""A fence on another machine: what crosses to the target, what the target draws from it.

Read off objects in this process: the levels a fence is said to a target in, the fence a
target draws again from them around its own workdir and home, the settings an anchor is given
to hold an agent to one, and where an anchored agent is refused one. The target half doing
it over a link is `tests/integration/coganchor/test_serve_fence.py`, and a real target
walling a real command in is `tests/system/coganchor/test_fence_abroad.py`.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig, Unfenced
from hmz.coganchor.agents.config import anchored
from hmz.coganchor.fence import ALL, NONE, READ, Fence, wrapper
from hmz.coganchor.fence.abroad import drawn, installed, told
from hmz.coganchor.machines import AnchoredConfig
from hmz.coganchor.proto import hello_fences

if TYPE_CHECKING:
    from pathlib import Path

HOME = "/home/here"


def _of(local: str, user: str, system: str, **more: Any) -> Fence:
    return Fence.of(
        local=local,
        user=user,
        system=system,
        online=more.pop("online", False),
        workdir="/home/here/work",
        home=HOME,
        **more,
    )


def _level(fence: Fence, path: str | Path) -> str:
    if fence.allows(path, write=True):
        return ALL
    return READ if fence.allows(path) else NONE


# ------------------------------------------------------------------------ the fence's levels


def test_a_fence_remembers_the_levels_it_was_drawn_from() -> None:
    fence = _of(ALL, READ, NONE)
    assert fence.scopes == (ALL, READ, NONE)
    assert fence.granting(write=["/x"]).scopes == fence.scopes
    assert Fence.loads(fence.dumps()) == fence
    # Taking the filesystem off is granting every level of it.
    assert fence.without(filesystem=True).scopes == (ALL, ALL, ALL)
    assert Fence(read=("/a",)).scopes == ()


def test_levels_that_are_not_three_of_a_fences_are_refused() -> None:
    with pytest.raises(ValueError, match="scopes"):
        Fence(scopes=(ALL, READ))
    with pytest.raises(ValueError, match="scopes"):
        Fence(scopes=(ALL, READ, "most"))


# ------------------------------------------------------------------ what crosses, and back


def test_a_supervised_agents_commands_are_told_only_the_levels() -> None:
    fence = _of(ALL, READ, READ, hosts=["api.example.com"], write=["/home/here/.cli"])
    assert told(fence, home=HOME, native=False) == {
        "local": ALL,
        "user": READ,
        "system": READ,
        "online": False,
    }


def test_a_native_cli_is_told_its_hosts_and_the_state_it_keeps_at_home() -> None:
    fence = Fence(
        scopes=(ALL, READ, READ),
        online=False,
        hosts=("api.example.com",),
        write=("/home/here/.cli", "/home/here/.config/cli", "/tmp/scratch"),
    )
    said = told(fence, home=HOME, native=True)
    assert said["hosts"] == ["api.example.com"]
    # Relative to the home, which is another directory there; nothing else of this machine's.
    assert said["write"] == ["~/.cli", "~/.config/cli"]
    assert said["programs"] is True


def test_a_fence_drawn_path_by_path_cannot_cross() -> None:
    with pytest.raises(ValueError, match="path by path"):
        told(Fence(read=("/a",)), home=HOME, native=False)


@pytest.mark.parametrize(
    ("local", "user", "system"),
    [(ALL, READ, READ), (ALL, READ, NONE), (ALL, NONE, NONE), (READ, READ, NONE)],
    ids=str,
)
def test_the_target_draws_each_level_around_its_own_paths(
    tmp_path: Path, local: str, user: str, system: str
) -> None:
    home, work = tmp_path / "home", tmp_path / "srv" / "work"
    home.mkdir()
    work.mkdir(parents=True)
    said = told(_of(local, user, system), home=HOME, native=False)

    fence = drawn(said, workdirs=[str(work)], home=str(home))

    assert _level(fence, work / "a.py") == local
    assert _level(fence, home / ".bashrc") == user
    assert _level(fence, "/etc/machine-id") == system
    # What this machine named is nothing there.
    assert _level(fence, "/home/here/work/a.py") == system
    # And the minimum is the target's own.
    assert fence.allows("/usr/bin/sh")
    assert fence.allows(sys.executable)
    assert fence.allows("/dev/null", write=True)
    assert not fence.online


def test_a_target_with_no_home_of_its_own_grants_nothing_past_the_workdir(
    tmp_path: Path,
) -> None:
    said = told(
        Fence(scopes=(ALL, ALL, READ), write=("/home/here/.cli",)),
        home=HOME,
        native=True,
    )
    fence = drawn(said, workdirs=[str(tmp_path)], home="/")
    # A home of `/` would otherwise be the whole machine to write.
    assert not fence.allows("/etc/passwd", write=True)
    assert fence.allows(tmp_path / "a", write=True)
    assert not fence.allows("/.cli", write=True)


def test_a_native_clis_state_lands_under_the_targets_home(tmp_path: Path) -> None:
    said = told(
        Fence(scopes=(ALL, READ, NONE), write=("/home/here/.cli",)),
        home=HOME,
        native=True,
    )
    said["write"].append("/tmp/session-1")
    fence = drawn(said, workdirs=[str(tmp_path / "w")], home=str(tmp_path))
    assert fence.allows(tmp_path / ".cli" / "x.json", write=True)
    assert fence.allows("/tmp/session-1/key", write=True)
    assert not fence.allows(tmp_path / ".other", write=True)


@pytest.mark.parametrize(
    "said",
    [
        {"local": "most", "user": READ, "system": READ},
        {"local": ALL, "user": READ, "system": READ, "online": "no"},
        {"local": ALL, "user": READ, "system": READ, "write": ["relative"]},
        {"local": ALL, "user": READ, "system": READ, "write": ["~/../escape"]},
        {"local": ALL, "user": READ, "system": READ, "hosts": "one"},
    ],
    ids=["level", "online", "relative", "climbing", "hosts"],
)
def test_what_is_not_a_fences_levels_is_refused(
    tmp_path: Path, said: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="fence"):
        drawn(said, workdirs=[str(tmp_path)], home=str(tmp_path))


def test_a_program_is_read_with_the_tree_it_was_installed_as(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "lib").mkdir(parents=True)
    (prefix / "bin").mkdir()
    node = prefix / "bin" / "node"
    node.write_text("")
    node.chmod(0o755)
    cli = prefix / "bin" / "cli"
    cli.write_text("#!/usr/bin/env node\n")
    cli.chmod(0o755)

    held = installed("cli", path=str(prefix / "bin"))

    assert str(cli) in held
    assert str(prefix) in held
    assert str(node) in held
    assert "/" not in held
    assert installed("nothing-called-this", path=str(tmp_path)) == []


# ----------------------------------------------------------------------------- the handshake


def test_a_target_says_what_it_can_fence_at_the_handshake() -> None:
    assert hello_fences({"fence": {"fs": True, "net": True}}, net=True)
    assert hello_fences({"fence": {"fs": True, "net": False}}, net=False)
    assert not hello_fences({"fence": {"fs": True, "net": False}}, net=True)
    assert not hello_fences({"fence": {"fs": False, "net": False}}, net=False)
    # A target from before fences says nothing, and cannot.
    assert not hello_fences({"platform": "linux"}, net=False)


def test_the_wrapper_is_run_from_the_archive_a_target_was_bootstrapped_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz import coganchor

    class Archived:
        archive = "/tmp/humanize-abc.pyz"

    monkeypatch.setattr(coganchor, "__loader__", Archived(), raising=False)
    argv = wrapper(_of(ALL, READ, READ))
    assert argv[:4] == [sys.executable, "/tmp/humanize-abc.pyz", "internal", "fence"]


# ------------------------------------------------------------------------------- the anchor


def test_an_anchor_refuses_a_fence_it_could_not_hold() -> None:
    with pytest.raises(ValueError, match="path by path"):
        AnchorConfig(target="ssh://box", fence=Fence(read=("/a",)))
    with pytest.raises(ValueError, match="harness"):
        AnchorConfig(target="ssh://box", harness="same", fence=_of(ALL, READ, READ))
    with pytest.raises(ValueError, match="net remote"):
        AnchorConfig(target="ssh://box", net="remote", fence=_of(ALL, READ, READ))
    # One that fences nothing is no fence to refuse.
    AnchorConfig(
        target="ssh://box",
        harness="same",
        fence=_of(ALL, ALL, ALL, online=True),
    )


# -------------------------------------------------------------------------------- the agent


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """A target that answers the handshake, fencing whatever this says it fences."""
    said: dict[str, Any] = {"platform": "linux", "fence": {"fs": True, "net": True}}

    def answered(anchor: AnchorConfig) -> dict[str, Any]:
        del anchor
        return said

    monkeypatch.setattr("hmz.coganchor.check", answered)
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setattr("hmz.coganchor.agents.base._FENCING", set[tuple[str, bool]]())
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HUMANIZE_SESSIONS", "off")
    return said


def _able(*, net: bool) -> bool:
    del net
    return True


def _unable(*, net: bool) -> bool:
    del net
    return False


def _agent(fence: Fence, anchor: AnchorConfig) -> ClaudeCodeAgent:
    return ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="m",
            effort="high",
            fence=fence,
            machine=AnchoredConfig(anchor=anchor),
        )
    )


def _told(argv: list[str]) -> Fence:
    (said,) = [one for one in argv if one.startswith("--fence=")]
    return Fence.loads(said.removeprefix("--fence="))


@pytest.mark.usefixtures("target")
def test_an_anchored_agent_is_fenced_by_its_anchor_not_around_it(
    tmp_path: Path,
) -> None:
    fence = dataclasses.replace(
        Fence.of(
            local=ALL,
            user=READ,
            system=READ,
            online=False,
            workdir="/srv/work",
            home=tmp_path / "home",
        ),
        tmp=str(tmp_path / "scratch"),
    )
    agent = _agent(fence, AnchorConfig(target="ssh://box", workspace="/srv/work"))

    argv = agent.spawned(["claude", "--print"])

    assert argv[:5] == [sys.executable, "-m", "hmz", "internal", "anchor"]
    assert "fence" not in argv[:6]
    held = _told(argv)
    assert held.scopes == (ALL, READ, READ)
    assert not held.online
    assert "api.anthropic.com" in held.hosts
    # What the CLI itself needs, as on this machine.
    assert held.allows(tmp_path / "home" / ".claude" / "settings.json", write=True)


def test_a_target_that_cannot_fence_refuses_the_turn(
    target: dict[str, Any], tmp_path: Path
) -> None:
    target["fence"] = {"fs": True, "net": False}
    agent = _agent(
        _of(ALL, READ, READ), AnchorConfig(target="ssh://box", workspace="/srv/w")
    )
    with pytest.raises(Unfenced, match="ABI 4"):
        agent.spawned(["claude"])
    target["fence"] = {"fs": True, "net": True}
    agent.spawned(["claude"])
    del tmp_path


@pytest.mark.usefixtures("target")
def test_an_anchored_agent_granted_everything_is_not_fenced() -> None:
    everything = _of(ALL, ALL, ALL, online=True)
    agent = _agent(everything, AnchorConfig(target="ssh://box", workspace="/srv/w"))
    assert not any(one.startswith("--fence=") for one in agent.spawned(["claude"]))


@pytest.mark.usefixtures("target")
def test_an_anchored_agent_is_refused_what_no_anchor_could_hold() -> None:
    with pytest.raises(Unfenced, match="path by path"):
        _agent(Fence(read=("/a",)), AnchorConfig(target="ssh://box"))
    with pytest.raises(Unfenced, match="harness"):
        _agent(_of(ALL, READ, READ), AnchorConfig(target="ssh://box", harness="same"))
    # Everything else is refused only by a target that says it cannot.
    ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="m",
            effort="high",
            fence=_of(ALL, READ, READ),
            machine=anchored("ssh://somewhere"),
        )
    )


def test_an_agent_supervised_here_needs_landlock_here(
    target: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    del target
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _unable)
    with pytest.raises(Unfenced, match="Landlock"):
        _agent(_of(ALL, READ, READ), AnchorConfig(target="ssh://box"))
    # A native CLI runs on the target alone, which is the target's to answer.
    _agent(_of(ALL, READ, READ), AnchorConfig(target="ssh://box", native=True))


@pytest.mark.usefixtures("target")
def test_a_native_cli_is_told_only_its_levels_hosts_and_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fence = Fence.of(
        local=ALL, user=READ, system=READ, online=False, workdir=home / "w", home=home
    )
    agent = _agent(fence, AnchorConfig(target="local", native=True))

    held = _told(agent.spawned(["claude", "--print"]))

    assert held.scopes == (ALL, READ, READ)
    assert "api.anthropic.com" in held.hosts
    assert held.read == ()
    # Its state, and none of the roots this machine's levels grant.
    assert str(home / ".claude") in held.write
    assert str(home / "w") not in held.write
    assert "/dev/null" not in held.write


def test_a_gpu_is_there_to_use_whatever_the_levels(tmp_path: Path) -> None:
    """A command in a container given GPUs opens their nodes to read and write."""
    fence = drawn(
        {"local": ALL, "user": NONE, "system": NONE, "online": False},
        workdirs=[str(tmp_path)],
        home=str(tmp_path),
    )
    assert fence.allows("/dev/dri/renderD128", write=True)
    assert fence.allows("/dev/kfd", write=True)
    assert not fence.allows("/dev/sda", write=True)
