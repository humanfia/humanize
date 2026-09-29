"""Qwen Code held to a fence: what its driver tells it, and what it leaves to the wrapper.

Qwen Code enforces none of a fence itself -- its permission rules hold its own tools and not
what its commands go on to do, and its sandbox is a container -- so the whole fence is put
around it from outside. What the driver adds is the fence said again as deny rules, and the
one grant the wrapper cannot know of: the settings files it wrote for the CLI to read.
"""

from __future__ import annotations

import dataclasses
import gc
import sys
from typing import TYPE_CHECKING

from hmz.coganchor.agents import QwenCodeAgent, QwenCodeAgentConfig
from hmz.coganchor.agents import qwen as backend
from hmz.coganchor.fence import ALL, NONE, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _able(*, net: bool) -> bool:
    del net
    return True


def _fence(tmp_path: Path, *, system: str = READ, online: bool = True) -> Fence:
    return Fence.of(
        local=ALL,
        user=READ,
        system=system,
        online=online,
        workdir=tmp_path / "work",
        home=tmp_path / "home",
    )


def _agent(fence: Fence | None) -> QwenCodeAgent:
    return QwenCodeAgent(QwenCodeAgentConfig(model="m", effort="low", fence=fence))


def test_everything_but_the_grants_is_spelled_out_directory_by_directory() -> None:
    assert backend._outside(["/nowhere-a", "/nowhere-b/c/d"]) == [
        "/!(nowhere-a|nowhere-b|@(nowhere-a|nowhere-b)/**)",
        "/nowhere-b/!(c|@(c)/**)",
        "/nowhere-b/c/!(d|@(d)/**)",
    ]


def test_a_grant_beneath_another_adds_nothing() -> None:
    assert backend._outside(["/nowhere-a", "/nowhere-a/b"]) == [
        "/!(nowhere-a|@(nowhere-a)/**)"
    ]


def test_the_whole_filesystem_granted_leaves_nothing_to_deny() -> None:
    assert backend._outside(["/", "/nowhere-a"]) == []


def test_a_name_with_glob_characters_in_it_is_matched_as_written() -> None:
    assert backend._escaped("a(b)|c,d*") == r"a\(b\)\|c\,d\*"


def test_a_grant_reached_through_a_link_is_granted_where_it_leads_too(
    tmp_path: Path,
) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")

    said = backend._outside([str(tmp_path / "link")])

    assert said[-1] == f"{tmp_path}/!(link|real|@(link|real)/**)"


def test_the_default_fence_is_said_as_edits_denied_and_nothing_else(
    tmp_path: Path,
) -> None:
    denied = backend._denied(_agent(_fence(tmp_path)).fenced())

    assert denied
    assert all(one.startswith("Edit(//") for one in denied)


def test_a_cut_network_takes_both_web_tools_away(tmp_path: Path) -> None:
    denied = backend._denied(
        _agent(_fence(tmp_path, system=NONE, online=False)).fenced()
    )

    assert {"WebFetch", "WebSearch"} <= set(denied)
    assert any(one.startswith("Read(//") for one in denied)


def test_no_fence_is_no_rules() -> None:
    assert backend._denied(None) == ()


def test_qwen_enforces_none_of_its_fence_and_is_let_read_its_settings(
    tmp_path: Path,
) -> None:
    fence = _fence(tmp_path, system=NONE, online=False)

    rest = _agent(fence).natively(fence)

    assert rest.allows(backend._root())
    assert not rest.allows(backend._root(), write=True)
    assert dataclasses.replace(rest, read=fence.read) == fence


def test_a_fence_that_grants_everything_is_left_as_it_is(tmp_path: Path) -> None:
    fence = Fence.of(
        local=ALL,
        user=ALL,
        system=ALL,
        online=True,
        workdir=tmp_path / "work",
        home=tmp_path / "home",
    )

    assert _agent(fence).natively(fence) == fence


def test_a_fenced_turn_is_spawned_inside_the_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    argv = _agent(_fence(tmp_path, system=NONE, online=False)).spawned(["qwen"])

    assert argv[:7] == [sys.executable, "-m", "hmz", "internal", "fence", argv[5], "--"]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert not policy.online
    assert policy.allows(backend._root())
    assert argv[-1] == "qwen"


def test_a_commands_streams_are_left_alone_whatever_the_fence(tmp_path: Path) -> None:
    denied = backend._denied(
        _agent(_fence(tmp_path, system=NONE, online=False)).fenced()
    )

    (devices,) = [one for one in denied if one.startswith("Edit(//dev/!(")]
    names = devices.removeprefix("Edit(//dev/!(").split("|@(")[0].split("|")
    assert {"stdin", "stdout", "stderr", "fd"} <= set(names)
    assert not any(one.startswith("Edit(//proc") for one in denied)


def test_fenced_agents_keep_settings_of_their_own_and_nothing_after_they_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend, "_EFFORTS", {})
    one, two = _agent(_fence(tmp_path)), _agent(_fence(tmp_path))

    first = backend._thinking("low", denied=("WebFetch",), owner=one)
    second = backend._thinking("low", denied=("WebFetch",), owner=two)

    assert first != second
    assert first.is_relative_to(backend._root())
    assert backend._EFFORTS == {}
    del one
    gc.collect()
    assert not first.exists()
    assert second.exists()
