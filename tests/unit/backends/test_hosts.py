"""The hosts each backend may still reach when a flow grants it no network."""

from __future__ import annotations

from hmz.coganchor import backends
from hmz.coganchor.backends import PROFILES, UNKNOWN, reachable


def _profile(name: str) -> backends.Profile:
    profile = backends.named(name)
    assert profile is not None
    return profile


def test_every_backend_names_the_hosts_it_cannot_run_without() -> None:
    for profile in PROFILES:
        assert profile.hosts, profile.name
        for host in profile.hosts:
            assert host == host.lower().rstrip("."), (profile.name, host)
            assert "/" not in host, (profile.name, host)
            assert ":" not in host, (profile.name, host)
            assert "*" not in host.removeprefix("*."), (profile.name, host)


def test_with_nothing_pointed_elsewhere_the_hosts_are_the_profiles_own() -> None:
    for profile in PROFILES:
        assert reachable(profile, {}) == profile.hosts


def test_a_backend_nothing_is_known_about_may_reach_nothing() -> None:
    assert reachable(UNKNOWN, {"ANTHROPIC_BASE_URL": "https://gw.example"}) == ()


def test_the_endpoint_an_account_points_at_is_added() -> None:
    claude = _profile("claude")
    hosts = reachable(claude, {"ANTHROPIC_BASE_URL": "https://GW.Example.com./v1"})
    assert hosts == (*claude.hosts, "gw.example.com")


def test_a_port_the_account_names_is_kept_with_its_host() -> None:
    claude = _profile("claude")
    hosts = reachable(claude, {"ANTHROPIC_BASE_URL": "https://gw.example:8443/v1"})
    assert hosts[-1] == "gw.example:8443"
    hosts = reachable(claude, {"ANTHROPIC_BASE_URL": "http://[::1]:4000"})
    assert hosts[-1] == "[::1]:4000"


def test_every_spelling_of_where_a_backend_goes_is_followed() -> None:
    qwen = _profile("qwen")
    assert "gw.example" in reachable(qwen, {"OPENAI_API_BASE": "https://gw.example/v1"})
    grok = _profile("grok")
    assert "id.example" in reachable(grok, {"GROK_OIDC_ISSUER": "https://id.example"})
    cursor = _profile("cursor-agent")
    assert "c.example" in reachable(
        cursor, {"CURSOR_API_ENDPOINT": "https://c.example"}
    )


def test_the_endpoint_an_mcode_gateway_was_added_with_is_followed() -> None:
    """Which the CLI never reads -- it is in `config.yaml` -- but the account keeps."""
    mcode = _profile("mcode")
    hosts = reachable(mcode, {"MCODE_GATEWAY_URL": "https://gw.example:8443/v1"})
    assert hosts == (*mcode.hosts, "gw.example:8443")


def test_base_urls_and_oauth_hosts_among_the_ambient_are_added() -> None:
    kimi = _profile("kimi")
    hosts = reachable(
        kimi,
        {
            "KIMI_BASE_URL": "https://models.example/v1",
            "KIMI_OAUTH_HOST": "auth.example",
            "KIMI_API_KEY": "https://not-a-host.example",
        },
    )
    assert "models.example" in hosts
    assert "auth.example" in hosts
    assert "not-a-host.example" not in hosts


def test_a_host_already_listed_is_listed_once() -> None:
    claude = _profile("claude")
    first = claude.hosts[0]
    assert reachable(claude, {"ANTHROPIC_BASE_URL": f"https://{first}"}) == claude.hosts


def test_an_empty_or_unreadable_value_adds_nothing() -> None:
    claude = _profile("claude")
    for value in ("", "   ", "https://", "http://[::1"):
        assert reachable(claude, {"ANTHROPIC_BASE_URL": value}) == claude.hosts


def test_a_cloud_switched_onto_adds_its_hosts_in_the_accounts_region() -> None:
    claude = _profile("claude")
    bedrock = reachable(
        claude, {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "eu-west-1"}
    )
    assert "bedrock-runtime.eu-west-1.amazonaws.com" in bedrock
    vertex = reachable(claude, {"CLAUDE_CODE_USE_VERTEX": "1"})
    assert "us-east5-aiplatform.googleapis.com" in vertex
    assert reachable(claude, {"CLAUDE_CODE_USE_BEDROCK": ""}) == claude.hosts
    foundry = {"CLAUDE_CODE_USE_FOUNDRY": "1", "ANTHROPIC_FOUNDRY_RESOURCE": "mine"}
    assert "mine.services.ai.azure.com" in reachable(claude, foundry)
    # A Foundry account with no resource, and one whose resource is not one DNS label,
    # spells no host at all rather than one of the value's own choosing.
    assert reachable(claude, {"CLAUDE_CODE_USE_FOUNDRY": "1"}) == claude.hosts
    foundry["ANTHROPIC_FOUNDRY_RESOURCE"] = "evil.example/"
    assert reachable(claude, foundry) == claude.hosts
    foundry["ANTHROPIC_FOUNDRY_BASE_URL"] = "https://res.example/anthropic"
    assert reachable(claude, foundry)[-1] == "res.example"
    # A switch that is not the backend's own switches nothing.
    codex = _profile("codex")
    assert reachable(codex, {"CLAUDE_CODE_USE_BEDROCK": "1"}) == codex.hosts
