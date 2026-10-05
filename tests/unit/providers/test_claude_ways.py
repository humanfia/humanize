"""Every kind of account Claude Code takes, as the ways into it ask for one and write it down.

Claude Code signs into a subscription or the Console, takes a key, a token or a federated
identity of Anthropic's, speaks to a gateway in front of Anthropic, Bedrock or Vertex, and runs
on six clouds' worth of somebody else's account. Each is a set of variables 2.1.288 reads, and
what is checked here is that each way asks for the ones that are somebody's to say and sets the
ones that are not -- nothing here runs the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, providers
from hmz.coganchor.providers import login
from tests import logins
from tests.logins import way

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home, somewhere temporary: nothing here may read or write the real one."""
    return logins.house(tmp_path, monkeypatch)


def test_the_ways_in_are_offered_sign_ins_first_and_clouds_last() -> None:
    assert [one.name for one in providers.ways("claude")] == [
        "login",
        "console",
        "token",
        "key",
        "wif",
        "anthropic-gateway",
        "bedrock-gateway",
        "vertex-gateway",
        "bedrock",
        "bedrock-key",
        "mantle",
        "vertex",
        "foundry",
        "aws",
        "google-cloud",
        "env",
    ]


def test_the_console_is_the_same_sign_in_told_which_account() -> None:
    assert way("claude", "console").argv == ("claude", "auth", "login", "--console")
    assert login.asked(way("claude", "console"), {}) == []


@pytest.mark.parametrize(
    ("name", "answers", "written"),
    [
        (
            "bedrock-gateway",
            {"ANTHROPIC_BEDROCK_BASE_URL": "https://gw.invalid", "ANTHROPIC_AUTH_TOKEN": "t"},
            {
                "ANTHROPIC_BEDROCK_BASE_URL": "https://gw.invalid",
                "ANTHROPIC_AUTH_TOKEN": "t",
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1",
            },
        ),
        (
            "vertex-gateway",
            {
                "ANTHROPIC_VERTEX_BASE_URL": "https://gw.invalid",
                "ANTHROPIC_AUTH_TOKEN": "t",
                "ANTHROPIC_VERTEX_PROJECT_ID": "p",
            },
            {
                "ANTHROPIC_VERTEX_BASE_URL": "https://gw.invalid",
                "ANTHROPIC_AUTH_TOKEN": "t",
                "ANTHROPIC_VERTEX_PROJECT_ID": "p",
                "CLOUD_ML_REGION": "us-east5",
                "CLAUDE_CODE_USE_VERTEX": "1",
                "CLAUDE_CODE_SKIP_VERTEX_AUTH": "1",
            },
        ),
        (
            "bedrock-key",
            {"AWS_BEARER_TOKEN_BEDROCK": "k"},
            {
                "AWS_BEARER_TOKEN_BEDROCK": "k",
                "AWS_REGION": "us-east-1",
                "CLAUDE_CODE_USE_BEDROCK": "1",
            },
        ),
        (
            "mantle",
            {"AWS_PROFILE": "work"},
            {
                "AWS_PROFILE": "work",
                "AWS_REGION": "us-east-1",
                "CLAUDE_CODE_USE_MANTLE": "1",
            },
        ),
        (
            "foundry",
            {"ANTHROPIC_FOUNDRY_RESOURCE": "mine", "ANTHROPIC_FOUNDRY_API_KEY": "k"},
            {
                "ANTHROPIC_FOUNDRY_RESOURCE": "mine",
                "ANTHROPIC_FOUNDRY_API_KEY": "k",
                "CLAUDE_CODE_USE_FOUNDRY": "1",
            },
        ),
        (
            "aws",
            {"ANTHROPIC_AWS_WORKSPACE_ID": "wrkspc_x", "ANTHROPIC_AWS_API_KEY": "k"},
            {
                "ANTHROPIC_AWS_WORKSPACE_ID": "wrkspc_x",
                "AWS_REGION": "us-east-1",
                "ANTHROPIC_AWS_API_KEY": "k",
                "CLAUDE_CODE_USE_ANTHROPIC_AWS": "1",
            },
        ),
        (
            "google-cloud",
            {
                "ANTHROPIC_GOOGLE_CLOUD_PROJECT": "p",
                "ANTHROPIC_GOOGLE_CLOUD_WORKSPACE_ID": "wrkspc_x",
            },
            {
                "ANTHROPIC_GOOGLE_CLOUD_PROJECT": "p",
                "ANTHROPIC_GOOGLE_CLOUD_LOCATION": "global",
                "ANTHROPIC_GOOGLE_CLOUD_WORKSPACE_ID": "wrkspc_x",
                "CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD": "1",
            },
        ),
        (
            "wif",
            {
                "ANTHROPIC_FEDERATION_RULE_ID": "fdrl_x",
                "ANTHROPIC_ORGANIZATION_ID": "o",
                "ANTHROPIC_SERVICE_ACCOUNT_ID": "svac_x",
                "ANTHROPIC_IDENTITY_TOKEN_FILE": "/var/run/token",
            },
            {
                "ANTHROPIC_FEDERATION_RULE_ID": "fdrl_x",
                "ANTHROPIC_ORGANIZATION_ID": "o",
                "ANTHROPIC_SERVICE_ACCOUNT_ID": "svac_x",
                "ANTHROPIC_IDENTITY_TOKEN_FILE": "/var/run/token",
            },
        ),
    ],
)
def test_each_way_writes_down_what_it_was_told_and_the_switch_it_needs(
    house: Path, name: str, answers: dict[str, str], written: dict[str, str]
) -> None:
    chosen = way("claude", name)
    assert login.asked(chosen, answers) == []

    provider = login.make("claude", name, chosen, answers)

    assert dict(provider.env) == written
    assert provider.args == ()


def test_every_switch_a_way_sets_is_one_a_turn_is_hushed_of() -> None:
    """A switch left in a shell would move every other account's turn onto that cloud."""
    claude = backends.named("claude")
    assert claude is not None
    for one in claude.ways:
        for name, _ in one.sets:
            assert name in claude.ambient, (one.name, name)


def test_no_secret_reaches_the_command_line() -> None:
    """A provider's values reach a turn as its environment, never as its arguments."""
    claude = backends.named("claude")
    assert claude is not None
    for one in claude.ways:
        assert one.args == ()
        assert not any(asked.secret and not asked.keep for asked in one.asks)
