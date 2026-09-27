"""What a terminal says a key was, read whole however long an input method made it.

Textual asks a terminal that speaks the kitty keyboard protocol to report every key as an
escape sequence with the text it typed inside, which is what lets `shift+enter` arrive as
itself. An input method commits what was composed as one of those reports: the key that
confirmed it -- space, or the number of the candidate -- and then every character committed, as
code points between colons. Ghostty sends 你帮我, confirmed with space, as

    ESC [ 32 ; ; 20320 : 24110 : 25105 u

and Textual gives up on a sequence past 32 characters, typing out what it has read as though
each of those were a key. So anything longer than four characters of Chinese, or about seven
letters, landed in the prompt as `^[32;;20320:24110:25105:...u`.

The ceiling is raised here to what one commit can be. It was also what kept two of the checks
Textual makes against every character of a sequence from backtracking without end: the one for
a key report, answered here with a pattern that takes exactly what Textual's takes in linear
time, and the one for a resize reported in band, held to the length it was only ever tried at.

All of it is Textual's to fix, and is asked of it in Textualize/textual#6721: once a release has
it, this module goes.
"""

# The ceiling and both patterns are private to Textual's parser, and changing them there is
# the whole of what this module is for.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import re

from textual import _xterm_parser

__all__ = ["LONGEST", "reads_long_reports"]

#: How long a sequence may run before Textual stops reading it as one: a commit of some hundred
#: and seventy characters of Chinese, at six characters of report to each. Every character of a
#: sequence is checked against all of it again, so this is also what one that never ends costs --
#: tens of milliseconds at this length, where the pattern Textual ships takes ten seconds at a
#: quarter of it.
LONGEST = 1 << 10

#: Textual's own ceiling, which is the one the resize check stays held to.
_CAP = _xterm_parser._MAX_SEQUENCE_SEARCH_THRESHOLD

#: A key report as Textual reads one -- up to three fields, and a semicolon that may follow them
#: -- without the nested repetition that has its pattern try every way of splitting a run of
#: digits in three.
_REPORT = re.compile(r"\x1b\[([\d:]*(?:;[\d:]*){0,2};?)([u~ABCDEFHPQRS])")

#: A resize reported in band as Textual reads one, and only at a length it was ever tried at: the
#: wildcard in each of its four fields takes the separators too, so on anything longer it
#: backtracks as badly as the key report's did.
_RESIZE = re.compile(
    rf"(?=[\s\S]{{0,{_CAP}}}\Z){_xterm_parser._re_in_band_window_resize.pattern}"
)


def reads_long_reports() -> None:
    """Has Textual read a key report whole, however long an input method made it."""
    _xterm_parser._MAX_SEQUENCE_SEARCH_THRESHOLD = LONGEST
    _xterm_parser._re_extended_key = _REPORT
    _xterm_parser._re_in_band_window_resize = _RESIZE
