"""A sign-in that refreshes itself: which files are one, and who may hold one at once.

Every turn here that uses such a sign-in in place shares it; a turn about to send a copy to
another machine takes it alone. Each is a lock in this process on a directory of the test's
own, so nothing here spawns anything or reaches a CLI.
"""

from __future__ import annotations

import errno
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor._lending import lent, refreshing

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def signed_in(tmp_path: Path) -> Path:
    """An account's home holding a sign-in that refreshes itself, beside one that does not."""
    home = tmp_path / "home"
    (home / "credentials").mkdir(parents=True)
    (home / "auth.json").write_text('{"tokens": {"refresh_token": "r"}}')
    (home / "credentials" / "kimi-code.json").write_text('{"refreshToken": "r"}')
    (home / "key.json").write_text('{"OPENAI_API_KEY": "sk-a-key"}')
    return home


def test_a_sign_in_is_known_by_its_refresh_token_in_any_spelling(
    signed_in: Path, tmp_path: Path
) -> None:
    (tmp_path / "opencode.json").write_text(
        '{"anthropic": {"type": "oauth", "refresh": "r"}}'
    )

    assert refreshing([str(signed_in), str(tmp_path / "opencode.json")]) == {
        str(signed_in / "auth.json"),
        str(signed_in / "credentials" / "kimi-code.json"),
        str(tmp_path / "opencode.json"),
    }
    # Not inside a directory where it may be a CLI's sessions rather than its credentials.
    assert refreshing([str(signed_in)], inside=False) == frozenset()
    assert refreshing([str(signed_in / "auth.json")], inside=False) == {
        str(signed_in / "auth.json")
    }


def test_turns_using_a_sign_in_in_place_share_it(signed_in: Path) -> None:
    files = refreshing([str(signed_in)])

    with lent(files, away=False), lent(files, away=False):
        pass


def test_no_copy_goes_out_while_a_turn_here_is_using_it(signed_in: Path) -> None:
    files = refreshing([str(signed_in)])

    with (
        lent(files, away=False),
        pytest.raises(OSError, match="refreshes itself") as refused,
        lent(files, away=True),
    ):
        pass

    assert refused.value.errno == errno.EBUSY
    assert "signs in with a token that refreshes itself" in str(refused.value)


def test_no_turn_uses_it_while_a_copy_is_out(signed_in: Path) -> None:
    files = refreshing([str(signed_in)])

    with lent(files, away=True):
        with (
            pytest.raises(OSError, match="out on another machine") as here,
            lent(files, away=False),
        ):
            pass
        with (
            pytest.raises(OSError, match="another turn is using it") as away,
            lent(files, away=True),
        ):
            pass

    assert here.value.errno == away.value.errno == errno.EBUSY
    assert "out on another machine" in str(here.value)
    # And once it is back, it is anybody's again.
    with lent(files, away=True):
        pass


def test_an_account_that_is_keys_is_held_by_nothing(signed_in: Path) -> None:
    keys = refreshing([str(signed_in / "key.json")])

    assert keys == frozenset()
    with lent(keys, away=True), lent(keys, away=True):
        pass
