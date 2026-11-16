"""WebRTC data channels as carriers: how a browser reaches a daemon through a relay.

    from hmz.rtc import answer

    with answer(signals, cert=cert, sign=sign, ice_servers=servers) as pipe:
        pipe.sendall(pipe.recv(65536))

A browser can open neither a socket nor TLS of its own choosing, but it can open WebRTC: it
offers a data channel through the relay's signals, and the daemon answers. What secures it is
DTLS, held to fingerprints each side signs or pins rather than to any certificate authority:
the daemon signs both with its device key, so the offering side knows the answer is the daemon
it pins, and DTLS holds the browser to the fingerprint of its own persistent certificate, which
is the device the daemon knows it as. :mod:`hmz.rtc.signals` holds those texts, and
:mod:`hmz.rtc.channel` the connection, on aiortc -- the optional dependency `webrtc`, imported
only once a channel is offered or answered, so that `hmz` without it still imports.

Both sides end in a :class:`Pipe`: reliable, ordered bytes in each direction, until either
closes. The daemon answers; :func:`offer` is the same channel from a native client's side.
"""

from hmz.rtc.channel import EXTRA, Pipe, answer, available, offer
from hmz.rtc.signals import CHUNK, LABEL, Refused, Signals, device, fingerprint, signed

__all__ = [
    "CHUNK",
    "EXTRA",
    "LABEL",
    "Pipe",
    "Refused",
    "Signals",
    "answer",
    "available",
    "device",
    "fingerprint",
    "offer",
    "signed",
]
