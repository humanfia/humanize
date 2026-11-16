"""A daemon's proof of its id: a fresh nonce signed by the key its certificate holds."""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from hmz.relay import CONTEXT, fingerprint, proven
from tests.unit.relay.doubles_relay import der, made, signed

NONCE = "bm9uY2Utbm9uY2Utbm9uY2Utbm9uY2Utbm9uY2U"


def test_the_fingerprint_is_the_spki_sha256_in_lowercase_base32() -> None:
    _, cert = made()
    spki = cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    expected = base64.b32encode(hashlib.sha256(spki).digest()).decode().rstrip("=")
    assert fingerprint(cert) == expected.lower()
    assert len(fingerprint(cert)) == 52


def test_a_nonce_signed_by_the_key_of_the_id_proves_it() -> None:
    key, cert = made()
    assert proven(fingerprint(cert), NONCE, der(cert), signed(key, NONCE))


def test_another_nonce_another_key_or_another_id_proves_nothing() -> None:
    key, cert = made()
    other, _ = made()
    daemon = fingerprint(cert)
    assert not proven(daemon, NONCE, der(cert), signed(key, "another"))
    assert not proven(daemon, NONCE, der(cert), signed(other, NONCE))
    assert not proven(fingerprint(made()[1]), NONCE, der(cert), signed(key, NONCE))


def test_what_cannot_be_read_proves_nothing() -> None:
    key, cert = made()
    daemon, sig = fingerprint(cert), signed(key, NONCE)
    assert not proven(daemon, NONCE, "not base64!", sig)
    assert not proven(daemon, NONCE, base64.b64encode(b"junk").decode(), sig)
    assert not proven(daemon, NONCE, der(cert), "not base64url!")
    assert not proven(daemon, NONCE, der(cert), sig[:-4])


def test_a_key_off_p256_proves_nothing() -> None:
    key, cert = made(ec.SECP384R1())
    r, s = decode_dss_signature(
        key.sign(f"{CONTEXT}\n{NONCE}".encode(), ec.ECDSA(hashes.SHA256()))
    )
    sig = base64.urlsafe_b64encode(r.to_bytes(48) + s.to_bytes(48)).decode()
    assert not proven(fingerprint(cert), NONCE, der(cert), sig.rstrip("="))
