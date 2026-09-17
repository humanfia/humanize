"""An OpenAI-compatible endpoint on the loopback, for the tests that need a model to answer.

Every account humanize drives is one of two things: a CLI signed into a vendor's own account,
or that same CLI pointed at somebody's endpoint. The suite has a deep bench of stand-ins for
the first half -- a fake CLI first on PATH, printing what the real one prints -- and had
nothing at all for the second. So a test that wanted a catalogue, or a turn, had to reach a
real gateway and spend real tokens, which is why the tests that take one are gated behind a
flag and do not run in CI at all.

This is the missing half. It serves the two requests everything here makes of an endpoint:
`GET /v1/models`, which is where an account's catalogue comes from, and
`POST /v1/chat/completions`, which is where a turn goes. Both answer out of what the test
said -- the ids it serves, the line the model replies -- and both write down what they were
asked, so that a test can be about the request rather than about the answer.

The catalogue half is written against :func:`hmz.coganchor.models._listing` and nothing else:
the paths it asks for, the headers it sends, and the shape it reads back. A mock that answers
a request humanize never makes, or reads a body humanize never sends, is a mock that proves
nothing -- so the two are kept in step here, where breaking one breaks a test.

The catalogue half serves every backend humanize asks an endpoint, all eight of them, because
that request is one request whoever is behind the URL. The turn half speaks one protocol:
chat completions, which is what a CLI pointed at an OpenAI-compatible gateway sends, and what
seven of the eight can be configured to send. A backend taking its turns in a protocol of its
own -- Claude Code at `/v1/messages`, agy at Gemini's `:streamGenerateContent` -- is answered
for its catalogue and 404s on its turn, which is a gap to fill here rather than a failure to
read as humanize's: `TALKS` and `do_POST` are where a second protocol would go.

Nothing waits on a clock and nothing sleeps: the service binds port 0 on the loopback, the
bodies are stamped with a moment written down rather than read off the clock, and every test
gets a service of its own. Which is what lets the suite run across as many workers as a
machine has cores without any of this being the thing that flakes.

The `llm` fixture that hands one out lives in `tests/conftest.py`, since a fixture is found
by pytest rather than imported: a test module that imported this one would shadow the name
with the parameter it names it by, which is a redefinition rather than a use.
"""

from __future__ import annotations

import contextlib
import json
import socketserver
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor import backends, providers

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence

__all__ = [
    "KEY",
    "MADE",
    "MOCKED",
    "POINTED",
    "SAYS",
    "SERVES",
    "Serving",
    "Taken",
    "answered",
    "catalogue",
    "framed",
    "pointing",
    "serving",
]

#: Every backend humanize asks an endpoint rather than its CLI, by name. Read off the profiles
#: rather than written out here, so that a backend given an endpoint tomorrow is covered on the
#: day it is given one -- which is the one thing this service is for, that each of them can now
#: be asked in CI. Beside the service rather than in either half of its tests: both
#: `tests/unit/test_llm.py` and `tests/integration/test_llm.py` parametrize over it, and a list
#: worked out twice is two answers to a question with one. A tuple rather than a list, for the
#: same reason it is shared: two modules holding one object is one of them able to append to it.
POINTED = tuple(profile.name for profile in backends.PROFILES if profile.endpoint)

#: The ids the service lists where a test has not said otherwise. Two rather than one,
#: because a reader that drops the last entry or keeps only the first reads a catalogue of
#: one correctly.
SERVES = ("mock/first-model", "mock/second-model")

#: What the model replies where a test has not said otherwise.
SAYS = "the endpoint answered"

#: The credential an account made for this service carries, and the one the service demands.
#: Checked rather than ignored: the point of asking an endpoint what it serves under the
#: account's own key is that the key goes with the request, and a service that took any
#: request at all would pass a humanize that had stopped sending one.
KEY = "mock-endpoint-key"

#: What an account made for the service is called, where a test does not name it.
MOCKED = "mocked"

#: The moment every answer is stamped with. Written down rather than read off the clock: a
#: body that is never twice the same is a body no test can assert whole, and a turn's
#: timestamps are not what any of this is about.
MADE = 1758067200

#: The id every answer carries, for the reason `MADE` is written down.
ROUND = "chatcmpl-humanize"

