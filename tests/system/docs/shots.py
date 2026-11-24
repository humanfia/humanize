"""The docs' pictures: SVG files made from the real interfaces, still or moving.

The documentation holds no video and no drawing of an interface made by hand. Every picture
of Humanize Desktop, of the web page, of the terminal interface or of a command's output is
an SVG written here from the interface itself, so that it draws as the real thing does:

- the web page (and the desktop app's window, which is that page) is printed by Chromium to
  a PDF and read back as vector paths, text and all, then held against a screenshot of the
  same page: a picture that does not rasterize to that screenshot fails its scene;
- the terminal interface is Textual's own screen (`App.export_screenshot`), and a command's
  output is what it wrote to a real terminal, both drawn by Rich in one terminal window and
  then turned into paths the same way, so that no picture depends on a font of the reader's;
- a `Reel` is several such frames in one SVG, played in a loop by CSS inside the file: it
  moves when loaded with `<img src>`, with no script and nothing fetched, and stands still on
  one frame for a reader who asked for less motion.

Light and dark
==============

Every picture is two files, written side by side from one run of its scene: `<name>.svg` is
the interface drawn light and `<name>.dark.svg` the same interface, at the same instant,
drawn dark -- the same size, the same frames, the same timing. The docs show whichever the
reader's theme asks for. A scene calls nothing twice and says nothing of it:

- a web page is taken as it draws where the system asks for light colours and again where
  it asks for dark ones (`page.emulate_media`), and is left in the scheme the scene had it
  in. From before the first to after the last its animations stand still, and so does what
  it had waiting -- its timers, and word from its daemon (`GATE`, which `world.page()` opens
  every page with) -- and afterwards the page is turned back and photographed once more:
  if it is not as it began, both sides are taken again, and a page that changes under every
  take fails its scene, so no pair is of two instants. Each side is held to its own
  screenshot. The window drawn around it and the pointer over it are of the same side;
- the terminal interface opens in humanfia, which has a light theme and a dark one as the
  page has: the screen as it stands is drawn in each (`_interface`), the light picture in a
  light window and the dark in a dark one, and the app is left in the theme it was in;
- a command's output is one terminal's in two profiles: a command writes in the terminal's
  own colours, so the dark picture is of a terminal with a dark profile and the light one
  of a terminal with a light profile -- a white window, dark ink, sixteen colours that read
  on white, its two whites greys as such a profile has them (`_profiles`) -- and a command
  runs once. The interface started in the terminal's colours (`TEXTUAL_THEME=terminal`,
  which `docs/user/themes.md` is about) is drawn the same way: rendered once, exported in
  each profile;
- where the colours are the scene's own subject the two files may be one picture: a page a
  scene pins to Light or Dark in its settings draws that side whatever the system asks, and
  a terminal interface started in a theme of Textual's (`TEXTUAL_THEME`) names every colour
  itself.

No scene opens the page dark to get a dark picture (`world.page(dark=True)` is what the
system asks while the scene drives the page, and both sides are taken all the same).

Writing a scene
===============

A scene is a test in `tests/system/docs/test_docs_<page>.py`, one file per docs page. It
stages what the picture shows with the `world` fixture (`conftest.py`, which is the other
half of this cookbook), drives the interface as a person would, and takes its pictures::

    from playwright.sync_api import expect

    from tests.system.docs import shots
    from tests.system.docs.conftest import World
    from tests.system.web.doubles_browser import go


    def test_a_chat(world: World) -> None:
        world.says({"coupon": "Checkout takes a coupon now: WELCOME10 is 10% off."})
        chat = world.chat("Add a coupon code to checkout")
        with world.page() as page:
            go(page, f"/chats/{chat}")
            expect(page.get_by_role("log")).to_contain_text("WELCOME10")
            shots.web(page, "chat-answered")                        # the whole window
            box = page.get_by_role("textbox", name="What to say")
            shots.web(page, "chat-box", clip=box, pad=48)           # one part of it

            reel = shots.Reel("chat-new")
            go(page, "/new/chat")
            box = page.get_by_role("textbox", name="First message")
            reel.web(page, hold=1.2, pointer=box, click=True)       # the pointer goes there
            reel.type(page, box, "Add a coupon code to checkout")   # and the words are typed
            ...
            reel.save()

The scenes beside this (`test_docs_<section>_<page>.py`) are whole scenes of each kind: start
from the one nearest what you need.

- `web(page, name, clip=, window=)` -- the page, or one part of it, as a still.
  `window="desktop"` draws the macOS app's window around it (open the page with
  `world.page(desktop=True)`, which is the page as that window draws it), `"browser"` a
  browser's.
- `tui(app, name)` -- the terminal interface's screen (`world.tui()` runs the app).
- `cli(argv, name)` -- a command run in a real terminal under the staged home, and what it
  printed, after the line that ran it.
- `splash(state, detail, name)` -- Humanize Desktop's launch window in one of its states.
- `Reel(name)` then `.web(...)`, `.type(...)`, `.tui(...)`, `.cli(...)`, `.splash(...)` a
  frame at a time, and `.save()`.

Run one file by naming it, which takes about a second a still and a few a reel::

    uv run pytest tests/system/docs/test_docs_<page>.py

Never in CI, and never part of a plain `uv run pytest`: a browser is driven only under
`tests/system`. It needs, on the machine it runs on:

- Chromium: `uv run playwright install chromium`;
- a `coganchor` built for this checkout (`cargo build` in `crates/coganchor`), or one of
  another checkout named in `HUMANIZE_COGANCHOR`: the stand-in agents are fenced by it;
- to run outside any sandbox of its caller's, since that fence is a sandbox of its own.

A picture that does not draw as its screenshot fails saying which file it is and where they
differ, and neither of its two files is written. Set `HMZ_SHOTS_KEEP` to a directory to
have both kept there, and look at them.

Names and sizes
===============

A picture is written to `docs/public/shots/<name>.svg`, with `<name>.dark.svg` beside it,
and a page shows it as `![what it shows](/shots/<name>.svg)`: it names the light file, and
the site shows the one of its theme. Name it `<page>-<what>` in lower case with dashes
(`chat-new`, `desktop-splash-installing`), so that two pages never write one file. A still
is held to `STILL` bytes (200 kB) and a reel to `REEL` (500 kB, the most the repository's
commit hook lets any file be), each of its two files by itself: crop to what the page is
about (`clip=`), take fewer frames, or show less on screen. A still of a whole window is
80 to 180 kB; one of an epic's graph or of a long form is more, and where the whole window
is what the page is about, say so with `most=shots.REEL`. A reel costs its first frame and
then what changes: 15 frames of a page are some 160 kB, a terminal's less.

Nothing private
===============

A picture shows nothing of the machine it was made on. `world` stages a person (`alex`), a
machine (`studio`), a home and a project (`~/shop`) under a temporary directory, stand-in
agents and stand-in flows; a scene adds only made-up names to it -- never a real account,
key, path or project. Text is drawn as paths, so nothing can be searched for afterwards:
look at each picture you write, both files of it (open the SVG in a browser), before you
leave it.

What it cannot do
=================

- Only Chromium prints a page to vectors, so the desktop app's window is drawn by Chromium
  saying it is the app (as `tests/system/web` drives it), not by WKWebView.
- A page is printed from its top: scroll what is inside the page, never the document itself.
- Nothing moves inside one frame: what moves to an end is waited for, and what moves for
  ever, as a spinner does, is held where it stands for the instant the frame is taken.
- The dark picture of a page is of the page told, that instant, that the system is dark: a
  page that draws something only as it loads, and never again when the system changes, keeps
  it as it was.
- What is held between a page's two sides is what was waiting when the first was taken. What
  a page does without a timer or its socket -- a script drawing every frame, an answer to a
  request it had sent -- is not held, only caught: the take is made again, and a page that
  never stands still fails. A page opened without `GATE` (not by `world.page()`) holds
  nothing, and is only caught.
- A terminal's cursor blinks, and is in a picture or not as the frame fell; both sides are
  of one screen, so in both or in neither.
- A selection is not shown as one: a print leaves its ground out, so a frame is taken with
  what is selected drawn as what is not.
- What the browser can only print as pixels -- a canvas, as the trace's timeline is, a soft
  shadow, a picture -- is pixels in the SVG too, and what makes a picture large.
- Dates and times are the real ones, of when the scene ran, in this machine's time zone,
  and an agent's own name (`Nammou320`) is made up anew each run.
"""

from __future__ import annotations

import base64
import concurrent.futures
import contextlib
import dataclasses
import fcntl
import html
import io
import json
import math
import os
import pty
import re
import select
import shlex
import struct
import subprocess
import sys
import termios
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from playwright.sync_api import Browser, CDPSession, Locator, Page
    from rich.console import Console
    from rich.terminal_theme import TerminalTheme
    from rich.text import Text
    from textual.app import App

__all__ = [
    "APP",
    "DESKTOP",
    "GATE",
    "REEL",
    "SHOTS",
    "SIDES",
    "STILL",
    "Reel",
    "cli",
    "splash",
    "tui",
    "web",
]

#: Where the pictures are written: what the docs serve as `/shots/<name>.svg`.
SHOTS = Path(__file__).resolve().parents[3] / "docs" / "public" / "shots"

#: The two sides every picture is written on: light (False), then dark (True). The light one
#: is `<name>.svg` and the dark one `<name>.dark.svg`, which the docs show by their theme.
SIDES = (False, True)

#: The most bytes a still may be, each of its two files.
STILL = 200_000

#: The most bytes a reel may be, each of its two files: what the commit hook
#: (`check-added-large-files`) lets in.
REEL = 500_000

#: How large Humanize Desktop's window opens, which is what a picture of it is drawn at
#: (`inner_size` in `desktop/src-tauri/src/lib.rs`).
DESKTOP = (1280, 820)

#: What a window is drawn around a picture as: a browser's, or the macOS app's.
type Window = Literal["browser", "desktop"]

#: Where on a page something is: a locator, a selector, or a point in CSS pixels.
type Where = Locator | str | tuple[float, float]

#: What the macOS app's window says it is (`chrome.rs`): the page draws its top row by it.
APP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) humanize-desktop/0.0.0"
)

#: The home of whoever runs the suite, read before a test names another: a browser's own.
_HOME = str(Path.home())

#: The splash the app's window opens on.
_SPLASH = Path(__file__).resolve().parents[3] / "desktop" / "ui" / "app" / "index.html"

#: A PDF is measured in points, a page in CSS pixels.
_PX = 96 / 72

#: How far two pixels may differ in any one colour before they count as different, and the
#: share of a picture's pixels that may: text drawn as paths is smoothed a little otherwise.
_FAR = 48
_SHARE = 0.003

#: The share that may in a terminal drawn light: a screen of dark letters on white, where a
#: letter and its ground are the whole range of a pixel apart, and the little by which a
#: letter's edge is smoothed otherwise as a path crosses `_FAR` all along it. Nothing that
#: goes missing hides in it: that is still all of a square (`_PATCH`).
_INK = 0.015

#: And how much of any one square of it may, the square this many half pixels a side: a small
#: thing gone missing -- an icon, a badge -- is a small share of a picture, and all of a square.
_TILE = 8
_PATCH = 0.4

#: How many CSS pixels a picture in a page is drawn across before it counts as a large one.
_LARGE = 200 * 200

#: The fewest bytes of drawing worth saying once and naming where it repeats.
_WORTH = 100

#: The font a terminal is drawn in: one every Mac has, as paths in the picture.
_MONO = 'Menlo, "DejaVu Sans Mono", "Liberation Mono", monospace'

_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?")
_MATRIX = re.compile(r"matrix\(([^)]*)\)")
_URL = re.compile(r"url\(#([^)]+)\)")
_HREF = "{http://www.w3.org/1999/xlink}href"
_ID = re.compile(r'<\w+ id="([^"]+)"')
_NAMED = re.compile(r'(?:href="#|url\(#)([^")]+)')


