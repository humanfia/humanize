"""`hmz.daemon.api.runtimes`: runtimes written, checked and brought in, and what is refused."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from hmz.daemon.api import runtimes
from hmz.rpc import RpcError


@dataclass(frozen=True)
class _Runtime:
    backend: str
    name: str

    def held(self) -> dict[str, Any]:
        return {"backend": self.backend, "name": self.name}


@dataclass(frozen=True)
class _Host:
    alias: str
    host: str


class _Runtimes:
    def __init__(self, *, readable: bool = True) -> None:
        self.held: dict[tuple[str, str], _Runtime] = {}
        self.readable = readable

    def new(self, backend: str, name: str, **fields: Any) -> _Runtime:
        if fields:
            raise ValueError(f"{backend} has no field {', '.join(fields)}")
        return _Runtime(backend, name)

    def add(self, one: _Runtime) -> None:
        if (one.backend, one.name) in self.held:
            raise ValueError(f"There is a {one.backend} runtime called {one.name}.")
        self.held[one.backend, one.name] = one

    def write(self, one: _Runtime) -> None:
        self.held[one.backend, one.name] = one

    def find(self, backend: str, name: str) -> _Runtime | None:
        return self.held.get((backend, name))

    def remove(self, backend: str, name: str) -> None:
        del self.held[backend, name]

    def all(self, backend: str = "") -> list[_Runtime]:
        return [one for one in self.held.values() if backend in {"", one.backend}]

    def check(self, one: _Runtime) -> _Host:
        return _Host(one.name, "reached")

    def hosts(self) -> list[_Host]:
        if not self.readable:
            raise OSError("no such file")
        return [_Host("gpu", "gpu.lab"), _Host("cpu", "cpu.lab")]

    def import_ssh(self, names: list[str], *, update: bool) -> None:
        for name in names:
            if name not in {"gpu", "cpu"}:
                raise ValueError(f"There is no Host {name}.")
            self.held["ssh", name] = _Runtime("ssh", name)


def _hmz(**kw: Any) -> Any:
    return SimpleNamespace(runtimes=_Runtimes(**kw))


def _refused(code: int, call: Any, *args: Any, **kw: Any) -> str:
    with pytest.raises(RpcError) as refused:
        call(*args, **kw)
    assert refused.value.code == code, refused.value.message
    return refused.value.message


def test_a_runtime_is_written_checked_and_removed() -> None:
    hmz = _hmz()

    said = runtimes.write(hmz, "ssh", "gpu", {})
    assert said["runtimes"] == [{"backend": "ssh", "name": "gpu"}]
    assert "slurm" in said["blanks"]
    _refused(400, runtimes.write, hmz, "ssh", "gpu", {})
    assert runtimes.write(hmz, "ssh", "gpu", {}, replace=True)["runtimes"]
    assert runtimes.check(hmz, "ssh", "gpu") == {"alias": "gpu", "host": "reached"}
    assert runtimes.remove(hmz, "ssh", "gpu")["runtimes"] == []
    _refused(404, runtimes.check, hmz, "ssh", "gpu")
    _refused(404, runtimes.remove, hmz, "ssh", "gpu")


def test_the_daemons_own_machine_is_always_listed_and_never_a_runtime() -> None:
    hmz = _hmz()

    said = runtimes.listed(hmz)
    assert said["runtimes"] == []
    assert set(said["local"]) == {"host", "system", "machine", "cpus", "memory"}
    assert said["local"]["host"]
    assert said["local"]["cpus"] > 0
    assert said["local"]["memory"] > 0
    assert runtimes.write(hmz, "ssh", "gpu", {})["local"] == said["local"]
    _refused(404, runtimes.remove, hmz, "local", said["local"]["host"])


def test_what_writing_a_runtime_is_refused() -> None:
    assert _refused(400, runtimes.write, _hmz(), "ssh", "gpu", {"name": "x"}) == (
        "Say name beside fields, not among them."
    )
    _refused(400, runtimes.write, _hmz(), "ssh", "gpu", {"nope": 1})


def test_hosts_are_brought_in_by_name_and_said_saved() -> None:
    hmz = _hmz()

    runtimes.imports(hmz, ["gpu"])

    assert [(one["alias"], one["saved"]) for one in runtimes.hosts(hmz)["hosts"]] == [
        ("gpu", True),
        ("cpu", False),
    ]
    _refused(400, runtimes.imports, hmz, [])
    _refused(400, runtimes.imports, hmz, ["nowhere"])
    assert "could not be read" in _refused(503, runtimes.hosts, _hmz(readable=False))
