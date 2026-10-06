"""`hmz.coganchor.settings`: the one settings file, read forgivingly and written whole."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from hmz.coganchor import settings


def test_where_is_settings_yaml_in_the_home() -> None:
    assert settings.where() == Path(os.environ["HUMANIZE_HOME"]) / "settings.yaml"


def test_a_missing_file_holds_nothing() -> None:
    assert not settings.where().exists()
    assert settings.reading() == {}
    assert settings.read() == {}


@pytest.mark.parametrize(
    ("written", "reading"),
    [
        ("", {}),
        ("# only a comment\n", {}),
        ("a: 1\nb: [x, y]\n", {"a": 1, "b": ["x", "y"]}),
        ("- a list\n", None),
        ("just a string\n", None),
        ("a: [unclosed\n", None),
        (":\n  - : -\n\t", None),
    ],
)
def test_reading_tells_unreadable_from_empty(
    written: str, reading: dict[str, Any] | None
) -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text(written, encoding="utf-8")
    assert settings.reading() == reading
    assert settings.read() == (reading or {})


def test_a_file_that_cannot_be_opened_reads_as_unreadable() -> None:
    settings.where().mkdir(parents=True)  # a directory where the file should be
    assert settings.reading() is None
    assert settings.read() == {}


def test_changes_writes_a_new_file_private() -> None:
    held = settings.changes(lambda held: held.update(a=1))
    assert held == {"a": 1}
    at = settings.where()
    assert yaml.safe_load(at.read_text(encoding="utf-8")) == {"a": 1}
    assert at.stat().st_mode & 0o777 == 0o600


def test_changes_keeps_every_other_part_and_the_files_mode() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text("keep: me\nchange: 1\n", encoding="utf-8")
    at.chmod(0o640)

    def change(held: dict[str, Any]) -> None:
        held["change"] = 2
        held["new"] = "ü"

    assert settings.changes(change) == {"keep": "me", "change": 2, "new": "ü"}
    assert settings.read() == {"keep": "me", "change": 2, "new": "ü"}
    assert at.stat().st_mode & 0o777 == 0o640
    assert "ü" in at.read_text(encoding="utf-8")  # unicode written as itself


def test_changes_reads_the_file_again_rather_than_an_earlier_reading() -> None:
    settings.changes(lambda held: held.update(first=1))
    settings.where().write_text("first: 1\nbetween: 2\n", encoding="utf-8")
    settings.changes(lambda held: held.update(last=3))
    assert settings.read() == {"first": 1, "between": 2, "last": 3}


def test_changes_never_writes_over_a_file_it_cannot_read() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text("half: [edited\n", encoding="utf-8")
    with pytest.raises(OSError, match="cannot be read as YAML"):
        settings.changes(lambda held: held.update(a=1))
    assert at.read_text(encoding="utf-8") == "half: [edited\n"


def test_a_change_that_raises_leaves_the_file_as_it_was() -> None:
    settings.changes(lambda held: held.update(a=1))

    def change(held: dict[str, Any]) -> None:
        held["a"] = 2
        raise RuntimeError("halfway")

    with pytest.raises(RuntimeError, match="halfway"):
        settings.changes(change)
    assert settings.read() == {"a": 1}


def test_a_change_yaml_cannot_hold_is_refused() -> None:
    with pytest.raises(yaml.YAMLError):
        settings.changes(lambda held: held.update(a=object()))
    assert settings.read() == {}
