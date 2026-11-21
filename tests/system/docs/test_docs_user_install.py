"""The pictures of `docs/user/install.md`: the app's first launch on Windows, its update, and `hmz`.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_install.py`.

Two things are staged here that the world does not come with:

- an install of a release. This checkout says it is `hmz 0.0.0`, installed from its own
  directory, which `hmz update` refuses, naming that directory. A release installed from PyPI
  is stood in for by its metadata alone (`hmz-<version>.dist-info`), put where every Python the
  stage starts looks first, beside a `uv` on `PATH` that is never run, since the release
  staged is the newest; the code that runs is this checkout's.
- the app's launch and update windows at the size of a small window, said to be the Windows
  app: what they show while `hmz` is installed in WSL is shown on Windows alone, so no macOS
  window is drawn around them. `shots` draws the splash at the size the app opens at, in the
  macOS window, and does not draw the update's window, so both are drawn here out of its parts.
"""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.system.docs import shots

_PAGE = "user-install"

#: The release the pictures say is installed, and is the newest.
_RELEASE = "0.9.2"

#: The app's own pages (`desktop/ui/app`): its splash, and its update's window.
_APP = Path(__file__).resolve().parents[3] / "desktop" / "ui" / "app"

#: What the Windows app's window says it is (`chrome.rs`).
_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    f" Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0 humanize-desktop/{_RELEASE}"
)

#: A window of the app, smaller than it opens at and no smaller than it may be made.
_SMALL = (800, 520)

#: The update's window, as the app opens it (`update.rs`).
_UPDATE = (400, 104)


@pytest.fixture
def released(monkeypatch: pytest.MonkeyPatch) -> str:
    """Stages `hmz` as a release installed from PyPI, which PyPI says is the newest."""
    site = Path(os.environ["PYTHONPATH"])
    told = site / f"hmz-{_RELEASE}.dist-info"
    told.mkdir()
    (told / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: hmz\nVersion: {_RELEASE}\n"
    )
    pypi = site.parent / "pypi.json"
    pypi.write_text(json.dumps({"info": {"version": _RELEASE}}))
    monkeypatch.setenv("HUMANIZE_RELEASES", str(pypi))
    # What would install a newer one, were there one: found on `PATH`, and never run here.
    tools = site.parent / "tools"
    tools.mkdir()
    (tools / "uv").write_text("#!/bin/sh\nexit 1\n")
    (tools / "uv").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    return _RELEASE


def _launch(defs: shots._Defs, state: str, detail: Any) -> shots._Frame:
    """One frame of the app's launch window on Windows, in one state (see `shots.splash`)."""
    return shots._draw(
        shots._Sheet(
            *_SMALL,
            address=(_APP / "index.html").as_uri(),
            init=shots._status(state, detail),
            agent=_WINDOWS,
            ready=f"main[data-state={state}]",
        ),
        defs,
    )


def _updating(defs: shots._Defs, title: str, percent: int | None) -> shots._Frame:
    """One frame of the update's window, told what the app tells it (`update.js`)."""
    said = json.dumps({"title": title, "percent": percent})
    return shots._draw(
        shots._Sheet(
            *_UPDATE,
            address=(_APP / "update.html").as_uri(),
            init=(
                "addEventListener('DOMContentLoaded', () => {"
                f" draw({said}); document.body.dataset.told = '1' }})"
            ),
            agent=_WINDOWS,
            ready="body[data-told]",
        ),
        defs,
    )


def test_the_version_is_printed(released: str) -> None:
    shots.cli(["hmz", "--version"], f"{_PAGE}-version", columns=56)


def test_an_update_finds_the_newest_release_installed(released: str) -> None:
    shots.cli(["hmz", "update"], f"{_PAGE}-update", columns=56)


def test_the_first_launch_on_windows_installs_the_cli() -> None:
    reel = shots.Reel(f"{_PAGE}-first-launch")
    reel._add(_launch(reel._defs, "starting", None), 1.2)
    for step, line in (
        ("uv", "Downloading uv 0.12.24"),
        ("python", "Downloading cpython-3.13.7-linux-x86_64-gnu"),
        ("hmz", "Resolved 64 packages in 412ms"),
        ("hmz", f"Installed hmz=={_RELEASE}"),
    ):
        reel._add(
            _launch(
                reel._defs,
                "installing",
                {"updating": False, "step": step, "line": line},
            ),
            1.3,
        )
    reel.save()


def test_an_update_waits_for_running_epics() -> None:
    defs = shots._Defs()
    shots._still(f"{_PAGE}-update-waiting", _launch(defs, "waiting", "0.9.1"), defs)


def test_a_check_for_updates_shows_how_far_it_is() -> None:
    reel = shots.Reel(f"{_PAGE}-check-for-updates")
    reel._add(_updating(reel._defs, "Checking for Updates…", None), 1.4)
    for percent in (18, 62, 100):
        reel._add(
            _updating(reel._defs, "Downloading Humanize Desktop 0.9.3…", percent), 1.1
        )
    reel.save()
