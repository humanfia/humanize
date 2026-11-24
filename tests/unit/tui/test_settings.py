"""`hmz.tui.settings`: which page of `/settings` a word opens, and the groups the pages are in."""

from __future__ import annotations

import pytest

from hmz.tui.settings import GROUPS, MOVED, PAGES, page_of


def test_the_pages_are_listed_in_the_groups_the_web_page_has_them_in() -> None:
    assert GROUPS == (
        ("App", ("themes", "daemons", "notifications", "language")),
        ("Daemon", ("general", "accounts", "nous", "runtimes", "backup", "usage")),
        ("Workspace", ("workspace",)),
    )
    assert PAGES == (
        "themes",
        "daemons",
        "notifications",
        "language",
        "general",
        "accounts",
        "nous",
        "runtimes",
        "backup",
        "usage",
        "workspace",
    )


@pytest.mark.parametrize(("at", "page"), list(enumerate(PAGES)))
def test_each_page_is_opened_by_its_own_name(at: int, page: str) -> None:
    assert page_of(page) == at


@pytest.mark.parametrize(
    ("said", "page"),
    [
        ("General", "general"),
        ("ACCOUNTS", "accounts"),
        ("Themes", "themes"),
        ("language", "language"),
        ("settings", "general"),
        ("everywhere", "general"),
        ("directory", "workspace"),
        ("environments", "runtimes"),
    ],
)
def test_a_page_is_opened_by_any_case_and_its_old_names(said: str, page: str) -> None:
    assert page_of(said) == PAGES.index(page)


@pytest.mark.parametrize("said", ["", "nothing", "flows", MOVED])
def test_a_word_that_is_no_page_opens_none(said: str) -> None:
    assert page_of(said) is None


def test_the_page_that_moved_is_named_apart() -> None:
    assert MOVED == "flowverses"
    assert MOVED not in PAGES
