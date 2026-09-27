"""What a broker decides about one meeting, with nothing on the other side of it."""

from __future__ import annotations

from hmz.coganchor.rendezvous import ANCHOR, SERVE, _Pair


def test_both_halves_are_told_one_way_of_joining_however_late_one_answers() -> None:
    """A half the other gave up waiting for is relayed too, rather than told to go direct.

    The half that waited out its patience has been told the session is carried; the late one,
    finding both verdicts in, would otherwise be told it is direct -- and a pair that
    disagrees about how it is joined is a pair one of whose ends waits on nothing.
    """
    pair = _Pair("late")

    first = pair.settle(ANCHOR, direct=True, patience=0.05)
    second = pair.settle(SERVE, direct=True, patience=0.05)

    assert (first, second) == (False, False)