# --------------------------------------------------------------------------------------
# A drawing, read out of what the browser printed.
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Box:
    """A rectangle, by its corner and size."""

    x: float
    y: float
    width: float
    height: float

    def meets(self, other: _Box, by: float = 0.0) -> bool:
        """Whether it comes within `by` of another."""
        return (
            self.x - by < other.x + other.width
            and other.x < self.x + self.width + by
            and self.y - by < other.y + other.height
            and other.y < self.y + self.height + by
        )

    def scaled(self, by: float) -> _Box:
        return _Box(self.x * by, self.y * by, self.width * by, self.height * by)


def _number(value: float, places: int) -> str:
    """A number as an SVG writes it shortest: rounded, no trailing zeros, no leading one."""
    said = f"{value:.{places}f}"
    if "." in said:
        said = said.rstrip("0").rstrip(".")
    if said in ("-0", ""):
        return "0"
    if said.startswith("0."):
        return said[1:]
    if said.startswith("-0."):
        return "-" + said[2:]
    return said


def _rounded(text: str, places: int) -> str:
    """Every number in a path or a list, rounded.

    A number may be parted from the one before it by nothing but its own sign or point
    (`656-0.4`, `1.5.004`): where rounding takes that away, a space is put in its place, or
    the two would be read as one (`6560`) and a letter drawn with a stray line off it.
    """

    def one(found: re.Match[str]) -> str:
        said = _number(float(found.group()), places)
        joined = found.start() and text[found.start() - 1] in "0123456789."
        return f" {said}" if joined and said[0] not in "-." else said

    return _NUMBER.sub(one, text)


def _outline(path: str) -> str:
    """A path with its numbers rounded as finely as its size needs: to four figures of it.

    Never coarser than a hundredth: a glyph may be drawn in thousandths of its font's em,
    or in ems, where a hundredth is a tenth of a letter.
    """
    most = max((abs(float(one)) for one in _NUMBER.findall(path)), default=1.0)
    return _rounded(path, max(2, 3 - math.floor(math.log10(most or 1.0))))


def _matrix(transform: str | None) -> tuple[float, float, float, float, float, float]:
    """A `matrix(...)` transform's six numbers, or the one that changes nothing."""
    found = _MATRIX.search(transform or "")
    if not found:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    a, b, c, d, e, f = (float(one) for one in found.group(1).split(","))
    return (a, b, c, d, e, f)


def _transform(transform: str) -> str:
    """A transform with its scale kept fine and where it moves to rounded to a hundredth."""
    a, b, c, d, e, f = _matrix(transform)
    scale = ",".join(_number(one, 8 if abs(one) < 0.01 else 5) for one in (a, b, c, d))
    return f"matrix({scale},{_number(e, 2)},{_number(f, 2)})"


def _extent(path: str, transform: str | None) -> _Box | None:
    """The box around a path's points, moved by its transform: no smaller than the path."""
    a, b, c, d, e, f = _matrix(transform)
    xs: list[float] = []
    ys: list[float] = []
    x = y = 0.0
    for command, numbers in re.findall(r"([A-Za-z])([^A-Za-z]*)", path):
        given = [float(one) for one in _NUMBER.findall(numbers)]
        if command == "H":
            points = [(one, y) for one in given]
        elif command == "V":
            points = [(x, one) for one in given]
        elif command.isupper():
            points = list(zip(given[::2], given[1::2], strict=False))
        else:
            # A relative command, which MuPDF never writes: nothing is known of the box.
            if command not in "zZ":
                return None
            points = []
        for x, y in points:
            xs.append(a * x + c * y + e)
            ys.append(b * x + d * y + f)
    if not xs:
        return None
    return _Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _written(tag: str, attributes: dict[str, str], inner: str = "") -> str:
    """One element as text."""
    said = "".join(
        f' {name}="{html.escape(value)}"' for name, value in attributes.items()
    )
    return f"<{tag}{said}>{inner}</{tag}>" if inner else f"<{tag}{said}/>"


class _Defs:
    """What a picture says once and names wherever it is drawn: glyphs, clips, images.

    Named by what it is, so that the same glyph of two frames is one definition, and no name
    of one frame is another's.
    """

    def __init__(self) -> None:
        self._names: dict[str, str] = {}
        self._said: list[str] = []
        #: The box of each clip, by its name, in the points it was printed in.
        self.boxes: dict[str, _Box] = {}

    def put(self, tag: str, attributes: dict[str, str], inner: str = "") -> str:
        """Names one definition, the same name for the same thing."""
        key = _written(tag, attributes, inner)
        name = self._names.get(key)
        if name is None:
            name = self._names[key] = f"d{_base36(len(self._names))}"
            self._said.append(_written(tag, {"id": name, **attributes}, inner))
        return name

    def written(self, by: str) -> str:
        """The definitions a drawing names, and those they name in turn: no others."""
        said = {_ID.match(one).group(1): one for one in self._said}  # pyright: ignore[reportOptionalMemberAccess]
        wanted: dict[str, None] = {}
        reading = [by]
        while reading:
            for name in _NAMED.findall(reading.pop()):
                if name in said and name not in wanted:
                    wanted[name] = None
                    reading.append(said[name])
        return "".join(one for name, one in said.items() if name in wanted)


def _base36(number: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    said = ""
    while True:
        number, at = divmod(number, 36)
        said = digits[at] + said
        if not number:
            return said


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


@dataclasses.dataclass
class _Read:
    """One printed page being read: its own names for what `_Defs` names, and what is kept."""

    defs: _Defs
    keep: _Box | None
    names: dict[str, str] = dataclasses.field(default_factory=dict[str, str])
    blank: set[str] = dataclasses.field(default_factory=set[str])

    def define(self, element: ET.Element) -> None:
        """Takes one of the page's definitions into the picture's, under what it is."""
        was = element.get("id", "")
        tag = _tag(element)
        children = list(element)
        if tag == "g" and len(children) == 1 and _tag(children[0]) == "path":
            # A glyph: one outline, in the units of its font, which are far finer than any
            # size it is drawn at.
            (path,) = children
            transform = path.get("transform", "")
            fine = abs(_matrix(transform)[0]) < 0.01
            if not path.get("d", "").strip():
                # A space: nothing is drawn of it, wherever it stands.
                self.blank.add(was)
                return
            self.names[was] = self.defs.put(
                "path",
                {
                    "transform": _transform(transform),
                    "d": _rounded(path.get("d", ""), 0)
                    if fine
                    else _outline(path.get("d", "")),
                },
            )
            return
        cleaned = self.clean(element, within=False)
        assert cleaned is not None
        if tag == "image":
            # Named already, as a picture is wherever it stands.
            return
        cleaned.attrib.pop("id", None)
        name = self.defs.put(tag, dict(cleaned.attrib), _inner(cleaned))
        self.names[was] = name
        if tag == "clipPath" and len(children) == 1 and _tag(children[0]) == "path":
            box = _extent(children[0].get("d", ""), children[0].get("transform"))
            if box is not None:
                self.defs.boxes[name] = box

    def clean(
        self,
        element: ET.Element,
        *,
        within: bool = True,
        scale: float = 1.0,
        moved: bool = False,
    ) -> ET.Element | None:
        """One element as the picture keeps it, or None where it is out of what is kept.

        Args:
          element: The element, as MuPDF wrote it.
          within: Whether it is drawn in the page, not one of its definitions.
          scale: How many points one of its units is drawn as, by what it is inside.
          moved: Whether what it is inside moves it from where its own numbers say.
        """
        tag = _tag(element)
        attributes: dict[str, str] = {}
        for name, value in element.attrib.items():
            plain = name.rsplit("}", 1)[-1]
            if plain == "data-text" or (name.startswith("{") and plain != "href"):
                continue
            if plain == "href" and value.startswith("#"):
                attributes["href"] = f"#{self.names.get(value[1:], value[1:])}"
            elif plain == "transform":
                attributes[plain] = _transform(value) if "matrix" in value else value
            elif plain == "d":
                attributes[plain] = _outline(value)
            else:
                attributes[plain] = _URL.sub(
                    lambda found: (
                        f"url(#{self.names.get(found.group(1), found.group(1))})"
                    ),
                    value,
                )
        if tag == "use" and element.get(_HREF, "")[1:] in self.blank:
            return None
        # Only what stands where it says it does: inside something moved, it stands elsewhere.
        if within and not moved and self.keep and self._outside(tag, attributes):
            return None
        if "transform" in attributes and tag != "use":
            moved = True
        if "matrix" in attributes.get("transform", ""):
            scale *= abs(_matrix(attributes["transform"])[0])
        if tag == "image" and attributes.get("href", "").startswith("data:"):
            # A picture in the page, said once however many frames show it, and no finer
            # than twice the size it is drawn at.
            was = attributes.pop("id", "")
            if within:
                attributes = _no_finer(attributes, scale * _PX)
            name = self.defs.put("image", attributes)
            if was:
                self.names[was] = name
            return ET.Element("use", {"href": f"#{name}"})
        cleaned = ET.Element(tag, attributes)
        cleaned.extend(
            _lines(
                kept
                for child in element
                if (kept := self.clean(child, within=within, scale=scale, moved=moved))
                is not None
            )
        )
        if tag == "g" and len(element) and not len(cleaned):
            return None
        return cleaned

    def _outside(self, tag: str, attributes: dict[str, str]) -> bool:
        """Whether an element is drawn wholly outside what is kept, as far as can be told."""
        assert self.keep is not None
        if tag == "g" and (found := _URL.match(attributes.get("clip-path", ""))):
            box = self.defs.boxes.get(found.group(1))
            return box is not None and not box.meets(self.keep)
        if tag == "use" and "transform" in attributes:
            *_, x, y = _matrix(attributes["transform"])
            # A glyph, which stands at its origin: within a line of text of it.
            return not _Box(x, y, 0, 0).meets(self.keep, 48)
        return False


def _lines(elements: Iterable[ET.Element]) -> list[ET.Element]:
    """Elements with each run of glyphs on one line, in one colour, said as one group.

    MuPDF places every glyph by a whole transform and its colour. Glyphs that follow one
    another at one size, on one baseline, in one colour, are a group with that said once,
    each glyph only as far along the line as it stands, in the glyph's own units.
    """
    said: list[ET.Element] = []
    run: list[ET.Element] = []
    last: tuple[object, ...] | None = None

    def close() -> None:
        if len(run) < 2:
            said.extend(run)
        else:
            a, b, c, d, e, f = _matrix(run[0].get("transform"))
            line = ET.Element(
                "g",
                {
                    "transform": _transform(f"matrix({a},{b},{c},{d},{e},{f})"),
                    "fill": run[0].get("fill", ""),
                },
            )
            for one in run:
                along = (_matrix(one.get("transform"))[4] - e) / a
                placed = {"href": one.get("href", "")}
                if along:
                    placed["x"] = _number(along, 4)
                line.append(ET.Element("use", placed))
            said.append(line)
        run.clear()

    for element in elements:
        key: tuple[object, ...] | None = None
        if element.tag == "use" and set(element.attrib) == {
            "href",
            "transform",
            "fill",
        }:
            a, b, c, d, _, f = _matrix(element.get("transform"))
            if a and not b and not c:
                key = (a, d, f, element.get("fill"))
        if key != last:
            close()
        last = key
        if key is None:
            said.append(element)
        else:
            run.append(element)
    close()
    return said


def _no_finer(image: dict[str, str], scale: float) -> dict[str, str]:
    """A picture's attributes, its pixels no finer than the size it is drawn at needs.

    A page draws a small picture from a large file -- an avatar of 256 pixels in a circle of
    28 -- and the file would be most of the SVG: a small picture is kept at twice the pixels
    it is drawn across, for a screen that has them. A large one is what the browser could
    only print as pixels -- a canvas, a soft shadow, a ground of fine lines -- and is kept
    at the pixels it is drawn across.

    Args:
      image: The attributes of the `<image>`.
      scale: How many CSS pixels one of its units is drawn as.
    """
    import pymupdf

    try:
        wide, tall = float(image["width"]), float(image["height"])
    except (KeyError, ValueError):
        return image
    kind, _, data = image["href"].partition(",")
    if "base64" not in kind:
        return image
    held: Any = pymupdf.Pixmap(base64.b64decode(data))
    finer = 1 if wide * scale * tall * scale > _LARGE else 2
    width, height = math.ceil(wide * scale * finer), math.ceil(tall * scale * finer)
    if width * 1.2 > held.width or height * 1.2 > held.height:
        return image
    smaller: Any = pymupdf.Pixmap(held, width, height, None)
    said = base64.b64encode(smaller.tobytes("png")).decode()
    return image | {
        "href": f"data:image/png;base64,{said}",
        "preserveAspectRatio": "none",
    }


def _inner(element: ET.Element) -> str:
    return "".join(_whole(child) for child in element)


def _whole(element: ET.Element) -> str:
    return _written(element.tag, dict(element.attrib), _inner(element))


def _read(svg: str, defs: _Defs, keep: _Box | None) -> list[ET.Element]:
    """What MuPDF wrote of one page, as the picture keeps it: in points, named by `defs`."""
    root = ET.fromstring(svg)  # noqa: S314 -- written by MuPDF a line above, not fetched
    reading = _Read(defs, keep)
    body: list[ET.Element] = []
    for child in root:
        if _tag(child) == "defs":
            for one in child:
                reading.define(one)
        else:
            body.append(child)
    while len(body) == 1 and _tag(body[0]) == "g" and not body[0].attrib:
        body = list(body[0])
    return _lines(kept for one in body if (kept := reading.clean(one)) is not None)


@dataclasses.dataclass
class _Frame:
    """One picture of an interface: what is drawn, where in it is shown, and its screenshot.

    Attributes:
      drawn: What is drawn, in the points it was printed in.
      at: The part of it shown, in CSS pixels of what was printed.
      png: The same part as the browser's own screenshot, which the drawing is held to.
      share: The share of its pixels that may differ from that screenshot's.
    """

    drawn: list[ET.Element]
    at: _Box
    png: bytes
    share: float = _SHARE


class _Sharing:
    """Writes frames out, saying once whatever several of them draw alike."""

    def __init__(self, defs: _Defs, frames: Sequence[_Frame]) -> None:
        self._defs = defs
        self._text: dict[int, str] = {}
        self._times: dict[str, int] = {}
        for frame in frames:
            for element in frame.drawn:
                self._count(element)

    def _said(self, element: ET.Element) -> str:
        said = self._text.get(id(element))
        if said is None:
            said = self._text[id(element)] = _whole(element)
        return said

    def _count(self, element: ET.Element) -> None:
        said = self._said(element)
        self._times[said] = self._times.get(said, 0) + 1
        # What is inside something already seen is shared with it, and counts for nothing.
        if self._times[said] == 1:
            for child in element:
                self._count(child)

    def _write(self, element: ET.Element) -> str:
        said = self._said(element)
        inner = "".join(self._write(child) for child in element)
        if self._times.get(said, 0) > 1 and len(said) >= _WORTH:
            name = self._defs.put(element.tag, dict(element.attrib), inner)
            return f'<use href="#{name}"/>'
        return _written(element.tag, dict(element.attrib), inner)

    def frame(self, frame: _Frame, x: float = 0, y: float = 0) -> str:
        """One frame, set with its corner at a point of the picture, cut to what it shows."""
        drawn = "".join(self._write(element) for element in frame.drawn)
        at = frame.at
        scaled = f'<g transform="scale({_number(_PX, 6)})">{drawn}</g>'
        if (x, y, at.x, at.y) == (0, 0, 0, 0):
            # Its own corner at the picture's: the picture's own box cuts it.
            return scaled
        box = " ".join(_number(one, 2) for one in (at.x, at.y, at.width, at.height))
        return (
            f'<svg x="{_number(x, 2)}" y="{_number(y, 2)}" width="{_number(at.width, 2)}"'
            f' height="{_number(at.height, 2)}" viewBox="{box}">{scaled}</svg>'
        )


def _document(
    width: float, height: float, defs: str, body: str, style: str = ""
) -> str:
    """A whole SVG file."""
    size = f"{_number(width, 2)} {_number(height, 2)}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size}"'
        f' width="{_number(width, 2)}" height="{_number(height, 2)}">'
        + (f"<style>{style}</style>" if style else "")
        + (f"<defs>{defs}</defs>" if defs else "")
        + body
        + "</svg>"
    )


