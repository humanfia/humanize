"""The Environments view: a host's environments listed by role, and the one picked with its panels.

The host is faked on the wire -- an `envs` snapshot of two roles and a worktree derived from
one -- and each panel's module is either a stand-in the test serves, which records what the frame
gives it, or missing, which the frame says is unavailable. A chat going on Local opens its own
environment in its side panel. Each in Chromium and in WebKit.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, frame, go, opened

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: Where the faked host says it is: no workspace of Local's.
_FAKE = "/nowhere/fake-workspace"

#: The subscription the faked host is attached by.
_SUB = "s-envs"


def _env(ident: str, role: str, **more: Any) -> dict[str, Any]:
    run, chain = ident.split(":", 1)
    return {
        "id": ident,
        "role": role,
        "chain": chain,
        "parent": None,
        "run": int(run),
        "backend": "docker",
        "provider": "local",
        "workdir": f"/work/{chain}",
        "available": True,
        "open": True,
        "caps": ["files", "shell", "bash", "git"],
        "declared": [],
        "facts": {"cpu": 8, "memory": 16 * 1024**3, "gpu_count": 0},
        **more,
    }


#: Two roles, a worktree derived from the coder's, and one of the reviewer's closed.
_ENVS = [
    _env("1:coder", "coder", declared=["git"]),
    _env(
        "1:coder/wt",
        "coder",
        parent="1:coder",
        caps=["files", "shell", "git_worktree"],
        backend="local",
    ),
    _env("1:reviewer", "reviewer", caps=["files", "shell"], declared=["shell"]),
    _env("1:old", "reviewer", open=False),
]

#: A panel module standing in for one a later change brings: it says what the frame gave it.
_STUB = """
export async function mount(el, ctx) {
  const kind = import.meta.url.split('/').pop().replace('.js', '')
  ;(window.mounted ||= []).push(`${kind}:${ctx.env.id}`)
  window.ctxs = { ...(window.ctxs || {}), [kind]: ctx }
  const box = document.createElement('textarea')
  box.dataset.hmz = `stub-${kind}`
  el.append(box)
  ctx.on('term', (message) => (window.heard = message))
  return {
    leave: () => (window.left ||= []).push(`${kind}:${ctx.env.id}`),
    reveal: (args) => (window.revealed = { kind, ...args }),
  }
}
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


class _EnvWire(Wire):
    """The wire, which also tells the page what a faked host says."""

    def event(self, sub: str, message: dict[str, Any]) -> None:
        """Tells the page one message of the host attached by `sub`."""
        assert self._page is not None
        self._page.send(
            frame(
                {
                    "jsonrpc": "2.0",
                    "method": "epic.event",
                    "params": {"sub": sub, "message": message},
                }
            )
        )


def _panels(page: Page, *, stubbed: tuple[str, ...]) -> None:
    """Serves a stand-in for each panel named, and none for the others."""

    def served_(route: Route) -> None:
        name = route.request.url.rsplit("/", 1)[1].split("?")[0].removesuffix(".js")
        if name in stubbed:
            route.fulfill(status=200, content_type="text/javascript", body=_STUB)
        else:
            route.fulfill(status=404, body="")

    page.route(
        re.compile(r".*/views/envs/(files|terminal|changes)\.js(\?.*)?$"), served_
    )


def _faked_host(wire: _EnvWire, page: Page) -> None:
    """Waits for the page to attach to the faked host, then tells it the environments."""
    while not wire.params("epic.attach"):
        page.wait_for_timeout(50)
    wire.event(_SUB, {"type": "welcome", "epoch": "e1", "client": "c1"})
    wire.event(_SUB, {"type": "envs", "envs": _ENVS})


def _until(page: Page, check: str) -> None:
    """Waits until what `check` says of the page holds."""
    for _ in range(600):
        if page.evaluate(f"() => Boolean({check})"):
            return
        page.wait_for_timeout(50)
    raise AssertionError(check)


def _attached(params: dict[str, Any]) -> dict[str, Any]:
    return {"result": {"sub": _SUB, "workspace": params.get("workspace"), "slot": ""}}


