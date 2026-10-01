"""What the whole suite shares: its markers, the gate on real agents, and the collection.

`pytest_addoption` is honoured only in a root conftest, so `--run-agents` has to live
here rather than beside the tests it gates; the `agent` marker it keys on is registered
by `pytest_configure` below, and so are the three tier markers, the `node` marker that
leaves out what needs a real Node on the machine, and the `matrix` marker every cell of the
regression matrix carries -- every marker this suite has, registered in one place, next to the
option that gates one of them. See `tests/tiers.py` for which tree is which tier and what a
test in it may touch.

The regression matrix's hooks are here too: labelling its cells as they are collected, hearing
what each came to, and drawing the grid at the end. Here because this is the one conftest the
process drawing a summary always loads -- under xdist that process collects nothing, so a hook
in a conftest deeper in the tree is never called on it. `tests/matrix/grid.py` is the rest.

The autouse fixtures here are the switches that keep a run on the machine it was started on:
nothing reports a crash, nothing fetches a price list, nothing starts a coding agent to ask
what it runs, and nothing clones a repository that is somewhere else. Each of those is
right at a prompt and wrong in a suite, and each is shut here rather than in the directory
whose tests happened to trip over it -- a road off the machine is a road off the machine
wherever the test that takes it is filed.
"""

from __future__ import annotations

import shutil
import signal
import unittest.mock
from typing import TYPE_CHECKING, Any, Final, cast

import pytest

import hmz.coganchor.models
import hmz.runtime.flowing.verses
from hmz.runtime import telemetry
from tests import tiers
from tests.llm import serving

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.coganchor.backends import Model
    from tests.llm import Serving

# Asks back for what the subsystems lost when their `conftest.py` became a `fixtures.py`.
# pytest rewrites the asserts in a conftest and in a test module, and in nothing else without
# being told, so an `assert` in one of these would have gone from naming the two values
# it compared to a bare `AssertionError` -- in a fixture, where a failure is already reported
# against whichever test happened to ask for it. Here because this is loaded before anything
# imports them, which is the only time the request means anything. `tests/tiers.py` has why
# those files are named as they are.
pytest.register_assert_rewrite(
    "tests.coganchor.fixtures",
    "tests.daemon.fixtures",
    "tests.machines.fixtures",
    "tests.tracing.fixtures",
    "tests.tui.fixtures",
    # And the hosts ssh reaches, and the regression matrix's helpers, whose fixtures and
    # scenarios assert inside modules no test is written in.
    "tests.flows.sshd",
    "tests.matrix.cells",
    "tests.matrix.fixtures",
    "tests.matrix.places",
)

#: Asking a backend what it runs, before the suite takes it away again. Held here so that a
#: test which is about the asking can have it back.
_ASKS = hmz.coganchor.models.ask

#: Every test this run collected, written down for the guard at `tests/test_tiers.py`.
#:
#: A test cannot otherwise see the collection it is part of. `request.session.items` is what is
#: left after `-m` has thrown the rest away, so under `-m "not system"` -- which is what CI
#: runs -- a check reading that would be checking exactly the tests it was already running, and
#: a system test filed in the wrong tree would be invisible to the run that most needs to catch
#: it. This is filled from a conftest's hook, and a conftest's hook is called before pytest's
#: own selection: what is written down is the whole tree, whatever the run asked for.
COLLECTED: Final[list[pytest.Item]] = []


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
      said: The address, after `hmz.runtime.flowing.verses` has turned `owner/repo` into a URL.

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
    # for those as it opens and a run as it starts, which is right at a prompt and wrong in a
    # suite: a test must not
    # reach anybody's network, and one that is about the fetching points this at a file.
    monkeypatch.setenv("HUMANIZE_PRICES", "off")
    # Whether the question about reporting has been answered is read once and kept for the
    # life of the process, which is right at a prompt and wrong across a suite: a test that
    # answers it -- and the ones about the question itself do -- leaves the answer behind for
    # every test after it, and the next one that expects to be asked is never asked at all.
    telemetry.again()


def _handlers() -> dict[int, Any]:
    """What this process does with each signal it can be told to do something with.

    All but `SIGALRM`, which is pytest-timeout's: it takes it for each test and puts it back
    after -- early, where the test failed -- so no test leaves it to the next.
    """
    held: dict[int, Any] = {}
    for one in signal.valid_signals():
        if one == signal.SIGALRM:
            continue
        try:
            held[int(one)] = signal.getsignal(one)
        except (OSError, ValueError):
            continue
    return held


