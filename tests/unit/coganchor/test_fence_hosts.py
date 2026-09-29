"""Which hosts the fence's proxy passes, decided without a socket."""

from __future__ import annotations

from hmz.coganchor.fence import permits


def test_an_exact_entry_passes_that_host_and_no_other() -> None:
    assert permits(["api.anthropic.com"], "api.anthropic.com", 443)
    assert not permits(["api.anthropic.com"], "anthropic.com", 443)
    assert not permits(["api.anthropic.com"], "evil-api.anthropic.com", 443)
    assert not permits(["api.anthropic.com"], "api.anthropic.com.evil.example", 443)


def test_case_and_a_trailing_dot_do_not_matter_on_either_side() -> None:
    assert permits(["API.Anthropic.com."], "api.anthropic.com", 443)
    assert permits(["api.anthropic.com"], "Api.ANTHROPIC.com.", 443)


def test_a_wildcard_passes_names_under_its_suffix_but_not_the_suffix() -> None:
    allowed = ["*.googleapis.com"]
    assert permits(allowed, "oauth2.googleapis.com", 443)
    assert permits(allowed, "a.b.googleapis.com", 443)
    assert not permits(allowed, "googleapis.com", 443)
    assert not permits(allowed, "evilgoogleapis.com", 443)
    assert not permits(allowed, "googleapis.com.evil.example", 443)


def test_an_entry_with_no_port_passes_only_the_usual_ones() -> None:
    assert permits(["api.anthropic.com"], "api.anthropic.com", 80)
    assert not permits(["api.anthropic.com"], "api.anthropic.com", 22)
    assert permits(["api.anthropic.com"], "api.anthropic.com", 22, ports=[22])


def test_an_entry_with_a_port_passes_that_port_alone() -> None:
    allowed = ["gw.example:8443"]
    assert permits(allowed, "gw.example", 8443)
    assert not permits(allowed, "gw.example", 443)
    assert permits(["[::1]:8443"], "::1", 8443)
    assert not permits(["[::1]:8443"], "::1", 443)


def test_an_ip_literal_passes_only_where_that_address_is_listed() -> None:
    assert not permits(["api.anthropic.com", "*.anthropic.com"], "160.79.104.10", 443)
    assert permits(["127.0.0.1"], "127.0.0.1", 443)
    assert permits(["::1"], "[::1]", 443)
    assert permits(["[0:0::1]"], "::1", 443)
    assert not permits(["*.0.0.1"], "127.0.0.1", 443)


def test_nothing_is_passed_by_an_empty_list_or_to_an_empty_host() -> None:
    assert not permits([], "api.anthropic.com", 443)
    assert not permits(["*."], "", 443)
    assert not permits(["", "*"], "api.anthropic.com", 443)
