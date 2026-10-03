"""Which kind of failure stopped a turn, and what each kind is owed.

Before this there were two: a turn that failed and a turn no other try could come out
differently on. So a 401 was retried five times on a schedule, a `database is locked` waited a
minute for contention that clears in a second, and a rate limit was answered by asking the same
service again at once. Nine kinds now, each with an answer of its own -- and the answers are
the point, the names being only how one is looked up.

What is checked here is that what a CLI says is read as the kind it is, that the kind decides
how many goes the turn gets here and how long the shortest wait is, that every step of it
narrates itself as an event, and that a backend which already knows is believed over any
reading of a message.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends, fallbacks, models, providers
from hmz.coganchor.agents import (
    AgentBase,
    AgentConfig,
    Event,
    Failed,
    SessionBase,
    Unrecoverable,
)
from tests.stubs import ShellAgent, ShellSession
from tests.stubs import ShellAgent as _Shell

if TYPE_CHECKING:
    import os
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


@pytest.fixture
def accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home nothing has written to, `shell` as a backend, and an account of it."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    backends.remember("shell", ["shell"])
    providers.add("shell", "main", env={"WHOSE": "main"})


@pytest.fixture
def unwaiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Waits that are worked out and narrated but not actually sat through.

    A rate limit waits half a minute on purpose, and a suite that sat through one per test
    would be a suite nobody runs. What the wait *was* is on the event that says it.
    """

    def slept(_session: SessionBase, _seconds: float) -> bool:
        """Waits nothing at all, and was not cut short."""
        return False

    monkeypatch.setattr(SessionBase, "_sits", slept)


#: A turn that says something on stderr and fails, writing down which account took it -- so a
#: test reads both what the recovery said and how many goes each account actually got.
_SAYING = 'echo "${{WHOSE:-nobody}}" >> {at}; echo {said!r} >&2; exit 1'


def _took(tally: Path) -> list[str]:
    """Which account took each go, in order."""
    return tally.read_text(encoding="utf-8").split()


def _watched(agent: AgentBase) -> list[str]:
    """The lines a watcher would see the recovery itself narrated with.

    A command backend puts each line of the agent's own stderr on the stream as a `tool` too,
    which is what a person watching a turn wants and not what these are about. The recovery's
    own lines are the ones that name the backend they are about.

    Args:
      agent: The agent to watch.

    Returns:
      The list, filled as the turn runs.
    """
    narrated: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            narrated.append(event.text)
            if event.kind == "notice" and event.text.startswith(f"{agent.backend} ")
            else None
        )
    )
    return narrated


def _driving() -> tuple[ShellAgent, list[str]]:
    """An agent on `main`, and the lines a watcher would see its recovery narrated with."""
    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))
    return agent, _watched(agent)


def _catalogued(*names: str) -> None:
    """Writes down what `shell` last said it runs, as of a fortnight ago.

    A catalogue rather than a call to ask for one: what is being read is what humanize kept
    and when it kept it, which is exactly what a person cannot see when every id in it is
    refused.

    Args:
      names: The models it holds, in the order it holds them.
    """
    models.where("shell", "main").write_text(
        json.dumps(
            {
                "asked": "2026-09-10T07:59:03Z",
                "models": [
                    {"name": name, "efforts": ["high"], "swarms": False}
                    for name in names
                ],
            }
        ),
        encoding="utf-8",
    )


def _fails(agent: ShellAgent, tally: Path, said: str) -> str:
    """Runs the failing turn and answers with what it finally failed with."""
    with pytest.raises(subprocess.CalledProcessError) as raised:
        agent.new()(_SAYING.format(at=tally, said=said))
    return str(raised.value)