#: What an answer names where the request named no model and the caller said nothing about
#: which of the served ids to stand in -- a request that named none is one nothing is being
#: asserted about the model of.
MODEL = SERVES[0]

#: Where the catalogue is served. Both spellings, because both are asked for: `_listing`
#: appends `/v1/models` to a base that names no version and `/models` to one that does --
#: `http://host` and `http://host/v1` being two spellings of one gateway -- and a CLI pointed
#: at the same base asks it for `/models` itself, which is what grok's does.
LISTS = ("/v1/models", "/models")

#: Where a turn goes, in both spellings for the same reason: an OpenAI-compatible client
#: appends `/chat/completions` to whatever base URL it was handed.
TALKS = ("/v1/chat/completions", "/chat/completions")


@dataclass(frozen=True, slots=True)
class Taken:
    """One request the service took, as it arrived.

    Attributes:
      method: The verb.
      path: What was asked for, query and all.
      headers: What it carried, by lower-cased name -- HTTP header names are
        case-insensitive, and a test that had to guess which case a client chose would be a
        test about the client's spelling rather than about what it sent.
      body: What it carried, read as JSON, and nothing at all for a request with no body or
        one that is not JSON.
    """

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict[str, str])
    body: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def secret(self) -> str:
        """The credential this request carried, out of whichever header it was sent as.

        All of them, because humanize sends more than one and the CLIs send another again:
        `Authorization` is what an OpenAI-shaped endpoint reads, `x-api-key` what an
        Anthropic-shaped one does and `x-goog-api-key` what Gemini's client sends, and a
        gateway is asked what it serves without knowing which of them it prefers. Each is
        tried in turn rather than only the first that is present, so that a client sending
        its key in one header and something else entirely in another is read by the one that
        carries the key.
        """
        said = self.headers.get("authorization", "")
        bearer = said.split(" ", 1)[1] if said.lower().startswith("bearer ") else ""
        return (
            bearer
            or self.headers.get("x-api-key", "")
            or self.headers.get("x-goog-api-key", "")
            # And whatever `Authorization` held under some other scheme, last: a test about a
            # request that was refused is a test about what that request actually carried.
            or said
        )

    @property
    def prompt(self) -> str:
        """What the turn asked, as the last thing the user said in it.

        The last rather than the first: a client sends the whole conversation every time, and
        what this turn is about is the end of it. Empty for a request that is not a turn.
        """
        said: list[dict[str, Any]] = [
            cast("dict[str, Any]", one)
            for one in cast("list[Any]", self.body.get("messages") or [])
            if isinstance(one, dict)
            and cast("dict[str, Any]", one).get("role") == "user"
        ]
        return _spoken(said[-1].get("content")) if said else ""


