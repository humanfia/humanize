"""What the command line and the terminal interface say is the page's, or written for them.

Three things hold `hmz.words` to its word: the page's texts kept there are the page's texts
now, every text a command declares is one of them, and every text the new parts of the two
interfaces say through `t` is one of them -- so that no sentence is written where it is said.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz import words
from hmz.cli import tree
from hmz.tui import shell

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]

#: What is written to the rule that every text is one of `hmz.words`: the commands that are
#: declarations, and the shell of the terminal interface with its views.
SAID_THROUGH_T = (
    "src/hmz/cli/tree.py",
    "src/hmz/cli/commands",
    "src/hmz/tui/shell.py",
    "src/hmz/tui/views",
    "src/hmz/tui/settings.py",
    "src/hmz/tui/usage.py",
    "src/hmz/tui/flows.py",
    "src/hmz/tui/stored.py",
    "src/hmz/tui/dropdown.py",
    "src/hmz/tui/selecting.py",
    "src/hmz/tui/chats.py",
    "src/hmz/tui/complete.py",
    "src/hmz/tui/asking.py",
    "src/hmz/tui/epic.py",
    "src/hmz/tui/envs.py",
    "src/hmz/tui/monitoring.py",
    "src/hmz/tui/exomyth.py",
)


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_pages_texts_kept_are_the_pages_texts_now() -> None:
    kept = ROOT / "src/hmz/words/gui"

    for name, text in _script("words_gui").written().items():
        assert (kept / name).read_text(encoding="utf-8") == text, (
            f"src/hmz/words/gui/{name} is stale: run `uv run python scripts/words_gui.py`"
        )


def _declared() -> Iterator[tuple[str, str]]:
    for name, command in tree.commands().items():
        for text in command.texts():
            yield name, text
    for status in tree.EXITS:
        yield "every command", status.says
    for arg in tree.COMMON:
        yield "every command", arg.says
    for name, view in shell.views().items():
        for text in (view.title, view.hint, *(does for _, does in view.keys)):
            if text:
                yield name, text


def test_every_text_a_command_or_a_view_declares_is_one_of_the_words() -> None:
    unknown = sorted(
        {f"{where}: {text!r}" for where, text in _declared() if not words.known(text)}
    )

    assert not unknown, (
        "texts written where they are said -- take the page's own, or have "
        "scripts/words_argon.py write them:\n" + "\n".join(unknown)
    )


def _through_t() -> Iterator[tuple[str, int, str]]:
    for under in SAID_THROUGH_T:
        at = ROOT / under
        for source in sorted(at.rglob("*.py")) if at.is_dir() else [at]:
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "t"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    yield str(source.relative_to(ROOT)), node.lineno, node.args[0].value


def test_every_text_said_through_t_is_one_of_the_words() -> None:
    unknown = [
        f"{source}:{line}: {text!r}"
        for source, line, text in _through_t()
        if not words.known(text)
    ]

    assert not unknown, "\n".join(unknown)


@pytest.mark.parametrize("language", ["zh-Hans", "zh-Hant"])
def test_every_text_of_the_page_is_said_in_each_of_its_languages(language: str) -> None:
    words.speak(language)
    try:
        assert words.t("Cancel") == "取消"
        assert words.t("{n} sessions", n=2) != "2 sessions"
    finally:
        words.speak("en")
