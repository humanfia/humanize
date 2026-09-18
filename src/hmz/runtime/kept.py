"""What an agent is, written down.

An agent is a CLI, an account, a model at an effort, and the machine its work lands on. What
it may do, the goals it may reach for, whether it searches the web and the skills it carries
are not its own to hold: the first three are the flow's, declared where the flow declares the
agent's place, and the last are the CLI's, installed and switched off where that CLI keeps
them. So this is a shape and the two directions it goes in, and nothing else.

Here rather than beside the interface because both ways in read it: the interface writes an
agent down per workspace per flow and a command line reads the same file back, and a command
line that had to load a terminal interface to read a file of six lines would be paying for a
layer it does not use.

How one agent goes into a file is here rather than beside the settings that hold it for the
reason it always was: an agent is written the same way wherever it is written, and two places
writing one shape is two places to drift.
"""

from __future__ import annotations

from typing import Any, NamedTuple

__all__ = ["Runs", "read_back", "written"]


class Runs(NamedTuple):
    """What one agent of a flow was set up to run, and where its turns land.

    Attributes:
      spec: The agent itself, as `cli/model:effort` -- the same word a command line takes.
      anchor: The machine its work lands on, as a target, or "" to work on this one.
      permission: What it may do without being asked, as one of `hmz.coganchor.agents.PERMISSIONS`,
        or "" for nothing said about it, which leaves the agent at what it was configured
        with. An answer withheld rather than a rung named quietly on somebody's behalf.
      provider: The account its turns run as, by the name a provider of its CLI was made
        under, or "" to run as this machine is already signed in.
      goals: Whether backend goals are available. This is always an on/off answer; any
        suggestion attached to the flow's agent place is resolved before this is constructed.
      web_search: Whether it may search the web, or None for nothing said about it. Three
        states rather than the two `goals` has, and the reason the two of them part company
        here is what happens to the answer afterwards: this one is settled onto the agent's
        config, and a `True` written down for an agent nobody asked about is an answer that
        switches searching on wherever the CLI had it off. The old two-state reading of this
        field -- on is what an agent nobody was asked about does -- was that answer, given
        every time this was built and never noticed because it agreed with the default it was
        overwriting. So the silence gets a value of its own and stays a silence all the way
        to the command line, and off and on go on being written down as the answers they are.
    """

    spec: str
    anchor: str = ""
    permission: str = ""
    provider: str = ""
    goals: bool = True
    web_search: bool | None = None


def written(runs: Runs) -> dict[str, Any]:
    """One agent as it goes into a file, which is the shape a workspace's settings hold.

    Read from both ends, as a command line reads one: a model may hold slashes of its own,
    while a CLI and an effort never do.

    Args:
      runs: What the agent is.

    Returns:
      Its fields, less any that says nothing -- an agent that works here, may do whatever an
      agent nobody was asked about may do, and runs as this machine is signed in is one every
      field of which is the field's own silence.
    """
    cli, _, rest = runs.spec.partition("/")
    model, _, effort = rest.rpartition(":")
    held: dict[str, Any] = {"cli": cli, "model": model, "effort": effort}
    if runs.anchor:
        held["anchor"] = runs.anchor
    if runs.permission:
        held["permission"] = runs.permission
    if runs.provider:
        held["provider"] = runs.provider
    # Both values are material: on may be an override of a workflow whose default is off, so
    # what is written down always records the explicit two-way choice. Web search is written
    # the same way and for the same reason -- and its silence is written too, as the `null`
    # it is. Left out, it could not be told from a file written before there was such a
    # setting, and those are the one case that has to read as on: that is what every agent
    # did then. A key that is there and empty is this file saying nobody was asked.
    held["goals"] = runs.goals
    held["web_search"] = runs.web_search
    return held


def read_back(held: dict[str, Any], *, goals: bool = True) -> Runs | None:
    """One agent as it comes back off a file, or None where what is there is not one.

    Args:
      held: What the file holds for it.
      goals: Whether goals are available where the entry does not say -- which is every entry
        written before there was such a setting.

    Returns:
      The agent, or None for an entry written by hand and not the way these are written.
    """
    cli, model, effort = held.get("cli"), held.get("model"), held.get("effort")
    if not (cli and model and effort):
        return None
    # An entry that says nothing about what it may do runs at what an agent nobody has been
    # asked about has always run at; one that names no account runs as this machine is signed
    # in. A `skills` an older file holds is the CLI's own business now, and is read past.
    said = held.get("goals")
    # Asked for with a default rather than read off what `get` returns for a key that is not
    # there, because here the two are different answers: a file holding `null` is one that
    # was asked and says nobody answered, and a file holding nothing at all is older than the
    # question.
    searches = held.get("web_search", True)
    return Runs(
        f"{cli}/{model}:{effort}",
        str(held.get("anchor") or ""),
        str(held.get("permission") or ""),
        str(held.get("provider") or ""),
        said if isinstance(said, bool) else goals,
        # An entry written before there was such a setting is one whose agent searched the
        # web, that being what every agent did then. A key holding anything that is not an
        # answer -- the `null` this writes, or something somebody typed in by hand -- holds
        # nothing anybody may act on, and it stays nothing.
        searches if isinstance(searches, bool) else None,
    )