def test_the_environments_are_listed_and_each_opens_its_panels(
    project: Path, engine: str
) -> None:
    wire = _EnvWire(
        faked={
            "epic.attach": _attached,
            "epic.detach": lambda _: {"result": {}},
            "env.list": lambda _: {"result": {"path": "/work/coder", "entries": []}},
        }
    )

    def routed(page: Page) -> None:
        wire.routes(page)
        _panels(page, stubbed=("files",))

    with served() as site, opened(site, engine=engine, routed=routed) as page:
        go(page, f"/envs/live?workspace={_FAKE}")
        _faked_host(wire, page)

        # Grouped by role, the worktree under the env it came from, the closed one dimmed.
        tree = page.locator("[data-hmz=envs-tree]")
        expect(tree.locator(".envs-role")).to_have_text(["coder", "reviewer"])
        items = tree.locator("[data-hmz=envs-item]")
        expect(items).to_have_count(4)
        expect(items.nth(1)).to_have_attribute("data-env", "1:coder/wt")
        expect(items.nth(1)).to_have_attribute("aria-level", "2")
        expect(items.nth(3)).to_have_class(re.compile(r"\boff\b"))

        # The latest run's first open env, opened on what its flow uses: Changes.
        expect(items.nth(0)).to_have_attribute("aria-selected", "true")
        head = page.locator("[data-hmz=envs-head]")
        expect(head.locator("[data-hmz=envs-backend]")).to_have_text("docker · local")
        expect(head.locator("[data-hmz=envs-facts]")).to_have_text(
            "8 CPUs · 16 GiB memory"
        )
        expect(head.locator("[data-hmz=envs-uses]")).to_contain_text("git")
        tabs = page.locator("[data-hmz=envs-tabs] [role=tab]")
        expect(tabs).to_have_text(["Files", "Terminal", "Changes•"])
        expect(page.locator("[data-hmz=envs-tab-changes]")).to_have_attribute(
            "aria-selected", "true"
        )
        # Its panel is not on this page: said so, where it would be.
        expect(
            page.locator("[data-hmz=envs-pane-changes] [data-hmz=envs-unavailable]")
        ).to_contain_text("This panel is unavailable.")
        expect(page).to_have_url(re.compile(re.escape("env=1%3Acoder&tab=changes")))

        # A panel opened is kept, hidden, while another is shown.
        page.locator("[data-hmz=envs-tab-files]").click()
        stub = page.locator("[data-hmz=stub-files]")
        stub.fill("still here")
        expect(page).to_have_url(re.compile(re.escape("tab=files")))
        page.locator("[data-hmz=envs-tab-terminal]").click()
        expect(stub).to_be_hidden()
        expect(
            page.locator("[data-hmz=envs-pane-terminal] [data-hmz=envs-unavailable]")
        ).to_be_visible()
        page.locator("[data-hmz=envs-tab-files]").click()
        expect(stub).to_have_value("still here")
        assert page.evaluate("window.mounted") == ["files:1:coder"]

        # What a panel is given: calls naming the environment on the host's subscription,
        # the host's messages, its own keeping, the theme, and being opened at a place.
        page.evaluate("window.ctxs.files.call('env.list', { path: '.' })")
        assert wire.params("env.list") == [{"path": ".", "env": "1:coder", "sub": _SUB}]
        wire.event(_SUB, {"type": "term", "term": "t1", "data": "aGk="})
        _until(page, "window.heard && window.heard.term === 't1'")
        assert page.evaluate(
            """(() => {
              const kept = window.ctxs.files
              kept.keep('open', ['a.py'])
              return kept.keep('open')
            })()"""
        ) == ["a.py"]
        theme = page.evaluate("window.ctxs.files.theme()")
        assert theme["dark"] is False
        assert theme["tokens"]["paper"]
        page.locator("[data-hmz=envs-tab-terminal]").click()
        page.evaluate("window.ctxs.files.open('files', { path: 'a.py', line: 3 })")
        _until(page, "window.revealed && window.revealed.line === 3")
        expect(page.locator("[data-hmz=envs-tab-files]")).to_have_attribute(
            "aria-selected", "true"
        )

        # Another environment: the last one's panels are left, and the new one opens on Files.
        items.nth(1).click()
        expect(page).to_have_url(re.compile(re.escape("env=1%3Acoder%2Fwt&tab=files")))
        expect(tabs).to_have_text(["Files", "Terminal", "Changes"])
        _until(page, "window.mounted.length === 2")
        assert page.evaluate("window.left") == ["files:1:coder"]

        # By the keyboard: down the list, and picked.
        items.nth(1).focus()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        expect(items.nth(2)).to_have_attribute("aria-selected", "true")
        expect(tabs).to_have_text(["Files", "Terminal•"])

        # One closed is said to be, and nothing in it opens.
        items.nth(3).click()
        expect(page.locator("[data-hmz=envs-off]")).to_contain_text(
            "This environment has closed."
        )
        expect(page.locator("[data-hmz=envs-tabs]")).to_be_hidden()

        # The list is as wide as it was last left, by the keyboard too.
        resizer = page.locator("[data-hmz=envs-resizer]")
        before = int(resizer.get_attribute("aria-valuenow") or 0)
        resizer.focus()
        page.keyboard.press("ArrowRight")
        expect(resizer).to_have_attribute("aria-valuenow", str(before + 16))
        assert page.evaluate("localStorage.getItem('hmz-envs-tree')") == str(
            before + 16
        )

        items.nth(0).click()
        page.locator("[data-hmz=envs-tab-files]").click()
        expect(page.locator("[data-hmz=stub-files]")).to_be_visible()
        # Kept where whoever runs it asked, to look at.
        # Chromium alone: WebKit's screenshot sets a style the page's policy refuses.
        if (to := os.environ.get("HMZ_SCREENSHOTS")) and engine == "chromium":
            page.screenshot(path=str(Path(to) / f"envs-frame-{engine}.png"))

        # It can no longer do git: its Changes go, and what it shows stays.
        fewer = [{**_ENVS[0], "caps": ["files", "shell"]}, *_ENVS[1:]]
        wire.event(_SUB, {"type": "envs", "envs": fewer})
        expect(tabs).to_have_text(["Files", "Terminal"])
        expect(page.locator("[data-hmz=envs-pane-changes]")).to_have_count(0)
        expect(page.locator("[data-hmz=stub-files]")).to_be_visible()

        # It closes: what was read of it stays shown, and nothing in it can be changed.
        closed = [{**fewer[0], "open": False}, *fewer[1:]]
        wire.event(_SUB, {"type": "envs", "envs": closed})
        expect(page.locator("[data-hmz=envs-off]")).to_contain_text(
            "This environment has closed."
        )
        expect(page.locator("[data-hmz=stub-files]")).to_be_visible()
        expect(page.locator("[data-hmz=envs-panes]")).to_have_attribute("inert", "")
        expect(
            page.locator("[data-hmz=envs-tabs] [role=tab]:not([hidden])")
        ).to_have_text(["Files"])


