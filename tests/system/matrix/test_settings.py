"""The regression matrix's rows about `/settings`: what is added there, and what it then does.

Each is about no one CLI, and is run once, in the column `any`. The interface is driven by the
Textual pilot, as `tests/integration/tui` drives it -- but what is on the far side of it is the
real thing: an account made on the one form of the accounts page takes a real turn, and a
machine brought in on the runtimes page is a real ssh host and this machine's docker
daemon, asked for real what they have.

The interface is opened with the fixtures `tests/tui` opens every one with, imported here for
this file alone rather than for the directory: the other rows of the matrix drive real hosts,
which those would take away.
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Any, cast

import pytest
from textual import events
from textual.widgets import OptionList

from hmz.tui import Humanize
from hmz.tui.pick import (
    _ACT_IMPORTS,
    _CHECKS,
    _DONE,
    Docking,
    Importing,
    Machine,
    Providers,
)
from tests.integration.tui.test_app import into_settings, onto
from tests.integration.tui.test_providers import _adds, _answers, _chooses, _writes
from tests.integration.tui.test_runtimes import _done, _drawn, _opens, _under
from tests.matrix import places
from tests.matrix.cells import feature
from tests.tui.fixtures import (  # noqa: F401
    _elsewhere,  # pyright: ignore[reportUnusedImport]
    _fetches_nothing,  # pyright: ignore[reportUnusedImport]
    _linked_to_nothing,  # pyright: ignore[reportUnusedImport]
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

    from tests.flows.sshd import Box

#: The account the accounts page makes, out of the one this machine keeps for DeepSeek's
#: gateway, and the cheapest model that gateway serves.
MADE = "matrix-made"
MODEL = "nvidia/deepseek-ai/deepseek-v4-flash"


#: How long a real CLI or a real machine is given to answer what the page asks it.
PATIENCE = 180.0


async def _pastes(app: Humanize, driver: Pilot[None], held: str, said: str) -> None:
    """Pastes a value onto one row of a form and keeps it, as pasting a secret in does."""
    await onto(app, driver, held)
    app.screen.query_one("#choices", OptionList).post_message(events.Paste(said))
    await driver.pause()
    await driver.press("enter")
    await driver.pause()


async def _says(app: Humanize, driver: Pilot[None], *said: str) -> str:
    """Waits for the line under the page to say one of some things, and answers it.

    Longer than `until` waits, and loud rather than silent when it runs out: what is being
    waited for is a real CLI or a real machine answering, not the interface redrawing.
    """
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        now = _under(app)
        if any(one in now for one in said):
            return now
        await driver.pause(0.2)
    raise AssertionError(f"the page never said any of {said}: it says {_under(app)!r}")


@feature(once=True, group="dsh", timeout=600)
async def test_settings_accounts(asking: None) -> None:
    """An account added on the one form of `/settings accounts` is one a real turn runs as.

    DeepSeek's `gateway` way, filled in with what this machine's own `dsh` account for the
    gateway holds: the form lands it in the store, the page asks it what it runs, and a turn
    is taken under it.
    """
    del asking
    from hmz.sdk import Hmz

    if not places.installed("dsh"):
        pytest.skip("environment: dsh is not installed here")
    try:
        theirs = cast(
            "dict[str, Any]",
            json.loads(
                (places.MACHINE / "dsh" / "nvidia" / "provider.json").read_text()
            ),
        )
    except (OSError, ValueError):
        pytest.skip("environment: this machine keeps no dsh account for a gateway")
    held = cast("dict[str, str]", theirs.get("env") or {})
    url, key = held.get("DEEPSEEK_BASE_URL", ""), held.get("DEEPSEEK_API_KEY", "")
    if not (url and key):
        pytest.skip("environment: this machine's dsh account names no gateway and key")
    accounts = Hmz().accounts
    try:
        app = Humanize()
        async with app.run_test() as driver:
            await into_settings(app, driver, "accounts")
            await _adds(app, driver)
            await _chooses(app, driver, "cli", "dsh")
            await _chooses(app, driver, "way", "gateway")
            await _writes(app, driver, "name", *MADE)
            await _pastes(app, driver, "DEEPSEEK_BASE_URL", url)
            await _pastes(app, driver, "DEEPSEEK_API_KEY", key)
            await _answers(app, driver)

            await until(lambda: isinstance(app.screen, Providers), driver)
            await until(lambda: accounts.find("dsh", MADE) is not None, driver)
            # Asked what it runs, for real, and it said.
            said = await _says(app, driver, "dsh supports", "could not get models for")
            assert re.search(rf"dsh supports \d+ models? as {MADE}", said), said

        made = accounts.find("dsh", MADE)
        assert made is not None
        assert made.way == "gateway"
        assert dict(made.env) == {"DEEPSEEK_BASE_URL": url, "DEEPSEEK_API_KEY": key}
        refused = places._answers(places.Place("dsh", MADE, MODEL, "off"))
        assert not refused, refused
    finally:
        # Somebody's live credential, in a directory pytest keeps for three runs.
        accounts.remove("dsh", MADE)
    assert accounts.find("dsh", MADE) is None


@feature(once=True, timeout=600)
async def test_settings_runtimes(
    ssh_box: Box, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ssh host imported and a docker daemon added on `/settings runtimes` answer.

    The host is imported from the ssh config it is named in -- the page's own import, reading
    it as `ssh -G` does -- and checked from its own menu; the daemon is docker's default here,
    added on the one form and asked what it has as it lands. Both are then in the SDK's store
    and answer when it checks them. Nothing of `~/.ssh` is read: the home is the test's, and
    the `ssh` that knows the host is taken off `PATH`, so only what was saved reaches it.
    """
    from hmz.coganchor.machines.store import IMPORTED, DockerRuntime, SSHRuntime
    from hmz.sdk import Hmz

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    ssh_box.unlisted(monkeypatch)
    config = str(ssh_box.config)
    app = Humanize()
    async with app.run_test() as driver:
        await into_settings(app, driver, "runtimes")
        sheet = app.screen
        await _opens(app, driver, _ACT_IMPORTS, Importing)
        form = cast("Importing", app.screen)
        await onto(app, driver, "config")
        await driver.press(*config, "enter")
        await until(lambda: form._read == config and not form._reading, driver)
        assert form._on(ssh_box.alias), _drawn(app)
        await onto(app, driver, _DONE)
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)
        await until(lambda: f"imported {ssh_box.alias}" in _under(app), driver)

        # Checked from its own menu, down the road a run takes.
        await onto(app, driver, f"ssh/{ssh_box.alias}")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Machine), driver)
        await onto(app, driver, _CHECKS)
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)
        host = f"ssh/{ssh_box.alias}"
        said = await _says(app, driver, f"{host} answers", f"{host} could not")
        assert f"{host} answers: home /root" in said, said

        await _opens(app, driver, "docker", Docking)
        name = cast("Docking", app.screen)._typed_in["name"]
        await _done(app, driver)
        await until(lambda: app.screen is sheet, driver)
        docked = f"docker/{name}"
        said = await _says(app, driver, f"{docked} answers", f"{docked} could not")
        assert f"{docked} answers: docker " in said, said

    envs = Hmz().runtimes
    host = envs.find("ssh", ssh_box.alias)
    assert isinstance(host, SSHRuntime), host
    assert (host.made, host.alias) == (IMPORTED, ssh_box.alias), host
    daemon = envs.find("docker", name)
    assert isinstance(daemon, DockerRuntime), daemon
    assert daemon.endpoint == "local", daemon
    for one in (host, daemon):
        checked = envs.check(one)
        assert checked.reached, checked
    assert not (tmp_path / "home" / ".ssh").exists()
