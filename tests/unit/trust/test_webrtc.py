"""`hmz.trust.webrtc`: the daemon's signature over both DTLS fingerprints."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from cryptography import x509

from hmz.trust import identity, webrtc
from tests.unit.trust.doubles_trust import device

if TYPE_CHECKING:
    from pathlib import Path

OFFER = ":".join(["AB"] * 32)
ANSWER = ":".join(["cd"] * 32)

SDP = (
    "v=0\r\n"
    "o=- 1 2 IN IP4 127.0.0.1\r\n"
    "a=fingerprint:sha-512 " + ":".join(["EE"] * 64) + "\r\n"
    "m=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n"
    f"a=fingerprint:sha-256 {OFFER}\r\n"
)


def test_the_fingerprint_is_read_as_written() -> None:
    assert webrtc.fingerprint_in(SDP) == OFFER
    assert webrtc.fingerprint_in(f"a=fingerprint:SHA-256 {ANSWER}\n") == ANSWER


def test_a_description_without_one_is_refused() -> None:
    with pytest.raises(ValueError, match="sha-256"):
        webrtc.fingerprint_in("v=0\r\n")


def test_an_answer_signed_by_the_pinned_daemon_verifies() -> None:
    daemon = identity.device()
    said = webrtc.signs(daemon, OFFER, ANSWER)
    assert set(said) == {"cert", "sig"}
    shown = x509.load_der_x509_certificate(base64.b64decode(said["cert"]))
    assert identity.fingerprint(shown) == daemon.fingerprint
    signature = base64.urlsafe_b64decode(said["sig"] + "=" * (-len(said["sig"]) % 4))
    assert "=" not in said["sig"]
    assert identity.verifies(
        shown, f"hmz-webrtc/1\n{OFFER}\n{ANSWER}".encode(), signature
    )
    assert webrtc.answered(said["cert"], said["sig"], OFFER, ANSWER, daemon.fingerprint)


def test_an_answer_is_refused_for_another_daemon_or_offer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = identity.device()
    other = device(tmp_path / "other", monkeypatch)
    said = webrtc.signs(daemon, OFFER, ANSWER)
    assert not webrtc.answered(
        said["cert"], said["sig"], OFFER, ANSWER, other.fingerprint
    )
    assert not webrtc.answered(
        said["cert"], said["sig"], ANSWER, ANSWER, daemon.fingerprint
    )
    assert not webrtc.answered(
        said["cert"], said["sig"], OFFER, OFFER, daemon.fingerprint
    )
    forged = webrtc.signs(other, OFFER, ANSWER)
    assert not webrtc.answered(
        said["cert"], forged["sig"], OFFER, ANSWER, daemon.fingerprint
    )
    assert not webrtc.answered("!!", said["sig"], OFFER, ANSWER, daemon.fingerprint)
    assert not webrtc.answered("AAAA", said["sig"], OFFER, ANSWER, daemon.fingerprint)


def test_a_browser_is_known_by_its_offers_fingerprint() -> None:
    known = webrtc.device(OFFER)
    assert known == "dtls:" + identity.base32(bytes([0xAB] * 32))
    assert len(known) == 5 + 52
    with pytest.raises(ValueError, match="32 bytes"):
        webrtc.device("AB:CD")
