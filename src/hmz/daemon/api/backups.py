"""The epics a backup target holds, and one fetched back: `backups.*` (Section 4.16.8 of daemon.md).

And the chats it holds, each said to be one, which are fetched back among this machine's chats.

Each asks the target's git repository afresh, which can take a while, on the call's own
thread; what the repository said is told without a credential its URL carried.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.daemon.api.runs import CHATS, RUNS, Runs, reason, resolved
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hmz.rpc import Call, Handler

__all__ = ["METHODS", "pulled", "stored"]


def stored(runs: Runs, target: str, chats: Runs | None = None) -> dict[str, Any]:
    """The epics and chats a target holds, newest first, as `backups.epics` answers it.

    Args:
      runs: The runs here, which say which of those this machine holds.
      target: The target, by name.
      chats: The chats here, which say the same of the chats it holds, or None for none.

    Raises:
      RpcError: 400 for a target there is not, 502 where it cannot be reached.
    """
    hmz = runs.hmz()
    held = _fetched(hmz, target, lambda: hmz.backups.listed(target))
    # Here is an epic of that name run in that workspace, as a download would land it.
    here = {
        (resolved(one.workspace), one.name)
        for one in [*runs.all(), *(chats.all() if chats is not None else ())]
    }
    return {
        "epics": [
            one._asdict() | {"here": (resolved(one.workspace), one.epic) in here}
            for one in reversed(held)
        ]
    }


def pulled(runs: Runs, target: str, key: str) -> dict[str, Any]:
    """One epic or chat downloaded from a target, as `backups.pull` answers it.

    Args:
      runs: The runs here.
      target: The target, by name.
      key: The epic, `<machine>/<workspace>/<epic>`.

    Raises:
      RpcError: 400 for a target or a key there is not, 502 where it cannot be reached.
    """
    hmz = runs.hmz()
    at = _fetched(hmz, target, lambda: hmz.backups.pulled(target, key))
    return {"name": at.name}


def _fetched[T](hmz: Any, target: str, fetch: Callable[[], T]) -> T:
    """What a backup target answered, or a refusal saying why not, with nothing signed in."""
    try:
        return fetch()
    except ValueError as why:
        raise RpcError(Code.REFUSED, reason(hmz.verses.plain(str(why)))) from why
    except OSError as why:
        said = hmz.verses.plain(str(why))
        raise RpcError(Code.UPSTREAM, reason(f"{target}: {said}")) from why


def _epics(call: Call) -> dict[str, Any]:
    return stored(RUNS, call.params["target"], CHATS)


def _pull(call: Call) -> dict[str, Any]:
    return pulled(RUNS, call.params["target"], call.params["key"])


#: The methods of `backups.*`.
METHODS: Mapping[str, Handler] = {"backups.epics": _epics, "backups.pull": _pull}
