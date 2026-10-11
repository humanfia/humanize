//! humanize for macOS: one window on the page `hmz web` serves, started as the app's child.
//! The window opens on the app's own page at once -- a splash while `hmz web` starts, and what
//! to do where it cannot -- and goes on to `hmz web`'s once it says where it listens.

mod alert;
mod menu;
mod server;
mod shell_env;
mod update;

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, MutexGuard, OnceLock, PoisonError};
use std::thread;

use serde::Serialize;
use tauri::webview::{DownloadEvent, NewWindowResponse, PageLoadEvent};
use tauri::window::Color;
use tauri::{
    AppHandle, Manager, RunEvent, State, Theme, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
    WindowEvent,
};
use tauri_plugin_window_state::StateFlags;
use tokio::sync::watch;
use url::{Position, Url};

use server::{Failure, Server};

/// The one window's label.
const MAIN: &str = "main";

/// The app's own page, as the bundle serves it.
const OWN: &str = "tauri://localhost/";

/// The page's paper, `--paper` in hmz's style.css, light and dark: what the window is drawn in
/// before a page is, so it never flashes white.
const PAPER: (Color, Color) = (Color(0xf5, 0xed, 0xf0, 0xff), Color(0x1c, 0x1a, 0x21, 0xff));

/// Where `hmz web` stands, as the app's own page draws it.
#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(tag = "state", content = "detail", rename_all = "lowercase")]
enum Status {
    Starting,
    Running,
    Missing,
    Outdated,
    /// It exited before it said where it listens, saying this.
    Failed(String),
    /// It exited on its own once it had started, saying this.
    Stopped(String),
}

impl From<Failure> for Status {
    fn from(failure: Failure) -> Self {
        match failure {
            Failure::Missing => Status::Missing,
            Failure::Outdated => Status::Outdated,
            Failure::Failed(said) => Status::Failed(said),
        }
    }
}

/// What the app keeps while it runs.
struct Shell {
    status: watch::Sender<Status>,
    server: Mutex<Option<Arc<Server>>>,
    /// The login shell's environment, asked once a launch.
    env: OnceLock<shell_env::Env>,
    zoom: Mutex<f64>,
    /// Each download in flight, by its address, and where it goes: macOS does not say where
    /// once it is done, and two at once must not be given one name.
    downloads: Mutex<Vec<(String, PathBuf)>>,
}

/// Where `hmz web` stands, once it is anything but starting.
#[tauri::command]
async fn status(shell: State<'_, Shell>) -> Result<Status, ()> {
    let mut status = shell.status.subscribe();
    let settled = status.wait_for(|status| *status != Status::Starting).await;
    Ok(settled
        .map(|status| status.clone())
        .unwrap_or(Status::Starting))
}

/// Starts `hmz web` again, where it is not starting or running already.
#[tauri::command]
fn retry(app: AppHandle, shell: State<'_, Shell>) {
    let again = shell.status.send_if_modified(|status| {
        let again = !matches!(status, Status::Starting | Status::Running);
        if again {
            *status = Status::Starting;
        }
        again
    });
    if again {
        start(app);
    }
}

/// Starts `hmz web` in the background, and shows its page or why it did not start.
fn start(app: AppHandle) {
    thread::spawn(move || {
        let shell = app.state::<Shell>();
        let env = shell.env.get_or_init(shell_env::login);
        // Home, where a new epic is offered first.
        let home = shell_env::home(env);
        let port_file = app.path().app_data_dir().unwrap_or_default().join("port");
        match server::start(env, &home, &port_file) {
            Ok(server) => {
                let server = Arc::new(server);
                *lock(&shell.server) = Some(server.clone());
                shell.status.send_replace(Status::Running);
                show(&app, server.address.url().clone());
                // Told once `hmz web` stops on its own; nothing where the app stopped it.
                if let Some(said) = server.exited() {
                    lock(&shell.server).take();
                    shell.status.send_replace(Status::Stopped(said));
                    // Back to the app's own page from one that has gone with `hmz web`.
                    if let Some(own) = own(&app) {
                        show(&app, own);
                    }
                }
            }
            // The window is on the app's own page already: it opens on it, and only it retries.
            Err(failure) => {
                log::warn!("hmz web did not start: {failure:?}");
                shell.status.send_replace(failure.into());
            }
        }
    });
}

/// Opens a page in the window.
fn show(app: &AppHandle, url: Url) {
    if let Some(window) = app.get_webview_window(MAIN)
        && let Err(why) = window.navigate(url)
    {
        log::error!("the window could not open the page: {why}");
    }
}

/// The app's own page: bundled, or served by `tauri dev` while it is developed.
fn own(app: &AppHandle) -> Option<Url> {
    app.config()
        .build
        .dev_url
        .clone()
        .or_else(|| Url::parse(OWN).ok())
}

