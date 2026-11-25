"""`hmz skills`, for real: the skill written into a home, and read as a harness reads it."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hmz import cli
from hmz.cli import tree
from hmz.coganchor import __version__
from hmz.coganchor.agents import skills
from hmz.sdk import Client

pytestmark = [pytest.mark.timeout(60)]


def test_the_skill_added_for_claude_is_one_claude_would_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # All of it is done on this machine's files: no daemon is there to be asked.
    monkeypatch.delattr(Client, "local")
    card = Path.home() / ".claude" / skills.SKILLS / "hmz" / skills.CARD

    assert cli.main(["skills", "add", "--for", "claude", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "version": __version__,
        "written": [{"harness": "claude", "path": str(card), "changed": True}],
    }
    (found,) = skills.skills("claude", tmp_path)
    assert (found.name, found.whose) == ("hmz", "yours")
    assert found.about.startswith("Works with Humanize through the hmz command line")
    # What it tells an agent to type is what there is to type: every line of it is read.
    listed = re.findall(
        r"^ *- `hmz ([a-z][a-z_. ]*)", card.read_text("utf-8"), re.MULTILINE
    )
    assert "skills add" in [one.strip() for one in listed]
    for line in listed:
        with pytest.raises(SystemExit) as raised:
            tree.runs([*line.split(), "--help"])
        assert raised.value.code == 0
    capsys.readouterr()

    assert cli.main(["skills", "list", "--for", "claude", "--json"]) == 0
    (claude,) = json.loads(capsys.readouterr().out)["harnesses"]
    assert (claude["state"], claude["version"]) == ("current", __version__)
    assert claude["installed"] is False

    assert cli.main(["skills", "remove", "--yes"]) == 0
    assert capsys.readouterr().out == f"Removed: {card}\n"
    assert skills.skills("claude", tmp_path) == []


def test_adding_where_no_harness_is_installed_is_refused_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["skills", "add"]) == 1

    assert capsys.readouterr().err == (
        "hmz skills add: No harness is installed here. Name a harness with `--for` or "
        "a folder with `--dir`.\n"
    )
    assert list(Path.home().iterdir()) == []
