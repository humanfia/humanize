"""The `coganchor cog` line, written out from the settings a session runs under."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from hmz.coganchor import binary
from hmz.coganchor.anchor import AnchorConfig
from hmz.coganchor.argv import forget, kept, options, render
from hmz.coganchor.fence import READ, WRITE, Fence
from hmz.coganchor.homes import Virtual

if TYPE_CHECKING:
    import pytest


def test_the_defaults_are_written_as_the_target_and_net_alone() -> None:
    assert options(AnchorConfig()) == ["--target=local", "--net=local"]


SUPERVISED = AnchorConfig(
    target="ssh://box",
    harness="local",
    broker="meet.example",
    workspace="/srv/project",
    chdir="/srv/project/sub",
    remote_path="/data/project",
    shadow="/mirror",
    local_paths=("/srv/project/.venv", "/srv/project/node_modules"),
    local_execs=("/usr/local/bin",),
    private=("ANTHROPIC_API_KEY",),
    redirects=(("/home/me/.claude", "/accounts/one/.claude"),),
    net="remote",
    net_allow=("api.example.com:443",),
    token="-starts-with-a-dash",
    force=True,
)

NATIVE = AnchorConfig(
    target="docker://box",
    native=True,
    hushes=("ANTHROPIC_API_KEY",),
    projects=(("CODEX_HOME", "/accounts/codex"),),
    home=Virtual(
        variable="CODEX_HOME",
        default=".codex",
        rewrites=("config.toml",),
        lodges="skills",
        private=("sessions", "state_*.sqlite*"),
        skills=(("review", "/flows/skills/review"),),
    ),
    brings=(("CODEX_HOME/sessions", "/epic/codex"),),
    tells="/tmp/homes",
    installs="npm install -g some-cli",
)

FENCED = AnchorConfig(
    target="local",
    fence=Fence.of(
        rules=[("~", READ), (".", WRITE)],
        online=False,
        workdir="/srv/project",
        home="/home/me",
        hosts=["api.example.com"],
    ),
)


def test_a_supervised_session_is_written_option_by_option() -> None:
    assert options(SUPERVISED) == [
        "--target=ssh://box",
        "--net=remote",
        "--workspace=/srv/project",
        "--chdir=/srv/project/sub",
        "--remote-path=/data/project",
        "--shadow=/mirror",
        f"--token-file={kept('-starts-with-a-dash')}",
        "--broker=meet.example",
        "--local-path=/srv/project/.venv",
        "--local-path=/srv/project/node_modules",
        "--local-exec=/usr/local/bin",
        "--net-allow=api.example.com:443",
        "--redirect=/home/me/.claude=/accounts/one/.claude",
        "--private=ANTHROPIC_API_KEY",
        "--force",
    ]


def test_a_native_session_is_written_option_by_option() -> None:
    assert NATIVE.home is not None
    assert options(NATIVE) == [
        "--target=docker://box",
        "--net=local",
        "--installs=npm install -g some-cli",
        f"--home={NATIVE.home.dumps()}",
        "--hush=ANTHROPIC_API_KEY",
        "--project=CODEX_HOME=/accounts/codex",
        "--bring=CODEX_HOME/sessions=/epic/codex",
        "--tell=/tmp/homes",
        "--native",
    ]


def test_a_fence_is_written_as_its_json() -> None:
    assert FENCED.fence is not None
    assert options(FENCED) == [
        "--target=local",
        "--net=local",
        f"--fence={FENCED.fence.dumps()}",
    ]
    assert Fence.loads(options(FENCED)[-1].removeprefix("--fence=")) == FENCED.fence


def test_a_harness_elsewhere_is_written_after_the_settings() -> None:
    assert options(AnchorConfig(harness="same", target="ssh://box")) == [
        "--target=ssh://box",
        "--net=local",
        "--harness=same",
    ]


def test_a_local_harness_and_empty_settings_are_not_written() -> None:
    written = options(AnchorConfig(harness="local", installs="", broker=""))

    assert not any(
        one.startswith(("--harness", "--installs", "--broker", "--fence"))
        for one in written
    )


def test_a_secret_is_never_on_the_command_line_but_in_a_file_only_its_user_reads() -> (
    None
):
    written = options(AnchorConfig(target="tcp://node:4000", token="s3cret"))

    assert not [one for one in written if "s3cret" in one]
    (named,) = [one for one in written if one.startswith("--token-file=")]
    held = Path(named.partition("=")[2])
    assert held.read_text() == "s3cret"
    assert held.stat().st_mode & 0o077 == 0
    assert kept("s3cret") == str(held)

    forget("s3cret")

    assert not held.exists()


def test_render_runs_coganchor_cog_with_the_agent_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binary, "here", lambda: Path("/opt/coganchor"))

    line = render(NATIVE, ["claude", "-p", "hi"])

    assert line == ["/opt/coganchor", "cog", *options(NATIVE), "claude", "-p", "hi"]
