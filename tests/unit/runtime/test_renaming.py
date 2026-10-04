"""What was remembered under a flow's name before other places' flows were named after an `@`.

Settings keep, per workspace, the flow last run and what each flow was set up with, under the
flow's name. Those kept the old way -- `local/x`, `user/x`, `<flowverse>/x`, `official/x` --
are named as flows are named now, once and without a word; those kept since say so, and are
read as they were written whatever flowverse has since been added under the same name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from hmz import home
from hmz.runtime.flowing.verses import renamed, under
from hmz.runtime.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _theirs() -> None:
    """A flowverse called `theirs`, which is all `theirs/x` needs to have meant one of it."""
    (under() / "theirs").mkdir(parents=True)


@pytest.mark.parametrize(
    ("was", "now"),
    [
        ("local/x", "@local/x"),
        ("user/x:inner", "@user/x:inner"),
        ("theirs/review", "@theirs/review"),
        ("official/aot", "aot"),
        # Already as names are now, or nothing a name could have meant before.
        ("@local/x", "@local/x"),
        ("chat", "chat"),
        ("humanize1:rlcr", "humanize1:rlcr"),
        ("ghost/review", "ghost/review"),
        ("./flows/x", "./flows/x"),
        ("/abs/x", "/abs/x"),
        ("git+https://example.invalid/r#x", "git+https://example.invalid/r#x"),
    ],
)
def test_a_name_said_the_old_way_is_said_as_names_are_now(was: str, now: str) -> None:
    assert renamed(was) == now


def _kept(workspace: Path, held: dict[str, object]) -> Path:
    """Writes a settings file as an older humanize did: unmarked, for one workspace."""
    file = home() / "settings.yaml"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        yaml.safe_dump({"workspaces": {str(workspace.resolve()): held}}),
        encoding="utf-8",
    )
    return file


def test_settings_kept_the_old_way_are_read_as_flows_are_named_now(
    tmp_path: Path,
) -> None:
    file = _kept(
        tmp_path,
        {
            "flow": "local/x",
            "flows": {
                "local/x": {"budget": {"cost": 1.0}},
                "theirs/review": {"params": {"loud": True}},
                "official/aot": {"profile": True},
                "chat": {"agents": {}},
            },
        },
    )

    settings = Settings(tmp_path)

    assert settings.flow == "@local/x"
    assert sorted(settings.flows()) == ["@local/x", "@theirs/review", "aot", "chat"]
    assert settings.budget("@local/x") == {"cost": 1.0}
    assert settings.params("@theirs/review") == {"loud": True}
    assert settings.profile("aot") is True
    assert yaml.safe_load(file.read_text())["naming"] == 2  # once, and said so


def test_settings_written_since_are_read_as_they_were_written(tmp_path: Path) -> None:
    """`theirs/review` written since is a flow of humanize's, whatever `theirs` is now."""
    Settings(tmp_path).remember("theirs/review", {}, budget={"cost": 1.0})

    settings = Settings(tmp_path)

    assert settings.flow == "theirs/review"
    assert settings.budget("theirs/review") == {"cost": 1.0}
