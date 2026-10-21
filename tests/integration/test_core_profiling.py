"""A run profiled: the flow's own Python, the programs its agents start, or both.

Each run is a real `python -m hmz exec` of `chat` driving the stand-in `claude`; what it wrote
down is read back, and laid out, through `hmz.sdk.Hmz.epics`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.runtime.tracing.profile import FLOW_PROFILE, PROFILE
from hmz.sdk import Hmz
from tests.integration.doubles_core import AGENT, hmz_exec, install

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    ("flags", "flow", "environment"),
    [
        (("--profile-flow", "--profile-environment"), True, True),
        (("--profile-flow",), True, False),
        (("--profile-environment",), False, True),
    ],
)
def test_what_a_run_was_asked_to_profile_is_written_and_laid_out(
    project: Path, flags: tuple[str, ...], flow: bool, environment: bool
) -> None:
    # A program the agent runs for longer than the environment's sampler takes to see it,
    # with room for a machine busy running the rest of the suite beside it.
    task = 'run: [["sleep", "2"]]'
    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", *flags, task)
    assert ran.returncode == 0, ran.stderr

    epics = Hmz(project).epics
    (epic,) = epics.all()
    said = epics.read(epic)
    assert said is not None
    assert (said.profile_flow, said.profile_environment) == (flow, environment)
    assert (epic / FLOW_PROFILE).is_file() is flow
    assert (epic / PROFILE).is_file() is environment

    document = epics.timeline(epic).document
    strings = document["strings"]
    kinds = [one["kind"] for one in document["processes"]]
    python = [
        one
        for one in document["processes"]
        if one["kind"] == "flow" and strings[one["name"]] == "python"
    ]
    if flow:
        # Under the epic, a lane of frames nested in what called them: the chat flow's own
        # code, among them, inside whatever ran it.
        (lane,) = python
        assert lane["parent"] == 0
        (track,) = lane["tracks"]
        held = document["tracks"][track]
        assert strings[held["name"]] == "flow"
        assert held["depths"] > 1
        names = {strings[one] for one in held["spans"]["name"]}
        assert any("chat" in one for one in names)
    else:
        assert python == []
    assert ("os" in kinds) is environment
