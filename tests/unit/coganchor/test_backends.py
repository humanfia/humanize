"""`hmz.coganchor.backends`: everything outside a driver needs to know about each CLI."""

from __future__ import annotations

import base64
import os
import re
import time
from pathlib import Path

import pytest

from hmz.coganchor import backends, settings
from hmz.coganchor.backends import PROFILES, Model, Profile


def _named(profile: Profile) -> str:
    return profile.name


# --- the table -------------------------------------------------------------------------------


def test_every_backend_is_named_once_and_every_alias_names_one() -> None:
    names = [one.name for one in PROFILES]
    aliases = [alias for one in PROFILES for alias in one.aliases]
    assert len(names) == len(set(names))
    assert len(aliases) == len(set(aliases))


@pytest.mark.parametrize("profile", PROFILES, ids=_named)
def test_every_profile_is_well_formed(profile: Profile) -> None:
    assert profile.name in profile.aliases
    assert profile.home_dir
    assert not profile.home_dir.startswith(("/", "~"))
    assert profile.efforts
    assert len(set(profile.efforts)) == len(profile.efforts)
    assert set(profile.beyond) <= set(profile.efforts)
    assert profile.silence > 0
    assert all("{ident}" in one for one in profile.logs)
    assert not profile.mounts or any(
        (profile.skills, profile.shared, profile.config, profile.works)
    )
    assert not profile.endpoint or profile.endpoint in profile.accounts()
    assert all(one.fault in backends.FAULTS for one in profile.signs)
    for way in profile.ways:
        assert way.name
        assert way.about
        assert not way.stdin or way.stdin in {one.env for one in way.asks}
    for host in profile.hosts:
        assert host == host.lower()
        assert "/" not in host
        assert "*" not in host.removeprefix("*.")


@pytest.mark.parametrize("profile", PROFILES, ids=_named)
def test_every_profile_takes_its_own_ladder(profile: Profile) -> None:
    for rung in profile.efforts:
        assert profile.takes(rung)
        if profile.swarms:
            assert profile.takes(backends.SWARM + rung)
    assert not profile.takes("no-such-rung")


@pytest.mark.parametrize("sign", backends.SIGNS, ids=lambda one: one.says)
def test_every_shared_sign_is_a_fault_and_a_pattern(sign: backends.Sign) -> None:
    assert sign.fault in backends.FAULTS
    re.compile(sign.says)


def test_a_bundle_fingerprint_must_be_a_pattern() -> None:
    assert backends.Bundled("cli.js", re.escape("VERSION:")).digest == ""
    with pytest.raises(ValueError, match="must be a pattern"):
        backends.Bundled("cli.js", "unclosed(")


# --- names -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "name"),
    [
        ("claude", "claude"),
        ("claude-code", "claude"),
        ("antigravity", "agy"),
        ("grokbuild", "grok"),
        ("minimax-code", "mcode"),
        ("cursor-cli", "cursor-agent"),
    ],
)
def test_named_by_any_alias(said: str, name: str) -> None:
    found = backends.named(said)
    assert found is not None
    assert found.name == name


@pytest.mark.parametrize("said", ["", "Claude", "nobody"])
def test_named_nothing(said: str) -> None:
    assert backends.named(said) is None


@pytest.mark.parametrize(("effort", "written"), [("", backends.AUTO), ("high", "high")])
def test_written(effort: str, written: str) -> None:
    assert backends.written(effort) == written


@pytest.mark.parametrize(
    ("permission", "said"), [("", backends.AS_CONFIGURED), ("read", "read")]
)
def test_permitted(permission: str, said: str) -> None:
    assert backends.permitted(permission) == said


def _profile(**given: object) -> Profile:
    fields: dict[str, object] = {
        "name": "x",
        "aliases": ("x",),
        "home_var": "X_HOME",
        "home_dir": ".x",
        "logs": ("logs/{ident}.jsonl",),
        "efforts": ("high", "low"),
    }
    return Profile(**(fields | given))  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    ("given", "effort", "takes"),
    [
        ({}, "high", True),
        ({}, "", True),
        ({}, backends.AUTO, True),
        ({}, "medium", False),
        ({}, "swarmhigh", False),
        ({"swarms": True}, "swarmhigh", True),
        ({"swarms": True}, "swarm", True),
        ({"beyond": ("ultra",)}, "ultra", True),
        ({"efforts": ()}, "anything", True),
        ({"efforts": ("as configured",)}, "anything", True),
    ],
)
def test_takes(given: dict[str, object], effort: str, takes: bool) -> None:
    assert _profile(**given).takes(effort) is takes