def test_what_a_cli_says_when_it_stops_is_read_as_the_kind_it_is() -> None:
    """One classifier, because a 429 is a 429 whichever CLI was holding the socket."""
    read = {
        "Error: 429 Too Many Requests": "throttled",
        "RESOURCE_EXHAUSTED: quota exceeded for this project": "spent",
        "429 You exceeded your current quota (insufficient_quota)": "spent",
        "Error: Some resource has been exhausted: You are sending requests too "
        "quickly. Please slow down": "throttled",
        "Claude AI usage limit reached": "throttled",
        "API Error: 401 unauthorized": "refused",
        "Authentication required": "refused",
        "You are not logged into Antigravity.": "refused",
        "Your access token could not be refreshed because your refresh token was "
        "revoked. Please log out and sign in again.": "refused",
        "The model is not supported when using a ChatGPT account": "unlisted",
        "403 key not allowed to access model. This key can only access "
        "models=['default-models']. Tried to access gpt-5.2": "unlisted",
        "bwrap: setting up uid map: Permission denied": "sandboxed",
        "hmz: cannot keep the local copy of the work at /home/me/x: "
        "Permission denied: /home/me": "unmirrored",
        "403 Forbidden: hmz: api.example.com:443 is not a host this run may reach": (
            "fenced"
        ),
        "404 model not found: gpt-9": "retired",
        "SqliteError: database is locked": "contended",
        "hmz: this account signs in with a token that refreshes itself, and a copy of "
        "it is out on another machine for a turn there": "contended",
        "Error: read ECONNRESET": "dropped",
        "FetchError: socket hang up": "dropped",
        "502 Bad Gateway": "dropped",
        "FATAL ERROR: Reached heap limit Allocation failed": "killed",
    }

    for said, fault in read.items():
        assert backends.trouble("claude", said) == fault, said


def test_a_model_grok_is_not_holding_the_catalogue_for_is_waited_out() -> None:
    """Grok Build refuses an id out of a list it fell back to, not out of the account's.

    With no account it answers `grok models` from a list built into the binary,
    and the ids a gateway account runs are fetched -- so a fetch that does not
    land leaves it refusing a model the turn before it ran on. Waiting is what
    answers that, which `unlisted` would not do and `throttled` does.
    """
    said = (
        "Error: Couldn't set model 'xai/xai/grok-4.6': Invalid params: "
        "\"unknown model id\". Run 'grok models' to see available models."
    )

    assert backends.trouble("grok", said) == "throttled"
    assert fallbacks.answers("throttled").tries > 0

    # One CLI's own sentence and no other's: read for anybody else, the shared
    # signatures still call a model nothing has heard of a model that is gone.
    assert backends.trouble("claude", said) == "retired"


def test_a_failure_nothing_recognises_is_the_turn_that_has_always_failed() -> None:
    """The only answer that cannot be wrong about something it has not understood."""
    assert backends.trouble("claude", "the build is broken") == ""

    owed = fallbacks.answers("")
    assert owed.tries == 0  # the goes the place asked for, and no floor under them
    assert not owed.held
    assert not owed.policy  # waited the way the place says


def test_the_exit_status_says_it_where_the_process_never_got_to_speak() -> None:
    """A signal is not a sentence, and a shell's 127 is not one either."""
    assert backends.trouble("claude", "", status=127) == "missing"
    assert backends.trouble("claude", "", status=126) == "missing"
    assert backends.trouble("claude", "some earlier output", status=-9) == "killed"
    assert backends.trouble("claude", "", status=137) == "killed"


def test_what_one_cli_says_and_no_other_does_is_read_off_that_cli() -> None:
    """An SDK rather than a CLI: nothing about what dsh says reads like HTTP."""
    said = "DeepSeek Harness only supports API-key login and needs a DeepSeek API key."

    assert backends.trouble("dsh", said) == "refused"
    # And it is dsh's own: nothing else is taught to read that sentence.
    assert backends.trouble("claude", said) == ""


def test_a_cli_s_own_sentence_beats_a_word_that_happens_to_be_beside_it() -> None:
    """It knows what its own failure is; a shared signature only knows what a word is."""
    said = "dsh needs a DeepSeek API key -- set one, or your quota is spent"

    assert backends.trouble("dsh", said) == "refused"
    # The same line to a backend that has no sentence of its own reads as the word does.
    assert backends.trouble("claude", said) == "spent"


