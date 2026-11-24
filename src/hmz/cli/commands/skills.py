"""`hmz skills`: the skill of using `hmz`, written where a harness reads its user's skills.

One skill, and the only one Humanize ever installs: a folder `hmz` holding a `SKILL.md` that
tells a coding agent how to use this command line. What it says is read off the commands'
own declarations (:func:`hmz.cli.tree.described`) each time it is written, so it says what
`--help` says and no more; where it goes is where each harness's profile says that harness
finds its user's skills (:mod:`hmz.coganchor.backends`), which is written down nowhere else.

These commands ask no daemon. A skill is a file of this user's on this machine, and so is
everything they read and write.
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from hmz.cli import tree
from hmz.cli.tree import Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from hmz.cli.tree import Call

__all__ = ["COMMANDS"]

#: What the skill is called: the folder it is in, and the name in its front matter.
NAME: Final = "hmz"

#: The file that is the skill, and the one beside it the commands are listed in once they
#: are too many for the first. The first is what every harness calls it
#: (:data:`hmz.coganchor.agents.skills.CARD`), said here too so that printing a skill costs
#: nothing of driving an agent.
_CARD: Final = "SKILL.md"
_REFERENCE: Final = "reference.md"

#: What in a skill's front matter says `hmz skills add` wrote it, and which hmz did. Both
#: under `metadata`, which is where the Agent Skills format keeps what is not its own.
_BY: Final = "written-by"
_MARK: Final = "hmz skills add"
_VERSION: Final = "hmz-version"

#: How long a `SKILL.md` is let grow before its list of commands is put beside it.
_LINES: Final = 500

_FENCE: Final = "---"

#: What a common job is called, and the daemon's methods its steps call, in order; a step
#: is the first of its methods some command calls. Named by method rather than by command,
#: so that a sequence is written from whatever commands there are, and left out until there
#: is one for each of its steps.
_SEQUENCES: Final = (
    ("Start a chat and read the answer", (("chat.start",), ("chat.get",))),
    ("Start an epic and follow it", (("epic.start",), ("epic.attach", "epic.status"))),
    (
        "Answer a question an epic asks",
        (("epic.status", "epic.attach"), ("epic.answer",)),
    ),
    ("List the runs and export one", (("runs.list",), ("runs.bundle",))),
)

#: What each state of a harness's hmz skill is called in a list.
_STATES: Final = {
    "current": "Current",
    "older": "Older",
    "absent": "Not installed",
    "foreign": "Not written by hmz",
}


def _version() -> str:
    from hmz import coganchor

    return coganchor.__version__


def _leaves(said: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Every command under one that is run, rather than a group of them."""
    if "commands" in said:
        for under in said["commands"]:
            yield from _leaves(under)
    else:
        yield said


def _listed(said: dict[str, Any], depth: int = 0, *, deep: bool = True) -> list[str]:
    """A command as one line, usage and summary, and those under it below it."""
    lines = [f"{'  ' * depth}- `{said['usage']}`: {said['summary']}"]
    if deep:
        for under in said.get("commands", ()):
            lines.extend(_listed(under, depth + 1))
    return lines


def _sequences(held: Sequence[dict[str, Any]]) -> list[str]:
    """The common jobs there is a command for every step of, each as numbered lines."""
    leaves = [leaf for said in held for leaf in _leaves(said)]

    def calling(methods: tuple[str, ...]) -> dict[str, Any] | None:
        for method in methods:
            calls = [one for one in leaves if method in one.get("daemon_methods", ())]
            # The command that is for a method before one that happens to call it too.
            calls.sort(key=lambda one: one["daemon_methods"][0] != method)
            if calls:
                return calls[0]
        return None

    lines: list[str] = []
    for title, steps in _SEQUENCES:
        found = [calling(step) for step in steps]
        if any(one is None for one in found):
            continue
        lines.extend(["", f"### {t(title)}", ""])
        seen: list[str] = []
        for one in cast("list[dict[str, Any]]", found):
            if one["command"] in seen:
                continue
            seen.append(one["command"])
            example = next(iter(one["examples"]), None)
            line = example["line"] if example else one["usage"]
            does = example["does"] if example else one["summary"]
            lines.append(f"{len(seen)}. `{line}`: {does}")
    if not lines:
        return []
    said = t(
        "Each step is a line as the command's own help gives it; "
        "replace its values with your own."
    )
    return ["", f"## {t('Common sequences')}", "", said, *lines]


