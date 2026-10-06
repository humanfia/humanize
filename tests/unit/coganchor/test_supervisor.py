"""The supervisor's settings, and which programs it leaves on this machine.

Linux only: the supervisor is a ptrace loop, and importing it reads that kernel's register map.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import pytest

if sys.platform != "linux":
    pytest.skip("the supervisor is Linux's alone", allow_module_level=True)

from hmz.coganchor.supervisor import Launch, Supervisor, Tracee


def test_a_launch_is_held_to_nothing_unless_told() -> None:
    launch = Launch("/bin/agent", ["agent", "-p"], {"A": "b"}, "/w")
    assert (launch.walled, launch.sockets) == (None, False)


def test_a_tracee_starts_with_nothing_pending() -> None:
    tracee = Tracee(12)
    assert (tracee.attached, tracee.exec_count, tracee.proxy, tracee.pending_errno) == (
        False,
        0,
        None,
        None,
    )


@dataclass
class Router:
    local: frozenset[str] = frozenset({"/opt/agent/node"})
    asked: list[str] = field(default_factory=list[str])

    def runs_locally(self, program: str) -> bool:
        self.asked.append(program)
        return program in self.local


def supervising(
    router: Router,
    private: tuple[str, ...] = (),
    fence: dict[str, object] | None = None,
) -> Supervisor:
    return Supervisor(
        object(),  # pyright: ignore[reportArgumentType]
        router,  # pyright: ignore[reportArgumentType]
        object(),  # pyright: ignore[reportArgumentType]
        Launch("/bin/agent", ["agent"], {}, "/w"),
        private=private,
        fence=fence,
    )


def test_what_it_was_given_is_what_it_holds() -> None:
    supervisor = supervising(
        Router(), private=("OPENAI_API_KEY", "OPENAI_API_KEY"), fence={}
    )
    assert supervisor.private == frozenset({"OPENAI_API_KEY"})
    assert supervisor.fence == {}
    assert supervisor.netproxy is None


@pytest.mark.parametrize(
    ("program", "here"), [("/opt/agent/node", True), ("/usr/bin/git", False)]
)
def test_a_program_the_agent_runs_goes_where_the_router_says(
    program: str, here: bool
) -> None:
    router = Router()
    assert supervising(router).is_agent_launch(Tracee(4321), program) is here
    assert router.asked == [program]
