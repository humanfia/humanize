"""What the daemon says for the DTLS of a WebRTC connection, and how a browser is known by it.

A browser has no device certificate to show in TLS; it has the DTLS certificate WebRTC
connects with, kept for as long as the browser lets it be. Its offer and the daemon's answer
cross the relay, which is trusted with neither: so the daemon signs the `sha-256` fingerprints
of both descriptions with its device key, and sends its certificate beside the signature. A
browser holding the daemon id checks that the certificate is the daemon's and that what was
signed is its own offer; DTLS then holds each side to the fingerprint the other was given, and
the daemon knows the browser as `dtls:` and that fingerprint.
"""

from __future__ import annotations

import base64
import binascii
import re

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from hmz.trust.identity import Identity, base32, fingerprint, verifies
from hmz.trust.pins import matches

__all__ = ["SIGNED", "answered", "device", "fingerprint_in", "signs"]

#: What the signed text begins with, before the two fingerprints.
SIGNED = "hmz-webrtc/1"

#: How many bytes a `sha-256` fingerprint is.
_SHA256 = 32

#: A description's `sha-256` fingerprint line, and the fingerprint as written there.
_FINGERPRINT = re.compile(
    r"^a=fingerprint:sha-256[ \t]+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){31})[ \t]*\r?$",
    re.MULTILINE | re.IGNORECASE,
)


def fingerprint_in(sdp: str) -> str:
    """The `sha-256` fingerprint of a session description, as written there.

    Args:
      sdp: The offer or the answer.

    Returns:
      The first `sha-256` fingerprint it gives: 32 bytes in hex, colon-separated.

    Raises:
      ValueError: If it gives none.
    """
    found = _FINGERPRINT.search(sdp)
    if found is None:
        raise ValueError("That description gives no sha-256 fingerprint.")
    return found.group(1)


def signs(identity: Identity, offer: str, answer: str) -> dict[str, str]:
    """What the daemon's `answer` signal carries besides its description.

    Args:
      identity: This machine's.
      offer: The `sha-256` fingerprint of the offer, as written there.
      answer: That of the answer, as written there.

    Returns:
      `cert`, the device certificate in base64 of its DER, and `sig`, the base64url of the
      device key's signature over `hmz-webrtc/1`, the offer's and the answer's fingerprints,
      a line feed between each.
    """
    der = identity.certificate.public_bytes(serialization.Encoding.DER)
    signature = identity.signs(_signed(offer, answer))
    return {
        "cert": base64.b64encode(der).decode("ascii"),
        "sig": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def answered(cert: str, sig: str, offer: str, answer: str, pinned: str) -> bool:
    """Whether an `answer` signal is the pinned daemon's, for this side's own offer.

    Args:
      cert: Its `cert`.
      sig: Its `sig`.
      offer: The `sha-256` fingerprint of the offer this side made.
      answer: That of the answer's description.
      pinned: The daemon id this side pins.

    Returns:
      Whether `cert` has the pinned id and `sig` verifies under its key over these two
      fingerprints. False where either does not decode.
    """
    try:
        certificate = x509.load_der_x509_certificate(
            base64.b64decode(cert, validate=True)
        )
        signature = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        known = fingerprint(certificate)
    except (ValueError, binascii.Error, UnsupportedAlgorithm):
        return False
    return matches(known, pinned) and verifies(
        certificate, _signed(offer, answer), signature
    )


def device(offer: str) -> str:
    """The device fingerprint of a browser, from the fingerprint of its offer.

    Args:
      offer: The `sha-256` fingerprint of the offer, as written there.

    Returns:
      `dtls:` and the base32 of its bytes.

    Raises:
      ValueError: If it is not 32 bytes in colon-separated hex.
    """
    raw = bytes.fromhex(offer.replace(":", ""))
    if len(raw) != _SHA256:
        raise ValueError("A sha-256 fingerprint is 32 bytes.")
    return f"dtls:{base32(raw)}"


def _signed(offer: str, answer: str) -> bytes:
    """The text the daemon signs: the label and the two fingerprints, a line each."""
    return f"{SIGNED}\n{offer}\n{answer}".encode()
