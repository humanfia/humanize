"""`hmz.daemon.api.paths`: a path under an unknown user's home, and one of another machine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.daemon.api.paths import completed, listed, listed_there
from hmz.rpc import Code, RpcError
from hmz.runtime.doing import envs

if TYPE_CHECKING:
    from pathlib import Path

#: A user no machine has: a name `useradd` would refuse.
_NOBODY = "~no:such:user"


@pytest.mark.parametrize("typed", [f"{_NOBODY}/", f"{_NOBODY}/x"])
def test_a_path_typed_under_an_unknown_users_home_could_become_nothing(
    typed: str,
) -> None:
    assert completed(typed) == []


@pytest.mark.parametrize("at", [_NOBODY, f"{_NOBODY}/x"])
def test_a_directory_under_an_unknown_users_home_is_refused_404(at: str) -> None:
    with pytest.raises(RpcError) as refused:
        listed(at, files=False, hidden=False)
    assert refused.value.code == Code.NOT_FOUND
    assert at in refused.value.message


def test_a_directory_of_this_machine_is_listed_whatever_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "repo").mkdir()
    (tmp_path / "notes.md").write_text("notes\n")
    asked: list[tuple[str, str]] = []

    def browsed(env: str, at: str) -> None:
        # This machine's, as the runtime says of itself and of a container here.
        asked.append((env, at))

    monkeypatch.setattr(envs, "browsed", browsed)
    here = listed(str(tmp_path), files=False, hidden=False)

    assert listed_there("docker", str(tmp_path), files=False, hidden=False) == here
    assert asked == [("docker", str(tmp_path))]
    assert [one["name"] for one in here["entries"]] == ["repo"]


@pytest.mark.parametrize("code", [400, 404, 409])
def test_what_the_runtime_refuses_is_refused_with_its_code_and_its_words(
    code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def browsed(env: str, at: str) -> None:
        raise envs.EnvRefusal(code, f"{env} at {at}: no")

    monkeypatch.setattr(envs, "browsed", browsed)

    with pytest.raises(RpcError) as refused:
        listed_there("ssh@gpu-box", "~", files=False, hidden=False)
    assert (refused.value.code, refused.value.message) == (code, "ssh@gpu-box at ~: no")


def test_a_directory_of_another_machine_is_listed_as_this_machines_are(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def browsed(env: str, at: str) -> tuple[str, list[tuple[str, bool]]]:
        del env, at
        return "/home/me/work", [
            ("repo", True),
            (".cache", True),
            ("Link", True),
            ("notes.md", False),
        ]

    monkeypatch.setattr(envs, "browsed", browsed)

    # Directories alone, and nothing hidden; the way up is its parent.
    assert listed_there("ssh@gpu-box", "~/work", files=False, hidden=False) == {
        "at": "/home/me/work",
        "whole": "/home/me/work",
        "up": "/home/me",
        "entries": [{"name": "Link", "dir": True}, {"name": "repo", "dir": True}],
        "more": 0,
    }
    both = listed_there("ssh@gpu-box", "", files=True, hidden=True)
    assert [one["name"] for one in both["entries"]] == [
        ".cache",
        "Link",
        "repo",
        "notes.md",
    ]
