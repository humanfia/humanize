"""What Cursor Agent settles before a turn is taken: the id it spells, and what it refuses.

A rung is no parameter of a Cursor model -- it is part of the id -- so what a flow asked for
becomes a name, and a name this account does not list is refused where it is written rather
than spent as a turn. None of that needs the CLI, so none of it is run here: these are calls
into the driver and the account it was told about, and nothing is launched.

Driving the same backend against a stand-in that prints what it prints is next door, in
`tests/integration/agents/test_cursor.py`.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import CursorAgent, CursorAgentConfig
from hmz.coganchor.agents.cursor import _COMMAND, spelled
from hmz.coganchor.fence import ALL, NONE, READ, Fence
from tests.agents import cursors

if TYPE_CHECKING:
    from pathlib import Path


def test_the_cli_is_named_by_what_it_is_installed_as() -> None:
    """`agent` is a name anything could have taken; `cursor-agent` can only be this one."""
    profile = backends.named("cursor-agent")
    assert profile is not None
    assert profile.name == "cursor-agent"
    # And the product's own name is not a spelling of it: nothing on a PATH is `cursor`, so
    # a line that says it is a line to correct rather than one to guess at.
    assert backends.named("cursor") is None
    # The word the driver spawns is that same word. It is written in two places, as every
    # other driver's is, and this is what holds the two together.
    assert profile.name == _COMMAND


def test_how_hard_it_thinks_is_written_into_the_models_own_id() -> None:
    """Cursor has no flag for a rung and no bracket either: `gpt-5.2-low` is the whole of it."""
    assert (
        spelled("gpt-5.2", "low", fast=False, listed=cursors.ACCOUNT) == "gpt-5.2-low"
    )
    # A name that has already answered is not answered over: `gpt-5.2-low-high` is nobody's
    # id, and which of the two a flow meant is the model's own word rather than the effort's.
    assert (
        spelled("gpt-5.2-low", "high", fast=False, listed=cursors.ACCOUNT)
        == "gpt-5.2-low"
    )
    # A model spelled with its own bracket meant what it said. The parameters are refused by
    # this account and documented by the CLI, and which accounts still take them is not this
    # driver's to decide -- so what was written goes out as it was written.
    assert (
        spelled(
            "claude-opus-4-8[context=1m]", "high", fast=True, listed=cursors.ACCOUNT
        )
        == "claude-opus-4-8[context=1m]"
    )


def test_the_faster_service_is_the_same_suffix_and_the_default_writes_nothing() -> None:
    """`composer-2.5-fast` is that model served quickly, which is the only spelling it has.

    And the default tier writes nothing at all rather than the opposite of it, which is what
    lets a model that is nothing but a name -- an id belonging to an endpoint of somebody
    else's -- arrive spelled exactly as it was given.
    """
    assert (
        spelled("composer-2.5", "", fast=True, listed=cursors.ACCOUNT)
        == "composer-2.5-fast"
    )
    assert (
        spelled("composer-2.5", "", fast=False, listed=cursors.ACCOUNT)
        == "composer-2.5"
    )
    assert (
        spelled("external/model-id", "", fast=False, listed=()) == "external/model-id"
    )


def test_a_rung_this_account_has_no_id_for_is_refused_rather_than_sent() -> None:
    """`gpt-5.2-medium` is not a model, and the turn it is sent on is a turn Cursor refuses.

    Which is the whole of the bug this replaced: humanize built an id nobody lists and spent
    a turn finding out. What it does list is named in the refusal, that being the one thing
    whoever wrote the effort needs to know.
    """
    with pytest.raises(ValueError, match=r"lists no gpt-5.2-medium"):
        spelled("gpt-5.2", "medium", fast=False, listed=cursors.ACCOUNT)
    with pytest.raises(ValueError, match=r"gpt-5.2-low, gpt-5.2-high, gpt-5.2-xhigh"):
        spelled("gpt-5.2", "medium", fast=False, listed=cursors.ACCOUNT)
    # A model with no rung form at all runs at whatever Cursor gives it, and says so rather
    # than guessing: it is named with no effort, and an effort against it is refused.
    with pytest.raises(ValueError, match="itself alone"):
        spelled("auto", "low", fast=False, listed=cursors.ACCOUNT)
    # The same for a service this account does not serve that model on.
    with pytest.raises(ValueError, match=r"lists no gpt-5.2-fast"):
        spelled("gpt-5.2", "", fast=True, listed=cursors.ACCOUNT)


def test_a_rung_the_account_has_no_id_for_is_refused_where_the_agent_is_made() -> None:
    """Where every other setting this backend cannot express is refused, and for one reason.

    A flow that names one is stopped before it spends a turn finding out, which is what the
    bracket never was: that one was built, sent, and answered `Cannot use this model`.
    """
    cursors.kept(cursors.ACCOUNT)

    with pytest.raises(ValueError, match=r"lists no gpt-5.2-medium"):
        CursorAgent(CursorAgentConfig(model="gpt-5.2", effort="medium"))

    # And the ones it does list are made without a word, at the rung and at no rung at all.
    CursorAgent(CursorAgentConfig(model="gpt-5.2", effort="low"))
    CursorAgent(CursorAgentConfig(model="composer-2.5", effort=""))


def test_a_catalogue_nobody_has_asked_for_refuses_nothing() -> None:
    """An empty list is a question nobody put rather than an account that said no.

    An account nobody has asked yet has no list at all and one asked before the vendor moved
    has the wrong one, and neither is a reason to withhold a rung a flow asked for: the id
    goes out as it was built and Cursor answers it with its own list.
    """
    assert spelled("gpt-5.2", "medium", fast=False, listed=()) == "gpt-5.2-medium"
    # And the same for a model this account's list says nothing about, which is a list taken
    # before the vendor moved rather than a model nobody may name.
    assert (
        spelled("gpt-5.9", "medium", fast=False, listed=cursors.ACCOUNT)
        == "gpt-5.9-medium"
    )


def test_web_search_cannot_be_switched_off_and_is_refused_rather_than_ignored() -> None:
    """Its own command line takes no tool away, and a setting that lies is worse than none."""
    from dataclasses import replace

    with pytest.raises(ValueError, match="no way of being told"):
        CursorAgent(replace(cursors.CURSOR, web_search=False))


def test_a_root_that_is_not_one_is_refused_where_it_is_written() -> None:
    """`--add-dir ''` is a turn Cursor refuses, and this is where that is found out."""
    from dataclasses import replace

    with pytest.raises(ValueError, match="add_dirs"):
        replace(cursors.CURSOR, add_dirs=("  ",))


def _able(*, net: bool) -> bool:
    del net
    return True


def test_a_fence_is_held_from_outside_with_its_sign_in_to_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Its own sandbox holds its shell commands and not itself, so all of it is held outside.

    And the directory its Linux sign-in is kept in is let be written, a token refreshed
    mid-turn being written back there, whatever the fence says of the home around it.
    """
    from dataclasses import replace

    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CURSOR_CONFIG_DIR", raising=False)
    home = tmp_path / "home"
    fence = Fence.of(
        local=ALL,
        user=READ,
        system=NONE,
        online=True,
        workdir=tmp_path / "work",
        home=home,
    )
    agent = CursorAgent(replace(cursors.CURSOR, fence=fence))

    argv = agent.spawned(["cursor-agent", "--print"])

    assert argv[:5] == [sys.executable, "-Pm", "hmz", "internal", "fence"]
    assert argv[argv.index("--") + 1 :] == ["cursor-agent", "--print"]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert policy.online
    assert policy.allows(home / ".config/cursor/auth.json", write=True)
    assert policy.allows(home / ".cursor/cli-config.json", write=True)
    assert not policy.allows(home / ".bashrc", write=True)
    assert not policy.allows("/etc/machine-id")
    # Only its sign-in is added: a fence that grants everything still puts nothing around it.
    everything = Fence.of(
        local=ALL, user=ALL, system=ALL, online=True, workdir=tmp_path, home=home
    )
    assert CursorAgent(replace(cursors.CURSOR, fence=everything)).spawned(
        ["cursor-agent"]
    ) == ["cursor-agent"]


