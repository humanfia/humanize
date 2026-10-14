"""The skills a session carries: the ones its CLI installs, and the ones a flow brings.

Two halves, and the difference between them is who they belong to.

The first is a reading. A skill installed on this machine is the CLI's own -- installed the
way that CLI installs one and switched off the way that CLI switches one off -- so humanize
lists them so that whoever is setting an agent up can see what it will be carrying, and
changes nothing about any of them. Nothing is asked of the CLI itself, for the reason nothing
else here asks it either: starting one costs seconds a prompt does not have. Where each of
them looks is written down in :mod:`hmz.coganchor.backends`, and reading a `SKILL.md` is reading its
front matter and stopping.

The second is what a flow brings: the skills it works by, which every session its agents
open gets. They go into the virtual home the session's CLI is started in
(:attr:`~hmz.coganchor.backends.Profile.lodges`, :mod:`hmz.coganchor.homes`), beside links to
the user's own, or are named in its configuration where a CLI reads them from a list -- never
into the workspace, which is the project's and holds nothing of humanize's.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from hmz.coganchor.backends import named

__all__ = [
    "CARD",
    "SKILLS",
    "Loaded",
    "Skill",
    "skills",
]

#: How much of a `SKILL.md` is read to find its front matter. The front matter is at the top
#: and the rest of the file is the skill itself, which can be a hundred kilobytes of prose.
_FRONT = 4096

#: What front matter is fenced with, and how little of a description a row has room for.
_FENCE = "---"
_ABOUT = 90

#: The layout every one of these CLIs reads a skill in: a directory of skills, one directory
#: apiece, each holding the file that is the skill. It is what a flow keeps its own in too, so
#: that a skill written for one of these CLIs is a skill a flow can carry unchanged.
SKILLS = "skills"
CARD = "SKILL.md"


@dataclass(frozen=True, slots=True)
class Skill:
    """One skill a backend would load.

    Attributes:
      name: What the CLI knows it by, which is what a turn is told about: the name in its
        front matter, or the directory it is in where it states none -- which is the rule
        every one of these CLIs reads a skill by.
      about: The line it describes itself with, which is what says whether to switch it off.
      whose: Where it came from: yours, or this project's.
    """

    name: str
    about: str
    whose: str


def skills(backend: str, where: Path | str | None = None) -> list[Skill]:
    """The skills one backend would load here, the way that backend finds them.

    Args:
      backend: The CLI, by any name it answers to.
      where: The project whose own skills to include, defaulting to this directory.

    Returns:
      One entry per skill, yours before the project's and each set in the order it is on disk.
      Empty for a backend that is not known here, keeps none, or has none installed.
    """
    profile = named(backend)
    if profile is None:
        return []
    found: list[Skill] = []
    seen: set[str] = set()
    for root, globs, whose in (
        (profile.directory(), profile.skills, "yours"),
        # The backend's own too, for one that keeps them under the directory every program
        # keeps its configuration in rather than beside its sessions.
        (profile.configuration(), profile.config, "yours"),
        # Under your own home rather than the backend's, and so not moved by whatever moves
        # that: `.agents` is the directory more than one of these has agreed to read.
        (Path.home(), profile.shared, "yours"),
        (Path(where or Path.cwd()), profile.works, "this project"),
    ):
        for pattern in globs:
            for path in sorted(root.glob(pattern)):
                skill = _skill(path, whose)
                # One name is one skill: a project's own of the same name is the same skill
                # to the CLI, which loads whichever of them it prefers and lists it once.
                if skill is not None and skill.name not in seen:
                    seen.add(skill.name)
                    found.append(skill)
    return found


def _skill(path: Path, whose: str) -> Skill | None:
    """One `SKILL.md`, read as the CLI reads it: its front matter, and nothing else.

    Args:
      path: The file.
      whose: Where it came from.

    Returns:
      The skill, or None for a file that cannot be read at all.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            head = stream.read(_FRONT)
    except OSError:
        return None
    front: Any = {}
    if head.startswith(_FENCE):
        _, _, rest = head.partition("\n")
        block, _, _ = rest.partition(f"\n{_FENCE}")
        with contextlib.suppress(yaml.YAMLError):
            front = yaml.safe_load(block)
    said = cast("dict[str, Any]", front) if isinstance(front, dict) else {}
    # The directory is the name where the front matter states none, which is the rule these
    # CLIs read a skill by -- the file is always `SKILL.md`.
    name = str(said.get("name") or path.parent.name).strip()
    about = " ".join(str(said.get("description") or "").split())
    return Skill(
        name=name,
        about=about[:_ABOUT] + ("…" if len(about) > _ABOUT else ""),
        whose=whose,
    )


@dataclass(frozen=True, slots=True)
class Loaded:
    """One skill a flow brings, to be given to every session its agents open.

    Attributes:
      name: What it is called, which is the directory it is in -- and the name the CLI will
        know it by once it is lodged.
      at: Where it is now: inside the flow, or inside the clone of a repository the flow
        named. It is copied from there rather than pointed at, so that a session on another
        machine carries it too.
      whose: What brought it, for whoever is being shown what a flow works by: the flow
        itself, or the repository it was named in.
    """

    name: str
    at: Path
    whose: str = ""
