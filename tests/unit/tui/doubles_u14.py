"""Doubles the `hmz.tui.pick` unit tests stand in for other packages with."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.flows import HarnessKind
    from hmz.runtime.flowing import AgentRole, EnvRole


@dataclass(frozen=True)
class _Role:
    name: str
    harness: HarnessKind | None = None
    capabilities: frozenset[type] = frozenset()
    auto: bool = False


def role(
    name: str,
    harness: HarnessKind | None = None,
    capabilities: frozenset[type] = frozenset(),
    *,
    auto: bool = False,
) -> AgentRole:
    """An agent role as a flow declares one, holding only what the menu reads of it."""
    return cast("AgentRole", _Role(name, harness, capabilities, auto))


def env(name: str, *, auto: bool = False) -> EnvRole:
    """An environment role as a flow declares one, holding only what the menu reads of it."""
    return cast("EnvRole", _Role(name, auto=auto))


@dataclass
class Settings:
    """The settings store: a budget per flow."""

    budgets: dict[str, Any] = field(default_factory=dict[str, Any])

    def budget(self, flow: str) -> Any:
        return self.budgets.get(flow)


@dataclass
class Flows:
    """The flows store, whose `declared` raises what it was given to."""

    raises: BaseException | None = None

    def declared(self, flow: str) -> str:
        if self.raises is not None:
            raise self.raises
        return flow


@dataclass
class Epics:
    """The epics store: gathers a trace and packs a run, writing only where it is told."""

    other: dict[str, Any] = field(default_factory=dict[str, Any])
    archive: bytes = b"archive"
    calls: list[tuple[str, Path, Path | str]] = field(
        default_factory=list[tuple[str, Path, "Path | str"]]
    )

    def traced(self, at: Path, output: Path) -> tuple[Path, dict[str, Any]]:
        self.calls.append(("traced", at, output))
        return output, {"otherData": self.other}

    def bundled(self, at: Path, output: str) -> tuple[Path, int]:
        self.calls.append(("bundled", at, output))
        landed = Path(output) / "run.tar.gz"
        landed.write_bytes(self.archive)
        return landed, len(self.archive)


@dataclass
class Hmz:
    """`hmz.daemon.Hmz`, holding only the stores the menu reaches; calling it is making it."""

    settings: Settings = field(default_factory=Settings)
    flows: Flows = field(default_factory=Flows)
    epics: Epics = field(default_factory=Epics)
    accounts: Any = None
    #: The backends that open here without further setup, and each one asked about.
    opens: set[str] = field(default_factory=set[str])
    asked: list[str] = field(default_factory=list[str])

    def __call__(self) -> Hmz:
        return self

    def ready_to_open(self, backend: str) -> bool:
        self.asked.append(backend)
        return backend in self.opens


@dataclass
class Described:
    """What a flow says of itself when it is described."""

    agents: tuple[AgentRole, ...] = ()
    envs: tuple[EnvRole, ...] = ()
    params: type = object
    resumable: bool = False


@dataclass
class Impl:
    """A loaded flow, which describes itself."""

    said: Described

    def describe(self) -> Described:
        return self.said


def resolving(
    flows: dict[str, Described], privileged: frozenset[str] = frozenset()
) -> tuple[Callable[[str], Impl], Callable[[Impl], bool]]:
    """A `resolved` loading the flows given and raising for any other, and a `privileged`."""
    loaded = {name: Impl(said) for name, said in flows.items()}

    def resolved(flow: str) -> Impl:
        try:
            return loaded[flow]
        except KeyError:
            raise ImportError(f"no flow {flow}") from None

    def is_privileged(impl: Impl) -> bool:
        return any(loaded[name] is impl for name in privileged)

    return resolved, is_privileged
