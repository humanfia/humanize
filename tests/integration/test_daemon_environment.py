"""The environment a daemon and its hosts run in, and what `epic.start` checks before a host.

`hmz daemon serve` is run for real in a session of its own, so with no terminal, as a service
manager runs it, in a bare environment whose `SHELL` is a stand-in login shell; a flow in a host
it started writes down the environment it was given.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.runtime import Hmz, Refused
from tests.integration.doubles_daemon import hosting, project, until, written

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.timeout(90)

#: Writes down the environment its host gave it.
ENVIRON = """
import json
import os
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=AgentCollection, envs=Envs, params=FlowParams, name="environ")
async def environ(task, *, agents, envs, params, ctx):
    Path("environ.json").write_text(json.dumps(dict(os.environ)))
"""

#: A login shell whose profile talks, sets `FOO` and puts a directory on `PATH`, and then
#: runs the line it was given, as `$SHELL -ilc <line>` does.
LOGIN = """#!/bin/sh
echo "a profile that talks"
FOO=bar
PATH="/opt/login/bin:$PATH"
export FOO PATH
exec /bin/sh -c "$2"
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    # Offered as `@local/environ`, which a start may write down as the workspace's set-up.
    (at / ".hmz" / "flows").mkdir(parents=True)
    written(at / ".hmz" / "flows", "environ", ENVIRON)
    with hosting():
        yield at


def _served(tmp_path: Path) -> subprocess.Popen[bytes]:
    """`hmz daemon serve` with no terminal and a bare environment, once it is listening."""
    shell = tmp_path / "login"
    shell.write_text(LOGIN)
    shell.chmod(0o755)
    bare = {
        "PATH": "/usr/bin:/bin",
        "SHELL": str(shell),
        **{
            name: value
            for name, value in os.environ.items()
            if name in ("HOME", "TMPDIR") or name.startswith("HUMANIZE_")
        },
    }
    served = subprocess.Popen(
        [sys.executable, "-Pm", "hmz", "daemon", "serve"],
        env=bare,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        start_new_session=True,
    )
    assert until(
        lambda: (
            where.held(where.at()).get("pid") == served.pid
            and (where.at() / where.SOCKET).exists()
        )
    )
    return served


def test_a_daemon_served_with_no_terminal_hands_its_hosts_the_login_shells_environment(
    workspace: Path, tmp_path: Path
) -> None:
    served = _served(tmp_path)
    try:
        with daemon.attach("sdk", workspace=workspace) as link:
            link.start("@local/environ", "", budget={"cost": 1})
            assert until((workspace / "environ.json").exists)
    finally:
        served.send_signal(signal.SIGTERM)
        assert served.wait(30) == 0

    given = json.loads((workspace / "environ.json").read_text())
    assert given["FOO"] == "bar"
    path = given["PATH"].split(os.pathsep)
    assert path[0] == "/opt/login/bin"
    assert {"/usr/local/bin", "/opt/homebrew/bin"} <= set(path)
    assert "SHLVL" not in given
    assert not any("a profile that talks" in one for one in given.values())


def test_a_start_flows_check_refuses_is_refused_before_the_host_starts_anything(
    workspace: Path,
) -> None:
    with daemon.attach("sdk", workspace=workspace) as link:
        with pytest.raises(Refused) as refused:
            link.start("@local/environ", "", agents={"nobody": "nothing/at-all"})
        assert link.asked({"do": "status"})["run"] == 0
    assert "nobody" in str(refused.value)
    assert not (workspace / "environ.json").exists()


def test_a_start_remembering_writes_the_set_up_down_first(workspace: Path) -> None:
    with daemon.attach("sdk", workspace=workspace) as link:
        link.asked(
            {
                "do": "start",
                "flow": "@local/environ",
                "task": "",
                "budget": {"cost": 2},
                "remember": True,
            }
        )
        assert until((workspace / "environ.json").exists)
    assert Hmz(workspace).settings.budget("@local/environ")["cost"] == 2