@pytest.mark.parametrize(("encodes", "spelled"), [(False, "abc"), (True, "YWJj")])
def test_logged(encodes: bool, spelled: str) -> None:
    assert _profile(encodes=encodes).logged("abc") == (f"logs/{spelled}.jsonl",)


def test_mcode_names_a_session_in_base64() -> None:
    profile = backends.named("mcode")
    assert profile is not None
    encoded = base64.urlsafe_b64encode(b"s-1").decode().rstrip("=")
    assert all(encoded in one for one in profile.logged("s-1"))


# --- homes -------------------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    held = tmp_path / "home"
    held.mkdir()
    monkeypatch.setenv("HOME", str(held))
    monkeypatch.delenv("X_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return held


def test_directory_defaults_under_the_home(home: Path) -> None:
    assert _profile().directory() == home / ".x"


def test_directory_moved_by_its_variable(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("X_HOME", "/moved")
    assert _profile().directory() == Path("/moved")
    assert _profile(home_in="x").directory() == Path("/moved/x")


def test_directory_read_from_a_turns_own_environment(home: Path) -> None:
    profile = _profile()
    assert profile.directory({"X_HOME": "/theirs"}) == Path("/theirs")
    assert profile.directory({"HOME": "/elsewhere"}) == Path("/elsewhere/.x")
    assert profile.directory({}) == home / ".x"


def test_configuration(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert Profile.configuration() == home / ".config"
    monkeypatch.setenv("XDG_CONFIG_HOME", "/cfg")
    assert Profile.configuration() == Path("/cfg")


def test_credentials_under_three_roots(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/cfg")
    profile = _profile(creds=("auth.json", "~/.x.json", "config/x/auth.json"))
    assert profile.credentials() == (
        (str(home / ".x" / "auth.json"), "home/auth.json"),
        (str(home / ".x.json"), "user/.x.json"),
        ("/cfg/x/auth.json", "config/x/auth.json"),
    )


def test_kept_maps_each_session_path_into_humanizes_own(
    home: Path, tmp_path: Path
) -> None:
    profile = _profile(sessions=("sessions", "index.jsonl"))
    at = tmp_path / "kept"
    assert profile.kept(at) == (
        (str(home / ".x" / "sessions"), str(at / "x" / "sessions")),
        (str(home / ".x" / "index.jsonl"), str(at / "x" / "index.jsonl")),
    )


def test_kept_also_spells_a_linked_home_with_the_link_followed(
    home: Path, tmp_path: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (home / ".x").symlink_to(real)
    profile = _profile(sessions=("sessions",))
    instead = str(tmp_path / "kept" / "x" / "sessions")
    assert profile.kept(tmp_path / "kept") == (
        (str(home / ".x" / "sessions"), instead),
        (str(real.resolve() / "sessions"), instead),
    )


@pytest.mark.parametrize("given", [{"told": True}, {}])
def test_kept_nothing_for_a_told_backend_or_one_without_sessions(
    home: Path, tmp_path: Path, given: dict[str, object]
) -> None:
    assert _profile(**given).kept(tmp_path) == ()


# --- accounts ----------------------------------------------------------------------------------


def test_accounts_and_hushes() -> None:
    profile = _profile(
        ways=(
            backends.Way(
                "key",
                "a key",
                asks=(backends.Asked("MOONSHOT_API_KEY", "key?", secret=True),),
                sets=(("USE_IT", "1"),),
            ),
        ),
        ambient=("X_BASE_URL",),
    )
    assert profile.accounts() == {"MOONSHOT_API_KEY", "USE_IT", "X_BASE_URL"}
    assert profile.hushes() == {
        "MOONSHOT_API_KEY",
        "KIMI_API_KEY",
        "USE_IT",
        "X_BASE_URL",
    }


@pytest.mark.parametrize(
    ("variable", "alike"),
    [
        ("GOOGLE_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
        ("OPENAI_API_BASE", ("OPENAI_BASE_URL", "OPENAI_API_BASE")),
        ("SOMETHING_ELSE", ("SOMETHING_ELSE",)),
    ],
)
def test_alike(variable: str, alike: tuple[str, ...]) -> None:
    assert backends.alike(variable) == alike


def test_alike_names_each_credential_in_one_group() -> None:
    names = [name for group in backends.ALIKE for name in group]
    assert len(names) == len(set(names))


def test_serves_respells_an_account_for_another_backend() -> None:
    assert backends.serves({"ANTHROPIC_API_KEY": "k"}, "claude") == {
        "ANTHROPIC_API_KEY": "k"
    }


@pytest.mark.parametrize(
    ("env", "backend"),
    [
        ({"ANTHROPIC_API_KEY": "k"}, "nobody"),
        ({}, "claude"),
        ({"NOBODY_READS_THIS": "k"}, "claude"),
    ],
)
def test_serves_nothing_it_cannot_carry(env: dict[str, str], backend: str) -> None:
    assert backends.serves(env, backend) is None


# --- hosts -------------------------------------------------------------------------------------


def test_reachable_is_the_profiles_hosts_alone_by_default() -> None:
    claude = backends.named("claude")
    assert claude is not None
    assert backends.reachable(claude, {}) == claude.hosts


@pytest.mark.parametrize(
    ("value", "host"),
    [
        ("https://gw.example/v1", "gw.example"),
        ("https://GW.Example.:8443/v1", "gw.example:8443"),
        ("gw.example", "gw.example"),
        ("http://[::1]:9000", "[::1]:9000"),
    ],
)
def test_reachable_follows_an_accounts_endpoint(value: str, host: str) -> None:
    profile = _profile(endpoint="X_BASE_URL", ambient=("X_BASE_URL",), hosts=("api.x",))
    assert backends.reachable(profile, {"X_BASE_URL": value}) == ("api.x", host)


@pytest.mark.parametrize("value", ["", "   ", "https://", "http://bad:port"])
def test_reachable_ignores_a_value_naming_no_host(value: str) -> None:
    profile = _profile(endpoint="X_BASE_URL", hosts=("api.x",))
    assert backends.reachable(profile, {"X_BASE_URL": value}) == ("api.x",)


def test_reachable_names_each_host_once() -> None:
    profile = _profile(
        endpoint="X_BASE_URL", ambient=("X_AUTH_HOST",), hosts=("api.x",)
    )
    said = {"X_BASE_URL": "https://api.x/", "X_AUTH_HOST": "auth.x"}
    assert backends.reachable(profile, said) == ("api.x", "auth.x")


def test_reachable_follows_a_switch_onto_a_cloud() -> None:
    claude = backends.named("claude")
    assert claude is not None
    found = backends.reachable(
        claude, {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "eu-west-1"}
    )
    assert "bedrock-runtime.eu-west-1.amazonaws.com" in found
    defaulted = backends.reachable(claude, {"CLAUDE_CODE_USE_BEDROCK": "1"})
    assert "bedrock-runtime.us-east-1.amazonaws.com" in defaulted


def test_reachable_refuses_a_region_that_is_not_a_label() -> None:
    claude = backends.named("claude")
    assert claude is not None
    found = backends.reachable(
        claude, {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "evil.com/x"}
    )
    assert not any("amazonaws" in one for one in found)


# --- failures ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "status", "fault"),
    [
        ((), 126, "missing"),
        ((), 127, "missing"),
        ((), -9, "killed"),
        ((), 137, "killed"),
        (("HTTP 429 Too Many Requests",), 1, "throttled"),
        ((b"Rate limit reached",), 1, "throttled"),
        (("You have exceeded your quota",), 1, "spent"),
        (("401 Unauthorized",), 1, "refused"),
        (("Error: model not found",), 1, "retired"),
        (("database is locked",), 1, "contended"),
        (("read ECONNRESET",), 1, "dropped"),
        (("bwrap: setting up uid map: Permission denied",), 1, "sandboxed"),
        (("something nobody recognises",), 1, ""),
        ((None, ""), 1, ""),
        # The stream it complains on is read before the protocol stream.
        (("rate limit", "401"), 1, "throttled"),
    ],
)
def test_trouble(said: tuple[str | bytes | None, ...], status: int, fault: str) -> None:
    assert backends.trouble("claude", *said, status=status) == fault


def test_trouble_reads_the_journal_last() -> None:
    assert backends.trouble("agy", "terminated", journal="status 429") == "throttled"
    assert backends.trouble("agy", "401", journal="status 429") == "refused"


def test_trouble_reads_only_the_end_of_a_long_stream() -> None:
    said = "429 " + "x" * 10_000
    assert backends.trouble("claude", said) == ""


def test_trouble_for_an_unknown_backend_reads_the_shared_signs() -> None:
    assert backends.trouble("nobody", "429") == "throttled"


def test_trouble_reads_a_backends_own_signs_first() -> None:
    said = "couldn't set model: unknown model id"
    assert backends.trouble("grok", said) == "throttled"
    assert backends.trouble("claude", said) == "retired"
    assert backends.trouble("mcode", "Please sign in to MiniMax") == "refused"


def test_journalled_reads_the_newest_recent_log(home: Path) -> None:
    agy = backends.named("agy")
    assert agy is not None
    logs = agy.directory() / "log"
    logs.mkdir(parents=True)
    older, newer = logs / "cli-1.log", logs / "cli-2.log"
    older.write_text("old 401", encoding="utf-8")
    newer.write_text("new 429", encoding="utf-8")
    long_ago = time.time() - 60
    os.utime(older, (long_ago, long_ago))
    assert backends.journalled("agy") == "new 429"
    os.utime(newer, (long_ago - 1, long_ago - 1))
    assert backends.journalled("agy") == "old 401"
    assert backends.journalled("agy", within=10) == ""


def test_journalled_reads_the_home_of_the_turns_environment(tmp_path: Path) -> None:
    agy = backends.named("agy")
    assert agy is not None
    theirs = tmp_path / "theirs"
    log = agy.directory({"HOME": str(theirs)}) / "cli.log"
    log.parent.mkdir(parents=True)
    log.write_text("429", encoding="utf-8")
    assert backends.journalled("agy", {"HOME": str(theirs)}) == "429"


@pytest.mark.parametrize("backend", ["claude", "nobody"])
def test_journalled_nothing_for_a_backend_without_a_log(
    home: Path, backend: str
) -> None:
    assert backends.journalled(backend) == ""


@pytest.mark.parametrize(
    ("backend", "said"),
    [
        ("agy", "install agy and put it on PATH"),
        ("antigravity", "install agy and put it on PATH"),
        ("nobody", "install nobody and put it on PATH"),
    ],
)
def test_installing_a_backend_nobody_wrote_the_install_of(
    backend: str, said: str
) -> None:
    assert backends.installing(backend) == said


def test_installing_a_known_backend_names_its_line() -> None:
    claude = backends.named("claude")
    assert claude is not None
    assert backends.installing("claude-code") == claude.installs != ""


# --- finding programs --------------------------------------------------------------------------


def _executable(at: Path, mode: int = 0o755) -> Path:
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text("#!/bin/sh\n", encoding="utf-8")
    at.chmod(mode)
    return at


_NAME = "hmz-unit-test-no-such-cli"


@pytest.fixture
def path(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    held = tmp_path / "bin"
    held.mkdir()
    monkeypatch.setenv("PATH", str(held))
    return held


def test_program_on_path(path: Path) -> None:
    on = _executable(path / _NAME)
    assert backends.program(_NAME) == str(on)
    assert backends.elsewhere(_NAME) is None


def test_program_installed_where_path_does_not_look(path: Path, home: Path) -> None:
    there = _executable(home / ".local" / "bin" / _NAME)
    assert backends.program(_NAME) == str(there)
    assert backends.elsewhere(_NAME) == str(there)


def test_program_not_installed(path: Path) -> None:
    _executable(path.parent / "not-on-path" / _NAME)
    assert backends.program(_NAME) is None
    assert backends.elsewhere(_NAME) is None


def test_program_as_a_path(tmp_path: Path) -> None:
    runs = _executable(tmp_path / "runs")
    stays = _executable(tmp_path / "stays", 0o644)
    assert backends.program(str(runs)) == str(runs)
    assert backends.program(str(stays)) is None
    assert backends.program(str(tmp_path)) is None
    assert backends.elsewhere(str(runs)) is None


# --- reading -a --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "place", "backend", "model", "effort", "provider"),
    [
        ("claude/claude-opus-5", "", "claude", "claude-opus-5", "", ""),
        ("claude/claude-opus-5:high", "", "claude", "claude-opus-5", "high", ""),
        ("claude/claude-opus-5:auto", "", "claude", "claude-opus-5", "", ""),
        ("coder=codex/gpt-5:xhigh", "coder", "codex", "gpt-5", "xhigh", ""),
        (" coder = codex/gpt-5", "coder", "codex", "gpt-5", "", ""),
        ("claude@work/m:low", "", "claude", "m", "low", "work"),
        ("kimi/moonshot/kimi-k3:max", "", "kimi", "moonshot/kimi-k3", "max", ""),
        ("mcode/custom:gw/m", "", "mcode", "custom:gw/m", "", ""),
    ],
)
def test_read(
    spec: str, place: str, backend: str, model: str, effort: str, provider: str
) -> None:
    name, profile, *rest = backends.read(spec)
    assert (name, profile.name, *rest) == (place, backend, model, effort, provider)


@pytest.mark.parametrize(
    ("spec", "why"),
    [
        ("1bad=claude/m", "not a place a flow could declare"),
        ("claude/m,codex/n", "expected one agent"),
        ("claude@/m", "expected an account"),
        ("nobody/m", "expected \\[NAME=\\]CLI"),
        ("claude", "expected \\[NAME=\\]CLI"),
        ("claude/ :high", "expected \\[NAME=\\]CLI"),
    ],
)
def test_read_refuses(spec: str, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        backends.read(spec)


# --- added CLIs --------------------------------------------------------------------------------


def test_nothing_added_is_the_built_in_backends_alone() -> None:
    assert backends.speaking() == {}
    assert backends.profiles() == PROFILES
    assert backends.declared("my-agent") == ((), ())


def test_remember_makes_a_backend_of_an_added_cli() -> None:
    assert backends.remember("", ["/opt/bin/my-agent", "--acp", " "]) == "my-agent"
    assert backends.speaking() == {"my-agent": ("/opt/bin/my-agent", "--acp")}
    added = backends.named("my-agent")
    assert added is not None
    assert added in backends.profiles()
    assert added.efforts == ("as configured",)
    assert added.takes("anything")
    assert added.resumes
    assert added.forks
    assert backends.read("my-agent/whatever")[1] == added


@pytest.mark.parametrize(
    ("name", "command", "why"),
    [
        ("x", [], "needs a command"),
        ("x", ["  "], "needs a command"),
        ("", ["claude", "--acp"], "already a backend"),
        ("", ["/usr/bin/claude-code"], "already a backend"),
        ("other", ["my-agent"], "called what it runs"),
    ],
)
def test_remember_refuses(name: str, command: list[str], why: str) -> None:
    with pytest.raises(ValueError, match=why):
        backends.remember(name, command)
    assert backends.speaking() == {}


def test_remember_again_replaces_the_command_and_keeps_what_was_declared() -> None:
    settings.changes(
        lambda held: held.update(
            clis={
                "my-agent": {
                    "command": ["my-agent"],
                    "hosts": ["api.mine", " "],
                    "state": ["~/.mine"],
                }
            }
        )
    )
    assert backends.declared("my-agent") == (("api.mine",), ("~/.mine",))
    added = backends.named("my-agent")
    assert added is not None
    assert added.hosts == ("api.mine",)

    backends.remember("my-agent", ["my-agent", "--v2"])

    assert backends.speaking() == {"my-agent": ("my-agent", "--v2")}
    assert backends.declared("my-agent") == (("api.mine",), ("~/.mine",))


def test_forget_takes_an_added_cli_away() -> None:
    settings.changes(lambda held: held.update(other=1))
    backends.remember("my-agent", ["my-agent"])
    backends.remember("their-agent", ["their-agent"])
    assert backends.forget("my-agent")
    assert not backends.forget("my-agent")
    assert backends.speaking() == {"their-agent": ("their-agent",)}
    assert backends.named("my-agent") is None
    assert settings.read()["other"] == 1


@pytest.mark.parametrize(
    "clis",
    [
        "not a map",
        {"bad": "not a list", "empty": [], "also": {"command": "nope"}},
    ],
)
def test_speaking_reads_a_hand_edited_file_forgivingly(clis: object) -> None:
    settings.changes(lambda held: held.update(clis=clis))
    assert backends.speaking() == {}


def test_speaking_reads_an_unreadable_file_as_nothing_added() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text("clis: [unclosed\n", encoding="utf-8")
    assert backends.speaking() == {}


def test_speaking_sees_a_change_made_since_it_last_read() -> None:
    backends.remember("my-agent", ["my-agent"])
    assert "my-agent" in backends.speaking()
    settings.where().write_text(
        "clis:\n  their-agent: [their-agent, --x]\n", encoding="utf-8"
    )
    assert backends.speaking() == {"their-agent": ("their-agent", "--x")}


def test_a_model_is_a_name_and_its_efforts() -> None:
    assert Model("m", ("high",)) == Model("m", ("high",), swarms=False)
    assert Model("m", ()) != Model("m", (), swarms=True)
