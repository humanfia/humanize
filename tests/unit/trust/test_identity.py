"""`hmz.trust.identity`: this machine's key, its certificate, and the fingerprint of either."""

from __future__ import annotations

import base64
import datetime
import hashlib
import socket
import stat
import subprocess
import sys
import threading
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from hmz.trust import identity

#: What the machine is asked for, before every test puts a fixed id in its place.
MACHINE_ID = identity.machine_id


def test_the_device_is_kept_under_the_home_by_machine() -> None:
    assert identity.directory().parts[-2:] == ("identity", "machine")


def test_a_device_is_made_once_and_read_back() -> None:
    made = identity.device()
    again = identity.device()
    assert again.fingerprint == made.fingerprint
    assert again.certificate == made.certificate


def test_the_files_are_the_users_alone() -> None:
    identity.device()
    at = identity.directory()
    assert stat.S_IMODE(at.stat().st_mode) == 0o700
    for name in (identity.KEY, identity.CERT):
        assert stat.S_IMODE((at / name).stat().st_mode) == 0o600


def test_the_key_is_p256_pkcs8_unencrypted() -> None:
    made = identity.device()
    pem = (identity.directory() / identity.KEY).read_bytes()
    assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    key = serialization.load_pem_private_key(pem, None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    assert key.curve.name == "secp256r1"
    assert key.public_key() == made.key.public_key()


def test_the_certificate_is_as_the_protocol_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity, "host", lambda: "box")
    before = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    made = identity.device().certificate
    assert made.version == x509.Version.v3
    common = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hmz box")])
    assert made.subject == common
    assert made.issuer == common
    assert isinstance(made.signature_hash_algorithm, hashes.SHA256)
    assert made.signature_algorithm_oid == x509.SignatureAlgorithmOID.ECDSA_WITH_SHA256
    assert 0 < made.serial_number < 1 << 128
    assert made.not_valid_before_utc >= before
    assert made.not_valid_after_utc == datetime.datetime(
        9999, 12, 31, 23, 59, 59, tzinfo=datetime.UTC
    )
    assert identity.self_signed(made)


def test_a_long_host_is_cut_so_the_common_name_is_64_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "gethostname", lambda: "h" * 70 + ".example.org")
    made = identity.device().certificate
    (common,) = made.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    assert common.value == "hmz " + "h" * 60
    assert len(common.value) == 64
    assert made.issuer == made.subject


def test_the_host_is_its_name_up_to_the_first_dot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "gethostname", lambda: "box.example.org")
    assert identity.host() == "box"


def test_the_fingerprint_is_the_base32_of_the_spki_digest() -> None:
    made = identity.device()
    spki = made.certificate.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    digest = hashlib.sha256(spki).digest()
    expected = base64.b32encode(digest).decode().rstrip("=").lower()
    assert made.fingerprint == expected
    assert identity.fingerprint(made.certificate) == expected
    assert len(expected) == 52
    assert identity.is_fingerprint(expected)
    assert not identity.is_fingerprint(expected.upper())
    assert not identity.is_fingerprint(expected[:-1])
    assert not identity.is_fingerprint(None)


def test_base32_is_lowercase_without_padding() -> None:
    assert identity.base32(b"\xff") == "74"


def test_a_key_left_without_its_certificate_is_kept() -> None:
    made = identity.device()
    (identity.directory() / identity.CERT).unlink()
    again = identity.device()
    assert again.fingerprint == made.fingerprint
    assert (identity.directory() / identity.CERT).is_file()


def test_a_certificate_of_another_key_is_made_again() -> None:
    made = identity.device()
    other = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hmz other")])
    stray = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(other.public_key())
        .serial_number(1)
        .not_valid_before(datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC))
        .not_valid_after(datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC))
        .sign(other, hashes.SHA256())
    )
    (identity.directory() / identity.CERT).write_bytes(
        stray.public_bytes(serialization.Encoding.PEM)
    )
    assert identity.device().fingerprint == made.fingerprint


def test_threads_racing_to_make_it_end_with_one() -> None:
    made: list[str] = []

    def make() -> None:
        made.append(identity.device().fingerprint)

    threads = [threading.Thread(target=make) for _ in range(8)]
    for one in threads:
        one.start()
    for one in threads:
        one.join()
    assert len(set(made)) == 1
    assert made[0] == identity.device().fingerprint


def test_a_signature_is_r_and_s_and_verifies() -> None:
    made = identity.device()
    signature = made.signs(b"hello")
    assert len(signature) == 64
    assert identity.verifies(made.certificate, b"hello", signature)
    assert not identity.verifies(made.certificate, b"hellO", signature)
    assert not identity.verifies(made.certificate, b"hello", signature[:-1])
    assert not identity.verifies(made.certificate, b"hello", bytes(64))


def test_a_certificate_signed_by_another_key_is_not_self_signed() -> None:
    made = identity.device()
    other = ec.generate_private_key(ec.SECP256R1())
    forged = (
        x509.CertificateBuilder()
        .subject_name(made.certificate.subject)
        .issuer_name(made.certificate.subject)
        .public_key(made.key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC))
        .not_valid_after(datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC))
        .sign(other, hashes.SHA256())
    )
    assert not identity.self_signed(forged)


def test_a_mac_is_known_by_its_platform_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    said = '  "IOPlatformUUID" = "0A1B2C3D-0000-1111-2222-333344445555"\n'

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert argv[0].endswith("ioreg")
        return subprocess.CompletedProcess(argv, 0, said, "")

    monkeypatch.setattr(subprocess, "run", run)
    assert MACHINE_ID() == "0A1B2C3D-0000-1111-2222-333344445555"


def test_elsewhere_a_machine_is_known_by_its_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd14")
    monkeypatch.setattr(socket, "gethostname", lambda: "box.example.org")
    assert MACHINE_ID() == "box"


def test_a_key_that_is_not_ec_is_refused() -> None:
    at = identity.directory()
    at.mkdir(parents=True)
    from cryptography.hazmat.primitives.asymmetric import ed25519

    (at / identity.KEY).write_bytes(
        ed25519.Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    with pytest.raises(TypeError):
        identity.device()
    assert (at / identity.KEY).is_file()
