"""A project's configuration that would start programs on a machine that is not its own."""

from __future__ import annotations

import errno
import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import AnchorConfig, crossing, remote, transport
from hmz.coganchor.backends import PROFILES, Launcher
from hmz.coganchor.proto import RemoteOSError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import BinaryIO

CLAUDE = (
    Launcher(".claude/settings.json", ("hooks", "statusLine")),
    Launcher(".mcp.json", ("mcpServers.*.command",)),
    Launcher(".cursor/hooks.json"),
)


def _reading(files: Mapping[str, str]) -> Any:
    def read(path: str) -> bytes | None:
        said = files.get(path)
        return None if said is None else said.encode()

    return read


@pytest.mark.parametrize(
    ("config", "apart"),
    [
        (AnchorConfig(target="ssh://box", workspace="/w"), True),
        (AnchorConfig(target="ssh://box", workspace="/w", native=True), False),
        (AnchorConfig(target="ssh://box", workspace="/w", harness="ssh://gpu"), True),
        (AnchorConfig(target="ssh://box", workspace="/w", harness="same"), False),
        (AnchorConfig(target="ssh://box", workspace="/w", harness="ssh://box"), False),
    ],
    ids=["supervised", "native", "afar", "harness-on-the-target", "spelled-out"],
)
def test_a_cli_is_apart_from_its_work_unless_on_the_works_machine(
    config: AnchorConfig, apart: bool
) -> None:
    assert crossing.apart(config) is apart


def test_nothing_is_held_by_a_project_without_those_files() -> None:
    assert crossing.held(CLAUDE, _reading({})) == []


def test_what_is_held_is_named_by_file_and_key() -> None:
    files = {
        ".claude/settings.json": json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"command": "x"}]}]}, "model": "opus"}
        ),
        ".mcp.json": json.dumps(
            {"mcpServers": {"web": {"url": "https://x"}, "db": {"command": "db-mcp"}}}
        ),
        ".cursor/hooks.json": "{}",
    }

    assert crossing.held(CLAUDE, _reading(files)) == [
        ".claude/settings.json: hooks",
        ".mcp.json: mcpServers.*.command",
        ".cursor/hooks.json",
    ]


@pytest.mark.parametrize(
    "settings",
    ['{"model": "opus"}', '{"hooks": {}}', '{"statusLine": null}', '{"hooks": []}'],
)
def test_settings_that_start_nothing_hold_nothing(settings: str) -> None:
    files = {".claude/settings.json": settings}

    assert crossing.held(CLAUDE, _reading(files)) == []


def test_json_with_comments_and_trailing_commas_is_read_as_the_clis_read_it() -> None:
    files = {".claude/settings.json": '{\n // mine\n "hooks": {"Stop": [1]},\n}'}

    assert crossing.held(CLAUDE, _reading(files)) == [".claude/settings.json: hooks"]


def test_claude_s_own_settings_hold_a_command_hook_and_not_a_plugin_turned_off() -> (
    None
):
    claude = next(one for one in PROFILES if one.name == "claude").launchers
    hook = {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "audit"}]}]}
    files = {
        ".claude/settings.json": json.dumps({"enabledPlugins": {"x@market": False}}),
        ".claude/settings.local.json": json.dumps({"hooks": hook}),
    }

    assert crossing.held(claude, _reading(files)) == [
        ".claude/settings.local.json: hooks.*.*.hooks.*.command"
    ]


def test_yaml_is_read_as_yaml() -> None:
    omp = (Launcher(".omp/config.yml", ("extensions",)),)
    files = {".omp/config.yml": "extensions: [x]"}

    assert crossing.held(omp, _reading(files)) == [".omp/config.yml: extensions"]


def test_toml_is_read_as_toml() -> None:
    codex = (Launcher(".codex/config.toml", ("mcp_servers.*.command", "notify")),)
    files = {".codex/config.toml": '[mcp_servers.db]\ncommand = "db-mcp"\n'}

    assert crossing.held(codex, _reading(files)) == [
        ".codex/config.toml: mcp_servers.*.command"
    ]


def test_a_file_that_cannot_be_read_is_held_for_what_it_might_say() -> None:
    files = {".claude/settings.json": "{not json at all"}

    assert crossing.held(CLAUDE, _reading(files)) == [
        ".claude/settings.json (unreadable)"
    ]


def test_every_cli_s_launchers_are_files_of_a_kind_that_is_read() -> None:
    launchers = [one for profile in PROFILES for one in profile.launchers]

    assert launchers, "some CLI reads a project's hooks"
    for launcher in launchers:
        assert not launcher.path.startswith(("/", "~")), launcher
        if launcher.keys:
            assert launcher.path.endswith((".json", ".jsonc", ".toml", ".yml")), (
                launcher
            )
        else:
            assert launcher.path.endswith(("/", ".json")), launcher


