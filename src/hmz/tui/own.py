"""What the terminal interface keeps of its own: how it looks, what it is written in, who it tells.

The web page keeps these in the browser it is read in -- they are the person's, not a daemon's
-- and the terminal interface keeps them beside its other settings of that kind, under `tui`
in this machine's `settings.toml`: which preset it is drawn in and which side of it, and the
language its texts are said in. `TEXTUAL_THEME` and `NO_COLOR` still say how it looks before
anything kept does (:func:`hmz.tui.humanfia.chosen`).

And it is here that a notice is told to the system rather than only drawn: through the
terminal, by the sequence the terminal is known to show as a notification of the system's own,
while the terminal is not what the person is looking at.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any, Final, Literal, cast
from weakref import WeakSet

from hmz.coganchor import settings
from hmz.words import LANGUAGES

from . import humanfia

if TYPE_CHECKING:
    from collections.abc import Mapping

    from textual.app import App

__all__ = [
    "APPEARANCES",
    "OVERRIDES",
    "Kept",
    "hears_focus",
    "keep",
    "overridden",
    "read",
    "sequence",
    "tells",
    "wanted",
]

#: Which side of the theme in use is drawn: the one the terminal asks for, one of the two,
#: or neither -- the terminal's own colours.
APPEARANCES: Final = ("auto", "light", "dark", "terminal")

#: The variables that say how the interface looks before anything kept does, first first.
OVERRIDES: Final = ("TEXTUAL_THEME", "NO_COLOR")

#: Where in `settings.toml` these are kept.
_KEY: Final = "tui"

#: The variables a system's language is read from, the one that overrides the rest first.
_LOCALE: Final = ("LC_ALL", "LC_MESSAGES", "LANG")


@dataclass(frozen=True)
class Kept:
    """What one person's terminal interface keeps of its own."""

    theme: str = "humanize"
    """The preset in use, by its key in :data:`hmz.tui.humanfia.PRESETS`."""
    appearance: str = "auto"
    """Which side of it is drawn: one of :data:`APPEARANCES`."""
    language: str = ""
    """What its texts are said in: one of :data:`hmz.words.LANGUAGES`, or "" for the system's."""

    def looks(self) -> str:
        """The theme kept, as :func:`hmz.tui.humanfia.chosen` takes it."""
        if self.appearance == "terminal":
            return "terminal"
        if self.appearance == "auto":
            return self.theme
        return humanfia.named(self.theme, self.appearance)

    def speaks(self, environ: Mapping[str, str]) -> str:
        """The language to say texts in, as :func:`hmz.words.speak` takes it.

        Args:
          environ: The process environment, which says the system's language.

        Returns:
          The language kept; else what `LC_ALL`, `LC_MESSAGES` or `LANG` says, the first of
          them set; else English.
        """
        if self.language:
            return self.language
        return next((environ[one] for one in _LOCALE if environ.get(one)), "en")


#: What was chosen in this process and could not be written down: kept for as long as it runs.
_unwritten: Kept | None = None


def _of(held: object) -> Kept:
    """What a reading of `settings.toml` keeps, anything it does not know read as not there."""
    said = cast("dict[str, Any]", held) if isinstance(held, dict) else {}
    theme, appearance, language = (
        said.get(one) for one in ("theme", "appearance", "language")
    )
    return Kept(
        theme=theme if theme in humanfia.PRESETS else "humanize",
        appearance=appearance if appearance in APPEARANCES else "auto",
        language=language if language in LANGUAGES else "",
    )


def read() -> Kept:
    """What is kept now: every default, where nothing was written."""
    return _unwritten or _of(settings.read().get(_KEY))


def keep(
    *,
    theme: str | None = None,
    appearance: str | None = None,
    language: str | None = None,
) -> Kept:
    """Keeps what was chosen, leaving what was not named as it was.

    Written into `settings.toml`, and where that cannot be written kept for this process,
    without a word: how the interface looks is not worth an error.

    Args:
      theme: The preset, by its key, or None to leave it.
      appearance: Which side, one of :data:`APPEARANCES`, or None to leave it.
      language: The language, "" for the system's, or None to leave it.

    Returns:
      What is kept now.
    """
    global _unwritten  # noqa: PLW0603 -- one person a process
    given = {
        name: value
        for name, value in (
            ("theme", theme),
            ("appearance", appearance),
            ("language", language),
        )
        if value is not None
    }

    def change(held: dict[str, Any]) -> None:
        # Over what could not be written before, where anything could not: it was chosen.
        was = _unwritten or _of(held.get(_KEY))
        now: object = held.get(_KEY)
        # Beside whatever else is under the key, which is somebody's.
        beside = cast("dict[str, Any]", now) if isinstance(now, dict) else {}
        held[_KEY] = {**beside, **asdict(replace(was, **given))}

    try:
        kept = _of(settings.changes(change).get(_KEY))
    except (OSError, ValueError):
        _unwritten = replace(read(), **given)
        return _unwritten
    _unwritten = None
    return kept


