"""Grok Build behind a gateway: which API it speaks, said the one way 1.0.46 reads it.

Under `GROK_XAI_API_BASE_URL` alone, Grok Build picks the API by the model's name -- a model
it ships to `/responses`, any other id to `/chat/completions` -- and has no word for
Anthropic's at all. So a gateway account says which, and the driver writes a `[model.*]`
entry carrying that `api_backend` into the CLI's `config.toml` and asks for it by name -- and
hands an Anthropic-shaped one its headers in the `GROK_CONFIG` overlay. Read off the commands
the driver builds, the environment it gives them and the file it leaves, with nothing spawned.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import GrokBuildAgent, GrokBuildAgentConfig
from hmz.coganchor.agents.event import Unrecoverable
from hmz.coganchor.agents.grok import _overlaid, _routed
from hmz.coganchor.machines import MachineBase, MachineConfig
from hmz.coganchor.providers import login
from tests.stubs import HereAnchor

if TYPE_CHECKING:
    from pathlib import Path

#: Where the gateway is, and the key it takes -- which must never be written to a file.
AT = "http://127.0.0.1:9/v1"
KEY = "sk-never-on-disk"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A Grok Build home of the test's own, so nobody's own `config.toml` is touched."""
    at = tmp_path / "grok"
    monkeypatch.setenv("GROK_HOME", str(at))
    return at


def _read(home: Path) -> dict[str, Any]:
    return tomllib.loads((home / "config.toml").read_text("utf-8"))


def _way(name: str) -> backends.Way:
    found = login.way_of("grok", name)
    assert found is not None
    return found


def _agent(provider: str, model: str = "claude-x") -> GrokBuildAgent:
    return GrokBuildAgent(
        GrokBuildAgentConfig(model=model, effort="high", provider=provider)
    )


def test_grok_offers_a_gateway_per_protocol_and_the_sign_ins_it_has() -> None:
    profile = backends.named("grok")
    assert profile is not None
    assert [way.name for way in profile.ways] == [
        "login",
        "device",
        "oidc",
        "provider-command",
        "key",
        "openai-gateway",
        "anthropic-gateway",
    ]
    # Every variable either gateway asks for is one a turn is hushed of when it is not its.
    assert {"GROK_GATEWAY_API_BACKEND", "GROK_CONFIG", "XAI_API_KEY"} <= (
        profile.accounts()
    )


def test_an_openai_gateway_asks_which_api_and_says_responses_unless_told() -> None:
    made = login.make(
        "grok",
        "gw",
        _way("openai-gateway"),
        {
            "GROK_XAI_API_BASE_URL": AT,
            "XAI_API_KEY": KEY,
        },
    )
    assert made.env["GROK_GATEWAY_API_BACKEND"] == "responses"

    told = login.make(
        "grok",
        "chat",
        _way("openai-gateway"),
        {
            "GROK_XAI_API_BASE_URL": AT,
            "XAI_API_KEY": KEY,
            "GROK_GATEWAY_API_BACKEND": "chat_completions",
        },
    )
    assert told.env["GROK_GATEWAY_API_BACKEND"] == "chat_completions"


def test_an_anthropic_gateway_speaks_messages_whatever_it_was_answered() -> None:
    made = login.make(
        "grok",
        "ant",
        _way("anthropic-gateway"),
        {
            "GROK_XAI_API_BASE_URL": AT,
            "XAI_API_KEY": KEY,
        },
    )
    assert made.env["GROK_GATEWAY_API_BACKEND"] == "messages"


@pytest.mark.parametrize("speaks", ["responses", "chat_completions"])
def test_both_transports_ask_for_the_entry_that_says_the_api(
    home: Path, speaks: str
) -> None:
    login.make(
        "grok",
        "gw",
        _way("openai-gateway"),
        {
            "GROK_XAI_API_BASE_URL": AT,
            "XAI_API_KEY": KEY,
            "GROK_GATEWAY_API_BACKEND": speaks,
        },
    )
    session = _agent("gw", "gpt-x").new()

    held = session._command()
    run, _ = session._turn("hi")

    named = held[held.index("--model") + 1]
    assert run[run.index("--model") + 1] == named
    entry = _read(home)["model"][named]
    assert entry == {
        "model": "gpt-x",
        "base_url": AT,
        "api_backend": speaks,
        "env_key": "XAI_API_KEY",
        "hidden": True,
    }
    assert KEY not in (home / "config.toml").read_text("utf-8")