def _name(one: int) -> str:
    try:
        return signal.Signals(one).name
    except ValueError:
        return f"signal {one}"


@pytest.fixture(autouse=True, scope="session")
def _hears_interrupts() -> Iterator[None]:
    """Hears an interrupt in every worker, even one started with interrupts ignored.

    A suite started as a background job from a script starts with `SIGINT` ignored, which
    Python keeps, and every program a test starts would inherit it -- which `hmz exec` is right
    to leave alone, so a test interrupting one would wait on it forever. Once for the session,
    before any test: what each test then leaves behind is the guard below's.
    """
    if signal.getsignal(signal.SIGINT) != signal.SIG_IGN:
        yield
        return
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)


@pytest.fixture(autouse=True)
def _leaves_the_signals_as_it_found_them() -> Iterator[None]:
    """Fails a test that leaves how this process takes a signal changed, and changes it back.

    A signal's handler is the process's, and an xdist worker is one process for every test it
    runs: an interrupt one test left ignored is an interrupt every later test hands down to
    what it starts as ignored -- which a child keeps across `exec` -- and the test that fails
    for it is one that did nothing wrong, on whichever worker drew it. So it is the test that
    changed it that fails, named, and the handlers are put back before the next one.
    """
    before = _handlers()
    yield
    after = _handlers()
    changed = sorted(_name(one) for one in before if after.get(one) != before[one])
    if not changed:
        return
    for one, was in before.items():
        if after.get(one) != was:
            signal.signal(one, signal.SIG_DFL if was is None else was)
    pytest.fail(f"left these signals handled otherwise than it found them: {changed}")


@pytest.fixture(autouse=True)
def _nothing_running_yet() -> Iterator[None]:
    """Starts each test with no flow running and no flow module held, and leaves neither.

    What is running is the process's own, and so are the flow modules a run imported.
    Several tests here hold a flow open on purpose -- two agents working at once is what half
    the interface is about -- and its thread is still alive when the test lets go of it, so
    the next test would find that flow running and say so on its own status line; and a flow
    directory a test wrote is imported under its own name, which the next test's flow of the
    same name must not be answered with.
    """
    _forgotten()
    yield
    _forgotten()


def _forgotten() -> None:
    """Leaves nothing of one test's flows for the next one to run under."""
    from hmz.runtime.flowing import engine, loading

    engine._RUNS.clear()
    loading.forget()


#: The sign-ins this machine's own CLIs keep that refresh themselves: the variable that moves
#: each CLI's home, where that home is otherwise, and the file. Codex signed in with ChatGPT and
#: Claude Code signed in with a subscription each keep one, and each refresh spends the refresh
#: token the file held -- so a copy of the file that refreshes on its own leaves the original
#: holding a spent one, and the vendor revokes the sign-in the moment that is presented.
_SIGN_INS = (
    ("CODEX_HOME", ".codex", "auth.json"),
    ("CLAUDE_CONFIG_DIR", ".claude", ".credentials.json"),
)

#: The keys a refresh token is kept under in those files, and in the others like them.
_REFRESH_KEYS = frozenset({"refresh_token", "refreshtoken", "refresh"})

#: A token shorter than this is not one worth looking for: it would be found by accident.
_TOKEN_AT_LEAST = 16

#: Bigger files than this are not looked in. A sign-in is a few kilobytes, and a test's tree
#: holds images and archives nobody copied a sign-in into.
_LOOKED_IN_AT_MOST = 1 << 20


def _refresh_tokens() -> frozenset[bytes]:
    """The refresh tokens this machine's own sign-ins hold right now, which nothing prints."""
    import json
    import os
    from pathlib import Path

    found: set[bytes] = set()

    def walk(said: object) -> None:
        if isinstance(said, dict):
            for key, value in cast("dict[str, object]", said).items():
                if (
                    key.lower() in _REFRESH_KEYS
                    and isinstance(value, str)
                    and len(value) >= _TOKEN_AT_LEAST
                ):
                    found.add(value.encode())
                walk(value)
        elif isinstance(said, list):
            for value in cast("list[object]", said):
                walk(value)

    for variable, default, name in _SIGN_INS:
        home = Path(os.environ.get(variable) or Path.home() / default)
        try:
            walk(json.loads((home / name).read_bytes()))
        except (OSError, ValueError):
            continue
    return frozenset(found)


