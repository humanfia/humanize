"""A daemon's device key and certificate, made afresh, and what it signs a relay's nonce with."""

from __future__ import annotations

import base64
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import NameOID

from hmz.relay import CONTEXT


def made(
    curve: ec.EllipticCurve | None = None,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """A key and a device certificate for it, self-signed."""
    key = ec.generate_private_key(curve or ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hmz test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, cert


def signed(key: ec.EllipticCurvePrivateKey, nonce: str) -> str:
    """The `sig` of a `prove`: `r` and `s`, 32 bytes each, in base64url."""
    r, s = decode_dss_signature(
        key.sign(f"{CONTEXT}\n{nonce}".encode(), ec.ECDSA(hashes.SHA256()))
    )
    raw = r.to_bytes(32) + s.to_bytes(32)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def der(cert: x509.Certificate) -> str:
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
