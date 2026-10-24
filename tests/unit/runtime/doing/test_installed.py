"""`hmz.runtime.doing.installed`: which agents are installed, which can be added."""

from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.runtime.doing import installed as discover

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.runtime.doing.accounts import Accounts


@dataclass
class _Profile:
    name: str


@dataclass
class _Accounts:
    known: dict[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )

    def models(self, backend: str) -> tuple[str, ...]:
        return self.known.get(backend, ())


@dataclass
class _World:
    """What the machine has, as `hmz.coganchor` and the accounts would say it."""

    profiles: list[str] = field(default_factory=list[str])
    programs: set[str] = field(default_factory=set[str])
    speaking: dict[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )
    modules: set[str] = field(default_factory=set[str])
    accounts: _Accounts = field(default_factory=_Accounts)

    @property
    def catalogue(self) -> Accounts:
        """The accounts, as what is installed is asked of them: for what each backend runs."""
        return cast("Accounts", self.accounts)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> _World:
    held = _World()
    known = importlib.util.find_spec

    def find_spec(name: str, package: str | None = None) -> Any:
        if name in {"deepseek_harness", "dotenv", "websockets", "litellm"}:
            return object() if name in held.modules else None
        return known(name, package)

    monkeypatch.setattr(
        discover, "profiles", lambda: tuple(_Profile(one) for one in held.profiles)
    )

    def named(backend: str) -> _Profile | None:
        return _Profile(backend) if backend in held.profiles else None

    def program(command: str) -> str | None:
        return f"/bin/{command}" if command in held.programs else None

    monkeypatch.setattr(discover, "named", named)
    monkeypatch.setattr(discover, "program", program)
    monkeypatch.setattr(discover, "speaking", lambda: held.speaking)
    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    return held


def test_nothing_installed_is_nothing_found(world: _World) -> None:
    world.profiles = ["claude", "codex"]

    assert discover.installed(world.catalogue) == {}


def test_a_backend_whose_program_is_here_is_installed_with_its_models(
    world: _World,
) -> None:
    world.profiles = ["claude", "codex"]
    world.programs = {"claude"}
    world.accounts.known = {"claude": ("opus", "sonnet")}

    assert discover.installed(world.catalogue) == {"claude": ("opus", "sonnet")}


def test_a_backend_never_asked_is_installed_with_nothing_in_it(world: _World) -> None:
    world.profiles = ["codex"]
    world.programs = {"codex"}

    assert discover.installed(world.catalogue) == {"codex": ()}


def test_a_cli_somebody_added_is_found_by_the_command_they_gave(world: _World) -> None:
    world.profiles = ["mine"]
    world.speaking = {"mine": ("my-agent", "--serve")}
    world.programs = {"my-agent"}

    assert "mine" in discover.installed(world.catalogue)


def test_a_cli_added_with_no_command_is_not_installed(world: _World) -> None:
    world.profiles = ["mine"]
    world.speaking = {"mine": ()}
    world.programs = {"mine"}

    assert discover.installed(world.catalogue) == {}


@pytest.mark.parametrize(
    ("backend", "modules", "found"),
    [
        ("kimi", set[str](), False),
        ("kimi", {"websockets"}, True),
        ("dsh", {"deepseek_harness"}, False),
        ("dsh", {"deepseek_harness", "dotenv"}, True),
        ("litellm", {"litellm"}, True),
        ("litellm", set[str](), False),
    ],
)
def test_a_backend_with_an_extra_needs_the_whole_of_it(
    world: _World, backend: str, modules: set[str], found: bool
) -> None:
    world.profiles = [backend]
    world.programs = {backend}
    world.modules = modules

    assert (backend in discover.installed(world.catalogue)) is found


def test_dsh_and_litellm_need_no_program(world: _World) -> None:
    world.profiles = ["dsh", "litellm"]
    world.modules = {"deepseek_harness", "dotenv", "litellm"}

    assert set(discover.installed(world.catalogue)) == {"dsh", "litellm"}


def test_an_optional_backend_missing_its_extra_is_installable(world: _World) -> None:
    world.programs = {"kimi"}
    world.accounts.known = {"kimi": ("k2",), "dsh": ("v3",)}

    assert discover.installable(world.catalogue) == {
        "dsh": ("v3",),
        "kimi": ("k2",),
        "litellm": (),
    }


def test_an_optional_backend_without_its_program_is_not_installable(
    world: _World,
) -> None:
    assert "kimi" not in discover.installable(world.catalogue)


def test_an_optional_backend_with_its_extra_is_not_installable(world: _World) -> None:
    world.programs = {"kimi"}
    world.modules = {"websockets", "litellm", "deepseek_harness", "dotenv"}

    assert discover.installable(world.catalogue) == {}


@pytest.mark.parametrize(("backend", "ready"), [("claude", True), ("litellm", False)])
def test_a_cli_is_ready_to_open_and_litellm_never_is(
    tmp_path: Path, backend: str, ready: bool
) -> None:
    assert discover.ready_to_open(backend, tmp_path) is ready


@pytest.mark.parametrize("configured", [True, False])
def test_dsh_is_ready_to_open_only_once_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, configured: bool
) -> None:
    asked: list[Path] = []

    def native_ready(where: Path) -> bool:
        asked.append(where)
        return configured

    driver = types.ModuleType("hmz.coganchor.agents.dsh")
    driver.__dict__["native_ready"] = native_ready
    monkeypatch.setitem(sys.modules, "hmz.coganchor.agents.dsh", driver)

    assert discover.ready_to_open("dsh", tmp_path) is configured
    assert asked == [tmp_path]


class _Hmz:
    """Humanize as it is installed: from an index, or from anywhere else."""

    version = "1.2.3"

    def __init__(self, *, indexed: bool) -> None:
        self._indexed = indexed

    def read_text(self, name: str) -> str | None:
        return None if self._indexed else '{"url": "file:///src"}'


@pytest.mark.parametrize(
    ("indexed", "requirement"),
    [(True, "'hmz[litellm]==1.2.3'"), (False, "'litellm>=")],
)
def test_adding_an_extra_names_what_is_missing_and_the_line_that_adds_it(
    monkeypatch: pytest.MonkeyPatch, *, indexed: bool, requirement: str
) -> None:
    import importlib.metadata

    def distribution(name: str) -> _Hmz:
        assert name == "hmz"
        return _Hmz(indexed=indexed)

    monkeypatch.setattr(importlib.metadata, "distribution", distribution)

    said = discover.adding("litellm")

    assert said.startswith("litellm is not installed; run: uv pip install --python ")
    assert requirement in said
    assert said.endswith("; then reopen hmz")


def test_adding_a_backend_with_no_extra_says_to_install_it() -> None:
    assert discover.adding("mine") == "install mine, then reopen Humanize"


def test_adding_an_extra_to_a_humanize_that_is_no_distribution_names_its_packages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.metadata

    def distribution(name: str) -> _Hmz:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "distribution", distribution)

    assert "'litellm>=" in discover.adding("litellm")
