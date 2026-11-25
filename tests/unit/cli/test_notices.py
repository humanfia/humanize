"""`hmz notices`: the notices a daemon keeps listed, and new ones printed as they arrive."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from hmz.cli import main, tree

if TYPE_CHECKING:
    from collections.abc import Iterator

AT = 1767225600.0


@dataclass(frozen=True)
class Notice:
    """A notice as the SDK's family hands one over, stood in for."""

    id: int
    kind: str
    workspace: str
    slot: str
    epic: str
    chat: str
    flow: str
    task: str
    role: str
    text: str
    at: float


def _notice(id: int, kind: str = "done", **said: Any) -> Notice:  # noqa: A002
    fields: dict[str, Any] = {
        "id": id,
        "kind": kind,
        "workspace": "/w",
        "slot": "",
        "epic": "e1",
        "chat": "",
        "flow": "asks",
        "task": "plan the week",
        "role": "",
        "text": "",
        "at": AT,
        **said,
    }
    return Notice(**fields)


def _when() -> str:
    return f"{datetime.datetime.fromtimestamp(AT).astimezone():%Y-%m-%d %H:%M:%S}"


@pytest.fixture
def notices(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The notices family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    return client.notices


def test_notices_are_listed_a_line_each_in_the_pages_words(
    notices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    notices.kept.return_value = (
        [
            _notice(7, "asked", text="## Which day?\nmore", role="planner"),
            _notice(8, "done", epic="", chat="c1", slot="chat:ab", flow="chat"),
        ],
        8,
    )

    assert main(["notices", "list"]) == 0

    assert capsys.readouterr().out == (
        f"7  {_when()}  Question  e1  Which day?\n"
        f"8  {_when()}  Done      c1  plan the week\n"
    )
    notices.kept.assert_called_once_with(None)


def test_the_list_is_narrowed_by_kind_and_says_the_newest_whatever_it_shows(
    notices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    notices.kept.return_value = ([_notice(7, "asked"), _notice(8, "failed")], 9)

    line = ["notices", "list", "--after", "6", "--kind", "asked", "--kind", "stopped"]
    assert main([*line, "--json"]) == 0

    said = json.loads(capsys.readouterr().out)
    assert [one["id"] for one in said["notices"]] == [7]
    assert said["notices"][0] == {
        "id": 7,
        "kind": "asked",
        "workspace": "/w",
        "slot": "",
        "epic": "e1",
        "chat": "",
        "flow": "asks",
        "task": "plan the week",
        "role": "",
        "text": "",
        "at": AT,
    }
    assert said["last"] == 9
    notices.kept.assert_called_once_with(6)


def test_with_nothing_kept_after_the_newest_it_is_still_said(
    notices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    notices.kept.return_value = ([], 41)

    assert main(["notices", "list", "--after", "41", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"notices": [], "last": 41}

    assert main(["notices", "list"]) == 0
    assert capsys.readouterr().out == ""


def test_a_kind_that_is_none_is_a_line_that_cannot_be_read(notices: mock.Mock) -> None:
    with pytest.raises(SystemExit) as unread:
        main(["notices", "list", "--kind", "finished"])

    assert unread.value.code == 2
    notices.kept.assert_not_called()


def _interrupted(*told: Notice) -> Iterator[Notice]:
    yield from told
    raise KeyboardInterrupt


def test_following_prints_each_notice_until_it_is_interrupted(
    notices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    notices.follow.return_value = _interrupted(
        _notice(7, "asked", text="Which day?"), _notice(8, "failed", text="no key")
    )

    assert main(["notices", "follow", "--after", "6"]) == 130

    assert capsys.readouterr().out == (
        f"7  {_when()}  Question  e1  Which day?\n8  {_when()}  Failed  e1  no key\n"
    )
    notices.follow.assert_called_once_with(6)


def test_following_as_json_is_a_document_a_line_of_the_kinds_wanted(
    notices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    notices.follow.return_value = _interrupted(
        _notice(7, "asked", text="Which day?"), _notice(8, "failed", text="no key")
    )

    assert main(["notices", "follow", "--kind", "failed", "--json"]) == 130

    (line,) = capsys.readouterr().out.splitlines()
    assert json.loads(line)["id"] == 8
    assert json.loads(line)["text"] == "no key"
    notices.follow.assert_called_once_with(None)


def test_following_a_daemon_that_went_ends_as_a_daemon_unreached(
    notices: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    notices.follow.side_effect = ConnectionError(
        "the session with the daemon has ended"
    )

    assert main(["notices", "follow"]) == 3

    assert "hmz notices follow: " in capsys.readouterr().err
