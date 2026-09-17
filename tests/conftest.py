"""The gates every suite shares: what a test may reach, and what it may drive.

`pytest_addoption` is honoured only in a root conftest, so `--run-agents` has to live
here rather than beside the tests it gates; the `agent` marker it keys on, and the `node`
marker that leaves out what needs a real Node on the machine, are registered by
`pytest_configure` below.

The autouse fixtures here are the switches that keep a run on the machine it was started on:
nothing reports a crash, nothing fetches a price list, nothing starts a coding agent to ask
what it runs, and nothing clones a repository that is somewhere else. Each of those is
right at a prompt and wrong in a suite, and each is shut here rather than in the directory
whose tests happened to trip over it -- a road off the machine is a road off the machine
wherever the test that takes it is filed.
"""

from __future__ import annotations

import shutil
import unittest.mock
from typing import TYPE_CHECKING

import pytest

import hmz.coganchor.models
import hmz.flows.verses
from hmz.runtime import telemetry

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.coganchor.backends import Model

#: Asking a backend what it runs, before the suite takes it away again. Held here so that a
#: test which is about the asking can have it back.
_ASKS = hmz.coganchor.models.ask

#: Why the tests that run a real Node cannot run here, or "" where they can. Asked once, as
#: this file is imported, rather than inside each test: the answer cannot change under a run,
#: and a question asked in the body is a test that has already started before it says it is
#: not going to finish.
_WITHOUT_NODE = "" if shutil.which("node") else "node is not installed here"


def _elsewhere(said: str) -> bool:
    """Whether an address git would clone names a machine other than this one.

    Read the way git reads one, because that is what decides where the clone goes rather than
    what it looks like at a glance. Two spellings name a host: a URL with a scheme, and the
    `host:path` form -- with or without a user in front of it, `github.com:org/flows` being as
    much a remote as `git@github.com:org/flows`. A colon after a slash is not that form, it is
    a directory with a colon in its name.

    `file://` is the exception among schemes: it is spelled like a remote and is a path on
    this machine, which is a thing a test is allowed to clone.

    Args:
      said: The address, after `hmz.flows.verses` has turned `owner/repo` into a URL.

    Returns:
      Whether cloning it would leave this machine.
    """
    scheme, found, _ = said.partition("://")
    if found:
        return scheme.lower() != "file"
    before, found, _ = said.partition(":")
    return bool(found) and "/" not in before


@pytest.fixture(autouse=True)
def _humanize_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps what outlives a run out of the home directory of whoever runs the tests.

    A run writes down its epic and what was typed at it, and neither belongs in the history
    of the person who only asked for the suite to pass.

    And nothing here reports anything anywhere. Every test starts with a home nobody has
    answered a question in, which is what humanize reads as a first start -- so without this
    the suite would put the question to a machine nobody is sitting at, and a crash a test
    made on purpose would be filed as a crash.

    The mirrors coganchor has been pointed at are recorded outside the mirror itself, and so
    outlive the temporary directory a test made one in: a suite writing those into the cache
    of whoever ran it leaves one per test there forever, and reads one back as soon as pytest
    hands out a temporary path some run of nine days ago had already used.
    """
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "humanize-home"))
    monkeypatch.setenv("HUMANIZE_SENTRY", "off")
    monkeypatch.setenv("HUMANIZE_SHADOWS", str(tmp_path / "shadows"))
    # And nothing here forks a run into the background. `hmz` with no command holds the run
    # apart from the terminal, which is right at a prompt and wrong in a suite: a test run
    # with `-s` from a real terminal would otherwise leave a detached interface behind it.
    # The tests that are about the holding turn it back on for themselves.
    monkeypatch.setenv("HUMANIZE_DAEMON", "off")
    # And nothing here fetches the unit prices a bill is worked out from. The interface asks
    # for those as it opens, which is right at a prompt and wrong in a suite: a test must not
    # reach anybody's network, and one that is about the fetching points this at a file.
    monkeypatch.setenv("HUMANIZE_PRICES", "off")
    # Whether the question about reporting has been answered is read once and kept for the
    # life of the process, which is right at a prompt and wrong across a suite: a test that
    # answers it -- and the ones about the question itself do -- leaves the answer behind for
    # every test after it, and the next one that expects to be asked is never asked at all.
    telemetry.again()


@pytest.fixture(autouse=True)
def _nothing_running_yet() -> Iterator[None]:
    """Starts each test with no flow running, on no branch, and leaves neither behind.

    What is running is the process's own, and the branch this task is on is the context's.
    Several tests here hold a flow open on purpose -- two agents working at once is what half
    the interface is about -- and its thread is still alive when the test lets go of it, so
    the next test would find that flow running, say so on its own status line, and call its
    own flows under it.
    """
    _forgotten()
    yield
    _forgotten()


def _forgotten() -> None:
    """Leaves nothing of one test's flows for the next one to run under."""
    from hmz.flows import driving

    driving._RUNNING.clear()
    driving._CLAIMED.clear()
    driving._WRITTEN.clear()
    driving._ON.set(None)