# --------------------------------------------------------------------------------------
# Taking a frame of a page, and holding it to the page.
# --------------------------------------------------------------------------------------


def _take(
    page: Page,
    defs: Mapping[bool, _Defs],
    at: _Box | None = None,
    *,
    clear: bool = False,
    sides: Sequence[bool] = SIDES,
    share: float = _SHARE,
    live: bool = True,
) -> dict[bool, _Frame]:
    """One frame of a page of Chromium's as it stands, or of one part of it, on each side.

    The page is taken as it draws where the system asks for light colours, and again where
    it asks for dark ones, and the two are of one interface: from before the first until
    after the last its animations stand still and, on a page opened with `GATE`, so does
    what it had waiting -- a timer that was running, word from its daemon. Between the two
    the page is told the other scheme, and waited for until it has redrawn in it, the
    colours it fades between brought to their end; afterwards it is put back in the scheme
    the scene left it in.

    That they are of one interface is checked, not hoped: once both are taken the page is
    turned back to the first scheme and photographed again, and where that is not the
    photograph it began with -- something moved that nothing here holds -- both sides are
    taken anew.

    Args:
      page: The page.
      defs: What the picture it is a frame of names, on each side.
      at: The part of the page shown, in CSS pixels, or None for all of it.
      clear: Whether the page has no ground of its own, and is drawn on none.
      sides: The sides taken: light (False), dark (True), or both.
      share: The share of a frame's pixels that may differ from its screenshot's.
      live: Whether the page may change by itself while it is taken, as an interface does
        and a sheet of the pictures' own does not.

    Returns:
      The frame of each side.

    Raises:
      AssertionError: If the page changed under every one of `_AGAIN` takes of its sides.
    """
    size = page.viewport_size
    assert size is not None, "the page has no window"
    whole = _Box(0, 0, size["width"], size["height"])
    at = at or whole
    page.evaluate(_SETTLED)
    was = _dark(page)
    # As the scene left it first: nothing is turned for that one.
    order = sorted(sides, key=lambda side: side != was)
    checked = live and len(order) > 1
    chromium = page.context.new_cdp_session(page)
    _told(chromium, "Animation.enable")
    _told(chromium, "Animation.setPlaybackRate", {"playbackRate": 0})
    _gate(page, shut=True)
    taken: dict[bool, tuple[bytes, str]] = {}
    try:
        began = ended = b""
        for _ in range(_AGAIN):
            began = b""
            for dark in order:
                _turn(page, dark, media="screen")
                page.evaluate(_HELD)
                try:
                    if checked and not began:
                        began = _shot(page, at, clear, caret=False)
                    taken[dark] = _both(page, chromium, whole, at, clear)
                finally:
                    page.evaluate(_LET_GO)
            if not checked:
                break
            _turn(page, was, media="screen")
            page.evaluate(_HELD)
            try:
                ended = _shot(page, at, clear, caret=False)
            finally:
                page.evaluate(_LET_GO)
            if _same(began, ended):
                break
        else:
            kept = "; set HMZ_SHOTS_KEEP to a directory to keep both and look"
            if keep := os.environ.get("HMZ_SHOTS_KEEP"):
                stem = Path(keep) / f"moved-{time.time_ns()}"
                stem.parent.mkdir(parents=True, exist_ok=True)
                stem.with_suffix(".began.png").write_bytes(began)
                stem.with_suffix(".ended.png").write_bytes(ended)
                kept = f"; the two are kept as {stem}.began.png and .ended.png"
            raise AssertionError(
                f"the page changed under each of {_AGAIN} takes of its light and its dark"
                " side, so the two would not be pictures of one interface: its photograph"
                " after the last is not its photograph before the first -- wait for what"
                " is arriving before the frame is taken" + kept
            )
    finally:
        _turn(page, was, media="null")
        _gate(page, shut=False)
        _told(chromium, "Animation.setPlaybackRate", {"playbackRate": 1})
        chromium.detach()
    keep = None if at == whole else at.scaled(1 / _PX)
    return {
        dark: _Frame(
            _read(_vectors(base64.b64decode(printed)), defs[dark], keep),
            at,
            png,
            share,
        )
        for dark, (png, printed) in taken.items()
    }


#: How far one colour of a pixel may be from itself in two photographs of a page that did
#: not change, and how many pixels may be further: a page turned dark and back is drawn
#: again, and a hair of an edge falls a shade otherwise. A letter that changed is hundreds.
_SHADE = 24
_STRAY = 4


def _same(one: bytes, other: bytes) -> bool:
    """Whether two photographs are of a page that stood still between them."""
    if one == other:
        return True
    import pymupdf

    a: Any = pymupdf.Pixmap(one)
    b: Any = pymupdf.Pixmap(other)
    if (a.width, a.height, a.n) != (b.width, b.height, b.n):
        return False
    row = a.width * a.n
    ours, theirs = cast("bytes", a.samples), cast("bytes", b.samples)
    stray = 0
    for at in range(0, len(ours), row):
        mine, yours = ours[at : at + row], theirs[at : at + row]
        if mine == yours:
            continue
        for x in range(0, row, a.n):
            if any(
                abs(mine[x + part] - yours[x + part]) > _SHADE for part in range(a.n)
            ):
                stray += 1
                if stray > _STRAY:
                    return False
    return True


def _gate(page: Page, *, shut: bool) -> None:
    """Holds what every frame of a page has waiting, or lets it go: see `GATE`."""
    for frame in page.frames:
        # A frame that went as it was asked, or a page opened without the gate.
        with contextlib.suppress(Exception):
            frame.evaluate(
                "(shut) => window.__hmzShotsGate && window.__hmzShotsGate(shut)", shut
            )


def _both(
    page: Page, chromium: CDPSession, whole: _Box, at: _Box, clear: bool
) -> tuple[bytes, str]:
    """A page's screenshot, and the page as printed just after: a PDF, in base 64."""
    png = _shot(page, at, clear)
    printed = _told(
        chromium,
        "Page.printToPDF",
        {
            "printBackground": True,
            "paperWidth": whole.width / 96,
            "paperHeight": whole.height / 96,
            "marginTop": 0,
            "marginBottom": 0,
            "marginLeft": 0,
            "marginRight": 0,
            "preferCSSPageSize": False,
        },
    )
    return png, printed["data"]


def _shot(page: Page, at: _Box, clear: bool, *, caret: bool = True) -> bytes:
    """The browser's own screenshot of one part of a page.

    With the caret of a box being typed in, as a frame shows it, or without: the caret
    blinks by the browser's clock, which nothing holds, and two photographs that are held
    to each other are taken without it.
    """
    return page.screenshot(
        clip={"x": at.x, "y": at.y, "width": at.width, "height": at.height},
        omit_background=clear,
        caret="initial" if caret else "hide",
    )


def _dark(page: Page) -> bool:
    """Whether the system a page is on asks for dark colours, as the page is told it does."""
    return bool(page.evaluate("matchMedia('(prefers-color-scheme: dark)').matches"))


def _turn(page: Page, dark: bool, *, media: Literal["screen", "null"]) -> None:
    """Tells a page which colours the system asks for, and waits until it draws in them.

    A page that follows the system redraws: its stylesheet at once, and what a script of
    its own paints -- a canvas, an editor, a frame inside it -- a moment after. What fades
    from one colour to the other is brought to its end, since the page's clock is held.
    """
    turned = _dark(page) != dark
    page.emulate_media(media=media, color_scheme="dark" if dark else "light")
    if not turned:
        return
    for _ in range(2):
        page.evaluate(_REDRAWN)
        for frame in page.frames:
            with contextlib.suppress(Exception):
                frame.evaluate(_FADED)
    page.evaluate("new Promise((done) => requestAnimationFrame(() => done(true)))")


