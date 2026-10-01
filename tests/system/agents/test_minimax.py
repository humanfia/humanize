"""MiniMax Code, driven against the real `mcode` this machine has installed.

The other half of this backend's tests lives in `tests/integration/agents/test_minimax.py`,
where every turn is taken against a stand-in written onto PATH. What only the real CLI can
answer is whether the way in humanize offers for an endpoint of somebody's is one it takes,
and whether a session opened under the account it made is one a second turn carries on --
through humanize answering its credentials and keeping its sessions at paths of its own, which
a stand-in reads none of. So the account here is made the way a person makes one, pointed at
the endpoint on the loopback the suite serves, and two turns are taken on it: no token is
spent and nobody's account is reached, and it runs wherever `mcode` is installed.

`mcode` writes a line putting its own helpers on PATH into the shell profile of the home it
runs under, and keeps everything else under its data directory. Both are moved into the
test's own directory, so that a run of this leaves nothing of the machine's changed.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, models
from hmz.coganchor.agents import KEEPING, MiniMaxCodeAgent, MiniMaxCodeAgentConfig
from hmz.coganchor.linux import landlock
from hmz.coganchor.providers import login, redirect
from hmz.flows import Permission, PermissionKind
from hmz.runtime.flowing import harnessing

if TYPE_CHECKING:
    from tests.llm import Serving

pytestmark = [pytest.mark.agent, pytest.mark.timeout(300)]


@pytest.fixture
def mcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The real `mcode`, with a home and a data directory of this test's own."""
    if shutil.which("mcode") is None:
        pytest.skip("mcode is not installed here: npm i -g @minimax-ai/code")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MINIMAX_DATA_DIR", str(home / ".minimax"))
    work = tmp_path / "work"
    work.mkdir()
    return work


def test_a_gateway_account_takes_a_turn_and_the_next_carries_it_on(
    asking: None, mcode: Path, llm: Serving
) -> None:
    profile = backends.named("mcode")
    assert profile is not None
    way = next(one for one in profile.ways if one.name == "gateway")
    answers = {
        "MCODE_GATEWAY_URL": f"{llm.base}/v1",
        "MCODE_PROVIDER_API_KEY": llm.secret,
        "MCODE_GATEWAY_MODEL": llm.serves[0],
    }
    account = login.make("mcode", "loopback", way, answers)
    assert login.sign_in(account, way, answers) == 0
    model = f"custom_provider:gateway/{llm.serves[0]}"
    assert model in [one.name for one in models.ask("mcode", "loopback")]
    agent = MiniMaxCodeAgent(
        MiniMaxCodeAgentConfig(
            model=model, effort="", permission="bypass", provider="loopback"
        )
    )
    session = agent.new(mcode)

    assert session("Reply with one word.") == llm.says
    assert session("And again.") == llm.says

    # One session across the two turns, kept where humanize keeps them and not in the CLI's
    # own home, and its log found there by the id the CLI stated.
    assert agent.opened == [session.id]
    kept = agent.kept()
    (pattern,) = profile.logged(session.id)
    assert list(kept.glob(pattern))
    assert agent.spent().total > 0


def test_a_fenced_turn_keeping_no_session_takes_its_lock_and_answers(
    asking: None, mcode: Path, llm: Serving, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`HUMANIZE_SESSIONS=off`, held by a real wall that reads the home and writes the workdir.

    `mcode` makes `~/.minimax.lock` beside its home at every start, which that wall does not
    let it write: the turn starts only where that one path is answered from elsewhere.
    """
    if not landlock.available(net=False):
        pytest.skip("this machine has no Landlock to put the fence up with")
    if not redirect.supervises():
        pytest.skip("this machine cannot supervise a turn to answer the lock's path")
    monkeypatch.setenv(KEEPING, "off")
    profile = backends.named("mcode")
    assert profile is not None
    way = next(one for one in profile.ways if one.name == "gateway")
    answers = {
        "MCODE_GATEWAY_URL": f"{llm.base}/v1",
        "MCODE_PROVIDER_API_KEY": llm.secret,
        "MCODE_GATEWAY_MODEL": llm.serves[0],
    }
    account = login.make("mcode", "loopback", way, answers)
    assert login.sign_in(account, way, answers) == 0
    permission = Permission(
        local=PermissionKind.ALL,
        user=PermissionKind.READ,
        system=PermissionKind.NONE,
        online=PermissionKind.ALL,
    )
    home = Path(os.environ["HOME"])
    fence = harnessing.fenced(
        permission,
        workdir=str(mcode),
        home=str(home),
        profile=profile,
        environ=dict(os.environ),
    )
    agent = MiniMaxCodeAgent(
        MiniMaxCodeAgentConfig(
            model=f"custom_provider:gateway/{llm.serves[0]}",
            effort="",
            permission="bypass",
            provider="loopback",
            fence=fence,
        )
    )

    assert agent.new(mcode)("Reply with one word.") == llm.says
    # The lock was taken where sessions would have been kept, and let go of; none was kept
    # there, and the home's own lock was never made.
    kept = agent.keeps / "mcode"
    assert kept.is_dir()
    assert list(kept.iterdir()) == []
    assert not list(home.glob("*.lock"))