/// Whether the window may load a page: the app's own, or `hmz web`'s. Anything else opens in
/// the browser.
fn allowed(url: &Url, own: Option<&Url>, server: Option<&Url>) -> bool {
    // By scheme, host and port: `tauri:` is no scheme `url` gives an origin that can match.
    let at = |place: &Url| {
        place.scheme() == url.scheme()
            && place.host_str() == url.host_str()
            && place.port_or_known_default() == url.port_or_known_default()
    };
    own.is_some_and(at) || server.is_some_and(at)
}

/// Opens an address in the default browser, where a browser opens it.
fn browse(url: &str) {
    let opens =
        Url::parse(url).is_ok_and(|url| matches!(url.scheme(), "http" | "https" | "mailto"));
    if opens && let Err(why) = tauri_plugin_opener::open_url(url, None::<&str>) {
        log::warn!("the browser could not be opened: {why}");
    }
}

/// `name` in `dir`, or `name (1)`, `name (2)` and on where that is taken, or `going` to be --
/// numbered before what follows the first dot, as Safari does: `epic (1).tar.gz`.
fn unique(dir: &Path, name: &str, going: &[PathBuf]) -> PathBuf {
    let name = Path::new(name)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("download");
    let (stem, ext) = match name.find('.').filter(|&dot| dot > 0) {
        Some(dot) => name.split_at(dot),
        None => (name, ""),
    };
    let mut path = dir.join(name);
    let mut n = 1;
    while path.exists() || going.contains(&path) {
        path = dir.join(format!("{stem} ({n}){ext}"));
        n += 1;
    }
    path
}

/// The paper the window is drawn in, for the appearance it is in.
fn paper(theme: Theme) -> Color {
    if theme == Theme::Dark {
        PAPER.1
    } else {
        PAPER.0
    }
}

/// The one window, on the app's own page, drawn in the page's paper before anything is.
fn window(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    let guarded = app.clone();
    let downloads = app.clone();
    let window = WebviewWindowBuilder::new(app, MAIN, WebviewUrl::App("index.html".into()))
        .title("humanize")
        .inner_size(1280.0, 820.0)
        .min_inner_size(640.0, 480.0)
        .visible(false)
        .on_navigation(move |url| {
            let shell = guarded.state::<Shell>();
            let server = lock(&shell.server)
                .as_ref()
                .map(|server| server.address.url().clone());
            let allowed = allowed(url, own(&guarded).as_ref(), server.as_ref());
            if !allowed {
                browse(url.as_str());
            }
            allowed
        })
        .on_new_window(|url, _| {
            browse(url.as_str());
            NewWindowResponse::Deny
        })
        .on_document_title_changed(|window, title| {
            let _ = window.set_title(&title);
        })
        // Up to its path alone: the first address `hmz web`'s page is opened on carries its key.
        .on_page_load(|_, page| {
            if page.event() == PageLoadEvent::Finished {
                log::info!("the window shows {}", &page.url()[..Position::BeforePath]);
            }
        })
        .on_download(move |_, event| {
            let shell = downloads.state::<Shell>();
            match event {
                // Into ~/Downloads, under the name the page suggested.
                DownloadEvent::Requested { url, destination } => {
                    let suggested = destination
                        .file_name()
                        .and_then(|name| name.to_str())
                        .unwrap_or("download");
                    let mut going = lock(&shell.downloads);
                    if let Ok(dir) = downloads.path().download_dir() {
                        let taken: Vec<_> = going.iter().map(|(_, path)| path.clone()).collect();
                        *destination = unique(&dir, suggested, &taken);
                    }
                    going.push((url.to_string(), destination.clone()));
                    true
                }
                DownloadEvent::Finished { url, success, .. } => {
                    let saved = {
                        let mut going = lock(&shell.downloads);
                        let at = going.iter().position(|(going, _)| going == url.as_str());
                        at.map(|at| going.remove(at).1)
                    };
                    if let (true, Some(saved)) = (success, saved)
                        && let Err(why) = tauri_plugin_opener::reveal_item_in_dir(&saved)
                    {
                        log::warn!("the download could not be shown: {why}");
                    }
                    true
                }
                _ => true,
            }
        })
        .build()?;
    window.set_background_color(Some(paper(window.theme()?)))?;
    window.show()?;
    Ok(window)
}

