"""`hmz web`: a run started from a page, followed on its stream, asked about, and read back."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz import machine
from hmz.runtime.epic import Epic
from tests.integration.doubles_core import AGENT, install, started
from tests.integration.doubles_web import Browser, elsewhere, served, until

if TYPE_CHECKING:
    from collections.abc import Callable

#: Chat, on the stand-in, as a page starts it.
_CHAT = {"flow": "chat", "task": "hello there", "agents": {"assistant": AGENT}}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The stand-in `claude` alone on PATH, and a project to serve the runs of."""
    return install(tmp_path, monkeypatch)


def _record(of: str, **said: Any) -> Callable[[str, Any], bool]:
    """Whether an event is a record of that type, saying all of that."""

    def wanted(event: str, data: Any) -> bool:
        return (
            event == "record"
            and data.get("type") == of
            and all(data.get(name) == value for name, value in said.items())
        )

    return wanted


def _turn(turn: str) -> Callable[[str, Any], bool]:
    """Whether an event says a chat's turn stands so."""

    def wanted(event: str, data: Any) -> bool:
        return (
            event == "standing"
            and data.get("type") == "run"
            and data.get("turn") == turn
        )

    return wanted


def test_a_run_started_from_a_page_is_followed_answered_and_stopped(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.follows() as heard:
            until(heard, lambda event, data: event == "hello", "hello")
            assert browser.post("/api/held/start", _CHAT).json()["ok"] is True

            _, said = until(heard, _record("event", kind="text"), "what the agent said")
            assert said["text"] == "did: hello there"
            _, asked = until(heard, _record("asked", role="human"), "chat asking")
            # Asking what to say next, the chat's turn is done, though it goes on.
            until(heard, _turn("done"), "the turn done")
            (going,) = browser.get("/api/runs").json()["runs"]
            assert (going["held"], going["how"]) == (True, "done")
            refused = browser.post("/api/held/answer", {"question": "q0", "text": "x"})
            assert refused.status == 409
            assert refused.json()["error"]
            answered = {"question": asked["question"], "text": "and again"}
            assert browser.post("/api/held/answer", answered).status == 200
            until(
                heard, _record("event", kind="text", text="did: and again"), "a reply"
            )

            assert browser.post("/api/held/stop").status == 200
            until(heard, _record("ended", how="stopped"), "the run ending")

        listed = browser.get("/api/runs").json()
        # A chat left is done, however it was left.
        assert listed["counts"] == {"done": 1}
        (run,) = listed["runs"]
        assert (run["flow"], run["task"], run["how"]) == (
            "chat",
            "hello there",
            "done",
        )
        one = browser.get(f"/api/runs/{run['name']}").json()
        assert [agent["runs"] for agent in one["agents"]] == [f"{AGENT}:auto"]
        assert one["spent"]["output_tokens"] > 0
        assert browser.get(f"/api/runs/{run['name']}/trace").status == 200
        bundle = browser.get(f"/api/runs/{run['name']}/bundle")
        assert bundle.status == 200
        assert bundle.headers["content-disposition"].startswith("attachment;")
        assert bundle.headers["content-type"] == "application/vnd.hmz.epic+gzip"
        assert bundle.headers["content-disposition"].endswith(".hmzepic")
        assert browser.get("/api/runs/no-such-run").status == 404


def test_a_line_said_in_the_conversation_between_turns_is_the_next_turn(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.follows() as heard:
            browser.post("/api/held/start", _CHAT)
            _, opened = until(heard, _record("opened"), "the session opening")
            _, asked = until(heard, _record("asked", mode="listen"), "chat asking")
            assert asked["key"] == ""

            # Its conversation goes by its agent's own name, never by the role it fills.
            assert opened["key"] == f"{opened['agent']}/1" != "assistant/1"
            said = {"text": "tell me more", "to": opened["key"]}
            assert browser.post("/api/held/say", said).status == 200
            until(
                heard,
                _record("answered", question=asked["question"], text="tell me more"),
                "the question answered",
            )
            until(
                heard,
                _record("event", kind="text", text="did: tell me more"),
                "a reply",
            )
            until(heard, _record("asked", mode="listen"), "chat asking again")
            browser.post("/api/held/stop")


def test_a_page_that_heard_part_of_the_stream_hears_the_rest_and_no_more(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.follows() as heard:
            browser.post("/api/held/start", _CHAT)
            last, _ = until(heard, _record("opened"), "the session opening")
            until(heard, _record("asked"), "chat asking")

        with browser.follows(last) as heard:
            _, first = until(heard, lambda event, data: event == "record", "a record")
            epoch, _, seq = last.partition(":")
            assert first["seq"] == int(seq) + 1

        with browser.follows(f"another-{epoch}:{seq}") as heard:
            _, first = until(heard, lambda event, data: event == "record", "a record")
            assert first["seq"] == 1
        browser.post("/api/held/stop")


def test_a_page_asks_the_runs_only_what_they_take(project: Path) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()

        assert browser.post("/api/held/start", _CHAT | {"budget": "1"}).status == 400
        assert browser.post("/api/held/start", _CHAT | {"rounds": 3}).status == 400
        assert browser.post("/api/held/launch", _CHAT).status == 404
        refused = browser.post("/api/held/stop")
        assert refused.status == 409
        assert refused.json()["error"]


def test_a_side_question_is_asked_beside_the_run_and_never_of_it(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.follows() as heard:
            browser.post("/api/held/start", _CHAT)
            _, opened = until(heard, _record("opened"), "the session opening")
            until(heard, _record("asked"), "chat asking")
            key = opened["key"]

            aside = browser.post("/api/btw", {"question": "what is it doing"})
            assert aside.status == 200
            assert aside.json()["answer"].startswith("did: ")
            of_one = browser.post("/api/btw", {"question": "and you", "to": key})
            assert of_one.json()["answer"].startswith("did: ")
            kept = browser.get("/api/btw").json()
            assert kept["open"] == ["", key]
            assert [(one["to"], one["question"]) for one in kept["said"]] == [
                ("", "what is it doing"),
                (key, "and you"),
            ]
            assert browser.post("/api/btw/leave").status == 200
            assert browser.get("/api/btw").json() == {"open": [], "said": []}

            # Nothing asked beside the run reached it: its one session said only its own.
            browser.post("/api/held/stop")
            heard_of_run: list[str] = []
            until(
                heard,
                lambda event, data: (
                    (
                        event == "record"
                        and data.get("kind") == "text"
                        and not heard_of_run.append(data["text"])
                    )
                    or (event == "record" and data.get("type") == "ended")
                ),
                "the run ending",
            )
            assert all("what is it doing" not in text for text in heard_of_run)


def _chatted(browser: Browser, task: str) -> None:
    """Runs chat on a task until it asks back, then stops it."""
    with browser.follows() as heard:
        until(heard, lambda event, data: event == "hello", "hello")
        assert browser.post("/api/held/start", _CHAT | {"task": task}).status == 200
        # The stream begins with what came before: an earlier epic's asking and ending too.
        until(heard, _record("started", task=task), "chat starting")
        until(heard, _record("asked"), "chat asking")
        browser.post("/api/held/stop")
        until(heard, _record("ended"), "the run ending")


def test_an_epic_another_process_goes_with_is_listed_as_running(project: Path) -> None:
    # Held as `hmz exec` holds the run it goes with, which no host here speaks for.
    with Epic("chat", "elsewhere", project) as held, served() as site:
        browser = Browser(site)
        browser.signs_in()

        (ran,) = browser.get("/api/runs").json()["runs"]
        assert (ran["how"], ran["held"]) == ("running", False)
        one = browser.get(f"/api/runs/{held.path.name}").json()
        assert one["how"] == "running"

    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        (ran,) = browser.get("/api/runs").json()["runs"]
        assert ran["how"] == "done"


def test_an_epic_written_down_is_read_back_out_of_the_logs_it_kept(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _chatted(browser, "the first one")

        (ran,) = browser.get("/api/runs").json()["runs"]
        traced = browser.get(f"/api/runs/{ran['name']}/trace").json()["sessions"]
        (session,) = traced
        turns = [one for one in session["actions"] if one["category"] == "turn"]
        assert [one["args"]["prompt"] for one in turns] == ["the first one"]
        said = [
            one["args"].get("text")
            for one in session["actions"]
            if one["category"] == "message"
        ]
        assert "did: the first one" in said


def test_an_epic_written_down_is_laid_out_as_a_timeline_and_each_span_read_whole(
    project: Path,
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _chatted(browser, "the first one")

        (ran,) = browser.get("/api/runs").json()["runs"]
        timeline = browser.get(f"/api/runs/{ran['name']}/timeline").json()
        assert timeline["epic"] == ran["name"]
        assert timeline["live"] is False
        strings = timeline["strings"]
        flow, session = timeline["processes"]
        assert (flow["kind"], strings[flow["name"]]) == ("flow", "chat")
        assert (session["kind"], session["parent"]) == ("session", 0)
        assert strings[session["role"]] == "assistant"
        track = timeline["tracks"][session["tracks"][0]]
        cats = [strings[one] for one in track["spans"]["cat"]]
        assert cats[:2] == ["session", "turn"]
        assert track["spans"]["depth"][:2] == [0, 1]

        turn = track["first"] + 1
        at = f"/api/runs/{ran['name']}/timeline/span/{turn}"
        said = browser.get(f"{at}?layout={timeline['layout']}").json()
        assert (said["cat"], said["args"]["prompt"]) == ("turn", "the first one")
        assert browser.get(f"{at}?layout=moved").status == 409
        for missing in (str(timeline["summary"]["spans"]), "nope"):
            gone = browser.get(f"/api/runs/{ran['name']}/timeline/span/{missing}")
            assert gone.status == 404


def test_a_session_of_an_earlier_epic_is_asked_beside_it_as_a_fork_of_its_history(
    tmp_path: Path, project: Path
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _chatted(browser, "remember papaya")
        _chatted(browser, "and then this")
        earlier, latest = reversed(browser.get("/api/runs").json()["runs"])
        assert latest["task"] == "and then this"

        written = browser.get(f"/api/runs/{earlier['name']}").json()
        kept = Path(written["at"]) / "sessions"
        before = sorted(str(one) for one in kept.rglob("*"))
        # Its session goes by its agent's own name, and the role it filled is said beside it.
        (agent,) = written["agents"]
        assert (agent["role"], written["sessions"][0]["agent"]) == (
            "assistant",
            agent["name"],
        )
        assert agent["name"] != "assistant"

        aside = browser.post(
            "/api/btw",
            {
                "question": "what was the word",
                "to": f"{agent['name']}/1",
                "epic": earlier["name"],
            },
        )

        assert aside.status == 200, aside.body
        said = aside.json()
        assert said["to"] == f"{earlier['name']}/{agent['name']}/1"
        # A fork carries the session's history and is told it is a side copy of it.
        assert "read-only side copy of the flow session" in said["answer"]
        ident = written["sessions"][0]["ident"]
        argv = started(tmp_path)[-1]["argv"]
        assert argv[argv.index("--resume") + 1] == ident
        assert "--fork-session" in argv
        # Nothing of the side conversation is kept where the earlier epic keeps its own.
        assert sorted(str(one) for one in kept.rglob("*")) == before
        browser.post("/api/btw/leave", {})
        assert (
            browser.post(
                "/api/btw",
                {"question": "x", "to": f"{agent['name']}/9", "epic": earlier["name"]},
            ).status
            == 404
        )


def test_an_exported_epic_is_imported_back_by_its_bytes_or_its_path(
    project: Path, tmp_path: Path
) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        with browser.follows() as heard:
            browser.post("/api/held/start", _CHAT)
            until(heard, _record("asked"), "chat asking")
            browser.post("/api/held/stop")
            until(heard, _record("ended"), "the run ending")
        (run,) = browser.get("/api/runs").json()["runs"]
        name = run["name"]
        archive = tmp_path / f"{name}.hmzepic"
        archive.write_bytes(browser.get(f"/api/runs/{name}/bundle").body)
        shutil.rmtree(browser.get(f"/api/runs/{name}").json()["at"])
        assert browser.get(f"/api/runs/{name}").status == 404

        sent = browser.sends("/api/runs/import", archive.read_bytes(), archive.name)
        assert sent.status == 201, sent.body
        assert sent.json() == {
            "name": name,
            "workspace": str(project.resolve()),
            "resumable": False,
            "why": "",
        }
        assert browser.get(f"/api/runs/{name}").json()["foreign"] == ""

        again = browser.sends("/api/runs/import", archive.read_bytes(), archive.name)
        assert again.status == 409
        assert again.json()["name"] == name
        assert "is already here" in again.json()["error"]
        named = browser.post("/api/runs/import", {"path": str(archive)})
        assert (named.status, named.json()["name"]) == (409, name)

        # Somebody else's: a workspace this machine has not got.
        (tmp_path / "theirs").mkdir()
        theirs = elsewhere(archive, "/nowhere/at/all", tmp_path / "theirs")
        shutil.rmtree(browser.get(f"/api/runs/{name}").json()["at"])
        read = browser.post("/api/runs/import", {"path": str(theirs)})
        assert read.status == 201, read.body
        assert (read.json()["workspace"], read.json()["resumable"]) == (
            "/nowhere/at/all",
            False,
        )
        assert "not on this machine" in read.json()["why"]
        one = browser.get(f"/api/runs/{name}").json()
        assert (one["foreign"], one["picks_up"]) == (read.json()["why"], False)

        not_one = browser.sends("/api/runs/import", b"not a bundle", "x.hmzepic")
        assert not_one.status == 400
        assert not_one.json()["error"].startswith("x.hmzepic is not a bundle")
        assert browser.sends("/api/runs/import", b"", "x.txt").status == 400
        assert browser.sends("/api/runs/import", b"", "").status == 400
        assert browser.post("/api/runs/import", {"path": "x.hmzepic"}).status == 400
        plain = {"Content-Type": "text/plain"}
        assert (
            browser.sends("/api/runs/import", b"", "x.hmzepic", **plain).status == 415
        )
        huge = {"Content-Length": str(3 << 30)}
        assert browser.sends("/api/runs/import", b"", "x.hmzepic", **huge).status == 413
        # Nothing sent is kept.
        assert not [*machine().glob("tmp*/x.hmzepic")]