def overridden(environ: Mapping[str, str], available: Mapping[str, object]) -> str:
    """Which variable says how the interface looks, whatever is kept.

    Args:
      environ: The process environment.
      available: Every theme there is, by name.

    Returns:
      `TEXTUAL_THEME` where it names a theme there is, `NO_COLOR` where that is set, the
      first of the two that holds, or "" where what is kept decides.
    """
    if environ.get("TEXTUAL_THEME", "") in available:
        return "TEXTUAL_THEME"
    return "NO_COLOR" if environ.get("NO_COLOR") else ""


# -- Telling the system ------------------------------------------------------------------------

#: The interfaces whose terminal has said, at least once, whether it is being looked at.
_reporting: WeakSet[App[Any]] = WeakSet()

#: What a terminal that takes OSC 777 says it is: urxvt, where the sequence comes from, foot,
#: and everything built on VTE.
_RXVT: Final = ("rxvt", "foot")

#: What a terminal inside another says it is: tmux, and screen.
_WITHIN: Final = ("tmux", "screen")

#: The terminals that show OSC 9 as a notification of the system's own, by what they say
#: they are in `TERM_PROGRAM`.
_ITERM: Final = ("iTerm.app", "ghostty", "WezTerm", "kitty", "WarpTerminal")


def hears_focus(app: App[Any]) -> None:
    """Has an interface remember that its terminal says when it is and is not looked at.

    A terminal that says so says it only as it changes, and one that never does looks, from
    here, exactly like one that is looked at all day: the first word of it is what tells them
    apart.

    Args:
      app: The interface.
    """

    def reported() -> None:
        _reporting.add(app)

    app.watch(app, "app_focus", reported, init=False)


def wanted(*, reports: bool, focused: bool) -> bool:
    """Whether the system is told of a notice now.

    Args:
      reports: Whether the terminal has ever said if it is looked at.
      focused: Whether it is looked at, as far as it has said.

    Returns:
      False only where the terminal says it is being looked at: what is on the screen in
      front of somebody needs no second telling.
    """
    return not (reports and focused)


def _way(environ: Mapping[str, str]) -> Literal["777", "9", ""]:
    """Which sequence a terminal shows as a system notification, or "" where none is known."""
    term = environ.get("TERM", "")
    # Inside tmux or screen the variables are the terminal's outside it, and a sequence
    # neither knows goes no further: the bell does.
    if environ.get("TMUX") or environ.get("STY") or term.startswith(_WITHIN):
        return ""
    if environ.get("VTE_VERSION") or term.startswith(_RXVT):
        return "777"
    if (
        environ.get("TERM_PROGRAM") in _ITERM
        or environ.get("WT_SESSION")
        or term in ("xterm-kitty", "xterm-ghostty")
    ):
        return "9"
    return ""


def sequence(environ: Mapping[str, str], title: str, body: str) -> str:
    """What is written to a terminal to have the system show one notification.

    OSC 777 where the terminal is one that takes it (urxvt, foot, anything on VTE); OSC 9
    where it is one known to show that (iTerm2, Ghostty, WezTerm, kitty, Warp, Windows
    Terminal); and to any other, and to any inside tmux or screen, the bell, which every
    terminal has a setting for, with OSC 9 after it, which one that does not know it
    ignores. One of them only where one is known, so that a terminal knowing both shows a
    notice once.

    Args:
      environ: The process environment, which says which terminal it is.
      title: What the notice is: its kind.
      body: What it is of, or "".

    Returns:
      The bytes, as text. Nothing in `title` or `body` can end the sequence early or say
      anything else to the terminal: every control character is a space.
    """
    title, body = (re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", one) for one in (title, body))
    way = _way(environ)
    if way == "777":
        # Its fields are parted by `;`, which what an agent wrote may hold.
        return f"\x1b]777;notify;{title.replace(';', ',')};{body.replace(';', ',')}\x07"
    told = f"{title}: {body}" if body else title
    return f"{'' if way else '\x07'}\x1b]9;{told}\x07"


def tells(app: App[Any], environ: Mapping[str, str], title: str, body: str) -> bool:
    """Tells the system of one notice, through the terminal, unless the terminal is looked at.

    Args:
      app: The interface, whose terminal is written to.
      environ: The process environment.
      title: What the notice is.
      body: What it is of.

    Returns:
      Whether anything was written: nothing is with no terminal to write to, nor while the
      terminal says it is being looked at.
    """
    driver = app._driver  # noqa: SLF001  # pyright: ignore[reportPrivateUsage] -- Textual has no public way to write a sequence of one's own
    if app.is_headless or driver is None:
        return False
    if not wanted(reports=app in _reporting, focused=app.app_focus):
        return False
    with contextlib.suppress(OSError):
        driver.write(sequence(environ, title, body))
        return True
    return False