def _spoken(content: object) -> str:
    """One message's text, whichever of the two shapes a client wrote it in.

    A string, which is what a plain client sends, or a list of parts, which is what one that
    can also send an image sends even where it is only sending words.

    Args:
      content: What the message held.

    Returns:
      The words in it, the parts joined by nothing.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        str(cast("dict[str, Any]", one).get("text") or "")
        for one in cast("list[Any]", content)
        if isinstance(one, dict)
    )


def _said(body: Mapping[str, Any]) -> str:
    """Every word one request carried, whoever in the conversation said it.

    Args:
      body: The request body.

    Returns:
      The text of each message, in order, run together.
    """
    return " ".join(
        _spoken(cast("dict[str, Any]", one).get("content"))
        for one in cast("list[Any]", body.get("messages") or [])
        if isinstance(one, dict)
    )


def catalogue(serves: Sequence[str]) -> dict[str, Any]:
    """The body `/v1/models` answers with.

    The shape `_listing` reads and no more of it: a list under `data`, each entry an object
    with an `id`. What else a real endpoint puts there is read by nothing here, and a mock
    that invented fields would be documenting a contract nobody has.

    Args:
      serves: The ids, in the order the endpoint offers them -- which is the order they come
        back in, a catalogue being the endpoint's own list rather than a sorted one.

    Returns:
      The body, ready to be written out as JSON.
    """
    return {
        "object": "list",
        "data": [
            {"id": one, "object": "model", "owned_by": "humanize"} for one in serves
        ],
    }


def answered(said: Mapping[str, Any], says: str, model: str = MODEL) -> dict[str, Any]:
    """One chat completion, as an OpenAI-compatible endpoint answers a prompt.

    Args:
      said: The request body, which names the model the answer is stamped with.
      says: What the model replies. The test's to say: an endpoint that decided for itself
        what came back would be a second thing to reason about in every test that used it.
      model: What to stamp it with where the request named none, which is one of the ids this
        endpoint serves rather than one it does not.

    Returns:
      The body, whole. The same body twice for the same pair, which is what lets a test
      assert on all of it rather than on the one field it hopes is stable.
    """
    # Every word of the conversation rather than the words of this turn: a client sends the
    # whole of it every time, and what it is billed for is the whole of what it sent. A count
    # taken off the last message alone would make a long conversation cost what a first
    # question costs, which is the one thing a test about a bill must not be told.
    asking = len(_said(said).split())
    replying = len(says.split())
    return {
        "id": ROUND,
        "object": "chat.completion",
        "created": MADE,
        "model": str(said.get("model") or model),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": says},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": asking,
            "completion_tokens": replying,
            "total_tokens": asking + replying,
        },
    }


def framed(said: Mapping[str, Any], says: str, model: str = MODEL) -> list[str]:
    """The same answer as a stream, one `data:` frame per element.

    Streaming as well as whole because every one of these CLIs streams: a turn is read back
    as it happens, and an endpoint that could only answer in one piece is an endpoint none of
    the drivers could be pointed at.

    Args:
      said: The request body.
      says: What the model replies.
      model: What to stamp the frames with where the request named no model.

    Returns:
      The frames, in order, each already terminated the way a server-sent event is -- the
      role, the words, the reason it stopped, and `[DONE]`, which is what an
      OpenAI-compatible client reads as the end rather than as another chunk.
    """
    whole = answered(said, says, model)
    under = {
        "id": ROUND,
        "object": "chat.completion.chunk",
        "created": MADE,
        "model": whole["model"],
    }
    # What the turn cost, on the last frame and only for a client that asked to be told: a
    # streamed answer carries none unless the request set `stream_options.include_usage`, so
    # an endpoint that sent it regardless would pass a driver that had stopped asking -- and
    # that driver reports no tokens at all against a real gateway.
    counted = cast("dict[str, Any]", said.get("stream_options") or {})
    stopped: dict[str, Any] = {
        **under,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    if counted.get("include_usage"):
        stopped["usage"] = whole["usage"]
    parts: list[dict[str, Any]] = [
        {**under, "choices": [{"index": 0, "delta": {"role": "assistant"}}]},
        {**under, "choices": [{"index": 0, "delta": {"content": says}}]},
        stopped,
    ]
    return [f"data: {json.dumps(one)}\n\n" for one in parts] + ["data: [DONE]\n\n"]


def pointing(
    cli: str, base: str, key: str = KEY, also: Mapping[str, str] | None = None
) -> tuple[backends.Way, dict[str, str]]:
    """The way to make an account by to put a backend on an endpoint, and what to make it with.

    Read off the backend rather than written down here: which variable routes a turn is
    `Profile.endpoint`, which way in asks for it is the way that names it among its questions,
    and which of that way's answers is a credential is the one it marked secret. A table here
    would be a ninth copy of eight facts, wrong the day a backend renames one of them -- and
    wrong quietly, an account pointed at a variable the CLI no longer reads being an account
    that reaches the vendor instead and answers exactly as it should.

    Args:
      cli: The backend, by any name it answers to.
      base: Where to point it, as the endpoint spells itself.
      key: The credential the account carries.
      also: Anything else that way asks for which nobody can answer from here -- the model
        kimi's gateway way is told to run, for one. A question left unanswered is an account
        that is missing something rather than one that is wrong, so these are the caller's.

    Returns:
      The way, whose name the account is made under and whose `args` a turn of it takes, and
      the variables the account is made with.

    Raises:
      ValueError: If the backend is not one there is, is one whose endpoint humanize does not
        ask -- for which there is nothing here to point anywhere -- or offers no way in that
        takes an answer.
    """
    profile = backends.named(cli)
    if profile is None:
        raise ValueError(f"{cli}: no such coding agent")
    if not profile.endpoint:
        raise ValueError(f"{profile.name} names no endpoint a turn of it goes to")
    way = _wayed(profile)
    env = dict(way.sets)
    for one in way.asks:
        if one.env == profile.endpoint:
            env[one.env] = base
        elif one.secret:
            env[one.env] = key
        elif one.fixed:
            env[one.env] = one.fixed
    # And the variable itself, for a backend no way of whose asks for it: agy's endpoint is
    # one somebody exports rather than one it offers to be told, and an account of it that
    # named nowhere would be answered by the CLI after all.
    env[profile.endpoint] = base
    return way, env | dict(also or {})


def _wayed(profile: backends.Profile) -> backends.Way:
    """Which way in an account on an endpoint is made by, out of what that backend offers.

    The way that asks where the endpoint is, which is how every backend that offers a gateway
    offers one. Failing that the first way that asks for a credential at all -- a backend
    whose endpoint is a variable rather than a question still takes a key through one of its
    ways, and `_secret` reads whichever of them is set.

    Args:
      profile: The backend.

    Returns:
      The way.

    Raises:
      ValueError: If it offers no way that takes an answer, and so no way to be given an
        account made here.
    """
    for way in profile.ways:
        if profile.endpoint in {one.env for one in way.asks}:
            return way
    for way in profile.ways:
        if any(one.secret for one in way.asks):
            return way
    raise ValueError(f"{profile.name} offers no way to be given an account")


class Serving:
    """One OpenAI-compatible endpoint on the loopback, answering out of what a test said.

    Held open for the length of one test and taken down however that test ends. What it
    serves and what it replies are attributes rather than arguments, so that a test which
    needs the endpoint to say something else halfway through says so where that happens.

    Attributes:
      serves: The ids `/v1/models` lists, the first of which stands in for a turn that named
        no model.
      says: What `/v1/chat/completions` replies. Chat completions and nothing else: a backend
        that takes its turns in a protocol of its own is answered for its catalogue and 404s
        on its turn, which is the gap the module docstring says where to fill.
      secret: The credential it demands, or "" for one that takes any request. Demanded,
        because humanize asking an endpoint under the account's own key is the whole of why
        the endpoint is asked rather than the CLI, and a service that never checked would
        pass a humanize that had quietly stopped sending one.
      taken: One per request it took, in the order they arrived -- the refused ones included,
        a test about a refusal being a test about what was sent.
    """

    def __init__(
        self,
        serves: Sequence[str] = SERVES,
        says: str = SAYS,
        secret: str = KEY,
    ) -> None:
        self.serves: list[str] = list(serves)
        self.says = says
        self.secret = secret
        self.taken: list[Taken] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            # Kept at 1.1 so that a client which reuses the connection for the second request
            # of a turn is answered on it rather than left waiting on a socket the service
            # has already closed. Every answer below says how long it is, or closes to say.
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                took = outer._records(self)
                if outer._refuses(self, took):
                    return
                if _asked_for(self.path) in LISTS:
                    _sends(self, 200, catalogue(outer.serves))
                    return
                _sends(self, 404, _wrong(f"nothing is served at {self.path}"))

            def do_POST(self) -> None:
                took = outer._records(self)
                if outer._refuses(self, took):
                    return
                if _asked_for(self.path) not in TALKS:
                    _sends(self, 404, _wrong(f"nothing is served at {self.path}"))
                    return
                # Stamped with one of the ids this service is serving now rather than with
                # the one it was made with: a test that changed what it serves and then took
                # a turn would otherwise be answered by a model it no longer offers.
                named = outer.serves[0] if outer.serves else MODEL
                if took.body.get("stream"):
                    _streams(self, framed(took.body, outer.says, named))
                    return
                _sends(self, 200, answered(took.body, outer.says, named))

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                """Nothing: a suite is not somewhere a web server keeps a log."""

        class Running(ThreadingHTTPServer):
            """The same, without the reverse lookup it names itself by.

            On a machine whose resolver has nothing to say about `127.0.0.1` that lookup
            blocks for the resolver's own timeout, which is half a minute.
            """

            daemon_threads = True

            def server_bind(self) -> None:
                socketserver.TCPServer.server_bind(self)
                host, port = self.server_address[:2]
                self.server_name, self.server_port = str(host), int(port)

        self._server = Running(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        """Where it is, as an account spells it: no version on the end and no trailing slash."""
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def account(
        self, cli: str, name: str = MOCKED, also: Mapping[str, str] | None = None
    ) -> providers.Provider:
        """Writes down an account of one backend that is pointed here.

        Args:
          cli: The backend, by any name it answers to.
          name: What to call the account.
          also: Anything else that backend's way in asks for, as `pointing` takes it.

        Returns:
          The account, as it is now written down.

        Raises:
          ValueError: If the backend is not one there is, or names no endpoint.
        """
        way, env = pointing(cli, self.base, self.secret or KEY, also)
        return providers.add(cli, name, way.name, env, way.args)

    def close(self) -> None:
        """Takes it down, and waits for the thread that was serving it to notice."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)

    def _records(self, handler: BaseHTTPRequestHandler) -> Taken:
        """Writes down one request, body and all, and answers with what was written."""
        raw = _read(handler)
        try:
            body: object = json.loads(raw) if raw else None
        except ValueError:
            body = None
        took = Taken(
            method=handler.command,
            path=handler.path,
            headers={name.lower(): value for name, value in handler.headers.items()},
            body=cast("dict[str, Any]", body) if isinstance(body, dict) else {},
        )
        self.taken.append(took)
        return took

    def _refuses(self, handler: BaseHTTPRequestHandler, took: Taken) -> bool:
        """Whether this request came without the credential, having said so where it did."""
        if not self.secret or took.secret == self.secret:
            return False
        _sends(handler, 401, _wrong("no key, or not one this endpoint knows"))
        return True


