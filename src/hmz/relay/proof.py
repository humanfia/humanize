"""Whether a daemon registering under an id holds the key that id was made of.

A daemon id is the SPKI fingerprint of the daemon's device certificate, so anybody can say
one; what nobody else can do is sign a fresh nonce with the key behind it. The relay asks for
exactly that before it gives a daemon its room, and nothing more: it does not care who made
the certificate, what it is called or when it runs out, since a client pins the id and checks
the certificate again end to end.

The one check is made here with `cryptography` alone. The identity helpers every other side
of a session uses will hold the same fingerprint and the same signature; this is the relay's
own copy of the few lines it needs, until they can be shared.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

__all__ = ["CONTEXT", "fingerprint", "proven"]

#: What a registering daemon signs, ahead of a line feed and the nonce it was given.
CONTEXT = "hmz-relay/1"

#: How long the two halves of a P-256 signature are, each.
_HALF = 32


def fingerprint(certificate: x509.Certificate) -> str:
    """The SPKI fingerprint of a certificate: the daemon id, for a daemon's own.

    Args:
      certificate: The certificate.

    Returns:
      The SHA-256 of its `SubjectPublicKeyInfo`, in lowercase base32 without padding.
    """
    spki = certificate.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    digest = hashlib.sha256(spki).digest()
    return base64.b32encode(digest).decode("ascii").rstrip("=").lower()


def proven(daemon: str, nonce: str, cert: str, sig: str) -> bool:
    """Whether a `prove` proves a daemon id, for the nonce it was challenged with.

    Args:
      daemon: The id the daemon registered under.
      nonce: The nonce it was given, as it was sent.
      cert: Its device certificate, in base64 of DER.
      sig: The base64url of the 64 bytes of `r` and `s` it signed the nonce with.

    Returns:
      True where the certificate's fingerprint is the id and the signature verifies under its
      P-256 key; false for anything else, a certificate or signature that cannot be read
      included.
    """
    try:
        certificate = x509.load_der_x509_certificate(
            base64.b64decode(cert, validate=True)
        )
        signature = base64.b64decode(
            sig + "=" * (-len(sig) % 4), altchars=b"-_", validate=True
        )
        key = certificate.public_key()
    except (ValueError, binascii.Error, UnsupportedAlgorithm):
        return False
    if fingerprint(certificate) != daemon or len(signature) != 2 * _HALF:
        return False
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        return False
    der = encode_dss_signature(
        int.from_bytes(signature[:_HALF]), int.from_bytes(signature[_HALF:])
    )
    try:
        key.verify(der, f"{CONTEXT}\n{nonce}".encode(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True
