"""What the home page's scenes share: the one task they all show, and the two windows.

The home page (`docs/index.md`) is one stage that plays a scene at a time, each a reel of the
real interface: `test_docs_home_<scene>.py` writes `home-<scene>` for a desk, in Humanize
Desktop's window, and `home-<scene>-phone` for a phone, in the web page at a phone's width.
Every reel for a desk is one size, and every one for a phone, so the stage never jumps; and
all of them show one task, so that the scenes read as one story.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from tests.system.docs import shots
from tests.system.docs.conftest import PROJECT
from tests.system.web.doubles_browser import opened

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

#: The task every scene of the home page shows.
TASK = "Add a coupon code to checkout"

#: The flow it is handed to: an actor works, a reviewer sends it back until it is done.
FLOW = "rlar"

#: The window a scene for a desk is taken in: Humanize Desktop's, made smaller than it opens,
#: so that what is in it is drawn larger on the stage.
DESK = (1040, 680)

#: And the one a scene for a phone is: the web page as a phone lays it out. A page is printed
#: on paper a whole number of points wide, which 392 pixels are and 390 are not.
PHONE = (392, 520)


@contextlib.contextmanager
def desk(world: World) -> Generator[Page]:
    """Humanize Desktop's window at the stage's size: take it with `window="desktop"`."""
    with opened(
        world.site,
        width=DESK[0],
        height=DESK[1],
        user_agent=shots.APP,
        init=shots.GATE,
    ) as page:
        page.get_by_text(PROJECT, exact=True).first.wait_for()
        yield page


@contextlib.contextmanager
def phone(world: World) -> Generator[Page]:
    """The web page on a phone, at the stage's size: take it with no window around it."""
    with opened(
        world.site, width=PHONE[0], height=PHONE[1], touch=True, init=shots.GATE
    ) as page:
        yield page
