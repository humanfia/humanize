"""Writes `src/hmz/words/gui/*.json`: every text the web page says, and what it is elsewhere.

The page's English is written where it is said, as `t('…')`, and its translations are kept one
catalog a language under `src/hmz/web/static/i18n`. The command line and the terminal interface
say the same texts, so they read them from here rather than from JavaScript: this lifts the
literals and the catalogs out, and `tests/integration/test_web_words.py` fails where what is
kept is not what this writes.

    uv run python scripts/words_gui.py          # write
    uv run python scripts/words_gui.py --check  # exit 1 where the kept files are stale
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src/hmz/web/static"
KEPT = ROOT / "src/hmz/words/gui"
LANGUAGES = ("en", "zh-Hans", "zh-Hant")

#: A call that says a text, up to the quote its first argument opens with.
_SAID = re.compile(r"(?<![\w.$])(?:t|pieces)\(\s*(?=['\"`])")
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", '"': '"', "`": "`", "\n": ""}


def literal(source: str, at: int) -> tuple[str, int] | None:
    """The JavaScript string opening at `at`, and where it ends; None for a template with holes."""
    quote, out, here = source[at], [], at + 1
    while here < len(source):
        char = source[here]
        if char == "\\":
            follows = source[here + 1]
            if follows == "u":
                out.append(chr(int(source[here + 2 : here + 6], 16)))
                here += 6
                continue
            out.append(_ESCAPES.get(follows, follows))
            here += 2
            continue
        if char == quote:
            return "".join(out), here + 1
        if quote == "`" and source.startswith("${", here):
            return None
        out.append(char)
        here += 1
    return None


def said(source: str) -> list[str]:
    """Every text a script says through `t` or `pieces`, in the order it says them."""
    found = []
    for match in _SAID.finditer(source):
        one = literal(source, match.end())
        if one is not None:
            found.append(one[0])
    return found


def catalog(source: str) -> dict[str, str | dict[str, str]]:
    """What one fragment of a catalog holds: each English text, and what it is there."""
    body = source[source.index("export default {") + len("export default {") :]
    held: dict[str, str | dict[str, str]] = {}
    here = 0
    while True:
        here = _skips(body, here)
        if body[here] == "}":
            return held
        key, here = _string(body, here)
        here = _skips(body, here)
        if body[here] != ":":
            raise ValueError(f"expected ':' after {key!r}")
        here = _skips(body, here + 1)
        if body[here] == "{":
            forms: dict[str, str] = {}
            here = _skips(body, here + 1)
            while body[here] != "}":
                name = re.match(r"\w+", body[here:])
                if name is None:
                    raise ValueError(f"expected a plural form in {key!r}")
                here = _skips(body, here + name.end())
                here = _skips(body, here + 1)
                forms[name[0]], here = _string(body, here)
                here = _skips(body, here)
                if body[here] == ",":
                    here = _skips(body, here + 1)
            held[key], here = forms, here + 1
        else:
            held[key], here = _string(body, here)
        here = _skips(body, here)
        if body[here] == ",":
            here += 1


def _string(body: str, at: int) -> tuple[str, int]:
    one = literal(body, at) if body[at] in "'\"`" else None
    if one is None:
        raise ValueError(f"expected a string at {body[at : at + 40]!r}")
    return one


def _skips(body: str, at: int) -> int:
    """Past the spaces and comments at `at`."""
    while True:
        while body[at].isspace():
            at += 1
        if body.startswith("//", at):
            at = body.index("\n", at)
        elif body.startswith("/*", at):
            at = body.index("*/", at) + 2
        else:
            return at


def written() -> dict[str, str]:
    """Each kept file's name, and what it should hold."""
    texts: set[str] = set()
    for script in sorted(STATIC.rglob("*.js")):
        inside = script.relative_to(STATIC).parts
        if inside[0] in ("vendor", "i18n"):
            continue
        texts.update(said(script.read_text(encoding="utf-8")))
    held: dict[str, dict[str, str | dict[str, str]]] = {}
    for language in LANGUAGES:
        held[language] = {}
        for fragment in sorted((STATIC / "i18n" / language).glob("*.js")):
            held[language].update(catalog(fragment.read_text(encoding="utf-8")))
    # English keeps every text said, each as itself unless it has plural forms; a text only a
    # catalog knows is one the page stopped saying, and is left out of all three.
    english: dict[str, str | dict[str, str]] = {
        text: held["en"].get(text, text) for text in sorted(texts)
    }
    out = {"en": english}
    for language in LANGUAGES[1:]:
        out[language] = {
            text: held[language][text] for text in english if text in held[language]
        }
    return {
        f"{language}.json": json.dumps(
            texts_, ensure_ascii=False, indent=1, sort_keys=True
        )
        + "\n"
        for language, texts_ in out.items()
    }


def main(argv: list[str]) -> int:
    """Writes the kept files, or with `--check` says which are stale."""
    stale = []
    for name, text in written().items():
        path = KEPT / name
        if "--check" in argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for name in stale:
        print(
            f"src/hmz/words/gui/{name} is stale: run scripts/words_gui.py",
            file=sys.stderr,
        )
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
