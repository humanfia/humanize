"""Whether the sampler can be run on the machine running the suite.

:mod:`hmz.runtime.tracing.profile` watches what a run started by asking the operating system about
every process under this one, a hundred times a second. On macOS under Python 3.13 doing that
wedges the whole interpreter: the call it is inside does not come back and does not let another
thread run either, so not even pytest's own per-test ceiling can end it. A run reaches the wall
having said nothing, which is the one outcome a ceiling exists to prevent.

On the other Pythons a Mac is not dependable either: 3.12 and 3.14 were seen hanging here about
one run in three, and on CI's macOS runners a sampler that did come back has missed a shell that
lived a whole second -- a red build about the runner rather than the change, on the gate in
front of `main`. So every Mac is left out, and this is what is known rather than the whole of
what is wrong: a thing to fix rather than a platform that cannot have it. The same file runs in
two seconds on Linux, where CI runs it on every Python, and profiling is off unless a run asks
for it. Written down here rather than as a bare `skipif` in two files so that there is one place
saying what is known and one place to delete when it is fixed.
"""

from __future__ import annotations

import sys

import pytest

#: Where the sampler cannot be relied on to start and come back.
WEDGES = sys.platform == "darwin"

#: The mark for a test that starts one.
sampled = pytest.mark.skipif(
    WEDGES,
    reason="the sampler wedges or misses processes on macOS -- see tests/sampling.py",
)
