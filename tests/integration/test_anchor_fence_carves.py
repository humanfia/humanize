"""What a fence carves out of a grant, held around a real program by `hmz internal fence`.

The workdir is written and the system read, but beneath the workdir one directory is kept out
of reach and another kept to reading. The program is this Python, walled in by Seatbelt on a
Mac or by Landlock on Linux -- where a directory holding a carve-out is granted entry by entry,
so that what is there beforehand is all that is written -- and by bubblewrap where it starts,
which mounts an empty directory over what is kept out of reach.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.fence import BWRAP, NONE, READ, WRITE, Fence, able, enforceable

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    not enforceable(net=False), reason="this machine has nothing to fence with"
)


#: Each backend this machine can put a fence up with: the one it chooses for itself, and
#: bubblewrap where it starts here.
BACKENDS = [
    "auto",
    pytest.param(
        "bwrap",
        marks=pytest.mark.skipif(
            sys.platform != "linux" or not able(BWRAP)[0],
            reason="this machine has no bwrap that starts",
        ),
    ),
]


_TRIES = """
import json, os, sys

w = sys.argv[1]


def tried(how):
    try:
        how()
    except OSError:
        return False
    return True


def write(name):
    with open(os.path.join(w, name), "w") as file:
        file.write("changed")


def read(name):
    with open(os.path.join(w, name)) as file:
        file.read()


def made():
    write("new")


def moved():
    os.rename(os.path.join(w, "secret"), os.path.join(w, "moved"))


def linked():
    os.link(os.path.join(w, "secret", "key"), os.path.join(w, "ro", "key"))


print(json.dumps({
    "write ok": tried(lambda: write("ok")),
    "read secret": tried(lambda: read("secret/key")),
    "list secret": tried(lambda: os.listdir(os.path.join(w, "secret"))),
    "write ro": tried(lambda: write("ro/notes")),
    "read ro": tried(lambda: read("ro/notes")),
    "make new": tried(made),
    "move secret": tried(moved),
    "link secret": tried(linked),
}))
"""


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    "granted",
    [
        pytest.param([("/", READ), (".", WRITE)], id="workspace"),
        # Everything written, the scratch reached through the links on the way to it.
        pytest.param([("/", WRITE)], id="everything"),
    ],
)
def test_a_fence_holds_what_it_carves_out_of_the_workdir(
    tmp_path: Path, granted: list[tuple[str, str]], backend: str
) -> None:
    work = tmp_path.resolve() / "work"
    (work / "secret").mkdir(parents=True)
    (work / "ro").mkdir()
    (work / "secret" / "key").write_text("key")
    (work / "ro" / "notes").write_text("notes")
    (work / "ok").write_text("ok")
    fence = Fence.of(
        rules=[*granted, ("./secret", NONE), ("./ro", READ)],
        online=True,
        workdir=work,
        home=tmp_path.resolve() / "home",
    )

    done = subprocess.run(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "internal",
            "fence",
            f"--policy={fence.dumps()}",
            f"--sandbox={backend}",
            "--",
            sys.executable,
            "-I",
            "-c",
            _TRIES,
            str(work),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=work,
    )

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "write ok": True,
        "read secret": False,
        # Bubblewrap keeps it out of reach by mounting an empty directory over it.
        "list secret": backend == "bwrap",
        "write ro": False,
        "read ro": True,
        # Seatbelt and bubblewrap carve out of a grant; Landlock grants what was there,
        # entry by entry.
        "make new": sys.platform == "darwin" or backend == "bwrap",
        "move secret": False,
        "link secret": False,
    }
    assert (work / "ok").read_text() == "changed"
    assert (work / "ro" / "notes").read_text() == "notes"
    assert (work / "secret" / "key").read_text() == "key"