def test_a_phone_folds_the_list_into_a_picker(project: Path, engine: str) -> None:
    wire = _EnvWire(
        faked={"epic.attach": _attached, "epic.detach": lambda _: {"result": {}}}
    )

    def routed(page: Page) -> None:
        wire.routes(page)
        _panels(page, stubbed=())

    with (
        served() as site,
        opened(site, engine=engine, routed=routed, width=390, height=800) as page,
    ):
        go(page, f"/envs/live?workspace={_FAKE}&env=1%3Areviewer")
        _faked_host(wire, page)
        expect(page.locator("[data-hmz=envs-tab-terminal]")).to_have_attribute(
            "aria-selected", "true"
        )
        expect(page.locator("[data-hmz=envs-tree]")).to_be_hidden()
        expect(page.locator("[data-hmz=envs-resizer]")).to_be_hidden()
        picker = page.locator("[data-hmz=envs-select]")
        expect(picker).to_be_visible()
        expect(picker).to_have_value("1:reviewer")
        picker.select_option("1:coder")
        expect(page).to_have_url(re.compile(re.escape("env=1%3Acoder&tab=changes")))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            "the page scrolls sideways"
        )
        gutter = page.locator("[data-hmz=envs-head]").evaluate(
            "(el) => getComputedStyle(el).paddingLeft"
        )
        assert gutter == "16px"


