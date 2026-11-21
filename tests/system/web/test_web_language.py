"""`hmz web`'s language, driven in a browser: English, Simplified or Traditional Chinese.

The page is the real one, served in the test's own process. The language is this browser's own:
the one chosen in Settings, kept in its storage, or the one the browser asks for where none is
chosen. Each test runs in Chromium and in WebKit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, again, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    # The home it gives the CLI is this machine's home, which the daemon's own settings are of.
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


def _written(page: Page, language: str) -> None:
    """Waits for the page to be open again, written in `language`, on its Language page."""
    expect(page.locator("html")).to_have_attribute("lang", language)
    page.wait_for_selector("[data-hmz=sidebar] .brand")
    expect(page.locator("[data-hmz=settings-language] select")).to_be_visible()


def _kept(page: Page) -> str | None:
    """The language this browser keeps as chosen, or none."""
    return page.evaluate("localStorage.getItem('hmz-language')")


def _ago(page: Page) -> str:
    """How the page says a moment that has only just been."""
    return page.evaluate("async () => (await import('/dom.js')).ago(Date.now() / 1000)")


def test_a_language_is_chosen_in_settings_and_the_page_is_written_in_it(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        # English until another is chosen, where English is what the browser asks for.
        expect(page.locator("html")).to_have_attribute("lang", "en")
        go(page, "/settings/language")
        nav = page.locator(".settings-nav")
        expect(nav.locator("a:visible")).to_contain_text(
            ["Themes", "Daemons", "Notifications", "Language", "General"]
        )
        expect(page.locator(".settings-head h3")).to_have_text("Language")
        picker = page.get_by_label("Language")
        expect(picker).to_have_attribute("data-hmz", "language")
        expect(picker.locator("option")).to_have_text(
            ["System", "English", "简体中文", "繁體中文"]
        )
        expect(picker).to_have_value("")
        # No daemon is picked for it: it is this browser's, whichever daemon is shown.
        expect(page.locator("[data-hmz=settings-daemon]")).to_have_count(0)
        assert _kept(page) is None
        assert _ago(page) == "just now"

        # Chosen, it is kept, and the page opens again where it was, written in it.
        picker.select_option("zh-Hans")
        _written(page, "zh-Hans")
        assert _kept(page) == "zh-Hans"
        assert page.url.endswith("#/settings/language")
        expect(page.locator(".settings-head h3")).to_have_text("语言")
        expect(nav.locator("[aria-current=page]")).to_have_text("语言")
        picker = page.get_by_label("语言")
        expect(picker).to_have_value("zh-Hans")
        # A language is called what it calls itself; only the system's is the page's word.
        expect(picker.locator("option")).to_have_text(
            ["跟随系统", "English", "简体中文", "繁體中文"]
        )
        assert _ago(page) == "刚刚"

        picker.select_option("zh-Hant")
        _written(page, "zh-Hant")
        expect(page.locator(".settings-head h3")).to_have_text("語言")
        assert _ago(page) == "剛剛"

        # Kept: a page opened anew is written in it, and the choice is shown as made.
        again(page)
        _written(page, "zh-Hant")
        picker = page.get_by_label("語言")
        expect(picker).to_have_value("zh-Hant")

        picker.select_option("en")
        _written(page, "en")
        assert _kept(page) == "en"
        expect(page.locator(".settings-head h3")).to_have_text("Language")

        # Under System nothing is kept, and what the browser asks for is followed.
        page.get_by_label("Language").select_option("")
        _written(page, "en")
        assert _kept(page) is None


@pytest.mark.parametrize(
    ("asked", "language", "heading"),
    [
        ("zh-CN", "zh-Hans", "语言"),
        ("zh-SG", "zh-Hans", "语言"),
        ("zh-TW", "zh-Hant", "語言"),
        ("zh-HK", "zh-Hant", "語言"),
        ("fr-FR", "en", "Language"),
    ],
)
def test_with_none_chosen_the_page_follows_what_the_browser_asks_for(
    project: Path, engine: str, asked: str, language: str, heading: str
) -> None:
    with served() as site, opened(site, engine=engine, locale=asked) as page:
        expect(page.locator("html")).to_have_attribute("lang", language)
        go(page, "/settings/language")
        expect(page.locator(".settings-head h3")).to_have_text(heading)
        picker = page.locator("[data-hmz=language]")
        expect(picker).to_have_value("")
        assert _kept(page) is None

        # One chosen is the page's, whatever the browser asks for; System follows it again.
        picker.select_option("en")
        _written(page, "en")
        expect(page.locator(".settings-head h3")).to_have_text("Language")
        page.locator("[data-hmz=language]").select_option("")
        _written(page, language)
        expect(page.locator(".settings-head h3")).to_have_text(heading)


@pytest.mark.parametrize(
    ("asked", "skip", "sidebar", "effort", "gone", "out"),
    [
        (
            "en-US",
            "Skip to the page",
            "Chats and epics",
            "Extra high",
            "The folder ghost is no longer on this machine. Pick another folder.",
            "This browser is not let in.",
        ),
        (
            "zh-CN",
            "跳到页面内容",
            "聊天和史诗",
            "超高",
            "文件夹 ghost 已不在这台机器上。请另选一个文件夹。",
            "此浏览器未获准进入。",
        ),
        (
            "zh-TW",
            "跳至頁面內容",
            "聊天與史詩",
            "超高",
            "資料夾 ghost 已不在這台機器上。請另選一個資料夾。",
            "此瀏覽器未獲准進入。",
        ),
    ],
)
def test_what_every_view_shares_is_said_in_the_pages_language(
    project: Path,
    engine: str,
    asked: str,
    skip: str,
    sidebar: str,
    effort: str,
    gone: str,
    out: str,
) -> None:
    with served() as site, opened(site, engine=engine, locale=asked) as page:
        # What index.html says in English before any script runs is said in the language.
        expect(page.locator("a.skip")).to_have_text(skip)
        expect(page.locator("#sidebar")).to_have_attribute("aria-label", sidebar)
        # An effort is the page's own word; a harness and a model keep their vendor's name.
        said = page.evaluate(
            """async () => {
              const names = await import('/names.js')
              const places = await import('/places.js')
              return [names.effortName('xhigh'), names.harnessName('claude'),
                names.modelName('claude-fable-5-2'), places.goneSaid('/work/ghost')]
            }"""
        )
        assert said == [effort, "Claude Code", "Fable 5.2", gone]

        # A browser that is not let in is told so in its language too.
        browser = page.context.browser
        assert browser is not None
        stranger = browser.new_context(locale=asked)
        try:
            shut = stranger.new_page()
            shut.goto(site.address.split("?")[0])
            expect(shut.locator("#page .empty strong")).to_have_text(out)
            expect(shut.locator("#page .empty code")).to_have_text("hmz web")
        finally:
            stranger.close()


@pytest.mark.parametrize(
    ("asked", "words"),
    [
        (
            "zh-CN",
            {
                "daemon": "本地",
                "env": "这台电脑",
                "runtime": "本机",
                "none": "无目录",
                "row": ["SSH 主机", "手动填写"],
                "way": "由 `claude setup-token` 生成",
                "asks": "`claude setup-token` 输出的令牌",
                "connected": "当前连接",
            },
        ),
        (
            "zh-TW",
            {
                "daemon": "本地",
                "env": "這台電腦",
                "runtime": "本機",
                "none": "無目錄",
                "row": ["SSH 主機", "手動填寫"],
                "way": "由 `claude setup-token` 產生",
                "asks": "`claude setup-token` 輸出的權杖",
                "connected": "目前連線",
            },
        ),
    ],
)
def test_in_chinese_the_daemon_the_env_and_the_runtime_each_have_a_word_of_their_own(
    project: Path, engine: str, asked: str, words: dict[str, Any]
) -> None:
    """Which hmz serves, where a chat works and the machine it runs on are never one word."""
    assert len({words["daemon"], words["env"], words["runtime"]}) == 3
    with served() as site, opened(site, engine=engine, locale=asked) as page:
        # A new chat: the daemon at the sidebar's foot, the env under the box, and the
        # choice of no folder by the word the sidebar groups such chats under.
        go(page, "/new/chat")
        chip = page.locator("[data-hmz=start] [data-hmz=environment]")
        expect(chip).to_contain_text(words["env"])
        expect(chip).not_to_contain_text(words["daemon"])
        page.locator("[data-hmz=start] [data-hmz=folder]").click()
        expect(page.get_by_role("menuitem").first).to_contain_text(words["none"])
        page.keyboard.press("Escape")

        # A new epic: the daemon in a part of its own, not in the environment's.
        go(page, "/new")
        serving = page.locator("[data-hmz=setup-serving]")
        expect(serving.locator(".setup-name")).to_have_text(words["connected"])
        expect(serving.locator("[data-hmz=daemon]")).to_have_text(words["daemon"])
        expect(
            page.locator("[data-hmz=setup-environment] [data-hmz=daemon]")
        ).to_have_count(0)

        # The runtimes: this machine by the runtime's word, and what the daemon names out
        # of a closed set -- a backend, how a runtime was made -- in the page's language.
        page.evaluate(
            "async () => (await import('/api.js')).call('runtimes.set',"
            " {backend: 'ssh', name: 'gpu', fields: {host: 'gpu.lab'}})"
        )
        go(page, "/settings/runtimes")
        expect(page.locator("[data-hmz=runtime-local] b")).to_have_text(
            words["runtime"]
        )
        row = page.locator("[data-hmz=runtime]")
        for said in words["row"]:
            expect(row).to_contain_text(said)
        assert "typed" not in row.inner_text()

        # A way of signing in, and what it asks for, say what they are in the language.
        go(page, "/settings/accounts")
        page.locator("#account-cli").select_option("claude")
        page.locator("#account-way").select_option("token")
        form = page.locator("form:has(#account-way)")
        expect(form.locator("p.hint")).to_contain_text(words["way"])
        expect(form.locator(".field .hint").first).to_contain_text(words["asks"])


def test_a_language_chosen_in_one_tab_is_every_tabs(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        other = page.context.new_page()
        other.goto(site.address)
        other.wait_for_selector("[data-hmz=sidebar] .brand")
        expect(other.locator("html")).to_have_attribute("lang", "en")

        go(page, "/settings/language")
        page.locator("[data-hmz=language]").select_option("zh-Hant")
        _written(page, "zh-Hant")
        expect(other.locator("html")).to_have_attribute("lang", "zh-Hant")
        other.wait_for_selector("[data-hmz=sidebar] .brand")


def test_the_language_page_fits_a_phone_in_every_language(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, width=390, height=780) as page:
        go(page, "/settings/language")
        for language in ("zh-Hans", "zh-Hant", "en"):
            page.locator("[data-hmz=language]").select_option(language)
            _written(page, language)
            body = page.locator("[data-hmz=settings-language]")
            for part in (body.locator("select"), body.locator(".hint")):
                box = part.bounding_box()
                assert box is not None
                assert box["x"] >= 0, language
                assert box["x"] + box["width"] <= 390, language
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), language
