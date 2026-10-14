"""A CLI under a harness put on another machine, in a virtual home built on that machine.

The harness's machine is the fake `ssh`'s far side: this machine, under a home of its own. The
work lands on the same machine, so the harness there supervises a `local:` target. The flow's
skills are carried there first; the anchor there builds the home around the CLI it starts, out
of that machine's user's own configuration, and takes it away when the CLI is done.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import homes
from hmz.coganchor.anchor import AnchorConfig
from hmz.coganchor.backends import named
from hmz.coganchor.homes import Virtual
from hmz.coganchor.providers import redirect
from tests.integration.doubles_anchor import fakes

if TYPE_CHECKING:
    from tests.integration.doubles_anchor import Fakes

#: The CLI: says where its home is and what the flow's skill says, rewrites its settings there
#: and adds to its history -- one a copy of the user's, the other a link to it.
_CLI = (
    'printf "%s\\n" "$CLAUDE_CONFIG_DIR"; '
    'while IFS= read -r said; do printf "%s\\n" "$said"; done '
    '< "$CLAUDE_CONFIG_DIR/skills/review/SKILL.md"; '
    'echo \'{"rewritten": true}\' > "$CLAUDE_CONFIG_DIR/settings.json"; '
    'echo said >> "$CLAUDE_CONFIG_DIR/history.jsonl"'
)


def _turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Fakes, list[str]]:
    """The far machine, its user's Claude configured there, and the line that runs a turn there.

    Returns:
      The far side, and the command this machine spawns for the turn.
    """
    far = fakes(tmp_path, monkeypatch)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    theirs = far.home / ".claude"
    theirs.mkdir()
    (theirs / "settings.json").write_text('{"theirs": true}\n')
    (theirs / "history.jsonl").write_text("")
    project = tmp_path / "project"
    project.mkdir()
    skill = tmp_path / "flow" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("the flow's review\n")
    profile = named("claude")
    assert profile is not None
    home = homes.virtual(profile, [("review", str(skill))])
    config = AnchorConfig(
        target=f"ssh://box-{tmp_path.name}",
        harness="same",
        workspace=str(project),
        remote_path=str(project),
        home=home,
    )
    return far, config.command(["/bin/sh", "-c", _CLI])


def _told(line: list[str]) -> Virtual:
    """The virtual home the harness's machine is told to build, read out of the ssh line."""
    (said,) = [one for one in shlex.split(line[-1]) if one.startswith("--home=")]
    return Virtual.loads(said.removeprefix("--home="))


def test_the_flows_skills_are_put_on_the_harness_s_machine_for_its_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    far, line = _turn(tmp_path, monkeypatch)

    ((name, there),) = _told(line).skills
    assert name == "review"
    assert Path(there).is_relative_to(far.home / ".cache" / "humanize" / "skills")
    assert (Path(there) / "SKILL.md").read_text() == "the flow's review\n"
    assert _told(line).variable == "CLAUDE_CONFIG_DIR"


@pytest.mark.skipif(
    sys.platform != "linux" or not redirect.supervises(),
    reason="a harness supervises its CLI on linux alone",
)
def test_the_cli_runs_in_a_virtual_home_built_on_the_harness_s_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    far, line = _turn(tmp_path, monkeypatch)

    done = subprocess.run(
        line, capture_output=True, text=True, timeout=120, check=False
    )

    assert done.returncode == 0, done.stderr
    at, said = done.stdout.splitlines()
    assert said == "the flow's review"
    assert Path(at).name.startswith("hmz-home-")
    assert not Path(at).exists(), "taken away with the CLI"
    theirs = far.home / ".claude"
    assert json.loads((theirs / "settings.json").read_text()) == {"theirs": True}
    assert (theirs / "history.jsonl").read_text() == "said\n"
    assert not (theirs / "skills").exists()
