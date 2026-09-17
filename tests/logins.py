"""This user's home moved out of the way, and the ways in, for both halves of the login tests.

Signing in is checked in two places, because it is two things. What a way in is asked and what
is written down once it has been answered reaches nothing, and is
`tests/unit/providers/test_login.py`; the command a backend runs to sign in needs a machine
that will hand over a tracee, and is `tests/system/providers/test_login.py`. Two directories,
so that a gate which cannot count on a tracer can leave the second out and still run the first.

What they share is the fixture neither may be without: the one that moves this user's home
somewhere temporary. Copied into both, the copy that fell behind the other would be a test
writing a real credential into the home directory of whoever ran the suite, and the suite would
be green either way.

Here rather than in a conftest because a conftest is a pytest plugin rather than a module to
import from, and the two halves are no longer under one directory to put a conftest in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.coganchor import backends
from hmz.coganchor.providers import login

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def way(cli: str, name: str) -> backends.Way:
    """The way in of that name, which every test that asks for one names one there is.

    Args:
      cli: The backend that offers it.
      name: What that backend calls it.

    Returns:
      The way in, the test having failed outright where the backend offers no such thing.
    """
    found = login.way_of(cli, name)
    assert found is not None, f"{cli} offers no way in called {name!r}"
    return found


def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Moves this user's home somewhere temporary, and every backend's own home with it.

    Nothing in either half may read or write the real one: a login writes a credential, and a
    provider made without this would write it where the person running the suite keeps theirs.

    Args:
      tmp_path: The test's own directory, which the home is made under.
      monkeypatch: What sets the variables, and puts them back however the test ends.

    Returns:
      The home, which is empty.
    """
    at = tmp_path / "house"
    at.mkdir()
    monkeypatch.setenv("HOME", str(at))
    for profile in backends.PROFILES:
        monkeypatch.delenv(profile.home_var, raising=False)
    return at
