from __future__ import annotations

from hmz.coganchor import places


def test_every_word_is_distinct() -> None:
    words = [getattr(places, name) for name in places.__all__ if name != "ROADS"]

    assert len(set(words)) == len(words)
    assert all(isinstance(one, str) and one for one in words)


def test_the_roads_are_the_anchor_words() -> None:
    assert places.ROADS == (places.NATIVE_CLI, places.SUPERVISED, places.AFAR)
    assert all(one.startswith("anchor:") for one in places.ROADS)


def test_the_kinds_of_place_are_no_roads() -> None:
    assert {places.REMOTE, places.ISOLATED, places.MANAGED}.isdisjoint(places.ROADS)
