"""The frames the socket between a workspace's runs and whatever reads them carries.

A stream socket hands back whatever has arrived, which is half a frame as often as it is two,
so what is checked here is that what went in comes out whole however it was cut up -- and that
a length no frame of this protocol has is refused rather than waited for.
"""

from __future__ import annotations

import pytest

from hmz.daemon import proto


def test_a_frame_comes_back_as_it_went_in() -> None:
    frames = proto.Frames()

    said = list(frames.feed(proto.frame(proto.MESSAGE, b"hello")))

    assert said == [(proto.MESSAGE, b"hello")]


def test_two_frames_in_one_read_are_two_frames() -> None:
    frames = proto.Frames()
    both = proto.frame(proto.MESSAGE, b"a") + proto.frame(proto.MESSAGE, b"bc")

    assert list(frames.feed(both)) == [(proto.MESSAGE, b"a"), (proto.MESSAGE, b"bc")]


def test_a_frame_cut_in_half_is_held_until_the_rest_arrives() -> None:
    frames = proto.Frames()
    whole = proto.frame(proto.MESSAGE, b"a message")

    for at in range(len(whole) - 1):
        assert list(frames.feed(whole[at : at + 1])) == []
    assert list(frames.feed(whole[-1:])) == [(proto.MESSAGE, b"a message")]


def test_a_frame_handed_over_is_not_handed_over_again() -> None:
    """A frontend told the runs let go of it stops reading, and must not be told twice."""
    frames = proto.Frames()
    both = proto.frame(proto.MESSAGE, b"one") + proto.frame(proto.GONE, b"over")

    for kind, _payload in frames.feed(both):
        if kind == proto.GONE:
            break  # as a frontend that has been let go of does

    assert list(frames.feed(b"")) == []
    assert list(frames.feed(proto.frame(proto.MESSAGE, b"two"))) == [
        (proto.MESSAGE, b"two")
    ]


def test_what_is_left_over_is_kept_and_what_was_whole_is_not() -> None:
    """Two frames and a piece of a third, which is what a read off a busy socket is."""
    frames = proto.Frames()
    said = (
        proto.frame(proto.MESSAGE, b"one")
        + proto.frame(proto.MESSAGE, b"two")
        + proto.frame(proto.MESSAGE, b"three")[:5]
    )

    assert list(frames.feed(said)) == [
        (proto.MESSAGE, b"one"),
        (proto.MESSAGE, b"two"),
    ]
    assert list(frames.feed(proto.frame(proto.MESSAGE, b"three")[5:])) == [
        (proto.MESSAGE, b"three")
    ]


def test_an_empty_payload_is_a_frame() -> None:
    """`GONE` carries a reason, which may be nothing at all."""
    frames = proto.Frames()

    assert list(frames.feed(proto.frame(proto.GONE))) == [(proto.GONE, b"")]


def test_a_length_no_frame_of_this_has_is_refused() -> None:
    """A socket carrying something else is a socket to close, not one to allocate for."""
    frames = proto.Frames()

    with pytest.raises(ValueError, match="not one of these"):
        list(frames.feed(proto.MESSAGE + b"\xff\xff\xff\xff"))


def test_a_mapping_goes_and_comes_back() -> None:
    said = proto.spoken(proto.CONTROL, {"do": "status"})
    frames = proto.Frames()

    ((kind, payload),) = frames.feed(said)

    assert kind == proto.CONTROL
    assert proto.asked(payload) == {"do": "status"}


@pytest.mark.parametrize("payload", [b"", b"not json", b"[1, 2]", b"\xff"])
def test_anything_that_is_not_a_mapping_reads_as_nothing_said(payload: bytes) -> None:
    """A frame from something that is not this is answered rather than raised about."""
    assert proto.asked(payload) == {}


def test_a_message_is_one_json_object_a_frame_either_way() -> None:
    """What a frontend and a host say to each other: a request in, a message out."""
    said = {"type": "event", "seq": 7, "text": "hello", "tokens": {"m": 3}}
    frames = proto.Frames()

    ((kind, payload),) = frames.feed(proto.spoken(proto.MESSAGE, said))

    assert kind == proto.MESSAGE
    assert proto.asked(payload) == said


def test_each_kind_is_a_kind_of_its_own() -> None:
    """A frontend's frame, a question and a letting go are told apart by their kind alone."""
    kinds = [proto.MESSAGE, proto.GONE, proto.CONTROL]
    assert len(set(kinds)) == len(kinds)
    assert not {"HELLO", "INPUT", "OUTPUT", "RESIZE"} & set(proto.__all__)


def test_the_version_beside_a_host_is_the_one_its_frontends_are_welcomed_with() -> None:
    """One protocol, said in two places: the note beside the socket, and the welcome."""
    from hmz.runtime.doing import hosting

    assert proto.PROTOCOL == hosting.PROTOCOL