def test_a_line_that_mentions_a_sandbox_is_not_a_sandbox_that_would_not_start() -> None:
    """The signatures are read from the top, so what they say has to be what happened.

    A CLI that warns about its sandbox on the way up and is then rate-limited has both in the
    stream it failed with, and the one that stopped the turn is the rate limit.
    """
    said = "WARN landlock is not supported on this kernel\nError: 429 Too Many Requests"

    assert backends.trouble("codex", said) == "throttled"
    # And the sandbox that actually did not start says so itself, in bubblewrap's own words.
    assert backends.trouble(
        "codex", "bwrap: setting up uid map: Permission denied"
    ) == ("sandboxed")


def test_a_backend_that_reports_an_http_status_is_not_read_as_a_signal() -> None:
    """Kimi is driven through a daemon: what it reports is the status of the call it made."""
    assert backends.trouble("kimi", "rate limit exceeded", status=429) == "throttled"
    assert backends.trouble("kimi", "invalid api key", status=401) == "refused"
    assert backends.trouble("kimi", "model not found", status=404) == "retired"
    # No real HTTP status falls where a signal does, which is what tells the two apart.
    assert backends.trouble("kimi", "", status=137) == "killed"


def test_the_end_of_a_stream_is_what_is_read_rather_than_the_whole_of_it() -> None:
    """An agent asked to write a rate limiter says `rate limit` in prose for a page."""
    said = "rate limit rate limit\n" + ("the agent went on at length. " * 400)

    assert backends.trouble("claude", said) == ""


def test_a_backend_that_names_the_kind_itself_is_believed(accounts: None) -> None:
    """It knows something no signature does, so nothing here reads its message to guess."""
    failed = Failed(
        1, ["claude"], "", "some sentence nothing recognises", fault="killed"
    )
    session = ShellAgent(CONFIG).new()

    assert session._trouble(failed).fault == "killed"
    # And what was decided is written back, so the turn's own failure says it too.
    assert "(killed:" in str(failed)


def test_a_credential_that_was_refused_is_not_tried_again_under_it(
    accounts: None, tmp_path: Path
) -> None:
    """It is refused a minute later too, so five goes on a schedule is five minutes spent."""
    # Written down asking for three goes, which this failure is worth none of.
    fallbacks.retrying("shell@main/m", 3, "none", 0.0)
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    said = _fails(agent, tally, "API Error: 401 unauthorized")

    assert _took(tally) == ["main"]  # one go, and straight on to wherever is next
    assert narrated == []  # nowhere is, so nothing to narrate carrying on with
    assert "(refused: that account needs signing in again)" in said


def test_a_host_the_fence_kept_it_off_is_not_an_account_to_sign_in_again(
    accounts: None, tmp_path: Path
) -> None:
    """The fence proxy refuses with a `403`, and a `403` alone reads as a credential.

    Found under real load: a turn the run's network fence kept off a host was told its account
    needed signing in again, which is a person sent to fix a login that nothing refused. It
    is said as the fence it was, and walked away from as a refusal is: the next go meets the
    same fence.
    """
    tally = tmp_path / "took.txt"
    agent, _narrated = _driving()

    said = _fails(
        agent,
        tally,
        "Error: 403 Forbidden: hmz: api.example.com:443 is not a host this run may reach",
    )

    assert _took(tally) == ["main"]
    assert "(fenced: the run's network fence keeps it off that host" in said
    assert "signing in again" not in said


def test_a_rate_limit_waits_long_before_it_is_tried_again(
    accounts: None, unwaiting: None, tmp_path: Path
) -> None:
    """The account is spending too fast; asking again at once is spending faster."""
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    _fails(agent, tally, "Error: 429 Too Many Requests")

    # A go apiece beyond the first, even though nobody wrote a retry down: the wait is the
    # answer here, and a place with no tries would otherwise have had nowhere to put one.
    assert _took(tally) == ["main", "main"]
    assert "is rate-limited" in narrated[0]
    assert f"trying again in {fallbacks.THROTTLED:.0f}s" in narrated[0]