def _locally(held: Sequence[dict[str, Any]]) -> list[str]:
    """What is said of the commands that ask no daemon, which are those taking none."""
    local = [
        leaf["command"]
        for said in held
        for leaf in _leaves(said)
        if "arguments" in leaf
        and not any("--daemon" in one["flags"] for one in leaf["arguments"])
    ]
    if not local:
        return []
    said = t(
        "These commands only read and write files on this machine, so they ask no "
        "daemon, take no `--daemon`, never exit with status 3, and exit with 1 when "
        "they refuse:"
    )
    return [f"- {said} " + ", ".join(f"`{one}`" for one in local)]


def _card(held: Sequence[dict[str, Any]], version: str, *, deep: bool) -> str:
    """The `SKILL.md`, with every command in it or only the ones `hmz` is followed by."""
    import yaml

    front = yaml.safe_dump(
        {
            "name": NAME,
            "description": t(
                "Works with Humanize through the hmz command line to start and follow "
                "chats and epics, run flows, answer their questions, read and export "
                "runs, and manage settings, accounts, environments and devices of a "
                "Humanize daemon. Load it whenever the task mentions hmz or Humanize."
            ),
            "metadata": {_BY: _MARK, _VERSION: version},
        },
        sort_keys=False,
        allow_unicode=True,
        width=2**16,
    )
    finds = [
        ("hmz --help", "lists every command with one line about each"),
        (
            "hmz COMMAND --help",
            (
                "prints everything about one command: its arguments, options, examples, "
                "what it prints, the fields of its JSON document and its exit codes"
            ),
        ),
    ]
    if any(said["command"] == "hmz help" for said in held):
        finds.append(
            (
                "hmz help --json",
                (
                    "prints every command's declaration as one JSON document, for reading "
                    "by a program"
                ),
            )
        )
    lines = [
        _FENCE,
        *front.splitlines(),
        _FENCE,
        "",
        f"# {NAME}",
        "",
        t(
            "`hmz` is the command line of Humanize, which runs AI coding agents on a "
            "person's own machines. Every command is a client of a Humanize daemon, "
            "which `hmz` starts on this machine when none is running. Everything "
            "written below is generated from the commands' own declarations, so it "
            "matches what `--help` prints."
        ),
        "",
        f"## {t('Discovering commands')}",
        "",
        *(f"- `{line}`: {t(does)}" for line, does in finds),
        "",
        f"## {t('Conventions')}",
        "",
        "- "
        + t(
            "Pass `--json` to any command to get one JSON document on standard output "
            "and nothing else there. Prefer it when a program reads the answer."
        ),
        "- "
        + t(
            "Under `--json`, a command that fails prints this document instead and "
            "exits with a status other than 0:"
        )
        + ' `{"error": {"code": 404, "message": "..."}}`',
        "- "
        + t(
            "`--daemon NAME` asks another daemon than this machine's, by the name it "
            "is kept under in the daemon list."
        ),
        "- " + t("Every command ends with one of these exit statuses:"),
        *(f"  - `{one.code}`: {t(one.says)}" for one in tree.EXITS),
        *_locally(held),
        "",
        f"## {t('Commands')}",
        "",
        t(
            "Each line below is one command's usage and what it does. Run the command "
            "with `--help` for its options, examples and JSON fields."
        ),
    ]
    if not deep:
        lines.append(
            t(
                "Every command is listed in [reference.md](reference.md) beside this file."
            )
        )
    lines.append("")
    for said in held:
        lines.extend(_listed(said, deep=deep))
    lines.extend(_sequences(held))
    return "\n".join(lines) + "\n"


