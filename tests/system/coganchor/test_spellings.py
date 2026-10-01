"""Every call that names a path, handed the mirror by a name only the target has for it.

An agent may be told its workspace by a spelling this machine has not got: a Mac's
`/private/tmp/...` for a mirror this machine keeps at `/tmp/...`, or -- for a harness on
another machine than its driver -- the workspace's own path, where that harness keeps its
mirror somewhere else entirely. The supervisor puts such a name back onto the mirror before
the call runs. It used to do that only for the calls it already stopped for the mirror's own
sake, so `statfs`, the extended attributes, `inotify_add_watch` and the rest ran against the
name as given, and failed `ENOENT` for a directory that was right there: `df .` in a CLI's
own process, a file watcher on the workspace.

`_spellings_probe.py` makes every one of those calls by number. Here it is run as the agent,
under a real supervisor, once against a stand-in target on this machine, naming the mirror
the Mac way, and once with its harness in one container and its work in another, naming the
workspace by its own path. And after it, what those calls do once stopped: which of them reach
the target, and which leave it alone.
"""

from __future__ import annotations

import errno
import os
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.supervising import WITHOUT_BINDINGS, traced

if (
    WITHOUT_BINDINGS
):  # what is imported below is the binding itself, so it is asked first
    pytest.skip(WITHOUT_BINDINGS, allow_module_level=True)

from hmz.coganchor import AnchorConfig, connect
from hmz.coganchor.linux.syscalls import NR
from hmz.coganchor.proto import spelled_twice
from hmz.runtime.flowing.environing_docker import TRACING
from tests.machines.fixtures import IMAGE
from tests.system.coganchor.probing import NUMBERS, PROBE, check, seed

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.coganchor.fixtures import Anchorage

pytestmark = [traced, pytest.mark.timeout(240)]

#: What a container is labelled with, so a run killed outright leaves something to sweep up.
LABEL = "humanize-spellings"


def test_a_mirror_named_the_way_a_mac_names_it_is_reached_by_every_call(
    anchorage: Anchorage,
) -> None:
    """`/private/tmp/...` for a mirror at `/tmp/...`, which a Mac target hands its agent."""
    if not spelled_twice(str(anchorage.mirror)):
        pytest.skip(f"{anchorage.mirror} is not where a Mac has a second name for")
    seed(anchorage.target)
    hostname = Path("/etc/hostname").read_text().strip()

    result = anchorage.run(
        "python3",
        "-c",
        PROBE,
        f"/private{anchorage.mirror}",
        NUMBERS,
        local_execs=(str(anchorage.mirror / "tool.sh"),),
    )

    assert result.returncode == 0, result.stderr
    check(result.stdout, hostname, hostname)


