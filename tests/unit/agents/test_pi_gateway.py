"""pi's ways in beyond its own /login: a vendor's key, a gateway, a cloud.

A key is a variable pi reads itself and a cloud is a few of them, so those are only what is
written down. A gateway is not: pi has no variable for where a vendor is, only providers
declared in `models.json` under its home -- so the driver writes one there out of what the
account was answered with, and holds the turn to it with `--provider`. Read off the command
lines built and the file left behind, with nothing spawned.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import PiAgent, PiAgentConfig
from hmz.coganchor.providers import login
from tests.logins import way

if TYPE_CHECKING:
    from pathlib import Path

#: What a gateway account of pi's is answered with, short of the protocol.
GATEWAY = {
    "PI_GATEWAY_URL": "https://gw.example/v1",
    "PI_GATEWAY_KEY": "not-a-real-key",
    "PI_GATEWAY_MODEL": "glm-5",
}


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The home pi keeps, under a home of the test's own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    return tmp_path / "home" / ".pi" / "agent"


def _command(account: str, model: str = "glm-5") -> list[str]:
    return (
        PiAgent(PiAgentConfig(model=model, effort="low", provider=account))
        .new()
        ._command()
    )


def _declared(home: Path) -> dict[str, dict[str, object]]:
    return json.loads((home / "models.json").read_text())["providers"]


def test_pi_offers_a_key_per_vendor_a_gateway_per_protocol_and_the_clouds() -> None:
    offered = [one.name for one in providers.ways("pi")]

    assert offered == [
        "login",
        "anthropic-key",
        "anthropic-token",
        "openai-key",
        "gemini-key",
        "xai-key",
        "openrouter-key",
        "deepseek-key",
        "groq-key",
        "mistral-key",
        "openai-gateway",
        "anthropic-gateway",
        "gemini-gateway",
        "bedrock",
        "vertex",
        "azure",
        providers.ENV.name,
    ]


@pytest.mark.parametrize(
    ("name", "variable"),
    [
        ("anthropic-key", "ANTHROPIC_API_KEY"),
        ("anthropic-token", "ANTHROPIC_OAUTH_TOKEN"),
        ("openai-key", "OPENAI_API_KEY"),
        ("gemini-key", "GEMINI_API_KEY"),
        ("xai-key", "XAI_API_KEY"),
        ("openrouter-key", "OPENROUTER_API_KEY"),
        ("deepseek-key", "DEEPSEEK_API_KEY"),
        ("groq-key", "GROQ_API_KEY"),
        ("mistral-key", "MISTRAL_API_KEY"),
    ],
)
def test_a_vendor_key_is_the_vendors_own_variable_and_nothing_else(
    name: str, variable: str
) -> None:
    made = login.make("pi", "mine", way("pi", name), {variable: "not-a-real-key"})

    assert dict(made.env) == {variable: "not-a-real-key"}
    assert made.args == ()


def test_the_clouds_ask_what_pis_own_providers_for_them_read() -> None:
    assert login.asked(way("pi", "bedrock"), {}) == ["AWS_PROFILE"]
    assert login.asked(way("pi", "vertex"), {}) == ["GOOGLE_CLOUD_PROJECT"]
    assert login.asked(way("pi", "azure"), {}) == [
        "AZURE_OPENAI_BASE_URL",
        "AZURE_OPENAI_API_KEY",
    ]


def test_an_openai_gateway_asks_which_of_openais_protocols_and_assumes_completions() -> (
    None
):
    gateway = way("pi", "openai-gateway")

    assert login.asked(gateway, {}) == [
        "PI_GATEWAY_URL",
        "PI_GATEWAY_KEY",
        "PI_GATEWAY_MODEL",
    ]
    made = login.make("pi", "gw", gateway, GATEWAY)
    assert dict(made.env) == {**GATEWAY, "PI_GATEWAY_API": "openai-completions"}
    responses = login.make(
        "pi", "gw2", gateway, {**GATEWAY, "PI_GATEWAY_API": "openai-responses"}
    )
    assert responses.env["PI_GATEWAY_API"] == "openai-responses"


@pytest.mark.parametrize(
    ("name", "api"),
    [
        ("anthropic-gateway", "anthropic-messages"),
        ("gemini-gateway", "google-generative-ai"),
    ],
)
def test_the_other_gateways_set_the_one_protocol_their_vendor_has(
    name: str, api: str
) -> None:
    made = login.make("pi", "gw", way("pi", name), GATEWAY)

    assert dict(made.env) == {**GATEWAY, "PI_GATEWAY_API": api}


def test_a_gateway_turn_is_held_to_a_provider_declared_in_models_json(
    home: Path,
) -> None:
    login.make("pi", "gw", way("pi", "openai-gateway"), GATEWAY)

    argv = _command("gw")

    named = argv[argv.index("--provider") + 1]
    assert named.startswith("humanize-")
    assert _declared(home)[named] == {
        "baseUrl": "https://gw.example/v1",
        "api": "openai-completions",
        "apiKey": "$PI_GATEWAY_KEY",
        "models": [{"id": "glm-5"}],
    }
    # The key is a reference pi resolves out of the turn's environment: it is in neither the
    # command line nor the file.
    assert "not-a-real-key" not in argv
    assert "not-a-real-key" not in (home / "models.json").read_text()
    assert (home / "models.json").stat().st_mode & 0o777 == 0o600


def test_what_the_user_declared_there_already_is_kept(home: Path) -> None:
    home.mkdir(parents=True)
    theirs = {"baseUrl": "http://localhost:11434/v1", "api": "openai-completions"}
    (home / "models.json").write_text(
        json.dumps({"providers": {"ollama": theirs}, "modelOverrides": {}})
    )
    (home / "models.json").chmod(0o644)
    login.make("pi", "gw", way("pi", "anthropic-gateway"), GATEWAY)

    _command("gw")

    said = json.loads((home / "models.json").read_text())
    assert said["providers"]["ollama"] == theirs
    assert "modelOverrides" in said
    assert len(said["providers"]) == 2
    assert (home / "models.json").stat().st_mode & 0o777 == 0o644


def test_a_gateway_declared_once_is_not_written_again(home: Path) -> None:
    login.make("pi", "gw", way("pi", "gemini-gateway"), GATEWAY)
    _command("gw")
    written = (home / "models.json").stat().st_ino  # a rewrite is a new file moved in

    again = _command("gw")

    assert "--provider" in again
    assert (home / "models.json").stat().st_ino == written


def test_two_gateways_are_two_providers(home: Path) -> None:
    login.make("pi", "a", way("pi", "openai-gateway"), GATEWAY)
    login.make(
        "pi",
        "b",
        way("pi", "openai-gateway"),
        {**GATEWAY, "PI_GATEWAY_URL": "https://other.example/v1"},
    )

    first, second = _command("a"), _command("b")

    assert (
        first[first.index("--provider") + 1] != second[second.index("--provider") + 1]
    )
    assert len(_declared(home)) == 2


def test_a_models_json_humanize_cannot_read_is_never_written_over(home: Path) -> None:
    home.mkdir(parents=True)
    commented = '{\n  // mine\n  "providers": {}\n}\n'
    (home / "models.json").write_text(commented)
    login.make("pi", "gw", way("pi", "openai-gateway"), GATEWAY)

    with pytest.raises(ValueError, match="comments"):
        _command("gw")

    assert (home / "models.json").read_text() == commented


def test_an_account_on_no_gateway_declares_nothing(home: Path) -> None:
    login.make("pi", "key", way("pi", "openai-key"), {"OPENAI_API_KEY": "k"})

    argv = _command("key", "openai/gpt-5")

    assert "--provider" not in argv
    assert not (home / "models.json").exists()


def test_a_linked_models_json_is_written_through_the_link(
    home: Path, tmp_path: Path
) -> None:
    kept = tmp_path / "dotfiles" / "models.json"
    kept.parent.mkdir()
    kept.write_text('{"providers": {}}')
    home.mkdir(parents=True)
    (home / "models.json").symlink_to(kept)
    login.make("pi", "gw", way("pi", "openai-gateway"), GATEWAY)

    _command("gw")

    assert (home / "models.json").is_symlink()
    assert len(json.loads(kept.read_text())["providers"]) == 1


def test_an_anchored_gateway_turn_is_refused_saying_why(home: Path) -> None:
    from hmz.coganchor.agents.config import anchored

    login.make("pi", "gw", way("pi", "openai-gateway"), GATEWAY)
    config = PiAgentConfig(
        model="glm-5", effort="low", provider="gw", machine=anchored("ssh://gpu-box")
    )

    with pytest.raises(ValueError, match=r"models\.json on the machine it runs on"):
        PiAgent(config).new()._command()
    assert not (home / "models.json").exists()
