"""The machines a flow's environments go on: saved on `/settings`, and chosen on `/flow`.

An ssh host or a docker daemon is saved on the environments page of `/settings` -- typed in on
one form, or imported from an ssh config -- and checked as it lands. What reaches a machine is
a stand-in here: `ssh` answers `-G` as ssh does and runs what it is told on this machine, and
`docker` answers `info` with what a machine with two GPUs said. Both are the ones
`tests/integration/machines` writes, so the page is checked against what the store is.
"""

from __future__ import annotations

import json
import os
import unittest.mock
from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Label, OptionList

from hmz.coganchor.backends import Model
from hmz.coganchor.machines import store
from hmz.coganchor.machines.store import DockerProvider, SSHProvider
from hmz.flows import EnvBackendKind
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import (
    _ADD,
    _BUDGET,
    _CHECKS,
    _CORRECTS,
    _DETECTS,
    _DOCKS,
    _DONE,
    _IMPORTS,
    _SAVE,
    _SEARCH,
    _TAKES_AWAY,
    _UNSAVED,
    Adjusts,
    Configures,
    Docking,
    Flows,
    Hosting,
    Hosts,
    Importing,
    Machine,
    Placing,
    Unsaved,
)
from tests.integration.machines.test_env_providers import _DOCKER, _INFO, _SSH
from tests.integration.tui.test_app import changes, ids, into_settings, onto, rows
from tests.stubs import written
from tests.tui.fixtures import until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: One installed CLI, so that the flow menu has an agent to set its one agent role up with.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}

#: A flow with one environment role of its own, which is what the picker places.
PLACED = '''
"""One agent, working on a machine somebody names."""

from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowContext, FlowParams
from hmz.flows import ShellEnvMixin, flow


class Box(Env, ShellEnvMixin): ...


class Agents(AgentCollection):
    """Just the one."""

    builder: Agent


class Envs(EnvCollection):
    box: Box


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def placed(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                 ctx: FlowContext) -> None:
    pass
'''

#: An ssh config of somebody's that is not theirs: two hosts, and a pattern that is none.
CONFIG = """\
Host gpu
  HostName 10.0.0.2
  User alice
  Port 2222
Host builder
  ProxyJump bastion
Host *
  ServerAliveInterval 30
"""


