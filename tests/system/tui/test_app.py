"""The one prompt, against a coding runtime that is really running.

The rest of the interface's tests drive fakes this repo wrote -- a `claude` on PATH that is
a Python script, a harness that is a `MagicMock` -- and live in `tests/integration/tui`.
This one starts DeepSeek's own runtime to read back what it says about a turn with no
credential, so what it asserts is that runtime's wording rather than ours, and it needs the
`[dsh]` extra to have anything to start. Either of those alone puts it in this tier: what it
talks to is nobody's fake, and what it needs is an optional install. A test whose requirement
is optional is one that goes quiet the day the extra leaves a sync, and a run that is green
because it stopped checking anything says nothing -- so which directory it is in is what
decides whether it is run, and the guard below is left only so that running this tier without
the extra skips rather than errors.
"""

from __future__ import annotations

import importlib.util
import unittest.mock
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.backends import Model
from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from tests.tui.fixtures import transcript, until

if TYPE_CHECKING:
    from pathlib import Path


# The rest of dsh is covered against a fake harness in `tests/unit/agents/test_dsh.py`.
@pytest.mark.skipif(
    importlib.util.find_spec("deepseek_harness") is None,
    reason="starts the dsh runtime, which the [dsh] extra installs",
)
@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"dsh": (Model("deepseek-v4-flash", ("max", "high", "off")),)},
)
async def test_deepseek_chat_explains_a_missing_api_key_instead_of_staying_blank(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- patch hands it over
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh-home"))
    app = Humanize(agents=[Runs("dsh/deepseek-v4-flash:high")])
    assert app._models == [Runs("dsh/deepseek-v4-flash:high")]

    async with app.run_test() as driver:
        await driver.press(*"hello")
        await driver.press("enter")
        await until(lambda: "needs a DeepSeek API key" in transcript(app), driver)
        said = transcript(app)

        assert "signs in with a key rather than a login" in said
        assert "press a on its" in said
        assert "DEEPSEEK_API_KEY" in said

        app.action_stop_flow()
        await until(lambda: not app._agents, driver)
