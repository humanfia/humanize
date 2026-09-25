"""The half of one run's record that only a machine which can supervise a turn can check.

The rest of it is `tests/integration/runtime/test_epics.py`, which drives a stand-in CLI and
asks what was written down. Here is the one thing that cannot be shown there: a turn taken as a
named account is a supervised turn -- the paths it reads are answered by others, which is a
seccomp filter and a ptrace supervisor -- so what an epic says about *which* account ran a
session can only be checked where the kernel will hand over a tracee. CI is not promised one,
which is why this is a tier of its own rather than a skip inside the other file.

What the two halves share -- a flow that opens one session, and the stand-in `claude` whose
logs humanize knows where to find -- is in `tests/recording.py`, where the exporter's two
halves reach for it as well.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.runtime.epic import epics, read, sessions
from hmz.runtime.runner import Runner
from tests.recording import ONE, TASK, standing_in
from tests.stubs import written
from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@traced
def test_a_session_says_which_account_took_its_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two agents of one CLI are two accounts, and the backend's log says neither."""
    from hmz.coganchor import providers

    standing_in(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    providers.add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk-nothing"})

    Runner(
        tmp_path / "flow",
        agents={"builder": "claude@work/claude-haiku-4-5:low"},
        budget={"cost": 1},
    ).run(TASK)

    (epic,) = epics()
    (one,) = sessions(epic)
    assert one.provider == "work"
    assert one.name == f"builder-claude@work-{one.ident}"
    # And what it was configured with is what the run says it was driven by.
    ran = read(epic)
    assert ran is not None
    assert ran.agents[0].provider == "work"
    assert ran.agents[0].spec == "claude@work/claude-haiku-4-5:low"