@pytest.fixture
def standins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`ssh` and `docker` stand-ins on `PATH`, and a home with no `.ssh` of its own in it.

    Returns:
      The log both write what they were asked to.
    """
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, said in (("ssh", _SSH), ("docker", _DOCKER)):
        (bin_ / name).write_text(said)
        (bin_ / name).chmod(0o755)
    info = tmp_path / "info.json"
    info.write_text(json.dumps(_INFO))
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STANDIN_LOG", str(tmp_path / "asked.log"))
    monkeypatch.setenv("STANDIN_INFO", str(info))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    return tmp_path / "asked.log"


def _asked(log: Path) -> str:
    """What the stand-ins were asked, in the order they were asked it."""
    return log.read_text() if log.exists() else ""


def _under(app: Humanize) -> str:
    """What is said under the list, which is where a sheet reports itself."""
    return str(app.screen.query_one("#tuning", Label).content)


def _drawn(app: Humanize) -> str:
    """Every row the sheet on top has put up, as one block to read."""
    return "\n".join(
        str(one.prompt) for one in app.screen.query_one("#choices", OptionList).options
    )


async def _opens(app: Humanize, driver: Pilot[None], held: str, sheet: type) -> None:
    """Walks on to one row, presses enter, and waits for the sheet it opens.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id.
      sheet: What it opens.
    """
    await until(lambda: held in ids(app), driver)
    await onto(app, driver, held)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, sheet), driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )


async def _types(app: Humanize, driver: Pilot[None], held: str, said: str) -> None:
    """Writes one row of a form, as typing on it does, and keeps it.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id.
      said: What to type over what it holds.
    """
    await onto(app, driver, held)
    sheet = app.screen
    was = cast("Hosting", sheet)._typed_in.get(held, "")
    fresh = held in cast("Hosting", sheet)._fresh
    await driver.press("enter")
    await driver.pause()
    if not fresh:
        await driver.press(*["backspace"] * len(was))
    await driver.press(*said, "enter")
    await driver.pause()


async def _done(app: Humanize, driver: Pilot[None]) -> None:
    """Answers the form on top from its `done` row."""
    await onto(app, driver, _DONE)
    await driver.press("enter")
    await driver.pause()


async def _into_machines(app: Humanize, driver: Pilot[None]) -> Adjusts:
    """Opens `/settings environments`, which is the page these are all about."""
    await into_settings(app, driver, 3)
    return cast("Adjusts", app.screen)


@pytest.mark.timeout(60)
async def test_the_page_brings_machines_in_from_its_top_rows_and_holds_nothing(
    standins: Path,
) -> None:
    """Adding either kind and importing, above the list; no save row, nothing being held."""
    del standins
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_machines(app, driver)

        assert rows(app) == [_ADD, _DOCKS, _IMPORTS]
        assert _SEARCH in ids(app)
        assert sheet.under() == _ADD
        assert "nothing saved yet" in _under(app)
        assert "add an ssh host" in _drawn(app)
        assert "add a docker host" in _drawn(app)


@pytest.mark.timeout(60)
async def test_an_ssh_host_is_added_on_one_form_and_asked_what_it_has(
    standins: Path,
) -> None:
    """`user@host:port` typed as one is taken apart, the name follows it, and it is checked."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_machines(app, driver)
        await _opens(app, driver, _ADD, Hosting)
        form = cast("Hosting", app.screen)
        assert form.under() == "host"

        await driver.press(*"me@gpu.example:2200", "enter")
        await driver.pause()
        assert form._typed_in["host"] == "gpu.example"
        assert (form._typed_in["user"], form._typed_in["port"]) == ("me", "2200")
        assert form._typed_in["name"] == "gpu"
        await _types(app, driver, "identity_file", "~/.ssh/gpu")
        await _types(app, driver, "options", "ServerAliveInterval=15, Compression=yes")
        await _types(app, driver, "workdir", "~/work")
        assert "adds ssh/gpu" in _drawn(app)
        await _done(app, driver)

        await until(lambda: app.screen is sheet, driver)
        await until(lambda: "answers" in _under(app), driver)
        saved = store.find("ssh", "gpu")
        assert saved == SSHProvider(
            name="gpu",
            host="gpu.example",
            user="me",
            port=2200,
            identity_file="~/.ssh/gpu",
            options={"ServerAliveInterval": "15", "Compression": "yes"},
            workdir="~/work",
        )
        # Asked what a run would ask it, down the road a run takes: its home, its CPUs.
        assert f"home {os.environ['HOME']}" in _under(app)
        assert f"{len(os.sched_getaffinity(0))} CPUs" in _under(app)
        assert sheet.under() == "ssh/gpu"
        assert "me@gpu.example:2200 · key ~/.ssh/gpu" in _drawn(app)
        assert "ssh/gpu is saved at" in "\n".join(sheet._told)
    assert "-o ServerAliveInterval=15" in _asked(standins)


@pytest.mark.timeout(60)
async def test_what_the_store_refuses_is_said_on_the_form_and_saves_nothing(
    standins: Path,
) -> None:
    del standins
    store.add(SSHProvider(name="gpu", host="elsewhere"))
    app = Humanize()
    async with app.run_test() as driver:
        await _into_machines(app, driver)
        await _opens(app, driver, _ADD, Hosting)
        form = cast("Hosting", app.screen)
        await driver.press(*"gpu", "enter")
        # Named after its host, but not over one saved already.
        assert form._typed_in["name"] == "gpu-2"

        await _types(app, driver, "options", "Compression")
        await _done(app, driver)
        assert isinstance(app.screen, Hosting)
        assert "'Compression' is not KEYWORD=VALUE" in _under(app)

        await _types(app, driver, "options", "HostName=x")
        await _done(app, driver)
        assert "HostName is said with host" in _under(app)

        await _types(app, driver, "options", "")
        await _types(app, driver, "port", "22x")
        await _done(app, driver)
        assert "is not a port" in _under(app)

        await _types(app, driver, "port", "")
        await _types(app, driver, "name", "gpu")
        await _done(app, driver)
        assert "saved as gpu already" in _under(app)

    assert [one.name for one in store.providers()] == ["gpu"]


