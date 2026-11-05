"""The skills a session carries: the ones its CLI installs, and the ones a flow brings.

Two halves, and the difference between them is who they belong to.

The first is a reading. A skill installed on this machine is the CLI's own -- installed the
way that CLI installs one and switched off the way that CLI switches one off -- so Humanize
lists them so that whoever is setting an agent up can see what it will be carrying, and
changes nothing about any of them. Nothing is asked of the CLI itself, for the reason nothing
else here asks it either: starting one costs seconds a prompt does not have. Where each of
them looks is written down in :mod:`hmz.coganchor.backends`, and reading a `SKILL.md` is reading its
front matter and stopping.

The second is what a flow brings: the skills it works by, which every session its agents
open gets. They go into the virtual home the session's CLI is started in
(:attr:`~hmz.coganchor.backends.Profile.lodges`, :mod:`hmz.coganchor.homes`), beside links to
the user's own, or are named in its configuration where a CLI reads them from a list -- never
into the workspace, which is the project's and holds nothing of Humanize's.
"""

from __future__ import annotations

import contextlib
import os
import re
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

#: What DeepSeek Harness takes a skill's name to be: kebab case, as `@deepseek-ai/dsh-skill`
#: checks it. A file naming anything else, or nothing, is one it passes over.
_KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

#: The front matter that says who may invoke a DeepSeek Harness skill, and the older
#: spellings of it that it refuses, passing the file over: each must be a boolean, `0` or `1`,
#: or `true`, `yes`, `on`, `false`, `no` or `off` in any case.
_INVOKED = ("disable-model-invocation", "user-invocable")
_LEGACY = frozenset({"disableModelInvocation", "modelInvocable", "userInvocable"})
_FLAGS = frozenset({"1", "0", "true", "yes", "on", "false", "no", "off"})

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
      One entry per skill, yours before the project's and each set in the order it is on disk
      -- but for dsh, which prefers the project's and is listed in its own order. Empty for
      a backend that is not known here, keeps none, or has none installed.
    """
    profile = named(backend)
    if profile is None:
        return []
    if profile.name == "dsh":
        return _dsh(Path(where or Path.cwd()).absolute())
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


def _dsh(where: Path) -> list[Skill]:
    """The skills DeepSeek Harness would load here, as its runtime finds them.

    Read off `@deepseek-ai/dsh-skill-filesystem` as the SDK's runtime bundles it, rather than
    off a profile's globs, since it finds them its own way: from the project's root -- the
    nearest directory up from here holding a `.git`, or here where none does -- and in the
    order it prefers them, the project's `.dsh` and `.agents` before the home's and then
    `$DSH_AGENTS_HOME`'s. Each root holds a skill as `<name>/SKILL.md` or as `<name>.md`, and
    a file it cannot read a kebab-case name and a description out of is one it passes over.

    Args:
      where: The directory a session would work in.

    Returns:
      One entry per name, the project's first, as the harness would list them.
    """
    project = next(
        (one for one in (where, *where.parents) if (one / ".git").exists()), where
    )
    home = os.environ.get("DSH_HOME", "").strip() or "~/.dsh"
    shared = os.environ.get("DSH_AGENTS_HOME") or "~/.agents"
    found: dict[str, Skill] = {}
    # Each with whether it passes over `.system`, where the harness keeps skills of its own --
    # which its home's root does, and no other, wherever else that root happens to be.
    for root, whose, system in (
        (project / ".dsh" / SKILLS, "this project", False),
        (project / ".agents" / SKILLS, "this project", False),
        (Path(home).expanduser() / SKILLS, "yours", True),
        (Path(shared).expanduser() / SKILLS, "yours", False),
    ):
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if system and entry.name == ".system":
                continue
            card = entry / CARD if entry.is_dir() else entry
            if card.suffix != ".md" or not card.is_file():
                continue
            skill = _native(card, whose)
            if skill is not None and skill.name not in found:
                found[skill.name] = skill
    return list(found.values())


def _native(path: Path, whose: str) -> Skill | None:
    """One skill file, read as DeepSeek Harness reads it, or None where it passes it over.

    Its front matter is everything between a first line of `---` and the next line that is
    `---` and nothing else, and must be a mapping whose `name` is a kebab-case string and
    whose `description` is a string with anything in it -- the whole of what the harness
    asks of one, of any length. Read whole, as the harness reads it, rather than its head.

    Args:
      path: The file.
      whose: Where it came from.

    Returns:
      The skill, or None for a file the harness would not list.
    """
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeError):
        return None
    fenced = [one.removesuffix("\r") == _FENCE for one in lines]
    if not fenced[0] or True not in fenced[1:]:
        return None
    try:
        front: Any = yaml.load(
            "\n".join(lines[1 : fenced.index(True, 1)]),
            Loader=_NativeLoader,  # noqa: S506 -- SafeLoader with different scalar rules
        )
    except (yaml.YAMLError, ValueError):
        return None
    said = cast("dict[str, Any]", front) if isinstance(front, dict) else {}
    name, about = said.get("name"), said.get("description")
    if not isinstance(name, str) or _KEBAB.fullmatch(name) is None:
        return None
    if not isinstance(about, str) or not about:
        return None
    # And who may invoke it, said in the words it reads and in no others.
    if _LEGACY & said.keys() or any(
        not _flag(said[key]) for key in _INVOKED if key in said
    ):
        return None
    return Skill(name=name, about=_short(about), whose=whose)


def _flag(value: object) -> bool:
    """Whether DeepSeek Harness reads a value of its front matter as a boolean."""
    if isinstance(value, (bool, int, float)):
        return value in (0, 1)
    return isinstance(value, str) and value.lower() in _FLAGS


class _NativeLoader(yaml.SafeLoader):
    """The runtime's YAML 1.2 strings, without changing other backends' YAML readers.

    The runtime's core schema keeps dates and YAML 1.1 booleans such as `yes` as strings.
    Its numbers include `1e3` and `0o7`, but not binary or underscored YAML 1.1 integers.
    """

    def core_int(self, node: yaml.ScalarNode) -> int:
        """Read decimal integers, including leading zeroes, and explicit octal or hex."""
        value = self.construct_scalar(node)
        base = 8 if value.startswith("0o") else 16 if value.startswith("0x") else 10
        return int(value, base)

    def core_float(self, node: yaml.ScalarNode) -> float:
        """Read core-schema floats, including signed infinities and NaNs."""
        value = self.construct_scalar(node).lower()
        return float(value.replace(".inf", "inf").replace(".nan", "nan"))


_NativeLoader.yaml_implicit_resolvers = {
    first: [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag.rsplit(":", 1)[-1] not in {"bool", "timestamp", "int", "float"}
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_NativeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)
_NativeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"),
    list("-+0123456789"),
)
_NativeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(
        r"^[-+]?(?:\.(?:inf|Inf|INF|nan|NaN|NAN)|"
        r"(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)[eE][-+]?[0-9]+|"
        r"\.[0-9]+|[0-9]+\.[0-9]*)$"
    ),
    list("-+.0123456789"),
)
_NativeLoader.add_constructor("tag:yaml.org,2002:int", _NativeLoader.core_int)
_NativeLoader.add_constructor("tag:yaml.org,2002:float", _NativeLoader.core_float)


def _short(about: str) -> str:
    """A description, on one line and cut to what a row has room for."""
    about = " ".join(about.split())
    return about[:_ABOUT] + ("…" if len(about) > _ABOUT else "")


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
    return Skill(
        name=name, about=_short(str(said.get("description") or "")), whose=whose
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
