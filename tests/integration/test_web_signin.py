"""The page's table of sign-in descriptions against what the harnesses give.

`accounts.list` answers each way of signing in, and each thing it asks for, with an English
`about`; the page says each in its own language out of a table keyed by that English
(`web/static/views/settings/signin.js`, Section 3.4.4.14.2 of protocol/web.md). A description
the table lacks would be said in English on a Chinese page, and one no harness gives is dead
weight in three catalogs: both fail here.
"""

import re
from importlib import resources

from hmz.coganchor import backends

_GATEWAY = "through a local LiteLLM gateway: "
_ROW = re.compile(r"^  \['((?:[^'\\]|\\.)*)', t\('((?:[^'\\]|\\.)*)'\)\],$", re.M)


def _given() -> set[str]:
    """Every description a harness gives, the gateway's prefix taken off as the page does."""
    found: set[str] = set()
    for profile in backends.profiles():
        for way in (*profile.ways, *backends.routed(profile)):
            for said in (way.about, *(one.about for one in way.asks)):
                if said:
                    found.add(said.removeprefix(_GATEWAY))
    return found


def test_the_page_says_every_sign_in_description_the_harnesses_give() -> None:
    source = (
        resources.files("hmz.web")
        .joinpath("static/views/settings/signin.js")
        .read_text(encoding="utf-8")
    )
    rows = _ROW.findall(source)

    # Each keyed by the text it says, and the gateway's prefix as the daemon writes it.
    assert rows
    assert all(key == said for key, said in rows)
    assert f"'{_GATEWAY}'" in source
    assert {key.replace("\\'", "'") for key, _ in rows} == _given()
