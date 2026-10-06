"""That the patches an agent's runtime is started with actually boot.

A unit test can say which rows `_composed` wrote; only the bundled runtime can say whether
those are rows its profile carries and whether the services left mounted still resolve. Cordis
does not fail a missing dependency loudly at load -- an entry whose service nobody provides is
left `pending` and the boot fails at the end, so a composition that is one row short of working
looks exactly like one that works until it is started.

This is why it is a system test and not a unit one: it needs the real
`deepseek-harness-runtime` executable on this machine. It spends no tokens and talks to no
model -- a harness that has started is a harness that loaded its plugins, and the key it is
handed is a fake -- so it is not behind `--run-agents`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import DshAgentConfig
from hmz.coganchor.agents.dsh import _GATEWAYS, _composed

pytest.importorskip(
    "deepseek_harness_runtime",
    reason="the [dsh] extra is not installed in this Python environment",
)

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = DshAgentConfig(model="deepseek-chat", effort="high")


def _boots(
    patch: str,
    where: Path,
    provider: str = "deepseek-official",
    env: dict[str, str] | None = None,
    effort: str | None = "high",
) -> None:
    """Starts the bundled runtime with one patch and puts it straight back down.

    Started as the driver starts it -- the SDK's own profile, the patch over it, a home of
    its own and the one permission preset the driver takes -- through the SDK's public
    launch, which adds the same profile, patch and home arguments the driver does.

    Args:
      patch: The patch, as `_composed` wrote it.
      where: A directory of this test's own for the runtime to work and keep its home in.
      provider: The adapter route the session is opened on, which the runtime refuses at
        the handshake where nothing in the composition registered it.
      env: What the account would add to the runtime's environment.
      effort: The reasoning level the handshake carries, which the route validates.

    Raises:
      Exception: Whatever the SDK raises for a runtime that would not come up, which for a
        patch naming a row the profile does not carry, or leaving a service nobody provides,
        is the boot's own message with the failing entry in it.
    """
    harness = pytest.importorskip("deepseek_harness")
    written = where / "humanize.patch.yml"
    written.write_text(patch, encoding="utf-8")
    started = harness.DeepSeekHarness(
        provider=provider,
        model=CONFIG.model,
        reasoning_effort=effort,
        cwd=str(where),
        runtime_cwd=str(where),
        dsh_home=str(where / "home"),
        profile="sdk",
        patches=(str(written),),
        # A key it never spends: the runtime resolves one as it boots and a turn is what
        # would have to be answered, which this test does not take.
        env={
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DSH_PERMISSION_MODE": "danger-full-access",
            **(env or {}),
        },
        request_timeout_seconds=120.0,
        initialize_timeout_seconds=120.0,
    )
    try:
        started.start()
    finally:
        started.close()


def test_an_agent_at_every_default_boots(tmp_path: Path) -> None:
    """The profile with humanize's defaults over it: an uncompressed session log."""
    _boots(_composed(CONFIG), tmp_path)


def test_an_agent_with_everything_switched_off_still_boots(tmp_path: Path) -> None:
    """No goals, no compaction and no web: every row the patch can unmount, unmounted.

    `dsh-base` rows inject each other, so a row switched off that another still waits on
    leaves that one pending, and the boot fails at the end rather than at the row.
    """
    quiet = replace(CONFIG, goals=False, compaction=False, web_search=False)
    _boots(_composed(quiet), tmp_path)


def test_an_agent_under_a_key_account_boots_without_this_machines_settings(
    tmp_path: Path,
) -> None:
    """The settings document unmounted, which nothing else in the profile may depend on."""
    _boots(_composed(CONFIG, "key"), tmp_path)


@pytest.mark.parametrize("effort", ["max", "high", "low", "off"])
def test_every_rung_of_dshs_ladder_is_one_the_adapter_takes(
    effort: str, tmp_path: Path
) -> None:
    """The handshake validates the level against the route.

    So a rung the adapter has no word for would be a runtime that never comes up.
    """
    _boots(_composed(CONFIG), tmp_path, effort=effort)


@pytest.mark.parametrize("way", sorted(_GATEWAYS))
def test_a_gateway_account_is_composed_onto_a_route_the_runtime_registers(
    way: str, tmp_path: Path
) -> None:
    """pi-ai's adapter, its one route and the web less its search, all loaded together.

    The route's protocol, base URL and model are read off the environment as the runtime
    boots, and a route it cannot serve is refused there -- so this is where a protocol name
    pi-ai stopped taking, or a catalogue route it stopped shipping, would show.
    """
    composed = _composed(replace(CONFIG, web_search=True), way)

    _boots(
        composed,
        tmp_path,
        provider=_GATEWAYS[way][0],
        env={
            "DEEPSEEK_BASE_URL": "https://gateway.invalid/v1",
            "DSH_GATEWAY_API": "openai-responses",
        },
        effort=None,
    )
