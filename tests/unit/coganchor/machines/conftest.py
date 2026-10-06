"""A `docker`, a `container` and a target handshake, faked, so no machine is ever reached."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

import hmz.coganchor

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hmz.coganchor import AnchorConfig


@dataclass
class Rule:
    """What one command answers with: each answer once, and the last one from then on."""

    words: tuple[str, ...]
    answers: list[tuple[int, str, str]]
    timeout: bool = False
    then: Callable[[list[str]], None] | None = None


def holds(argv: Sequence[str], words: Sequence[str]) -> bool:
    """Whether `words` are in `argv`, one after another."""
    n = len(words)
    return any(
        list(argv[at : at + n]) == list(words) for at in range(len(argv) - n + 1)
    )


@dataclass
class Runs:
    """Stands in for `subprocess.run`: records every argv, answers by rules."""

    calls: list[list[str]] = field(default_factory=list[list[str]])
    rules: list[Rule] = field(default_factory=list[Rule])
    #: Commands that are not on `PATH`.
    absent: set[str] = field(default_factory=set[str])

    def on(
        self,
        *words: str,
        out: str = "",
        err: str = "",
        status: int = 0,
        timeout: bool = False,
        then: Callable[[list[str]], None] | None = None,
    ) -> Rule:
        rule = Rule(words, [(status, out, err)], timeout, then)
        self.rules.append(rule)
        return rule

    def __call__(
        self, argv: Sequence[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[Any]:
        said = [str(one) for one in argv]
        self.calls.append(said)
        for rule in reversed(self.rules):
            if not holds(said, rule.words):
                continue
            if rule.then is not None:
                rule.then(said)
            if rule.timeout:
                raise subprocess.TimeoutExpired(said, kwargs.get("timeout") or 0)
            status, out, err = (
                rule.answers[0] if len(rule.answers) == 1 else rule.answers.pop(0)
            )
            return subprocess.CompletedProcess(said, status, out, err)
        return subprocess.CompletedProcess(said, 0, "", "")

    def called(self, *words: str) -> list[list[str]]:
        return [one for one in self.calls if holds(one, words)]


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> Runs:
    """Every command run, answered by rules; `docker` and `container` on `PATH`."""
    faked = Runs()
    monkeypatch.setattr(subprocess, "run", faked)

    def which(name: str, *_: object, **__: object) -> str | None:
        return None if name in faked.absent else f"/usr/bin/{name}"

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    return faked


@dataclass
class Handshake:
    """Stands in for `hmz.coganchor.check`: what each target says it is."""

    platform: str = "linux"
    asked: list[AnchorConfig] = field(default_factory=list["AnchorConfig"])
    fails: Exception | None = None

    def __call__(self, config: AnchorConfig | None = None) -> dict[str, Any]:
        assert config is not None
        self.asked.append(config)
        if self.fails is not None:
            raise self.fails
        return {"platform": self.platform}


@pytest.fixture
def handshake(monkeypatch: pytest.MonkeyPatch) -> Handshake:
    faked = Handshake()
    monkeypatch.setattr(hmz.coganchor, "check", faked)
    return faked