def _told(
    chromium: CDPSession, method: str, params: dict[str, Any] | None = None
) -> Any:
    """Tells Chromium one thing over its own protocol, and answers what it said."""
    return cast("dict[str, Any]", cast("Any", chromium).send(method, params))


def _vectors(printed: bytes) -> str:
    """A page printed as a PDF, read back as an SVG: every letter the path it is drawn by.

    Raises:
      AssertionError: If it was printed on more than one sheet.
    """
    import pymupdf

    pdf: Any
    with pymupdf.open(stream=printed, filetype="pdf") as pdf:
        assert pdf.page_count == 1, (
            f"the page was printed on {pdf.page_count} sheets, not one: the document itself"
            " scrolls, or something in it grew taller than the window once printed"
        )
        return str(pdf[0].get_svg_image(text_as_path=True))


def _where(page: Page, where: Where, pad: float = 0) -> _Box:
    """The box of something on a page, with room around it, within the page."""
    size = page.viewport_size
    assert size is not None
    if isinstance(where, tuple):
        return _Box(where[0], where[1], 0, 0)
    found = (page.locator(where) if isinstance(where, str) else where).bounding_box()
    assert found is not None, f"{where} is not on the page"
    left = max(0, math.floor(found["x"] - pad))
    top = max(0, math.floor(found["y"] - pad))
    right = min(size["width"], math.ceil(found["x"] + found["width"] + pad))
    bottom = min(size["height"], math.ceil(found["y"] + found["height"] + pad))
    return _Box(left, top, right - left, bottom - top)


def _point(page: Page, where: Where) -> tuple[float, float]:
    """The middle of something on a page."""
    box = _where(page, where)
    return (box.x + box.width / 2, box.y + box.height / 2)


#: Waits, for a second at most, until whatever is moving on the page to an end has got
#: there -- a button changing colour, a panel sliding in -- so that a frame is of the page
#: at rest; what moves for ever, as a spinner does, is held where it stands instead. Then
#: says again where the caret is, which starts it showing: a box being typed in is printed
#: with its caret, whenever in its blinking the frame is taken.
_SETTLED = """async () => {
  const ending = document.getAnimations().filter((one) => {
    const timing = one.effect && one.effect.getComputedTiming()
    return one.playState === 'running' && timing && Number.isFinite(timing.endTime)
  })
  await Promise.race([
    Promise.allSettled(ending.map((one) => one.finished)),
    new Promise((done) => setTimeout(done, 1000)),
  ])
  const box = document.activeElement
  if (box && typeof box.selectionStart === 'number') {
    const [from, to, way] = [box.selectionStart, box.selectionEnd, box.selectionDirection]
    box.setSelectionRange(to === 0 ? 1 : 0, to === 0 ? 1 : 0)
    box.setSelectionRange(from, to, way)
  }
  await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))
}"""

#: Waits for a page told another colour scheme to have redrawn in it: for the scripts that
#: listen for the change, the shortest of which answer a moment later, and two frames.
_REDRAWN = """async () => {
  await new Promise((done) => setTimeout(done, 90))
  await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))
}"""

#: Brings every colour a document is fading to another to the end of its fade: the page's
#: clock is held while a frame is taken, and a fade begun then would stand at its start.
_FADED = """() => {
  for (const one of document.getAnimations())
    if (one instanceof CSSTransition) one.finish()
}"""

#: How many times the two sides of a frame are taken before the scene fails: each time the
#: page is found to have changed between its first photograph and its last.
_AGAIN = 4

#: Run in a page before any script of its own (`world.page()` does), this lets `_take` hold
#: what the page has waiting while its two sides are taken, so that both are of one instant:
#: a timer set before the hold -- a tip about to come up, a count of seconds, a poll -- does
#: not fire until it ends, and what the daemon says over the page's socket is not heard
#: until then, in the order it came. A timer set during the hold runs as ever: it is the
#: page answering the change of scheme. Nothing is changed while nothing is held.
GATE = """(() => {
  if (window.__hmzShotsGate) return
  let hold = 0
  let holds = 0
  const waiting = new Map()
  const mail = []
  for (const name of ['setTimeout', 'setInterval']) {
    const native = window[name]
    window[name] = function (callback, ...rest) {
      if (typeof callback !== 'function') return native.call(this, callback, ...rest)
      const born = hold
      const id = native.call(this, function (...given) {
        if (!hold || hold === born) return callback.apply(this, given)
        waiting.set(id, () => callback.apply(this, given))
      }, ...rest)
      return id
    }
  }
  for (const name of ['clearTimeout', 'clearInterval']) {
    const native = window[name]
    window[name] = function (id) {
      waiting.delete(id)
      return native.call(this, id)
    }
  }
  const Socket = window.WebSocket
  if (Socket)
    window.WebSocket = class extends Socket {
      constructor(...given) {
        super(...given)
        super.addEventListener('message', (event) => {
          if (!hold) return
          event.stopImmediatePropagation()
          mail.push([this, event])
        })
      }
    }
  window.__hmzShotsGate = (shut) => {
    hold = shut ? ++holds : 0
    if (shut) return
    const late = [...waiting.values()]
    waiting.clear()
    for (const run of late) run()
    for (const [socket, { data, origin, lastEventId }] of mail.splice(0))
      socket.dispatchEvent(new MessageEvent('message', { data, origin, lastEventId }))
  }
})()"""

#: Holds everything that scrolls to the height it has, and lets it go again. Printed, a page
#: is laid out anew as paper, and what scrolls inside a column that shares its height out may
#: be given the height of all it holds, pushing what stands under it off the sheet. And shows
#: what is selected as what is not, for as long: a print leaves a selection's ground out, and
#: on a dark page that ground is far from what is under it.
_HELD = """() => {
  const plain = document.createElement('style')
  plain.textContent =
    '*::selection { background-color: transparent !important; color: currentColor !important }'
  document.head.appendChild(plain)
  window.__hmzShotsPlain = plain
  window.__hmzShotsHeld = [...document.querySelectorAll('*')].flatMap((one) => {
    if (!/auto|scroll/.test(getComputedStyle(one).overflowY)) return []
    if (one.scrollHeight <= one.clientHeight + 1) return []
    const was = ['height', 'minHeight', 'maxHeight'].map((name) => [name, one.style[name]])
    const tall = `${one.getBoundingClientRect().height}px`
    for (const [name] of was) one.style[name] = tall
    return [[one, was]]
  })
}"""
_LET_GO = """() => {
  for (const [one, was] of window.__hmzShotsHeld || [])
    for (const [name, value] of was) one.style[name] = value
  delete window.__hmzShotsHeld
  if (window.__hmzShotsPlain) window.__hmzShotsPlain.remove()
  delete window.__hmzShotsPlain
}"""

_COMPARE = """async ([drawn, shot, far, tile]) => {
  const load = (address) => new Promise((done, failed) => {
    const image = new Image()
    image.onload = () => done(image)
    image.onerror = () => failed(new Error('a picture did not load'))
    image.src = address
  })
  const [a, b] = await Promise.all([load(drawn), load(shot)])
  // At half size, each pixel the mean of four: how a letter's edge is smoothed differs
  // between text and the same text as paths, and what is drawn there does not.
  const wide = Math.ceil(b.width / 2), tall = Math.ceil(b.height / 2)
  const pixels = (image) => {
    // Drawn at its own size first: an SVG drawn small is drawn anew, not averaged.
    const whole = new OffscreenCanvas(b.width, b.height)
    whole.getContext('2d').drawImage(image, 0, 0, b.width, b.height)
    const canvas = new OffscreenCanvas(wide, tall)
    const context = canvas.getContext('2d')
    context.imageSmoothingQuality = 'high'
    context.drawImage(whole, 0, 0, wide, tall)
    return context.getImageData(0, 0, wide, tall).data
  }
  const p = pixels(a), q = pixels(b)
  const across = Math.ceil(wide / tile)
  const tiles = new Uint32Array(across * Math.ceil(tall / tile))
  let differing = 0
  for (let i = 0; i < p.length; i += 4) {
    const d = Math.max(Math.abs(p[i] - q[i]), Math.abs(p[i + 1] - q[i + 1]),
      Math.abs(p[i + 2] - q[i + 2]), Math.abs(p[i + 3] - q[i + 3]))
    if (d <= far) continue
    differing++
    const x = (i / 4) % wide, y = Math.floor(i / 4 / wide)
    tiles[Math.floor(y / tile) * across + Math.floor(x / tile)]++
  }
  const worst = tiles.indexOf(Math.max(...tiles))
  return [differing, wide * tall, tiles[worst], (worst % across) * tile * 2,
    Math.floor(worst / across) * tile * 2, a.width, a.height, b.width, b.height]
}"""


def _address(data: bytes, kind: str) -> str:
    return f"data:{kind};base64,{base64.b64encode(data).decode()}"


def _faithful(
    browser: Browser, svg: str, png: bytes, what: str, share: float = _SHARE
) -> None:
    """Fails unless an SVG rasterizes, in the browser, to the screenshot it was made beside.

    Raises:
      AssertionError: If more than `share` of its pixels are further than `_FAR` from the
        screenshot's, or more than `_PATCH` of any one square of it.
    """
    page = browser.new_page()
    try:
        differing, of, worst, x, y, *sizes = page.evaluate(
            _COMPARE,
            [
                _address(svg.encode(), "image/svg+xml"),
                _address(png, "image/png"),
                _FAR,
                _TILE,
            ],
        )
    finally:
        page.close()
    assert sizes[:2] == sizes[2:], f"{what} is {sizes[:2]}, its screenshot {sizes[2:]}"
    if differing <= of * share and worst <= _TILE * _TILE * _PATCH:
        return
    kept = ""
    if keep := os.environ.get("HMZ_SHOTS_KEEP"):
        stem = Path(keep) / re.sub(r"[^a-z0-9]+", "-", what.lower()).strip("-")
        stem.parent.mkdir(parents=True, exist_ok=True)
        stem.with_suffix(".drawn.svg").write_text(svg, encoding="utf-8")
        stem.with_suffix(".shot.png").write_bytes(png)
        kept = f"; both are kept as {stem}.drawn.svg and .shot.png"
    raise AssertionError(
        f"{what} does not draw as the interface does: {differing} of {of} pixels"
        f" ({differing / of:.2%}) are not the screenshot's, most of them around {x},{y}"
        " -- something there is missing, or was still moving when the frame was taken"
        + (kept or "; set HMZ_SHOTS_KEEP to a directory to keep both and look")
    )


class _Studio:
    """A Chromium of the pictures' own, on a thread of its own.

    What is not a page of a test's -- a terminal's screen, the splash, a caption -- is drawn
    in it, and every picture is held to its screenshot in it. On a thread because a scene of
    the terminal interface runs inside an event loop, where Playwright's blocking API may not
    be called.
    """

    def __init__(self) -> None:
        self._thread = concurrent.futures.ThreadPoolExecutor(1, "hmz-shots")
        self._browser: Browser | None = None
        self._close: contextlib.ExitStack | None = None

    def does[T](self, job: Callable[[Browser], T]) -> T:
        """Runs one job with the browser, and answers what it did."""
        return self._thread.submit(lambda: job(self._opened())).result()

    def _opened(self) -> Browser:
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._close = contextlib.ExitStack()
            driving = self._close.enter_context(sync_playwright())
            self._browser = driving.chromium.launch(env={**os.environ, "HOME": _HOME})
            self._close.callback(self._browser.close)
        return self._browser

    def close(self) -> None:
        """Shuts the browser, if one was opened."""

        def shut() -> None:
            if self._close is not None:
                self._close.close()
            self._browser = self._close = None

        self._thread.submit(shut).result()


