"""What an agent is, written down.

An agent is a CLI, an account, and a model at an effort. What it may do, the capabilities it
is granted and the skills it carries are not its own to hold: they are the flow's, declared
where the flow declares the agent's role. Where its work lands is not its own either: that is
the environment the flow opens its session in. So this is a shape and the two directions it
goes in, and nothing else -- the same word `-a` takes after the role.

Here rather than beside the interface because both ways in read it: the interface writes an
agent down per workspace per flow and a command line reads the same file back, and a command
line that had to load a terminal interface to read a file of six lines would be paying for a
layer it does not use.
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = ["Runs", "read_back", "written"]


class Runs(NamedTuple):
    """What one agent of a flow was set up to run.

    Attributes:
      spec: The agent itself, as `cli/model:effort`.
      provider: The account its turns run as, by the name a provider of its CLI was made
        under, or "" to run as this machine is already signed in.
    """

    spec: str
    provider: str = ""


def written(runs: Runs) -> str:
    """One agent as it goes into a file: the word `-a` takes after `<role>=`.

    Args:
      runs: What the agent is.

    Returns:
      `cli@provider/model:effort`, or `cli/model:effort` for one that runs as this machine
      is signed in.
    """
    cli, _, rest = runs.spec.partition("/")
    account = f"@{runs.provider}" if runs.provider else ""
    return f"{cli}{account}/{rest}"


def read_back(said: object) -> Runs | None:
    """One agent as it comes back off a file, or None where what is there is not one.

    Read from both ends, as a command line reads one: a model may hold slashes and colons of
    its own, while a CLI and an effort never do.

    Args:
      said: What the file holds for it.

    Returns:
      The agent, or None for an entry written by hand, or by an older humanize, and not the
      way these are written.
    """
    if not isinstance(said, str):
        return None
    head, slash, rest = said.partition("/")
    cli, _, provider = head.partition("@")
    model, colon, effort = rest.rpartition(":")
    if not (slash and colon and cli and model and effort):
        return None
    return Runs(f"{cli}/{model}:{effort}", provider)
