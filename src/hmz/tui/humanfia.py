"""How the terminal interface looks: humanfia's colours, drawn the constructivist way.

The colours are the web page's own (`src/hmz/web/static/style.css`), so that an epic is the
same cyan in a terminal as in a browser, and they mean what they mean there: cyan is what can
be followed or has the keys, pink is what is pressed or picked out, lavender and gold come
third, and green -- the mark's -- is only ever set beside cyan, never beside pink.

The drawing is the mark's (`docs/.vitepress/theme/humanfia/logo.ts`): flat planes, heavy
rules, square corners and one diagonal. Nothing is rounded and nothing is shaded; what
separates two things is a rule or a change of plane, and what matters most on a screen is the
one thing on it in pink.

Humanfia's own two themes are `humanfia-dark` and `humanfia-light`, and `terminal` names no
colour of its own and so reads as part of whatever terminal it is in. Beside them are the
page's presets (`src/hmz/web/static/presets.js`), a light and a dark of each, said in the same
few colours and worked out the same way. Humanfia is what the interface opens in; `NO_COLOR`,
`TEXTUAL_THEME` and Settings > Themes say otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

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
    "PRESETS",
    "RULE",
    "SQUARE",
    "THEMES",
    "Pair",
    "chosen",
    "mark",
    "named",
    "preset",
    "side",
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


class Pair(NamedTuple):
    """One of the page's presets: what it is called, and the few colours each side is said in.

    Attributes:
      name: What the page calls it, in English.
      light: Its light side: `paper`, `side`, `ink`, and its accents -- `accent` where the
        page is live or followed, `highlight` where something is picked out, `brand` for the
        mark, `tertiary` and `gold` -- or nothing for humanfia's own.
      dark: Its dark side, said the same way.
    """

    name: str
    light: Mapping[str, str] = {}
    dark: Mapping[str, str] = {}


#: Every preset of the page, by the key its themes' names start with, in the page's order:
#: `PAIRS` of `src/hmz/web/static/presets.js`, value for value.
# fmt: off
PRESETS: Final[dict[str, Pair]] = {
    "humanize": Pair("Humanize Green"),
    "temperate-gold": Pair(
        "Temperate Gold",
        {
            "paper": "#fbf7ec", "side": "#f1e8d2", "ink": "#2b2115",
            "accent": "#c9a24a", "accentInk": "#7a5a14", "highlight": "#b9826a",
            "highlightInk": "#8a4f35", "brand": "#d4a23c", "tertiary": "#7d8fb3",
            "gold": "#e0b04a",
        },
        {
            "paper": "#17130c", "side": "#100d08", "ink": "#f3ead6",
            "accent": "#e3bf6a", "accentInk": "#f0d38f", "highlight": "#d9a58a",
            "highlightInk": "#ebbfa6", "brand": "#e3b04f", "tertiary": "#a9b8d8",
            "gold": "#f2c862",
        },
    ),
    "concordant-scarlet": Pair(
        "Concordant Scarlet",
        {
            "paper": "#fcf5ef", "side": "#f5e6dc", "ink": "#2a1414",
            "accent": "#c8322b", "accentInk": "#9e1f1a", "highlight": "#d9a24a",
            "highlightInk": "#7f5a12", "brand": "#d6463d", "tertiary": "#8c7fb8",
            "gold": "#d9a440",
        },
        {
            "paper": "#1a0f0f", "side": "#120a0a", "ink": "#f6e9e4",
            "accent": "#f0645a", "accentInk": "#ff8f86", "highlight": "#f0c46a",
            "highlightInk": "#f5d38c", "brand": "#e04b42", "tertiary": "#b5a8e0",
            "gold": "#f2c862",
        },
    ),
    "restrained-crimson": Pair(
        "Restrained Crimson",
        {
            "paper": "#faf3ec", "side": "#f1e2d4", "ink": "#2a1612",
            "accent": "#a62c22", "accentInk": "#8a2219", "highlight": "#a8641e",
            "highlightInk": "#8a5418", "brand": "#b8322a", "tertiary": "#6f7fa8",
            "gold": "#d1a03c",
        },
        {
            "paper": "#190f0d", "side": "#110a08", "ink": "#f5e6dc",
            "accent": "#e05a4c", "accentInk": "#f08a7e", "highlight": "#f0b06a",
            "highlightInk": "#f5c48e", "brand": "#d9473a", "tertiary": "#a6b4dc",
            "gold": "#f2c862",
        },
    ),
    "critical-teal": Pair(
        "Critical Teal",
        {
            "paper": "#f2f7f6", "side": "#e2ecea", "ink": "#12171e",
            "accent": "#2e8f95", "accentInk": "#1d6a70", "highlight": "#4d6aa8",
            "highlightInk": "#34508a", "brand": "#3aa7a0", "tertiary": "#8b72d6",
            "gold": "#c9a24a",
        },
        {
            "paper": "#0f1518", "side": "#0a0f11", "ink": "#e4f0ee",
            "accent": "#6fd3c9", "accentInk": "#9ae4dc", "highlight": "#8fb0f0",
            "highlightInk": "#b0c8f5", "brand": "#4fc2b8", "tertiary": "#b9a6f5",
            "gold": "#e6c46a",
        },
    ),
    "desirous-indigo": Pair(
        "Desirous Indigo",
        {
            "paper": "#f6f3f5", "side": "#ebe5ea", "ink": "#1c1826",
            "accent": "#3d4a8c", "accentInk": "#2f3a78", "highlight": "#b07a8a",
            "highlightInk": "#87505f", "brand": "#383d76", "tertiary": "#9a8fb8",
            "gold": "#d4a440",
        },
        {
            "paper": "#14121c", "side": "#0e0c14", "ink": "#ece6f0",
            "accent": "#8f9cf0", "accentInk": "#b0baf7", "highlight": "#e0a8b8",
            "highlightInk": "#edc0cc", "brand": "#7f8de6", "tertiary": "#c5b8e8",
            "gold": "#f0c862",
        },
    ),
    "peaceful-lilac": Pair(
        "Peaceful Lilac",
        {
            "paper": "#f7f2f7", "side": "#ece2ee", "ink": "#22182a",
            "accent": "#8d5c9d", "accentInk": "#6e3f7e", "highlight": "#d98fb0",
            "highlightInk": "#a3466f", "brand": "#9e7eaf", "tertiary": "#5d7fb0",
            "gold": "#c9a24a",
        },
        {
            "paper": "#151019", "side": "#0e0a11", "ink": "#efe6f2",
            "accent": "#c5a3e0", "accentInk": "#d7bdf0", "highlight": "#f0a8c8",
            "highlightInk": "#f5c0d8", "brand": "#bb92d6", "tertiary": "#9cb8f0",
            "gold": "#f2c862",
        },
    ),
    "hateful-silver": Pair(
        "Hateful Silver",
        {
            "paper": "#f5f5f7", "side": "#e8e7ec", "ink": "#1d1820",
            "accent": "#5a6a8c", "accentInk": "#3f4d6e", "highlight": "#b8423e",
            "highlightInk": "#9a2e2a", "brand": "#c9a24a", "tertiary": "#8c87a8",
            "gold": "#d9a440",
        },
        {
            "paper": "#121115", "side": "#0c0b0e", "ink": "#ecebf0",
            "accent": "#a9b8dc", "accentInk": "#c2cdea", "highlight": "#f07a6e",
            "highlightInk": "#f59a90", "brand": "#e0b960", "tertiary": "#b8b3d4",
            "gold": "#f2c862",
        },
    ),
    "devoted-pink": Pair(
        "Devoted Pink",
        {
            "paper": "#fdf6f5", "side": "#f7e6e6", "ink": "#2a1520",
            "accent": "#e07a98", "accentInk": "#b0406a", "highlight": "#3fb8cf",
            "highlightInk": "#0f7385", "brand": "#d4566e", "tertiary": "#a993c6",
            "gold": "#d9a84a",
        },
        {
            "paper": "#1a1016", "side": "#120b0f", "ink": "#f7e8ee",
            "accent": "#ff94b8", "accentInk": "#ffb0c9", "highlight": "#6fd6ea",
            "highlightInk": "#95e3f0", "brand": "#e0566e", "tertiary": "#c9b4e6",
            "gold": "#f2c862",
        },
    ),
    "self-negating-plum": Pair(
        "Self-Negating Plum",
        {
            "paper": "#f6f2f5", "side": "#ebe3ea", "ink": "#1e1622",
            "accent": "#6b3a63", "accentInk": "#5a2d53", "highlight": "#2f7fae",
            "highlightInk": "#24688f", "brand": "#673550", "tertiary": "#8c7fb8",
            "gold": "#c9a24a",
        },
        {
            "paper": "#141017", "side": "#0d0a10", "ink": "#efe6f0",
            "accent": "#c48ab8", "accentInk": "#d8a8cf", "highlight": "#7fc4ea",
            "highlightInk": "#a2d4f0", "brand": "#b0608f", "tertiary": "#b5a8e0",
            "gold": "#f2c862",
        },
    ),
    "dominant-azure": Pair(
        "Dominant Azure",
        {
            "paper": "#f3f7fb", "side": "#e3ecf6", "ink": "#141c2e",
            "accent": "#3a7fc0", "accentInk": "#24609c", "highlight": "#8a7fc0",
            "highlightInk": "#5c519a", "brand": "#5497ce", "tertiary": "#3fa8b9",
            "gold": "#d9a440",
        },
        {
            "paper": "#0e1420", "side": "#090e17", "ink": "#e6eef8",
            "accent": "#7fb8f0", "accentInk": "#a6cff5", "highlight": "#b8b0f0",
            "highlightInk": "#ccc6f5", "brand": "#70b0e8", "tertiary": "#70d6f7",
            "gold": "#f2c862",
        },
    ),
    "surviving-jade": Pair(
        "Surviving Jade",
        {
            "paper": "#f5f3ee", "side": "#e9e5dc", "ink": "#1b1518",
            "accent": "#2f8a74", "accentInk": "#1f6656", "highlight": "#b8923e",
            "highlightInk": "#7d5d14", "brand": "#3a9a80", "tertiary": "#8f6a4a",
            "gold": "#d1a03c",
        },
        {
            "paper": "#141213", "side": "#0d0c0c", "ink": "#f0e9de",
            "accent": "#6fd0b0", "accentInk": "#95dec6", "highlight": "#e6c070",
            "highlightInk": "#f0d28f", "brand": "#4fc09c", "tertiary": "#c4a688",
            "gold": "#f2c862",
        },
    ),
    "lamenting-orchid": Pair(
        "Lamenting Orchid",
        {
            "paper": "#fdf5f8", "side": "#f8e6ee", "ink": "#2a1724",
            "accent": "#c95f98", "accentInk": "#a3437a", "highlight": "#5aa8c8",
            "highlightInk": "#246985", "brand": "#e08ab4", "tertiary": "#a993cf",
            "gold": "#d9b04a",
        },
        {
            "paper": "#1a1018", "side": "#120b10", "ink": "#f8e9f1",
            "accent": "#f0a0c8", "accentInk": "#f5bcd8", "highlight": "#9ad8f0",
            "highlightInk": "#b8e4f5", "brand": "#e88ec0", "tertiary": "#c9b4ec",
            "gold": "#f2c862",
        },
    ),
}
# fmt: on

#: The pair that is humanfia's own, whose two themes keep the names they always had.
_OWN: Final = "humanize"


def _mixed(one: str, other: str, by: float) -> str:
    """Two colours mixed, `by` of the way from the first to the second, as the page mixes them."""
    parts = (
        (int(one[at : at + 2], 16), int(other[at : at + 2], 16)) for at in (1, 3, 5)
    )
    # Rounded half up, as `Math.round` does, not to the even number.
    return "#" + "".join(f"{int(a + (b - a) * by + 0.5):02x}" for a, b in parts)


def _worked(
    said: Mapping[str, str], base: Mapping[str, str], *, dark: bool
) -> dict[str, str]:
    """Every colour a theme is drawn from, worked out of the few a preset's side is said in.

    As `colours` of `presets.js` works them out: the planes from the paper, the greys from
    the ink, the lines from the ink seen through -- mixed here, a terminal's cell having one
    colour and nothing behind it to see through to. What a preset does not say -- done,
    failed, the last two lanes -- is humanfia's own of that side.
    """
    paper, ink = said["paper"], said["ink"]
    return {
        **base,
        "paper": paper,
        "ink": ink,
        "surface": _mixed(paper, ink, 0.06) if dark else _mixed(paper, "#ffffff", 0.5),
        "raised": _mixed(paper, ink, 0.1) if dark else _mixed(paper, "#ffffff", 0.85),
        "ink-2": _mixed(ink, paper, 0.25 if dark else 0.3),
        "ink-3": _mixed(ink, paper, 0.42 if dark else 0.32),
        "line": _mixed(paper, ink, 0.12),
        "line-strong": _mixed(paper, ink, 0.3 if dark else 0.28),
        "cyan": said["accent"],
        "cyan-ink": said["accentInk"],
        "pink": said["highlight"],
        "pink-ink": said["highlightInk"],
        "green": said["brand"],
        "lavender": said["tertiary"],
        "gold": said["gold"],
    }


def named(pair: str, side: str) -> str:
    """What one side of a preset is called as a theme.

    Args:
      pair: The preset's key, one of `PRESETS`.
      side: `light` or `dark`.

    Returns:
      `humanfia-<side>` for humanfia's own, which keep the names they always had, and
      `<pair>-<side>` for any other.
    """
    return f"humanfia-{side}" if pair == _OWN else f"{pair}-{side}"


def preset(
    key: str, light: Mapping[str, str], dark: Mapping[str, str]
) -> tuple[Theme, Theme]:
    """The two themes of one preset, drawn by humanfia's rules in the preset's colours.

    Args:
      key: The preset's key, which its themes are named by -- see `named`.
      light: The few colours its light side is said in, as `Pair.light` holds them; nothing
        for humanfia's own palette.
      dark: Its dark side.

    Returns:
      The light theme and the dark one.
    """
    return (
        _theme(
            named(key, "light"),
            _worked(light, LIGHT, dark=False) if light else LIGHT,
            dark=False,
        ),
        _theme(
            named(key, "dark"),
            _worked(dark, DARK, dark=True) if dark else DARK,
            dark=True,
        ),
    )


#: Every theme that is humanfia's, by name: each preset's two, its own first.
THEMES: Final = {
    theme.name: theme
    for key, pair in PRESETS.items()
    for theme in reversed(preset(key, pair.light, pair.dark))
}


def side(environ: Mapping[str, str]) -> str:
    """Which side of a preset the terminal asks for.

    Args:
      environ: The process environment.

    Returns:
      `light` where the terminal says its background is (`COLORFGBG`, which is told rather
      than asked for), and `dark` where it says nothing.
    """
    # `15;0`: the foreground, then the background, each one of the sixteen; 7 and 15 are the
    # two whites.
    ground = environ.get("COLORFGBG", "").rpartition(";")[2]
    return "light" if ground in ("7", "15") else "dark"


def chosen(
    environ: Mapping[str, str], available: Mapping[str, object], kept: str = ""
) -> str:
    """The theme the interface opens in.

    Args:
      environ: The process environment.
      available: Every theme there is, by name.
      kept: What Settings > Themes keeps: a theme's name; a preset's key, for whichever
        of its sides the terminal asks for; `light` or `dark`, for that side of humanfia's
        own; or "" for following the terminal in humanfia's own.

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
    return named(kept if kept in PRESETS else _OWN, side(environ))


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
