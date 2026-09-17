"""Where a login lands: the backend's own command, run so that what it writes is the provider's.

This is the half of signing in that is a command. Each of these drives a stand-in CLI on PATH
-- a script that writes a file at the path the real one writes its credentials to, because
where that file lands is the one thing a real login would tell us and it would cost a browser
and an account to ask -- and drives it the way a turn does, under the supervisor that answers
every credential path the CLI names with one inside the provider. A machine that will not hand
over a tracee can check none of it: a container without `CAP_SYS_PTRACE` has every module here
and can supervise nothing. Which is what makes these the system tier, the one a gate is meant
to be able to leave out.

The other half is `tests/unit/providers/test_login.py`: what a way in is asked, and what is
written down once it has been answered. That reaches nothing and runs anywhere, and it is not
in this file because a tier is a directory -- left here, it would be left out of the gate
along with the tracer these need.

Nothing here may touch the credentials of whoever is running the suite: this user's home is
moved to `tmp_path` for every test that names one, and every backend's own home variable is
taken out of the environment with it.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends
from hmz.coganchor.providers import login
from tests import logins
from tests.logins import way
from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path


#: A stand-in for `claude auth login`: what a login leaves behind, without the browser.
CLAUDE_LOGIN = """\
import json, os, sys

home = os.environ["HOME"]
os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
with open(os.path.join(home, ".claude", ".credentials.json"), "w") as landed:
    json.dump({"argv": sys.argv[1:], "signed": "the provider"}, landed)
# At a path nothing answers for, so that it says the stand-in ran at all.
open(os.environ["STAND_IN_RAN"], "w").write("ran")
"""

#: A stand-in for `codex login --with-api-key`, which reads the key off its own stdin.
CODEX_KEY = """\
import json, os, sys

key = sys.stdin.readline().strip()
home = os.environ["HOME"]
os.makedirs(os.path.join(home, ".codex"), exist_ok=True)
with open(os.path.join(home, ".codex", "auth.json"), "w") as landed:
    json.dump({"argv": sys.argv[1:], "key": key}, landed)
"""

#: A stand-in for `opencode auth login <url>`, whose home is under the one every program shares.
OPENCODE_LOGIN = """\
import json, os, sys

at = os.path.join(os.environ["HOME"], ".local", "share", "opencode")
os.makedirs(at, exist_ok=True)
with open(os.path.join(at, "auth.json"), "w") as landed:
    json.dump({"argv": sys.argv[1:]}, landed)
"""


def stand_in(monkeypatch: pytest.MonkeyPatch, at: Path, name: str, script: str) -> Path:
    """Puts a program of that name first on PATH, which is what a way in then runs.

    Args:
      monkeypatch: What puts it on PATH, and takes it off again afterwards.
      at: The directory to keep it in.
      name: What the backend is called, since a way in runs the backend.
      script: The Python the stand-in is.

    Returns:
      The program.
    """
    at.mkdir(parents=True, exist_ok=True)
    program = at / name
    program.write_text(f"#!{sys.executable}\n{script}")
    program.chmod(0o755)
    monkeypatch.setenv("PATH", f"{at}{os.pathsep}{os.environ['PATH']}")
    return program


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home somewhere temporary, and a mark the stand-ins say they ran at.

    At a path nothing a provider answers for, so that a stand-in which was never spawned is
    told from one that ran and wrote nowhere.
    """
    at = logins.house(tmp_path, monkeypatch)
    monkeypatch.setenv("STAND_IN_RAN", str(tmp_path / "ran"))
    return at


# ------------------------------------------------------------- what signs in


@traced
@pytest.mark.timeout(60)
def test_what_a_login_writes_lands_in_the_provider_and_not_in_this_home(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole errand: the CLI writes the path it always writes, and the provider gets it."""
    stand_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE_LOGIN)
    provider = login.make("claude", "mine", way("claude", "login"))

    assert login.sign_in(provider, way("claude", "login")) == 0

    landed = json.loads((provider.at / "home" / ".credentials.json").read_text())
    assert landed == {"argv": ["auth", "login"], "signed": "the provider"}
    assert (tmp_path / "ran").exists(), "the stand-in never ran"
    # The home itself is the CLI's own and is left where it is; what moved is the credential.
    assert not (house / ".claude" / ".credentials.json").exists()
    assert not (house / ".claude.json").exists()


@traced
@pytest.mark.timeout(60)
def test_a_key_read_off_stdin_lands_in_the_backends_own_store_inside_the_provider(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command is fed what it was told to be fed, and keeps it where it keeps its own."""
    stand_in(monkeypatch, tmp_path / "bin", "codex", CODEX_KEY)
    answers = {"OPENAI_API_KEY": "sk-not-a-real-key"}
    provider = login.make("codex", "mine", way("codex", "key"), answers)

    assert login.sign_in(provider, way("codex", "key"), answers) == 0

    landed = json.loads((provider.at / "home" / "auth.json").read_text())
    assert landed == {"argv": ["login", "--with-api-key"], "key": "sk-not-a-real-key"}
    assert not (house / ".codex" / "auth.json").exists()
    assert dict(provider.env) == {}  # and the key itself is written down nowhere


@traced
@pytest.mark.timeout(60)
def test_an_answer_a_way_puts_in_its_own_command_line_is_filled_in(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And a home under the directory every program shares is answered like any other."""
    stand_in(monkeypatch, tmp_path / "bin", "opencode", OPENCODE_LOGIN)
    answers = {"OPENCODE_WELLKNOWN": "https://example.invalid/gateway"}
    provider = login.make("opencode", "mine", way("opencode", "wellknown"), answers)

    assert login.sign_in(provider, way("opencode", "wellknown"), answers) == 0

    landed = json.loads((provider.at / "home" / "auth.json").read_text())
    assert landed == {"argv": ["auth", "login", "https://example.invalid/gateway"]}
    assert not (house / ".local" / "share" / "opencode" / "auth.json").exists()
    assert dict(provider.env) == {}  # the URL is the command's, not the turn's


@traced
@pytest.mark.timeout(60)
def test_the_status_a_way_in_came_to_is_the_status_of_signing_in(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A login that was refused is a provider that is written down and not signed in."""
    stand_in(monkeypatch, tmp_path / "bin", "claude", "import sys\nsys.exit(3)\n")
    provider = login.make("claude", "mine", way("claude", "login"))

    assert login.sign_in(provider, way("claude", "login")) == 3
    assert not (provider.at / "home" / ".credentials.json").exists()


@traced
@pytest.mark.timeout(60)
def test_a_backend_that_is_not_installed_is_a_login_that_did_not_happen(
    house: Path,
) -> None:
    """Rather than a provider that looks signed in: what it comes to is what could not run."""
    missing = backends.Way(
        name="nowhere",
        about="a backend nobody has installed",
        argv=("hmz-no-such-backend",),
    )
    provider = login.make("kimi", "mine", missing)

    assert login.sign_in(provider, missing) != 0
    assert not list((provider.at / "home").iterdir())
