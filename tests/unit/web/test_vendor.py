"""The page's third-party code, as the package ships it under `static/vendor/`.

Each bundle is there, says what it carries, exports what the page imports from it, and is of a
size that loads; the two that draw what an agent or a flow wrote (Markdown and charts) compile
no code at run time, as the page's policy refuses that.
"""

from __future__ import annotations

import re
from importlib import resources

import pytest

#: Each file, what it must export, and its size bounds in KiB.
_BUNDLES: dict[str, tuple[tuple[str, ...], int, int]] = {
    "markdown.js": (("render",), 20, 200),
    "vega.js": (("embed",), 300, 1500),
    "codemirror.js": (
        (
            "EditorState",
            "EditorView",
            "MergeView",
            "basicSetup",
            "languageFor",
            "languageName",
            "themeFor",
            "unifiedMergeView",
        ),
        300,
        2000,
    ),
    "xterm.js": (
        (
            "Terminal",
            "FitAddon",
            "SearchAddon",
            "WebLinksAddon",
            "Unicode11Addon",
            "WebglAddon",
        ),
        150,
        800,
    ),
}

#: An `export{a as b,c}` statement of a minified ES module.
_EXPORT = re.compile(r"export\s*\{([^}]*)\}")

#: Code compiled from a string: `eval(...)` that is neither a method call (`x.eval(`) nor a
#: method's definition (`eval(a,b){`), `eval` called indirectly (`(0,eval)(`, `eval?.(`),
#: `new Function(`, or `Function(` called bare.
_COMPILING = re.compile(
    r"(?<![\w$.])eval\((?![\w$,]*\)\{)|(?<![\w$.])eval(?:\)\(|\?\.\()"
    r"|\bnew\s+Function\(|(?<![\w$.])Function\("
)


def _text(name: str) -> str:
    return (
        resources.files("hmz.web").joinpath("static", "vendor", name).read_text("utf-8")
    )


def _exports(text: str) -> set[str]:
    names: set[str] = set()
    for group in _EXPORT.findall(text):
        for part in group.split(","):
            if part.strip():
                names.add(part.split(" as ")[-1].strip())
    return names


@pytest.mark.parametrize("name", sorted(_BUNDLES))
def test_each_bundle_exports_what_the_page_imports(name: str) -> None:
    exports, _, _ = _BUNDLES[name]

    assert set(exports) <= _exports(_text(name))


@pytest.mark.parametrize("name", sorted(_BUNDLES))
def test_each_bundle_is_of_a_size_that_loads(name: str) -> None:
    _, least, most = _BUNDLES[name]

    assert least * 1024 <= len(_text(name).encode()) <= most * 1024


@pytest.mark.parametrize("name", [*sorted(_BUNDLES), "xterm_css.css"])
def test_each_bundle_opens_with_the_licences_of_what_it_carries(name: str) -> None:
    assert _text(name).startswith(
        "/*! Third-party code, bundled by src/hmz/web/vendor/build.mjs."
    )


@pytest.mark.parametrize(
    ("name", "carries"),
    [
        ("markdown.js", ("marked@", "dompurify@")),
        ("vega.js", ("vega@", "vega-lite@", "vega-embed@", "vega-interpreter@")),
    ],
)
def test_markdown_and_charts_carry_the_packages_they_are_made_of(
    name: str, carries: tuple[str, ...]
) -> None:
    head = _text(name).split("*/", 1)[0]

    assert all(package in head for package in carries)


@pytest.mark.parametrize("name", ["markdown.js", "vega.js"])
def test_markdown_and_charts_compile_no_code_at_run_time(name: str) -> None:
    assert _COMPILING.findall(_text(name)) == []


@pytest.mark.parametrize("name", ["markdown.js", "vega.js"])
def test_markdown_and_charts_import_nothing(name: str) -> None:
    # Self-contained: no `import ... from`, no `import(...)`, so nothing beyond the file loads.
    text = _text(name).split("*/", 1)[1]

    assert re.search(r"\bimport(?:\s*[({*\"']|\s+[\w$])", text) is None


def test_the_compiling_check_sees_what_it_looks_for() -> None:
    assert _COMPILING.search("x=eval(s)")
    assert _COMPILING.search('f=new Function("d","return d")')
    assert _COMPILING.search("f=Function(...a)")
    assert _COMPILING.search("(0,eval)(s)")
    assert _COMPILING.search("eval?.(s)")
    assert not _COMPILING.search("this.eval(e,t)")
    assert not _COMPILING.search("},eval(e,t){return 1}")
    assert not _COMPILING.search("e instanceof Function&&f()")