@pytest.mark.timeout(60)
async def test_the_hosts_of_another_config_are_imported_and_theirs_is_never_written(
    standins: Path, tmp_path: Path
) -> None:
    """Read as ssh reads them, switched on unless saved, and saved under their `Host`."""
    config = tmp_path / "work_ssh_config"
    config.write_text(CONFIG)
    store.write(
        SSHProvider(
            name="builder", alias="builder", config=str(config), made="imported"
        )
    )
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_machines(app, driver)
        await _opens(app, driver, _IMPORTS, Importing)
        form = cast("Importing", app.screen)
        await until(lambda: form._read is not None, driver)
        assert form._typed_in["config"] == "~/.ssh/config"
        assert "names no host" in _under(app)

        # Typed over what it guessed, which is what the first letter does.
        await onto(app, driver, "config")
        await driver.press(*str(config), "enter")
        await until(lambda: form._read == str(config) and not form._reading, driver)
        assert rows(app) == ["config", "host:gpu", "host:builder", _DONE]
        # The one not saved is on, the one saved is off and says so.
        assert form._on("gpu")
        assert not form._on("builder")
        # What `ssh -G` said of it, which the stand-in says of any host.
        assert "me@gpu.example:22" in _drawn(app)
        assert "saved already" in _drawn(app)
        # And the cursor is on the row that imports them.
        assert form.under() == _DONE
        assert "imports gpu" in _drawn(app)
        await driver.press("enter")

        await until(lambda: app.screen is sheet, driver)
        assert "imported gpu" in _under(app)
        assert "left builder" in _under(app)
        assert sheet.under() == "ssh/gpu"

    assert store.find("ssh", "gpu") == SSHProvider(
        name="gpu", alias="gpu", config=str(config.resolve()), made="imported"
    )
    assert not (tmp_path / "home" / ".ssh").exists()
    assert "-G -F" in _asked(standins)


@pytest.mark.timeout(60)
async def test_a_host_switched_off_is_not_imported(
    standins: Path, tmp_path: Path
) -> None:
    del standins
    config = tmp_path / "config"
    config.write_text(CONFIG)
    app = Humanize()
    async with app.run_test() as driver:
        await _into_machines(app, driver)
        await _opens(app, driver, _IMPORTS, Importing)
        form = cast("Importing", app.screen)
        await onto(app, driver, "config")
        await driver.press(*str(config), "enter")
        await until(lambda: form._read == str(config) and not form._reading, driver)

        await changes(app, driver, "host:gpu", "right")
        await changes(app, driver, "host:builder", "right")
        assert "imports nothing" in _drawn(app)
        await _done(app, driver)
        assert "no host is switched on" in _under(app)

        await changes(app, driver, "host:builder", "right")
        await _done(app, driver)
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        assert "left gpu" in _under(app)

    assert [one.name for one in store.providers()] == ["builder"]


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("steps", "rows_said", "endpoint", "tls"),
    [
        pytest.param(0, {}, "local", "", id="local"),
        pytest.param(
            1,
            {"socket": "/run/docker.sock"},
            "unix:///run/docker.sock",
            "",
            id="socket",
        ),
        pytest.param(
            2,
            {"address": "10.0.0.5:2376", "tls_dir": "/certs"},
            "tcp://10.0.0.5:2376",
            "/certs",
            id="tcp",
        ),
        pytest.param(3, {}, "ssh:gpu", "", id="saved-ssh-host"),
        pytest.param(4, {"address": "me@box:2200"}, "ssh://me@box:2200", "", id="ssh"),
        pytest.param(5, {"context": "remote"}, "context:remote", "", id="context"),
    ],
)
async def test_a_docker_host_is_reached_every_way_a_daemon_is(
    standins: Path, steps: int, rows_said: dict[str, str], endpoint: str, tls: str
) -> None:
    """Each way is a rung of one row, and the rows under it are what that way asks."""
    store.add(SSHProvider(name="gpu", host="gpu.example"))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_machines(app, driver)
        await _opens(app, driver, _DOCKS, Docking)
        form = cast("Docking", app.screen)
        if steps:
            await changes(app, driver, "endpoint", *["right"] * steps)
        for held, said in rows_said.items():
            await _types(app, driver, held, said)
        if endpoint == "ssh:gpu":
            assert form.under() == "via"  # the one thing that way still needs
            await _opens(app, driver, "via", Hosts)
            await onto(app, driver, "gpu")
            await driver.press("enter")
            await until(lambda: app.screen is form, driver)
        name = form._typed_in["name"]
        await _done(app, driver)

        await until(lambda: app.screen is sheet, driver)
        await until(lambda: "answers" in _under(app), driver)
        assert "docker 29.4.3" in _under(app)

    saved = store.find("docker", name)
    assert isinstance(saved, DockerProvider)
    assert (saved.endpoint, saved.tls_dir) == (endpoint, tls)
    asked = _asked(standins)
    assert "info --format" in asked


