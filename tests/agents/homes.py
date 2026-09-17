"""This user's home moved out of the way, for the two agents files whose halves both need it.

Two of the agents tests split across tiers, and each half kept a fixture that puts a home
somewhere temporary: `here` in `tests/{integration,system}/agents/test_agent_fallback.py`, and
`home` in `tests/{integration,system}/agents/test_providers.py`. Both are about the same thing
-- nothing in either file may read or write the home directory of whoever ran the suite -- and
both were copied rather than shared, because the eighteen branches that did the splitting were
told to leave shared modules alone.

`here` is the copy worth naming. It is *autouse*, so nobody asks for it and nothing says it is
missing; a copy that falls behind the other is a test that goes on passing while checking less,
and the only sign is somebody else's `~/.humanize` turning up in an assertion months later.
The body is therefore written once, here, and each half keeps a three-line fixture that calls
it -- which is the shape `tests/logins.py` already uses for the two halves of the login tests,
and for the same reason.

Here rather than in a conftest because these are imported by name, and a conftest is a pytest
plugin rather than a module to import from. A conftest would also be the wrong reach: a
`tests/agents/conftest.py` re-exported into the tier conftests would hand `here` to all
forty-odd agents test files rather than to the one it belongs to, which is a fixture chdir-ing
and re-homing tests that never asked for either.

The fixture itself stays a fixture in each half, because pytest finds one by name: imported
into a module that also names it in a signature, it reads as a redefinition rather than as a
use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.coganchor import backends

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home nothing has written to, and `shell` as a backend of your own.

    What both halves of the fallback tests are run under. The home is moved because a step
    between two places writes down where it steps, and that record belongs to the test rather
    than to whoever ran it; the working directory goes with it because a step is read back out
    of the project it was written in. `shell` is remembered as a CLI of one's own because the
    step under test is one *onto* a named CLI, and `ShellAgent` is what stands in for it.

    Args:
      tmp_path: The test's own directory, which the home is made under.
      monkeypatch: What sets the variable and chdirs, and puts both back however the test ends.
    """
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    backends.remember("shell", ["shell"])


def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home somewhere temporary, with the machine's own sign-in left in it.

    What both halves of the provider tests are run under. A provider answers the paths a CLI
    opens with another account's, so what has to be there to be checked is the account this
    machine is signed in as -- written into the temporary home rather than the real one, so
    that a turn which stopped being redirected reads a credential this file wrote and says so,
    instead of reading the developer's and passing.

    Args:
      tmp_path: The test's own directory, which the home is made under.
      monkeypatch: What sets the variables, and puts them back however the test ends.

    Returns:
      The home, holding a `.claude.json` and a `.claude/.credentials.json` that name this
      machine.
    """
    house = tmp_path / "home"
    (house / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(house))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # What the machine itself is signed in as, which a turn under a provider must never see.
    (house / ".claude.json").write_text('{"account": "the one at this machine"}')
    (house / ".claude" / ".credentials.json").write_text('{"token": "this machine"}')
    return house