def test_a_plain_429_is_a_rate_limit_and_not_a_quota_spent(
    accounts: None, unwaiting: None, tmp_path: Path
) -> None:
    """A gateway asking for room is not an account somebody has to top up.

    Found under real load: every `429` a gateway answered with was narrated as an account
    that had spent its quota, which sends a person to the billing page of an account that was
    only being asked too fast. A quota is said where the service says one.
    """
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    said = _fails(agent, tally, "Error: 429 Too Many Requests")

    assert "is rate-limited" in narrated[0]
    assert "slow down" in narrated[0]
    assert "spent its quota" not in narrated[0]
    assert "(throttled: " in said
    assert "spent its quota" not in said

    tally.unlink()
    agent, narrated = _driving()
    said = _fails(
        agent, tally, "429 You exceeded your current quota (insufficient_quota)"
    )

    # Waited out the same way, being the same status, and said as what it is.
    assert _took(tally) == ["main", "main"]
    assert "has spent its quota" in narrated[0]
    assert "(spent: this account has spent its quota" in said


def test_the_time_a_place_was_given_still_holds_over_a_long_wait(
    accounts: None, tmp_path: Path
) -> None:
    """Checked before the wait, so a turn is never started knowing it is already spent."""
    fallbacks.retrying("shell@main/m", 1, "none", 0.5)
    tally = tmp_path / "took.txt"
    agent, _narrated = _driving()

    _fails(agent, tally, "Error: 429 Too Many Requests")

    # Half a second was all it had, and the wait a rate limit asks for is longer than that:
    # one go, and no thirty seconds spent finding that out.
    assert _took(tally) == ["main"]


@pytest.mark.timeout(20)
def test_a_turn_cut_off_while_it_waits_out_a_rate_limit_ends_then(
    accounts: None, tmp_path: Path
) -> None:
    """ctrl+c during the thirty seconds is the end of the turn, not thirty seconds later.

    And said once: the interface asks again until the turn has ended, which read as twenty
    cut-offs of one turn.
    """
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()
    cuts: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            cuts.append(event.text) if event.text.startswith("cutting") else None
        )
    )
    session = agent.new()
    said: list[str] = []
    turn = threading.Thread(
        target=lambda: said.append(
            session(_SAYING.format(at=tally, said="Error: 429 Too Many Requests"))
        )
    )
    turn.start()
    deadline = time.monotonic() + 10
    while not narrated and time.monotonic() < deadline:
        time.sleep(0.05)
    assert narrated, "the rate limit was never waited out"

    started = time.monotonic()
    for _ in range(5):
        session.interrupt(why="interrupted")
    turn.join(timeout=10)

    assert not turn.is_alive()
    assert time.monotonic() - started < fallbacks.THROTTLED / 2
    assert _took(tally) == ["main"]
    assert said == [""]
    assert len(cuts) == 1


def test_a_model_that_is_gone_is_not_tried_again(
    accounts: None, tmp_path: Path
) -> None:
    """The next call names the same model, so it is told the same thing again."""
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    said = _fails(agent, tally, "404 model not found: m")

    assert _took(tally) == ["main"]
    assert (
        narrated == []
    )  # nowhere to carry on to, so nothing to narrate carrying on with
    assert "(retired: the model is gone" in said


def test_a_model_this_account_may_not_name_is_not_an_account_to_sign_in_again(
    accounts: None, tmp_path: Path
) -> None:
    """The status says a credential was refused and the sentence says which model it was.

    Read by the number it is a person sent to sign an account in that refused nothing -- which
    is what a gateway fronting several clouds got from humanize for every id in a catalogue it
    had moved under.
    """
    tally = tmp_path / "took.txt"
    agent, _narrated = _driving()

    said = _fails(
        agent,
        tally,
        "403 key not allowed to access model. This key can only access "
        "models=[default-models]. Tried to access m",
    )

    assert "(unlisted:" in said
    assert "signing in" not in said
    # And not tried again: the list of what this account runs has not changed a second later.
    assert _took(tally) == ["main"]


