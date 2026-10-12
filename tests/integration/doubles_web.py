"""What the web interface's integration tests share: the interface served, and a browser.

The interface is served over runs held in the test's own process, as `hmz web` serves it where
runs are not held apart, and answers on a thread of its own until the test is done. A browser
is a client speaking HTTP to it from this machine, one connection a request -- let in with the
key the address carries, or not -- and the stream of a run is read as a browser reads it, an
event at a time. The page itself, drawn by a real browser, is `tests/system/web`'s.
"""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import tarfile
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hmz.runtime.epic import JOURNAL
from hmz.web import listening

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    import pytest

    from hmz.web.site import Site

#: How long anything here waits for the interface before failing the test.
PATIENCE = 30.0


@contextlib.contextmanager
def served() -> Generator[Site]:
    """The web interface, answering on a thread of its own until the block ends."""
    with listening(apart=False) as site:
        threading.Thread(
            target=site.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
            name="hmz-web-test",
        ).start()
        try:
            yield site
        finally:
            site.shutdown()


@dataclass
class Answer:
    """What the interface answered one request with."""

    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        """The body, read as the JSON it is."""
        return json.loads(self.body)


@dataclass
class Browser:
    """A browser on this machine: what it names the server as, and the cookie it carries.

    Attributes:
      site: The interface it reaches.
      host: What its requests name the server as, which is the address's own by default.
      cookie: The cookie it carries, or "" before it is let in.
      at: Which loopback it connects to.
    """

    site: Site
    host: str = ""
    cookie: str = field(default="")
    at: str = "127.0.0.1"

    def signs_in(self) -> Answer:
        """Opens the address the interface printed, keeping the cookie it is handed."""
        query = urllib.parse.urlsplit(self.site.address).query
        answer = self.get(f"/?{query}")
        said = answer.headers.get("set-cookie", "")
        self.cookie = said.split(";", 1)[0]
        return answer

    def get(self, path: str, **headers: str) -> Answer:
        """Asks for one thing."""
        return self._asks("GET", path, None, headers)

    def post(self, path: str, body: Any = None, **headers: str) -> Answer:
        """Sends one thing, as the page's own script sends it unless `headers` say otherwise."""
        sent = {
            "Origin": f"http://{self._host()}",
            "Content-Type": "application/json",
        } | headers
        return self._asks("POST", path, json.dumps(body or {}).encode(), sent)

    def sends(self, path: str, body: bytes, name: str, **headers: str) -> Answer:
        """Sends a file as it is, named, as the page's own script sends an epic's archive."""
        sent = {
            "Origin": f"http://{self._host()}",
            "Content-Type": "application/vnd.hmz.epic+gzip",
            "X-Hmz-Filename": urllib.parse.quote(name),
        } | headers
        return self._asks("POST", path, body, sent)

    def _host(self) -> str:
        return self.host or f"127.0.0.1:{self.site.port}"

    def _asks(
        self, method: str, path: str, body: bytes | None, headers: dict[str, str]
    ) -> Answer:
        connection = http.client.HTTPConnection(
            self.at, self.site.port, timeout=PATIENCE
        )
        try:
            sent = {"Host": self._host()} | (
                {"Cookie": self.cookie} if self.cookie else {}
            )
            connection.request(method, path, body=body, headers=sent | headers)
            answer = connection.getresponse()
            return Answer(
                answer.status,
                {name.lower(): value for name, value in answer.getheaders()},
                answer.read(),
            )
        finally:
            connection.close()

    @contextlib.contextmanager
    def follows(
        self, last: str = "", *, workspace: str = ""
    ) -> Generator[Callable[[], tuple[str, str, Any]]]:
        """Listens to the runs' stream, as the page does, from where it last heard.

        Args:
          last: The id of the last event it heard, or "" for the start.
          workspace: Whose runs, or "" for those of where the interface was started.

        Yields:
          What gives the next event: its id, what it is, and what it carries.
        """
        connection = http.client.HTTPConnection(
            self.at, self.site.port, timeout=PATIENCE
        )
        headers = {"Host": self._host(), "Cookie": self.cookie}
        if last:
            headers["Last-Event-ID"] = last
        query = (
            f"?{urllib.parse.urlencode({'workspace': workspace})}" if workspace else ""
        )
        connection.request("GET", f"/api/held/stream{query}", headers=headers)
        stream = connection.getresponse()

        def next_event() -> tuple[str, str, Any]:
            ident = event = ""
            data: list[str] = []
            while True:
                line = stream.readline().decode().rstrip("\n")
                if line.startswith("id: "):
                    ident = line[len("id: ") :]
                elif line.startswith("event: "):
                    event = line[len("event: ") :]
                elif line.startswith("data: "):
                    data.append(line[len("data: ") :])
                elif not line and event:
                    return ident, event, json.loads("\n".join(data))

        try:
            yield next_event
        finally:
            connection.close()


def until(
    next_event: Callable[[], tuple[str, str, Any]],
    wanted: Callable[[str, Any], bool],
    what: str,
) -> tuple[str, Any]:
    """Reads the stream until an event is the one wanted.

    Args:
      next_event: What gives the next event.
      wanted: Whether an event, by what it is and what it carries, is the one.
      what: What is waited for, for the failure.

    Returns:
      Its id, and what it carries.

    Raises:
      AssertionError: If none comes in time.
    """
    ending = time.monotonic() + PATIENCE
    while time.monotonic() < ending:
        ident, event, data = next_event()
        if wanted(event, data):
            return ident, data
    raise AssertionError(f"the stream never said {what}")


def backed_up_elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """An epic run here and backed up to `t`, then this machine made one that has not got it.

    Another machine is a home of its own, sharing the workspace and the repository: what it
    has is a target `t` in its settings and nothing else.

    Returns:
      The epic's name.
    """
    import subprocess

    import yaml

    from hmz import home
    from hmz.runtime.epic import every
    from tests.integration.doubles_core import AGENT, hmz_exec

    bare = tmp_path / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    target = {"name": "t", "url": str(bare), "policies": ["end"]}

    def targets() -> None:
        home().mkdir(parents=True, exist_ok=True)
        said = {"backup": {"targets": [target], "defaults": []}}
        (home() / "settings.yaml").write_text(yaml.safe_dump(said))

    targets()
    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "--backup", "t", "hi")
    assert ran.returncode == 0, ran.stderr
    (name,) = [one.name for one in every()]
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "elsewhere"))
    targets()
    return name


def elsewhere(archive: Path, workspace: str, to: Path) -> Path:
    """A copy of an epic's archive whose run says it ran in another workspace.

    Args:
      archive: The `.hmzepic`.
      workspace: Where the copy says its run ran.
      to: The directory the copy is written into, under the archive's own name.

    Returns:
      The copy.
    """
    copy = to / archive.name
    with (
        tarfile.open(archive, "r:gz") as reading,
        tarfile.open(copy, "w:gz") as writing,
    ):
        for member in reading.getmembers():
            held = reading.extractfile(member)
            body = held.read() if held is not None else b""
            if member.name.endswith(f"/{JOURNAL}"):
                lines = [json.loads(line) for line in body.splitlines()]
                for line in lines:
                    if line.get("event") == "began":
                        line["workspace"] = workspace
                body = b"".join(json.dumps(line).encode() + b"\n" for line in lines)
                member.size = len(body)
            writing.addfile(member, io.BytesIO(body) if member.isfile() else None)
    return copy