_studio = _Studio()


def shut() -> None:
    """Shuts the pictures' own browser: once, after the last scene of a session."""
    _studio.close()


@dataclasses.dataclass(frozen=True)
class _Sheet:
    """Something to draw in the pictures' own browser: a document, or an address."""

    width: int
    height: int
    content: str = ""
    address: str = ""
    init: str = ""
    agent: str | None = None
    dark: bool = False
    clear: bool = False
    ready: str = ""
    share: float = _SHARE


def _draw(sheet: _Sheet, defs: Mapping[bool, _Defs]) -> dict[bool, _Frame]:
    """One frame of a sheet on each side: as it draws for a light system, and for a dark."""
    return _drawn({dark: dataclasses.replace(sheet, dark=dark) for dark in defs}, defs)


def _drawn(
    sheets: Mapping[bool, _Sheet], defs: Mapping[bool, _Defs]
) -> dict[bool, _Frame]:
    """One frame of each side's sheet."""
    return {dark: _sided(sheet, defs[dark]) for dark, sheet in sheets.items()}


def _sided(sheet: _Sheet, defs: _Defs) -> _Frame:
    """One frame of a sheet, drawn in the pictures' own browser in the sheet's own scheme."""

    def job(browser: Browser) -> _Frame:
        context = browser.new_context(
            viewport={"width": sheet.width, "height": sheet.height},
            device_scale_factor=1,
            user_agent=sheet.agent,
            color_scheme="dark" if sheet.dark else "light",
            locale="en-US",
        )
        try:
            if sheet.init:
                context.add_init_script(sheet.init)
            page = context.new_page()
            if sheet.address:
                page.goto(sheet.address)
            else:
                page.set_content(sheet.content)
            page.evaluate("document.fonts.ready.then(() => true)")
            if sheet.ready:
                page.wait_for_selector(sheet.ready)
            return _take(
                page,
                {sheet.dark: defs},
                clear=sheet.clear,
                sides=[sheet.dark],
                share=sheet.share,
                live=False,
            )[sheet.dark]
        finally:
            context.close()

    return _studio.does(job)


# --------------------------------------------------------------------------------------
# What is drawn around and over a frame: a window, a pointer, a caption.
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Dressed:
    """A window around a frame: what is drawn under it, how it is cut, what is drawn over.

    Attributes:
      width: How wide the whole picture is.
      height: How tall.
      x: Where the frame's left edge stands in it.
      y: Where its top does.
      under: What is drawn before the frame.
      cut: The clip the frame is drawn in, as an attribute, or "".
      over: What is drawn after it.
      defs: What the window defines.
    """

    width: float
    height: float
    x: float = 0
    y: float = 0
    under: str = ""
    cut: str = ""
    over: str = ""
    defs: str = ""


#: The room left around a window for its shadow: at its sides, above it and under it.
_SHADOW = (44, 28, 60)

#: The traffic lights: where the first one's middle is from the window's corner, how far
#: apart they are and how big, as `chrome.rs` sets them in the app's window (16 in, their
#: middle 22 down, 14 across as macOS draws them now), and each one's colour and edge.
_LIGHTS = (23.0, 22.0, 23.0, 7.0)
_LIGHT = (("#ff5f57", "#e0443e"), ("#febc2e", "#d89e24"), ("#28c840", "#1aab29"))

#: How round a window's corners are, and how tall a browser's bar is over its page.
_ROUND = 12
_BAR = 44


def _lights(x: float, y: float) -> str:
    first, down, apart, radius = _LIGHTS
    return "".join(
        f'<circle cx="{_number(x + first + apart * at, 2)}" cy="{_number(y + down, 2)}"'
        f' r="{radius - 0.25}" fill="{fill}" stroke="{edge}" stroke-width=".5"/>'
        for at, (fill, edge) in enumerate(_LIGHT)
    )


def _dress(
    window: Window | None, width: float, height: float, *, dark: bool, address: str
) -> _Dressed:
    """The window drawn around a frame of a size, or nothing where there is none.

    The macOS app's window has no title bar of its own (`TitleBarStyle::Overlay`, its title
    hidden): the page is drawn up to its top edge and the lights stand in the page's top
    row. A browser's has a bar over the page, with the lights and where the page is.
    """
    if window is None:
        return _Dressed(width, height)
    side, above, below = _SHADOW
    bar = _BAR if window == "browser" else 0
    x, y = side, above + bar
    tall = height + bar
    frame = (
        f'x="{side}" y="{above}" width="{_number(width, 2)}" height="{_number(tall, 2)}"'
        f' rx="{_ROUND}"'
    )
    edge = "#ffffff" if dark else "#000000"
    defs = (
        '<filter id="w-shadow" x="-10%" y="-10%" width="120%" height="130%">'
        '<feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#000"'
        ' flood-opacity=".28"/></filter>'
        f'<clipPath id="w-cut"><rect {frame}/></clipPath>'
    )
    paper = "#1e2124" if dark else "#f1f3f4"
    under = f'<rect {frame} fill="{paper}" filter="url(#w-shadow)"/>'
    over = _lights(side, above)
    if window == "browser":
        ink = "#bdc1c6" if dark else "#5f6368"
        field = "#2b2f33" if dark else "#ffffff"
        over += (
            f'<rect x="{side + 96}" y="{above + 8}" width="{_number(width - 192, 2)}"'
            f' height="28" rx="14" fill="{field}"/>'
            f'<text x="{side + 114}" y="{above + 26.5}" font-size="13" fill="{ink}"'
            ' font-family="system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
            f"{html.escape(address)}</text>"
        )
    over += (
        f'<rect {frame} fill="none" stroke="{edge}" stroke-opacity=".18"'
        ' stroke-width="1"/>'
    )
    return _Dressed(
        width + 2 * side,
        tall + above + below,
        x,
        y,
        under,
        ' clip-path="url(#w-cut)"',
        over,
        defs,
    )


def _pointer(dark: bool) -> str:
    """The pointer: an arrow with its tip at the point it is moved to.

    Black edged in white on a light picture, as macOS draws it, and white edged in black on
    a dark one, where a black arrow is lost.
    """
    fill, edge, shade = ("#f4f6f7", "#0b0d0f", ".5") if dark else ("#111", "#fff", ".2")
    return (
        '<path d="M0 0v17.2l4.4-4.1 3.1 7.1 2.9-1.3-3.1-6.9h6z" fill="#000"'
        f' fill-opacity="{shade}" transform="translate(1 1.6)"/>'
        f'<path d="M0 0v17.2l4.4-4.1 3.1 7.1 2.9-1.3-3.1-6.9h6z" fill="{fill}"'
        f' stroke="{edge}" stroke-width="1.3" stroke-linejoin="round"/>'
    )


#: What a key is written as on its cap, where not as it is named.
_KEYS = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "cmd": "⌘",
    "meta": "⌘",
    "alt": "Alt",
    "option": "⌥",
    "shift": "⇧",
    "enter": "↵ Enter",
    "return": "↵ Enter",
    "tab": "Tab",
    "escape": "Esc",
    "esc": "Esc",
    "space": "Space",
    "backspace": "⌫",
    "delete": "Del",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "home": "Home",
    "end": "End",
    "pageup": "PgUp",
    "pagedown": "PgDn",
}

#: How tall the strip under a reel is, where any frame of it says a key or a caption.
_STRIP = 52

#: The strip is drawn on the docs page's own paper, light or dark: its ink is that page's.
_STRIP_STYLE = """
html, body { margin: 0; background: transparent }
body { -webkit-font-smoothing: antialiased; height: 100vh; display: flex;
  align-items: center; justify-content: center; gap: 8px;
  font: 500 15px/1 -apple-system, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
  color: #5d6a72 }
kbd { font: 600 13px/1 ui-monospace, Menlo, monospace; color: #3b454c; background: #f3f5f6;
  border: 1px solid #c9d0d5; border-bottom-width: 2.5px; border-radius: 6px;
  padding: 6px 8px 5px; min-width: 10px; text-align: center }
kbd.typed { font-weight: 500 }
span.plus { color: #9aa4ab; margin: 0 -3px }
span.said { margin-left: 6px }
@media (prefers-color-scheme: dark) {
  body { color: #9aa9b0 }
  kbd { color: #dbe5e8; background: #1b252b; border-color: #3a4850 }
  span.plus { color: #6f7d85 }
}
"""


def _strip(keys: str, caption: str, width: int, defs: _Defs, *, dark: bool) -> _Frame:
    """The strip under a frame: the keys pressed for it, as caps, and what it is told as.

    Args:
      keys: Chords apart by spaces, the keys of each joined by `+` (`ctrl+k`, `down down
        enter`); a word that names no key is something typed, written as it is.
      caption: What is said after them, or "".
      width: How wide the frame over it is.
      defs: What the reel names.
      dark: Whether it is the dark picture's.
    """
    said: list[str] = []
    for chord in keys.split():
        parts = chord.split("+") if len(chord) > 1 else [chord]
        if all(len(one) == 1 or one.lower() in _KEYS for one in parts):
            caps = [
                f"<kbd>{html.escape(_KEYS.get(one.lower(), one.upper()))}</kbd>"
                for one in parts
            ]
            said.append('<span class="plus">+</span>'.join(caps))
        else:
            said.append(f'<kbd class="typed">{html.escape(chord)}</kbd>')
    if caption:
        said.append(f'<span class="said">{html.escape(caption)}</span>')
    content = (
        f'<!doctype html><meta charset="utf-8"><style>{_STRIP_STYLE}</style>'
        + "".join(said)
    )
    return _sided(_Sheet(width, _STRIP, content, clear=True, dark=dark), defs)


# --------------------------------------------------------------------------------------
# A terminal: the interface's screen, and what a command wrote.
# --------------------------------------------------------------------------------------


def _terminal(svg: str, dark: bool) -> _Sheet:
    """A terminal window as Rich draws one, as a sheet to draw: in a font of this machine.

    Rich names a font to be fetched, which a picture may not: the window is drawn in a
    monospace every Mac has, and turned into paths like anything else.
    """
    svg = re.sub(r"@font-face\s*\{[^}]*\}", "", svg)
    svg = svg.replace("font-family: Fira Code, monospace", f"font-family: {_MONO}")
    # A cell's ground is a rectangle that ends where the next begins, and between two that
    # meet at a fraction of a pixel the window shows through as a hair: each is drawn a
    # little over its edge, in its own colour.
    svg = re.sub(
        r'<rect fill="([^"]+)"([^>]*) shape-rendering="crispEdges"/>',
        r'<rect fill="\1" stroke="\1" stroke-width=".6"\2/>',
        svg,
    )
    found = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    assert found, "not a terminal as Rich draws one"
    width, height = (math.ceil(float(one)) for one in found.groups())
    content = (
        '<!doctype html><meta charset="utf-8"><style>html,body{margin:0;'
        f"background:transparent}}svg{{display:block;width:{width}px;height:{height}px;"
        "-webkit-font-smoothing:antialiased}"
        f"</style>{svg}"
    )
    return _Sheet(
        width, height, content, clear=True, dark=dark, share=_SHARE if dark else _INK
    )


