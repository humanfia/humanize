"""`hmz update`: this install moved to the newest release, by whatever installed it.

The releases, the daemon, the installed metadata and every installer run are stand-ins.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

import hmz.cli.update
import hmz.coganchor
import hmz.daemon
from hmz.cli import main
from hmz.coganchor import releases

if TYPE_CHECKING:
    from pathlib import Path

#: What `hmz` requires, as its installed metadata says.
_REQUIRES = [
    "pyyaml>=6",
    "hmz[dsh,kimi,litellm] ; extra == 'all'",
    "python-dotenv>=1 ; extra == 'dsh'",
    "websockets>=15 ; extra == 'kimi'",
    "litellm>=1 ; extra == 'litellm'",
]


def _extras(_: str) -> list[str]:
    return ["all", "dsh", "kimi", "litellm"]


def _on_path(name: str) -> str | None:
    return f"/bin/{name}"


def _nowhere(_: str) -> None:
    return None


def _pip(_: str) -> object:
    return object()


class _Installed:
    """The installed `hmz`, as `importlib.metadata` reads it."""

    def __init__(self, source: dict[str, Any] | None = None) -> None:
        self.requires = _REQUIRES
        self.metadata = SimpleNamespace(get_all=_extras)
        self._source = source

    def read_text(self, name: str) -> str | None:
        assert name == "direct_url.json"
        return json.dumps(self._source) if self._source else None


class _World:
    """Everything `hmz update` asks, and every line it ran."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, prefix: Path) -> None:
        self.ran: list[list[str]] = []
        self.installed: _Installed | None = _Installed()
        self.there = {"hmz", "pyyaml", "websockets"}
        self.after = "0.3.0"
        self.exits = 0
        self.daemons: list[Any] = []
        monkeypatch.setattr(sys, "prefix", str(prefix))
        monkeypatch.setattr(hmz.coganchor, "__version__", "0.2.0", raising=False)
        monkeypatch.setattr(releases, "fetch", lambda: "0.3.0")
        monkeypatch.setattr(hmz.daemon, "daemons", lambda: self.daemons)
        monkeypatch.setattr(hmz.cli.update, "distribution", self._distribution)
        monkeypatch.setattr(subprocess, "run", self._run)
        monkeypatch.setattr(shutil, "which", _on_path)

    def _distribution(self, name: str) -> Any:
        from importlib.metadata import PackageNotFoundError

        if name == "hmz" and self.installed is not None:
            return self.installed
        if name != "hmz" and name in self.there:
            return SimpleNamespace()
        raise PackageNotFoundError(name)

    def _run(self, line: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if line[0] == sys.executable and line[1] == "-c":
            return subprocess.CompletedProcess(line, 0, f"{self.after}\n", "")
        self.ran.append(line)
        return subprocess.CompletedProcess(line, self.exits)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _World:
    return _World(monkeypatch, tmp_path)


def test_a_uv_tool_is_upgraded_by_uv(
    world: _World, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "uv-receipt.toml").touch()
    assert main(["update"]) == 0
    assert world.ran == [["/bin/uv", "tool", "upgrade", "hmz"]]
    assert "Updated hmz to 0.3.0" in capsys.readouterr().out


def test_a_pipx_install_is_upgraded_by_pipx(world: _World, tmp_path: Path) -> None:
    (tmp_path / "pipx_metadata.json").touch()
    assert main(["update"]) == 0
    assert world.ran == [["/bin/pipx", "upgrade", "hmz"]]


def test_an_environment_is_upgraded_with_the_extras_it_has(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", _pip)
    assert main(["update"]) == 0
    assert world.ran == [
        [sys.executable, "-m", "pip", "install", "--upgrade", "hmz[kimi]"]
    ]


def test_an_environment_without_pip_is_upgraded_by_uv(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", _nowhere)
    world.there |= {"python-dotenv", "litellm"}
    assert main(["update"]) == 0
    assert world.ran == [
        [
            "/bin/uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--upgrade",
            "hmz[dsh,kimi,litellm]",
        ]
    ]


def test_the_newest_release_is_left_alone(
    world: _World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "uv-receipt.toml").touch()
    monkeypatch.setattr(hmz.coganchor, "__version__", "0.3.0", raising=False)
    assert main(["update"]) == 0
    assert world.ran == []
    assert capsys.readouterr().out == "hmz 0.3.0 is the newest release\n"


@pytest.mark.parametrize(
    "source",
    [
        {"url": "file:///src/humanize", "dir_info": {"editable": True}},
        {"url": "https://github.com/humanfia/humanize", "vcs_info": {}},
    ],
)
def test_an_install_from_a_source_is_that_sources_to_move(
    world: _World, capsys: pytest.CaptureFixture[str], source: dict[str, Any]
) -> None:
    world.installed = _Installed(source)
    assert main(["update"]) == 1
    assert world.ran == []
    assert f"installed from {source['url']}, not PyPI" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("url", "said"),
    [
        (
            "git+https://x-access-token:ghs_abcdefghijkl@github.com/o/r.git@main",
            "git+https://github.com/o/r.git@main",
        ),
        (
            "https://pkgs.example:8443/hmz.whl?private_token=glpat-abc#sha256=00",
            "https://pkgs.example:8443/hmz.whl",
        ),
        ("https://[::1/x", "a URL that could not be read"),
    ],
)
def test_an_install_url_is_said_without_what_was_signed_into_it(
    world: _World, capsys: pytest.CaptureFixture[str], url: str, said: str
) -> None:
    world.installed = _Installed({"url": url, "vcs_info": {}})
    assert main(["update"]) == 1
    err = capsys.readouterr().err
    assert f"installed from {said}, not PyPI" in err
    assert "ghs_" not in err
    assert "glpat" not in err


def test_no_install_at_all_is_refused(
    world: _World, capsys: pytest.CaptureFixture[str]
) -> None:
    world.installed = None
    assert main(["update"]) == 1
    assert "not installed" in capsys.readouterr().err


def test_an_installer_not_on_path_is_said(
    world: _World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "uv-receipt.toml").touch()
    monkeypatch.setattr(shutil, "which", _nowhere)
    assert main(["update"]) == 1
    assert "uv installed hmz but is not on PATH" in capsys.readouterr().err


def test_pypi_unreachable_is_said(
    world: _World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "uv-receipt.toml").touch()
    monkeypatch.setattr(releases, "fetch", lambda: None)
    assert main(["update"]) == 1
    assert world.ran == []
    assert "PyPI could not be asked" in capsys.readouterr().err


def test_an_installer_failing_is_said(
    world: _World, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "uv-receipt.toml").touch()
    world.exits = 2
    assert main(["update"]) == 1
    assert "/bin/uv exited 2" in capsys.readouterr().err


def test_an_install_left_behind_is_said(
    world: _World, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "uv-receipt.toml").touch()
    world.after = "0.2.0"
    assert main(["update"]) == 1
    assert "left hmz at 0.2.0, not 0.3.0" in capsys.readouterr().err


def test_the_daemon_running_the_old_release_is_said(
    world: _World, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "uv-receipt.toml").touch()
    world.daemons = [SimpleNamespace(pid=4242)]
    assert main(["update"]) == 0
    assert "(pid 4242) run hmz 0.2.0" in capsys.readouterr().out


def test_help_takes_nothing_else(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["update", "--help"])
    assert raised.value.code == 0
    assert capsys.readouterr().out.startswith("usage: hmz update")
