"""Plays a `.tape` into a terminal and writes what it showed as an asciicast.

    python cast.py /tapes/tui.tape /out/tui.cast

The documentation draws each demo in the reader's browser from the text a terminal was sent,
rather than showing a picture of it. This writes that text: it reads the same tape VHS reads,
types it into `bash` on a pseudo-terminal the size VHS would have drawn, and keeps every byte
that came back while the tape was showing, with the moment it came.

`pyte` keeps a copy of the screen as it goes, for `Wait+Screen` to read and for `Show` to
redraw: what a `Hide` did off camera is put on the recording as the screen it left behind,
in one go, rather than played. A redraw that leaves the screen as it was is left off.

Run by `render.sh`, inside the container its Dockerfile builds. Only what the tapes here use is
understood; anything else is an error rather than a guess.
"""

from __future__ import annotations

import codecs
import json
import os
import re
import shlex
import sys
import threading
import time
from pathlib import Path

import pexpect
import pyte

# VHS's own prompt: a purple `>`, and no user, host or path.
PROMPT = r"\[\e[38;2;90;86;224m\]> \[\e[0m\]"

KEYS = {
    "Enter": "\r",
    "Tab": "\t",
    "Escape": "\x1b",
    "Backspace": "\x7f",
    "Space": " ",
    "Up": "A",
    "Down": "B",
    "Right": "C",
    "Left": "D",
}

# pyte names the sixteen colours; a recording names them by number.
COLOURS = ["black", "red", "green", "brown", "blue", "magenta", "cyan", "white"]


def duration(text: str) -> float:
    """Seconds, from a tape's `500ms` or `2s`."""
    match = re.fullmatch(r"([\d.]+)(ms|s)?", text)
    if not match:
        raise ValueError(f"not a duration: {text}")
    value = float(match[1])
    return value / 1000 if match[2] == "ms" else value


def colour(value: str, *, background: bool) -> str | None:
    """The SGR parameters for one of pyte's colours, or None for the default."""
    if value == "default":
        return None
    base = 40 if background else 30
    name = value.removeprefix("bright")
    if name in COLOURS:
        return str(
            base + COLOURS.index(name) + (60 if value.startswith("bright") else 0)
        )
    if re.fullmatch(r"[0-9a-fA-F]{6}", value):
        r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
        return f"{base + 8};2;{r};{g};{b}"
    return None


