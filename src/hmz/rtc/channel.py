"""A data channel as a pipe: aiortc on a thread of its own, read and written by blocking calls.

aiortc is asyncio from end to end, and what reads a carrier here blocks. So each connection has
an event loop on a thread of its own, which the connection is made on, its messages arrive on
and its bytes leave from; :class:`Pipe` hands bytes over to it and back, and closing the pipe
closes the connection, stops the loop and joins the thread.

The daemon answers (:func:`answer`) and whoever reaches it offers (:func:`offer`). A
description gathers every candidate before it is sent, so neither side here sends `candidate`;
those a browser trickles are added as they come. The data channel is the one the offer opens,
`hmz`, ordered and reliable; a byte string larger than one message is sent as several, and a
text message closes it.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import concurrent.futures
import importlib.util
import queue
import threading
from typing import TYPE_CHECKING, Any, Self, cast

from hmz.rtc.signals import CHUNK, LABEL, Refused, device, signed

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping, Sequence
    from types import TracebackType

    from aiortc import RTCDataChannel, RTCIceServer, RTCPeerConnection

    from hmz.rtc.signals import Signals

__all__ = ["EXTRA", "Pipe", "answer", "available", "offer"]

#: What to say when aiortc is not in this Python environment. WebRTC is an extra rather than
#: part of every install, so this is a choice somebody made, and the way back is named.
EXTRA = (
    "WebRTC needs aiortc, which is the [webrtc] extra and is not installed in this Python "
    "environment: uv sync --extra webrtc from a checkout, or pip install 'hmz[webrtc]'"
)

#: How long one wait for a signal lasts before the connection is looked at again.
_POLL = 0.25

#: How long closing a connection may take before its loop is stopped anyway.
_CLOSING = 5.0

#: The bytes that may wait to leave before a write waits for them, and how few let it on.
_HIGH = 1024 * 1024
_LOW = 256 * 1024


def available() -> bool:
    """Whether aiortc, the optional dependency `webrtc`, is installed.

    Returns:
      True where a data channel can be offered or answered here.
    """
    return importlib.util.find_spec("aiortc") is not None


def answer(
    signals: Signals,
    *,
    cert: bytes,
    sign: Callable[[bytes], bytes],
    ice_servers: Sequence[Mapping[str, Any]] = (),
    timeout: float = 30.0,
) -> Pipe:
    """Answers one offer as the daemon, and the data channel it opens.

    The offer's SHA-256 fingerprint is the device fingerprint of the side that made it, which
    DTLS holds it to; the answer carries the daemon's certificate and its signature over both
    fingerprints, so that the offering side can tell the answer is the daemon's own.

    Args:
      signals: The signals of the join, the offer first.
      cert: The daemon's device certificate, DER.
      sign: Signs a text with the daemon's device key, answering the 64 bytes of ECDSA P-256
        SHA-256 `r` and `s`.
      ice_servers: The STUN and TURN servers, as the setting `ice_servers` lists them; none
        are used but these.
      timeout: How long the data channel may take to open, in seconds.

    Returns:
      The data channel, open, whose `device` is the offering side's device fingerprint.

    Raises:
      ModuleNotFoundError: If aiortc is not installed.
      Refused: If a signal cannot be read, or the offer or its data channel is not as the
        protocol has it.
      TimeoutError: If the data channel does not open within `timeout`.
      EOFError: If the signals end before it opens.
      ValueError: If an ICE server names no URL.
    """
    _needed()
    return _connect(_answering(signals, cert, sign, _servers(ice_servers)), timeout)


def offer(
    signals: Signals,
    *,
    pin: str,
    verify: Callable[[bytes, bytes, bytes], str],
    ice_servers: Sequence[Mapping[str, Any]] = (),
    timeout: float = 30.0,
) -> Pipe:
    """Offers a data channel to a daemon, and checks the answer is the daemon's pinned.

    Args:
      signals: The signals of the join.
      pin: The daemon id the answer must prove.
      verify: Given a certificate (DER), a text and a signature (the 64 bytes of `r` and `s`),
        answers the SPKI fingerprint of the certificate where the signature verifies under
        its key, and raises ValueError where it does not.
      ice_servers: The STUN and TURN servers; none are used but these.
      timeout: How long the data channel may take to open, in seconds.

    Returns:
      The data channel, open, whose `device` is the daemon id.

    Raises:
      ModuleNotFoundError: If aiortc is not installed.
      Refused: If a signal cannot be read, or the answer is not the pinned daemon's.
      TimeoutError: If the data channel does not open within `timeout`.
      EOFError: If the signals end before it opens.
      ValueError: If an ICE server names no URL.
    """
    _needed()
    return _connect(_offering(signals, pin, verify, _servers(ice_servers)), timeout)


class Pipe:
    """An open data channel, as a carrier: bytes in each direction, until either side closes.

    Reads and writes block the thread that makes them; the connection lives on a loop of its
    own. Closing is idempotent, and whatever the other side does, a pipe is closed by its
    owner, which is what stops its thread.

    Attributes:
      device: The device fingerprint of the other side: a browser's `dtls:…` to the daemon,
        the daemon id to whoever offered.
    """

    def __init__(self, loop: _Loop, peer: _Peer, device: str) -> None:
        self.device = device
        self._loop = loop
        self._peer = peer
        self._rest = b""
        self._ended = False
        self._reading = threading.Lock()
        self._writing = threading.Lock()
        self._closing = threading.Lock()
        self._closed = False

    def recv(self, size: int) -> bytes:
        """Reads what has arrived, waiting for something where nothing has.

        Args:
          size: The most bytes to read.

        Returns:
          Between 1 and `size` bytes, or none once the channel is closed.
        """
        with self._reading:
            if not self._rest and not self._ended:
                chunk = self._peer.inbox.get()
                if chunk is None:
                    self._ended = True
                else:
                    self._rest = chunk
            out, self._rest = self._rest[:size], self._rest[size:]
            return out

    def sendall(self, data: bytes) -> None:
        """Writes every byte, in messages of at most 16 384 bytes each.

        Args:
          data: The bytes.

        Raises:
          BrokenPipeError: If the channel is closed.
        """
        with self._writing:
            if self._closed:
                raise BrokenPipeError
            self._loop.run(self._peer.send(data))

    def close(self) -> None:
        """Closes the channel and the connection, and stops the thread they live on."""
        with self._closing:
            if self._closed:
                return
            self._closed = True
        try:
            self._loop.run(self._peer.close(), _CLOSING)
        except TimeoutError:
            pass
        finally:
            self._loop.stop()
            self._peer.inbox.put(None)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.close()


class _Loop:
    """An event loop running on a thread of its own until it is stopped."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._signalling = concurrent.futures.ThreadPoolExecutor(
            thread_name_prefix="hmz-rtc"
        )
        self.loop.set_default_executor(self._signalling)
        self._thread = threading.Thread(target=self._run, name="hmz-rtc", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
            # What aiortc leaves behind once a connection is closed, given up.
            left = asyncio.all_tasks(self.loop)
            for task in left:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*left, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            # A signal still being sent or waited for is left to its thread rather than waited on.
            self._signalling.shutdown(wait=False, cancel_futures=True)
        finally:
            self.loop.close()

    def run[T](self, work: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
        """Runs a coroutine on the loop, waiting for what it answers.

        Raises:
          BrokenPipeError: If the loop is stopped before the coroutine is done.
        """
        try:
            future = asyncio.run_coroutine_threadsafe(work, self.loop)
        except RuntimeError:  # the loop is closed
            work.close()
            raise BrokenPipeError from None
        try:
            return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise
        except concurrent.futures.CancelledError:
            raise BrokenPipeError from None

    def stop(self) -> None:
        """Stops the loop and joins its thread."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join()


class _Peer:
    """One connection and its data channel, as the loop sees them."""

    def __init__(self, connection: RTCPeerConnection) -> None:
        self.connection = connection
        self.channel: RTCDataChannel | None = None
        self.inbox: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()
        self.opened: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        # Read here as well, so that a connection that failed after nobody waited says nothing.
        self.opened.add_done_callback(lambda done: done.cancelled() or done.exception())
        self._low = asyncio.Event()
        self._over = False
        self._tasks: set[asyncio.Future[None]] = set()

        @connection.on("connectionstatechange")
        def _changed() -> None:
            if connection.connectionState in {"failed", "closed"}:
                self._ended(ConnectionError("The WebRTC connection failed."))

    def take(self, channel: RTCDataChannel) -> None:
        """Makes a channel the one this connection carries bytes on."""
        self.channel = channel
        channel.bufferedAmountLowThreshold = _LOW

        @channel.on("message")
        def _message(message: bytes | str) -> None:
            if isinstance(message, str):
                self._later(self.close())
            elif message:
                self.inbox.put(message)

        @channel.on("open")
        def _open() -> None:
            if not self.opened.done():
                self.opened.set_result(None)

        @channel.on("close")
        def _close() -> None:
            self._ended(EOFError("The data channel closed before it opened."))

        @channel.on("bufferedamountlow")
        def _low() -> None:
            self._low.set()

        if channel.readyState == "open":
            _open()

    def refuse(self, why: str) -> None:
        """Gives up the connection for a peer the protocol does not admit."""
        self._ended(Refused(why))
        self._later(self.close())

    def _later(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _ended(self, why: Exception) -> None:
        if not self.opened.done():
            self.opened.set_exception(why)
        self._over = True
        self.inbox.put(None)
        self._low.set()

    async def send(self, data: bytes) -> None:
        """Sends bytes on the channel, waiting while too many wait to leave."""
        channel = self.channel
        if channel is None or self._over:
            raise BrokenPipeError
        for start in range(0, len(data), CHUNK):
            while not self._over and channel.bufferedAmount > _HIGH:
                self._low.clear()
                await self._low.wait()
            if self._over or channel.readyState != "open":
                raise BrokenPipeError
            channel.send(data[start : start + CHUNK])

    async def close(self) -> None:
        """Closes the connection, and with it the channel."""
        await self.connection.close()
        self._ended(EOFError("The connection was closed."))


def _needed() -> None:
    if not available():
        raise ModuleNotFoundError(EXTRA)


def _connect(work: Coroutine[Any, Any, tuple[_Peer, str]], timeout: float) -> Pipe:
    loop = _Loop()
    try:
        peer, who = loop.run(_within(work, timeout))
    except BaseException:
        loop.stop()
        raise
    return Pipe(loop, peer, who)


async def _within[T](work: Coroutine[Any, Any, T], seconds: float) -> T:
    async with asyncio.timeout(seconds):
        return await work


def _servers(ice_servers: Sequence[Mapping[str, Any]]) -> list[RTCIceServer]:
    from aiortc import RTCIceServer

    servers: list[RTCIceServer] = []
    for server in ice_servers:
        urls = server.get("urls")
        if not urls or not isinstance(urls, str | list):
            msg = "An ICE server needs urls: a URL, or a list of them."
            raise ValueError(msg)
        servers.append(
            RTCIceServer(
                urls=cast("str | list[str]", urls),
                username=server.get("username"),
                credential=server.get("credential"),
            )
        )
    return servers


def _connection(ice_servers: list[RTCIceServer]) -> RTCPeerConnection:
    from aiortc import RTCConfiguration, RTCPeerConnection

    # A list even where empty: given none, aiortc reaches for a STUN server of Google's.
    return RTCPeerConnection(RTCConfiguration(iceServers=ice_servers))


async def _answering(
    signals: Signals,
    cert: bytes,
    sign: Callable[[bytes], bytes],
    ice_servers: list[RTCIceServer],
) -> tuple[_Peer, str]:
    from aiortc import RTCSessionDescription

    early: list[dict[str, Any]] = []
    while (signal := await _next(signals, "offer"))["type"] == "candidate":
        early.append(signal)
    sdp = _text(signal, "sdp")
    who = device(sdp)
    peer = _Peer(_connection(ice_servers))

    @peer.connection.on("datachannel")
    def _channel(channel: RTCDataChannel) -> None:
        if peer.channel is not None:
            peer.refuse("An offer opens exactly one data channel.")
        elif (
            channel.label != LABEL
            or not channel.ordered
            or channel.maxRetransmits is not None
            or channel.maxPacketLifeTime is not None
        ):
            peer.refuse(f"The data channel must be {LABEL}, ordered and reliable.")
        else:
            peer.take(channel)

    try:
        await peer.connection.setRemoteDescription(RTCSessionDescription(sdp, "offer"))
        await _candidates(peer, early)
        await peer.connection.setLocalDescription(await peer.connection.createAnswer())
        mine = peer.connection.localDescription.sdp
        await asyncio.to_thread(
            signals.send,
            {
                "type": "answer",
                "sdp": mine,
                "cert": base64.b64encode(cert).decode(),
                "sig": base64.urlsafe_b64encode(sign(signed(sdp, mine)))
                .decode()
                .rstrip("="),
            },
        )
        await _opening(peer, signals)
    except BaseException:
        await peer.close()
        raise
    return peer, who


async def _offering(
    signals: Signals,
    pin: str,
    verify: Callable[[bytes, bytes, bytes], str],
    ice_servers: list[RTCIceServer],
) -> tuple[_Peer, str]:
    from aiortc import RTCSessionDescription

    peer = _Peer(_connection(ice_servers))
    try:
        peer.take(peer.connection.createDataChannel(LABEL, ordered=True))
        await peer.connection.setLocalDescription(await peer.connection.createOffer())
        mine = peer.connection.localDescription.sdp
        await asyncio.to_thread(signals.send, {"type": "offer", "sdp": mine})
        early: list[dict[str, Any]] = []
        while (signal := await _next(signals, "answer"))["type"] == "candidate":
            early.append(signal)
        sdp = _text(signal, "sdp")
        _proven(signal, signed(mine, sdp), pin, verify)
        await peer.connection.setRemoteDescription(RTCSessionDescription(sdp, "answer"))
        await _candidates(peer, early)
        await _opening(peer, signals)
    except BaseException:
        await peer.close()
        raise
    return peer, pin


def _proven(
    signal: Mapping[str, Any],
    text: bytes,
    pin: str,
    verify: Callable[[bytes, bytes, bytes], str],
) -> None:
    """Refuses an answer whose certificate is not the daemon pinned, or whose signature fails."""
    try:
        cert = base64.b64decode(_text(signal, "cert"), validate=True)
        sig = _text(signal, "sig")
        raw = base64.b64decode(
            sig + "=" * (-len(sig) % 4), altchars=b"-_", validate=True
        )
        proven = verify(cert, text, raw)
    except (ValueError, binascii.Error) as why:
        msg = "The answer's signature does not verify."
        raise Refused(msg) from why
    if proven != pin:
        msg = f"The answer is not daemon {pin}'s."
        raise Refused(msg)


async def _opening(peer: _Peer, signals: Signals) -> None:
    """Adds the candidates the other side trickles until the data channel opens."""
    while not peer.opened.done():
        reading = asyncio.ensure_future(_one(signals, "candidate"))
        await asyncio.wait({peer.opened, reading}, return_when=asyncio.FIRST_COMPLETED)
        if not reading.done():
            reading.cancel()
            break
        try:
            await _candidates(peer, [reading.result()])
        except TimeoutError:
            continue
        except EOFError:
            break  # the other side may stop signalling once its candidates are sent
    await peer.opened


async def _next(signals: Signals, wanted: str) -> dict[str, Any]:
    """The next signal, which must be `wanted` or a candidate, however long it takes."""
    while True:
        try:
            return await _one(signals, wanted)
        except TimeoutError:
            continue


async def _one(signals: Signals, wanted: str) -> dict[str, Any]:
    """The next signal within a moment, which must be `wanted` or a candidate."""
    data = await asyncio.to_thread(signals.receive, _POLL)
    signal = cast("dict[str, Any]", data) if isinstance(data, dict) else {}
    if signal.get("type") not in {wanted, "candidate"}:
        msg = f"A signal here must be {wanted} or candidate."
        raise Refused(msg)
    return signal


def _text(signal: Mapping[str, Any], key: str) -> str:
    value = signal.get(key)
    if not isinstance(value, str):
        msg = f"A {signal['type']} signal needs {key} as text."
        raise Refused(msg)
    return value


async def _candidates(peer: _Peer, signals: Sequence[Mapping[str, Any]]) -> None:
    from aiortc.sdp import candidate_from_sdp

    for signal in signals:
        line = signal.get("candidate")
        mid = signal.get("sdpMid")
        index = signal.get("sdpMLineIndex")
        if (
            not isinstance(line, str)
            or not isinstance(mid, str | None)
            or not isinstance(index, int | None)
        ):
            msg = "A candidate signal needs candidate, sdpMid and sdpMLineIndex."
            raise Refused(msg)
        if not line:
            continue  # the end of the other side's candidates
        words = line.removeprefix("candidate:")
        if len(words.split()) < 8:  # noqa: PLR2004 - as many as a candidate line has
            msg = f"{line} is not a candidate."
            raise Refused(msg)
        try:
            candidate = candidate_from_sdp(words)
            candidate.sdpMid = mid
            candidate.sdpMLineIndex = index
            await peer.connection.addIceCandidate(candidate)
        except ValueError as why:
            msg = f"{line} is not a candidate."
            raise Refused(msg) from why
