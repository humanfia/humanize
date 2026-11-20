"""`hosts.env.*`: reading, writing, searching and running commands in the envs of an epic going.

Each is carried out by the host the call names, on the env it names, as the epic's flow would
carry it out through that env (Section 4.23 of daemon.md): asked down the host's link, attaching
nobody and starting no host, and refused with the code the host refused it with.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hmz.daemon.methods import slot, workspace
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.rpc import Call, Handler

__all__ = ["METHODS"]


def _carried(method: str) -> Handler:
    """The handler of one method of Section 4.23, which the host the call names carries out."""

    def carries(call: Call) -> dict[str, Any]:
        from hmz.daemon import routing
        from hmz.runtime.doing.envs import NO_FLOW

        named = workspace(call.params["workspace"], made=True)
        slotted = slot(call.params.get("slot"))
        router = routing.serving
        hosted = None if router is None else router.hosts.get(named, slotted)
        if hosted is None:
            raise RpcError(Code.CONFLICT, NO_FLOW)
        said = {
            k: v
            for k, v in call.params.items()
            if k not in ("workspace", "slot", "idem")
        }
        answer = hosted.env({"do": method, **said})
        if not answer.get("ok"):
            raise RpcError(
                int(answer.get("code") or Code.CONFLICT),
                str(answer.get("why") or "refused"),
            )
        return {k: v for k, v in answer.items() if k != "ok"}

    return carries


METHODS: Mapping[str, Handler] = {
    f"hosts.env.{name}": _carried(f"hosts.env.{name}")
    for name in ("list", "read", "write", "exec", "grep")
}
