//! The menu bar: what a Mac app has, and nothing that takes a shortcut the page binds --
//! Cmd+K, Cmd+Shift+O and Cmd+. are its own. On Windows, no menu bar but the tray icon's menu.

#[cfg(target_os = "macos")]
use tauri::menu::{AboutMetadata, Submenu};
use tauri::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
#[cfg(windows)]
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Runtime};

/// Where the documentation is.
pub const DOCS: &str = "https://docs.humanfia.ai/humanize/";

/// Check for Updates…, and what it says while a look by hand runs.
const CHECK: &str = "check-for-updates";
const CHECK_LABEL: &str = "Check for Updates…";
const CHECKING_LABEL: &str = "Checking for Updates…";

/// Show humanize and Quit, in the tray icon's menu.
#[cfg(windows)]
const SHOW: &str = "show";
#[cfg(windows)]
const QUIT: &str = "quit";

/// How far each Zoom In or Zoom Out goes, and how far they may go in all.
const ZOOM_STEP: f64 = 1.1;
const ZOOM_RANGE: (f64, f64) = (0.5, 3.0);

/// The menu bar.
#[cfg(target_os = "macos")]
pub fn init<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    app.set_menu(build(app)?).map(drop)
}

/// The tray icon, whose menu stands for the menu bar, and which a click shows the window by.
#[cfg(windows)]
pub fn init<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let item = |id: &str, label: &str| MenuItem::with_id(app, id, label, true, None::<&str>);
    let menu = Menu::with_items(
        app,
        &[
            &item(SHOW, "Show Humanize Desktop")?,
            &check(app)?,
            &item("docs", "Documentation")?,
            &PredefinedMenuItem::separator(app)?,
            &item(QUIT, "Quit")?,
        ],
    )?;
    let mut tray = TrayIconBuilder::with_id(crate::MAIN)
        .tooltip("Humanize Desktop")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                crate::reveal(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    // Where Check for Updates… is found again.
    app.manage(menu);
    Ok(())
}

/// Check for Updates…, off in a development build, which is never updated.
fn check<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<MenuItem<R>> {
    let on = crate::update::checks(&app.package_info().version);
    MenuItem::with_id(app, CHECK, CHECK_LABEL, on, None::<&str>)
}

#[cfg(target_os = "macos")]
fn build<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<Menu<R>> {
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
                "Humanize Desktop",
                true,
                &[
                    &PredefinedMenuItem::about(app, Some("About Humanize Desktop"), Some(about))?,
                    &check(app)?,
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
        #[cfg(windows)]
        SHOW => {
            crate::reveal(app);
            Ok(())
        }
        #[cfg(windows)]
        QUIT => {
            app.exit(0);
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
    #[cfg(target_os = "macos")]
    let item = app.menu().and_then(|menu| {
        menu.items().ok()?.iter().find_map(|kind| {
            let item = kind.as_submenu()?.get(CHECK)?;
            item.as_menuitem().cloned()
        })
    });
    #[cfg(windows)]
    let item = app
        .try_state::<Menu<R>>()
        .and_then(|menu| menu.get(CHECK)?.as_menuitem().cloned());
    if let Some(item) = item {
        let label = if on { CHECKING_LABEL } else { CHECK_LABEL };
        if let Err(why) = item.set_enabled(!on).and_then(|()| item.set_text(label)) {
            log::warn!("{CHECK}: {why}");
        }
    }
}
