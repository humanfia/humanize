"""`hmz.coganchor.settings`: the one settings file, read forgivingly and written whole."""

from __future__ import annotations

import datetime
import os
import tomllib
from pathlib import Path
from typing import Any

import pytest

from hmz.coganchor import settings


def test_where_is_settings_toml_in_the_home() -> None:
    assert (
        settings.where()
        == Path(os.environ["XDG_CONFIG_HOME"]) / "humanize" / "settings.toml"
    )


def test_a_missing_file_holds_nothing() -> None:
    assert not settings.where().exists()
    assert settings.reading() == {}
    assert settings.read() == {}


@pytest.mark.parametrize(
    ("written", "reading"),
    [
        ("", {}),
        ("# only a comment\n", {}),
        ('a = 1\nb = ["x", "y"]\n', {"a": 1, "b": ["x", "y"]}),
        ("a = [unclosed\n", None),
        ("just a string\n", None),
        ("a = 1\na = 2\n", None),
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
    assert tomllib.loads(at.read_text(encoding="utf-8")) == {"a": 1}
    assert at.stat().st_mode & 0o777 == 0o600


def test_changes_keeps_every_other_part_and_the_files_mode() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text('keep = "me"\nchange = 1\n', encoding="utf-8")
    at.chmod(0o640)

    def change(held: dict[str, Any]) -> None:
        held["change"] = 2
        held["new"] = "ü"

    assert settings.changes(change) == {"keep": "me", "change": 2, "new": "ü"}
    assert settings.read() == {"keep": "me", "change": 2, "new": "ü"}
    assert at.stat().st_mode & 0o777 == 0o640
    assert "ü" in at.read_text(encoding="utf-8")  # unicode written as itself


def test_changes_keeps_the_comments_beside_what_it_leaves() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text(
        '# mine\nkeep = "me" # and this\n\n[table]\n# inside\nx = 1\n', encoding="utf-8"
    )
    settings.changes(lambda held: held["table"].update(y=2))
    said = at.read_text(encoding="utf-8")
    assert "# mine" in said
    assert "# and this" in said
    assert "# inside" in said
    assert settings.read() == {"keep": "me", "table": {"x": 1, "y": 2}}


def test_a_part_set_to_none_is_taken_out() -> None:
    settings.changes(lambda held: held.update(a=1, b={"c": 2, "d": 3}))
    held = settings.changes(lambda held: held.update(a=None, b={"c": None, "d": 3}))
    assert held == {"b": {"d": 3}}
    assert settings.read() == {"b": {"d": 3}}


def test_every_kind_of_value_comes_back_as_it_went() -> None:
    when = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)
    given = {
        "text": "a",
        "number": 7,
        "fraction": 0.5,
        "flag": False,
        "when": when,
        "list": ["a", 1],
        "rows": [{"name": "x", "under": {"deep": [1, 2]}}, {"name": "y"}],
        "nested": {"one": {"two": {"three": "four"}}},
        "empty": {},
        "none": [],
    }
    settings.changes(lambda held: held.update(given))
    held = settings.read()
    assert held == given
    assert type(held["nested"]) is dict
    rows: list[object] = held["rows"]
    assert type(rows) is list
    assert type(rows[0]) is dict


def test_changes_reads_the_file_again_rather_than_an_earlier_reading() -> None:
    settings.changes(lambda held: held.update(first=1))
    settings.where().write_text("first = 1\nbetween = 2\n", encoding="utf-8")
    settings.changes(lambda held: held.update(last=3))
    assert settings.read() == {"first": 1, "between": 2, "last": 3}


def test_changes_never_writes_over_a_file_it_cannot_read() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text("half = [edited\n", encoding="utf-8")
    with pytest.raises(OSError, match=r"settings\.toml cannot be read"):
        settings.changes(lambda held: held.update(a=1))
    assert at.read_text(encoding="utf-8") == "half = [edited\n"


def test_a_change_that_raises_leaves_the_file_as_it_was() -> None:
    settings.changes(lambda held: held.update(a=1))

    def change(held: dict[str, Any]) -> None:
        held["a"] = 2
        raise RuntimeError("halfway")

    with pytest.raises(RuntimeError, match="halfway"):
        settings.changes(change)
    assert settings.read() == {"a": 1}


def test_a_change_toml_cannot_hold_is_refused() -> None:
    with pytest.raises(ValueError, match="Unable to convert"):
        settings.changes(lambda held: held.update(a=object()))
    assert settings.read() == {}


def _former(said: str) -> Path:
    at = settings.where().with_name("settings.yaml")
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(said, encoding="utf-8")
    return at


def test_a_yaml_file_from_before_is_converted_once() -> None:
    former = _former(
        "a: 1\n"
        "gone: null\n"
        "nested:\n  x: {y: [1, 2]}\n  z: null\n"
        "rows:\n- {p: 1, q: null}\n- {p: 2}\n"
        "graph:\n  n:\n    on: {fault: m}\n"
    )
    former.chmod(0o644)
    expected = {
        "a": 1,
        "nested": {"x": {"y": [1, 2]}},
        "rows": [{"p": 1}, {"p": 2}],
        "graph": {"n": {"on": {"fault": "m"}}},
    }
    assert settings.read() == expected
    at = settings.where()
    assert tomllib.loads(at.read_text(encoding="utf-8")) == expected
    assert at.stat().st_mode & 0o777 == 0o600
    assert not former.exists()
    assert former.with_name("settings.yaml.migrated").read_text(encoding="utf-8")
    assert former.with_name(".settings.toml.lock").stat().st_mode & 0o777 == 0o600


def test_a_yaml_file_from_before_is_converted_by_a_write_too() -> None:
    _former("a: 1\n")
    assert settings.changes(lambda held: held.update(b=2)) == {"a": 1, "b": 2}
    assert settings.read() == {"a": 1, "b": 2}
    assert settings.where().with_name("settings.yaml.migrated").exists()


def test_a_toml_file_wins_over_a_yaml_one_beside_it() -> None:
    former = _former("a: 1\n")
    settings.where().write_text("b = 2\n", encoding="utf-8")
    assert settings.read() == {"b": 2}
    assert former.exists()
    assert not former.with_name("settings.yaml.migrated").exists()


def test_a_yaml_file_that_cannot_be_read_is_left_and_read_as_unreadable() -> None:
    former = _former("a: [unclosed\n")
    assert settings.reading() is None
    with pytest.raises(OSError, match=r"settings\.yaml cannot be read"):
        settings.changes(lambda held: held.update(b=2))
    assert former.read_text(encoding="utf-8") == "a: [unclosed\n"
    assert not settings.where().exists()


def test_a_change_of_type_alone_is_written() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text("details = 1\nflags = [1, 0]\ncost = 20\n", encoding="utf-8")
    settings.changes(
        lambda held: held.update(details=True, flags=[True, False], cost=20.0)
    )
    held = settings.read()
    assert held == {"details": True, "flags": [True, False], "cost": 20.0}
    assert type(held["details"]) is bool
    assert type(held["cost"]) is float
