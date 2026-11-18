"""An environment's git repository, as its Changes panel reads and changes it.

Every command runs in the environment, through its driver's `exec`, as `/bin/sh -c` with a
script fixed here and everything a frontend said -- paths, a message, a ref -- passed as its
arguments: nothing typed reaches a shell as code. Git runs with `--no-optional-locks` and
`GIT_OPTIONAL_LOCKS=0`, so that looking at a repository never takes a lock an agent working
in it then trips on, with no pager and no prompt, and with `core.quotepath=off`, so that a
path is the path rather than an escaped one.

Paths are relative to the root of the repository, which is what `git status` says them as.
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

__all__ = [
    "DIFF_CAP",
    "Exec",
    "GitError",
    "commit",
    "diff",
    "discard",
    "log",
    "parse_log",
    "parse_renames",
    "parse_status",
    "root",
    "stage",
    "status",
    "unstage",
]

#: How a command is run in the environment: an argv, in its workdir, answered with the exit
#: status, stdout and stderr.
type Exec = Callable[[Sequence[str]], Awaitable[tuple[int, str, str]]]

#: How large a side of a diff may be, in bytes, before it is said as binary rather than sent.
DIFF_CAP = 8 << 20

#: What every script starts with: the environment git is run under, and `g` for git in the
#: repository the first argument names. A path is a file's name, never a pattern.
_PRELUDE = (
    "export GIT_OPTIONAL_LOCKS=0 GIT_PAGER=cat GIT_TERMINAL_PROMPT=0 GIT_EDITOR=: "
    "GIT_LITERAL_PATHSPECS=1; "
    'root=$1; shift; g() { git --no-optional-locks -c core.quotepath=off -C "$root" "$@"; }; '
)

#: Says one side of a diff: `n` for nothing there, `big` for too large, or `y` and the
#: bytes in base64 -- for `=path` the index (stage 0, else ours), for `@path` the worktree,
#: and otherwise the object named.
_SIDE = (
    "side() { "
    'case "$1" in '
    '"") echo n ;; '
    '@*) f="$root/${1#@}"; '
    'if [ -L "$f" ]; then echo y; readlink "$f" | tr -d "\\n" | base64; '
    'elif [ -f "$f" ]; then s=$(wc -c < "$f" | tr -d " "); '
    f'if [ "$s" -gt {DIFF_CAP} ]; then echo big; else echo y; base64 < "$f"; fi; '
    "else echo n; fi ;; "
    '*) o=""; '
    'case "$1" in "="*) for one in ":0:${1#=}" ":2:${1#=}"; do '
    'if g cat-file -e "$one" 2>/dev/null; then o=$one; break; fi; done ;; '
    '*) if g cat-file -e "$1" 2>/dev/null; then o=$1; fi ;; esac; '
    'if [ -z "$o" ]; then echo n; '
    f'elif [ "$(g cat-file -s "$o")" -gt {DIFF_CAP} ]; then echo big; '
    'else echo y; g cat-file blob "$o" | base64; fi ;; '
    "esac; echo .; }; "
    'side "$1"; side "$2"'
)

#: How much of what git said when it refused is said on.
_SAID = 2000

#: How much of a file git itself reads to call it binary.
_SNIFF = 8000


class GitError(Exception):
    """Git said no, in its own words; or the environment's workdir is not in a repository."""


async def _git(exec_: Exec, top: str, body: str, *args: str) -> str:
    """Runs one script against the repository at `top`, answering its stdout.

    Raises:
      GitError: If it exited non-zero, with what git said.
    """
    code, out, err = await exec_(["/bin/sh", "-c", _PRELUDE + body, "sh", top, *args])
    if code != 0:
        said = err.strip() or out.strip() or f"git exited {code}"
        raise GitError(said[:_SAID])
    return out


