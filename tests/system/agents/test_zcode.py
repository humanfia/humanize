"""ZCode, driven against the real `zcode` this machine has installed.

The other half of this backend's tests lives in `tests/integration/agents/test_zcode.py`,
where every turn is taken against a stand-in app server written onto PATH. A stand-in says
yes to whatever it is asked, which is what makes it safe in CI and what makes it blind: the
two checks here are the ones only the real server can answer -- that a session is refused
outright until it has been handed a provider, and that a turn taken on the account humanize
was given lands on that account and writes the file it says it wrote. Both want `zcode` on
PATH, and the second wants an account configured on this machine, so neither is run by CI.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from hmz.coganchor.agents import ZcodeAgent, ZcodeAgentConfig

#: Somewhere a request would never reach, for the half of the real-server test that only
#: opens a session: nothing is sent to the endpoint until a turn is, so this is a base URL
#: that names a provider without naming anybody's account.
_NOWHERE = "https://zcode.invalid/v1"


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_real_app_server_opens_a_session_only_when_it_is_handed_a_provider(
    tmp_path: Path,
) -> None:
    """A stand-in says yes to a session whatever it is asked; the real one does not.

    ZCode resolves its model provider from the configuration file the person at this machine
    owns, and a server started without one refuses every session outright. That is the whole
    of the bug this pins: a driver that names a model and no provider is a driver whose every
    turn comes back `Model config is missing`, and a stand-in cannot tell anybody so.

    It costs nothing and reaches nobody -- a session is opened and the server put down, no
    turn is sent, so the endpoint named here is never called on.
    """
    import shutil

    from hmz.coganchor.agents.zcode import _AppServer, _Held, _runtime

    if shutil.which("zcode") is None:
        pytest.skip("zcode is not installed here")
    held = _Held(model="hmz-test/no-such-model", effort="high", mode="plan")
    theirs = Path.home() / ".zcode" / "cli" / "config.json"
    if not theirs.exists():
        # Only where this machine has no provider of its own to fall back on: an install
        # that has one is an install where a session opens either way, and the refusal this
        # is about is not one it can be shown.
        server = _AppServer(["zcode", "app-server", "--stdio"])
        try:
            with pytest.raises(subprocess.CalledProcessError) as refused:
                server.open(
                    str(tmp_path),
                    held,
                    searches=True,
                    titles=False,
                    delivery="desktop-continuous",
                )
            assert "model config is missing" in str(refused.value).lower()
        finally:
            server.stop()

    held.runtime = _runtime(
        held.model,
        held.effort,
        {"ZCODE_BASE_URL": _NOWHERE, "ZCODE_API_KEY": "not-a-key"},
        "openai-compatible",
    )
    server = _AppServer(["zcode", "app-server", "--stdio"])
    try:
        session = server.open(
            str(tmp_path),
            held,
            searches=True,
            titles=False,
            delivery="desktop-continuous",
        )
        assert session.startswith("sess_")
    finally:
        server.stop()


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_a_real_turn_lands_on_the_account_humanize_was_given(
    asking: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ZCode is the one backend with no account of its own on a machine like this.

    The others are signed in where the CLI keeps its own login, so a real-agent test reaches
    them by doing nothing. ZCode's account is a humanize provider instead, and the suite runs
    under a `HUMANIZE_HOME` of its own -- which is what keeps a run's epic out of the history
    of whoever asked for the tests to pass, and which also puts every provider out of reach.
    So the account is borrowed rather than the home given up: the provider's directory is
    copied into this run's home, and everything the turn writes still lands in `tmp_path`.

    What it proves is the whole path -- the gateway named as a session's own provider, a
    catalogue asked of that endpoint and written the way ZCode reads a model, a turn, a tool
    call, and the file on disk afterwards. None of it could be run at all until ZCode had an
    install to be run from.
    """
    import shutil

    from hmz.coganchor import models

    theirs = Path.home() / ".humanize" / "providers" / "zcode" / "nvidia"
    if not theirs.is_dir():
        pytest.skip("no zcode account is configured on this machine")
    if shutil.which("zcode") is None:
        pytest.skip("zcode is not installed here")
    ours = Path(os.environ["HUMANIZE_HOME"]) / "providers" / "zcode" / "nvidia"
    ours.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(theirs, ours)

    served = [one.name for one in models.ask("zcode", "nvidia", seconds=180)]
    assert served, "the endpoint said nothing about what it serves"
    # Written as ZCode reads a model, `provider/id`, which an endpoint cannot say on its own.
    assert all(one.startswith("gw/") for one in served[:10]), served[:10]
    wanted = next((one for one in served if "glm" in one), served[0])

    monkeypatch.chdir(tmp_path)  # so an agent that tidies up tidies up nothing of ours
    agent = ZcodeAgent(ZcodeAgentConfig(model=wanted, effort="high", provider="nvidia"))
    try:
        session = agent.new()
        assert "ok" in session("reply with exactly: ok").lower()

        session("create a file named hello.txt whose only contents are: hi")
        landed = tmp_path / "hello.txt"
        # The file rather than the agent's word for it: an agent that reports a write which
        # never happened is the one failure this whole check exists to catch.
        assert landed.is_file(), "the turn said it wrote a file that is not there"
        assert landed.read_text().strip() == "hi"
    finally:
        agent.stop()
