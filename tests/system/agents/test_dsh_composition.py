"""That the composition an agent which may search the web is started from actually boots.

A unit test can say which plugin names `_composed` wrote; only the bundled runtime can say
whether those names are plugins it carries and whether the services they inject resolve. Cordis
does not fail a missing dependency loudly at load -- an entry whose service nobody injects is
left `pending` and the boot fails at the end with `1 entry did not activate`, so a composition
that is one plugin short of working looks exactly like one that works until it is started.

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
from hmz.coganchor.agents.dsh import _WEB, _composed

if TYPE_CHECKING:
    from pathlib import Path

#: A composition is written to a file and pointed at with `$DSH_CORDIS_CONFIG`, which is what
#: the driver does too: the SDK injects its own bundled default only for a launch whose
#: arguments it resolved itself, and this one resolves them here.
CONFIG = DshAgentConfig(model="deepseek-chat", effort="high")


def _boots(cordis: str, where: Path) -> None:
    """Starts the bundled runtime from one composition and puts it straight back down.

    Args:
      cordis: The composition, as `_composed` wrote it.
      where: A directory of this test's own for the runtime to work and keep sessions in.

    Raises:
      Exception: Whatever the SDK raises for a runtime that would not come up, which for a
        composition naming a plugin the build does not carry is the boot's own
        `... did not activate` message with the pending entry in it.
    """
    runtime = pytest.importorskip(
        "deepseek_harness_runtime",
        reason="the [dsh] extra is not installed in this Python environment",
    )
    harness = pytest.importorskip("deepseek_harness")
    written = where / "cordis.yml"
    written.write_text(cordis, encoding="utf-8")
    started = harness.DeepSeekHarness(
        provider="deepseek-official",
        model=CONFIG.model,
        cwd=str(where),
        runtime_cwd=str(where),
        session_root=str(where / "sessions"),
        cordis=str(written),
        # A key it never spends: the runtime resolves one as it boots and a turn is what
        # would have to be answered, which this test does not take.
        env={"DEEPSEEK_API_KEY": "not-a-real-key", "HMZ_DSH_EFFORT": "high"},
        launch_args_override=tuple(runtime.resolve_bundled_launch_args()),
        request_timeout_seconds=120.0,
    )
    try:
        started.start()
    finally:
        started.close()


def test_the_web_plugins_an_agent_that_may_search_is_composed_with_are_real(
    tmp_path: Path,
) -> None:
    """Every one of the four, and the services they inject resolving into each other.

    The pin admits any `0.1.x` and only 0.1.1rc1 was read, so a release that renamed or
    dropped one of these would otherwise turn every dsh turn into a runtime that will not
    start -- and it would do it at the first turn of a run rather than here.
    """
    searching = _composed(replace(CONFIG, web_search=True))
    assert all(plugin["name"] in searching for plugin in _WEB)

    _boots(searching, tmp_path)


def test_an_agent_told_not_to_search_is_composed_without_them_and_still_boots(
    tmp_path: Path,
) -> None:
    """The half this backend is told with, and the half nothing downstream may break."""
    quiet = _composed(replace(CONFIG, web_search=False))
    assert not any(plugin["name"] in quiet for plugin in _WEB)

    _boots(quiet, tmp_path)
