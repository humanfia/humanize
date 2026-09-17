"""What Antigravity's driver reads off a home before it decides to restart the CLI.

The process is kept between turns, and what would make it wrong to keep -- the native
configuration the CLI was started under -- is a fingerprint taken off a directory. That
reading is a function of a home, an environment and a command line, so it is checked as one:
directories are made, `_native` is asked about them, and nothing is ever started.

The turns that process actually takes, against a stand-in on PATH, are next door in
`tests/integration/agents/test_agy_stream.py`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import hmz.coganchor.agents.agy as agy_driver

if TYPE_CHECKING:
    from pathlib import Path


def test_native_home_flag_tracks_custom_settings_without_runtime_databases(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    native = tmp_path / "isolated"
    native.mkdir()
    settings = native / "settings.json"
    settings.write_text('{"modelProvider":"gemini"}')
    environment = {"HOME": str(home)}
    args = ("--app_data_dir", os.path.relpath(native, home / ".gemini"))
    before = agy_driver._native(tmp_path, environment, args)
    database = native / "conversations/new.db"
    database.parent.mkdir()
    database.write_text("history")
    assert agy_driver._native(tmp_path, environment, args) == before
    settings.write_text('{"modelProvider":"gemini","verbosity":"high"}')
    assert agy_driver._native(tmp_path, environment, args) != before


def test_a_data_directory_flag_with_nothing_after_it_names_nothing(
    tmp_path: Path,
) -> None:
    """An empty value is not the whole of `~/.gemini`, which is a home read every turn."""
    home = tmp_path / "home"
    (home / ".gemini/antigravity-cli").mkdir(parents=True)
    (home / ".gemini/antigravity-cli/settings.json").write_text("{}")
    environment = {"HOME": str(home)}

    assert agy_driver._native(tmp_path, environment, ("--app_data_dir",)) == (
        agy_driver._native(tmp_path, environment, ())
    )


def test_a_native_home_flag_naming_nothing_leaves_the_default_home(
    tmp_path: Path,
) -> None:
    """Rather than collapsing onto the whole Gemini home and walking all of it."""
    home = tmp_path / "home"
    (home / ".gemini/antigravity-cli").mkdir(parents=True)
    (home / ".gemini/settings.json").write_text("{}")
    environment = {"HOME": str(home)}
    plain = agy_driver._native(tmp_path, environment, ())
    for args in (("--app_data_dir",), ("--app_data_dir=",)):
        assert agy_driver._native(tmp_path, environment, args) == plain
    # And the flag still moves the home when it names one.
    assert agy_driver._native(tmp_path, environment, ("--app_data_dir", "x")) != plain