async def root(exec_: Exec) -> str:
    """The root of the repository the workdir is in.

    Raises:
      GitError: If it is in none.
    """
    out = await _git(exec_, ".", 'g rev-parse --show-toplevel "$@"')
    return out.strip()


def parse_status(text: str, top: str) -> dict[str, Any]:
    """`git status --porcelain=v2 -z --branch`, as `env.git.status` answers it.

    Args:
      text: What git printed.
      top: The root of the repository.

    Returns:
      `root`, `branch` (None when detached), `head` (None before the first commit),
      `upstream`, `ahead`, `behind` and `files`: each with `path`, `orig` for a rename or a
      copy, `index` and `worktree` (the XY characters) and `state`.
    """
    said: dict[str, Any] = {
        "root": top,
        "branch": None,
        "head": None,
        "upstream": None,
        "ahead": 0,
        "behind": 0,
        "files": [],
    }
    files: list[dict[str, Any]] = said["files"]
    records = text.split("\0")
    at = 0
    while at < len(records):
        line = records[at]
        at += 1
        if not line:
            continue
        kind = line[0]
        if kind == "#":
            _header(said, line)
        elif kind == "1":
            fields = line.split(" ", 8)
            files.append(_file(fields[8], fields[1], "changed"))
        elif kind == "2":
            fields = line.split(" ", 9)
            orig = records[at] if at < len(records) else ""
            at += 1
            files.append(_file(fields[9], fields[1], "changed") | {"orig": orig})
        elif kind == "u":
            fields = line.split(" ", 10)
            files.append(_file(fields[10], fields[1], "conflict"))
        elif kind == "?":
            files.append(_file(line[2:], "??", "untracked"))
    return said


def _header(said: dict[str, Any], line: str) -> None:
    _, key, *rest = line.split(" ", 2)
    value = rest[0] if rest else ""
    if key == "branch.oid":
        said["head"] = None if value == "(initial)" else value
    elif key == "branch.head":
        said["branch"] = None if value == "(detached)" else value
    elif key == "branch.upstream":
        said["upstream"] = value
    elif key == "branch.ab":
        ahead, _, behind = value.partition(" ")
        said["ahead"] = abs(int(ahead or 0))
        said["behind"] = abs(int(behind or 0))


def _file(path: str, xy: str, state: str) -> dict[str, Any]:
    return {"path": path, "index": xy[0], "worktree": xy[1], "state": state}


async def status(exec_: Exec, top: str) -> dict[str, Any]:
    """The repository's branch and every file that differs, as :func:`parse_status` says."""
    out = await _git(
        exec_, top, 'g status --porcelain=v2 -z --branch --untracked-files=all "$@"'
    )
    return parse_status(out, top)


def parse_renames(text: str) -> dict[str, str]:
    """`git diff --name-status -z`, as where each renamed or copied path came from."""
    fields = text.split("\0")
    renamed: dict[str, str] = {}
    at = 0
    while at < len(fields):
        kind = fields[at]
        at += 1
        if not kind:
            continue
        if kind[0] in "RC" and at + 1 < len(fields):
            renamed[fields[at + 1]] = fields[at]
            at += 2
        else:
            at += 1
    return renamed


def _sides(text: str) -> list[tuple[bytes | None, bool]]:
    """What :data:`_SIDE` printed: each side's bytes, or None, and whether it was too large."""
    sides: list[tuple[bytes | None, bool]] = []
    lines = text.split("\n")
    at = 0
    while at < len(lines) and len(sides) < 2:  # noqa: PLR2004
        mark = lines[at].strip()
        at += 1
        if not mark:
            continue
        body: list[str] = []
        while at < len(lines) and lines[at].strip() != ".":
            body.append(lines[at])
            at += 1
        at += 1
        if mark == "y":
            try:
                sides.append((base64.b64decode("".join(body)), False))
            except (binascii.Error, ValueError):
                sides.append((None, True))
        else:
            sides.append((None, mark == "big"))
    while len(sides) < 2:  # noqa: PLR2004
        sides.append((None, False))
    return sides


