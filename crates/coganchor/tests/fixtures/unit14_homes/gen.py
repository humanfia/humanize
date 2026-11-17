"""Writes `expected.json`: what Python's virtual homes make of each case in `cases.json`.

Run from the repository's root as
`uv run python crates/coganchor/tests/fixtures/unit14_homes/gen.py`.
`tests/unit14_differential.rs` does the same with the Rust port and compares, so a home built
and dropped by either side is the same tree: the same files, the same bytes, the same links.

For each case: the files of `user` are laid out under a fresh root, the home is built from the
`Virtual` said (its `dumps`, which is what the Rust side reads), the built tree is listed, the
`session`'s changes are made, the home is dropped, and the whole root is listed again. Paths
are said with `{root}`, `{at}` and `{home}` in place of the root, the home and its name.
"""

# ruff: noqa: INP001 -- a script beside its fixtures, not a package

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from hmz.coganchor.homes import Virtual, build

HERE = Path(__file__).resolve().parent

#: The time a file is given where its case says none: one before, one after the session.
BEFORE = 1_600_000_000
AFTER = 1_700_000_000


def placed(said: str, root: str, at: str = "{at}") -> str:
    """`said` with its placeholders filled in."""
    return said.replace("{root}", root).replace("{at}", at)


def unplaced(said: str, root: str, at: str) -> str:
    """`said` with the root and the home named as placeholders, the home's own name too."""
    said = said.replace(at, "{at}").replace(root, "{root}")
    return said.replace(Path(at).name, "{home}") if at != "{at}" else said


def timed(path: Path, seconds: int) -> None:
    """Gives a file a time of its own, so that both sides list the same one."""
    ns = seconds * 1_000_000_000
    os.utime(path, ns=(ns, ns))


def lay(root: Path, entries: list[dict[str, Any]]) -> None:
    """Lays out a case's files, links and databases under `root`."""
    for one in entries:
        path = root / one["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if "link" in one:
            path.symlink_to(placed(one["link"], str(root)))
        elif "sql" in one:
            with sqlite3.connect(path) as connection:
                for statement in one["sql"]:
                    connection.execute(placed(statement, str(root)))
            connection.close()
        else:
            path.write_text(one["text"], encoding="utf-8")
            path.chmod(one.get("mode", 0o644))
            timed(path, one.get("mtime", BEFORE))


def act(root: Path, at: Path, ops: list[dict[str, Any]]) -> None:
    """Makes a session's changes, as a CLI in the home would."""
    for op in ops:
        path = Path(placed(op["path"], str(root), str(at)))
        kind = op["op"]
        if kind == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(op["text"], encoding="utf-8")
            timed(path, op.get("mtime", AFTER))
        elif kind == "rename_over":
            beside = path.with_name(f".{path.name}.tmp")
            beside.write_text(op["text"], encoding="utf-8")
            timed(beside, op.get("mtime", AFTER))
            beside.replace(path)
        elif kind == "replace_dir":
            beside = path.with_name(f"{path.name}.tmp")
            for name, file in op["files"].items():
                (beside / name).parent.mkdir(parents=True, exist_ok=True)
                (beside / name).write_text(file["text"], encoding="utf-8")
                timed(beside / name, file.get("mtime", AFTER))
            path.unlink()
            beside.rename(path)
        elif kind == "sql":
            with sqlite3.connect(path) as connection:
                for statement in op["sql"]:
                    connection.execute(placed(statement, str(root), str(at)))
            connection.close()
        else:
            raise ValueError(kind)


def listed(top: Path, root: str, at: str, *, times: bool) -> dict[str, dict[str, Any]]:
    """Every entry under `top`, links not followed, as the Rust side lists it."""
    out: dict[str, dict[str, Any]] = {}
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            rel = str(path.relative_to(top))
            if path.is_symlink():
                out[rel] = {"link": unplaced(str(path.readlink()), root, at)}
            elif path.is_dir():
                out[rel] = {"dir": True}
            elif name.endswith(".sqlite") and path.read_bytes()[:6] == b"SQLite":
                out[rel] = {"sqlite": dumped(path, root, at)}
            elif ".sqlite-" in name:
                continue
            else:
                data = path.read_bytes()
                st = path.lstat()
                one: dict[str, Any] = {"mode": st.st_mode & 0o7777}
                try:
                    one["text"] = unplaced(data.decode("utf-8"), root, at)
                except UnicodeDecodeError:
                    one["hex"] = data.hex()
                # A database's time is whenever it was last written, which no case sets.
                if times and ".sqlite" not in name:
                    one["mtime"] = st.st_mtime_ns
                out[rel] = one
    return dict(sorted(out.items()))


def dumped(path: Path, root: str, at: str) -> dict[str, list[list[Any]]]:
    """Every row of every table of a database, in the order they were written."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [
            name
            for (name,) in connection.execute(
                "select name from sqlite_master where type = 'table' order by name"
            )
        ]
        return {
            table: [
                [unplaced(v, root, at) if isinstance(v, str) else v for v in row]
                for row in connection.execute(
                    f'select * from "{table}" order by rowid'  # noqa: S608 -- the case's own
                )
            ]
            for table in tables
        }
    finally:
        connection.close()


def virtual(said: dict[str, Any], root: str) -> Virtual:
    """The `Virtual` a case says, its merges' arguments said as `homes.merged` says them."""

    def text(one: object) -> object:
        if isinstance(one, str):
            return placed(one, root)
        if isinstance(one, list):
            return tuple(text(x) for x in one)
        return one

    kwargs = {key: text(value) for key, value in said.items() if key != "merges"}
    kwargs["merges"] = tuple(
        (name, json.dumps(arg)) for name, arg in said.get("merges", ())
    )
    return Virtual(**kwargs)  # pyright: ignore[reportArgumentType]


def run(case: dict[str, Any]) -> dict[str, Any]:
    """One case, built, changed and dropped by Python."""
    with tempfile.TemporaryDirectory() as made:
        root = Path(os.path.realpath(made))
        lay(root, case["user"])
        spec = virtual(case["virtual"], str(root))
        dumps = spec.dumps()
        environ = {key: placed(value, str(root)) for key, value in case["env"].items()}
        try:
            home = build(Virtual.loads(dumps), environ, under=root)
        except Exception as error:  # noqa: BLE001 -- whatever it refuses with
            left = sorted(
                one.name for one in root.iterdir() if one.name.startswith("hmz-home-")
            )
            return {
                "dumps": unplaced(dumps, str(root), "{at}"),
                "error": type(error).__name__,
                "left": left,
            }
        at = str(home.at)
        result = {
            "dumps": unplaced(dumps, str(root), at),
            "sets": [[key, unplaced(value, str(root), at)] for key, value in home.sets],
            "argv": [unplaced(one, str(root), at) for one in home.argv],
            "linked": sorted(home.linked),
            "built": listed(home.at, str(root), at, times=False),
        }
        act(root, home.at, case["session"])
        home.drop()
        result["at_left"] = home.at.exists()
        result["dropped"] = listed(root, str(root), at, times=True)
        return result


def main() -> None:
    """Runs every case and writes what came of each."""
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    os.umask(0o022)
    expected = {case["name"]: run(case) for case in cases}
    (HERE / "expected.json").write_text(
        json.dumps(expected, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sys.stdout.write(f"wrote {len(expected)} cases\n")


if __name__ == "__main__":
    main()
