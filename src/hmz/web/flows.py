"""The flows there are to run here, what each declares, and the agents that can fill them.

The daemon's `flows.*` (:mod:`hmz.daemon.api.flows`), served over HTTP until the page calls
them: the flows on offer in a workspace, one flow as a run of it is set up, the backends
installed here, and what a workspace is set up to run a flow with.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .routing import Refusal, answered, routes

if TYPE_CHECKING:
    from .routing import Asked

__all__ = ["ROUTES", "declared", "remembered"]


def declared(hmz: Any, name: str) -> dict[str, Any]:
    """One flow, as a page sets a run of it up, as `flows.get` answers.

    Raises:
      Refusal: If there is no such flow, or it will not load.
    """
    from hmz.daemon.api import flows

    with answered():
        return flows.declared(hmz, name)


def remembered(hmz: Any, said: dict[str, Any]) -> None:
    """Writes down what a workspace is set up to run a flow with, as `flows.setup` does.

    Raises:
      Refusal: If the flow is not on offer there, an agent is not one, or it is not set up
        enough to run.
    """
    from hmz.daemon.api import flows

    with answered():
        flows.remembered(hmz, said)


def _setup(asked: Asked) -> dict[str, Any]:
    said = asked.body.get("workspace", "")
    hmz = asked.site.places.of(said if isinstance(said, str) else "").hmz
    remembered(hmz, asked.body)
    return declared(hmz, asked.text("flow"))


def _hmz(asked: Asked) -> Any:
    """Humanize, for the workspace a request names, or where the interface started."""
    return asked.site.places.of(asked.query.get("workspace", "")).hmz


def _flows(asked: Asked) -> dict[str, Any]:
    from hmz.daemon.api import flows

    return flows.listed(_hmz(asked))


def _flow(asked: Asked) -> dict[str, Any]:
    from hmz.daemon.api import flows

    hmz = _hmz(asked)
    name = asked.query.get("name", "")
    if not name:
        raise Refusal("Say which flow, as name.")
    with answered():
        return flows.offered(hmz, name)


def _backends(asked: Asked) -> dict[str, Any]:
    from hmz.daemon.api import flows

    return flows.backends(_hmz(asked))


#: What a page reads of the flows here and the agents that can run them.
ROUTES = routes(
    ("GET", "/api/flows", _flows),
    ("GET", "/api/flow", _flow),
    ("GET", "/api/backends", _backends),
    ("POST", "/api/flows/setup", _setup),
)
