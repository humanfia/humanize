"""`hmz.coganchor.statepaths`: which files are the agent's own rather than the project's."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, statepaths
from hmz.coganchor.statepaths import PROFILES, profile_for, resolve

if TYPE_CHECKING:
    from pathlib import Path


def _program(at: Path, first: str = "#!/bin/sh\n") -> Path:
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(first + "exit 0\n", encoding="utf-8")
    at.chmod(0o755)
    return at


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A resolved scratch root with its own `HOME` and an empty `PATH`."""
    held = tmp_path.resolve()
    (held / "home").mkdir()
    monkeypatch.setenv("HOME", str(held / "home"))
    monkeypatch.setenv("PATH", str(held / "empty"))
    return held


def test_every_profile_is_named_once_and_after_a_backend() -> None:
    names = [one.name for one in PROFILES]
    assert len(names) == len(set(names))
    assert set(names) == {one.name for one in backends.PROFILES}


@pytest.mark.parametrize("profile", PROFILES, ids=lambda one: one.name)
def test_every_state_path_is_under_the_home(profile: statepaths.AgentProfile) -> None:
    assert profile.state_paths
    assert all(one.startswith("~/") for one in profile.state_paths)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("claude", "claude"),
        ("/usr/local/bin/codex", "codex"),
        ("cursor-agent", "cursor-agent"),
        ("dsh-jsonrpc-agent-darwin-arm64", "dsh"),
        ("/opt/x/dsh-jsonrpc-agent-linux", "dsh"),
    ],
)
def test_profile_for_a_known_agent(name: str, expected: str) -> None:
    found = profile_for(name)
    assert found.name == expected
    assert found.state_paths


def test_profile_for_an_unknown_agent_is_generic() -> None:
    found = profile_for("/somewhere/my-agent")
    assert found == statepaths.AgentProfile(name="my-agent")
    assert found.state_paths == ()


def test_resolve_refuses_no_command() -> None:
    with pytest.raises(ValueError, match="no agent command"):
        resolve([])


@pytest.mark.parametrize("command", ["claude", "/nowhere/claude"])
def test_resolve_refuses_an_agent_that_is_not_there(root: Path, command: str) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        resolve([command])


def test_resolve_keeps_the_agents_own_state_and_humanizes_here(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = _program(root / "bin" / "claude")
    monkeypatch.setenv("PATH", str(root / "bin"))

    found = resolve(["claude", "-p", "hi"])

    home = root / "home"
    assert found.profile.name == "claude"
    assert found.program == str(program)
    assert found.argv == [str(program), "-p", "hi"]
    assert found.local_paths == sorted(found.local_paths)
    for kept in (".claude", ".claude.json", ".hmz", ".humanize", ".cache/humanize"):
        assert str(home / kept) in found.local_paths
    assert str(program) in found.local_programs
    assert str(home / ".claude") in found.local_programs
    assert "/bin/sh" in found.local_programs  # the interpreter it names outright


def test_resolve_follows_a_link_to_the_real_program(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = _program(root / "real" / "grok")
    (root / "bin").mkdir()
    (root / "bin" / "grok").symlink_to(real)
    monkeypatch.setenv("PATH", str(root / "bin"))

    found = resolve(["grok"])

    assert found.program == str(real)
    assert found.argv == [str(root / "bin" / "grok")]
    assert {str(real), str(root / "bin" / "grok")} <= set(found.local_programs)


def test_resolve_takes_a_path_as_it_is_written(root: Path) -> None:
    program = _program(root / "elsewhere" / "kimi")
    found = resolve([str(program), "--yolo"])
    assert found.profile.name == "kimi"
    assert found.argv == [str(program), "--yolo"]


def test_an_env_shebang_claims_every_place_the_interpreter_could_be(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _program(root / "bin" / "qwen", "#!/usr/bin/env node\n")
    node = _program(root / "tools" / "node")
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(root / "bin"), str(root / "tools")])
    )

    found = resolve(["qwen"])

    assert "/usr/bin/env" in found.local_programs
    assert str(root / "bin" / "node") in found.local_programs  # a miss, kept here too
    assert str(node) in found.local_programs


@pytest.mark.parametrize(
    "shebang", ["#!/usr/bin/env -S node --flag\n", "#!/usr/bin/env FOO=1 node\n"]
)
def test_an_env_shebang_reads_past_flags_and_variables(
    root: Path, monkeypatch: pytest.MonkeyPatch, shebang: str
) -> None:
    _program(root / "bin" / "pi", shebang)
    monkeypatch.setenv("PATH", str(root / "bin"))
    assert str(root / "bin" / "node") in resolve(["pi"]).local_programs


def test_an_env_shebang_naming_a_path_keeps_that_path(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _program(root / "bin" / "pi", f"#!/usr/bin/env {root}/opt/node\n")
    monkeypatch.setenv("PATH", str(root / "bin"))
    assert str(root / "opt" / "node") in resolve(["pi"]).local_programs


def test_an_npm_package_keeps_the_programs_beside_its_own(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = root / "lib" / "node_modules" / "@x" / "mimo" / "bin"
    launcher = _program(package / "mimo")
    native = _program(package / ".mimocode")
    (package / "README").write_text("not a program", encoding="utf-8")
    shims = root / "lib" / "node_modules" / ".bin"
    shims.mkdir()
    (shims / "mimo").symlink_to(launcher)
    monkeypatch.setenv("PATH", str(shims))

    found = resolve(["mimo"])

    assert {str(launcher), str(native)} <= set(found.local_programs)
    assert str(package / "README") not in found.local_programs


def test_a_program_outside_a_package_keeps_no_neighbours(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _program(root / "bin" / "pi")
    neighbour = _program(root / "bin" / "other")
    monkeypatch.setenv("PATH", str(root / "bin"))
    assert str(neighbour) not in resolve(["pi"]).local_programs


def test_codex_keeps_its_native_runtime_here(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = root / "codex"
    _program(package / "bin" / "codex", "#!/usr/bin/env node\n")
    vendor = package / "vendor" / "x86_64-unknown-linux-musl" / "bin"
    native = _program(vendor / "codex")
    host = _program(vendor / "codex-code-mode-host")
    node = _program(root / "tools" / "node")
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(package / "bin"), str(root / "tools")])
    )

    found = resolve(["codex"])

    assert {str(native), str(host), str(node)} <= set(found.local_programs)
    assert found.local_programs == sorted(set(found.local_programs))
