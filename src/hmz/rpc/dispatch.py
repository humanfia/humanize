"""The methods one end serves, each refused unless the OpenRPC document lists it.

A :class:`Dispatcher` is the `serve` of a :class:`hmz.rpc.Peer`, and may be that of many: it
holds a handler for each method by name, answers `rpc.discover` with the document itself
(Section 6.11.4 of wire.md), refuses a method it holds no handler for with -32601, and refuses
parameters the document does not give the method with -32602 in the words of Section 6.6.3 --
a name it does not take, a required one absent, or one of another JSON type. Where the document
lists `session.hello`, a session's first call must be that and no later one may be (Section
6.5.2).

Those three refusals of parameters are checked here, by hand, against each parameter's own
`type` in the document; what a parameter's schema says beneath its type -- a pattern, a range,
the fields of an object -- is the method's to refuse. Checking whole schemas at a call would
need a JSON Schema validator at run time, which this package does not carry: `jsonschema` is a
development dependency, which holds the document itself to the OpenRPC meta-schema in the suite,
and pydantic validates models declared in Python rather than schemas read from a document.

Each call is carried out on a thread of its own, so that one call of a session waits on no
other (Section 6.4.4) -- but for the calls of one session that name one `sub`, which are carried
out one after another in the order sent, `epic.aside` apart (Section 6.4.5). A notification is
handed to its handler on the peer's reading thread, in the order notifications arrive.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING, Any, cast
from weakref import WeakSet

from hmz.rpc.document import document
from hmz.rpc.errors import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.rpc.peer import Call, Peer

__all__ = ["Dispatcher", "Handler"]

_log = logging.getLogger(__name__)

#: What carries out a call: given it, it gives back the result, or raises :class:`RpcError` to
#: answer with that error. A notification's handler gives back nothing.
type Handler = Callable[[Call], Any]

#: The JSON types a schema's `type` names, and whether a value read off JSON is of each. An
#: integer is one JSON wrote without a fraction, which is what a handler can count with.
_TYPES: dict[str, Callable[[object], bool]] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}

#: The first call of a session.
_HELLO = "session.hello"

#: The one call naming a subscription that waits on none of the others (Section 6.4.5).
_APART = "epic.aside"


class Dispatcher:
    """A handler for each method one end serves, and the `serve` that calls them.

    Args:
      openrpc: The OpenRPC document the methods are listed in; the protocol's own,
        :func:`hmz.rpc.document`, where none is given.
    """

    def __init__(self, openrpc: dict[str, Any] | None = None) -> None:
        self._document = document() if openrpc is None else openrpc
        listed = cast("list[dict[str, Any]]", self._document["methods"])
        told = cast("list[dict[str, Any]]", self._document.get("x-notifications", []))
        #: Each method a call may name, and its parameters: each one's name, whether it is
        #: required, and the JSON types it may be.
        self._methods = {
            m["name"]: [
                (p["name"], bool(p.get("required")), self._types(p["schema"]))
                for p in cast("list[dict[str, Any]]", m["params"])
            ]
            for m in listed
            if not m.get("x-notification")
        }
        #: Each notification either end may send.
        self._told = {m["name"] for m in listed if m.get("x-notification")} | {
            n["name"] for n in told
        }
        self._handlers: dict[str, Handler] = {}
        if "rpc.discover" in self._methods:
            self._handlers["rpc.discover"] = lambda _: self._document
        self._lock = threading.Lock()
        #: The sessions that have said hello, forgotten with them.
        self._greeted: WeakSet[Peer] = WeakSet()
        #: The calls waiting behind one being carried out, by session and `sub`.
        self._lanes: dict[tuple[int, str], deque[tuple[Handler, Call]]] = {}

    def register(self, name: str, handler: Handler) -> None:
        """Serves a method or a notification with a handler, in place of any it had.

        Args:
          name: The method or notification, as the document lists it.
          handler: What carries it out.

        Raises:
          ValueError: If the document lists no such method or notification, which may not be
            served (Section 6.11.1).
        """
        if name not in self._methods and name not in self._told:
            raise ValueError(f"{name} is not in the OpenRPC document")
        self._handlers[name] = handler

    def __call__(self, call: Call) -> None:
        """Carries out a call or a notification, as a :class:`hmz.rpc.Peer` hands it over."""
        handler = self._handlers.get(call.method)
        if call.id is None:
            if handler is not None and call.method in self._told:
                try:
                    handler(call)
                except Exception:  # noqa: BLE001 -- nobody is answered, so the log says it
                    _log.exception("handling %s failed", call.method)
            return
        refusal = self._refusal(call)
        if refusal is not None:
            call.fail(refusal)
        elif handler is not None:  # which `_refusal` saw to
            self._start(handler, call)

    def _refusal(self, call: Call) -> RpcError | None:
        """What a call is refused with before it is carried out, or `None` where it is not."""
        method = call.method
        if _HELLO in self._methods:
            with self._lock:
                greeted = call.peer in self._greeted
            if not greeted and method != _HELLO:
                return RpcError(
                    Code.INVALID_REQUEST, "A client says session.hello first."
                )
            if greeted and method == _HELLO:
                return RpcError(
                    Code.INVALID_REQUEST, "This session has already said hello."
                )
        if method not in self._methods or method not in self._handlers:
            return RpcError(Code.METHOD_NOT_FOUND, f"There is no method {method}.")
        declared = self._methods[method]
        extra = [name for name in call.params if name not in {d[0] for d in declared}]
        if extra:
            return _invalid(f"{method} takes no {', '.join(extra)}.")
        for name, required, types in declared:
            if name not in call.params:
                if required:
                    return _invalid(f"{method} needs {name}.")
            elif types and not any(_TYPES[t](call.params[name]) for t in types):
                return _invalid(f"{method} takes {name} as {' or '.join(types)}.")
        if method == _HELLO:
            with self._lock:
                self._greeted.add(call.peer)
        return None

    def _start(self, handler: Handler, call: Call) -> None:
        """Carries a call out on a thread, behind the calls of its session naming its `sub`."""
        sub = call.params.get("sub")
        if not isinstance(sub, str) or call.method == _APART:
            threading.Thread(
                target=_carry_out, args=(handler, call), name=call.method, daemon=True
            ).start()
            return
        lane = (id(call.peer), sub)
        with self._lock:
            waiting = self._lanes.get(lane)
            if waiting is not None:
                waiting.append((handler, call))
                return
            self._lanes[lane] = deque()
        threading.Thread(
            target=self._drain, args=(lane, handler, call), name=sub, daemon=True
        ).start()

    def _drain(self, lane: tuple[int, str], handler: Handler, call: Call) -> None:
        """Carries out a call and then each queued behind it, until none is."""
        while True:
            _carry_out(handler, call)
            with self._lock:
                waiting = self._lanes[lane]
                if not waiting:
                    del self._lanes[lane]
                    return
                handler, call = waiting.popleft()

    def _types(self, schema: dict[str, Any]) -> list[str]:
        """The JSON types a schema names, through a `$ref` to the document's components."""
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            components = cast("dict[str, Any]", self._document["components"])
            schema = components["schemas"][ref.rsplit("/", 1)[1]]
        named = schema.get("type")
        if isinstance(named, str):
            return [named]
        return [t for t in cast("list[str]", named or []) if t in _TYPES]


def _invalid(message: str) -> RpcError:
    return RpcError(Code.INVALID_PARAMS, message)


def _carry_out(handler: Handler, call: Call) -> None:
    """Carries out one call and answers it, with -32603 for a failure nobody anticipated.

    The failure itself, with its traceback, goes to the log rather than into the answer
    (Section 6.6.5).
    """
    try:
        call.answer(handler(call))
    except RpcError as e:
        call.fail(e)
    except Exception as e:  # noqa: BLE001 -- answered -32603, as Section 6.6.2 says
        _log.exception("%s failed", call.method)
        call.fail(RpcError.unanticipated(e))