class _Target:
    """The work's machine, as the road to it reads its files."""

    def __init__(self, files: Mapping[str, str]) -> None:
        self.files = files
        self.denied = False
        self.unreachable = False
        self.read: list[str] = []
        self.closed = 0

    def connect(self, target: Any, exports: Any, token: Any) -> Any:
        del target, exports, token
        if self.unreachable:
            raise ConnectionRefusedError("nobody there")
        held = self

        class Link:
            channel = None

            def close(self) -> None:
                held.closed += 1

        return Link()

    def client(self, channel: Any) -> Any:
        del channel
        held = self

        class Client:
            def start(self, token: Any) -> dict[str, Any]:
                return {}

            def read_file(self, path: str, sink: BinaryIO) -> dict[str, Any]:
                held.read.append(path)
                if held.denied:
                    raise RemoteOSError(errno.EACCES, "denied", path)
                if path not in held.files:
                    raise RemoteOSError(errno.ENOENT, "gone", path)
                sink.write(held.files[path].encode())
                return {}

            def listdir(self, path: str) -> dict[str, Any]:
                held.read.append(f"{path}/")
                inside = [one for one in held.files if one.startswith(f"{path}/")]
                return {"entries": inside}

            def close(self) -> None:
                held.closed += 1

        return Client()


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch) -> _Target:
    def make(files: Mapping[str, str]) -> _Target:
        made = _Target(files)
        monkeypatch.setattr(transport, "connect", made.connect)
        monkeypatch.setattr(remote, "RemoteClient", made.client)
        return made

    return make({})


def test_a_project_is_read_from_the_session_s_directory_up_to_the_workspace(
    target: _Target,
) -> None:
    target.files = {
        "/w/.mcp.json": '{"mcpServers": {"db": {"command": "db"}}}',
        "/w/desk/.claude/settings.json": '{"hooks": {"Stop": [1]}}',
    }
    config = AnchorConfig(target="ssh://box", workspace="/w")

    said = crossing.found(config, CLAUDE, "/w/desk")

    assert said == [
        "desk/.claude/settings.json: hooks",
        ".mcp.json: mcpServers.*.command",
    ]
    assert "/w/desk/.mcp.json" in target.read
    assert not [one for one in target.read if not one.startswith("/w/")]
    assert target.closed == 2, "the road put down again"


def test_a_directory_of_plugins_counts_where_it_holds_anything(target: _Target) -> None:
    plugins = (Launcher(".opencode/plugins/"),)
    config = AnchorConfig(target="ssh://box", workspace="/w")

    assert crossing.found(config, plugins, None) == []
    target.files = {"/w/.opencode/plugins/notify.ts": "export default {}"}
    assert crossing.found(config, plugins, None) == [".opencode/plugins/"]


def test_a_cli_reading_nothing_reaches_nothing(target: _Target) -> None:
    config = AnchorConfig(target="ssh://box", workspace="/w")

    assert crossing.found(config, (), None) == []
    assert target.read == []


def test_a_file_the_target_will_not_let_be_read_is_held_for_what_it_might_say(
    target: _Target,
) -> None:
    target.files = {"/w/.mcp.json": "{}"}
    target.denied = True

    said = crossing.found(
        AnchorConfig(target="ssh://box", workspace="/w"), CLAUDE, None
    )

    assert said == [f"{one.path} (unreadable)" for one in CLAUDE]
    assert target.closed == 2


def test_a_target_that_cannot_be_reached_is_its_failure(target: _Target) -> None:
    target.unreachable = True

    with pytest.raises(ConnectionRefusedError):
        crossing.found(AnchorConfig(target="ssh://box", workspace="/w"), CLAUDE, None)


def test_a_cli_apart_from_a_project_that_would_start_programs_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    said = [".claude/settings.json: hooks", ".mcp.json: mcpServers.*.command"]

    def found(*_: object) -> list[str]:
        return said

    monkeypatch.setattr(crossing, "found", found)

    with pytest.raises(NotImplementedError) as refused:
        crossing.refuse(
            AnchorConfig(target="ssh://box", workspace="/w"), CLAUDE, None, "claude"
        )

    assert ".claude/settings.json: hooks" in str(refused.value)
    assert ".mcp.json: mcpServers.*.command" in str(refused.value)
    assert "ssh://box" in str(refused.value)


def test_a_cli_on_the_works_machine_is_not_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def found(*_: Any) -> list[str]:
        raise AssertionError("nothing is read")

    monkeypatch.setattr(crossing, "found", found)

    crossing.refuse(
        AnchorConfig(target="ssh://box", workspace="/w", native=True),
        CLAUDE,
        None,
        "claude",
    )


def test_a_cli_apart_from_a_project_that_starts_nothing_is_let_be(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def found(*_: object) -> list[str]:
        return []

    monkeypatch.setattr(crossing, "found", found)

    crossing.refuse(AnchorConfig(target="ssh://box", workspace="/w"), CLAUDE, None, "x")
