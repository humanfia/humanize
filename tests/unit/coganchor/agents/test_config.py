"""`hmz.coganchor.agents.config`: what every session of an agent runs at."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from hmz.coganchor.agents.config import (
    CUTOFFS,
    OUTCOMES,
    PERMISSIONS,
    SERVICE_TIERS,
    UNSAID,
    AgentConfig,
    Budget,
    Unfenced,
    Unserved,
    anchored,
)
from hmz.coganchor.machines import AnchoredConfig


def test_the_vocabularies() -> None:
    assert PERMISSIONS == ("read-only", "workspace-write", "auto", "bypass")
    assert UNSAID == ""
    assert SERVICE_TIERS == ("default", "fast")
    assert CUTOFFS == ("next-response", "immediately")
    assert OUTCOMES == ("end", "fail")
    assert issubclass(Unfenced, Unserved)
    assert issubclass(Unserved, ValueError)


def test_an_empty_budget_caps_nothing() -> None:
    budget = Budget()
    assert not budget.bounded
    assert budget.over(output=1e9, seconds=1e9) == ""
    assert (budget.when, budget.then) == ("next-response", "end")


@pytest.mark.parametrize(
    ("budget", "output", "seconds", "over"),
    [
        (Budget(output=500), 499, 0, ""),
        (Budget(output=500), 500, 0, "500 output tokens"),
        (Budget(seconds=90), 0, 89.9, ""),
        (Budget(seconds=90), 0, 90, "90s"),
        (Budget(output=10, seconds=1.5), 10, 2, "10 output tokens"),
        (Budget(output=10, seconds=1.5), 0, 2, "1.5s"),
    ],
)
def test_a_budget_says_which_cap_was_run_through(
    budget: Budget, output: float, seconds: float, over: str
) -> None:
    assert budget.bounded
    assert budget.over(output=output, seconds=seconds) == over


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"when": "later"}, "when must be one of"),
        ({"then": "explode"}, "then must be one of"),
        ({"output": -1}, "less than nothing"),
        ({"seconds": -1}, "less than nothing"),
    ],
)
def test_a_budget_that_would_never_bite_is_refused(
    kwargs: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        Budget(**kwargs)  # pyright: ignore[reportArgumentType]


def test_a_config_defaults_to_saying_nothing() -> None:
    config = AgentConfig(model="m", effort="high")
    assert (config.service_tier, config.permission, config.provider) == (
        "default",
        UNSAID,
        "",
    )
    assert config.goals
    assert config.web_search is None
    assert (config.machine, config.fence, config.budget) == (None, None, None)
    assert AgentConfig.of_model == ()


def test_a_config_is_frozen() -> None:
    config = AgentConfig(model="m", effort="")
    with pytest.raises(FrozenInstanceError):
        config.model = "other"  # pyright: ignore[reportAttributeAccessIssue]


def test_auto_effort_is_no_rung() -> None:
    assert AgentConfig(model="m", effort="auto").effort == ""


@pytest.mark.parametrize("permission", [*PERMISSIONS, UNSAID])
def test_every_rung_and_the_silence_are_sayable(permission: str) -> None:
    assert AgentConfig(model="m", effort="", permission=permission).permission == (
        permission
    )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"service_tier": "slow"}, "service_tier must be one of"),
        ({"permission": "root"}, "permission must be one of"),
    ],
)
def test_a_config_no_backend_could_carry_is_refused(
    kwargs: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        AgentConfig(model="m", effort="", **kwargs)


def test_anchored_nothing_is_this_machine() -> None:
    assert anchored("") is None


def test_anchored_names_a_running_machine() -> None:
    machine = anchored("ssh://host")
    assert isinstance(machine, AnchoredConfig)
    assert machine.anchor.target == "ssh://host"


def test_anchored_refuses_a_target_it_cannot_read() -> None:
    with pytest.raises(ValueError, match="unsupported target"):
        anchored("bogus://x")
