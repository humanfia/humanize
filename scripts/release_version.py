"""Which Python version a release tag stands for.

A release is a tag, and the tag is the only place its version is written: `v1.2.3` is the
release 1.2.3, `v1.2.3-rc.1` the first candidate for it. A tag says that in SemVer and a
Python package has to say it in PEP 440, so this reads one and writes the other, and the
release stamps what it writes into pyproject.toml before anything is built:

    uv run --no-project scripts/release_version.py v1.2.3-rc.1    # 1.2.3rc1

A tag it cannot say in PEP 440 -- a build suffix, a pre-release label PEP 440 has no word
for -- is refused with what a tag should look like, rather than turned into a version
nobody meant. Run by path and imported by nothing, so it uses nothing but the standard library.
"""

from __future__ import annotations

import re
import sys

#: `vMAJOR.MINOR.PATCH`, with no leading zeros, and at most one pre-release that PEP 440
#: also has a name for.
_TAG = re.compile(
    r"v(?P<release>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
    r"(?:-(?P<label>alpha|beta|rc)\.(?P<number>0|[1-9]\d*))?",
)

#: What PEP 440 calls each pre-release SemVer's tags may name.
_PRE = {"alpha": "a", "beta": "b", "rc": "rc"}


def pep440(tag: str) -> str:
    """The Python version a release tag stands for.

    Args:
      tag: The tag, such as `v1.2.3` or `v1.2.3-rc.1`.

    Returns:
      Its version, in PEP 440's normal form: `1.2.3`, `1.2.3rc1`.

    Raises:
      ValueError: If the tag is not one a release is cut from.
    """
    match = _TAG.fullmatch(tag)
    if match is None:
        message = (
            f"{tag!r} is not a release tag: tag vX.Y.Z, or vX.Y.Z-alpha.N, "
            "vX.Y.Z-beta.N or vX.Y.Z-rc.N for a pre-release"
        )
        raise ValueError(message)
    release, label, number = match.group("release", "label", "number")
    return release if label is None else f"{release}{_PRE[label]}{number}"


def main(argv: list[str]) -> int:
    """Prints the version the one tag given stands for.

    Args:
      argv: The arguments, less the program's name.

    Returns:
      0, or 2 if there was not one tag, or 1 if it is not a release tag.
    """
    if len(argv) != 1:
        print("usage: release_version.py vX.Y.Z[-(alpha|beta|rc).N]", file=sys.stderr)
        return 2
    try:
        print(pep440(argv[0]))
    except ValueError as refused:
        print(f"release_version.py: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
