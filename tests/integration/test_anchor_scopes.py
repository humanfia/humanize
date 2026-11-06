"""A Landlock ruleset applied for real, in a child that restricts itself and checks what it may do.

Each check runs in a subprocess of its own: restricting is irreversible, and only the thread that
asks is restricted.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import uuid
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.linux.landlock import abi

if TYPE_CHECKING:
    from pathlib import Path

SCOPED = """
import os, socket, sys
from hmz.coganchor.linux.landlock import Ruleset

Ruleset(read=("/",)).restrict_self()
os.kill(os.getpid(), 0)
inside = socket.socket(socket.AF_UNIX)
inside.bind("\\0" + sys.argv[2] + "-inside")
inside.listen()
with socket.socket(socket.AF_UNIX) as client:
    client.connect("\\0" + sys.argv[2] + "-inside")
try:
    os.kill(int(sys.argv[1]), 0)
except PermissionError:
    pass
else:
    raise AssertionError("signal reached a process outside the scope")
with socket.socket(socket.AF_UNIX) as client:
    try:
        client.connect("\\0" + sys.argv[2])
    except PermissionError:
        pass
    else:
        raise AssertionError("connected to an abstract socket outside the scope")
"""

#: A Python built without `os.O_PATH`, which some are: the kernel still has it.
WITHOUT_O_PATH = """
import os, sys
del os.O_PATH
from hmz.coganchor.linux.landlock import Ruleset

Ruleset(read=("/",), write=(sys.argv[1],)).restrict_self()
with open(os.path.join(sys.argv[1], "written"), "w") as file:
    file.write("ok")
try:
    open("/written", "w")
except PermissionError:
    pass
else:
    raise AssertionError("wrote outside the ruleset")
"""


def _run(script: str, *argv: str) -> None:
    done = subprocess.run(
        [sys.executable, "-c", script, *argv],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert done.returncode == 0, done.stderr


@pytest.mark.skipif(abi() < 6, reason="needs Landlock scopes (ABI 6)")
def test_a_ruleset_keeps_signals_and_abstract_sockets_inside_it() -> None:
    """The same operations succeed inside the scope and fail across its boundary."""
    name = f"hmz-scope-{uuid.uuid4().hex}"
    with socket.socket(socket.AF_UNIX) as outside:
        outside.bind("\0" + name)
        outside.listen()
        _run(SCOPED, str(os.getpid()), name)


@pytest.mark.skipif(abi() < 1, reason="needs Landlock")
def test_a_ruleset_is_applied_by_a_python_without_o_path(tmp_path: Path) -> None:
    _run(WITHOUT_O_PATH, str(tmp_path))
