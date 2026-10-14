"""The `hmz internal anchor` line, read into settings and written back out as the same line."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hmz.coganchor.anchor import AnchorConfig
from hmz.coganchor.argv import forget, kept, options, parser, render, settings
from hmz.coganchor.fence import ALL, NONE, READ, Fence
from hmz.coganchor.homes import Virtual

ENVIRONMENT = (
    "HUMANIZE_TARGET",
    "HUMANIZE_HARNESS",
    "HUMANIZE_RENDEZVOUS",
    "HUMANIZE_SHADOW",
    "HUMANIZE_TOKEN",
)


@pytest.fixture(autouse=True)
def unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


def read(*argv: str) -> AnchorConfig:
    return settings(parser().parse_args(argv))


def test_nothing_said_is_every_default() -> None:
    args = parser().parse_args([])

    assert settings(args) == AnchorConfig()
    assert args.command == []
    assert not args.check
    assert args.log_level is None


def test_the_environment_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUMANIZE_TARGET", "ssh://box")
    monkeypatch.setenv("HUMANIZE_RENDEZVOUS", "meet.example")
    monkeypatch.setenv("HUMANIZE_SHADOW", "/mirror")
    monkeypatch.setenv("HUMANIZE_TOKEN", "secret")

    config = read()

    assert config.target == "ssh://box"
    assert config.broker == "meet.example"
    assert config.shadow == "/mirror"
    assert config.token == "secret"


def test_everything_after_the_options_is_the_agent() -> None:
    args = parser().parse_args(
        ["--target=local", "claude", "--model", "opus", "--net=x"]
    )

    assert args.command == ["claude", "--model", "opus", "--net=x"]


def test_pairs_are_read_on_their_first_equals_sign() -> None:
    config = read(
        "--redirect=/a=/b=c",
        "--project=CODEX_HOME=/creds",
        "--bring=CODEX_HOME/sessions=/epic/codex",
        "--tell=/tmp/homes",
    )

    assert config.redirects == (("/a", "/b=c"),)
    assert config.projects == (("CODEX_HOME", "/creds"),)
    assert config.brings == (("CODEX_HOME/sessions", "/epic/codex"),)
    assert config.tells == "/tmp/homes"


def test_a_fence_is_read_from_its_json() -> None:
    fence = Fence(write=("/",), hosts=("api.example.com",))

    assert read(f"--fence={fence.dumps()}").fence == fence


@pytest.mark.parametrize(
    "argv",
    [
        ["--redirect=relative=/b"],
        ["--redirect=/only-half"],
        ["--hush=A=B"],
        ["--project=NAME=relative"],
        ["--bring=CODEX_HOME=/epic"],
        ["--bring=CODEX_HOME/../x=/epic"],
        ["--bring=CODEX_HOME/sessions=relative"],
        ["--tell=relative"],
        ["--target=nonsense://x"],
    ],
)
def test_settings_no_session_could_run_under_are_refused(argv: list[str]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 -- each says its own
        read(*argv)


@pytest.mark.parametrize(
    "argv", [["--net=sideways"], ["--log-level=loud"], ["--bogus"]]
)
def test_options_the_parser_does_not_take_are_refused(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    with pytest.raises(SystemExit):
        parser().parse_args(argv)
    assert "hmz internal anchor" in capsys.readouterr().err


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
        local=ALL,
        user=READ,
        system=NONE,
        online=False,
        workdir="/srv/project",
        home="/home/me",
        hosts=["api.example.com"],
    ),
)


@pytest.mark.parametrize(
    "config",
    [
        AnchorConfig(),
        SUPERVISED,
        NATIVE,
        FENCED,
        AnchorConfig(harness="same", target="ssh://box"),
    ],
    ids=["defaults", "supervised", "native", "fenced", "harnessed"],
)
def test_what_is_written_reads_back_as_the_same_settings(config: AnchorConfig) -> None:
    assert read(*options(config)) == config


def test_a_local_harness_and_empty_settings_are_not_written() -> None:
    written = options(AnchorConfig(harness="local", installs="", broker=""))

    assert not any(
        one.startswith(("--harness", "--installs", "--broker", "--fence"))
        for one in written
    )


def test_render_runs_this_interpreter_with_the_agent_after() -> None:
    line = render(NATIVE, ["claude", "-p", "hi"])

    assert line[:5] == [sys.executable, "-Pm", "hmz", "internal", "anchor"]
    assert line[5:-3] == options(NATIVE)
    assert line[-3:] == ["claude", "-p", "hi"]


def test_a_secret_is_never_on_the_command_line_but_in_a_file_only_its_user_reads() -> (
    None
):
    written = options(AnchorConfig(target="tcp://node:4000", token="s3cret"))

    assert not [one for one in written if "s3cret" in one]
    (named,) = [one for one in written if one.startswith("--token-file=")]
    held = Path(named.partition("=")[2])
    assert held.read_text() == "s3cret"
    assert held.stat().st_mode & 0o077 == 0
    assert read(*written).token == "s3cret"
    assert kept("s3cret") == str(held)

    forget("s3cret")

    assert not held.exists()
