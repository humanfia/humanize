"""This machine's one key pair, the self-signed certificate that says it, and how either is known.

A device is known by its key and by nothing else: no authority signs its certificate, no name
in it is checked, and it never expires. What another side keeps of it is the SPKI
fingerprint, the SHA-256 of the public key as the certificate encodes it, in base32 -- which is
a daemon's id to its clients and a client's device fingerprint to a daemon. The daemon of a
machine and every client on it are one device, with one certificate between them.

Kept in the data directory, a directory per machine (`<data>/identity/<machine>/`), because a home
many machines mount must not make them one device: the directory is named for the machine's
own id, which the operating system keeps for exactly this. Made the first time anything needs
it, by whichever of two processes gets there first: the other waits on the directory's lock
and reads what the first one wrote, so that a machine never has two keys, not even for a
moment, and never makes a second while it holds one.
"""

from __future__ import annotations

import base64
import contextlib
import datetime
import fcntl
import hashlib
import os
import re
import secrets
import socket
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.x509.oid import NameOID

from hmz import data

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "CERT",
    "KEY",
    "Identity",
    "base32",
    "device",
    "directory",
    "fingerprint",
    "host",
    "is_fingerprint",
    "machine_id",
    "self_signed",
    "verifies",
]

#: The device's private key, PKCS #8 in PEM, inside its directory.
KEY = "key.pem"

#: The device certificate, in PEM, beside it.
CERT = "cert.pem"

#: When a device certificate stops being valid, which is never: `99991231235959Z`.
_NEVER = datetime.datetime(9999, 12, 31, 23, 59, 59, tzinfo=datetime.UTC)

#: How much of the host name a certificate's common name holds: `hmz ` and 60 characters
#: are the 64 X.509 allows, which a long host name would otherwise run past.
_HOST_IN_NAME = 60

#: How long a signature of `r` and `s` is: 32 bytes each.
_SIGNATURE = 64

#: What an SPKI fingerprint looks like: 32 bytes in lowercase base32, unpadded.
_FINGERPRINT = re.compile(r"[a-z2-7]{52}")

#: Where Linux keeps the id of the machine, written once when it was installed.
_MACHINE_ID = "/etc/machine-id"

#: The line of `ioreg` that holds a Mac's own id.
_PLATFORM_UUID = re.compile(r'"IOPlatformUUID"\s*=\s*"([^"]+)"')