def test_a_model_refused_says_what_humanize_last_kept_and_when_it_kept_it(
    accounts: None, tmp_path: Path
) -> None:
    """The catalogue is what offered the id, so the catalogue is what the failure names."""
    _catalogued("m")
    tally = tmp_path / "took.txt"
    agent, _narrated = _driving()

    said = _fails(agent, tally, "403 key not allowed to access model m")

    # The list still names the model the endpoint has just refused, so the list is the stale
    # part -- and saying when it was taken is what tells somebody that.
    assert (
        "the 1 models this account was last offered (asked 2026-09-10) still list it"
        in said
    )
    assert 'the "check again" button under its models checks again' in said


def test_a_model_no_catalogue_here_has_says_it_is_not_in_the_one_kept(
    accounts: None, tmp_path: Path
) -> None:
    """The other half: an id nothing here offered, and a list to read rather than a guess."""
    _catalogued("elsewhere/m")
    tally = tmp_path / "took.txt"
    agent, _narrated = _driving()

    said = _fails(agent, tally, "403 key not allowed to access model m")

    assert (
        "not among the 1 models this account was last offered (asked 2026-09-10)"
        in said
    )


def test_a_machine_that_will_not_let_a_cli_sandbox_itself_says_so(
    accounts: None, tmp_path: Path
) -> None:
    """`Permission denied` out of bubblewrap is no credential anybody can sign in again."""
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    said = _fails(agent, tally, "bwrap: setting up uid map: Permission denied")

    assert "(sandboxed: this machine will not let it sandbox itself" in said
    # Not tried again: a kernel that has just said no says it to the next go too.
    assert _took(tally) == ["main"]
    assert narrated == []


def test_a_store_another_turn_had_open_is_tried_again_here_briefly(
    accounts: None, tmp_path: Path
) -> None:
    """Opencode keeps its sessions in one database shared across workspaces."""
    tally = tmp_path / "took.txt"
    agent, narrated = _driving()

    _fails(agent, tally, "SqliteError: database is locked")

    # Three goes beyond the first, a second apart, and only then somewhere else.
    assert _took(tally).count("main") == 4
    assert "found its own store busy" in narrated[0]
    assert "trying again in 1s (1 of 3)" in narrated[0]


def test_a_dropped_connection_reopens_the_transport_and_resumes_the_conversation(
    accounts: None, tmp_path: Path
) -> None:
    """What was lost was the socket and not the session: the conversation is the backend's."""
    shut: list[str] = []

    class Reopening(ShellSession):
        """A session that says when what was holding its conversation open is let go of."""

        def _shut(self) -> None:
            shut.append(self._id or "")

    # Named for the backend it drives, as every agent here is: the class name is what says
    # which CLI this is, and a stand-in called anything else would be a backend of its own.
    class ShellAgent(_Shell):
        def new(self, cwd: str | os.PathLike[str] | None = None) -> Reopening:
            return Reopening(self, cwd)

    tally = tmp_path / "took.txt"
    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))
    narrated = _watched(agent)

    _fails(agent, tally, "Error: read ECONNRESET")

    assert shut  # let go of before the next go rather than spoken to again
    assert "lost the connection" in narrated[0]
    assert "reopening and resuming" in narrated[0]
    # And waited over the way the place says and no other way: there is nothing here to wait
    # out, the thing that failed having already gone.
    assert not fallbacks.answers("dropped").policy
    assert fallbacks.answers("dropped").least == 0.0


def test_a_cli_that_is_not_installed_says_which_line_installs_it(
    accounts: None,
) -> None:
    """A turn that failed for a missing CLI has nothing else worth saying."""

    class Gone(ShellSession):
        """A session whose command is not a command anything here has."""

        def _turn(self, prompt: str) -> tuple[list[str], str | None]:
            return (["definitely-not-installed-anywhere", prompt], None)

    class ClaudeCodeAgent(AgentBase):
        """Named for `claude`, so that the line it says is the line that installs claude."""

        def new(self, cwd: str | os.PathLike[str] | None = None) -> Gone:
            return Gone(self, cwd)

    with pytest.raises(subprocess.CalledProcessError) as raised:
        ClaudeCodeAgent(CONFIG).new()("hello")

    # A `CalledProcessError` rather than the `FileNotFoundError` the spawn actually raised: a
    # flow catches turns rather than transports, and a loop written against a failed turn
    # could not have carried on past anything else.
    assert "(missing: npm i -g @anthropic-ai/claude-code)" in str(raised.value)


