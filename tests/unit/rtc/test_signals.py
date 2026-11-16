"""What is read off a description and signed, and what a missing extra says."""

from __future__ import annotations

import base64
import importlib.util
from typing import Any, cast

import pytest

from hmz.rtc import (
    CHUNK,
    EXTRA,
    LABEL,
    Refused,
    Signals,
    answer,
    device,
    fingerprint,
    offer,
    signed,
)

#: A SHA-256 fingerprint, as a description writes one.
_SHA = ":".join(f"{byte:02X}" for byte in range(32))

#: And another.
_OTHER = ":".join(f"{byte:02x}" for byte in range(32, 64))


def _sdp(*lines: str) -> str:
    return "\r\n".join(["v=0", "o=- 1 1 IN IP4 0.0.0.0", "s=-", *lines, ""])


def test_the_channel_is_the_one_the_protocol_fixes() -> None:
    assert LABEL == "hmz"
    assert CHUNK == 16384


def test_the_sha256_fingerprint_is_read_as_written() -> None:
    sdp = _sdp(
        "m=application 9 UDP/DTLS/SCTP webrtc-datachannel",
        f"a=fingerprint:sha-256 {_SHA}",
        "a=fingerprint:sha-384 AB:CD",
        "m=application 9 UDP/DTLS/SCTP webrtc-datachannel",
        f"a=fingerprint:SHA-256 {_SHA}",
    )
    assert fingerprint(sdp) == _SHA
    assert fingerprint(sdp.replace("\r\n", "\n")) == _SHA


def test_a_description_must_say_exactly_one_fingerprint() -> None:
    with pytest.raises(Refused, match="exactly one"):
        fingerprint(_sdp("a=fingerprint:sha-1 AB:CD"))
    with pytest.raises(Refused, match="exactly one"):
        fingerprint(
            _sdp(f"a=fingerprint:sha-256 {_SHA}", f"a=fingerprint:sha-256 {_OTHER}")
        )
    with pytest.raises(Refused, match="is not a sha-256 fingerprint"):
        fingerprint(_sdp("a=fingerprint:sha-256 AB:CD"))


def test_a_browser_is_known_by_dtls_and_the_base32_of_its_fingerprint() -> None:
    expected = base64.b32encode(bytes(range(32))).decode().rstrip("=").lower()
    assert device(_sdp(f"a=fingerprint:sha-256 {_SHA}")) == f"dtls:{expected}"
    assert len(expected) == 52


def test_the_daemon_signs_both_fingerprints_under_one_context() -> None:
    offered = _sdp(f"a=fingerprint:sha-256 {_SHA}")
    answered = _sdp(f"a=fingerprint:sha-256 {_OTHER}")
    assert signed(offered, answered) == f"hmz-webrtc/1\n{_SHA}\n{_OTHER}".encode()


def test_without_the_extra_a_channel_names_it(monkeypatch: pytest.MonkeyPatch) -> None:
    found = importlib.util.find_spec

    def find(name: str, *rest: Any) -> Any:
        return None if name == "aiortc" else found(name, *rest)

    monkeypatch.setattr(importlib.util, "find_spec", find)
    nowhere = cast("Signals", None)
    with pytest.raises(ModuleNotFoundError, match=r"\[webrtc\]") as raised:
        answer(nowhere, cert=b"", sign=bytes)
    assert str(raised.value) == EXTRA
    with pytest.raises(ModuleNotFoundError, match=r"\[webrtc\]"):
        offer(nowhere, pin="", verify=lambda cert, text, sig: "")