@dataclass(frozen=True)
class Identity:
    """One device's key pair and its certificate, as this process holds them.

    Attributes:
      key: The private key, which never leaves this process but as a signature.
      certificate: The self-signed certificate of its public half.
    """

    key: ec.EllipticCurvePrivateKey
    certificate: x509.Certificate

    @property
    def fingerprint(self) -> str:
        """The SPKI fingerprint of the certificate: the daemon id, and the device fingerprint."""
        return fingerprint(self.certificate)

    def signs(self, message: bytes) -> bytes:
        """A signature of the message by the device key, as the 64 bytes of `r` and `s`.

        ECDSA on P-256 over SHA-256, written as the two numbers side by side rather than in
        DER, which is how the relay and a browser read one.

        Args:
          message: What is signed.

        Returns:
          The signature.
        """
        r, s = decode_dss_signature(self.key.sign(message, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32) + s.to_bytes(32)


def base32(data: bytes) -> str:
    """Bytes in base32 as the protocol writes it: lowercase, without padding."""
    return base64.b32encode(data).decode("ascii").rstrip("=").lower()


def fingerprint(certificate: x509.Certificate) -> str:
    """The SPKI fingerprint of a certificate.

    Args:
      certificate: Any certificate.

    Returns:
      The SHA-256 of the DER of its `SubjectPublicKeyInfo`, in base32: 52 characters.
    """
    spki = certificate.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base32(hashlib.sha256(spki).digest())


def is_fingerprint(said: object) -> bool:
    """Whether something is written as an SPKI fingerprint is: 52 base32 characters."""
    return isinstance(said, str) and _FINGERPRINT.fullmatch(said) is not None


def self_signed(certificate: x509.Certificate) -> bool:
    """Whether a certificate is signed by the key it holds, which is all a device's need be.

    Args:
      certificate: The certificate another side presented.

    Returns:
      Whether its issuer is its subject and its signature verifies under its own public key.
    """
    try:
        certificate.verify_directly_issued_by(certificate)
    except (ValueError, TypeError, InvalidSignature, UnsupportedAlgorithm):
        return False
    return True


def verifies(certificate: x509.Certificate, message: bytes, signature: bytes) -> bool:
    """Whether a signature of `r` and `s` is the key of a certificate's over a message.

    Args:
      certificate: The certificate whose key is said to have signed.
      message: What it is said to have signed.
      signature: The 64 bytes of `r` and `s`, as :meth:`Identity.signs` writes them.

    Returns:
      Whether it does, which is False for a key that is not P-256 and a signature of another
      length.
    """
    try:
        key = certificate.public_key()
    except (ValueError, UnsupportedAlgorithm):
        return False
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        return False
    if len(signature) != _SIGNATURE:
        return False
    der = encode_dss_signature(
        int.from_bytes(signature[:32]), int.from_bytes(signature[32:])
    )
    try:
        key.verify(der, message, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


def host() -> str:
    """This machine's host name, up to its first `.`."""
    return socket.gethostname().split(".")[0]


def machine_id() -> str:
    """What this machine is called among the machines that mount one home.

    Returns:
      The content of `/etc/machine-id` on Linux and the `IOPlatformUUID` on macOS, and the
      host name up to its first `.` elsewhere -- and where either cannot be read, as in a
      container that was given no machine id.
    """
    if sys.platform == "linux":
        with contextlib.suppress(OSError, UnicodeDecodeError):
            with open(_MACHINE_ID, encoding="ascii") as reading:  # noqa: PTH123
                said = reading.read().strip()
            if said:
                return said
    elif sys.platform == "darwin":
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            ran = subprocess.run(
                ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            found = _PLATFORM_UUID.search(ran.stdout)
            if found:
                return found.group(1)
    return host()


def directory() -> Path:
    """Where this machine's identity is kept: `<data>/identity/<machine>/`, made or not."""
    return data() / "identity" / machine_id()


def device() -> Identity:
    """This machine's identity, made the first time it is asked for.

    Read as it is where it is whole. Otherwise made under the directory's lock, which a
    second process making it at the same moment waits on and then reads the first one's
    from: the certificate is written first and the key last, each whole, so a reader finds a
    key only beside its certificate. A key already there is never replaced: a certificate
    gone from beside it is made again for that key.

    Returns:
      The identity.

    Raises:
      OSError: If the directory or a file in it cannot be made.
      ValueError: If the key there does not load.
      TypeError: If it is not an elliptic-curve key.
    """
    at = directory()
    held = _held(at)
    if held is not None:
        return held
    at.mkdir(mode=0o700, parents=True, exist_ok=True)
    at.chmod(0o700)
    locking = os.open(at, os.O_RDONLY)
    try:
        fcntl.flock(locking, fcntl.LOCK_EX)
        held = _held(at)
        if held is not None:
            return held
        return _made(at)
    finally:
        os.close(locking)


def _held(at: Path) -> Identity | None:
    """The identity in a directory, and None where it has no key and certificate whole.

    Args:
      at: The directory.

    Raises:
      ValueError: If the key there does not load.
      TypeError: If it is not an elliptic-curve key.
    """
    try:
        key = serialization.load_pem_private_key((at / KEY).read_bytes(), None)
    except FileNotFoundError:
        return None
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise TypeError(f"{at / KEY} is not an elliptic-curve key")
    try:
        certificate = x509.load_pem_x509_certificate((at / CERT).read_bytes())
    except (FileNotFoundError, ValueError):
        return None
    if certificate.public_key() != key.public_key():
        return None
    return Identity(key, certificate)


def _made(at: Path) -> Identity:
    """Makes what is missing of the identity in a directory, under its lock.

    Args:
      at: The directory, held locked.

    Returns:
      The identity: the key that was there, or a new one, with a certificate made for it
      where none matching it was.

    Raises:
      ValueError: If the key there does not load.
      TypeError: If it is not an elliptic-curve key.
    """
    from hmz.coganchor import atomic

    try:
        loaded = serialization.load_pem_private_key((at / KEY).read_bytes(), None)
    except FileNotFoundError:
        key = ec.generate_private_key(ec.SECP256R1())
        fresh = True
    else:
        if not isinstance(loaded, ec.EllipticCurvePrivateKey):
            raise TypeError(f"{at / KEY} is not an elliptic-curve key")
        key, fresh = loaded, False
    certificate = _certified(key)
    atomic.writes(
        at / CERT, certificate.public_bytes(serialization.Encoding.PEM), mode=0o600
    )
    if fresh:
        atomic.writes(
            at / KEY,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            mode=0o600,
        )
    return Identity(key, certificate)


def _certified(key: ec.EllipticCurvePrivateKey) -> x509.Certificate:
    """A device certificate for a key: X.509 v3, self-signed, `hmz <host>`, valid forever.

    `<host>` is the host name up to its first `.`, cut to its first 60 characters.

    Args:
      key: The device key.

    Returns:
      The certificate, with a serial of 16 random bytes and valid from now.
    """
    called = f"hmz {host()[:_HOST_IN_NAME]}"
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, called)])
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(int.from_bytes(secrets.token_bytes(16)) or 1)
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(_NEVER)
        .sign(key, hashes.SHA256())
    )