@pytest.mark.timeout(60)
async def test_detect_writes_in_what_the_daemon_has_to_be_typed_over(
    standins: Path,
) -> None:
    """All it has, written in and walked through, so handing out less is typing less."""
    del standins
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_machines(app, driver)
        await _opens(app, driver, _DOCKS, Docking)
        form = cast("Docking", app.screen)
        assert form._typed_in["name"] == "local"

        await onto(app, driver, _DETECTS)
        await driver.press("enter")
        await until(lambda: form._typed_in.get("cpus") == "64", driver)
        assert form._typed_in["memory"] == "2015G"
        assert form._typed_in["gpus"] == "0, 1"
        assert "runtimes nvidia" in _under(app)
        assert form.under() == "cpus"

        # The first letter replaces what it wrote, and enter walks on to the next of them.
        await driver.press(*"16", "enter")
        assert form.under() == "memory"
        await driver.press(*"64G", "enter")
        assert form.under() == "gpus"
        await driver.press("0", "enter")
        # What it hands out is the last of the form, so that was the last of it.
        assert form.under() == _DONE
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)
        await until(lambda: "answers" in _under(app), driver)
        assert "short of" not in _under(app)
        assert "16 CPUs, 64G, GPUs 0" in _drawn(app)

    assert store.find("docker", "local") == DockerProvider(
        name="local", cpus=16.0, memory=64 << 30, gpus=("0",)
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("held", "said", "why"),
    [
        ("memory", "64", "is not an amount"),
        ("cpus", "many", "cpus: 'many' is not a number"),
        ("max_containers", "two", "is not a number of containers"),
        ("gpus", "0,0", "a GPU is named twice"),
        ("run_args", "--label 'x", "run args:"),
        ("workdir", "work", "neither absolute nor under ~/"),
    ],
)
async def test_what_a_daemon_cannot_be_given_is_refused_on_the_form(
    standins: Path, held: str, said: str, why: str
) -> None:
    del standins
    app = Humanize()
    async with app.run_test() as driver:
        await _into_machines(app, driver)
        await _opens(app, driver, _DOCKS, Docking)
        await _types(app, driver, held, said)
        await _done(app, driver)

        assert isinstance(app.screen, Docking)
        assert why in _under(app)
    assert store.providers() == []


@pytest.mark.timeout(60)
async def test_what_a_daemon_is_saved_to_hand_out_and_has_not_got_is_said_in_yellow(
    standins: Path,
) -> None:
    del standins
    store.add(DockerProvider(name="local", cpus=128, gpus=("0", "3")))
    app = Humanize()
    async with app.run_test() as driver:
        await _into_machines(app, driver)
        await onto(app, driver, "docker/local")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Machine), driver)
        await onto(app, driver, _CHECKS)
        await driver.press("enter")
        await until(lambda: "short of" in _under(app), driver)

        assert "[yellow]" in _under(app)
        assert "128 CPUs and has 64" in _under(app)
        assert "no GPU 3" in _under(app)


