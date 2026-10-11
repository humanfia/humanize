//! The window's chrome, one with the page: no title bar of its own but the traffic lights,
//! standing over the page's top row, and the page told it is in the app, and when the window is
//! full screen and they are gone, to draw that row around them.

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{
    LogicalPosition, Manager, Runtime, TitleBarStyle, WebviewWindow, WebviewWindowBuilder, Window,
};

/// Where the traffic lights stand: centred on the page's top row, 57 pixels tall, and inset from
/// its left edge as far as from the top.
const LIGHTS: LogicalPosition<f64> = LogicalPosition { x: 20.0, y: 21.0 };

/// What WKWebView says it is where it is not told otherwise.
const WEBKIT: &str =
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)";

/// Whether the window is full screen, as the page was last told.
static FULL: AtomicBool = AtomicBool::new(false);

/// The window's chrome: the page drawn up to its top edge, under the traffic lights.
pub fn dress<'a, R: Runtime, M: Manager<R>>(
    window: WebviewWindowBuilder<'a, R, M>,
    version: &str,
) -> WebviewWindowBuilder<'a, R, M> {
    window
        .title_bar_style(TitleBarStyle::Overlay)
        .hidden_title(true)
        .traffic_light_position(LIGHTS)
        .user_agent(&user_agent(version))
}

/// WKWebView's own user agent, and the app's, which `hmz web`'s page draws its top row by.
fn user_agent(version: &str) -> String {
    format!("{WEBKIT} humanize-desktop/{version}")
}

/// Tells the page in the window whether it is full screen, once that changes.
pub fn resized<R: Runtime>(window: &Window<R>) {
    let full = window.is_fullscreen().unwrap_or(false);
    if FULL.swap(full, Ordering::Relaxed) != full
        && let Some(webview) = window.get_webview_window(window.label())
    {
        tell(&webview);
    }
}

/// Tells a page whether the window is full screen: each page newly loaded, too.
pub fn tell<R: Runtime>(webview: &WebviewWindow<R>) {
    let _ = webview.eval(script(FULL.load(Ordering::Relaxed)));
}

fn script(full: bool) -> String {
    format!("document.documentElement.toggleAttribute('data-fullscreen', {full})")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn says_it_is_the_app_after_what_webkit_says() {
        let agent = user_agent("1.2.3");
        assert!(agent.starts_with("Mozilla/5.0 (Macintosh;"));
        assert!(agent.ends_with(" humanize-desktop/1.2.3"));
    }

    #[test]
    fn tells_the_page_whether_it_is_full_screen() {
        assert_eq!(
            script(true),
            "document.documentElement.toggleAttribute('data-fullscreen', true)"
        );
        assert_eq!(
            script(false),
            "document.documentElement.toggleAttribute('data-fullscreen', false)"
        );
    }
}
