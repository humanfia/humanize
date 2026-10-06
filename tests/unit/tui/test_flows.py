"""`hmz.tui.flows`: the pages of `/flow`, and the questions it asks before it acts."""

from __future__ import annotations

import pytest

from hmz.tui.flows import HOME, INSTALLED, VERSES, Fetches, Lists, Removes


def test_the_pages_are_named_as_on_the_screen() -> None:
    assert (HOME, INSTALLED, VERSES) == ("home", "installed", "verses")


class _Rereads:
    def reread(self) -> None:
        """Drops what was read, as a sheet of flows does."""


def test_a_sheet_that_rereads_is_one_that_lists_flows() -> None:
    assert isinstance(_Rereads(), Lists)
    assert not isinstance(object(), Lists)


@pytest.mark.parametrize(
    ("flows", "about"),
    [
        (0, "Takes its index away."),
        (1, "Takes its index away and 1 installed flow."),
        (3, "Takes its index away and 3 installed flows."),
    ],
)
def test_removing_a_flowverse_says_what_goes_with_it(flows: int, about: str) -> None:
    asked = Removes("@mine", flows)

    assert asked.asked == "Remove @mine?"
    assert asked.about == about
    assert [key for key, _, _ in asked.rows()] == ["yes", "no"]


def test_adding_a_flowverse_asks_where_it_is_then_what_to_call_it() -> None:
    form = Fetches()

    repository, name = form.asked()

    assert (repository.held, repository.needed) == ("repository", True)
    assert (name.held, name.needed) == ("name", False)
    assert form.done_about() == "clones its index; install flows from it next"