def _asked_for(path: str) -> str:
    """The path out of what was asked for, with whatever query came after it left off."""
    return path.split("?", 1)[0].rstrip("/") or "/"


def _wrong(said: str) -> dict[str, Any]:
    """A refusal, in the shape both protocols spell one: a message under `error`."""
    return {"error": {"message": said, "type": "invalid_request_error"}}


def _read(handler: BaseHTTPRequestHandler) -> bytes:
    """Everything one request carried, however the client said how much that was.

    Both ways, because the client picks: one that knows the length sends it, and one that
    builds the body as it goes sends it in chunks. A service that read only the first would
    hang on the second, holding a socket open until the suite's own timeout ended the run.
    """
    if "chunked" in handler.headers.get("Transfer-Encoding", "").lower():
        held = bytearray()
        while True:
            said = handler.rfile.readline().split(b";", 1)[0].strip()
            size = int(said or b"0", 16)
            if not size:
                while handler.rfile.readline().strip():
                    pass  # the trailers, which nothing here reads
                return bytes(held)
            held += handler.rfile.read(size)
            handler.rfile.readline()  # the CRLF after each chunk
    return handler.rfile.read(int(handler.headers.get("Content-Length") or 0))


def _sends(
    handler: BaseHTTPRequestHandler, status: int, body: Mapping[str, Any]
) -> None:
    """Answers with one JSON body, saying how long it is so the connection can be kept."""
    said = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(said)))
    handler.end_headers()
    handler.wfile.write(said)


def _streams(handler: BaseHTTPRequestHandler, frames: Sequence[str]) -> None:
    """Answers with server-sent events, closing at the end to say that is all of them.

    Closing rather than counting: a stream's length is not known when its headers go out, and
    the connection ending is what a client reads as the end of a body that never said how
    long it was.
    """
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()
    for one in frames:
        handler.wfile.write(one.encode())
        handler.wfile.flush()
    handler.close_connection = True


@contextlib.contextmanager
def serving(
    serves: Sequence[str] = SERVES, says: str = SAYS, secret: str = KEY
) -> Generator[Serving]:
    """One endpoint, held open for as long as the block and taken down however it ends.

    What the `llm` fixture in `tests/conftest.py` hands out, and what a test that wants two
    of them at once -- an account that falls back to another account is two endpoints -- asks
    for itself, that being a thing one fixture cannot do.

    Args:
      serves: The ids it lists.
      says: What it replies.
      secret: The credential it demands.

    Yields:
      It.
    """
    held = Serving(serves, says, secret)
    try:
        yield held
    finally:
        held.close()