def _rendered() -> dict[str, str]:
    """The files the skill is made of now, by name: the `SKILL.md`, and what is beside it."""
    version = _version()
    held = [
        tree.described([name], command) for name, command in tree.commands().items()
    ]
    whole = _card(held, version, deep=True)
    if whole.count("\n") <= _LINES:
        return {_CARD: whole}
    reference = [f"# {NAME}: {t('Commands')}", ""]
    for said in held:
        reference.extend(_listed(said))
    return {
        _CARD: _card(held, version, deep=False),
        _REFERENCE: "\n".join(reference) + "\n",
    }


@dataclass(frozen=True)
class _Place:
    """One skills folder the skill is written into, and whose it is."""

    harness: str | None
    """The harness that reads it, or None for a folder given by its path."""
    directory: Path
    installed: bool = True
    """Whether that harness is on this machine."""

    @property
    def card(self) -> Path:
        return self.directory / NAME / _CARD


def _folders(profile: Any) -> list[Path]:
    """Where a harness finds its user's skills, as its profile's globs have it.

    In the order that makes the first its own: its home's before the configuration
    directory's, and those harnesses share under the user's home after both.
    """
    under = f"/*/{_CARD}"
    return [
        root() / pattern.removesuffix(under)
        for root, globs in (
            (profile.directory, profile.skills),
            (profile.configuration, profile.config),
            (Path.home, profile.shared),
        )
        for pattern in globs
        if pattern.endswith(under)
    ]


def _folder(profile: Any) -> Path | None:
    """The skills folder that is a harness's own: the first it looks in, or None."""
    return next(iter(_folders(profile)), None)


def _places(call: Call, *, installed: bool) -> list[_Place]:
    """The folders a line is about: those it names, or each harness's own.

    Args:
      call: The command, with its `--for` and its `--dir`.
      installed: Whether a line that names none is about only the harnesses on this
        machine, rather than every harness that has a skills folder.

    Raises:
      hmz.sdk.Refused: If a harness named is not one, or has no skills folder.
    """
    from hmz.coganchor import backends
    from hmz.sdk import Refused

    found: list[_Place] = []
    named: list[str] = getattr(call.given, "for") or []
    for name in named:
        profile = backends.named(name)
        if profile is not None and profile.name in [one.harness for one in found]:
            continue
        if profile is None:
            raise Refused(
                t(
                    "There is no harness named {name}. `hmz skills list` prints the names.",
                    name=name,
                )
            )
        folder = _folder(profile)
        if folder is None:
            raise Refused(
                t(
                    "The harness {name} loads no skills from a folder of its own. "
                    "Give a folder with `--dir`.",
                    name=profile.name,
                )
            )
        here = backends.program(profile.name) is not None
        found.append(_Place(profile.name, folder, installed=here))
    if call.dir is not None:
        found.append(_Place(None, call.dir))
    if named or call.dir is not None:
        return found
    for profile in backends.profiles():
        folder = _folder(profile)
        here = backends.program(profile.name) is not None
        if folder is not None and (here or not installed):
            found.append(_Place(profile.name, folder, installed=here))
    if not installed:
        # And wherever else a harness would find it, which is where a `--dir` may have
        # put it: nobody's own folder, so said only where something is there.
        own = {place.directory for place in found}
        for profile in backends.profiles():
            for folder in _folders(profile):
                if folder in own or _state(folder / NAME / _CARD, "")[0] == "absent":
                    continue
                own.add(folder)
                found.append(_Place(None, folder))
    return found


def _once(places: Sequence[_Place]) -> list[_Place]:
    """The places, each folder once: what is written is written to a folder."""
    seen: dict[Path, _Place] = {}
    for place in places:
        # As the folder is, rather than as it is spelled: one linked to another is that one.
        seen.setdefault(place.directory.resolve(), place)
    return list(seen.values())


