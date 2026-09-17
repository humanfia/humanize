"""What a machine test needs and cannot make for itself: a daemon holding the image.

The tests are under `tests/integration/machines/` and `tests/system/machines/`; this stays
here, outside both, because the image's name is wanted on either side of that line -- a system
test starts a container of it, and an integration test names it in a setting it never brings
up. Shared rather than written out twice so that the skip a machine without docker gets is
worded once: a second copy that drifted would be a container test reporting failure on a
machine that simply has no daemon running. `tests/system/machines/conftest.py` re-exports the
fixture to the tests that want one.
"""

from __future__ import annotations

import subprocess

import pytest

#: Small, and has the `python3` a target needs. Pulled by hand rather than by the test, so a
#: machine without it skips instead of spending a minute on a download.
IMAGE = "python:3.12-slim"


@pytest.fixture
def daemon() -> None:
    """A docker daemon holding the image, or a skip: these tests run a container for real."""
    try:
        ready = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
        )
    except OSError as reason:
        pytest.skip(f"needs the docker command: {reason}")
    if ready.returncode != 0:
        pytest.skip(f"needs a docker daemon holding {IMAGE}")