class Terminal:
    """`bash` on a pseudo-terminal, with pyte keeping a copy of its screen."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.lock = threading.Lock()
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.events: list[tuple[float, str]] = []
        self.shown = False
        self.hidden = 0.0  # seconds spent off camera, taken out of every timestamp
        self.hid_at: float | None = time.monotonic()
        self.start = time.monotonic()
        self.modes = {"alt": False, "cursor": True, "keys": False}
        env = dict(os.environ, PS1=PROMPT, TERM="xterm-256color", COLORTERM="truecolor")
        self.child = pexpect.spawn(
            "bash",
            ["--norc", "--noprofile"],
            env=env,
            dimensions=(rows, cols),
            encoding=None,
        )
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def now(self) -> float:
        return time.monotonic() - self.start - self.hidden

    def read(self) -> None:
        while True:
            try:
                data = self.child.read_nonblocking(65536, timeout=0.05)
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                return
            self.answer(data)
            with self.lock:
                self.track(data)
                self.stream.feed(data)
                text = self.decoder.decode(data)
                if self.shown and text:
                    self.events.append((self.now(), text))

    def answer(self, data: bytes) -> None:
        """Say what a terminal would, to the few questions an interface asks of one."""
        if b"\x1b[6n" in data:
            y, x = self.screen.cursor.y + 1, self.screen.cursor.x + 1
            self.child.send(f"\x1b[{y};{x}R".encode())
        if b"\x1b[c" in data or b"\x1b[0c" in data:
            self.child.send(b"\x1b[?62;22c")
        for code in re.findall(rb"\x1b\](1[01]);\?", data):
            rgb = "e2e2/e4e4/eaea" if code == b"10" else "1616/1717/1d1d"
            self.child.send(f"\x1b]{code.decode()};rgb:{rgb}\x1b\\".encode())

    def track(self, data: bytes) -> None:
        for flag, mode in re.findall(rb"\x1b\[\?(1049|1047|47|25|1)([hl])", data):
            on = mode == b"h"
            if flag == b"25":
                self.modes["cursor"] = on
            elif flag == b"1":
                self.modes["keys"] = on
            else:
                self.modes["alt"] = on

    def screen_text(self) -> str:
        with self.lock:
            return "\n".join(self.screen.display)

    def repaint(self) -> str:
        """The screen as it stands, drawn from nothing."""
        out = ["\x1b[?1049h" if self.modes["alt"] else "", "\x1b[0m\x1b[2J\x1b[H"]
        for y in range(self.rows):
            out.append(f"\x1b[{y + 1};1H")
            line = self.screen.buffer[y]
            last = None
            for x in range(self.cols):
                char = line[x]
                if char.data == "":  # the right half of a wide character
                    continue
                sgr = ["0"]
                sgr += [
                    c
                    for c in (
                        colour(char.fg, background=False),
                        colour(char.bg, background=True),
                    )
                    if c
                ]
                for attr, code in (
                    ("bold", "1"),
                    ("italics", "3"),
                    ("underscore", "4"),
                    ("reverse", "7"),
                    ("strikethrough", "9"),
                ):
                    if getattr(char, attr):
                        sgr.append(code)
                if sgr != last:
                    out.append(f"\x1b[{';'.join(sgr)}m")
                    last = sgr
                out.append(char.data)
        cursor = self.screen.cursor
        out.append(f"\x1b[0m\x1b[{cursor.y + 1};{cursor.x + 1}H")
        out.append("\x1b[?25h" if self.modes["cursor"] else "\x1b[?25l")
        return "".join(out)

    def hide(self) -> None:
        with self.lock:
            self.shown = False
            self.hid_at = time.monotonic()

    def show(self) -> None:
        time.sleep(
            0.3
        )  # what the last hidden key set off, drawn before the screen is copied
        with self.lock:
            if self.hid_at is not None:
                self.hidden += time.monotonic() - self.hid_at
                self.hid_at = None
            self.events.append((self.now(), self.repaint()))
            self.shown = True

    def key(self, name: str) -> str:
        if name in ("Up", "Down", "Right", "Left"):
            return ("\x1bO" if self.modes["keys"] else "\x1b[") + KEYS[name]
        return KEYS[name]


class Tape:
    """A `.tape`, and the settings it makes."""

    def __init__(self, path: Path) -> None:
        self.lines = path.read_text().splitlines()
        self.settings = {
            "FontSize": "22",
            "Width": "1200",
            "Height": "600",
            "Padding": "60",
        }
        self.settings |= {"TypingSpeed": "50ms", "PlaybackSpeed": "1"}
        for line in self.lines:
            match = re.fullmatch(r"Set (\w+) (.+)", line.strip())
            if match:
                self.settings[match[1]] = match[2].strip('"')

    def size(self) -> tuple[int, int]:
        """The columns and rows VHS fits into its window, with its font and line height."""
        font = float(self.settings["FontSize"])
        pad = 2 * float(self.settings["Padding"])
        cols = int((float(self.settings["Width"]) - pad) // (font * 0.6))
        rows = int((float(self.settings["Height"]) - pad) // (font * 1.2))
        return cols, rows

    def play(self, term: Terminal) -> None:
        typing = duration(self.settings["TypingSpeed"])
        for number, raw in enumerate(self.lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            head, _, rest = line.partition(" ")
            command, _, speed = head.partition("@")
            if command in ("Set", "Output", "Screenshot", "Require"):
                continue
            if command == "Hide":
                term.hide()
            elif command == "Show":
                term.show()
            elif command == "Sleep":
                time.sleep(duration(rest))
            elif command == "Type":
                self.type(term, rest, duration(speed) if speed else typing)
            elif command.startswith("Wait"):
                self.wait(term, rest, duration(speed) if speed else 15.0, number)
            elif command.startswith("Ctrl+"):
                term.child.send(bytes([ord(command[-1].lower()) & 0x1F]))
            elif command in KEYS:
                for _ in range(int(rest.split()[0]) if rest else 1):
                    term.child.send(term.key(command).encode())
                    time.sleep(duration(speed) if speed else 0.1)
            else:
                raise SystemExit(f"line {number}: {command} is not understood here")

    def type(self, term: Terminal, rest: str, speed: float) -> None:
        # `Type "text" Enter`: the text in any of VHS's three quotes, maybe a key after it.
        match = re.fullmatch(r"""(["'`])(.*)\1\s*(\w+)?""", rest)
        if not match:
            raise SystemExit(f"cannot read the text in: Type {rest}")
        for char in match[2]:
            term.child.send(char.encode())
            time.sleep(speed)
        if match[3]:
            term.child.send(term.key(match[3]).encode())

    def wait(self, term: Terminal, rest: str, timeout: float, number: int) -> None:
        pattern = re.compile(rest.strip()[1:-1])
        deadline = time.monotonic() + timeout
        while not pattern.search(term.screen_text()):
            if time.monotonic() > deadline:
                screen = term.screen_text()
                raise SystemExit(
                    f"line {number}: never saw /{pattern.pattern}/:\n{screen}"
                )
            time.sleep(0.05)


# Output that comes within this many seconds of the first of it is one frame.
PIECES = 0.03

# An escape sequence written whole: CSI, OSC, or one of the two-byte kind.
WHOLE = re.compile(r"\x1b(\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[ -/]*[0-~])")


def state(screen: pyte.Screen) -> tuple[object, ...]:
    """Everything about a screen that the next byte written to it could depend on."""
    cursor = screen.cursor
    return (
        tuple(
            tuple(screen.buffer[y][x] for x in range(screen.columns))
            for y in range(screen.lines)
        ),
        (cursor.x, cursor.y, cursor.attrs, cursor.hidden),
        frozenset(screen.mode),
        screen.margins,
        (screen.charset, screen.g0_charset, screen.g1_charset),
    )


def changing(
    events: list[tuple[float, str]], cols: int, rows: int
) -> list[tuple[float, str]]:
    """The events, less the redraws that leave the screen as it was.

    An interface may redraw the whole of a screen nothing on which has changed, twice a second;
    kept, those redraws are most of a cast's size. Output that comes in pieces within a few
    milliseconds is taken as one frame -- never cut inside an escape sequence -- and a frame
    after which the screen, the cursor and the modes are as they were before it is left out.
    The last moment is kept, so that the recording lasts as long as the tape did.
    """
    frames: list[tuple[float, str]] = []
    for moment, text in events:
        if frames:
            began, held = frames[-1]
            tail = held[held.rfind("\x1b") :] if "\x1b" in held else ""
            if moment - began < PIECES or (tail and not WHOLE.match(tail)):
                frames[-1] = (began, held + text)
                continue
        frames.append((moment, text))

    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    kept: list[tuple[float, str]] = []
    before = state(screen)
    for began, text in frames:
        stream.feed(text)
        after = state(screen)
        if after != before:
            kept.append((began, text))
        before = after
    if events and (not kept or kept[-1][0] < events[-1][0]):
        kept.append((events[-1][0], ""))
    return kept


def main() -> None:
    """Record the tape named first into the cast named second."""
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    tape = Tape(source)
    cols, rows = tape.size()
    term = Terminal(cols, rows)
    tape.play(term)
    time.sleep(0.5)
    with term.lock:
        events = list(term.events)
    term.child.terminate(force=True)
    events = changing(events, cols, rows)

    speed = float(tape.settings["PlaybackSpeed"])
    header = {
        "version": 2,
        "width": cols,
        "height": rows,
        "env": {"TERM": "xterm-256color"},
    }
    with target.open("w") as out:
        out.write(json.dumps(header) + "\n")
        for moment, text in events:
            out.write(
                json.dumps([round(moment / speed, 3), "o", text], ensure_ascii=False)
                + "\n"
            )
    print(
        f"{target.name}: {cols}x{rows}, {len(events)} events, {shlex.quote(str(target))}"
    )


if __name__ == "__main__":
    main()