def _state(card: Path, version: str) -> tuple[str, str | None]:
    """What is where the skill goes, and the version of hmz that wrote it where one did.

    Returns:
      `absent` for nothing there, `foreign` for anything `hmz skills add` did not write,
      else `current` for a skill of this version and `older` for one of any other.
    """
    import yaml

    skill = card.parent
    if not skill.is_symlink() and not skill.exists():
        return "absent", None
    try:
        text = card.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # An empty folder is nobody's; anything else in the way is somebody's.
        with contextlib.suppress(OSError):
            if skill.is_dir() and not any(skill.iterdir()):
                return "absent", None
        return "foreign", None
    front: Any = None
    lines = [one.rstrip() for one in text.split("\n")]
    if lines[0] == _FENCE and _FENCE in lines[1:]:
        with contextlib.suppress(yaml.YAMLError):
            front = yaml.safe_load("\n".join(lines[1 : lines.index(_FENCE, 1)]))
    said = cast("dict[str, Any]", front) if isinstance(front, dict) else {}
    kept: Any = said.get("metadata")
    meta = cast("dict[str, Any]", kept) if isinstance(kept, dict) else {}
    if meta.get(_BY) != _MARK:
        return "foreign", None
    wrote = str(meta.get(_VERSION) or "")
    return ("current" if wrote == version else "older"), wrote or None


def _foreign(place: _Place) -> Exception:
    from hmz.sdk import Refused

    return Refused(
        t(
            "{path} holds a skill named hmz that hmz did not write, so it was left as "
            "it is.",
            path=place.card.parent,
        )
    )


def _add(call: Call) -> None:
    from hmz.coganchor import atomic
    from hmz.sdk import Refused

    version = _version()
    places = _once(_places(call, installed=True))
    if not places:
        raise Refused(
            t(
                "No harness is installed here. Name a harness with `--for` or a folder "
                "with `--dir`."
            )
        )
    # All of them looked at before any is written: a line refused has changed nothing.
    for place in places:
        if _state(place.card, version)[0] == "foreign":
            raise _foreign(place)
    files = _rendered()
    written: list[dict[str, Any]] = []
    lines: list[str] = []
    for place in places:
        skill = place.card.parent
        skill.mkdir(parents=True, exist_ok=True)
        changed = False
        for name, text in files.items():
            at = skill / name
            if not at.is_file() or at.read_bytes() != text.encode():
                # Whole or not at all: a harness starting now reads one or the other.
                atomic.writes(at, text)
                changed = True
        if _REFERENCE not in files and (skill / _REFERENCE).is_file():
            # What an hmz with more commands put beside it, which this one links nowhere.
            (skill / _REFERENCE).unlink()
            changed = True
        written.append(
            {"harness": place.harness, "path": str(place.card), "changed": changed}
        )
        lines.append(
            t("Installed: {path}", path=place.card)
            if place.harness is None
            else t(
                "Installed for {harness}: {path}",
                harness=place.harness,
                path=place.card,
            )
        )
    call.answers({"version": version, "written": written}, lines)


def _list(call: Call) -> None:
    version = _version()
    harnesses: list[dict[str, Any]] = []
    rows: list[list[str]] = []
    for place in _places(call, installed=False):
        state, wrote = _state(place.card, version)
        harnesses.append(
            {
                "harness": place.harness,
                "installed": place.installed,
                "directory": str(place.directory),
                "path": str(place.card),
                "state": state,
                "version": wrote,
            }
        )
        name = place.harness or "-"
        rows.append(
            [
                name if place.installed else t("{name} (not installed)", name=name),
                str(place.directory),
                t(_STATES[state]),
            ]
        )
    call.answers({"version": version, "harnesses": harnesses}, table(rows))


