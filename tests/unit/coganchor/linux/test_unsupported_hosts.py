"""A host the tracing bindings have no register map for is refused as they load, saying why.

Run on every host: each case says what platform and machine it is, and the module is loaded
afresh under that, and put back as it was after.
"""

from __future__ import annotations

import importlib
import platform
import sys
import types
from typing import TYPE_CHECKING

import pytest

import hmz.coganchor.linux

if TYPE_CHECKING:
    from collections.abc import Iterator

SYSCALLS = "hmz.coganchor.linux.syscalls"
NAME = SYSCALLS.rpartition(".")[2]
MISSING = object()


@pytest.fixture(autouse=True)
def afresh() -> Iterator[None]:
    """Loads the bindings anew in each test, and leaves them after as they were before."""
    module = sys.modules.pop(SYSCALLS, MISSING)
    package = hmz.coganchor.linux
    bound: object = getattr(package, NAME, MISSING)
    if bound is not MISSING:
        delattr(package, NAME)
    try:
        yield
    finally:
        sys.modules.pop(SYSCALLS, None)
        if hasattr(package, NAME):
            delattr(package, NAME)
        if isinstance(module, types.ModuleType):
            sys.modules[SYSCALLS] = module
        if bound is not MISSING:
            setattr(package, NAME, bound)


@pytest.mark.parametrize(
    ("system", "machine", "said"),
    [
        ("darwin", "arm64", "Linux virtual machine"),
        ("win32", "AMD64", "Linux virtual machine"),
        ("linux", "riscv64", "register map for aarch64, x86_64"),
        ("linux", "aarch64_be", "'aarch64_be'"),
    ],
)
def test_a_host_without_a_register_map_is_refused(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str, said: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)
    monkeypatch.setattr(platform, "machine", lambda: machine)

    with pytest.raises(RuntimeError, match=said):
        importlib.import_module(SYSCALLS)


@pytest.mark.parametrize("machine", ["x86_64", "aarch64"])
def test_a_supported_machine_loads_its_own_map(
    monkeypatch: pytest.MonkeyPatch, machine: str
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: machine)

    loaded = importlib.import_module(SYSCALLS)

    assert loaded.ARCH.name == machine
    assert loaded.NR is loaded.ARCH.numbers