def _profiles() -> dict[bool, TerminalTheme]:
    """The colours of the terminal a screen is drawn in, on each side.

    hmz draws in the terminal's own colours -- its ground, its ink and the sixteen it names
    -- so what a screen looks like is a matter of the terminal's profile. The dark picture
    is of a terminal with a dark profile, the one Rich draws an exported screen in; the light
    one is the same screen in a terminal with a light profile: a white window, dark ink, and
    sixteen colours that can be read on white. Its `white` and `bright white` are greys, as
    light profiles have them: pale enough to be written on a coloured ground, and dark enough
    that a ground of them -- the cursor, a bar of the timeline -- is seen on the window's
    white, where a white one is lost.
    """
    from rich.terminal_theme import SVG_EXPORT_THEME, TerminalTheme

    light = TerminalTheme(
        (255, 255, 255),
        (31, 35, 40),
        [
            (31, 35, 40),
            (196, 32, 48),
            (26, 127, 55),
            (148, 100, 0),
            (9, 105, 218),
            (130, 80, 223),
            (17, 120, 130),
            (175, 184, 193),
        ],
        [
            (106, 115, 125),
            (164, 14, 38),
            (17, 99, 41),
            (122, 78, 0),
            (5, 80, 174),
            (102, 57, 186),
            (12, 96, 105),
            (208, 215, 222),
        ],
    )
    return {False: light, True: SVG_EXPORT_THEME}


def _windows(
    console: Console, title: str, *, own: bool = False, only: bool | None = None
) -> dict[bool, str]:
    """What a console recorded, as the terminal window Rich draws, on each side.

    Args:
      console: The console, which recorded what was printed on it.
      title: What the window is titled.
      own: Whether what it recorded names every colour itself, as an interface in a theme
        of its own does: nothing of it is the terminal's, and both sides are one picture, the
        dark window.
      only: The one side wanted, or None for both.
    """
    said: dict[bool, str] = {}
    for dark, profile in _profiles().items():
        if only is not None and dark != only:
            continue
        svg = console.export_svg(
            title=title, theme=_profiles()[True] if own else profile, clear=False
        )
        if not (dark or own):
            # The window's edge, which Rich draws for a dark one: a light line on white.
            svg = svg.replace("rgba(255,255,255,0.35)", "rgba(20,26,31,0.22)")
        said[dark] = svg
    return said


def _console(columns: int, rows: int | None = None) -> Console:
    """A console that records what is printed on it, as Textual makes one to export a screen."""
    from rich.console import Console

    return Console(
        width=columns,
        height=rows,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        record=True,
        legacy_windows=False,
        safe_box=False,
    )


def _screen(lines: Sequence[Text], columns: int, title: str) -> dict[bool, _Sheet]:
    """Lines of a terminal, drawn by Rich in the window it draws the interface's screen in."""
    console = _console(columns)
    for line in lines:
        console.print(line, no_wrap=True, overflow="crop", highlight=False)
    return {
        dark: _terminal(svg, dark) for dark, svg in _windows(console, title).items()
    }


def _sides(app: App[Any]) -> dict[bool, str] | None:
    """The two themes an interface in one of humanfia's is drawn in: its light and its dark.

    Returns:
      The preset's two themes by side, or None for an app in the terminal's own colours or
      in a theme of Textual's, which has no other side.
    """
    from hmz.tui import humanfia

    name = app.current_theme.name
    if name not in humanfia.THEMES:
        return None
    key = name.rpartition("-")[0]
    return {False: f"{key}-light", True: f"{key}-dark"}


def _themed(app: App[Any], name: str) -> None:
    """Puts the interface in a theme at once, restyled before anything else is done."""
    from hmz.tui.selecting import Transcript

    if app.theme == name:
        return
    app.theme = name
    app.refresh_css(animate=False)
    # What a transcript holds was drawn in the colours of the moment it was written: its
    # rows are drawn again, as a change of the terminal's width draws them, and what is
    # selected over them stays selected.
    for screen in app.screen_stack:
        for transcript in screen.query(Transcript):
            held = cast("Any", transcript)
            if held._drawn_at <= 0:  # noqa: SLF001 -- nothing drawn yet to draw again
                continue
            held._rows.clear()  # noqa: SLF001
            held._lines.clear()  # noqa: SLF001
            held._joined, held._widest = None, 0  # noqa: SLF001
            for written in held._written:  # noqa: SLF001
                held._drew(written)  # noqa: SLF001
            held._measured()  # noqa: SLF001
            transcript.refresh()


def _rendered(app: App[Any]) -> Console:
    """The screen as it stands, printed on a console that recorded it."""
    running = cast("Any", app)
    width, height = app.size
    console = _console(width, height)
    console.print(
        running.screen._compositor.render_update(  # noqa: SLF001 -- as export_screenshot
            full=True,
            screen_stack=running._background_screens,  # noqa: SLF001
            simplify=False,
        )
    )
    return console


def _interface(app: App[Any]) -> dict[bool, _Sheet]:
    """The terminal interface's screen as it stands, on each side.

    What `App.export_screenshot` does, on both sides of what the interface is drawn in. In
    one of humanfia's themes, which is what it opens in, the screen is drawn in the preset's
    light theme for the light picture and in its dark theme for the dark one, at the same
    instant, and left in the theme the scene had it in. In the terminal's own colours
    (`TEXTUAL_THEME=terminal`) it is rendered once and exported in a terminal of each
    profile, which that theme leaves to Rich. An app started in a theme of Textual's names
    every colour itself and has no other side: it is one picture.
    """
    sides = _sides(app)
    if sides is None:
        return {
            dark: _terminal(svg, dark)
            for dark, svg in _windows(
                _rendered(app), app.title, own=not app.current_theme.ansi
            ).items()
        }
    was = app.theme
    drawn: dict[bool, _Sheet] = {}
    try:
        for dark, name in sides.items():
            _themed(app, name)
            window = _windows(_rendered(app), app.title, only=dark)[dark]
            drawn[dark] = _terminal(window, dark)
    finally:
        _themed(app, was)
    return drawn


#: The colours a terminal names, as Rich names them.
_COLOURS = {
    "black": "black",
    "red": "red",
    "green": "green",
    "brown": "yellow",
    "blue": "blue",
    "magenta": "magenta",
    "cyan": "cyan",
    "white": "white",
}


def _colour(named: str) -> str | None:
    """A colour as the terminal emulator names it, as Rich does, or None for the default."""
    if named == "default":
        return None
    if named in _COLOURS:
        return _COLOURS[named]
    if named.startswith("bright") and named[6:] in _COLOURS:
        return f"bright_{_COLOURS[named[6:]]}"
    return f"#{named}"


@dataclasses.dataclass
class _Ran:
    """A command as it ran in a terminal: what it wrote, and when.

    Attributes:
      said: Each thing it wrote, and how long after it started.
      columns: How wide its terminal was.
      rows: How tall.
      status: What it ended with.
    """

    said: list[tuple[float, bytes]]
    columns: int
    rows: int
    status: int

    def screens(self) -> Iterator[tuple[float, list[Text]]]:
        """The terminal's screen after each thing written, and when: its lines down to the last.

        Read by a terminal emulator, so that what a command redraws -- a line it writes over,
        a region it keeps up to date -- is as the terminal showed it.
        """
        import pyte
        from rich.style import Style
        from rich.text import Text

        screen = pyte.Screen(self.columns, self.rows)
        stream = pyte.ByteStream(screen)
        for at, written in self.said:
            stream.feed(written)
            lines: list[Text] = []
            for y in range(self.rows):
                row = screen.buffer[y]
                line = Text()
                # Down to the last cell that shows anything: a letter, or a ground of its own.
                shows = [
                    x
                    for x in range(self.columns)
                    if row[x].data.strip() or row[x].bg != "default" or row[x].reverse
                ]
                for x in range(shows[-1] + 1 if shows else 0):
                    cell = row[x]
                    line.append(
                        cell.data,
                        Style(
                            color=_colour(cell.fg),
                            bgcolor=_colour(cell.bg),
                            # The terminal's ink and ground change places, whichever they are.
                            reverse=cell.reverse or None,
                            bold=cell.bold or None,
                            italic=cell.italics or None,
                            underline=cell.underscore or None,
                            strike=cell.strikethrough or None,
                        ),
                    )
                lines.append(line)
            while lines and not lines[-1].plain:
                lines.pop()
            yield at, lines


def _run(
    argv: Sequence[str], cwd: Path | None, columns: int, rows: int, patience: float
) -> _Ran:
    """Runs a command in a terminal of its own, under the environment as it is staged.

    `hmz` is this checkout's, run by this Python, whatever `PATH` holds.

    Raises:
      AssertionError: If it has not ended within `patience` seconds.
    """
    run = [sys.executable, "-m", "hmz", *argv[1:]] if argv[0] == "hmz" else list(argv)
    ours, theirs = pty.openpty()
    fcntl.ioctl(theirs, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("NO_COLOR", "FORCE_COLOR", "PYTEST_CURRENT_TEST")
    } | {"TERM": "xterm-256color", "COLUMNS": str(columns), "LINES": str(rows)}
    started = time.monotonic()
    with subprocess.Popen(
        run,
        stdin=theirs,
        stdout=theirs,
        stderr=theirs,
        cwd=cwd,
        env=env,
        start_new_session=True,
    ) as running:
        os.close(theirs)
        said: list[tuple[float, bytes]] = []
        try:
            while True:
                left = patience - (time.monotonic() - started)
                assert left > 0, f"{shlex.join(argv)} had not ended in {patience:.0f}s"
                if not select.select([ours], [], [], min(left, 0.2))[0]:
                    if running.poll() is not None:
                        break
                    continue
                try:
                    written = os.read(ours, 65536)
                except OSError:
                    # The terminal's other end is shut: the command, and all it started, ended.
                    break
                if not written:
                    break
                said.append((time.monotonic() - started, written))
        finally:
            if running.poll() is None:
                running.kill()
            os.close(ours)
        return _Ran(said, columns, rows, running.wait())


def _prompt(typed: str, columns: int, *, caret: bool = False) -> list[Text]:
    """The lines a command is typed on: a prompt, and as much of the command as is typed.

    Wrapped at the terminal's edge, as a terminal wraps what is typed past it.
    """
    from rich.text import Text

    line = Text.assemble(("$ ", "bold green"), typed)
    if caret:
        line.append(" ", "reverse")
    return list(line.divide(range(columns, len(line), columns)))


# --------------------------------------------------------------------------------------
# Stills.
# --------------------------------------------------------------------------------------


def _file(name: str, dark: bool) -> str:
    """What one side of a picture is called: `<name>.svg` light, `<name>.dark.svg` dark."""
    return f"{name}.dark.svg" if dark else f"{name}.svg"


def _put(name: str, written: Mapping[bool, str], most: int) -> Path:
    """Writes a picture's two sides where the docs serve them from, each held to its size.

    Neither is written unless both may be: a picture is never left with one side of an
    earlier run beside one of this.

    Returns:
      The light file.
    """
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), (
        f"a picture is named in lower case with dashes, as `chat-new`: not {name!r}"
    )
    assert set(written) == set(SIDES), "a picture is written on both sides"
    for dark, svg in written.items():
        assert len(svg.encode()) <= most, (
            f"{_file(name, dark)} is {len(svg.encode()):,} bytes, over the {most:,} a"
            " picture of its kind may be: crop it, show less on screen, or take fewer"
            " frames"
        )
    SHOTS.mkdir(parents=True, exist_ok=True)
    for dark, svg in written.items():
        (SHOTS / _file(name, dark)).write_text(svg + "\n", encoding="utf-8")
    return SHOTS / _file(name, False)


def _pair() -> dict[bool, _Defs]:
    """What a picture names, on each of its sides: the two files share nothing."""
    return {dark: _Defs() for dark in SIDES}


