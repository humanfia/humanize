"""The errors a call is answered with (Section 6.6 of wire.md), and a session that has closed.

An error carries a `code` of the table of Section 6.6.2, a `message` of one sentence in the
words the protocol gives, and, where a method states further fields, `data`, an object holding
them. :class:`RpcError` is that error both ways: raised by a handler to answer a call with it,
and raised to a caller whose call was answered with it.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

__all__ = ["Closed", "Code", "RpcError"]


class Code(IntEnum):
    """Every code of Section 6.6.2, by what it means."""

    #: The frame does not hold JSON: `Send JSON.`
    PARSE_ERROR = -32700
    #: Not a JSON-RPC 2.0 request, a batch, or a call before `session.hello`.
    INVALID_REQUEST = -32600
    #: No such method: `There is no method <method>.`
    METHOD_NOT_FOUND = -32601
    #: Parameters not as the OpenRPC document states (Section 6.6.3).
    INVALID_PARAMS = -32602
    #: A failure the method does not anticipate: `Something went wrong here: <why>`
    INTERNAL_ERROR = -32603
    #: The call was given up: `The call was cancelled.`
    CANCELLED = -32800
    #: A value the method refuses.
    REFUSED = 400
    #: The session is unpaired.
    NOT_PAIRED = 401
    #: Refused to this device, a pairing code not valid included.
    FORBIDDEN = 403
    #: What the call names does not exist.
    NOT_FOUND = 404
    #: Refused in the state things are in, a host's refusal included.
    CONFLICT = 409
    #: No such subscription: `There is no subscription <sub>.`
    UNKNOWN_SUBSCRIPTION = 410
    #: More than a call or an answer here may carry.
    TOO_LARGE = 413
    #: Another protocol version (Section 6.5.5).
    PROTOCOL_MISMATCH = 426
    #: A program or service the daemon asked did not answer.
    UPSTREAM = 502
    #: What the call needs cannot be reached now.
    UNAVAILABLE = 503


class RpcError(Exception):
    """A call answered with an error, or to be answered with one.

    Attributes:
      code: Its code, one of :class:`Code` from a peer that keeps to the protocol.
      message: Why, in one sentence.
      data: The further fields its method states, or `None` where it states none.
    """

    def __init__(
        self, code: int, message: str, data: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    @classmethod
    def unanticipated(cls, failure: BaseException) -> RpcError:
        """-32603 for a failure the method does not anticipate, naming it but not its traceback."""
        why = str(failure) or type(failure).__name__
        return cls(Code.INTERNAL_ERROR, f"Something went wrong here: {why}")

    def to_json(self) -> dict[str, Any]:
        """The error object a response carries."""
        said: dict[str, Any] = {"code": int(self.code), "message": self.message}
        if self.data is not None:
            said["data"] = self.data
        return said


class Closed(ConnectionError):  # noqa: N818 -- what the session is, not what went wrong
    """The session closed, so a call on it will never be answered, and none can be made."""
