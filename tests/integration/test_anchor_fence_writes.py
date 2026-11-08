"""What a fence writes, reached and checked where it is put up again.

An agent writes the directory its scratch is in -- the temporary directory a workdir it writes
brings with it, or as here, a state directory of its own -- and so may put its scratch aside
in one turn and leave a link out of the wall at its name. Each test runs the agent for real,
under `hmz internal fence` or walled in by the supervisor that traces it, for two turns of the
same fence: the second is where a grant made by name would follow that link.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.fence import NONE, READ, Fence, enforceable, landlocked
from hmz.coganchor.providers import redirect

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    not enforceable(net=False), reason="this machine has nothing to fence with"
)


def _turn(
    put_up: str, fence: Fence, work: Path, script: str
) -> subprocess.CompletedProcess[str]:
    """One turn of an agent that is this Python running `script`, inside the fence."""
    if put_up == "wrapper":
        around = ["internal", "fence", f"--policy={fence.dumps()}", "--"]
    else:
        around = [
            "internal",
            "anchor",
            "--target",
            "local",
            "--workspace",
            str(work),
            f"--fence={fence.dumps()}",
        ]
    return subprocess.run(
        [sys.executable, "-Pm", "hmz", *around, sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=work,
    )


@pytest.mark.parametrize(
    "put_up",
    [
        "wrapper",
        pytest.param(
            "supervisor",
            marks=pytest.mark.skipif(
                not landlocked(net=False) or not redirect.supervises(),
                reason="this machine supervises nothing",
            ),
        ),
    ],
)
def test_a_scratch_swapped_for_a_link_out_is_refused_where_the_fence_is_put_up_again(
    tmp_path: Path, put_up: str
) -> None:
    tmp_path = tmp_path.resolve()
    home, work, state = tmp_path / "home", tmp_path / "work", tmp_path / "state"
    for one in (home, work, state):
        one.mkdir()
    scratch = state / "scratch"
    # The workdir read, the home kept out, and written only what the agent keeps of its own:
    # its state, and its scratch in it.
    fence = dataclasses.replace(
        Fence.of(
            local=READ, user=NONE, system=NONE, online=True, workdir=work, home=home
        ).granting(write=[state]),
        tmp=str(scratch),
    )
    swapped = _turn(
        put_up,
        fence,
        work,
        f"import os; os.rename({str(scratch)!r}, {str(state / 'aside')!r}); "
        f"os.symlink({str(home)!r}, {str(scratch)!r})",
    )
    if sys.platform == "darwin":
        # Seatbelt lets no directory it writes be taken from its name, nor any root be made
        # a link; one is put there as a fence from before that, or a program outside any,
        # could have left it.
        assert swapped.returncode != 0
        assert scratch.is_dir()
        assert not scratch.is_symlink()
        scratch.rename(state / "aside")
        scratch.symlink_to(home)
    else:
        assert swapped.returncode == 0, swapped.stderr

    # The next turn's fence reaches its scratch through no link a fenced program could have
    # made: refused before anything runs, and nothing written into the home.
    said = _turn(put_up, fence, work, f"open({str(scratch / 'x')!r}, 'w').write('x')")

    assert said.returncode != 0
    assert "a link where a fenced program could have made one" in said.stderr
    assert not (home / "x").exists()


#: What a program inside a Seatbelt profile tries of the roots it writes, directories `d` and
#: `e` and a file `f`, with `out` beside them unwritten: whether each attempt went through, in
#: order.
_SWAPS = """
import ctypes, json, os, shutil, sys
d, e, f, out = sys.argv[1:]
libc = ctypes.CDLL(None, use_errno=True)
def tried(how):
    try:
        how()
    except OSError:
        return False
    return True
def swapped_dir():
    os.symlink(out, os.path.join(d, "s"))
    RENAME_SWAP = 2
    if libc.renamex_np(os.path.join(d, "s").encode(), e.encode(), RENAME_SWAP):
        raise OSError(ctypes.get_errno(), "renamex_np")
def relinked_dir():
    shutil.rmtree(d)
    os.symlink(out, d)
def relinked_file():
    os.unlink(f)
    os.symlink(os.path.join(out, "secret"), f)
def renamed_link():
    os.symlink(os.path.join(out, "secret"), os.path.join(d, "l"))
    os.replace(os.path.join(d, "l"), f)
def saved():
    with open(os.path.join(d, "t"), "w") as t:
        t.write("saved")
    os.replace(os.path.join(d, "t"), f)
def inside():
    os.mkdir(os.path.join(d, "sub"))
    os.symlink(out, os.path.join(d, "sub", "l"))
    os.unlink(os.path.join(d, "sub", "l"))
    os.rmdir(os.path.join(d, "sub"))
hows = (saved, inside, renamed_link, relinked_file, swapped_dir, relinked_dir)
print(json.dumps({how.__name__: tried(how) for how in hows}))
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is a Mac's")
def test_a_root_a_seatbelt_profile_writes_cannot_be_swapped_for_a_link(
    tmp_path: Path,
) -> None:
    from hmz.coganchor.darwin import seatbelt

    if not seatbelt.available():
        pytest.skip("this Mac is already inside a sandbox")
    tmp_path = tmp_path.resolve()
    d, e, f, out = (tmp_path / name for name in ("d", "e", "f", "out"))
    d.mkdir()
    e.mkdir()
    out.mkdir()
    f.write_text("kept")
    (out / "secret").write_text("secret")
    profile = seatbelt.Profile(read=("/",), write=(str(d), str(e), str(f)))

    done = subprocess.run(
        profile.command(
            [sys.executable, "-I", "-B", "-c", _SWAPS, *map(str, (d, e, f, out))]
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    # Neither root can be left a link out of the wall for the next profile to grant, and a
    # file root can still be saved over atomically, as editors and CLIs save.
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "saved": True,
        "inside": True,
        "renamed_link": False,
        "relinked_file": False,
        "swapped_dir": False,
        "relinked_dir": False,
    }
    assert not d.is_symlink()
    assert not e.is_symlink()
    assert not f.is_symlink()
    assert (out / "secret").read_text() == "secret"
