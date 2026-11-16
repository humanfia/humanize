"""The OpenRPC document an install reads is the protocol's, byte for byte."""

from importlib import resources
from pathlib import Path

from hmz.rpc import PROTOCOL, document

PROTOCOL_DOCUMENT = Path(__file__).resolve().parents[3] / "protocol" / "openrpc.json"


def test_the_packaged_copy_is_the_protocols() -> None:
    packaged = resources.files("hmz.rpc").joinpath("openrpc.json").read_bytes()
    assert packaged == PROTOCOL_DOCUMENT.read_bytes(), (
        "copy protocol/openrpc.json to src/hmz/rpc/openrpc.json"
    )


def test_the_document_is_of_this_protocol_version() -> None:
    assert document()["info"]["version"] == PROTOCOL
    assert document() is document()
