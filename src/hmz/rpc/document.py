"""The OpenRPC document every method of a session is listed in (Section 6.11 of wire.md).

`protocol/openrpc.json` is outside the package and so outside the wheel, which is built from
`src/hmz` alone. The copy beside this module is what an install reads, and the suite holds it
byte for byte to the protocol's.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any, cast

__all__ = ["document"]


@cache
def document() -> dict[str, Any]:
    """The OpenRPC document, read once.

    Returns:
      The document as parsed; one object shared by every caller, which none of them changes.
    """
    text = resources.files(__package__).joinpath("openrpc.json").read_text("utf-8")
    return cast("dict[str, Any]", json.loads(text))