def _asked(place: _Place) -> bool:
    """Whether the person at the terminal says to remove one."""
    print(
        f"{t('Remove {name}?', name=place.card.parent)} [y/N] ", end="", file=sys.stderr
    )
    sys.stderr.flush()
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def _remove(call: Call) -> None:
    from hmz.sdk import Refused

    version = _version()
    named = bool(getattr(call.given, "for")) or call.dir is not None
    found: list[_Place] = []
    for place in _once(_places(call, installed=False)):
        state, _ = _state(place.card, version)
        if state == "foreign" and named:
            raise _foreign(place)
        if state in ("current", "older"):
            found.append(place)
    if found and not call.yes and (call.json or not sys.stdin.isatty()):
        raise Refused(t("Removing asks first. Run it again with `--yes`."))
    removed: list[dict[str, Any]] = []
    lines: list[str] = []
    for place in found:
        if not call.yes and not _asked(place):
            continue
        skill = place.card.parent
        # What `add` writes and nothing else: whatever somebody put beside it is theirs,
        # and keeps the folder it is in.
        for name in (_CARD, _REFERENCE):
            (skill / name).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            skill.rmdir()
        removed.append({"harness": place.harness, "path": str(place.card)})
        lines.append(t("Removed: {path}", path=place.card))
    call.answers(
        {"removed": removed}, lines if found else [t("No hmz skill is installed.")]
    )


def _show(call: Call) -> None:
    files = _rendered()
    call.answers(
        {
            "name": NAME,
            "version": _version(),
            "files": [{"name": name, "text": text} for name, text in files.items()],
        },
        [files[_CARD].removesuffix("\n")],
    )


def path(said: str) -> Path:
    """The folder a `--dir` names, which names one: not nothing, and not nobody's home."""
    if not said:
        raise ValueError(said)
    try:
        return Path(said).expanduser().absolute()
    except RuntimeError as why:
        raise ValueError(said) from why


_DIR: Final = Arg(
    ("--dir",),
    "a skills folder to use instead of any harness's own; the skill is the folder `hmz` "
    "inside it",
    metavar="PATH",
    kind=path,
)
_FOR: Final = Arg(
    ("--for",),
    "only this harness, by the name `hmz skills list` prints",
    metavar="HARNESS",
    many=True,
)
_HARNESS: Final = Field(
    "",
    "string|null",
    "the harness whose own skills folder it is, or null for any other folder (one given "
    "with `--dir`, or one several harnesses share)",
)
_WROTE: Final = Field("version", "string", "the version of hmz the skill is written by")

