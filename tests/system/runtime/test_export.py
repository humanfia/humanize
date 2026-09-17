"""The one promise a bundle makes that only a supervised turn can be held to.

The rest of the exporter is `tests/integration/runtime/test_export.py`: what a bundle holds,
what its manifest says, where it lands and how big it came out, all of it against a stand-in
agent. Here is the promise that a run taken as a named account carries none of that account's
key -- and a turn under an account is a turn whose reads are answered by others, which is a
seccomp filter and a ptrace supervisor. CI is not promised a kernel that will hand one over,
so this is a tier of its own rather than a skip inside the other file: a redaction test that
quietly stops running is a key that quietly starts shipping.

The flow it runs, the stand-in it runs it with and the readers that open the bundle back up
are the other file's too, and are kept in `tests/recording.py` rather than written down twice:
a copy of them here is one that goes on asserting last year's tar layout long after the other
was fixed, in the one file CI never runs and so never says so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.coganchor import providers
from hmz.coganchor.agents import AgentConfig
from hmz.runtime.epic import epics
from hmz.runtime.exporting import REDACTED, bundle
from hmz.runtime.runner import Runner
from tests.recording import ONE, ClaudeAgent, claude_home, held, manifest
from tests.stubs import written
from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@traced
def test_no_account_variable_rides_along(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An export is the user's to send. The key it ran on is nobody's."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    providers.add(
        "claude",
        "work",
        "key",
        {"ANTHROPIC_AUTH_TOKEN": "hunter2-hunter2-hunter2"},
    )
    claude_home(
        tmp_path,
        monkeypatch,
        '{"headers":{"x-api-key":"hunter2-hunter2-hunter2"}}',
    )
    agent = ClaudeAgent(
        AgentConfig(model="m", effort="high", provider="work"), name="builder"
    )

    Runner(tmp_path / "flow", [agent]).run("go")
    (epic,) = epics()

    inside = held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert not any("hunter2" in said for said in inside.values()), inside
    (log,) = [one for one in inside if one.startswith("sessions/")]
    assert REDACTED in inside[log]
    # The account is still named, which is what the run was: an agent ran as `work`.
    assert manifest(tmp_path / "out.tar.gz")["agents"][0]["provider"] == "work"
