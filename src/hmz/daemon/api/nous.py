"""`nous.*`: every nous, concrete and virtual, written, renamed and cleared.

A concrete nous is `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`, a virtual one a name standing for a
graph of other nous; each has its tries, its wait, its limit and the graph a turn goes to once
those are spent (Section 4.18.3 of the daemon protocol). The nous page `/settings` opens in the
terminal interface writes through the same object and into the same file.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.coganchor.nous import Nous
    from hmz.rpc import Handler

__all__ = ["METHODS", "clear", "listed", "rename", "scan", "scans", "write"]

#: The variable that turns the scan a daemon makes as it starts off.
SCAN = "HUMANIZE_SCAN"

#: How many harnesses a scan somebody asked for asks at once: asking one starts it.
_AT_ONCE = 4

#: The scan going on in this process, which a second one asked for meanwhile waits for.
_going: tuple[Future[list[dict[str, str]]], bool] | None = None
_GOING = threading.Lock()


def _shown(book: Any, one: Nous) -> dict[str, Any]:
    return {
        "name": one.name,
        "virtual": one.virtual,
        "tries": one.tries,
        "policy": one.policy,
        "timeout": one.timeout,
        "graph": book.shown(one.graph),
        "then": book.shown(one.then),
    }


def listed(hmz: Any) -> dict[str, Any]:
    """Every nous, the ways of waiting and picking there are, and the nous to name."""
    book = hmz.nous
    return {
        "nous": [_shown(book, one) for one in book.all()],
        "policies": [{"name": one.name, "about": one.about} for one in book.policies()],
        "default": book.default,
        "strategies": [
            {"name": one.name, "about": one.about} for one in book.strategies()
        ],
        "faults": list(book.faults()),
        "concrete": _concrete(hmz),
        "scanning": _going is not None,
    }


def _concrete(hmz: Any) -> list[str]:
    """Every concrete nous a graph could name: each model of each account, at no effort."""
    accounts, spec = hmz.accounts, hmz.nous.spec
    found = {
        spec(cli, model.name)
        for cli, models in hmz.installed().items()
        for model in models
    }
    found |= {
        spec(one.cli, model.name, one.name)
        for one in accounts.all()
        for model in accounts.models(one.cli, one.name)
    }
    return sorted(found)


def scan(hmz: Any, *, stale: bool = False) -> dict[str, Any]:
    """Asks every harness installed here what it runs, as each of its accounts.

    What each says is kept, as `accounts.models` keeps it, and is what `nous.list` answers as
    `concrete` from then on. One scan goes on at a time: one asked for while another is going
    waits for that one and answers what it found -- unless that one asks only the stale and
    this one asks all, which then scans in its turn, so that a scan somebody asked for is never
    answered by the lesser one a daemon starts with.

    Args:
      hmz: Humanize.
      stale: Whether only those never asked, or asked too long ago, are asked, one at a time:
        what a daemon does as it starts, behind everything it serves.

    Returns:
      What :func:`listed` answers afterwards, and `failed`: each `cli` and `account` that would
      not say, and `why`.
    """
    global _going  # noqa: PLW0603 -- one scan per process
    while True:
        with _GOING:
            held = _going
            mine = held is None
            if held is None:
                held = _going = (Future(), stale)
        going, lesser = held
        if mine:
            failed: list[dict[str, str]] = []
            try:
                failed = _asks(hmz, stale=stale)
            finally:
                with _GOING:
                    _going = None
                going.set_result(failed)
        found = going.result()
        if mine or stale or not lesser:
            return {**listed(hmz), "failed": found}


def _asks(hmz: Any, *, stale: bool) -> list[dict[str, str]]:
    accounts = hmz.accounts
    pairs = [
        (cli, name)
        for cli in hmz.installed()
        for name in ("", *(one.name for one in accounts.all(cli)))
        if not stale or accounts.stale(cli, name)
    ]

    def asks(pair: tuple[str, str]) -> dict[str, str] | None:
        cli, name = pair
        try:
            accounts.ask(cli, name)
        except Exception as why:  # noqa: BLE001 -- a harness that will not say what it runs
            # Whatever it failed with is said of it, and the others are still asked.
            return {"cli": cli, "account": name, "why": str(why)}
        return None

    if not pairs:
        return []
    with ThreadPoolExecutor(1 if stale else _AT_ONCE, "humanize-scan") as pool:
        return [one for one in pool.map(asks, pairs) if one is not None]


def scans() -> None:
    """Scans in the background, as a daemon starts: what was never asked, or long ago.

    On a thread of its own, one harness at a time, so that nothing the daemon serves waits
    on it; `HUMANIZE_SCAN` set to `off`, `0`, `no`, `none` or nothing turns it off.
    """
    said = os.environ.get(SCAN)
    if said is not None and said.strip().lower() in {"", "off", "0", "no", "none"}:
        return
    threading.Thread(
        target=lambda: scan(_hmz(), stale=True), daemon=True, name="humanize-scan"
    ).start()


def write(hmz: Any, said: Mapping[str, Any]) -> dict[str, Any]:
    """Writes one nous, whole.

    Args:
      hmz: Humanize.
      said: `name`, and `tries`, `policy`, `timeout`, `graph` and `then` as `nous.list`
        answers them; a graph may also be a nous or a list of them tried in turn.

    Returns:
      What :func:`listed` answers afterwards.

    Raises:
      RpcError: 400 for a value `NousBook` refuses.
    """
    book = hmz.nous
    name, tries = said.get("name"), said.get("tries", 0)
    policy, timeout = said.get("policy") or book.default, said.get("timeout", 0)
    if not isinstance(name, str) or not book.reads(name):
        raise _refused(
            f"{name} is not a nous: say it as HARNESS[@ACCOUNT]/MODEL[:EFFORT] or a name."
        )
    if not isinstance(tries, int) or isinstance(tries, bool) or tries < 0:
        raise _refused("Say tries as how many more goes, 0 or more.")
    if not isinstance(policy, str) or book.named(policy) is None:
        raise _refused(f"{policy} is no way of waiting.")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout < 0
    ):
        raise _refused("Say timeout in seconds, or 0 for no limit.")
    try:
        book.write(
            name,
            tries=tries,
            policy=policy,
            timeout=float(timeout),
            graph=said.get("graph"),
            then=said.get("then"),
        )
    except (TypeError, ValueError) as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def rename(hmz: Any, said: str, name: str) -> dict[str, Any]:
    """Gives a virtual nous another name.

    Raises:
      RpcError: 400 for a name that cannot be given.
    """
    try:
        hmz.nous.renamed(said, name)
    except ValueError as why:
        raise _refused(str(why)) from why
    return listed(hmz)


def clear(hmz: Any, said: str) -> dict[str, Any]:
    """Removes one nous.

    Raises:
      RpcError: 404 for a nous nothing is written against; 400 for one still named.
    """
    try:
        gone = hmz.nous.clear(said)
    except ValueError as why:
        raise _refused(str(why)) from why
    if not gone:
        raise RpcError(Code.NOT_FOUND, f"Nothing is written down against {said}.")
    return listed(hmz)


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _hmz() -> Any:
    from hmz.runtime import Hmz

    return Hmz()


#: Every method of `nous.*`, by name.
METHODS: Mapping[str, Handler] = {
    "nous.list": lambda _: listed(_hmz()),
    "nous.scan": lambda _: scan(_hmz()),
    "nous.set": lambda call: write(_hmz(), call.params),
    "nous.rename": lambda call: rename(_hmz(), call.params["name"], call.params["to"]),
    "nous.clear": lambda call: clear(_hmz(), call.params["name"]),
}
