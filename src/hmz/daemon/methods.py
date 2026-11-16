"""The methods this machine's daemon serves itself: sessions, pairing, devices, hosts and epics.

Each is a handler of `hmz.rpc`, given the call and answering its result or raising
:class:`hmz.rpc.RpcError` (Section 4 of daemon.md). The other families -- settings, epics
written down, flows and the rest -- are each a module of :mod:`hmz.daemon.api`, which names its
own in `METHODS`; every one is found here and served beside these. A method the OpenRPC
document lists that nothing serves is answered -32601, as `hmz.rpc` answers it.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import pkgutil
import socket
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.daemon.hosts import Hosted, Subscription
    from hmz.daemon.routing import Router
    from hmz.rpc import Call, Handler

__all__ = ["EPIC", "families", "methods"]

_log = logging.getLogger(__name__)

#: Every call to an epic (Section 4.8 of daemon.md), by what follows `epic.`.
EPIC = (
    "start",
    "say",
    "answer",
    "stop",
    "force",
    "afk",
    "claim",
    "release",
    "board",
    "aside",
    "unaside",
    "status",
    "detach",
    "quit",
)


def _refused(code: int, message: str) -> Exception:
    from hmz.rpc import RpcError

    return RpcError(code, message)


def workspace(said: object) -> str:
    """A `workspace` parameter, as the daemon knows a workspace (Section 4.5.2).

    Raises:
      RpcError: 400 for a path that is not absolute, 404 for one naming no directory.
    """
    path = Path(str(said)).expanduser()
    if not path.is_absolute():
        raise _refused(400, f"Say the workspace as a whole path, not {said}.")
    if not path.is_dir():
        raise _refused(404, f"There is no directory {path}.")
    return where.workspace(path)


def slot(said: object, *, new: bool = False) -> str:
    """A `slot` parameter (Section 4.5.3): `chat:` or `exec:` alone too where `new`.

    Raises:
      RpcError: 400 for one that is not a slot.
    """
    if said is None or said == "":
        return ""
    if new and said in ("chat:", "exec:"):
        return cast("str", said)
    try:
        return where.slot(said)
    except ValueError:
        raise _refused(400, f"{said} is not a slot.") from None


def _none_held(workspace: str, slot: str) -> Exception:
    return _refused(
        404, f"no runs are held in {workspace}" + (f" for {slot}" if slot else "")
    )


class _Methods:
    """The handlers of the daemon's own methods, over the daemon they serve."""

    def __init__(self, router: Router) -> None:
        self._router = router

    # -- sessions and pairing

    def hello(self, call: Call) -> dict[str, Any]:
        from hmz.rpc import PROTOCOL, admit

        router = self._router
        session = router.session(call)
        admit(str(call.params["protocol"]))
        client = cast("dict[str, Any]", call.params["client"])
        name, kind = client.get("name"), client.get("kind")
        if not isinstance(name, str) or not isinstance(kind, str):
            raise _refused(-32602, "session.hello takes client as {name, kind}.")
        session.name, session.kind = name, kind
        return {
            "daemon_id": router.daemon_id,
            "version": _version(),
            "protocol": PROTOCOL,
            "capabilities": router.capabilities(),
            "machine": socket.gethostname().split(".")[0],
            "wsl": os.environ.get("WSL_DISTRO_NAME") or None,
            "newer": _newer(),
            "paired": session.paired,
            "device": session.device,
        }

    def pair_create(self, call: Call) -> dict[str, Any]:
        router = self._router
        routes = call.params.get("routes")
        given = (
            [str(one) for one in cast("list[object]", routes)]
            if isinstance(routes, list)
            else router.routes()
        )
        if not given:
            raise _refused(409, "There is no route to pair over: give one, or listen.")
        try:
            code = router.codes.make(
                router.daemon_id,
                given,
                call.params.get("seconds", 600),
            )
        except ValueError as why:
            raise _refused(400, str(why)) from None
        return {"code": code.text(), "expires": code.expires}

    def pair_claim(self, call: Call) -> dict[str, Any]:
        from hmz.trust import pairing

        router = self._router
        session = router.session(call)
        if session.paired:
            raise _refused(409, "This device is already paired.")
        try:
            device = pairing.claim(
                router.codes,
                router.devices,
                str(call.params["token"]),
                str(call.params["name"]),
                session.fingerprint,
            )
        except pairing.InvalidCodeError as why:
            raise _refused(403, str(why)) from None
        except ValueError as why:
            raise _refused(400, str(why)) from None
        except OSError as why:
            raise _refused(
                503, f"The device could not be written down: {why}"
            ) from None
        session.device = device
        return {"daemon_id": router.daemon_id, "device": device}

    def devices_list(self, call: Call) -> dict[str, Any]:
        del call
        router = self._router
        live = router.live()
        return {
            "devices": [
                {
                    "name": one.name,
                    "fingerprint": one.fingerprint,
                    "added": one.added,
                    "seen": one.seen,
                    "live": live.get(one.fingerprint, 0),
                }
                for one in router.devices.listed()
            ]
        }

    def devices_revoke(self, call: Call) -> dict[str, Any]:
        router = self._router
        name = str(call.params["name"])
        session = router.session(call)
        listed = {one.name: one.fingerprint for one in router.devices.listed()}
        dropped = router.live().get(listed.get(name, ""), 0)
        try:
            with router.revoking(session):
                router.devices.revoke(name)
        except ValueError as why:
            raise _refused(400, str(why)) from None
        except LookupError as why:
            raise _refused(404, str(why.args[0])) from None
        except (OSError, TypeError) as why:
            raise _refused(503, f"The device could not be revoked: {why}") from None
        if session.fingerprint == listed.get(name):
            # Its own session too, once it has been answered.
            call.answer({"dropped": dropped})
            session.out.flush_then_close()
        return {"dropped": dropped}

    # -- hosts

    def hosts_list(self, call: Call) -> dict[str, Any]:
        del call
        return {"held": [one.listed for one in self._router.hosts.listed()]}

    def hosts_running(self, call: Call) -> dict[str, Any]:
        del call
        running: list[dict[str, Any]] = []
        for hosted in self._router.hosts.listed():
            status = hosted.status()
            if status.get("state") not in ("running", "stopping"):
                continue
            pending = cast("list[dict[str, Any]]", status.get("pending") or [])
            running.append(
                {
                    key: status.get(key)
                    for key in ("state", "run", "flow", "epic", "task", "turn")
                    if key in status
                }
                | {
                    "workspace": hosted.workspace,
                    "slot": hosted.slot,
                    "asking": [
                        f"{status.get('run')}:{one['question']}" for one in pending
                    ],
                }
            )
        return {"running": running}

    def hosts_open(self, call: Call) -> dict[str, Any]:
        hosted = self._router.hosts.opened(
            workspace(call.params["workspace"]), slot(call.params.get("slot"), new=True)
        )
        return {**hosted.keys, "slot": hosted.slot}

    def _held(self, call: Call) -> Hosted:
        named = workspace(call.params["workspace"])
        slotted = slot(call.params.get("slot"))
        hosted = self._router.hosts.get(named, slotted)
        if hosted is None:
            raise _none_held(named, slotted)
        return hosted

    def hosts_status(self, call: Call) -> dict[str, Any]:
        return self._held(call).status()

    def hosts_detach(self, call: Call) -> dict[str, Any]:
        return {"let_go": self._held(call).detach_all()}

    def hosts_stop(self, call: Call) -> dict[str, Any]:
        hosted = self._held(call)
        call.answer({})
        hosted.stop()
        return {}

    # -- epics

    def attach(self, call: Call) -> dict[str, Any]:
        from hmz.daemon.hosts import Subscription

        router = self._router
        session = router.session(call)
        params = call.params
        if params.get("scratch"):
            named = where.workspace(tempfile.mkdtemp(prefix="hmz-"))
        elif "workspace" in params:
            named = workspace(params["workspace"])
        else:
            raise _refused(-32602, "epic.attach needs workspace.")
        hosted = router.hosts.opened(named, slot(params.get("slot"), new=True))
        sub = Subscription(
            session, session.named(), hosted, figures=params.get("figures") is True
        )
        with session.lock:
            session.subs[sub.sub] = sub
        since = params.get("since")
        try:
            sub.client = hosted.attach(
                sub,
                replay=params.get("replay", True) is not False,
                since=cast("dict[str, Any]", since)
                if isinstance(since, dict)
                else None,
            )
        except BaseException:
            with session.lock:
                session.subs.pop(sub.sub, None)
            raise
        if session.closed:
            sub.dropped()
            raise _refused(409, "the frontend went while it was saying hello")
        result = {
            "sub": sub.sub,
            "client": sub.client,
            "workspace": hosted.workspace,
            "slot": hosted.slot,
        }
        call.answer(result)
        sub.opened()
        return result

    def epic(self, do: str) -> Handler:
        """The handler of one call to an epic, which the host attached carries out."""

        def asks(call: Call) -> dict[str, Any]:
            sub = self.subscription(call)
            said = {k: v for k, v in call.params.items() if k not in ("sub", "idem")}
            answer = sub.hosted.ask(sub.client, {"do": do, **said})
            if not answer.get("ok"):
                raise _refused(409, str(answer.get("why") or "refused"))
            result = {k: v for k, v in answer.items() if k != "ok"}
            if do == "start":
                result |= {"slot": sub.hosted.slot, "workspace": sub.hosted.workspace}
            return result

        return asks

    def subscription(self, call: Call) -> Subscription:
        """The epic subscription a call names on its session.

        Raises:
          RpcError: 410 where none of that name is open.
        """
        named = str(call.params.get("sub"))
        session = self._router.session(call)
        with session.lock:
            sub = session.subs.get(named)
        if sub is None or sub.gone:
            raise _refused(410, f"There is no subscription {named}.")
        return sub

    def methods(self) -> dict[str, Handler]:
        """Every method served here, by name."""
        from hmz.daemon.asides import Asides

        asides = Asides(self._router)
        return {
            "session.hello": self.hello,
            "pair.create": self.pair_create,
            "pair.claim": self.pair_claim,
            "devices.list": self.devices_list,
            "devices.revoke": self.devices_revoke,
            "hosts.list": self.hosts_list,
            "hosts.running": self.hosts_running,
            "hosts.open": self.hosts_open,
            "hosts.status": self.hosts_status,
            "hosts.detach": self.hosts_detach,
            "hosts.stop": self.hosts_stop,
            "epic.attach": self.attach,
            **{f"epic.{do}": self.epic(do) for do in EPIC},
            "btw.list": asides.listed,
            "btw.ask": asides.ask,
            "btw.leave": asides.leave,
        }


def methods(router: Router) -> dict[str, Handler]:
    """The daemon's own methods, over the daemon that serves them."""
    return _Methods(router).methods()


def families() -> dict[str, Handler]:
    """The methods every module of :mod:`hmz.daemon.api` names in `METHODS`.

    A module that cannot be imported is written to the daemon's log and served without. The
    package is found by its name: the families are a layer above this one, which names them
    only through what they register.
    """
    api = importlib.import_module("hmz.daemon.api")

    found: dict[str, Handler] = {}
    for one in pkgutil.iter_modules(api.__path__, f"{api.__name__}."):
        try:
            module = importlib.import_module(one.name)
        except Exception:  # noqa: BLE001 -- one family that fails keeps no other from serving
            _log.exception("%s could not be imported", one.name)
            continue
        named = cast("Mapping[str, Handler]", getattr(module, "METHODS", {}))
        found.update(named)
    return found


def _version() -> str:
    """This hmz's version."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("hmz")
    except PackageNotFoundError:
        return "0.0.0"


def _newer() -> str:
    """A newer release of hmz, as the daemon last learned it, or ""."""
    with contextlib.suppress(Exception):
        from hmz.coganchor import releases

        return releases.newer() or ""
    return ""
