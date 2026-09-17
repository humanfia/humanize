"""What a signed-in Cursor account lists, and the catalogue written down as if it had answered.

`tests/{unit,integration}/agents/test_cursor.py` are two halves of one subject: a rung is no
parameter of a Cursor model, it is part of the id, so what a flow asked for becomes a name and
a name this account does not list is refused. The unit half asks the driver that question with
nothing running; the integration half drives a stand-in `cursor-agent` on PATH and reads the
call back off it. Both have to be told what the account lists before either can say anything,
and both say it by writing a catalogue where humanize keeps one.

Written down once here because that is a fact about somebody else's CLI and about humanize's
own on-disk shape, neither of which is either half's to own: a list that grew a variant in the
tier CI runs and not in the other is a refusal being checked against last month's account.

Here rather than in a conftest because these are imported by name, and a conftest is a pytest
plugin rather than a module to import from -- and because the two halves are no longer under
one directory to put a conftest in.
"""

from __future__ import annotations

import json

from hmz.coganchor import models
from hmz.coganchor.agents import CursorAgentConfig

#: The configuration both halves start from. The model is one `ACCOUNT` lists, which is the
#: whole of what makes either half mean anything: a configuration naming a model the account
#: does not list is refused before it reaches any of the questions being asked.
CURSOR = CursorAgentConfig(model="composer-2.5", effort="high")

#: What a signed-in account lists, as `cursor-agent models` prints it: a bare id beside the
#: variants that carry a rung, one that is listed with no variant at all, and the same model
#: again with the service it can be served on written behind it.
ACCOUNT = (
    "gpt-5.2",
    "gpt-5.2-low",
    "gpt-5.2-high",
    "gpt-5.2-xhigh",
    "composer-2.5",
    "composer-2.5-fast",
    "auto",
)


def kept(named: tuple[str, ...]) -> None:
    """Writes a catalogue down as if this account had just been asked what it runs.

    Args:
      named: The ids, as the account lists them.
    """
    at = models.where("cursor-agent")
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        json.dumps(
            {
                "asked": "2026-09-17T00:00:00Z",
                "models": [
                    {"name": one, "efforts": [], "swarms": False} for one in named
                ],
            }
        ),
        encoding="utf-8",
    )
