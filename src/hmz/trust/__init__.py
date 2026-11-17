"""Who is at the other end of a carrier that proves nothing by itself.

A Unix socket, `ssh` and WSL have already said the client is the daemon's user; a TCP port, a
WebSocket and a relay have said nothing. On those, each side shows the self-signed certificate
of its own device (:mod:`hmz.trust.identity`), and each checks the other's by the fingerprint
of its key rather than by any authority: the client against the daemon id it pinned
(:mod:`hmz.trust.pins`), the daemon against the devices paired with it
(:mod:`hmz.trust.devices`), which a one-time code admits (:mod:`hmz.trust.pairing`). Native
clients do this in mutual TLS over whatever pipe the carrier is (:mod:`hmz.trust.tls`); a
browser does it in WebRTC, whose DTLS the daemon signs for (:mod:`hmz.trust.webrtc`).

Section 4 of `protocol/wire.md` is what this is, and Section 4.14 of `protocol/files.md` where
it is kept.
"""