def test_a_redirected_directory_is_answered_by_every_call_under_an_anchor(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """A provider's credentials under an anchor: every call answers the redirected file."""
    named = tmp_path / "home" / ".claude"
    instead = tmp_path / "provider" / "home"
    instead.mkdir(parents=True)
    seed(instead)

    result = anchorage.run(
        "python3",
        "-c",
        PROBE,
        str(named),
        NUMBERS,
        "--no-programs",
        redirects=((str(named), str(instead)),),
    )

    assert result.returncode == 0, result.stderr
    check(result.stdout)
    assert (instead / "watched.txt").read_text() == "seen\n"
    assert not named.exists()


def _docker(*argv: str) -> str:
    """One docker command, with what it said, for a test that needs it to have worked."""
    done = subprocess.run(
        ["docker", *argv], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, f"docker {' '.join(argv)}: {done.stderr.strip()}"
    return done.stdout.strip()


@pytest.fixture
def containers(daemon: None) -> Iterator[list[str]]:
    """The names of the containers a test starts, every one of them taken down after it."""
    del daemon
    made: list[str] = []
    try:
        yield made
    finally:
        for name in made:
            subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True, check=False
            )


def _machine(made: list[str], *mounted: str, given: tuple[str, ...] = ()) -> str:
    """One container, idling as this user with a home it may write, holding these paths."""
    name = f"hmz-{uuid.uuid4().hex[:10]}"
    _docker(
        "run",
        "--detach",
        f"--name={name}",
        f"--hostname={name}",
        f"--label={LABEL}={os.getuid()}",
        f"--user={os.getuid()}:{os.getgid()}",
        *(f"--volume={path}:{path}" for path in mounted),
        "--env=HOME=/tmp",
        *given,
        IMAGE,
        "sleep",
        "infinity",
    )
    made.append(name)
    return name


def test_a_workspace_named_by_its_own_path_is_reached_by_every_call_under_a_harness_afar(
    tmp_path: Path, containers: list[str], capfd: pytest.CaptureFixture[str]
) -> None:
    """`-H standalone`: the harness in a container that has no such directory at all."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    seed(workspace)
    harness = _machine(containers, given=TRACING)
    work = _machine(containers, str(workspace))

    status = connect(
        ["python3", "-c", PROBE, str(workspace), NUMBERS],
        AnchorConfig(
            harness=f"docker://{harness}",
            target=f"docker://{work}",
            workspace=str(workspace),
            local_execs=(str(workspace / "tool.sh"),),
        ),
    )

    output = capfd.readouterr().out
    assert status == 0, output
    check(output, harness, work)
    # And what the agent made through the workspace's own path is in the workspace.
    assert (workspace / "watched.txt").read_text() == "seen\n"


def test_times_set_through_a_descriptor_reach_the_target(anchorage: Anchorage) -> None:
    """`futimens(fd)` is `utimensat(fd, NULL)`: no path, and the descriptor's file is the one."""
    anchorage.seed({"stamped.txt": "x\n"})
    held = anchorage.mirror / "stamped.txt"

    result = anchorage.run(
        "python3",
        "-c",
        f"import os\nfd = os.open({str(held)!r}, os.O_RDONLY)\n"
        "os.utime(fd, ns=(10**18, 10**18))\n",
    )

    assert result.returncode == 0, result.stderr
    assert (anchorage.target / "stamped.txt").stat().st_mtime_ns == 10**18


def test_a_plain_file_made_by_mknod_reaches_the_target(anchorage: Anchorage) -> None:
    """A node of no kind is a plain file, which crosses as one `creat` made would."""
    result = anchorage.run(
        "python3", "-c", f"import os\nos.mknod({str(anchorage.mirror / 'made')!r})\n"
    )

    assert result.returncode == 0, result.stderr
    assert (anchorage.target / "made").is_file()


def test_a_mode_not_to_follow_a_link_leaves_what_it_points_at_alone(
    anchorage: Anchorage,
) -> None:
    """Replayed, the target's `chmod` would follow the link the call said not to."""
    if NR.FCHMODAT2 < 0:
        pytest.skip("fchmodat2 is not a call this architecture has")
    anchorage.seed({"kept.txt": "x\n"})
    (anchorage.target / "kept.txt").chmod(0o644)
    (anchorage.target / "pointer").symlink_to("kept.txt")
    pointer = os.fsencode(anchorage.mirror / "pointer")
    program = (
        "import ctypes, errno\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        f"done = libc.syscall({NR.FCHMODAT2}, -100, {pointer!r}, 0o600, 0x100)\n"
        "print(errno.errorcode.get(ctypes.get_errno()) if done else 'changed')\n"
    )

    result = anchorage.run("python3", "-c", program)

    assert result.returncode == 0, result.stderr
    refusals = (errno.errorcode[errno.EOPNOTSUPP], errno.errorcode[errno.ENOSYS])
    assert result.stdout.strip() in refusals, result.stdout
    assert (anchorage.target / "kept.txt").stat().st_mode & 0o777 == 0o644


def test_an_attribute_set_before_a_file_is_read_outlasts_its_reading(
    anchorage: Anchorage,
) -> None:
    """The placeholder is replaced whole when its bytes arrive, and its attributes with it."""
    anchorage.seed({"marked.txt": "contents\n"})
    held = str(anchorage.mirror / "marked.txt")
    program = (
        "import errno, os\n"
        f"try:\n    os.setxattr({held!r}, 'user.hmz', b'kept')\n"
        "except OSError as why:\n"
        "    print('unsupported' if why.errno in (errno.ENOTSUP, errno.EPERM) else why)\n"
        "    raise SystemExit\n"
        f"assert open({held!r}).read() == 'contents\\n'\n"
        f"print(os.getxattr({held!r}, 'user.hmz').decode())\n"
    )

    result = anchorage.run("python3", "-c", program)

    assert result.returncode == 0, result.stderr
    if result.stdout.strip() == "unsupported":
        pytest.skip(f"{anchorage.mirror} keeps no user attributes")
    assert result.stdout.strip() == "kept"
