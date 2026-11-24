"""The CLI reference says of the declared commands what the commands say of themselves.

The part of `docs/reference/cli.md` between its markers is written by
`scripts/cli_reference.py` from the declarations, and is held here to be what that writes now:
a command added or changed without the page is a page that says something untrue.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from hmz import cli
from hmz.cli import tree

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def colourless(monkeypatch: pytest.MonkeyPatch) -> None:
    """Help read plain: a workflow sets `FORCE_COLOR`, which bolds it and colours argparse's."""
    for name in ("FORCE_COLOR", "NO_COLOR"):
        monkeypatch.delenv(name, raising=False)


def _script() -> ModuleType:
    at = ROOT / "scripts" / "cli_reference.py"
    spec = importlib.util.spec_from_file_location("cli_reference", at)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_reference_is_what_the_declarations_write_now() -> None:
    script = _script()

    assert script.PAGE.read_text(encoding="utf-8") == script.written(), (
        "docs/reference/cli.md is stale: run `uv run python scripts/cli_reference.py`"
    )
    assert script.main(["--check"]) == 0


def test_every_command_is_listed_and_every_declared_one_has_a_section() -> None:
    script = _script()

    listing = script.listing()
    for name in cli.summaries():
        assert f"| `{name}` |" in listing, name
    section = script.section()
    for name, command in tree.commands().items():
        assert f"## hmz {name}\n" in section
        for one in command.commands:
            assert f"### hmz {name} {one.name}\n" in section
    # What a table would take for a column, or a page for a tag, is written so it is not.
    assert "`string\\|null`" in section


def test_a_stale_page_is_said_and_left_alone_under_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    page = tmp_path / "docs" / "cli.md"
    page.parent.mkdir()
    stale = (
        f"before\n{script.LISTED[0]}\nold\n{script.LISTED[1]}\nbetween\n"
        f"{script.DECLARED[0]}\n{script.DECLARED[1]}\nafter\n"
    )
    page.write_text(stale, encoding="utf-8")
    monkeypatch.setattr(script, "PAGE", page)
    monkeypatch.setattr(script, "ROOT", tmp_path)

    assert script.main(["--check"]) == 1
    assert "is stale" in capsys.readouterr().err
    assert page.read_text(encoding="utf-8") == stale

    assert script.main([]) == 0
    written = page.read_text(encoding="utf-8")
    assert written.startswith(f"before\n{script.LISTED[0]}\n\n| About | Command |")
    assert "\nbetween\n" in written
    assert written.endswith(f"{script.DECLARED[1]}\nafter\n")
    assert "old" not in written.split("between")[0].split("| About")[0]
    assert script.main(["--check"]) == 0
