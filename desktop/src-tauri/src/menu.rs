//! The menu bar: what a Mac app has, and nothing that takes a shortcut the page binds --
//! Cmd+K, Cmd+Shift+O and Cmd+. are its own.

use tauri::menu::{AboutMetadata, Menu, MenuEvent, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Manager, Runtime};

/// Where the documentation is.
pub const DOCS: &str = "https://docs.humanfia.ai/humanize/";

/// Check for Updates…, and what it says while a look by hand runs.
const CHECK: &str = "check-for-updates";
const CHECK_LABEL: &str = "Check for Updates…";
const CHECKING_LABEL: &str = "Checking for Updates…";

/// How far each Zoom In or Zoom Out goes, and how far they may go in all.
const ZOOM_STEP: f64 = 1.1;
const ZOOM_RANGE: (f64, f64) = (0.5, 3.0);

pub fn build<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<Menu<R>> {
    let about = AboutMetadata {
        website: Some(DOCS.into()),
        website_label: Some("Documentation".into()),
        ..Default::default()
    };
    let separator = || PredefinedMenuItem::separator(app);
    let item = |id: &str, label: &str, shortcut: &str| {
        MenuItem::with_id(app, id, label, true, Some(shortcut))
    };
    let window = Submenu::with_items(
        app,
        "Window",
        true,
        &[
            &PredefinedMenuItem::minimize(app, None)?,
            &PredefinedMenuItem::maximize(app, Some("Zoom"))?,
            &separator()?,
            &PredefinedMenuItem::close_window(app, None)?,
        ],
    )?;
    let help = Submenu::with_items(
        app,
        "Help",
        true,
        &[&MenuItem::with_id(
            app,
            "docs",
            "Documentation",
            true,
            None::<&str>,
        )?],
    )?;
    let menu = Menu::with_items(
        app,
        &[
            &Submenu::with_items(
                app,
                "humanize",
                true,
                &[
                    &PredefinedMenuItem::about(app, Some("About humanize"), Some(about))?,
                    // Off in a development build, which is never updated.
                    &MenuItem::with_id(
                        app,
                        CHECK,
                        CHECK_LABEL,
                        crate::update::checks(&app.package_info().version),
                        None::<&str>,
                    )?,
                    &separator()?,
                    &PredefinedMenuItem::hide(app, None)?,
                    &PredefinedMenuItem::hide_others(app, None)?,
                    &PredefinedMenuItem::show_all(app, None)?,
                    &separator()?,
                    &PredefinedMenuItem::quit(app, None)?,
                ],
            )?,
            // WKWebView copies and pastes only through these.
            &Submenu::with_items(
                app,
                "Edit",
                true,
                &[
                    &PredefinedMenuItem::undo(app, None)?,
                    &PredefinedMenuItem::redo(app, None)?,
                    &separator()?,
                    &PredefinedMenuItem::cut(app, None)?,
                    &PredefinedMenuItem::copy(app, None)?,
                    &PredefinedMenuItem::paste(app, None)?,
                    &PredefinedMenuItem::select_all(app, None)?,
                ],
            )?,
            &Submenu::with_items(
                app,
                "View",
                true,
                &[
                    &item("reload", "Reload", "CmdOrCtrl+R")?,
                    &separator()?,
                    &item("actual-size", "Actual Size", "CmdOrCtrl+0")?,
                    &item("zoom-in", "Zoom In", "CmdOrCtrl+=")?,
                    &item("zoom-out", "Zoom Out", "CmdOrCtrl+-")?,
                    &separator()?,
                    &PredefinedMenuItem::fullscreen(app, None)?,
                ],
            )?,
            &window,
            &help,
        ],
    )?;
    window.set_as_windows_menu_for_nsapp()?;
    help.set_as_help_menu_for_nsapp()?;
    Ok(menu)
}

/// What a menu item of this app's own does.
pub fn handle<R: Runtime>(app: &AppHandle<R>, event: MenuEvent) {
    let Some(window) = app.get_webview_window(crate::MAIN) else {
        return;
    };
    let zoom = |to: fn(f64) -> f64| {
        let shell = app.state::<crate::Shell>();
        let mut zoom = crate::lock(&shell.zoom);
        *zoom = to(*zoom).clamp(ZOOM_RANGE.0, ZOOM_RANGE.1);
        window.set_zoom(*zoom)
    };
    let done = match event.id().as_ref() {
        "reload" => window.reload(),
        "actual-size" => zoom(|_| 1.0),
        "zoom-in" => zoom(|zoom| zoom * ZOOM_STEP),
        "zoom-out" => zoom(|zoom| zoom / ZOOM_STEP),
        CHECK => {
            crate::update::check(app, crate::update::By::Hand);
            Ok(())
        }
        "docs" => {
            crate::browse(DOCS);
            Ok(())
        }
        _ => Ok(()),
    };
    if let Err(why) = done {
        log::warn!("{}: {why}", event.id().as_ref());
    }
}

/// Takes Check for Updates… off while a look by hand runs, saying so, and puts it back after.
pub fn checking<R: Runtime>(app: &AppHandle<R>, on: bool) {
    let item = app.menu().and_then(|menu| {
        menu.items().ok()?.iter().find_map(|kind| {
            let item = kind.as_submenu()?.get(CHECK)?;
            item.as_menuitem().cloned()
        })
    });
    if let Some(item) = item {
        let label = if on { CHECKING_LABEL } else { CHECK_LABEL };
        if let Err(why) = item.set_enabled(!on).and_then(|()| item.set_text(label)) {
            log::warn!("{CHECK}: {why}");
        }
    }
}
