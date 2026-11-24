"""How the terminal interface looks: humanfia's colours, drawn the constructivist way.

The colours are the web page's own (`src/hmz/web/static/style.css`), so that an epic is the
same cyan in a terminal as in a browser, and they mean what they mean there: cyan is what can
be followed or has the keys, pink is what is pressed or picked out, lavender and gold come
third, and green -- the mark's -- is only ever set beside cyan, never beside pink.

The drawing is the mark's (`docs/.vitepress/theme/humanfia/logo.ts`): flat planes, heavy
rules, square corners and one diagonal. Nothing is rounded and nothing is shaded; what
separates two things is a rule or a change of plane, and what matters most on a screen is the
one thing on it in pink.

Three themes: `humanfia-dark` and `humanfia-light`, and `terminal`, which names no colour of
its own and so reads as part of whatever terminal it is in. Humanfia is what the interface
opens in; `NO_COLOR`, `TEXTUAL_THEME` and Settings > Themes say otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from textual.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "BAR",
    "BLOCK",
    "CUT",
    "DARK",
    "FALLBACK",
    "LIGHT",
    "MARK",
    "POINT",
    "RULE",
    "SQUARE",
    "THEMES",
    "chosen",
    "mark",
]

#: The page's colours, by the names its stylesheet gives them.
LIGHT: Final = {
    "paper": "#f4f8f9",
    "surface": "#fbfdfd",
    "raised": "#ffffff",
    "ink": "#141a1f",
    "ink-2": "#435058",
    "ink-3": "#5d6a72",
    "line": "#d9dfe1",
    "line-strong": "#b5bfc3",
    "green": "#76b900",
    "pink": "#ec6fa3",
    "pink-ink": "#b83a72",
    "cyan": "#1fb3c7",
    "cyan-ink": "#0b7080",
    "lavender": "#8b72d6",
    "gold": "#d9a440",
    "done": "#2a9468",
    "fail": "#cf3552",
    "lane-5": "#4a8fd8",
    "lane-6": "#7f8d95",
}
DARK: Final = {
    "paper": "#0f1418",
    "surface": "#172026",
    "raised": "#1d272e",
    "ink": "#e6eff1",
    "ink-2": "#b3c3c8",
    "ink-3": "#82939a",
    "line": "#293339",
    "line-strong": "#4f5c62",
    "green": "#76b900",
    "pink": "#ff94c2",
    "pink-ink": "#ffa8cf",
    "cyan": "#4fd8ea",
    "cyan-ink": "#7fe4f1",
    "lavender": "#b9a6f5",
    "gold": "#f2c862",
    "done": "#5fdca3",
    "fail": "#ff6f88",
    "lane-5": "#86b8f2",
    "lane-6": "#94a3aa",
}

#: What a stylesheet asks for beyond Textual's own names, and what each is in a theme that
#: is not one of these -- the terminal's, or one `TEXTUAL_THEME` named.
FALLBACK: Final = {
    "hmz-green": "ansi_green",
    "hmz-pink": "ansi_magenta",
    "hmz-cyan": "ansi_cyan",
    "hmz-lavender": "ansi_blue",
    "hmz-gold": "ansi_yellow",
    "hmz-line": "ansi_bright_black",
    "hmz-line-strong": "ansi_bright_black",
    "hmz-ink-2": "ansi_default",
    "hmz-ink-3": "ansi_bright_black",
    "hmz-lane-1": "ansi_cyan",
    "hmz-lane-2": "ansi_magenta",
    "hmz-lane-3": "ansi_blue",
    "hmz-lane-4": "ansi_yellow",
    "hmz-lane-5": "ansi_bright_blue",
    "hmz-lane-6": "ansi_bright_black",
}

#: What the planes are cut from and ruled with.
RULE: Final = "━"
BAR: Final = "┃"
BLOCK: Final = "█"
SQUARE: Final = "■"
POINT: Final = "▸"
CUT: Final = "╱"  # noqa: RUF001 -- the one diagonal, which is not a solidus


def _theme(name: str, said: Mapping[str, str], *, dark: bool) -> Theme:
    return Theme(
        name=name,
        primary=said["cyan"],
        secondary=said["lavender"],
        accent=said["pink"],
        warning=said["gold"],
        error=said["fail"],
        success=said["done"],
        foreground=said["ink"],
        background=said["paper"],
        surface=said["surface"],
        panel=said["raised"],
        dark=dark,
        variables={
            "hmz-green": said["green"],
            "hmz-pink": said["pink"],
            "hmz-cyan": said["cyan"],
            "hmz-lavender": said["lavender"],
            "hmz-gold": said["gold"],
            "hmz-line": said["line"],
            "hmz-line-strong": said["line-strong"],
            "hmz-ink-2": said["ink-2"],
            "hmz-ink-3": said["ink-3"],
            # What is said quietly is the page's third ink: a colour of its own rather than
            # the text's own made fainter, so that what draws by hand can ask for it too.
            "text-muted": said["ink-3"],
            "foreground-muted": said["ink-3"],
            "hmz-lane-1": said["cyan"],
            "hmz-lane-2": said["pink"],
            "hmz-lane-3": said["lavender"],
            "hmz-lane-4": said["gold"],
            "hmz-lane-5": said["lane-5"],
            "hmz-lane-6": said["lane-6"],
            # What is under the cursor is what is picked out, so it is pink, with the paper
            # showing through as its text: a plane, not an outline.
            "block-cursor-background": said["pink"],
            "block-cursor-foreground": said["paper"],
            "block-cursor-text-style": "bold",
            "block-cursor-blurred-background": said["line-strong"],
            "block-cursor-blurred-foreground": said["ink"],
            "block-cursor-blurred-text-style": "none",
            "input-cursor-background": said["cyan"],
            "input-cursor-foreground": said["paper"],
            "input-selection-background": f"{said['cyan']} 35%",
            "border": said["line-strong"],
            "border-blurred": said["line"],
            "footer-key-foreground": said["cyan-ink"],
            "link-color": said["cyan-ink"],
            "scrollbar": said["line-strong"],
            "scrollbar-hover": said["ink-3"],
            "scrollbar-active": said["cyan"],
            "scrollbar-background": said["paper"],
        },
    )


#: The two themes that are humanfia's, by name.
THEMES: Final = {
    "humanfia-dark": _theme("humanfia-dark", DARK, dark=True),
    "humanfia-light": _theme("humanfia-light", LIGHT, dark=False),
}


def chosen(
    environ: Mapping[str, str], available: Mapping[str, object], kept: str = ""
) -> str:
    """The theme the interface opens in.

    Args:
      environ: The process environment.
      available: Every theme there is, by name.
      kept: What Settings > Themes keeps: a theme's name, `light`, `dark`, or "" for
        following the terminal.

    Returns:
      What `TEXTUAL_THEME` names where it names one; `terminal` under `NO_COLOR`; else what
      is kept; else humanfia, light where the terminal says its background is (`COLORFGBG`,
      which is told rather than asked for) and dark where it says nothing.
    """
    asked = environ.get("TEXTUAL_THEME", "")
    if asked in available:
        return asked
    if environ.get("NO_COLOR"):
        return "terminal"
    if kept in available:
        return kept
    if kept in ("light", "dark"):
        return f"humanfia-{kept}"
    # `15;0`: the foreground, then the background, each one of the sixteen; 7 and 15 are the
    # two whites.
    ground = environ.get("COLORFGBG", "").rpartition(";")[2]
    return "humanfia-light" if ground in ("7", "15") else "humanfia-dark"


#: The mark's outline and its dot, on the grid it is drawn on: 96 across, 108 down.
_PLANES: Final = (
    (0, 0), (24, 0), (24, 50), (96, 26), (96, 108),
    (72, 108), (72, 55), (24, 71), (24, 108), (0, 108),
)  # fmt: skip
_DOT: Final = (84, 12, 12)


def _inked(x: float, y: float) -> bool:
    """Whether a point of the grid is inside the mark."""
    across, down, radius = _DOT
    if (x - across) ** 2 + (y - down) ** 2 <= radius**2:
        return True
    inside = False
    for at, (x1, y1) in enumerate(_PLANES):
        x2, y2 = _PLANES[(at + 1) % len(_PLANES)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def mark(columns: int = 16) -> list[str]:
    """The H, drawn in cells: two stems, the one diagonal between them, and the dot.

    Args:
      columns: How many cells wide; it is nine rows tall at sixteen, and keeps its shape.

    Returns:
      Its rows, top first, each `columns` wide.
    """
    rows = max(round(columns * 9 / 16), 1)
    wide, tall = 96 / columns, 108 / (rows * 2)
    drawn: list[str] = []
    for row in range(rows):
        line = ""
        for column in range(columns):
            x = (column + 0.5) * wide
            upper = _inked(x, (2 * row + 0.5) * tall)
            lower = _inked(x, (2 * row + 1.5) * tall)
            line += (
                BLOCK if upper and lower else "▀" if upper else "▄" if lower else " "
            )
        drawn.append(line)
    return drawn


#: The mark at the size the interface opens with.
MARK: Final = tuple(mark())
