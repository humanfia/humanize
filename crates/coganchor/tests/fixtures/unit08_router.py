# ruff: noqa: INP001, S108  -- a script beside its fixture; the paths are only compared.
"""Writes `unit08_router.json`: what Python's `Router` answers, for the Rust port to match.

Run from the repository's root, and commit what it writes:

    uv run python crates/coganchor/tests/fixtures/unit08_router.py

Each case is a router's settings, the platform its target says (`""` for none yet), and
what every path of `PATHS` and every text of `TEXTS` comes to under it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hmz.coganchor.policy import Layout, Router

CONFIGS: list[dict[str, Any]] = [
    {"layouts": [["/srv/mirror", "/work"]]},
    {"layouts": [["/m", None]]},
    {"layouts": [["/m", "/w"], ["/m/inner", "/elsewhere"]]},
    {"layouts": [["/tmp/m", "/w"]]},
    {"layouts": [["/private/var/m/", "/w"]]},
    {"layouts": [["/", "/root-of-target"]]},
    {"layouts": [["/Straße/m", "/w"]]},
    {"layouts": [["/strasse/m", "/w"]]},
    {
        "layouts": [["/srv/mirror", "/work"]],
        "aliases": [["/work", "/srv/mirror"], ["/home/me/proj/", "/srv/mirror"]],
        "local_paths": ["/work/.state", "/srv/mirror/.cache", "/home/me/.hmz"],
        "local_programs": ["/work/bin/agent", "/opt/agent", "/srv/mirror"],
    },
    {
        "layouts": [["/home/me/.hmz/mirror", "/w"]],
        "local_paths": ["/home/me/.hmz", "/home/me/.hmz/mirror"],
    },
    {
        "layouts": [["/m", "/w"]],
        "local_paths": ["/m/.state"],
        "redirects": [
            ["/h/.c", "/p/all"],
            ["/h/.c/creds.json", "/p/creds.json"],
            ["/h/state_*.db", "/p/state_*.db"],
            ["/h/projects/*/chats", "/s/projects/*/chats"],
            ["/h//x/../y/", "/q"],
        ],
    },
]

PLATFORMS = ["", "linux", "darwin"]

PATHS = [
    "/",
    "/srv",
    "/srv/mirror",
    "/srv/mirror/a/B",
    "/SRV/Mirror/a/B",
    "/srv/mirrored",
    "/work",
    "/work/a",
    "/WORK/a",
    "/workshop",
    "/work/.state/x",
    "/srv/mirror/.state/x",
    "/srv/mirror/.STATE/x",
    "/srv/mirror/.cache",
    "/home/me/proj",
    "/home/me/proj/x",
    "/home/me/.hmz/mirror/a",
    "/home/me/.hmz/other",
    "/m",
    "/m/a",
    "/M/A",
    "/m/inner/a",
    "/m/.state/x",
    "/m/.STATE/x",
    "/tmp/m/a",
    "/private/tmp/m/a",
    "/private/TMP/m/a",
    "/PRIVATE/tmp/m/a",
    "/var/m/x",
    "/private/var/m/x",
    "/private/var/x",
    "/Straße/m/x",
    "/STRASSE/m/x",
    "/strasse/m/x",
    "/straße/m/x",
    "/opt/agent/bin/node",
    "/opt/agentx",
    "/work/bin/agent",
    "/srv/mirror/bin/agent",
    "/h/.c",
    "/h/.c/creds.json",
    "/h/.c/creds.json.tmp",
    "/h/.c/other",
    "/h/.cx",
    "/h/.c.bak",
    "/h/state_5.db",
    "/h/state_5.db-wal",
    "/h/state_.db/in",
    "/h/projects/a/chats/1",
    "/h/projects/a/logs",
    "/h/y",
    "/h/y.z",
]

TEXTS = [
    "grep -r x /srv/mirror/src",
    "echo hello/srv/mirror",
    "cat /SRV/MIRROR/a",
    "ls /private/tmp/m/x /tmp/m",
    "cat /home/me/proj/a",
    "--flag=/m/a:/m/inner/b",
    "PATH=/m/bin:/usr/bin",
    "/Straße/m/a /STRASSE/m/b",
    "/private/var/m/x /var/m/y",
]


def build(config: dict[str, Any], platform: str) -> Router:
    """The router `config` describes, for a target on `platform`."""
    return Router(
        layouts=tuple(
            Layout.create(local, virtual) for local, virtual in config["layouts"]
        ),
        aliases=tuple((name, root) for name, root in config.get("aliases", ())),
        local_paths=tuple(config.get("local_paths", ())),
        local_programs=tuple(config.get("local_programs", ())),
        redirects=tuple((a, b) for a, b in config.get("redirects", ())),
        platform=lambda: platform,
    )


def main() -> None:
    """Writes the fixture beside this script."""
    cases = []
    for config in CONFIGS:
        for platform in PLATFORMS:
            router = build(config, platform)
            paths = {
                path: {
                    "canonical": router.canonical(path),
                    "virtual": (
                        router.to_virtual(path) if router.is_remote_path(path) else None
                    ),
                    "runs_locally": router.runs_locally(path),
                    "swap": router.swap(path),
                }
                for path in PATHS
            }
            cases.append(
                {
                    "config": config,
                    "platform": platform,
                    "settles": router.settles,
                    "paths": paths,
                    "texts": {text: router.rewrite(text) for text in TEXTS},
                }
            )
    out = Path(__file__).with_suffix(".json")
    out.write_text(
        json.dumps(cases, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