def _holding(root: Path, tokens: frozenset[bytes]) -> list[str]:
    """Every file under `root` holding any of `tokens`, by path -- never by what it held."""
    import os
    import stat

    held: list[str] = []
    for at, _, names in os.walk(root):
        for name in names:
            path = os.path.join(at, name)  # noqa: PTH118
            try:
                # A regular file alone: a link is somebody else's, and a FIFO or a device a
                # test made -- with mknod, say -- is one whose opening waits on a writer.
                found = os.lstat(path)
                if (
                    not stat.S_ISREG(found.st_mode)
                    or found.st_size > _LOOKED_IN_AT_MOST
                ):
                    continue
                with open(path, "rb") as reading:  # noqa: PTH123
                    said = reading.read()
            except OSError:
                continue
            if any(token in said for token in tokens):
                held.append(path)
    return held


@pytest.fixture(autouse=True, scope="session")
def _copies_no_sign_in(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Fails the run if a test left a copy of this machine's own sign-in under its temp dirs.

    The one thing a test must never do with a sign-in that refreshes itself is copy it: a
    Codex in a container signed in with a copy of `~/.codex/auth.json` refreshed it, and the
    sign-in on this machine was revoked. A test that needs one uses it where it is -- the CLI
    run as local, or the CLI's home mounted rather than copied -- and this is what says so
    when one does not. Looked for by the refresh tokens themselves, as this machine holds them
    at the start and at the end (a real CLI may refresh the original meanwhile), in every
    file under the temporary directories pytest keeps for the run. Nothing at all where this
    machine is signed in with no such file, which is every machine CI runs on.
    """
    before = _refresh_tokens()
    yield
    tokens = before | _refresh_tokens()
    if not tokens:
        return
    if copied := _holding(tmp_path_factory.getbasetemp(), tokens):
        pytest.fail(
            "a test copied this machine's own sign-in, which refreshes itself, to "
            + ", ".join(copied)
            + " -- a copy refreshing apart from the original gets the sign-in revoked; "
            "use the CLI's own home in place instead",
            pytrace=False,
        )


@pytest.fixture(autouse=True, scope="session")
def _clones_nothing_elsewhere() -> Iterator[None]:
    """Stops anything in the suite cloning a repository that is not already on this machine.

    Every repository cloned here is one a test made a moment ago under a temporary directory
    of its own -- except humanize's own flowverse, whose address is a real one, written into
    the package because that is where humanize's flows are kept. So anything that fetches
    flowverses without being told which one fetches that one, and that was the suite's last
    road off the machine it was started on. It was shut in `tests/tui/fixtures.py`, which is
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
    clones = hmz.runtime.flowing.verses.clone

    def only_from_here(url: str, at: Path) -> None:
        """Clones what is already on this machine, and refuses what would have to be sent.

        The address is worked out once and the worked-out one is what is cloned: `owner/repo`
        is a remote or a directory depending on whether that directory is there, which is a
        question whose answer depends on where the process happens to be standing. Asked twice
        it could be answered twice, and the address checked would not be the address cloned.
        """
        whence = hmz.runtime.flowing.verses._url_of(url)
        if _elsewhere(whence):
            raise OSError(f"the suite does not clone {whence}")
        clones(whence, at)

    with unittest.mock.patch.object(
        hmz.runtime.flowing.verses, "clone", only_from_here
    ):
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
def llm() -> Iterator[Serving]:
    """One model endpoint on the loopback, taken down however the test ends.

    What a test uses instead of somebody's gateway: it serves the catalogue an account is
    asked for, and answers the chat completions a CLI pointed at an OpenAI-compatible gateway
    takes its turns as, out of what the test said it serves and says. `tests/llm.py` is the
    service itself, and `Serving.account` is what points a backend at it.

    Here rather than beside the service because a fixture is found by pytest rather than
    imported: a test module that imported it would shadow the name with the parameter it
    names it by, which reads as a redefinition rather than as a use.
    """
    with serving() as held:
        yield held


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
    from tests.stubs import price_list, priced_model

    source = tmp_path / "prices-source.json"
    source.write_text(
        json.dumps(
            price_list(
                priced_model(
                    "claude-haiku-4.5",
                    "Claude Haiku 4.5",
                    provider="Anthropic",
                    input_tokens=1,
                    output_tokens=5,
                    cache_read_tokens=0.1,
                    cache_write_tokens=1.25,
                )
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(prices.WHENCE, str(source))
    prices._tried = 0.0
    assert prices.refresh(wait=True)
    return "claude-haiku-4.5"


def pytest_configure(config: pytest.Config) -> None:
    for line in tiers.TIERS.values():
        config.addinivalue_line("markers", line)
    config.addinivalue_line(
        "markers",
        "agent: system test that drives a real coding agent binary, and spends real tokens",
    )
    config.addinivalue_line(
        "markers", "node: test that runs a real `node`, rather than a stand-in for one"
    )
    config.addinivalue_line(
        "markers",
        "matrix(feature, order[, column]): a cell of the regression matrix in"
        " tests/system/matrix -- one feature, driven through one CLI, or once for a feature"
        " about none",
    )
    _grouped(config)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-agents",
        action="store_true",
        default=False,
        help="also run the tests that drive real coding agents, and spend real tokens",
    )
    parser.addoption(
        "--matrix-report",
        default=None,
        metavar="PATH",
        help="also write the regression matrix's feature x CLI grid to PATH:"
        " JSON for a `.json`, markdown otherwise",
    )


#: What a worker is told, through its `workerinput`, when the run hands its tests out a CLI at
#: a time. A worker reads its own `--dist` rather than the controller's, so it is told.
_GROUPED = "hmz_grouped"


def _grouped(config: pytest.Config) -> None:
    """Hands out a run that drives real agents a CLI at a time per worker, under `-n`.

    A test that drives a real CLI shares that CLI's own store -- its sessions, its sign-in,
    its rate limit -- with every other test driving it at the same moment, and several of
    these CLIs answer two turns into one store with a lost write (`HarnessContended`) or a
    provider with a `429`. So a run with `--run-agents` is `--dist loadgroup`, grouping by
    `xdist_group`, which every cell of the regression matrix carries as its CLI: each CLI's
    cells run one after another on one worker, and the CLIs run beside one another. A test
    that carries no group is its own, and is handed out as `load` would hand it. A `--dist`
    somebody asked for is theirs.

    Two halves, because xdist decides twice: the controller picks the scheduler from its
    `--dist`, and each worker decides from its own whether to tag what it collects with its
    group -- without which every test is a group of one. `pytest_configure_node` below tells
    each worker which way the controller went.
    """
    held = getattr(config, "workerinput", None)
    if held is not None:
        if cast("dict[str, Any]", held).get(_GROUPED):
            config.option.loadgroup = True
        return
    if config.getoption("--run-agents") and config.getoption("dist", "no") == "load":
        config.option.dist = "loadgroup"


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node: Any) -> None:
    """Tells each worker whether the run's tests are handed out a group at a time."""
    node.workerinput[_GROUPED] = node.config.getoption("dist") == "loadgroup"


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Hears what each cell of the regression matrix came to, for the grid drawn at the end."""
    from tests.matrix import grid

    grid.heard(report)


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    """Draws the regression matrix's grid under a run that ran any of it."""
    from tests.matrix import grid

    grid.reported(terminalreporter, config)


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
            # Asked of the markers, not `item.keywords`, for the reason given at the
            # agent gate below: keywords also hold the names of a test's parents.
            if any(mark.name == "node" for mark in item.iter_markers()):
                item.add_marker(nodeless)
    COLLECTED[:] = items
    # Each cell of the regression matrix says which feature and which CLI it is, on every
    # report it makes: whatever process draws the grid hears the reports and nothing else.
    from tests.matrix import grid

    grid.labelled(items)
    if config.getoption("--run-agents"):
        return
    skip = pytest.mark.skip(
        reason="needs --run-agents (drives real agents, costs tokens)"
    )
    for item in items:
        # Asked of the markers rather than of `item.keywords`, which also holds the names of a
        # test's parents: a directory or a test called `agent` would otherwise be skipped for
        # spending tokens it never spends, and `tests/test_tiers.py` -- which reads the markers
        # -- would not agree that it was an agent test at all.
        if any(mark.name == "agent" for mark in item.iter_markers()):
            item.add_marker(skip)
