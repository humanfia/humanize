"""`hmz web`: a run started from a page, followed on its stream, asked about, and read back."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_web import Browser, served, until

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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
        assert listed["counts"] == {"stopped": 1}
        (run,) = listed["runs"]
        assert (run["flow"], run["task"], run["how"]) == (
            "chat",
            "hello there",
            "stopped",
        )
        one = browser.get(f"/api/runs/{run['name']}").json()
        assert [agent["runs"] for agent in one["agents"]] == [f"{AGENT}:auto"]
        assert one["spent"]["output_tokens"] > 0
        assert browser.get(f"/api/runs/{run['name']}/trace").status == 200
        bundle = browser.get(f"/api/runs/{run['name']}/bundle")
        assert bundle.status == 200
        assert bundle.headers["content-disposition"].startswith("attachment;")
        assert browser.get("/api/runs/no-such-run").status == 404


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
            until(heard, _record("asked"), "chat asking")

            aside = browser.post("/api/btw", {"question": "what is it doing"})
            assert aside.status == 200
            assert aside.json()["answer"].startswith("did: ")
            of_one = browser.post(
                "/api/btw", {"question": "and you", "to": "assistant/1"}
            )
            assert of_one.json()["answer"].startswith("did: ")
            kept = browser.get("/api/btw").json()
            assert kept["open"] == ["", "assistant/1"]
            assert [(one["to"], one["question"]) for one in kept["said"]] == [
                ("", "what is it doing"),
                ("assistant/1", "and you"),
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
