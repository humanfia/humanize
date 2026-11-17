"""The proofs a `HELLO` inside TLS carries, as `coganchor` makes and checks them."""

from __future__ import annotations

from hmz.coganchor.tls import Bound

#: The same vectors as `proofs_and_names_are_the_ones_python_makes` in crates/coganchor/src/tls.rs.
COG = "da5949b1478b964693b598f319d55316248da3d9f195c96853f4ba3d3cf79132"
ANCHOR = "4d05cf7df40a6402be008133e936b5fcd85865dbb49c38d4876ffa6099dbba32"


def bound(key: bytes | None = b"k", binding: bytes = bytes([1] * 32)) -> Bound:
    return Bound(binding, key, "tcp://far:1")


def test_the_cogs_proof_is_the_one_coganchor_makes() -> None:
    proof = bound().cog_proof()

    assert proof is not None
    assert proof.hex() == COG


def test_the_anchors_proof_is_held_to_key_binding_and_the_cogs_proof() -> None:
    cog = bytes.fromhex(COG)

    assert bound().anchor_proved(cog, ANCHOR)
    assert bound().anchor_proved(cog, ANCHOR.upper())
    assert not bound(key=b"j").anchor_proved(cog, ANCHOR)
    assert not bound(binding=bytes(32)).anchor_proved(cog, ANCHOR)
    assert not bound().anchor_proved(bytes(32), ANCHOR)


def test_a_missing_or_malformed_proof_proves_nothing() -> None:
    cog = bytes.fromhex(COG)

    for said in (None, "", "zz", 7, ANCHOR[:-2]):
        assert not bound().anchor_proved(cog, said)


def test_without_a_key_there_is_no_proof() -> None:
    assert bound(key=None).cog_proof() is None
    assert not bound(key=None).anchor_proved(b"", ANCHOR)
