"""`hmz.flows.envs`: where an environment is, and how its protocols build on one another."""

from __future__ import annotations

import pytest

from hmz.flows import (
    BashEnvMixin,
    Env,
    EnvBackendKind,
    GitEnvMixin,
    LocalEnv,
    RewindableEnvMixin,
    ShellEnvMixin,
)


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (EnvBackendKind.LOCAL, "local"),
        (EnvBackendKind.SSH, "ssh"),
        (EnvBackendKind.DOCKER, "docker"),
        (EnvBackendKind.SWARM, "swarm"),
        (EnvBackendKind.APPLE_CONTAINER, "apple-container"),
    ],
)
def test_a_backend_is_named_as_dash_e_names_it(kind: EnvBackendKind, name: str) -> None:
    assert kind == name
    assert EnvBackendKind(name) is kind


def test_there_are_five_backends() -> None:
    assert len(EnvBackendKind) == 5


def test_an_unknown_backend_is_refused() -> None:
    with pytest.raises(ValueError, match="apple_container"):
        EnvBackendKind("apple_container")


@pytest.mark.parametrize(
    ("protocol", "base"),
    [
        (LocalEnv, Env),
        (BashEnvMixin, ShellEnvMixin),
        (GitEnvMixin, RewindableEnvMixin),
    ],
)
def test_a_protocol_builds_on_what_it_widens(protocol: type, base: type) -> None:
    assert base in protocol.__mro__
