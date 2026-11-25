"""What the command line and the terminal interface say, which is what the web page says.

One text is one English sentence wherever it is read: a button the page calls `Archive` is
`Archive` in a menu of the terminal interface and in a line of `hmz chat --help`. So the page's
texts are kept here (`gui/`, lifted out of the page by `scripts/words_gui.py`) with what each is
in the languages the page is written in, and a text the page has no need of is written once
(`argon/`, one file an area, written by `scripts/words_argon.py`) rather than wherever it is
said. As on the page, the English text is what a text is looked up by.
"""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import Final

__all__ = ["LANGUAGES", "known", "language", "speak", "t", "texts"]

#: Every language a text can be said in, and what the language calls itself.
LANGUAGES: Final = {"en": "English", "zh-Hans": "简体中文", "zh-Hant": "繁體中文"}

#: What tells two English homographs apart, which is no part of what is said.
_NOTE = re.compile(r"@@.*$", re.DOTALL)
_NAME = re.compile(r"\{(\w+)\}")

_spoken = "en"

type _Forms = dict[str, str]
type _Catalog = dict[str, str | _Forms]


@cache
def _gui(lang: str) -> _Catalog:
    held = resources.files(__name__).joinpath("gui", f"{lang}.json")
    return json.loads(held.read_text(encoding="utf-8"))


@cache
def _argon() -> dict[str, str | None]:
    """Each area's texts, and what one that counts is for exactly one."""
    found: dict[str, str | None] = {}
    for held in resources.files(__name__).joinpath("argon").iterdir():
        if held.name.endswith(".json"):
            for entry in json.loads(held.read_text(encoding="utf-8"))["entries"]:
                if entry.get("text"):
                    found[entry["text"]] = entry.get("one") or None
    return found


def texts() -> frozenset[str]:
    """Every text there is to say: the page's, and each area's own."""
    return frozenset(_gui("en")) | frozenset(_argon())


def known(text: str) -> bool:
    """Whether a text is one of them, and so was written by the page or for an area."""
    return text in _gui("en") or text in _argon()


def language() -> str:
    """The language texts are said in: one of `LANGUAGES`."""
    return _spoken


def speak(lang: str) -> None:
    """Says every text after this in a language.

    Args:
      lang: One of `LANGUAGES`; a tag naming a kind of one (`zh-CN`, `en_US.UTF-8`) is taken
        for it, and anything else for English.
    """
    global _spoken  # noqa: PLW0603 -- one language a process, as one a page
    tag = lang.replace("_", "-").split(".")[0].lower()
    if tag.startswith("zh"):
        traditional = any(part in tag for part in ("hant", "tw", "hk", "mo"))
        _spoken = "zh-Hant" if traditional else "zh-Hans"
    else:
        _spoken = "en"


def _form(forms: _Forms, lang: str, n: object) -> str:
    """The plural form a number takes: English has two, Chinese one."""
    if lang == "en" and n in (1, "1") and "one" in forms:
        return forms["one"]
    return forms["other"]


def t(text: str, /, **given: object) -> str:
    """A text, in the language being spoken, with what is given put at its `{names}`.

    Args:
      text: The English text; `@@note` after it where the same English is two texts.
      **given: What is put at each name; `n` is the number a plural is picked by. A name given
        nothing stays as written.

    Returns:
      It, or the English where the language has none.
    """
    lang = _spoken if text in _gui(_spoken) else "en"
    found = _gui(lang).get(text)
    if found is None:
        # An area's own text, which is English only, or one nobody wrote down: as it is.
        one = _argon().get(text)
        found = one if one and given.get("n") in (1, "1") else _NOTE.sub("", text)
    elif not isinstance(found, str):
        found = _form(found, lang, given.get("n"))
    if lang == "en":
        found = _NOTE.sub("", found)
    return _NAME.sub(lambda name: str(given.get(name[1], name[0])), found)