#: The chat faked: its slot, its id, the run it has going, and what `chat.get` answers of it.
_SLOT = "chat:fake"
#: The chat's host, as an address's query names it.
_HOST = urlencode({"workspace": _FAKE, "slot": _SLOT})
_CHAT = "20261117T000000.000Z-c4a7e0"
_STARTED = {
    "flow": "chat",
    "ref": "chat:chat",
    "task": "hello there",
    "by": "me@web",
    "client": "c1",
    "roles": ["assistant"],
    "names": {"assistant": "Ada"},
    "outworlders": ["human"],
    "agents": {"assistant": "claude/claude-haiku-4-5"},
    "envs": {},
    "params": {},
    "began": 100.0,
    "at": 1794879452.0,
}
_DETAIL: dict[str, Any] = {
    "id": _CHAT,
    "title": "hello there",
    "workspace": _FAKE,
    "workdir": _FAKE,
    "agent": "claude/claude-haiku-4-5",
    "model": "claude-haiku-4-5",
    "began": "2026-11-17T00:00:00.000Z",
    "updated": "2026-11-17T00:00:00.000Z",
    "state": "going",
    "slot": _SLOT,
    "asking": [],
    "permission": "workspace-write",
    "archived": False,
    "spent": None,
    "at": "/nowhere/chat",
    "task": "hello there",
    "prefer": "",
    "forked": "",
    "agents": [{"name": "Ada", "role": "assistant", "runs": "claude/claude-haiku-4-5"}],
    "sessions": [],
    "earlier": 0,
    "backup": [],
    "backed": {},
}