COMMANDS = (
    Command(
        "skills",
        "install, list and remove the hmz skill for using the CLI",
        says="The hmz skill is a `SKILL.md` telling a harness how to use the `hmz` "
        "command line. `hmz` installs no other skill and changes none of yours.",
        commands=(
            Command(
                "add",
                "write the hmz skill into each installed harness's skills folder",
                says="Writes the folder `hmz` into the user-level skills folder of "
                "every installed harness, or those named. Running it again replaces "
                "it, unless `hmz` did not write it.",
                args=(
                    Arg(
                        ("--for",),
                        "install for this harness only, by the name `hmz skills list` "
                        "prints (such as claude or codex), whether or not it is "
                        "installed",
                        metavar="HARNESS",
                        many=True,
                    ),
                    _DIR,
                ),
                examples=(
                    Example(
                        "hmz skills add",
                        "install the skill for every harness installed on this machine",
                    ),
                    Example(
                        "hmz skills add --for claude --for codex",
                        "install the skill for Claude Code and Codex only",
                    ),
                    Example(
                        "hmz skills add --dir ~/.agents/skills",
                        "install the skill into the skills folder several harnesses "
                        "share",
                    ),
                ),
                prints="One line per skill written, naming the harness and the path of "
                "its `SKILL.md`.",
                output=(
                    _WROTE,
                    Field("written", "list", "the skills written, one per folder"),
                    Field("written[].harness", _HARNESS.kind, _HARNESS.says),
                    Field(
                        "written[].path", "string", "the path of the `SKILL.md` written"
                    ),
                    Field(
                        "written[].changed",
                        "boolean",
                        "whether the file was written, false where it already held the "
                        "same text",
                    ),
                ),
                see=("skills list", "skills show"),
                run=_add,
                local=True,
            ),
            Command(
                "list",
                "show each harness's skills folder and the hmz skill's state",
                args=(_FOR, _DIR),
                examples=(
                    Example(
                        "hmz skills list",
                        "show where each harness keeps its skills and whether the hmz "
                        "skill is there",
                    ),
                    Example(
                        "hmz skills list --json | jq -r "
                        "'.harnesses[] | select(.state == \"older\") | .harness'",
                        "print the harnesses whose hmz skill was written by another "
                        "version of hmz",
                    ),
                ),
                prints="One line per harness: its name, its user-level skills folder, "
                "and whether the hmz skill there is current, older, not installed, or "
                "not written by hmz.",
                output=(
                    _WROTE,
                    Field(
                        "harnesses",
                        "list",
                        "every harness that has a user-level skills folder",
                    ),
                    Field(
                        "harnesses[].harness",
                        "string|null",
                        "the harness's name, as `--for` takes it, or null for a folder "
                        "that is not one harness's own (one given with `--dir`, or one "
                        "several harnesses share)",
                    ),
                    Field(
                        "harnesses[].installed",
                        "boolean",
                        "whether the harness itself is installed on this machine",
                    ),
                    Field(
                        "harnesses[].directory",
                        "string",
                        "the harness's user-level skills folder",
                    ),
                    Field(
                        "harnesses[].path",
                        "string",
                        "where the hmz skill's `SKILL.md` is, or would be written",
                    ),
                    Field(
                        "harnesses[].state",
                        "string",
                        "one of `current` (written by this version of hmz), `older` "
                        "(written by another version), `absent` (not installed), or "
                        "`foreign` (a skill named hmz that hmz did not write)",
                    ),
                    Field(
                        "harnesses[].version",
                        "string|null",
                        "the version of hmz that wrote the installed skill, or null "
                        "where there is none",
                    ),
                ),
                see=("skills add", "skills remove"),
                run=_list,
                local=True,
            ),
            Command(
                "remove",
                "remove the hmz skill that `hmz skills add` wrote",
                says="Removes the hmz skill wherever `hmz skills add` wrote it, or "
                "from the harnesses named. Asks first unless `--yes` is given. Never "
                "removes a skill `hmz` did not write.",
                args=(_FOR, _DIR, Arg(("-y", "--yes"), "remove without asking first")),
                examples=(
                    Example(
                        "hmz skills remove",
                        "remove the hmz skill from every harness, asking first",
                    ),
                    Example(
                        "hmz skills remove --for codex --yes",
                        "remove the hmz skill from Codex without asking",
                    ),
                ),
                prints="One line per skill removed, with its path.",
                output=(
                    Field("removed", "list", "the skills removed"),
                    Field("removed[].harness", _HARNESS.kind, _HARNESS.says),
                    Field(
                        "removed[].path", "string", "the path of the `SKILL.md` removed"
                    ),
                ),
                see=("skills list", "skills add"),
                run=_remove,
                local=True,
            ),
            Command(
                "show",
                "print the `SKILL.md` that `hmz skills add` would write",
                examples=(
                    Example("hmz skills show", "print the skill without installing it"),
                    Example(
                        "hmz skills show --json | jq -r '.files[].name'",
                        "print the names of the files the skill is made of",
                    ),
                ),
                prints="The text of `SKILL.md` as it would be written.",
                output=(
                    Field("name", "string", "the skill's name, which is `hmz`"),
                    _WROTE,
                    Field(
                        "files",
                        "list",
                        "the files the skill is made of, `SKILL.md` first",
                    ),
                    Field(
                        "files[].name",
                        "string",
                        "the file's name inside the skill's folder",
                    ),
                    Field("files[].text", "string", "the file's whole text"),
                ),
                see=("skills add",),
                run=_show,
                local=True,
            ),
        ),
    ),
)