@pytest.mark.timeout(60)
async def test_a_host_that_cannot_be_reached_says_why_rather_than_hanging(
    standins: Path,
) -> None:
    del standins
    store.add(SSHProvider(name="far", host="refusing"))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_machines(app, driver)
        await onto(app, driver, "ssh/far")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Machine), driver)
        assert rows(app) == [_CORRECTS, _CHECKS, _TAKES_AWAY]
        await onto(app, driver, _CHECKS)
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)

        await until(lambda: "could not be reached" in _under(app), driver)
        assert "Connection refused" in _under(app)
        assert "[red]" in _under(app)


@pytest.mark.timeout(60)
async def test_a_machine_is_corrected_and_taken_away_from_its_own_menu(
    standins: Path,
) -> None:
    """Each at once, which is why the page has no row to save from."""
    del standins
    store.add(SSHProvider(name="gpu", host="gpu.example", workdir="~/a"))
    store.add(DockerProvider(name="far", endpoint="ssh:gpu"))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_machines(app, driver)
        await onto(app, driver, "ssh/gpu")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Machine), driver)
        await _opens(app, driver, _CORRECTS, Hosting)
        # Correcting one asks all of it but the name it is saved under.
        assert "name" not in rows(app)
        await _types(app, driver, "workdir", "~/b")
        assert "corrects ssh/gpu" in _drawn(app)
        await _done(app, driver)
        await until(lambda: app.screen is sheet, driver)
        stored = store.find("ssh", "gpu")
        assert stored is not None
        assert stored.workdir == "~/b"
        assert "ssh/gpu is corrected" in "\n".join(sheet._told)

        await until(lambda: "answers" in _under(app), driver)
        await onto(app, driver, "ssh/gpu")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Machine), driver)
        await onto(app, driver, _TAKES_AWAY)
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)

        assert store.find("ssh", "gpu") is None
        assert "ssh/gpu" not in ids(app)
        assert "no longer saved" in _under(app)
        # And what reached its daemon through it is said, in yellow.
        assert "far reached its daemon through it" in _under(app)
        assert _SAVE not in ids(app)


# ------------------------------------------------------------ the role picker on /flow


