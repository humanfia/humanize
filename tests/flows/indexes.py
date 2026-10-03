"""Flowverse indexes, and the repositories the releases they list live in, written for a test.

A flowverse is an index: a git repository of `flows/<flow>/<version>/flow.yaml`, each naming a
repository, the commit a release was cut from and the directory of it the flow is in. So a test
that installs anything wants two kinds of repository -- one holding a flow's code, and one
listing releases of it -- and this writes both under the test's own temporary directory,
committed as an identity of their own, so that nothing depends on the git config of whoever is
running the suite and nothing is ever fetched from anywhere but this machine.

A helper rather than a test module, imported by path as `tests.flows.kit` is. Writing a
manifest needs no git at all, so the unit tier reads indexes this wrote as well; committing one
is the integration tier's.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import yaml

from hmz.runtime.flowing.index import RELEASE
from hmz.runtime.flowing.verses import FLOWS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = ["committed", "git", "listed", "manifest", "release"]

#: Who commits here: nobody's own identity, the same on every machine, and never signed --
#: a signing key somebody configured for their own repositories has no business here.
_WHO = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(at: Path, *said: str) -> str:
    """Runs one git command in a directory, failing the test if it fails.

    Args:
      at: The directory.
      said: The arguments, after `git -C <at>`.

    Returns:
      What it printed, without the whitespace around it.
    """
    return subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-C",
            str(at),
            *said,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_WHO},
    ).stdout.strip()


def committed(at: Path, message: str = "as it is now") -> str:
    """Commits everything in a directory, making a repository of it first if it is not one.

    Args:
      at: The directory, made if it is not there.
      message: What the commit says.

    Returns:
      The commit, written out in full -- which is what a manifest names.
    """
    if not (at / ".git").exists():
        at.mkdir(parents=True, exist_ok=True)
        git(at, "init", "--quiet", "-b", "main")
    git(at, "add", "-A")
    git(at, "commit", "--quiet", "--allow-empty", "-m", message)
    return git(at, "rev-parse", "HEAD")


def release(
    name: str, version: str, repo: str, commit: str, **more: object
) -> dict[str, object]:
    """What one release's manifest says: the four things every one says, and whatever else.

    Args:
      name: The flow.
      version: The release.
      repo: Where it lives -- a `file://` URL, here.
      commit: The commit it was cut from.
      more: The rest of what it says: `subdir`, `dependencies`, a key nobody knows.

    Returns:
      The manifest, as the mapping its YAML is.
    """
    return {"name": name, "version": version, "repo": repo, "commit": commit, **more}


def manifest(index: Path, flow: str, version: str, said: object) -> Path:
    """Writes one manifest where an index keeps it, whatever it says.

    Args:
      index: The index's own directory, which `flows/` is made under.
      flow: The directory of the flow it goes in.
      version: The directory of the version it goes in.
      said: What it says: YAML text as it is, or anything else dumped as YAML.

    Returns:
      The file.
    """
    at = index / FLOWS / flow / version / RELEASE
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        said if isinstance(said, str) else yaml.safe_dump(said, sort_keys=False),
        encoding="utf-8",
    )
    return at


def listed(index: Path, *releases: Mapping[str, object]) -> Path:
    """Writes releases into an index, each where its name and version say it goes.

    Args:
      index: The index's own directory.
      releases: The manifests, as :func:`release` makes them.

    Returns:
      The index's directory, to be committed or read.
    """
    for one in releases:
        manifest(index, str(one["name"]), str(one["version"]), dict(one))
    return index