def _still(
    name: str,
    frames: Mapping[bool, _Frame],
    defs: Mapping[bool, _Defs],
    *,
    window: Window | None = None,
    address: str = "",
    pointer: tuple[float, float] | None = None,
    most: int = STILL,
) -> Path:
    """Writes one frame as a picture, light and dark, each held to its own screenshot.

    Neither file is written unless both are faithful and of a size.

    Returns:
      The light file.
    """
    written: dict[bool, str] = {}
    for dark, frame in frames.items():
        sharing = _Sharing(defs[dark], [frame])
        box = frame.at
        bare = sharing.frame(frame)
        plain = _document(box.width, box.height, defs[dark].written(bare), bare)
        _studio.does(
            lambda browser, plain=plain, frame=frame, dark=dark: _faithful(
                browser, plain, frame.png, _file(name, dark), frame.share
            )
        )
        dressed = _dress(window, box.width, box.height, dark=dark, address=address)
        body = bare
        if window is not None:
            placed = sharing.frame(frame, dressed.x, dressed.y)
            body = f"{dressed.under}<g{dressed.cut}>{placed}</g>{dressed.over}"
        if pointer is not None:
            x = pointer[0] - box.x + dressed.x
            y = pointer[1] - box.y + dressed.y
            body += (
                f'<g transform="translate({_number(x, 1)} {_number(y, 1)})">'
                f"{_pointer(dark)}</g>"
            )
        written[dark] = _document(
            dressed.width,
            dressed.height,
            dressed.defs + defs[dark].written(body),
            body,
        )
    return _put(name, written, most)


def web(
    page: Page,
    name: str,
    *,
    clip: Where | None = None,
    pad: float = 12,
    window: Window | None = None,
    pointer: Where | None = None,
    address: str = "localhost",
    most: int = STILL,
) -> Path:
    """Writes a still of the web page as it stands: `docs/public/shots/<name>.svg`.

    And `<name>.dark.svg` beside it. The page is Chromium's, as `world.page()` opens it.
    Wait for what the picture is of before taking it (`expect(...)`): the page is drawn as
    it is at that instant, once as it draws where the system is light and once where it is
    dark, and is left as it was.

    Args:
      page: The page.
      name: The picture's name: `<docs page>-<what>`, lower case with dashes.
      clip: One part of the page to show alone -- a locator or a selector -- or None for
        the whole window.
      pad: How much of the page is kept around `clip`, in CSS pixels.
      window: A window to draw around it: `"desktop"` the macOS app's (open the page with
        `world.page(desktop=True)`), `"browser"` a browser's; None for the page alone. Only
        around the whole page.
      pointer: Where a mouse pointer is drawn, if anywhere: a locator, a selector or a point.
        To show what is under it as hovered, `locator.hover()` first.
      address: What a browser's window says the page is at.
      most: The most bytes it may be.

    Returns:
      The light file written.

    Raises:
      AssertionError: If either picture does not rasterize to the page's screenshot, is
        named badly or is too large.
    """
    assert window is None or clip is None, "a window is drawn around the whole page"
    defs = _pair()
    frames = _take(page, defs, _where(page, clip, pad) if clip is not None else None)
    return _still(
        name,
        frames,
        defs,
        window=window,
        address=address,
        pointer=_point(page, pointer) if pointer is not None else None,
        most=most,
    )


def tui(app: App[Any], name: str, *, most: int = STILL) -> Path:
    """Writes a still of the terminal interface's screen: `docs/public/shots/<name>.svg`.

    The screen is the running app's own, as `App.export_screenshot` renders it, in the
    terminal window Rich draws, titled as the app is: in humanfia's light theme for the
    light picture and its dark theme for the dark (in the terminal's own colours, a terminal
    of each profile; an app started in a theme of Textual's is one picture, twice). Call
    it inside `async with world.tui() as (app,
    pilot):`, after `await pilot.pause()` has let the screen settle.

    Args:
      app: The running app.
      name: The picture's name.
      most: The most bytes it may be.

    Returns:
      The light file written.
    """
    defs = _pair()
    return _still(name, _drawn(_interface(app), defs), defs, most=most)


def cli(
    argv: Sequence[str],
    name: str,
    *,
    cwd: Path | None = None,
    typed: bool = True,
    columns: int = 88,
    title: str = "Terminal",
    patience: float = 120,
    most: int = STILL,
) -> Path:
    """Runs a command in a real terminal and writes a still of what it printed.

    The command runs once, and what it printed is drawn twice: in a terminal with a light
    profile and in one with a dark profile. It runs under the environment as the test has it
    -- the staged home, daemon and agents of `world` -- in the working directory, with
    colours as a terminal gets them. `hmz` is this checkout's.

    Args:
      argv: The command, as typed: `["hmz", "--help"]`.
      name: The picture's name.
      cwd: Where it runs, if not in the working directory (`world.workspace`).
      typed: Whether the line that ran it is shown above what it printed, after a prompt.
      columns: How wide the terminal is.
      title: What the terminal's window is titled.
      patience: How many seconds it may run.
      most: The most bytes it may be.

    Returns:
      The light file written.
    """
    ran = _run(argv, cwd, columns, 200, patience)
    screens = [lines for _, lines in ran.screens()]
    lines = _prompt(shlex.join(argv), columns) if typed else []
    lines += screens[-1] if screens else []
    defs = _pair()
    return _still(name, _drawn(_screen(lines, columns, title), defs), defs, most=most)


def _status(state: str, detail: Any) -> str:
    """A script that stands in for the app behind its splash, saying one state and no more."""
    said = json.dumps({"state": state, "detail": detail})
    return (
        "window.__TAURI_INTERNALS__ = { invoke: (command, given) =>"
        f" command === 'status' && !given?.after ? Promise.resolve({said})"
        " : new Promise(() => {}) }"
    )


def _splash(state: str, detail: Any, dark: bool) -> dict[bool, _Sheet]:
    """The splash in one state, on each side: both dark where the scene asks for dark."""
    return {
        side: _Sheet(
            *DESKTOP,
            address=_SPLASH.as_uri(),
            init=_status(state, detail),
            agent=APP,
            dark=dark or side,
            ready=f"main[data-state={state}]",
        )
        for side in SIDES
    }


def splash(
    state: str,
    detail: Any,
    name: str,
    *,
    dark: bool = False,
    window: Window | None = "desktop",
    most: int = STILL,
) -> Path:
    """Writes a still of Humanize Desktop's launch window in one state.

    The splash is the app's own (`desktop/ui/app`), told the state by a stand-in for the app
    behind it, as `ui.js` reads it:

    - `"starting"`, detail None -- the mark, and Starting;
    - `"installing"`, detail `{"updating": False, "step": "uv" | "python" | "hmz", "line":
      "<what the installer last said>"}`;
    - `"waiting"`, detail the version running (`"0.9.2"`) -- an update held back by epics;
    - `"install-failed"`, detail `{"updating": False, "said": "<why>", "keep": False}`;
    - `"missing"`, detail None.

    Args:
      state: The state.
      detail: What the app says with it.
      name: The picture's name.
      dark: Whether both pictures are of a system that asks for dark colours: where the
        dark splash itself is what the page is about. Left alone, the light picture is of a
        light system and the dark one of a dark.
      window: The window drawn around it: the app's, unless None.
      most: The most bytes it may be.

    Returns:
      The light file written.
    """
    defs = _pair()
    frames = _drawn(_splash(state, detail, dark), defs)
    return _still(name, frames, defs, window=window, most=most)


# --------------------------------------------------------------------------------------
# Reels.
# --------------------------------------------------------------------------------------


@dataclasses.dataclass
class _Shown:
    """One frame of a reel, on each of its sides, and how it is shown."""

    frame: dict[bool, _Frame]
    hold: float
    pointer: tuple[float, float] | None = None
    click: bool = False
    keys: str = ""
    caption: str = ""
    cut: bool = False
    poster: bool = False


def _percent(at: float, of: float) -> str:
    return f"{_number(min(100.0, max(0.0, 100 * at / of)), 3)}%"


