# A script beside the crate's tests, not a module of any package.
# ruff: noqa: INP001
"""Writes unit07_targets.json: what Python's transport makes of many target spellings.

Run from the repository root, and commit what it writes beside it:

    HUMANIZE_SSH_REUSE=off uv run python crates/coganchor/tests/unit07_targets.py

`tests/unit07_targets.rs` reads the file and checks the Rust port makes the same of each:
the same spelling back, the same fields, the same road and the same refusals.
"""

import json
import pathlib

from hmz.coganchor.transport import Road, Target

SPELLINGS = [
    "local",
    "local:",
    "local:/w/real",
    "local:rel dir",
    "ssh://box",
    "ssh://box:2201",
    "ssh://me@box",
    "ssh://me@box:22",
    "ssh://me@jump@box:22",
    "ssh://@box",
    "ssh://box:0",
    "ssh://[::1]:22",
    "ssh://[::1]",
    "ssh://box:port",
    "ssh://",
    "ssh://:22",
    "ssh://box?F=/etc/ssh/cfg",
    "ssh://box?IdentityFile=~/.ssh/id_x&ProxyJump=me@jump:2222",
    "ssh://box?User=a%20b",
    "ssh://box?User=a+b",
    "ssh://box?ProxyCommand=ssh%20-W%20%25h:%25p%20jump",
    "ssh://box?Opt=caf%C3%A9",
    "ssh://box?Opt=%C3",
    "ssh://box?Opt=x%zz",
    "ssh://box?Opt=a&b=c",
    "ssh://box?Opt=a&&b=c",
    "ssh://box?Opt=",
    "ssh://box?1Opt=x",
    "ssh://box?Op_t=x",
    "ssh://box?Opt=a%22b",
    "ssh://box?Opt=a%0Ab",
    "ssh://box?Opt=a=b",
    "ssh://box?Opt=x#frag",
    "ssh://box?",
    "docker://c1",
    "docker://c1@local",
    "docker://c1@",
    "docker://@local",
    "docker://",
    "docker://c1@unix:///var/run/docker.sock",
    "docker://c1@unix://rel",
    "docker://c1@tcp://10.0.0.1:2375",
    "docker://c1@tcp://10.0.0.1:2376?tls=/certs",
    "docker://c1@tcp://10.0.0.1:2376?tls=certs",
    "docker://c1@tcp://10.0.0.1",
    "docker://c1@tcp://[::1]:2375",
    "docker://c1@ssh://me@daemon",
    "docker://c1@ssh://me@daemon:2222",
    "docker://c1@ssh://daemon/path",
    "docker://c1@ssh://@",
    "docker://c1@context:prod",
    "docker://c1@context:",
    "docker://c1@nowhere",
    "docker://c1?user=1000",
    "docker://c1?user=1000:1000",
    "docker://c1?user=me",
    "docker://c1?user=1&user=2",
    "docker://c1?env=A=1&env=B=two%20words",
    "docker://c1?env=1A=x",
    "docker://c1?env=A",
    "docker://c1?exec=tini&exec=--",
    "docker://c1?exec=",
    "docker://c1?exec=a%40b",
    "docker://c1?exec=a+b",
    "docker://c1?shell=sh",
    "docker://c1?user=1000&env=PATH=/x:/y&exec=nice@tcp://h:1",
    "docker://c1?user=1000@context:ci",
    "apple-container://box",
    "apple-container://",
    "apple-container://a/b",
    "apple-container://a@b",
    "apple-container://a?b",
    "slurm://12345",
    "slurm://12345?python=/opt/py/bin/python3",
    "slurm://12345?python=~/py/bin/python3",
    "slurm://12345?python=rel/python",
    "slurm://12345?python=/a%20b/python",
    "slurm://12345?python=/a&x=y",
    "slurm://12345?python=",
    "slurm://12x",
    "slurm://",
    "tcp://127.0.0.1:7000",
    "tcp://host.example:1",
    "tcp://[::1]:7000",
    "tcp://host",
    "tcp://:7000",
    "tcp://host:",
    "peer://abc@broker:9000",
    "peer://abc@[::1]:9000",
    "peer://a@b@broker:9000",
    "peer://@broker:9000",
    "peer://abc@broker",
    "peer://abc@:9000",
    "peer://abc",
    "http://x",
    "",
    "box",
    "SSH://box",
]


def entry(spelling: str) -> dict[str, object]:
    """What Python's transport makes of one spelling, or the error it refuses it with."""
    try:
        target = Target.parse(spelling)
    except ValueError as error:
        return {"said": spelling, "error": str(error)}
    found: dict[str, object] = {
        "said": spelling,
        "describe": target.describe(),
        "scheme": target.scheme,
        "host": target.host,
        "port": target.port,
        "path": target.path,
        "options": [list(pair) for pair in target.options],
    }
    if target.scheme in ("tcp", "peer"):
        return found
    road = Road.to(target)
    found["cache"] = road.cache
    found["mirrors"] = road.mirrors
    found["owned"] = road.owned
    # A docker endpoint with ssh options names a shim under this machine's temporary
    # directory, which the Rust tests check on their own.
    if not (target.scheme == "docker" and target.endpoint.options):
        found["line"] = road.line(["prog", "a b", "it's"])
    return found


here = pathlib.Path(__file__).with_name("unit07_targets.json")
here.write_text(
    json.dumps([entry(one) for one in SPELLINGS], indent=1, ensure_ascii=False) + "\n"
)