/// Brings the window back: from the Dock, or from a second launch.
fn reveal(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// A lock, taken even where a thread panicked holding it: what it guards stays usable.
fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

pub fn run() {
    let app = tauri::Builder::default()
        // First: a second launch hands over to the first before anything else is set up.
        .plugin(tauri_plugin_single_instance::init(|app, _, _| reveal(app)))
        // To stdout and ~/Library/Logs/ai.humanfia.humanize.
        .plugin(
            tauri_plugin_log::Builder::new()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .plugin(
            // Not whether it is visible: closing it only hides it.
            tauri_plugin_window_state::Builder::new()
                .with_state_flags(StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED)
                .build(),
        )
        .manage(Shell {
            status: watch::Sender::new(Status::Starting),
            server: Mutex::default(),
            env: OnceLock::new(),
            zoom: Mutex::new(1.0),
            downloads: Mutex::default(),
        })
        .menu(menu::build)
        .on_menu_event(menu::handle)
        .invoke_handler(tauri::generate_handler![status, retry])
        .setup(|app| {
            window(app.handle())?;
            start(app.handle().clone());
            update::init(app.handle())?;
            Ok(())
        })
        .on_window_event(|window, event| match event {
            // Closing the window only hides it: the app stays in the Dock, `hmz web` with it.
            WindowEvent::CloseRequested { api, .. } => {
                api.prevent_close();
                let _ = window.hide();
            }
            WindowEvent::ThemeChanged(theme) => {
                let _ = window.set_background_color(Some(paper(*theme)));
            }
            _ => {}
        })
        .build(tauri::generate_context!());
    let app = match app {
        Ok(app) => app,
        Err(why) => {
            log::error!("humanize could not start: {why}");
            eprintln!("humanize could not start: {why}");
            std::process::exit(1);
        }
    };
    app.run(|app, event| match event {
        RunEvent::Reopen {
            has_visible_windows: false,
            ..
        } => reveal(app),
        RunEvent::Exit => {
            if let Some(server) = lock(&app.state::<Shell>().server).take() {
                server.stop();
            }
            update::on_exit(app);
        }
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn allows_its_own_page_and_the_servers_alone() {
        let own = Url::parse(OWN).ok();
        let server = Url::parse("http://127.0.0.1:8765/?key=secret").ok();
        let at = |url: &str| allowed(&Url::parse(url).unwrap(), own.as_ref(), server.as_ref());
        assert!(at("tauri://localhost/index.html"));
        assert!(at("http://127.0.0.1:8765/"));
        assert!(at("http://127.0.0.1:8765/#/epics/x"));
        assert!(!at("http://127.0.0.1:8766/"));
        assert!(!at("http://localhost:8765/"));
        assert!(!at("https://127.0.0.1:8765/"));
        assert!(!at("https://docs.humanfia.ai/humanize/"));
        assert!(!at("file:///etc/passwd"));
        assert!(!at("tauri://elsewhere/"));
        // Before `hmz web` listens, only the app's own page; while it is developed, the one
        // `tauri dev` serves.
        let first = Url::parse("http://127.0.0.1:8765/").unwrap();
        assert!(!allowed(&first, own.as_ref(), None));
        let dev = Url::parse("http://localhost:1430/").ok();
        let served = Url::parse("http://localhost:1430/index.html").unwrap();
        assert!(allowed(&served, dev.as_ref(), None));
    }

    #[test]
    fn numbers_a_download_whose_name_is_taken() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(
            unique(dir.path(), "epic.tar.gz", &[]),
            dir.path().join("epic.tar.gz")
        );
        std::fs::write(dir.path().join("epic.tar.gz"), "").unwrap();
        assert_eq!(
            unique(dir.path(), "epic.tar.gz", &[]),
            dir.path().join("epic (1).tar.gz")
        );
        std::fs::write(dir.path().join("epic (1).tar.gz"), "").unwrap();
        assert_eq!(
            unique(dir.path(), "epic.tar.gz", &[]),
            dir.path().join("epic (2).tar.gz")
        );
        std::fs::write(dir.path().join("README"), "").unwrap();
        assert_eq!(
            unique(dir.path(), "README", &[]),
            dir.path().join("README (1)")
        );
        std::fs::write(dir.path().join(".hidden"), "").unwrap();
        assert_eq!(
            unique(dir.path(), ".hidden", &[]),
            dir.path().join(".hidden (1)")
        );
        assert_eq!(
            unique(dir.path(), "../../escape.zip", &[]),
            dir.path().join("escape.zip")
        );
        // Nor one another download in flight is going to.
        let going = [dir.path().join("epic (2).tar.gz")];
        assert_eq!(
            unique(dir.path(), "epic.tar.gz", &going),
            dir.path().join("epic (3).tar.gz")
        );
    }

    #[test]
    fn says_its_status_as_the_page_reads_it() {
        let json = |status| serde_json::to_string(&status).unwrap();
        assert_eq!(json(Status::Missing), r#"{"state":"missing"}"#);
        assert_eq!(
            json(Status::Failed("no".into())),
            r#"{"state":"failed","detail":"no"}"#
        );
    }
}
