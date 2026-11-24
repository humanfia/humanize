"""What the command line and the terminal interface say is the page's, or written for them.

Three things hold `hmz.words` to its word: the page's texts kept there are the page's texts
now, every text a command declares is one of them, and every text the new parts of the two
interfaces say through `t` is one of them -- so that no sentence is written where it is said.
"""

from __future__ import annotations

import ast
import importlib.util
import re
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
    "src/hmz/tui/pick.py",
)

#: What is held to more than that: no literal text reaches the screen of these but through
#: `t`. A file is added here once every text of it is said so.
WRITTEN_NOWHERE = ("src/hmz/tui/pick.py",)

#: The literals that are data and no text: a command's name, the prefix a failure is told
#: with, the start of a name made of an id.
PLAIN = frozenset({"/epics", "Ai-chan#", "hmz:", "ssh/"})

#: What carries a text to the screen, and which of its arguments are the texts: the widgets
#: and what a sheet says its rows, buttons, keys and refusals with.
_CARRIES = {
    "Label": (0,),
    "Static": (0,),
    "Option": (0,),
    "Text": (0,),
    "Button": (0,),
    "update": (0,),
    "notify": (0,),
    "Question": (1, 2),
    "Action": (1, 2),
    "Key": (1,),
    "Value": (1, 2),
    "Drop": (0,),
    "switched": (0, 2),
    "Dropdown": (0,),
    "ValueError": (0,),
    "OSError": (0,),
    "bad": (0,),
    "iffy": (0,),
    "escape": (0,),
    "append": (0,),
    "_tell": (1,),
}

#: The names a sheet keeps a text under until it is drawn.
_HELD = frozenset(
    {
        "asked",
        "about",
        "adds",
        "again",
        "ESC",
        "HEADED",
        "DONE",
        "KIND",
        "CHECKS",
        "ABOUT",
        "_wrong",
        "_said",
        "_noted",
        "said",
        "held",
    }
)

#: The methods a sheet answers a text from; `rows` answers each row as what it is kept under,
#: then what it says.
_SAYS = frozenset({"nothing", "note", "done_about", "means", "rows", "worded", "crumb"})

_MARKUP = re.compile(r"\[/?[^\]]*\]")
_WORD = re.compile(r"[A-Za-z]{2}")


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


def _literals(node: ast.expr, *, row: bool = False) -> Iterator[tuple[int, str]]:
    """The literals a value is made of, and their lines: not what a call makes of them."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.lineno, node.value
    elif isinstance(node, ast.JoinedStr):
        for part in node.values:
            yield from _literals(part)
    elif isinstance(node, ast.IfExp):
        yield from _literals(node.body, row=row)
        yield from _literals(node.orelse, row=row)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _literals(value, row=row)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        yield from _literals(node.left, row=row)
        yield from _literals(node.right, row=row)
    elif isinstance(node, (ast.Tuple, ast.List)):
        # The first of a row is what it is kept under, which is no text.
        skipped = 1 if row and isinstance(node, ast.Tuple) else 0
        for one in node.elts[skipped:]:
            yield from _literals(one, row=row)
    elif isinstance(node, ast.Starred):
        yield from _literals(node.value, row=row)
    elif isinstance(node, (ast.ListComp, ast.GeneratorExp)):
        yield from _literals(node.elt, row=row)


def _shown(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Every literal of a file that reaches the screen without `t`, and its line."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = node.func
            name = (
                called.attr
                if isinstance(called, ast.Attribute)
                else called.id
                if isinstance(called, ast.Name)
                else ""
            )
            for at in _CARRIES.get(name, ()):
                if at < len(node.args):
                    yield from _literals(node.args[at])
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {
                one.attr
                if isinstance(one, ast.Attribute)
                else one.id
                if isinstance(one, ast.Name)
                else ""
                for one in targets
            }
            if node.value is not None and names & _HELD:
                yield from _literals(node.value)
        elif isinstance(node, ast.FunctionDef) and node.name in _SAYS:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return) and inner.value is not None:
                    yield from _literals(inner.value, row=node.name == "rows")


def test_no_text_is_written_where_it_is_shown() -> None:
    written = sorted(
        {
            f"{under}:{line}: {said!r}"
            for under in WRITTEN_NOWHERE
            for line, text in _shown(
                ast.parse((ROOT / under).read_text(encoding="utf-8"))
            )
            if _WORD.search(said := _MARKUP.sub("", text).strip()) and said not in PLAIN
        }
    )

    assert not written, (
        "texts written where they are shown -- say them through `t`, or name them in "
        "PLAIN where they are data:\n" + "\n".join(written)
    )


@pytest.mark.parametrize("language", ["zh-Hans", "zh-Hant"])
def test_every_text_of_the_page_is_said_in_each_of_its_languages(language: str) -> None:
    words.speak(language)
    try:
        assert words.t("Cancel") == "取消"
        assert words.t("{n} sessions", n=2) != "2 sessions"
    finally:
        words.speak("en")