@pytest.fixture(autouse=True, scope="session")
def _clones_nothing_elsewhere() -> Iterator[None]:
    """Stops anything in the suite cloning a repository that is not already on this machine.

    Every repository cloned here is one a test made a moment ago under a temporary directory
    of its own -- except humanize's own flowverse, whose address is a real one, written into
    the package because that is where humanize's flows are kept. So anything that fetches
    flowverses without being told which one fetches that one, and that was the suite's last
    road off the machine it was started on. It was shut in `tests/tui/conftest.py`, which is
    the interface's own directory: two tests inside it turned the fetcher back on without
    saying where it fetched from and spent four seconds of somebody's network on every run,
    and nothing outside that directory was covered at all.

    Shut here instead, beside the switches that stop a run reporting a crash and fetching a
    price list, because a road out is a road out wherever the test that takes it happens to be
    filed. Written against what is being cloned rather than against the one address, too: a
    guard that names today's URL is a guard the next one written into the package walks
    straight past.

    Refused as an `OSError`, which is what a clone that would not go says anyway, so whatever
    asked for it goes on doing exactly what it does when a fetch fails.

    The clone is the only thing that has to be stopped, because a fetch again goes where the
    clone came from: `verses.refresh` is `git fetch` inside a repository, and the only
    repositories here are the ones this let through, whose origin is therefore a directory on
    this machine. That holds as long as nothing writes a remote origin into a repository of
    its own, which nothing does, and it is why there is one guard rather than two.

    For the whole session, and patched rather than monkeypatched, because the thread is the
    point: the fetch runs in one that the test which started it can finish without, and it
    reads the address again when it gets there -- so a test that pointed it somewhere of its
    own has already put the real one back by the time the clone is asked for, and a guard
    lifted at teardown is a guard with the clone still to come.

    Refused rather than failed at the test that asked, for the same reason: on that thread
    there is no telling who asked. The test on the screen is whichever happened to be running
    when a clone somebody else started came round, and a suite that failed that one would fail
    somewhere new every time it was run. So this promises the thing worth promising -- that no
    run of these tests reaches anybody's network -- and saying where a fetch fetches from is
    the other half, written where the test that meant it is.
    """
    clones = hmz.flows.verses.clone

    def only_from_here(url: str, at: Path) -> None:
        """Clones what is already on this machine, and refuses what would have to be sent.

        The address is worked out once and the worked-out one is what is cloned: `owner/repo`
        is a remote or a directory depending on whether that directory is there, which is a
        question whose answer depends on where the process happens to be standing. Asked twice
        it could be answered twice, and the address checked would not be the address cloned.
        """
        whence = hmz.flows.verses._url_of(url)
        if _elsewhere(whence):
            raise OSError(f"the suite does not clone {whence}")
        clones(whence, at)

    with unittest.mock.patch.object(hmz.flows.verses, "clone", only_from_here):
        yield


@pytest.fixture(autouse=True)
def _asks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stops anything here starting a real coding agent to find out what it runs.

    An account made is asked what it runs, and the interface asks every backend installed
    here as it opens. Both are right, and neither is something a suite should be doing on
    whoever's machine is running it -- so it is refused, and a test that is about the asking
    asks for `asking` and has it back.
    """

    def refuse(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        raise AssertionError(f"the suite does not start {cli} to ask what it runs")

    monkeypatch.setattr(hmz.coganchor.models, "ask", refuse)


@pytest.fixture
def asking(_asks_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives this test the asking back, for one that is about a backend being asked.

    Named after the fixture that took it away, so that it is put back after rather than
    before: two fixtures setting one attribute is the order they run in.
    """
    monkeypatch.setattr(hmz.coganchor.models, "ask", _ASKS)


@pytest.fixture
def priced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Puts one model's unit prices where the interface will read them.

    Written and fetched from a file rather than from the network: what a token costs is
    somebody else's list, and a suite must not go and ask them for it.

    Returns:
      The model that is now listed, at a dollar a million in and five a million out.
    """
    import json

    from hmz.coganchor import prices

    source = tmp_path / "prices-source.json"
    source.write_text(
        json.dumps(
            {
                "currency": "USD",
                "unit": "per 1M tokens",
                "versions": [
                    {
                        "date": "2026-09-10",
                        "models": [
                            {
                                "provider": "Anthropic",
                                "id": "claude-haiku-4.5",
                                "name": "Claude Haiku 4.5",
                                "pricingItems": [
                                    {"category": "input_tokens", "price": 1},
                                    {"category": "output_tokens", "price": 5},
                                    {"category": "cache_read_tokens", "price": 0.1},
                                    {"category": "cache_write_tokens", "price": 1.25},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(prices.WHENCE, str(source))
    prices._tried = 0.0
    assert prices.refresh(wait=True)
    return "claude-haiku-4.5"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "agent: end-to-end test that drives a real coding agent binary"
    )
    config.addinivalue_line(
        "markers", "node: test that runs a real `node`, rather than a stand-in for one"
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-agents",
        action="store_true",
        default=False,
        help="also run the end-to-end tests that drive real coding agents",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Leaves out what this machine, or this run, is not in a position to do.

    Both by marker rather than by a `skip` written in the body. A marker is registered, so
    `--strict-markers` refuses a misspelt one instead of letting it mark nothing quietly; the
    skip it becomes is named in the `-ra` summary with the reason attached, so a test that has
    stopped running says which it was and why; and it can be asked for or left out with `-m`,
    which a `skip` reached halfway through a test body cannot be.
    """
    if _WITHOUT_NODE:
        nodeless = pytest.mark.skip(reason=_WITHOUT_NODE)
        for item in items:
            if "node" in item.keywords:
                item.add_marker(nodeless)
    if config.getoption("--run-agents"):
        return
    skip = pytest.mark.skip(
        reason="needs --run-agents (drives real agents, costs tokens)"
    )
    for item in items:
        if "agent" in item.keywords:
            item.add_marker(skip)
