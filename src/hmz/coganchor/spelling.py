"""Where an agent's model ends and its effort begins, wherever an agent is written down.

A leaf, and on purpose: `-a` reads an agent through :mod:`hmz.coganchor.backends`, while what
keeps one written down -- a settings file, the interface's sheet -- reads the same word back
without loading every fact about every CLI to do it. Both split it here, so they split it the
same way.
"""

from __future__ import annotations

import re

__all__ = ["parted"]

#: What an effort is spelled as, in every CLI's own words: words of letters joined by `-` or a
#: space -- `xhigh`, `extra-high`, `swarmmax`, `as configured`. Read wider than any ladder --
#: any case, `_` as a joint -- so that `High` or `x_high` is still an effort, and refused as
#: one off the ladder rather than run as part of a model nobody has. What follows a model's
#: own `:` is something else -- `gateway/mock/first-model`, `8b` -- and stays the model's.
_EFFORT = re.compile(r"[A-Za-z]+(?:[-_ ][A-Za-z]+)*")


def parted(said: str) -> tuple[str, str]:
    """What follows an agent's CLI, split into its model and its effort.

    Read from both ends: a model may hold slashes and colons of its own, while an effort never
    does. So the last `:` sets an effort off only where what follows it is spelled as one --
    nothing, or a word -- and is the model's own otherwise: MiniMax Code's
    `custom_provider:gateway/m` is one model, at no effort of its own. A model whose own name
    ends in `:` and a word is written with its effort after it, as `qwen3:latest:auto`.

    Args:
      said: `model[:effort]`.

    Returns:
      The model, and the effort as written: "" where none was, or the `:` had nothing after
      it.
    """
    model, colon, effort = said.rpartition(":")
    if colon and (not effort.strip() or _EFFORT.fullmatch(effort.strip())):
        return model, effort
    return said, ""
