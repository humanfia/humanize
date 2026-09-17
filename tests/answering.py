"""What each backend answers when it is asked what it runs, and how it is asked.

Every backend here is a stand-in first on PATH printing what the real one prints, and every
gateway is a server on the loopback answering what a real one answers: nothing is written
down, so what a test can check is that each backend's own way of being asked is read the way
that backend answers it.

Here rather than in a conftest for the reason `tests/stubs.py` gives -- a conftest is a pytest
plugin rather than a module to import from -- and here rather than inside one test module
because asking a backend splits across two tiers. Asking a CLI is a stand-in on PATH and a
process of its own, which CI runs; asking it *as an account* is a supervised turn, which needs
a kernel that will hand over a tracee and so is left out of CI. The two halves are
`tests/integration/backends/test_models.py` and `tests/system/backends/test_models.py`, and a
stand-in written down twice is a backend's answer that gets corrected in one copy.
"""

from __future__ import annotations

import contextlib
import json
import os
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@pytest.fixture(autouse=True)
def no_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leaves no endpoint of whoever is running this suite for a test to go and ask.

    Asking one is right, and reaching anybody's network from a suite is not. Every base URL
    a backend would read is taken away here, so a test about the asking asks a loopback
    server it started itself and every other one falls back to its stand-in CLI.

    Autouse, but only where it is imported: a module that reaches for `stands_in` or
    `endpoint` and forgets this one keeps whoever's `ANTHROPIC_BASE_URL` is set on the
    machine running the suite, and `models.ask` will go and ask it. Import it beside them.
    """
    for profile in backends.PROFILES:
        if profile.endpoint:
            monkeypatch.delenv(profile.endpoint, raising=False)


#: What Claude Code answers the control request with: the default under its own name as well
#: as under `default`, a window written on the end of an id, and one model that takes no
#: effort at all.
CLAUDE = json.dumps(
    {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "models",
            "response": {
                "models": [
                    {
                        "value": "default",
                        "resolvedModel": "claude-nine[1m]",
                        "supportedEffortLevels": ["low", "high", "max"],
                    },
                    {
                        "value": "claude-nine[1m]",
                        "resolvedModel": "claude-nine",
                        "supportedEffortLevels": ["low", "high", "max"],
                    },
                    {"value": "haiku", "resolvedModel": "claude-quick"},
                ]
            },
        },
    }
)

#: What Claude answers when somebody has set `ANTHROPIC_CUSTOM_MODEL_OPTION` themselves. The
#: resolved id is deliberately a different name: the alias is the one they chose and the one
#: `--model` takes, so it is the one a catalogue keeps.
CLAUDE_CUSTOM = json.dumps(
    {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "models",
            "response": {
                "models": [
                    {
                        "value": "fable",
                        "resolvedModel": "claude-fable-5",
                        "description": "Custom model (fable)",
                        "supportedEffortLevels": ["high", "max"],
                    }
                ]
            },
        },
    }
)

#: What `codex debug models` renders: the efforts per model, and the ones it does not offer.
CODEX = json.dumps(
    {
        "models": [
            {
                "slug": "gpt-nine",
                "visibility": "list",
                "supported_reasoning_levels": [
                    {"effort": "low"},
                    {"effort": "high"},
                    {"effort": "ultra"},
                ],
            },
            {
                "slug": "gpt-eight",
                "visibility": "list",
                "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}],
            },
            {
                "slug": "gpt-hidden",
                "visibility": "hide",
                "supported_reasoning_levels": [{"effort": "low"}],
            },
        ]
    }
)

#: What `kimi provider list --json` dumps: the models are the keys, and only some of them say
#: which efforts they take.
KIMI = json.dumps(
    {
        "providers": {"managed:kimi-code": {"type": "kimi"}},
        "models": {
            "kimi-code/kthree": {
                "provider": "managed:kimi-code",
                "supportEfforts": ["low", "high", "max"],
            },
            "kimi-code/kold": {"provider": "managed:kimi-code"},
        },
    }
)

#: What `pi --list-models` prints, which is a table with the columns named across the top.
PI = """\
provider      model     context  max-out  thinking  images
openai-codex  gpt-nine  272K     128K     yes       yes
anthropic     opus-ten  200K     64K      yes       yes
"""

#: What `agy models` prints: a slug and the name its own picker shows, two columns a line --
#: and the slug carries the effort, since it lists a model at three efforts as three models.
AGY = """gemini-nine-high	Gemini Nine (High)
gemini-nine-low	Gemini Nine (Low)
claude-sonnet-nine	Claude Sonnet Nine (Thinking)
"""

#: What `zcode app-server --stdio` answers `workspace/readState` with. Its command line has no
#: `models`: a model there belongs to a provider its configuration names, and the app server is
#: what resolves the one into the other. The thought levels are the model's own, and its models
#: really do have two vocabularies of them.
ZCODE = (
    json.dumps(
        {
            "id": "server-1",
            "method": "interaction/requestOfficialMcpAuthHeaders",
            "params": {"mcpKey": "image_search"},
        }
    )
    + "\n"
    + json.dumps(
        {
            "id": 1,
            "result": {
                "modelCatalog": {
                    "available": [
                        {
                            "ref": {"providerId": "zai", "modelId": "glm-nine"},
                            "label": "GLM Nine",
                            "reasoning": {
                                "enabled": True,
                                "levels": [
                                    {"value": "low", "label": "low"},
                                    {"value": "high", "label": "high"},
                                    {"value": "max", "label": "max"},
                                ],
                            },
                        },
                        {
                            "ref": {"providerId": "zai", "modelId": "glm-quick"},
                            "label": "GLM Quick",
                            "reasoning": {
                                "enabled": True,
                                "levels": [
                                    {"value": "enabled", "label": "enabled"},
                                    {"value": "disabled", "label": "disabled"},
                                ],
                            },
                        },
                    ]
                }
            },
        }
    )
    + "\n"
)

#: What `opencode models` prints, and what `mimo models` prints, which is the same list with
#: the size of each written after it.
OPENCODE = "opencode/big-pickle\nopencode/small-pickle\n"
MIMO = "mimo/mimo-auto — window 1M, compacts at 960K\nopenai/gpt-nine — window 272K\n"


def stands_in(
    monkeypatch: pytest.MonkeyPatch,
    at: Path,
    name: str,
    prints: str,
    *,
    code: int = 0,
    says: str = "",
) -> Path:
    """Puts a backend of that name first on PATH, printing what the real one would print.

    Args:
      monkeypatch: What puts it on PATH, and takes it off again afterwards.
      at: The directory to keep it in.
      name: What the backend is called, since that is what is run.
      prints: What it prints where anybody would read it.
      code: What it exits with.
      says: What it prints where the trouble goes.

    Returns:
      The program, which also writes down the arguments and the environment it was given.
    """
    at.mkdir(parents=True, exist_ok=True)
    program = at / name
    program.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"json.dump({{'argv': sys.argv[1:], 'env': dict(os.environ), "
        "'said': sys.stdin.read()}, "
        f"open({str(at / f'{name}.seen')!r}, 'w'))\n"
        f"sys.stdout.write({prints!r})\n"
        f"sys.stderr.write({says!r})\n"
        f"raise SystemExit({code})\n"
    )
    program.chmod(0o755)
    monkeypatch.setenv("PATH", f"{at}{os.pathsep}{os.environ['PATH']}")
    return program


def seen(at: Path, name: str) -> dict[str, object]:
    """What the stand-in was run with."""
    return json.loads((at / f"{name}.seen").read_text())


#: What an OpenAI-shaped `/v1/models` answers with, which is the shape an Anthropic-shaped one
#: answers in too: the ids under `data`, route-prefixed the way a gateway in front of several
#: clouds writes them. The empty one is what a list with a hole in it looks like.
SERVED = json.dumps(
    {
        "object": "list",
        "data": [
            {"id": "azure/anthropic/claude-haiku-4-5", "object": "model"},
            {"id": "azure/openai/gpt-5.6-sol", "object": "model"},
            {"id": "", "object": "model"},
        ],
    }
)


@contextlib.contextmanager
def endpoint(
    body: str, *, status: int = 200, moved: str = ""
) -> Generator[tuple[str, list[list[str]]]]:
    """One endpoint on the loopback, answering that and writing down what it was asked.

    Args:
      body: What it answers with.
      status: What it answers it under.
      moved: Where it sends the first request instead, for an endpoint that redirects. The
        one after it is answered, so that a redirect it is right to follow lands somewhere.

    Yields:
      Where it is, and one `[path, authorization]` per request it took.
    """
    asked: list[list[str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            asked.append([self.path, self.headers.get("Authorization", "")])
            sending = moved and len(asked) == 1
            said = body.encode()
            self.send_response(302 if sending else status)
            if sending:
                self.send_header("Location", moved)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(said)))
            self.end_headers()
            self.wfile.write(said)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Nothing: a suite is not somewhere a web server keeps a log."""

    class Serving(ThreadingHTTPServer):
        """The same, without the reverse lookup it names itself by.

        On a machine whose resolver has nothing to say about `127.0.0.1` that lookup blocks
        for the resolver's own timeout, which is half a minute.
        """

        def server_bind(self) -> None:
            socketserver.TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name, self.server_port = str(host), int(port)

    running = Serving(("127.0.0.1", 0), Handler)
    reader = threading.Thread(target=running.serve_forever, daemon=True)
    reader.start()
    try:
        yield f"http://127.0.0.1:{running.server_port}", asked
    finally:
        running.shutdown()
        running.server_close()
        reader.join(timeout=2)
