//! The window's chrome, one with the page: no title bar of its own but the traffic lights, where
//! macOS puts them, over a strip the page keeps for them, and the page told it is in the app, and
//! when the window is full screen and they are gone, to keep it no more. On Windows, the caption
//! buttons, drawn by the app over the top right of whichever page the window shows.

use std::sync::atomic::{AtomicBool, Ordering};

#[cfg(target_os = "macos")]
use tauri::TitleBarStyle;
use tauri::{Manager, Runtime, WebviewWindow, WebviewWindowBuilder, Window};

/// What WKWebView says it is where it is not told otherwise.
#[cfg(target_os = "macos")]
const WEBKIT: &str =
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)";

/// Minimize, maximize and close, 46×32 px each as Windows draws them, in a shadow root the page's
/// style never reaches, and outside its body, which may drag the window. Styled by a sheet built
/// in script, which no page's `style-src` refuses.
#[cfg(windows)]
const CAPTION: &str = r#"addEventListener('DOMContentLoaded', () => {
  const host = document.createElement('humanize-caption')
  const root = host.attachShadow({ mode: 'closed' })
  const sheet = new CSSStyleSheet()
  sheet.replaceSync(`
    :host { position: fixed; top: 0; right: 0; z-index: 2147483647; display: flex; color: CanvasText }
    :host([hidden]) { display: none }
    button { all: unset; width: 46px; height: 32px; display: grid; place-items: center;
      font: 10px 'Segoe Fluent Icons', 'Segoe MDL2 Assets'; color: inherit }
    button:hover { background: color-mix(in srgb, currentColor 9%, transparent) }
    button:active { background: color-mix(in srgb, currentColor 6%, transparent) }
    #close:hover { background: #c42b1c; color: #fff }
    #close:active { background: #c84031; color: #fff }`)
  root.adoptedStyleSheets = [sheet]
  const { invoke, metadata } = window.__TAURI_INTERNALS__
  const button = (id, glyph, name) => {
    const button = document.createElement('button')
    button.id = id
    button.onclick = () => invoke(`plugin:window|${id}`, { label: metadata.currentWindow.label })
    const label = (glyph, name) => {
      button.textContent = glyph
      button.title = name
      button.ariaLabel = name
    }
    label(glyph, name)
    root.append(button)
    return label
  }
  button('minimize', '', 'Minimize')
  const toggle = button('toggle_maximize', '', 'Maximize')
  button('close', '', 'Close')
  window.__HUMANIZE_CAPTION__ = (full, max) => {
    host.hidden = full
    if (max) toggle('', 'Restore Down')
    else toggle('', 'Maximize')
  }
  document.documentElement.append(host)
})"#;

/// Whether the window is full screen, and maximized, as the page was last told.
static FULL: AtomicBool = AtomicBool::new(false);
static MAX: AtomicBool = AtomicBool::new(false);

/// The window's chrome: the page drawn up to its top edge, under the traffic lights.
#[cfg(target_os = "macos")]
pub fn dress<'a, R: Runtime, M: Manager<R>>(
    window: WebviewWindowBuilder<'a, R, M>,
    version: &str,
) -> WebviewWindowBuilder<'a, R, M> {
    window
        .title_bar_style(TitleBarStyle::Overlay)
        .hidden_title(true)
        .user_agent(&user_agent(version))
}

/// The window's chrome: the page drawn up to its top edge, under the caption buttons, in a
/// window with a shadow and Windows 11's corners; WebView2's own keys reload and zoom.
#[cfg(windows)]
pub fn dress<'a, R: Runtime, M: Manager<R>>(
    window: WebviewWindowBuilder<'a, R, M>,
    version: &str,
) -> WebviewWindowBuilder<'a, R, M> {
    let webview = tauri::webview_version().unwrap_or_default();
    window
        .decorations(false)
        .shadow(true)
        .zoom_hotkeys_enabled(true)
        .initialization_script(CAPTION)
        .user_agent(&user_agent(&webview, version))
}

/// WKWebView's own user agent, and the app's, which `hmz web`'s page draws its top row by.
#[cfg(target_os = "macos")]
fn user_agent(version: &str) -> String {
    format!("{WEBKIT} humanize-desktop/{version}")
}

/// What WebView2 says it is, of the version installed, and the app's, which `hmz web`'s page
/// draws its top row by.
#[cfg(windows)]
fn user_agent(webview: &str, version: &str) -> String {
    let major = webview.split('.').next().unwrap_or_default();
    format!(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) \
         Chrome/{major}.0.0.0 Safari/537.36 Edg/{major}.0.0.0 humanize-desktop/{version}"
    )
}

/// Tells the page in the window whether it is full screen, or maximized, once that changes.
pub fn resized<R: Runtime>(window: &Window<R>) {
    let full = window.is_fullscreen().unwrap_or(false);
    let max = cfg!(windows) && window.is_maximized().unwrap_or(false);
    let changed = FULL.swap(full, Ordering::Relaxed) != full;
    if (MAX.swap(max, Ordering::Relaxed) != max || changed)
        && let Some(webview) = window.get_webview_window(window.label())
    {
        tell(&webview);
    }
}

/// Tells a page whether the window is full screen: each page newly loaded, too.
pub fn tell<R: Runtime>(webview: &WebviewWindow<R>) {
    let full = FULL.load(Ordering::Relaxed);
    let _ = webview.eval(script(full));
    #[cfg(windows)]
    let _ = webview.eval(caption(full, MAX.load(Ordering::Relaxed)));
}

fn script(full: bool) -> String {
    format!("document.documentElement.toggleAttribute('data-fullscreen', {full})")
}

/// The caption buttons, gone in full screen, and maximize's restoring once maximized.
#[cfg(windows)]
fn caption(full: bool, max: bool) -> String {
    format!("window.__HUMANIZE_CAPTION__?.({full}, {max})")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(target_os = "macos")]
    #[test]
    fn says_it_is_the_app_after_what_webkit_says() {
        let agent = user_agent("1.2.3");
        assert!(agent.starts_with("Mozilla/5.0 (Macintosh;"));
        assert!(agent.ends_with(" humanize-desktop/1.2.3"));
    }

    #[cfg(windows)]
    #[test]
    fn says_it_is_the_app_after_what_webview2_says() {
        let agent = user_agent("130.0.2849.68", "1.2.3");
        assert!(agent.starts_with("Mozilla/5.0 (Windows NT 10.0; Win64; x64)"));
        assert!(agent.contains(" Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0 "));
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

    #[cfg(windows)]
    #[test]
    fn tells_the_caption_whether_the_window_is_maximized() {
        assert_eq!(
            caption(false, true),
            "window.__HUMANIZE_CAPTION__?.(false, true)"
        );
    }
}