def test_an_anthropic_gateway_sends_its_key_as_anthropic_does(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The person's own overlay, which is hushed under an account like any other.
    monkeypatch.setenv("GROK_CONFIG", '{"models": {"default": "theirs"}}')
    login.make(
        "grok",
        "ant",
        _way("anthropic-gateway"),
        {
            "GROK_XAI_API_BASE_URL": AT,
            "XAI_API_KEY": KEY,
        },
    )
    agent = _agent("ant")
    held = agent.new()._command()

    entry = _read(home)["model"][held[held.index("--model") + 1]]
    assert entry["api_backend"] == "messages"
    assert KEY not in (home / "config.toml").read_text("utf-8")
    # In the overlay, which both transports apply, and never on the command line.
    overlay = json.loads(agent.environment()["GROK_CONFIG"])
    assert overlay == {
        "models": {
            "extra_headers": {"x-api-key": KEY, "anthropic-version": "2023-06-01"}
        }
    }
    assert not any(KEY in one for one in held)


@pytest.mark.parametrize("way", ["key", "openai-gateway"])
def test_only_an_anthropic_gateway_is_given_an_overlay(home: Path, way: str) -> None:
    login.make(
        "grok", "gw", _way(way), {"GROK_XAI_API_BASE_URL": AT, "XAI_API_KEY": KEY}
    )

    assert "GROK_CONFIG" not in _agent("gw").environment()


def test_an_overlay_already_set_keeps_what_it_said() -> None:
    theirs = json.dumps(
        {
            "features": {"x": True},
            "models": {"default": "m", "extra_headers": {"X-Team": "a"}},
        }
    )

    said = json.loads(_overlaid(theirs, {"x-api-key": "k"}))

    assert said == {
        "features": {"x": True},
        "models": {"default": "m", "extra_headers": {"X-Team": "a", "x-api-key": "k"}},
    }
    assert json.loads(_overlaid("not json", {"x-api-key": "k"})) == {
        "models": {"extra_headers": {"x-api-key": "k"}}
    }


def test_an_account_on_xai_itself_asks_for_the_model_as_it_is(home: Path) -> None:
    login.make("grok", "mine", _way("key"), {"XAI_API_KEY": KEY})
    held = _agent("mine", "grok-4.5").new()._command()

    assert held[held.index("--model") + 1] == "grok-4.5"
    assert not (home / "config.toml").exists()


def test_what_the_person_wrote_is_still_there_after_an_entry_is(home: Path) -> None:
    home.mkdir()
    theirs = '# mine\n[ui]\npermission_mode = "default" # keep this\n'
    (home / "config.toml").write_text(theirs, "utf-8")
    environ = {
        "GROK_HOME": str(home),
        "GROK_XAI_API_BASE_URL": AT,
        "GROK_GATEWAY_API_BACKEND": "responses",
    }

    named = _routed("gpt-x", environ)
    once = (home / "config.toml").read_text("utf-8")

    assert once.startswith(theirs)
    assert _read(home)["model"][named]["api_backend"] == "responses"
    # The same endpoint, model and API are the same entry, and finding it writes nothing.
    assert _routed("gpt-x", environ) == named
    assert (home / "config.toml").read_text("utf-8") == once
    # And another API is another entry beside it rather than this one written over.
    other = _routed("gpt-x", environ | {"GROK_GATEWAY_API_BACKEND": "chat_completions"})
    assert other != named
    assert set(_read(home)["model"]) == {named, other}


def test_a_config_kept_through_a_link_stays_a_link(home: Path, tmp_path: Path) -> None:
    real = tmp_path / "dotfiles" / "grok.toml"
    real.parent.mkdir()
    real.write_text("[ui]\n", "utf-8")
    home.mkdir()
    (home / "config.toml").symlink_to(real)

    _routed(
        "gpt-x",
        {
            "GROK_HOME": str(home),
            "GROK_XAI_API_BASE_URL": AT,
            "GROK_GATEWAY_API_BACKEND": "responses",
        },
    )

    assert (home / "config.toml").is_symlink()
    assert "model" in tomllib.loads(real.read_text("utf-8"))


def test_a_config_that_is_not_toml_is_refused_and_left_alone(home: Path) -> None:
    home.mkdir()
    (home / "config.toml").write_text("[ui\n", "utf-8")

    with pytest.raises(Unrecoverable, match="cannot be read as TOML"):
        _routed(
            "gpt-x",
            {
                "GROK_HOME": str(home),
                "GROK_XAI_API_BASE_URL": AT,
                "GROK_GATEWAY_API_BACKEND": "responses",
            },
        )

    assert (home / "config.toml").read_text("utf-8") == "[ui\n"


def test_an_api_grok_has_no_word_for_is_refused_once(home: Path) -> None:
    with pytest.raises(Unrecoverable, match="none of chat_completions, messages"):
        _routed(
            "gpt-x",
            {
                "GROK_HOME": str(home),
                "GROK_XAI_API_BASE_URL": AT,
                "GROK_GATEWAY_API_BACKEND": "completions",
            },
        )
    assert not (home / "config.toml").exists()


@dataclass(frozen=True, kw_only=True)
class _Machine(MachineConfig):
    """A machine only ever said to be started, handing back the anchor it holds."""

    anchor: HereAnchor

    def create(self) -> _Started:
        return _Started(self)


class _Started(MachineBase):
    def __init__(self, config: _Machine) -> None:
        super().__init__(config)
        self._anchor = config.anchor

    def start(self) -> HereAnchor:
        return self._anchor

    def stop(self) -> None:
        """Nothing was started, so there is nothing to take down."""


@pytest.mark.parametrize(
    ("way", "native", "refused"),
    [
        ("openai-gateway", True, True),
        ("openai-gateway", False, False),
        ("anthropic-gateway", False, True),
    ],
)
def test_a_gateway_account_on_another_machine_runs_only_where_it_can_be_said(
    home: Path, way: str, native: bool, refused: bool
) -> None:
    """A target's own CLI never reads this `config.toml`, nor may its commands get the key."""
    login.make(
        "grok", "gw", _way(way), {"GROK_XAI_API_BASE_URL": AT, "XAI_API_KEY": KEY}
    )
    anchor = HereAnchor(target="tcp://stub:0", native=native)
    agent = GrokBuildAgent(
        GrokBuildAgentConfig(
            model="gpt-x", effort="high", provider="gw", machine=_Machine(anchor=anchor)
        )
    )

    assert "GROK_CONFIG" not in agent.environment()
    if refused:
        with pytest.raises(Unrecoverable, match="runs on this machine"):
            agent.new()._command()
    else:
        held = agent.new()._command()
        assert held[held.index("--model") + 1].startswith("hmz-")
