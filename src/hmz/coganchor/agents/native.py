"""Native input: what a harness takes from a person at its own prompt, beyond prose.

A chat is somebody talking to a coding agent as they would at its own command line, so what
they type there has to mean what it means there: Claude Code's `/` commands and skills,
Codex's `$` skills, `!` for a shell command, `@` for a file. Each driver says which of those
the way hmz drives its harness can carry, as a catalog of :class:`NativeCommand`, and serves a
turn whose prompt is such a line when the turn is marked native (``stream(..., native=True)``,
read back as ``native_turn``).

What each entry is served by is :data:`How`:

- ``pass``: the line goes into the turn as it was typed, and the harness expands it itself.
- ``call``: the driver calls the harness's own operation for it -- a compaction, a review, a
  skill or mention input item, the app server's shell command.
- ``emulate``: hmz does what the harness's interface would have done (a `!` command run in the
  chat's workspace, its output carried into the next turn), the chat rather than the driver.
- ``refuse``: only the harness's own interactive interface serves it; the line is refused,
  saying so.

A turn that is not marked native is a flow's prompt, and a driver never reads one as anything
but text: a flow that writes `/compact` into a prompt is talking about compaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: The characters a native entry is typed after.
Sigil = Literal["/", "$", "!", "@"]

#: How a native entry is served; see the module's docstring.
How = Literal["pass", "call", "emulate", "refuse"]


@dataclass(frozen=True, slots=True)
class NativeCommand:
    """One entry of a harness's native catalog.

    Attributes:
      sigil: What it is typed after.
      name: What follows the sigil, `compact` for `/compact`; "" for `!` and `@`, whose
        argument is a command or a path rather than a name.
      about: One line on what it does, for an offer list.
      how: How it is served.
    """

    sigil: Sigil
    name: str
    about: str
    how: How