class Reel:
    """A moving picture made of real frames: one SVG that plays them in a loop.

    Take a frame of the interface at each step of what is shown, then `save()`::

        reel = shots.Reel("chat-new")
        reel.web(page, hold=1.2, pointer=box, click=True)   # the pointer goes to the box
        reel.type(page, box, "Add a coupon field")          # and the words are typed
        page.keyboard.press("Enter")
        expect(page.locator(".answer")).to_be_visible()
        reel.web(page, hold=3)                              # what came of it
        reel.save()

    Each frame is shown for its `hold` seconds, then the next fades in over it; after the
    last the reel starts again. A frame's `pointer` is where the mouse goes while it is
    shown, and `click` marks a click there just before the next frame: so a frame is taken
    *before* what its click does, and the next one after. Frames are all of one size; what
    several draw alike is said once, so a frame that changes little costs little. For a
    reader who asked for reduced motion the reel stands still on its last frame, or on the
    one taken with `poster=True`.

    A reel is two files, as a still is: `<name>.svg` of the light interface and
    `<name>.dark.svg` of the dark one, frame for frame and beat for beat, from one run.

    Args:
      name: The picture's name: `<docs page>-<what>`, lower case with dashes.
      clip: For a reel of the web page, the one part of it shown in every frame -- a locator
        or a selector, found when the first frame is taken -- or None for the whole window.
      pad: How much of the page is kept around `clip`, in CSS pixels.
      window: A window drawn around the frames: `"desktop"` or `"browser"`, or None.
      fade: How many seconds one frame takes to fade in over the last.
      address: What a browser's window says the page is at.
      most: The most bytes it may be.
    """

    def __init__(
        self,
        name: str,
        *,
        clip: Where | None = None,
        pad: float = 12,
        window: Window | None = None,
        fade: float = 0.18,
        address: str = "localhost",
        most: int = REEL,
    ) -> None:
        assert window is None or clip is None, "a window is drawn around the whole page"
        self.name = name
        self._clip = clip
        self._pad = pad
        self._window: Window | None = window
        self._fade = fade
        self._address = address
        self._most = most
        self._defs = _pair()
        self._shown: list[_Shown] = []
        self._at: _Box | None = None

    # -- frames -------------------------------------------------------------------------

    def web(
        self,
        page: Page,
        *,
        hold: float = 1.4,
        pointer: Where | None = None,
        click: bool = False,
        caption: str = "",
        keys: str = "",
        poster: bool = False,
        cut: bool = False,
    ) -> None:
        """Takes a frame of the web page as it stands.

        Args:
          page: The page, as `world.page()` opens it.
          hold: How many seconds the frame is shown.
          pointer: Where the mouse pointer goes while it is shown: a locator, a selector or
            a point of the page. It stays where it last went in the frames that name none.
          click: Whether it clicks there, just before the next frame.
          caption: A few words said under the frame, if any.
          keys: The keys pressed for it, drawn as caps under the frame (`"ctrl+k"`).
          poster: Whether this is the frame a reader who asked for less motion sees.
          cut: Whether it replaces the last at once, with no fade.
        """
        if self._clip is not None and self._at is None:
            self._at = _where(page, self._clip, self._pad)
        self._add(
            _take(page, self._defs, self._at),
            hold,
            pointer=_point(page, pointer) if pointer is not None else None,
            click=click,
            caption=caption,
            keys=keys,
            poster=poster,
            cut=cut,
        )

    def type(
        self,
        page: Page,
        into: Locator | str,
        text: str,
        *,
        per: int = 3,
        hold: float = 0.1,
        rest: float = 0.6,
    ) -> None:
        """Types into a box of the web page, taking a frame every few characters.

        The text is typed as a keyboard types it, so the page does what it does as somebody
        writes: completes, grows the box, lights its button.

        Args:
          page: The page.
          into: The box: a locator or a selector. It is clicked first.
          text: What is typed.
          per: How many characters are typed between frames.
          hold: How many seconds each frame is shown.
          rest: How many seconds the last one is, with all of it typed.
        """
        box = page.locator(into) if isinstance(into, str) else into
        box.click()
        for start in range(0, len(text), per):
            box.press_sequentially(text[start : start + per])
            last = start + per >= len(text)
            self.web(page, hold=rest if last else hold, cut=True)

    def tui(
        self,
        app: App[Any],
        *,
        hold: float = 1.2,
        keys: str = "",
        caption: str = "",
        poster: bool = False,
        cut: bool = False,
    ) -> None:
        """Takes a frame of the terminal interface's screen as it stands.

        Args:
          app: The running app (`world.tui()`).
          hold: How many seconds the frame is shown.
          keys: The keys that were pressed to get here, drawn as caps under the frame:
            chords apart by spaces (`"ctrl+k"`, `"down down enter"`), or what was typed
            (`"/flow"`).
          caption: A few words said under the frame, if any.
          poster: Whether this is the frame a reader who asked for less motion sees.
          cut: Whether it replaces the last at once, with no fade: as typing does.
        """
        self._add(
            _drawn(_interface(app), self._defs),
            hold,
            keys=keys,
            caption=caption,
            poster=poster,
            cut=cut,
        )

    def cli(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        typed: bool = True,
        columns: int = 88,
        rows: int = 24,
        title: str = "Terminal",
        hold: float = 3.0,
        frames: int = 12,
        patience: float = 120,
    ) -> None:
        """Runs a command in a real terminal and takes frames of it as it went.

        The command is typed after a prompt, a few characters a frame, and then what the
        terminal showed as it ran: a frame wherever its screen changed, held as long as it
        stood, though never longer than a moment -- waiting is not shown at its length.

        Args:
          argv: The command, as typed: `["hmz", "exec", "-f", "goal", "tidy up"]`.
          cwd: Where it runs, if not in the working directory.
          typed: Whether the command is shown being typed first.
          columns: How wide the terminal is.
          rows: How tall, which every frame of the reel is: what scrolls off its top is gone,
            as in a terminal.
          title: What the terminal's window is titled.
          hold: How many seconds the last frame, with all it printed, is shown.
          frames: The most frames taken of it running: the screens between are left out.
          patience: How many seconds it may run.
        """
        said = shlex.join(argv)
        ran = _run(
            argv, cwd, columns, rows - len(_prompt(said, columns)) * typed, patience
        )
        steps: list[tuple[list[Text], float]] = []
        if typed:
            steps.append((_prompt("", columns, caret=True), 0.7))
            steps += [
                (_prompt(said[: at + 3], columns, caret=True), 0.09)
                for at in range(0, len(said), 3)
            ]
            steps[-1] = (steps[-1][0], 0.45)
        head = _prompt(said, columns) if typed else []
        screens: list[tuple[float, list[Text]]] = []
        for at, lines in ran.screens():
            if screens and [one.markup for one in screens[-1][1]] == [
                one.markup for one in lines
            ]:
                continue
            screens.append((at, lines))
        if len(screens) > frames:
            # Evenly through it, the last always among them.
            picked = {
                round(at * (len(screens) - 1) / (frames - 1)) for at in range(frames)
            }
            screens = [one for at, one in enumerate(screens) if at in picked]
        for at, (when, lines) in enumerate(screens):
            last = at == len(screens) - 1
            stood = hold if last else min(1.2, max(0.25, screens[at + 1][0] - when))
            steps.append((head + lines, stood))
        from rich.text import Text

        for at, (lines, stood) in enumerate(steps):
            padded = [*lines, *(Text() for _ in range(rows - len(lines)))][-rows:]
            self._add(
                _drawn(_screen(padded, columns, title), self._defs),
                stood,
                cut=True,
                poster=at == len(steps) - 1,
            )

    def splash(
        self,
        state: str,
        detail: Any = None,
        *,
        hold: float = 1.4,
        dark: bool = False,
        caption: str = "",
        poster: bool = False,
    ) -> None:
        """Takes a frame of Humanize Desktop's launch window in one state (see `splash`).

        Give the reel `window="desktop"` to draw the app's window around them.
        """
        self._add(
            _drawn(_splash(state, detail, dark), self._defs),
            hold,
            caption=caption,
            poster=poster,
        )

    def _add(self, frame: dict[bool, _Frame], hold: float, **how: Any) -> None:
        first = (self._shown[0].frame if self._shown else frame)[False].at
        for one in frame.values():
            assert (one.at.width, one.at.height) == (first.width, first.height), (
                f"every frame of a reel is one size: {one.at} after {first}"
            )
        self._shown.append(_Shown(frame, hold, **how))

    # -- the file -----------------------------------------------------------------------

    def save(self) -> Path:
        """Writes the reel: `docs/public/shots/<name>.svg` and `<name>.dark.svg`.

        Every frame is first held to its screenshot, as it is written in its file, and
        neither file is written unless both are faithful and of a size.

        Returns:
          The light file written.

        Raises:
          AssertionError: If a frame does not rasterize to its screenshot, or the reel is
            named badly or is too large.
        """
        assert self._shown, "a reel is made of frames"
        return _put(
            self.name, {dark: self._written(dark) for dark in SIDES}, self._most
        )

    def _written(self, dark: bool) -> str:
        """One side of the reel, as its file says it."""
        shown = self._shown
        mine = self._defs[dark]
        size = shown[0].frame[dark].at
        strips: dict[tuple[str, str], _Frame] = {
            (one.keys, one.caption): _strip(
                one.keys, one.caption, int(size.width), mine, dark=dark
            )
            for one in shown
            if one.keys or one.caption
        }
        sharing = _Sharing(
            mine, [one.frame[dark] for one in shown] + list(strips.values())
        )
        dressed = _dress(
            self._window,
            size.width,
            size.height,
            dark=dark,
            address=self._address,
        )
        placed = [sharing.frame(one.frame[dark], dressed.x, dressed.y) for one in shown]
        under = dressed.height - (_SHADOW[2] - 8 if self._window else 0)
        told = {
            key: sharing.frame(strip, dressed.x, under) for key, strip in strips.items()
        }
        defs = mine.written("".join(placed) + "".join(told.values()))
        self._check(dark, sharing, defs)

        total = sum(one.hold for one in shown)
        starts = [sum(one.hold for one in shown[:at]) for at in range(len(shown))]
        fades = [0.0 if one.cut else min(self._fade, one.hold / 2) for one in shown]
        poster = next(
            (at for at, one in enumerate(shown) if one.poster), len(shown) - 1
        )
        style = [".f,.s{opacity:0}", f"#f{poster}{{opacity:1}}"]
        moving = ["#f0{opacity:1}"]
        still = ["#p,.c{display:none}"]
        body = [dressed.under, f"<g{dressed.cut}>"]
        tiny = 0.0004 * total
        for at, frame in enumerate(placed):
            body.append(f'<g class="f" id="f{at}">{frame}</g>')
            if at == 0:
                continue
            # In over the last, there until the next is wholly in, and gone at once after:
            # the last of all fades away over the first, which never goes.
            begins, faded = starts[at], starts[at] + fades[at]
            last = at == len(placed) - 1
            away = min(self._fade, shown[at].hold / 2)
            leaves = total - away if last else starts[at + 1] + fades[at + 1]
            before = _percent(begins - (0 if fades[at] else tiny), total)
            there = f"{_percent(max(faded, begins), total)},{_percent(leaves, total)}"
            after = "100%" if last else f"{_percent(leaves + tiny, total)},100%"
            steps = [
                f"0%,{before}{{opacity:0}}",
                f"{there}{{opacity:1}}",
                f"{after}{{opacity:0}}",
            ]
            style.append(f"@keyframes f{at}{{{''.join(steps)}}}")
            moving.append(
                f"#f{at}{{animation:f{at} {_number(total, 2)}s linear infinite}}"
            )
        body.append("</g>")
        body.append(dressed.over)
        for at, one in enumerate(shown):
            strip = told.get((one.keys, one.caption))
            if strip is None:
                continue
            ends = total if at == len(shown) - 1 else starts[at + 1]
            body.append(f'<g class="s" id="s{at}">{strip}</g>')
            style.append(
                f"@keyframes s{at}{{0%,{_percent(starts[at] - tiny, total)}{{opacity:0}}"
                f"{_percent(starts[at], total)},{_percent(ends - tiny, total)}{{opacity:1}}"
                f"{_percent(ends, total)},100%{{opacity:0}}}}"
            )
            moving.append(
                f"#s{at}{{animation:s{at} {_number(total, 2)}s linear infinite}}"
            )
            if at == poster:
                still.append(f"#s{at}{{opacity:1}}")
        body.append(self._pointed(dark, starts, total, dressed, size, style, moving))
        height = dressed.height + (_STRIP if strips else 0)
        if strips and self._window:
            height -= _SHADOW[2] - 8
        sheet = (
            "".join(style)
            + "@media (prefers-reduced-motion:no-preference){"
            + "".join(moving)
            + "}@media (prefers-reduced-motion:reduce){"
            + "".join(still)
            + "}"
        )
        return _document(
            dressed.width, height, dressed.defs + defs, "".join(body), sheet
        )

    def _check(self, dark: bool, sharing: _Sharing, defs: str) -> None:
        """Holds each frame of one side, as its file says it, to its screenshot."""

        def job(browser: Browser) -> None:
            for at, one in enumerate(self._shown):
                frame = one.frame[dark]
                box = frame.at
                _faithful(
                    browser,
                    _document(box.width, box.height, defs, sharing.frame(frame)),
                    frame.png,
                    f"frame {at + 1} of {_file(self.name, dark)}",
                    frame.share,
                )

        _studio.does(job)

    def _pointed(
        self,
        dark: bool,
        starts: Sequence[float],
        total: float,
        dressed: _Dressed,
        size: _Box,
        style: list[str],
        moving: list[str],
    ) -> str:
        """The pointer, gliding to where each frame points, and a ring where it clicks."""
        shown = self._shown
        if not any(one.pointer for one in shown):
            return ""

        def placed(point: tuple[float, float]) -> tuple[float, float]:
            return (point[0] - size.x + dressed.x, point[1] - size.y + dressed.y)

        first = next(one.pointer for one in shown if one.pointer)
        # From a little way off the first place it goes, as a hand comes to it.
        at = placed((min(first[0] + 150, size.x + size.width - 30), first[1] + 110))
        began = at
        steps = [
            f"0%{{transform:translate({_number(at[0], 1)}px,{_number(at[1], 1)}px)}}"
        ]
        rings: list[str] = []
        for index, one in enumerate(shown):
            if one.pointer is None:
                continue
            to = placed(one.pointer)
            leaves = starts[index] + min(0.25, one.hold * 0.15)
            arrives = leaves + min(0.7, one.hold * 0.5)
            steps.append(
                f"{_percent(leaves, total)}{{transform:translate({_number(at[0], 1)}px,"
                f"{_number(at[1], 1)}px);animation-timing-function:ease-in-out}}"
            )
            steps.append(
                f"{_percent(arrives, total)}{{transform:translate({_number(to[0], 1)}px,"
                f"{_number(to[1], 1)}px)}}"
            )
            at = to
            if one.click:
                clicks = max(arrives, starts[index] + one.hold - 0.3)
                rings.append(
                    f'<circle class="c" id="c{index}" cx="{_number(to[0], 1)}"'
                    f' cy="{_number(to[1], 1)}" r="16" fill="#3b82f6" opacity="0"'
                    f' style="transform-origin:{_number(to[0], 1)}px {_number(to[1], 1)}px"/>'
                )
                style.append(
                    f"@keyframes c{index}{{0%,{_percent(clicks, total)}{{opacity:0;"
                    f"transform:scale(.2)}}{_percent(clicks + 0.01, total)}{{opacity:.45;"
                    f"transform:scale(.2)}}{_percent(clicks + 0.4, total)},100%{{opacity:0;"
                    "transform:scale(1)}}"
                )
                moving.append(
                    f"#c{index}{{animation:c{index} {_number(total, 2)}s ease-out infinite}}"
                )
        steps.append(
            f"99.99%{{transform:translate({_number(at[0], 1)}px,{_number(at[1], 1)}px)}}"
            f"100%{{transform:translate({_number(began[0], 1)}px,{_number(began[1], 1)}px)}}"
        )
        style.append(f"@keyframes p{{{''.join(steps)}}}")
        style.append(
            f"#p{{transform:translate({_number(began[0], 1)}px,{_number(began[1], 1)}px)}}"
        )
        moving.append(f"#p{{animation:p {_number(total, 2)}s linear infinite}}")
        return "".join(rings) + f'<g id="p">{_pointer(dark)}</g>'
