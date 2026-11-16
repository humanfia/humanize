# ruff: noqa: INP001 -- a script beside the fixture it writes, not a package
"""Captures what Python's native `drive` asks of a `local:` target, for unit 13's Rust tests.

Run from the repository's root as `uv run python crates/coganchor/tests/fixtures/unit13_capture.py`.
It writes `unit13_drive.json` beside itself: the settings of one native turn, the files it
carried, and every `EXEC` the turn made in order -- the request, what was fed to its stdin,
and what the target answered -- so that the Rust drive can be given the same answers and be
checked to ask the same things. The environment is cleared first, so nothing of the machine
it is captured on lands in the fixture.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

# Fixed paths, so the fixture reads the same wherever it is captured.
ROOT = Path("/tmp/hmz-unit13")  # noqa: S108
WORKSPACE = "/coganchor-native"
SESSION = "/tmp/tmp.SESSION"  # noqa: S108
REFRESHED = '{"tokens": {"access_token": "a2", "refresh_token": "r2"}}\n'
CLI = (
    'printf %s "$REFRESHED" > "$CODEX_HOME/auth.json.tmp" && '
    'mv "$CODEX_HOME/auth.json.tmp" "$CODEX_HOME/auth.json"; '
    'mkdir -p "$CODEX_HOME/sessions" && echo turn > "$CODEX_HOME/sessions/one.jsonl"; '
    'cat; echo "to stderr" >&2; exit 3'
)


def hexed(data: bytes) -> str:
    """Bytes as the fixture holds them."""
    return data.hex()


def scrubbed(packed: bytes) -> bytes:
    """An archive as the target wrote it, its owners' names and extended attributes taken out."""
    out = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(packed)) as reading,
        tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as writing,
    ):
        for member in reading:
            member.uname, member.gname, member.uid, member.gid = (
                "user",
                "group",
                1000,
                1000,
            )
            member.pax_headers = {}
            data = reading.extractfile(member) if member.isreg() else None
            writing.addfile(member, data)
    return out.getvalue()


def main() -> None:
    """Takes one native turn on a `local:` target, recording it, and writes the fixture."""
    from hmz.coganchor import remote
    from hmz.coganchor.anchor import AnchorConfig, drive
    from hmz.coganchor.homes import Virtual

    shutil.rmtree(ROOT, ignore_errors=True)
    (ROOT / "target").mkdir(parents=True)
    (ROOT / "home").mkdir()
    (ROOT / "tell").mkdir()
    files = {
        "creds/auth.json": '{"tokens": {"access_token": "a1", "refresh_token": "r1"}}\n',
        "creds/config.toml": 'model = "o3"\n',
        "creds/nested/notes.txt": "kept\n",
        "skills/review/SKILL.md": "---\nname: review\n---\n",
        "skills/review/run.sh": "#!/bin/sh\necho review\n",
        "home/.codex/settings.json": "{}\n",
    }
    for name, said in files.items():
        (ROOT / name).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / name).write_text(said)
    (ROOT / "creds/auth.json").chmod(0o600)
    (ROOT / "skills/review/run.sh").chmod(0o755)
    home = Virtual(
        variable="CODEX_HOME",
        default=".codex",
        rewrites=("config.toml",),
        lodges="skills",
        private=("sessions",),
        skills=(("review", str(ROOT / "skills/review")),),
    )
    config = AnchorConfig(
        target=f"local:{ROOT / 'target'}",
        workspace=WORKSPACE,
        native=True,
        hushes=("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
        projects=(("CODEX_HOME", str(ROOT / "creds")),),
        home=home,
        brings=(("CODEX_HOME/sessions", str(ROOT / "brought")),),
        tells=str(ROOT / "tell"),
    )
    command = ["/bin/sh", "-c", CLI]

    environ = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(ROOT / "home"),
        "LANG": "C",
        "ANTHROPIC_API_KEY": "sk-the-actual-secret",
        "REFRESHED": REFRESHED,
    }
    os.environ.clear()
    os.environ.update(environ)

    exchanges: list[dict[str, object]] = []
    by_id: dict[int, dict[str, object]] = {}
    start_exec = remote.RemoteClient.start_exec

    def recorded(self, argv, cwd, env, on_output, on_exit, **options):  # noqa: ANN001, ANN003, ANN202
        held: dict[str, object] = {
            "request": {
                "argv": argv,
                "program": options.get("program"),
                "cwd": cwd,
                "env": env,
                "tty": options.get("tty", False),
                "winsize": options.get("winsize"),
                "fence": options.get("fence"),
            },
            "stdin": b"",
            "stdout": b"",
            "stderr": b"",
        }
        exchanges.append(held)

        def output(stream, data):  # noqa: ANN001, ANN202
            key = "stderr" if stream is remote.Stream.STDERR else "stdout"
            held[key] += data
            on_output(stream, data)

        def done(result, error):  # noqa: ANN001, ANN202
            held["result"] = result
            held["error"] = None if error is None else [error.errno, str(error)]
            on_exit(result, error)

        handle = start_exec(self, argv, cwd, env, output, done, **options)
        by_id[handle.msg_id] = held
        return handle

    send_stdin = remote.ExecHandle.send_stdin

    def fed(self, data):  # noqa: ANN001, ANN202
        by_id[self.msg_id]["stdin"] += data
        send_stdin(self, data)

    remote.RemoteClient.start_exec = recorded
    remote.ExecHandle.send_stdin = fed

    read, write = os.pipe()
    os.write(write, b"from stdin\n")
    os.close(write)
    os.dup2(read, 0)
    status = drive(command, config)

    # The turn's private directory is named for the user it was made by: said as a fixed one.
    session = next(
        held["stdout"] for held in exchanges if "mktemp" in held["request"]["argv"][2]
    )
    for held in exchanges:
        if held["stdout"] and "tar cf" in held["request"]["argv"][2]:
            held["stdout"] = scrubbed(held["stdout"])
        held["request"] = json.loads(
            json.dumps(held["request"]).replace(session.decode(), SESSION)
        )
        for key in ("stdin", "stdout", "stderr"):
            held[key] = hexed(held[key].replace(session, SESSION.encode()))
    fixture = {
        "root": str(ROOT),
        "workspace": WORKSPACE,
        "target": f"local:{ROOT / 'target'}",
        "command": command,
        "environ": environ,
        "hushes": list(config.hushes),
        "home": json.loads(home.dumps()),
        "files": files,
        "status": status,
        "written_back": (ROOT / "creds/auth.json").read_text(),
        "brought": sorted(
            str(one.relative_to(ROOT / "brought"))
            for one in (ROOT / "brought").rglob("*")
        ),
        "exchanges": exchanges,
    }
    out = Path(sys.argv[0]).resolve().parent / "unit13_drive.json"
    out.write_text(json.dumps(fixture, indent=1) + "\n")
    shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