@pytest.fixture
def placed(tmp_path: Path) -> Path:
    """Puts a flow with one environment role where this project's own would be."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    return written(where, "placed", PLACED)


async def _placing(app: Humanize, driver: Pilot[None]) -> Placing:
    """Opens the flow menu on `placed`, and then where its environment role is."""
    await driver.press(*"/flow placed", "enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = cast("Flows", app.screen)
    await until(lambda: sheet._inside, driver)
    await _opens(app, driver, "@box", Placing)
    return cast("Placing", app.screen)


async def _saves(app: Humanize, driver: Pilot[None]) -> None:
    """Gives the flow a budget, and saves the menu from its row."""
    await onto(app, driver, _BUDGET)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Configures), driver)
    await changes(app, driver, "duration", *"1h")
    await _done(app, driver)
    await until(lambda: isinstance(app.screen, Flows), driver)
    await onto(app, driver, _SAVE)
    await driver.press("enter")
    await until(lambda: not isinstance(app.screen, Flows), driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_role_is_put_on_a_saved_host_and_remembered_as_e_spells_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
    placed: Path,
    tmp_path: Path,
) -> None:
    """Backend, host, workdir -- the host bringing its own -- and saved as `-e` spells it."""
    del placed
    store.add(SSHProvider(name="box", host="box.example", workdir="~/work"))
    store.add(SSHProvider(name="gpu", host="gpu.example"))
    app = Humanize()
    async with app.run_test() as driver:
        form = await _placing(app, driver)
        # On ssh, there being hosts saved for it, and on the one thing still to answer.
        assert form._typed_in["backend"] == "ssh"
        assert form.under() == "provider"
        assert "leaves box unsaid" in _drawn(app)

        await _opens(app, driver, "provider", Hosts)
        assert rows(app)[:2] == [_ADD, _UNSAVED]
        await onto(app, driver, "box")
        await driver.press("enter")
        await until(lambda: app.screen is form, driver)

        assert form._typed_in["workdir"] == "~/work"
        assert form._typed_in["spelled"] == "ssh@box/~/work"
        assert form.under() == _DONE
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert "ssh@box/~/work" in _drawn(app)
        await _saves(app, driver)

    assert app._envs == {"box": "ssh@box/~/work"}
    assert Settings(tmp_path).envs("placed") == {"box": "ssh@box/~/work"}


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_remembered_role_opens_as_it_was_and_the_workdir_is_its_own(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
    placed: Path,
    tmp_path: Path,
) -> None:
    del placed
    store.add(SSHProvider(name="box", host="box.example", workdir="~/work"))
    Settings(tmp_path).remember(
        "placed",
        {"builder": Runs("claude/claude-opus-5:max")},
        envs={"box": "ssh@box/srv/x"},
    )
    app = Humanize()
    async with app.run_test() as driver:
        form = await _placing(app, driver)
        assert (form._typed_in["backend"], form._typed_in["provider"]) == ("ssh", "box")
        assert form._typed_in["workdir"] == "/srv/x"

        # Another workdir, typed over the one it had, and spelled as it is typed.
        await _types(app, driver, "workdir", "~/other")
        assert form._typed_in["spelled"] == "ssh@box/~/other"
        await _done(app, driver)
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert "ssh@box/~/other" in _drawn(app)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_role_is_put_on_a_host_nobody_saved(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
    placed: Path,
) -> None:
    del placed
    app = Humanize()
    async with app.run_test() as driver:
        form = await _placing(app, driver)
        # Nothing saved for any backend, so it starts on the first `-e` takes.
        assert form._typed_in["backend"] == next(iter(EnvBackendKind)).value
        await changes(app, driver, "backend", "right")
        assert form._typed_in["backend"] == "ssh"

        await _opens(app, driver, "provider", Hosts)
        assert "no ssh host is saved yet" in _under(app)
        await _opens(app, driver, _UNSAVED, Unsaved)
        await driver.press(*"me@far:2222", "enter")
        await _done(app, driver)
        await until(lambda: app.screen is form, driver)

        assert form._typed_in["provider"] == "me@far:2222"
        assert "not saved" in _drawn(app)
        # No workdir of its own, so that is what is asked next -- and asked for, on done.
        assert form.under() == "workdir"
        await _done(app, driver)
        assert "say the workdir as well" in _under(app) or "expected" in _under(app)
        await _types(app, driver, "workdir", "/srv")
        await _done(app, driver)
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert cast("Flows", app.screen)._envs == {"box": "ssh@me@far:2222/srv"}


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_host_added_from_the_role_is_saved_and_comes_back_chosen(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
    placed: Path,
) -> None:
    del placed
    store.add(SSHProvider(name="old", host="old.example"))
    app = Humanize()
    async with app.run_test() as driver:
        form = await _placing(app, driver)
        await _opens(app, driver, "provider", Hosts)
        await _opens(app, driver, _ADD, Hosting)
        await driver.press(*"new.example", "enter")
        await _types(app, driver, "workdir", "~/w")
        await _done(app, driver)
        await until(lambda: app.screen is form, driver)

        assert form._typed_in["provider"] == "new"
        assert form._typed_in["spelled"] == "ssh@new/~/w"
    assert store.find("ssh", "new") == SSHProvider(
        name="new", host="new.example", workdir="~/w"
    )


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_spec_typed_whole_sets_the_rows_and_one_that_does_not_read_is_refused(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
    placed: Path,
    tmp_path: Path,
) -> None:
    """The power user's row: `-e` as they would type it, read the way `-e` is."""
    del placed
    app = Humanize()
    async with app.run_test() as driver:
        form = await _placing(app, driver)
        assert form.choices("backend") == [kind.value for kind in EnvBackendKind]

        await _types(app, driver, "spelled", "nowhere")
        await _done(app, driver)
        assert isinstance(app.screen, Placing)
        assert "expected <role>=<backend>" in _under(app)

        await _types(app, driver, "spelled", f"local@{tmp_path}")
        assert form._typed_in["backend"] == "local"
        assert form._typed_in["workdir"] == str(tmp_path)
        assert "provider" not in rows(app)
        await _done(app, driver)
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert f"local@{tmp_path}" in _drawn(app)