@pytest.mark.parametrize("scopes", [(ALL, ALL, ALL), (ALL, READ, NONE)])
def test_a_fence_that_cuts_the_network_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, scopes: tuple[str, str, str]
) -> None:
    """Its web search and fetch run on Cursor's servers, through the hosts its model is at.

    So a proxy that lets the model through lets them through too, and nothing a driver owns
    switches them off: a permission granting no network is refused, whatever it says of the
    disk, rather than run with the web still in reach -- where the agent is made, and where
    one already made is set up again.
    """
    from dataclasses import replace

    from hmz.coganchor.agents import Unfenced

    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    local, user, system = scopes
    offline = Fence.of(
        local=local,
        user=user,
        system=system,
        online=False,
        workdir=tmp_path,
        home=tmp_path / "home",
    )

    with pytest.raises(Unfenced, match="grant it online ALL"):
        CursorAgent(replace(cursors.CURSOR, fence=offline))
    agent = CursorAgent(cursors.CURSOR)
    with pytest.raises(Unfenced, match="web search and web fetch"):
        agent.reconfigure(replace(cursors.CURSOR, fence=offline))
    # A fence that is let reach the network is not.
    CursorAgent(replace(cursors.CURSOR, fence=replace(offline, online=True)))


def test_a_provider_sign_in_lands_where_the_cli_reads_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On Linux `auth.json` is under `$XDG_CONFIG_HOME/cursor`; on macOS under `~/.cursor`.

    Neither is under the home `CURSOR_CONFIG_DIR` moves, so a provider pointing only that
    home's `auth.json` elsewhere would leave the machine's own sign-in to answer its turns and
    let its login overwrite it. Both are pointed at the provider's own copy.
    """
    from hmz.coganchor import providers

    house = tmp_path / "house"
    monkeypatch.setenv("HOME", str(house))
    monkeypatch.setenv("CURSOR_CONFIG_DIR", str(tmp_path / "moved"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    provider = providers.add(_COMMAND, "mine")

    swaps = dict(provider.swaps())

    assert swaps[str(tmp_path / "xdg" / "cursor" / "auth.json")] == str(
        provider.at / "config" / "cursor" / "auth.json"
    )
    assert swaps[str(house / ".cursor" / "auth.json")] == str(
        provider.at / "user" / ".cursor" / "auth.json"
    )
    assert swaps[str(tmp_path / "moved" / "cli-config.json")] == str(
        provider.at / "home" / "cli-config.json"
    )
    assert str(tmp_path / "moved" / "auth.json") not in swaps
