"""ZCode, driven against the real `zcode` this machine has installed.

The other half of this backend's tests lives in `tests/integration/agents/test_zcode.py`,
where every turn is taken against a stand-in app server written onto PATH. A stand-in says
yes to whatever it is asked, which is what makes it safe in CI and what makes it blind: the
three checks here are the ones only the real server can answer -- that a session is refused
outright until it has been handed a provider, that one opens as soon as it has been, and that
a turn taken on the account humanize was given lands on that account and writes the file it
says it wrote. All three want `zcode` on PATH and the last wants an account configured on
this machine, so none of them is run by CI.

The refusal is a test of its own rather than the opening half of the one that gets a session,
because it is the one check here that some machines cannot be shown: an install with a zcode
provider of its own opens a session either way. Apart, such a machine reports a skip that
says so. Together, it reported a pass for a test that had quietly stopped checking.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hmz.coganchor.agents import ZcodeAgent, ZcodeAgentConfig

#: Somewhere a request would never reach, for the test that only opens a session: nothing is
#: sent to the endpoint until a turn is, so this is a base URL that names a provider without
#: naming anybody's account.
_NOWHERE = "https://zcode.invalid/v1"


def _scrubbed(where: Path) -> None:
    """Takes a borrowed account back off disk, and says so if any of it is still there.

    `ignore_errors` because this runs as a test comes apart, at a directory a copy which
    failed part-way may never have made: raising there would bury whatever the test was
    actually failing about. The check afterwards is what that leniency would otherwise cost
    -- a removal that quietly did nothing is a credential left in a temporary directory,
    which is the thing being guarded against rather than a tidy-up worth being quiet about.

    Args:
      where: The copy to remove.
    """
    shutil.rmtree(where, ignore_errors=True)
    assert not where.exists(), f"a borrowed account is still on disk at {where}"


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_real_app_server_refuses_a_session_until_it_is_handed_a_provider(
    tmp_path: Path,
) -> None:
    """A stand-in says yes to a session whatever it is asked; the real one does not.

    ZCode resolves its model provider from the configuration file the person at this machine
    owns, and a server started without one refuses every session outright. That is the whole
    of the bug this pins: a driver that names a model and no provider is a driver whose every
    turn comes back `Model config is missing`, and a stand-in cannot tell anybody so.

    It costs nothing and reaches nobody -- a session is asked for and the server put down, no
    turn is sent, and there is no endpoint named to send one to.
    """
    from hmz.coganchor.agents.zcode import _AppServer, _Held

    if shutil.which("zcode") is None:
        pytest.skip("zcode is not installed here")
    if (Path.home() / ".zcode" / "cli" / "config.json").exists():
        # An install with a provider of its own is one where a session opens whether it was
        # handed one or not, so the refusal cannot be shown on this machine. Said as a skip
        # rather than stepped over quietly, which is what this used to do: a check that
        # stops checking without saying so is a pass that means nothing, and it comes back
        # in the report reading exactly like the one from a machine that proved it.
        pytest.skip(
            "this machine has a zcode provider of its own, which refuses nothing"
        )
    held = _Held(model="hmz-test/no-such-model", effort="high", mode="plan")
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


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_real_app_server_opens_a_session_once_it_is_handed_a_provider(
    tmp_path: Path,
) -> None:
    """The other side of the refusal: handed a provider, the real server opens a session.

    Which is the half a stand-in cannot make either, for the opposite reason -- it opens a
    session whatever it was passed, so a driver that stopped writing the provider into one
    would go on passing there and fail on every real turn.

    It costs nothing and reaches nobody: a session is opened and the server put down, and
    nothing is sent to the endpoint a session names until a turn is, so :data:`_NOWHERE` is
    never called on.
    """
    from hmz.coganchor.agents.zcode import _AppServer, _Held, _runtime

    if shutil.which("zcode") is None:
        pytest.skip("zcode is not installed here")
    held = _Held(model="hmz-test/no-such-model", effort="high", mode="plan")
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
    from hmz.coganchor import models

    theirs = Path.home() / ".humanize" / "providers" / "zcode" / "nvidia"
    if not theirs.is_dir():
        pytest.skip("no zcode account is configured on this machine")
    if shutil.which("zcode") is None:
        pytest.skip("zcode is not installed here")
    monkeypatch.chdir(tmp_path)  # so an agent that tidies up tidies up nothing of ours
    ours = Path(os.environ["HUMANIZE_HOME"]) / "providers" / "zcode" / "nvidia"
    # Where the copy is going, checked before anything is registered to delete it. `ours` is
    # built from an environment variable and what goes on the stack below is a recursive
    # remove: a run whose `HUMANIZE_HOME` had somehow become the real home -- the autouse
    # fixture in `tests/conftest.py` bypassed, the variable exported by hand at a terminal --
    # would have this test delete the very account it set out to borrow, which is the one
    # failure here that cannot be undone by running the suite again.
    assert ours.resolve() != theirs.resolve(), (
        "HUMANIZE_HOME is the home this account lives in; the copy would be the original"
    )
    assert theirs.resolve() not in ours.resolve().parents, (
        "HUMANIZE_HOME is inside the account being borrowed"
    )
    ours.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as holding:
        # Taken back off disk however this test ends, and registered before the copy is made
        # so that a copy which failed part-way leaves nothing either. What is borrowed here
        # is somebody's live account, and the home it is borrowed into is under `tmp_path`,
        # which is not as temporary as the name: pytest keeps the last three runs' worth of
        # them under `/tmp/pytest-of-<user>` for the next run to read. A credential left
        # there outlives the run that copied it, sitting in a world-readable directory under
        # a name anybody can guess, which is the one thing a test may never leave behind --
        # so the removal is checked rather than assumed, `rmtree` having been told to keep
        # quiet about a directory that a failed copy never made.
        holding.callback(_scrubbed, ours)
        shutil.copytree(theirs, ours)

        served = [one.name for one in models.ask("zcode", "nvidia", seconds=180)]
        assert served, "the endpoint said nothing about what it serves"
        # Written as ZCode reads a model, `provider/id`, which an endpoint cannot say alone.
        assert all(one.startswith("gw/") for one in served[:10]), served[:10]
        wanted = next((one for one in served if "glm" in one), served[0])

        agent = ZcodeAgent(
            ZcodeAgentConfig(model=wanted, effort="high", provider="nvidia")
        )
        # Registered after the removal above and so run before it, a stack coming apart in
        # the reverse of the order it was built: an agent stopped after its account had been
        # taken off disk is one whose last act is a call it cannot make. Swapping these two
        # lines swaps that, which is why the order is written down rather than left to read.
        holding.callback(agent.stop)
        session = agent.new()
        assert "ok" in session("reply with exactly: ok").lower()

        session("create a file named hello.txt whose only contents are: hi")
        landed = tmp_path / "hello.txt"
        # The file rather than the agent's word for it: an agent that reports a write which
        # never happened is the one failure this whole check exists to catch.
        assert landed.is_file(), "the turn said it wrote a file that is not there"
        assert landed.read_text().strip() == "hi"
