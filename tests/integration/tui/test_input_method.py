"""An input method's commit, from what the terminal sends to what the prompt holds.

What Ghostty sends is read into keys by Textual's own parser, and the keys reach the interface
in one go, the way a terminal hands over one read. The prompt holds the characters committed,
rather than the report they arrived in typed out a character at a time.
"""

from __future__ import annotations

import pytest
from textual._xterm_parser import XTermParser

from hmz.tui import Humanize
from hmz.tui.app import Editor


@pytest.mark.timeout(60)
async def test_a_long_commit_lands_in_the_prompt_whole() -> None:
    """Twelve characters confirmed with space, which is a report of 78 -- past Textual's 32."""
    text = "你帮我检查一下这个代码库"
    sent = "\x1b[32;;" + ":".join(str(ord(each)) for each in text) + "u"
    parser = XTermParser()
    app = Humanize()
    async with app.run_test() as driver:
        for each in [*parser.feed(sent), *parser.feed("")]:
            each.set_sender(app)
            app.post_message(each)
        await driver.pause()

        assert app.query_one(Editor).text == text