async def diff(exec_: Exec, top: str, path: str, *, staged: bool) -> dict[str, Any]:
    """Both sides of one file's change: the index and the worktree, or `HEAD` and the index.

    Returns:
      `old` and `new` in base64, each None where the file is not on that side -- or too
      large to send -- and `binary`, where either side is.
    """
    if staged:
        orig = path
        if (
            await _git(exec_, top, "g rev-parse -q --verify HEAD >/dev/null || echo no")
        ).strip() != "no":
            renames = parse_renames(
                await _git(exec_, top, 'g diff --cached -M -z --name-status "$@"')
            )
            orig = renames.get(path, path)
        old_spec, new_spec = f"HEAD:{orig}", f"={path}"
    else:
        old_spec, new_spec = f"={path}", f"@{path}"
    out = await _git(exec_, top, _SIDE, old_spec, new_spec)
    (old, old_big), (new, new_big) = _sides(out)
    binary = (
        old_big
        or new_big
        or any(one is not None and b"\0" in one[:_SNIFF] for one in (old, new))
    )
    return {
        "old": None if old is None else base64.b64encode(old).decode(),
        "new": None if new is None else base64.b64encode(new).decode(),
        "binary": binary,
    }


def parse_log(text: str) -> list[dict[str, Any]]:
    """`git log -z` in the format :func:`log` asks for, as `env.git.log` answers it."""
    commits: list[dict[str, Any]] = []
    for one in text.split("\0"):
        fields = one.strip("\n").split("\x1f")
        if len(fields) < 5:  # noqa: PLR2004
            continue
        commit, parents, author, date, subject = fields[:5]
        commits.append(
            {
                "hash": commit,
                "parents": parents.split(),
                "author": author,
                "date": date,
                "subject": subject,
            }
        )
    return commits


async def log(exec_: Exec, top: str, limit: int) -> list[dict[str, Any]]:
    """The newest `limit` commits of `HEAD`, none before the first."""
    out = await _git(
        exec_,
        top,
        "if g rev-parse -q --verify HEAD >/dev/null; then "
        'g log -z -n "$1" --format=%H%x1f%P%x1f%an%x1f%aI%x1f%s; fi',
        str(limit),
    )
    return parse_log(out)


async def stage(exec_: Exec, top: str, paths: Sequence[str]) -> None:
    """Stages paths whole: changed, new and deleted alike."""
    await _git(exec_, top, 'g add -A -- "$@"', *paths)


async def unstage(exec_: Exec, top: str, paths: Sequence[str]) -> None:
    """Puts paths in the index back as `HEAD` has them; before the first commit, out of it."""
    await _git(
        exec_,
        top,
        "if g rev-parse -q --verify HEAD >/dev/null; "
        'then g restore --staged -- "$@"; '
        'else g rm --cached -r -q --ignore-unmatch -- "$@"; fi',
        *paths,
    )


async def discard(exec_: Exec, top: str, paths: Sequence[str]) -> None:
    """Throws away the worktree's changes to paths: tracked restored, untracked removed.

    What is tracked is put back as the index has it, and what is untracked is removed -- a
    directory holding both, both.
    """
    await _git(
        exec_,
        top,
        'for p in "$@"; do '
        'if [ -n "$(g ls-files -- "$p" | head -n 1)" ]; then '
        'g restore --worktree -- "$p" || exit; fi; '
        'g clean -f -d -q -- "$p" || exit; done',
        *paths,
    )


async def commit(exec_: Exec, top: str, message: str, *, amend: bool) -> str:
    """Commits what is staged -- or amends `HEAD` with it -- and answers the new `HEAD`."""
    args = ["--amend"] if amend else []
    args += ["-m", message] if message or not amend else ["--no-edit"]
    out = await _git(exec_, top, 'g commit -q "$@" && g rev-parse HEAD', *args)
    return out.strip().splitlines()[-1]