def test_a_directory_that_has_gone_is_not_a_cli_that_is_not_installed(
    accounts: None, tmp_path: Path
) -> None:
    """Telling somebody to install a CLI they have is an answer to a question nobody asked."""
    session = ShellAgent(CONFIG).new()
    away = tmp_path / "gone"

    read = session._nothing_ran(FileNotFoundError(2, "No such file", str(away)))
    assert (
        read.fault == "missing"
    )  # a path that is not there and is not where the turn runs

    # And the directory the turn was to run in, which `subprocess` names instead of the
    # program when it is the chdir that failed.
    read = session._nothing_ran(FileNotFoundError(2, "No such file", session.cwd))
    assert (
        read.fault == ""
    )  # a failed turn nothing classified, tried again as any other is


def test_a_backend_that_keeps_its_reason_in_its_own_log_is_read_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Antigravity exits with a generic error and puts the status where nobody was looking."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    log = tmp_path / ".gemini/antigravity-cli/log"
    log.mkdir(parents=True)
    (log / "cli-20260910_070643.log").write_text(
        "I0910 07:06:43 client.go:88] rpc error: code = ResourceExhausted "
        "desc = HTTP 429: quota exceeded\n",
        encoding="utf-8",
    )

    # What the streams said is the generic error the evaluation saw six of.
    generic = "Agent execution terminated due to error."
    assert backends.trouble("agy", generic) == ""
    assert backends.trouble("agy", generic, journal=backends.journalled("agy")) == (
        "spent"
    )


def test_a_log_nothing_has_written_to_lately_is_not_this_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log is appended to for as long as that CLI runs; an old one is another run's."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    log = tmp_path / ".gemini/antigravity-cli/log"
    log.mkdir(parents=True)
    (log / "cli-old.log").write_text("HTTP 429\n", encoding="utf-8")

    assert backends.journalled("agy", within=0.0) == ""
    # And a backend that keeps no such log never opens a file to find that out.
    assert backends.journalled("claude") == ""


def test_a_kind_answered_by_another_place_is_not_an_unrecoverable(
    accounts: None,
) -> None:
    """It is a turn with somewhere left to go, and `suppress` catches turns that failed."""
    session = ShellAgent(CONFIG).new()
    failed = Failed(1, ["sh"], "", "404 model not found", fault="retired")

    assert not isinstance(failed, Unrecoverable)
    assert session._trouble(
        failed
    ).held  # not tried again here: another place answers it
    assert session._trouble(failed).fault == "retired"


def test_a_turn_no_try_could_change_is_still_taken_once(
    accounts: None, tmp_path: Path
) -> None:
    """Whatever the kind says: a `while True` that swallowed one would never come out."""
    fallbacks.retrying("shell@main/m", 5, "none", 0.0)
    tally = tmp_path / "took.txt"

    class Once(ShellSession):
        """A backend that knows its own failure cannot come out differently, and says so."""

        def _result(self, transcript: str) -> Event:
            raise Unrecoverable(1, ["sh"], "", "429 too many requests")

    class ShellAgent(_Shell):
        def new(self, cwd: str | os.PathLike[str] | None = None) -> Once:
            return Once(self, cwd)

    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))
    with pytest.raises(Unrecoverable):
        agent.new()(f'echo main >> {tally}; echo "429 too many requests"')

    # Said once, though every signature in it reads as a rate limit and the place asked for
    # five more goes: a backend that knows its own failure is believed over any of that.
    assert _took(tally) == ["main"]


def test_a_suppressed_turn_still_says_which_kind_it_was(
    accounts: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Quiet on the answer, not on the reason: an account needing attention says so."""
    tally = tmp_path / "took.txt"
    agent = ShellAgent(AgentConfig(model="m", effort="high", provider="main"))

    assert (
        agent.new()(_SAYING.format(at=tally, said="401 unauthorized"), suppress=True)
        == ""
    )

    assert "(refused: that account needs signing in again)" in capsys.readouterr().err
