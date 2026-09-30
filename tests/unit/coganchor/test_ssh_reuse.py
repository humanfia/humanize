"""Whether every `ssh` humanize runs rides one connection to a host, as `HUMANIZE_SSH_REUSE` says.

Read the way humanize's other switches are: trimmed and in any case, off for `off`, `0`, `no`
or `false`, and on otherwise -- unset included. Set and empty is off as well.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import transport

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def afresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The answer not yet worked out, and its sockets kept where the test can see them."""
    monkeypatch.setattr(transport, "_reusing_held", None)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


def test_unset_it_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUMANIZE_SSH_REUSE", raising=False)

    assert "ControlMaster=auto" in transport._reuse()


@pytest.mark.parametrize(
    "said", ["off", "0", "no", "false", " NO ", "False", "OFF\n", ""]
)
def test_it_is_off_however_off_is_written(
    said: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_SSH_REUSE", said)

    assert transport._reuse() == ()


@pytest.mark.parametrize("said", ["1", "yes", " YES ", "on", "true"])
def test_anything_else_is_on(said: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUMANIZE_SSH_REUSE", said)

    assert "ControlMaster=auto" in transport._reuse()