def test_a_chat_opens_its_environment_beside_it(project: Path, engine: str) -> None:
    wire = _EnvWire(
        faked={
            "epic.attach": lambda params: {
                "result": {"sub": _SUB, "workspace": _FAKE, "slot": _SLOT}
            },
            "epic.detach": lambda _: {"result": {}},
            "chat.get": lambda _: {"result": _DETAIL},
        }
    )

    def routed(page: Page) -> None:
        wire.routes(page)
        _panels(page, stubbed=())

    workspace = _env(
        "1:workspace", "workspace", backend="local", workdir=_FAKE, declared=[]
    )
    with served() as site, opened(site, engine=engine, routed=routed) as page:
        go(page, f"/live?workspace={_FAKE}&slot={_SLOT}")
        while not wire.params("epic.attach"):
            page.wait_for_timeout(50)
        messages: list[dict[str, Any]] = [
            {
                "type": "welcome",
                "epoch": "e1",
                "client": "c1",
                "workspace": _FAKE,
                "slot": _SLOT,
            },
            {
                "type": "run",
                "state": "running",
                "run": 1,
                "epic": "",
                "chat": _CHAT,
                "slot": _SLOT,
                "turn": "",
                **_STARTED,
            },
            {"type": "sessions", "run": 1, "open": ["Ada/1"], "working": []},
            {"type": "pending", "pending": []},
            {"type": "envs", "envs": [workspace]},
            {"type": "started", "seq": 1, "run": 1, **_STARTED},
            {
                "type": "opened",
                "seq": 2,
                "run": 1,
                "key": "Ada/1",
                "agent": "Ada",
                "role": "assistant",
                "env": {"role": "workspace", "kind": "local", "workdir": _FAKE},
            },
            {
                "type": "env_used",
                "seq": 3,
                "run": 1,
                "env": "1:workspace",
                "by": "web",
                "what": "wrote",
                "path": "notes.md",
            },
            {"type": "live", "seq": 3, "elided": 0},
        ]
        for message in messages:
            wire.event(_SUB, message)

        # What was done in it is said dimly, where the chat is read.
        expect(page.locator("[data-hmz=thread] [data-hmz=env-used]")).to_have_text(
            "·web wrote notes.md in workspace"
        )

        # In the chat's menu, with everything else that is done to the chat.
        page.locator("[data-hmz=chat-menu]").click()
        opener = page.locator("[data-hmz=env-open]")
        expect(opener).to_be_visible()
        opener.click()
        panel = page.locator("[data-hmz=inspector]")
        expect(panel).to_be_visible()
        # Headed by the panel shown, with no tabs: the bar's buttons pick it.
        title = panel.locator("[data-hmz=pane-title]")
        expect(title).to_have_text("Files")
        expect(panel.get_by_role("tab").locator("visible=true")).to_have_count(0)
        frame_ = panel.locator("[data-hmz=envs]")
        expect(frame_.locator("[data-hmz=envs-name]")).to_have_text("workspace")
        expect(frame_.locator("[data-hmz=envs-tree]")).to_have_count(0)
        expect(frame_.locator("[data-hmz=envs-tab-files]")).to_have_attribute(
            "aria-selected", "true"
        )
        expect(frame_.locator("[data-hmz=envs-unavailable]")).to_be_visible()
        expect(frame_.locator("[data-hmz=envs-full]")).to_have_attribute(
            "href", f"#/envs/live?{_HOST}&chat={_CHAT}&env=1%3Aworkspace&tab=files"
        )

        # The bar's buttons each open the environment on a panel of its own, say which
        # is open -- wherever it was picked -- and shut the panel where it is the one open.
        bar = page.locator("[data-hmz=bar]")
        pressed = bar.locator(".pane-toggle[aria-pressed=true]")
        expect(pressed).to_have_attribute("data-hmz", "pane-files")
        for pane in ("terminal", "changes", "files"):
            button = bar.locator(f"[data-hmz=pane-{pane}]")
            expect(button).to_be_enabled()
            button.click()
            expect(pressed).to_have_attribute("data-hmz", f"pane-{pane}")
            expect(frame_.locator(f"[data-hmz=envs-tab-{pane}]")).to_have_attribute(
                "aria-selected", "true"
            )
            expect(title).to_have_text(pane.capitalize())
        bar.locator("[data-hmz=pane-changes]").click()
        expect(pressed).to_have_attribute("data-hmz", "pane-changes")
        expect(frame_.locator("[data-hmz=envs-tabs]")).to_be_hidden()
        bar.locator("[data-hmz=pane-changes]").click()
        expect(panel).to_be_hidden()
        expect(pressed).to_have_count(0)
        bar.locator("[data-hmz=pane-details]").click()
        expect(pressed).to_have_attribute("data-hmz", "pane-details")
        expect(title).to_have_text("Details")
        bar.locator("[data-hmz=pane-files]").click()
        expect(frame_.locator("[data-hmz=envs-tab-files]")).to_have_attribute(
            "aria-selected", "true"
        )

        # The row of tabs drawn again -- a board put up -- leaves the environment as it was.
        frame_.evaluate("(el) => (el.dataset.marked = 'yes')")
        wire.event(_SUB, {"type": "board", "items": [{"key": "k", "value": "v"}]})
        expect(frame_).to_have_attribute("data-marked", "yes")
        # The board is a pane of View options, beside the side questions.
        bar.locator("[data-hmz=chat-view]").click()
        expect(
            page.get_by_role("menu", name="View options").get_by_role("menuitem")
        ).to_have_text(["Side questions", "Board"])
        page.keyboard.press("Escape")
        expect(frame_).to_have_attribute("data-marked", "yes")

        # The Details tab links where the chat works to it, and says what was done in it.
        bar.locator("[data-hmz=pane-details]").click()
        expect(panel.locator("[data-hmz=env-link]")).to_have_attribute(
            "href", f"#/envs/live?{_HOST}&chat={_CHAT}&env=1%3Aworkspace"
        )
        expect(panel.locator("[data-hmz=envs-open]")).to_have_attribute(
            "href", f"#/envs/live?{_HOST}&chat={_CHAT}"
        )
        expect(panel.locator("[data-hmz=env-used-list]")).to_contain_text(
            "web wrote notes.md in workspace"
        )

        # Followed, it opens the environment in a view of its own.
        panel.locator("[data-hmz=env-link]").click()
        expect(page.locator("[data-hmz=envs-view] [data-hmz=envs-item]")).to_have_count(
            1
        )
        expect(page.locator("[data-hmz=envs-view] [data-hmz=envs-epic]")).to_have_text(
            "hello there"
        )
