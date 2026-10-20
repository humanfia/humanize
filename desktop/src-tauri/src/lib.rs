//! humanize for macOS: one window on the page `hmz web` serves, started as the app's child.
//! The window opens on the app's own page at once -- a splash while `hmz` is installed and
//! `hmz web` starts, and what went wrong where it cannot -- and goes on to `hmz web`'s once it
//! says where it listens. A `.hmzepic` opened with the app, or dropped on its window, is
//! imported by that page, which opens the epic's Exomyth.

mod alert;
mod child;
mod chrome;
mod install;
mod menu;
mod notify;
mod server;
mod shell_env;
mod update;

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, MutexGuard, OnceLock, PoisonError};
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::webview::{DownloadEvent, NewWindowResponse, PageLoadEvent};
use tauri::window::Color;
use tauri::{
    AppHandle, DragDropEvent, Manager, RunEvent, State, Theme, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_window_state::StateFlags;
use tokio::sync::watch;
use url::{Position, Url};

use install::{Chosen, How};
use server::{Failure, Server};

/// The one window's label.
const MAIN: &str = "main";

/// The app's own page, as the bundle serves it.
const OWN: &str = "tauri://localhost/";

/// The page's paper, `--paper` in hmz's style.css, light and dark: what the window is drawn in
/// before a page is, so it never flashes white.
const PAPER: (Color, Color) = (Color(0xf4, 0xf8, 0xf9, 0xff), Color(0x0f, 0x14, 0x18, 0xff));

/// What an epic's archive is named with.
const EPIC: &str = "hmzepic";

/// How often an update waiting for epics to end looks whether they have.
const WAITING: Duration = Duration::from_secs(2);

/// Where `hmz web` stands, as the app's own page draws it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "state", content = "detail", rename_all = "kebab-case")]
enum Status {
    Starting,
    Installing(install::Progress),
    /// An `hmz` of this version, too old to serve the app, holds running epics: it is updated
    /// once they end.
    Waiting(String),
    InstallFailed(install::Failed),
    Running,
    /// No `hmz`, where nothing installs one.
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
    /// `hmz web`'s page, key and all, once the window is sent to it. Set and read on the main
    /// thread, where a file is opened, so that one opened as it is set is never missed.
    page: Mutex<Option<Url>>,
    /// An epic's archive opened before then, imported once it is set.
    opening: Mutex<Option<PathBuf>>,
    /// The address of a notification clicked before then, opened once it is set.
    notified: Mutex<Option<String>>,
}

/// Where `hmz web` stands, once it is anything but starting, and other than the page drew last.
#[tauri::command]
async fn status(after: Option<Status>, shell: State<'_, Shell>) -> Result<Status, ()> {
    let mut status = shell.status.subscribe();
    let settled = status
        .wait_for(|status| *status != Status::Starting && Some(status) != after.as_ref())
        .await;
    Ok(settled
        .map(|status| status.clone())
        .unwrap_or(Status::Starting))
}

/// Posts a notification from `hmz web`'s page; clicking it brings the window forward, on the
/// page's hash `address` where it is one.
#[tauri::command]
fn notify(title: String, body: String, address: Option<String>) {
    notify::post(&title, &body, address.as_deref().unwrap_or_default());
}

/// Starts again where it stopped short: installing `hmz`, then `hmz web`.
#[tauri::command]
fn retry(app: AppHandle, shell: State<'_, Shell>) {
    again(app, &shell, How::Usual, |status| {
        matches!(
            status,
            Status::InstallFailed(_)
                | Status::Missing
                | Status::Outdated
                | Status::Failed(_)
                | Status::Stopped(_)
        )
    });
}

/// Starts `hmz web` with the `hmz` there, where installing the app's own failed.
#[tauri::command]
fn keep(app: AppHandle, shell: State<'_, Shell>) {
    again(
        app,
        &shell,
        How::Keep,
        |status| matches!(status, Status::InstallFailed(failed) if failed.keep),
    );
}

/// Updates `hmz` without waiting for the epics it holds to end: told to the thread waiting.
#[tauri::command]
fn update_now(shell: State<'_, Shell>) {
    shell.status.send_if_modified(|status| {
        let waiting = matches!(status, Status::Waiting(_));
        if waiting {
            *status = Status::Starting;
        }
        waiting
    });
}

/// Starts as asked, where what it stands at is one it may start from.
fn again(app: AppHandle, shell: &Shell, how: How, from: impl Fn(&Status) -> bool) {
    let again = shell.status.send_if_modified(|status| {
        let again = from(status);
        if again {
            *status = Status::Starting;
        }
        again
    });
    if again {
        start(app, how);
    }
}

/// Installs `hmz` where it must, starts `hmz web` in the background, and shows its page or
/// why it did not start.
fn start(app: AppHandle, how: How) {
    thread::spawn(move || {
        let shell = app.state::<Shell>();
        let env = shell.env.get_or_init(shell_env::login);
        // Home, where a new epic is offered first.
        let home = shell_env::home(env);
        let data = app.path().app_data_dir().unwrap_or_default();
        let version = app.package_info().version.to_string();
        let tell = |progress| {
            shell.status.send_replace(Status::Installing(progress));
        };
        let mut how = how;
        let started = loop {
            let (hmz, held) = match install::choose(env, &data, &version, how, &tell) {
                Ok(Chosen::Ready(hmz)) => (hmz, None),
                Ok(Chosen::Held(hmz, version)) => (hmz, Some(version)),
                Ok(Chosen::Missing) => break Err(Status::Missing),
                Err(failed) => break Err(Status::InstallFailed(failed)),
            };
            match (server::start(env, &hmz, &home, &data.join("port")), held) {
                // Too old to serve the app, and holding running epics: updated once they end,
                // or once Update is pressed.
                (Err(Failure::Outdated), Some(version)) => {
                    log::info!("hmz {version} cannot serve the app; waiting for its epics");
                    let waiting = Status::Waiting(version);
                    shell.status.send_replace(waiting.clone());
                    while *shell.status.borrow() == waiting && install::busy(env) {
                        thread::sleep(WAITING);
                    }
                    shell.status.send_replace(Status::Starting);
                    how = How::Now;
                }
                (started, _) => break started.map_err(Status::from),
            }
        };
        match started {
            Ok(server) => {
                let server = Arc::new(server);
                *lock(&shell.server) = Some(server.clone());
                shell.status.send_replace(Status::Running);
                let page = server.address.url().clone();
                on_main(&app, move |app, shell| {
                    *lock(&shell.page) = Some(page.clone());
                    let opening = lock(&shell.opening).take();
                    let opening = opening.and_then(|path| importing(&page, &path));
                    let notified = lock(&shell.notified).take();
                    let notified = notified.and_then(|address| notify::target(&page, &address));
                    show(app, opening.or(notified).unwrap_or(page));
                });
                // Told once `hmz web` stops on its own; nothing where the app stopped it.
                if let Some(said) = server.exited() {
                    lock(&shell.server).take();
                    shell.status.send_replace(Status::Stopped(said));
                    // Back to the app's own page from one that has gone with `hmz web`.
                    on_main(&app, |app, shell| {
                        lock(&shell.page).take();
                        if let Some(own) = own(app) {
                            show(app, own);
                        }
                    });
                }
            }
            // The window is on the app's own page already: it opens on it, and only it retries.
            Err(status) => {
                log::warn!("hmz web did not start: {status:?}");
                shell.status.send_replace(status);
            }
        }
    });
}

/// Runs on the main thread, after whatever this thread sent there before.
fn on_main(app: &AppHandle, run: impl FnOnce(&AppHandle, &Shell) + Send + 'static) {
    let on = app.clone();
    if let Err(why) = app.run_on_main_thread(move || run(&on, &on.state::<Shell>())) {
        log::error!("the window could not be told: {why}");
    }
}

/// Opens a page in the window.
fn show(app: &AppHandle, url: Url) {
    if let Some(window) = app.get_webview_window(MAIN)
        && let Err(why) = window.navigate(url)
    {
        log::error!("the window could not open the page: {why}");
    }
}

/// Of files opened or dropped at once, the last that is an epic's archive: the page imports
/// one at a time.
fn epic(paths: impl IntoIterator<Item = PathBuf>) -> Option<PathBuf> {
    paths
        .into_iter()
        .filter(|path| {
            path.extension()
                .and_then(|ext| ext.to_str())
                .is_some_and(|ext| ext.eq_ignore_ascii_case(EPIC))
        })
        .last()
}

/// The address on `hmz web`'s page that imports an epic's archive by its path and opens its
/// Exomyth: from the address with the key, which signs in again and keeps the hash, so that it
/// is a new load even where the same file was opened last.
fn importing(page: &Url, path: &Path) -> Option<Url> {
    let path: String = url::form_urlencoded::byte_serialize(path.to_str()?.as_bytes()).collect();
    let mut url = page.clone();
    url.set_fragment(Some(&format!("/epics/import?path={path}")));
    Some(url)
}

/// Imports an epic's archive in `hmz web`'s page, or once the window is on it, and brings the
/// window forward. On the main thread, where a file is opened or dropped.
fn open(app: &AppHandle, path: PathBuf) {
    let shell = app.state::<Shell>();
    let page = lock(&shell.page).clone();
    match page.and_then(|page| importing(&page, &path)) {
        Some(url) => show(app, url),
        None => *lock(&shell.opening) = Some(path),
    }
    reveal(app);
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
/// numbered before the extension: `20260930T053725.504Z-a3d685 (1).hmzepic`, the dot inside
/// an epic's name being part of the name.
fn unique(dir: &Path, name: &str, going: &[PathBuf]) -> PathBuf {
    let name = Path::new(name)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("download");
    let (stem, ext) = match name.rfind('.').filter(|&dot| dot > 0) {
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
    let version = app.package_info().version.to_string();
    let window = WebviewWindowBuilder::new(app, MAIN, WebviewUrl::App("index.html".into()));
    let window = chrome::dress(window, &version)
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
        .on_page_load(|window, page| {
            if page.event() == PageLoadEvent::Finished {
                log::info!("the window shows {}", &page.url()[..Position::BeforePath]);
                chrome::tell(&window);
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
            // Not whether it is visible: closing it only hides it. Nor the update's window,
            // centred anew each time.
            tauri_plugin_window_state::Builder::new()
                .with_state_flags(StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED)
                .with_denylist(&[update::WINDOW])
                .build(),
        )
        .manage(Shell {
            status: watch::Sender::new(Status::Starting),
            server: Mutex::default(),
            env: OnceLock::new(),
            zoom: Mutex::new(1.0),
            downloads: Mutex::default(),
            page: Mutex::default(),
            opening: Mutex::default(),
            notified: Mutex::default(),
        })
        .menu(menu::build)
        .on_menu_event(menu::handle)
        .invoke_handler(tauri::generate_handler![
            status, retry, keep, update_now, notify
        ])
        .setup(|app| {
            window(app.handle())?;
            notify::init(app.handle());
            start(app.handle().clone(), How::Usual);
            update::init(app.handle())?;
            Ok(())
        })
        .on_window_event(|window, event| match event {
            // Closing the window only hides it: the app stays in the Dock, `hmz web` with it.
            // The update's window is the updater's own.
            _ if window.label() != MAIN => {}
            WindowEvent::CloseRequested { api, .. } => {
                api.prevent_close();
                let _ = window.hide();
            }
            WindowEvent::ThemeChanged(theme) => {
                let _ = window.set_background_color(Some(paper(*theme)));
            }
            WindowEvent::Resized(_) => chrome::resized(window),
            WindowEvent::DragDrop(DragDropEvent::Drop { paths, .. }) => {
                if let Some(path) = epic(paths.iter().cloned()) {
                    open(window.app_handle(), path);
                }
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
        // Whether or not the update's window shows.
        RunEvent::Reopen { .. } => reveal(app),
        // Double-clicked in the Finder, or Open With: at launch too, before `hmz web` listens.
        RunEvent::Opened { urls } => {
            if let Some(path) = epic(urls.iter().filter_map(|url| url.to_file_path().ok())) {
                open(app, path);
            }
        }
        RunEvent::Exit => {
            if let Some(server) = lock(&app.state::<Shell>().server).take() {
                server.stop();
            }
            // Whatever starting had got to: an install, a version asked, `hmz web` starting.
            child::quit();
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
    fn imports_the_last_epic_of_those_opened_and_nothing_else() {
        let paths = |all: &[&str]| all.iter().map(PathBuf::from).collect::<Vec<_>>();
        assert_eq!(
            epic(paths(&[
                "/a/one.hmzepic",
                "/a/notes.txt",
                "/a/two.HmzEpic",
                "/a/x.zip"
            ])),
            Some(PathBuf::from("/a/two.HmzEpic"))
        );
        assert_eq!(
            epic(paths(&["/a/notes.txt", "/a/hmzepic", "/a/x.hmzepic.gz"])),
            None
        );
        assert_eq!(epic(paths(&[])), None);
        // As the Finder hands them over.
        let url = Url::parse("file:///Users/me/My%20Epics/1T2.3Z-a.hmzepic").unwrap();
        assert_eq!(
            epic(url.to_file_path()),
            Some(PathBuf::from("/Users/me/My Epics/1T2.3Z-a.hmzepic"))
        );
    }

    #[test]
    fn imports_by_its_path_on_the_page_it_is_given() {
        let path = Path::new("/Users/me/My Epics/a&b=c#d+e%.hmzepic");
        // At the address with the key, which signs in and keeps the hash.
        let first = Url::parse("http://127.0.0.1:8765/?key=secret").unwrap();
        let url = importing(&first, path).unwrap();
        assert_eq!(
            url.as_str(),
            "http://127.0.0.1:8765/?key=secret#/epics/import?path=%2FUsers%2Fme%2FMy+Epics%2Fa%26b%3Dc%23d%2Be%25.hmzepic"
        );
        // Read back as the page reads its hash.
        let hash = Url::parse(&format!("http://page{}", url.fragment().unwrap())).unwrap();
        let read: Vec<_> = hash.query_pairs().collect();
        assert_eq!(read, [("path".into(), path.to_str().unwrap().into())]);
        assert!(allowed(&url, None, Some(&first)));
    }

    #[test]
    fn numbers_a_download_whose_name_is_taken() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(
            unique(dir.path(), "epic.hmzepic", &[]),
            dir.path().join("epic.hmzepic")
        );
        std::fs::write(dir.path().join("epic.hmzepic"), "").unwrap();
        assert_eq!(
            unique(dir.path(), "epic.hmzepic", &[]),
            dir.path().join("epic (1).hmzepic")
        );
        std::fs::write(dir.path().join("epic (1).hmzepic"), "").unwrap();
        assert_eq!(
            unique(dir.path(), "epic.hmzepic", &[]),
            dir.path().join("epic (2).hmzepic")
        );
        std::fs::write(dir.path().join("1T2.3Z-a.hmzepic"), "").unwrap();
        assert_eq!(
            unique(dir.path(), "1T2.3Z-a.hmzepic", &[]),
            dir.path().join("1T2.3Z-a (1).hmzepic")
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
        let going = [dir.path().join("epic (2).hmzepic")];
        assert_eq!(
            unique(dir.path(), "epic.hmzepic", &going),
            dir.path().join("epic (3).hmzepic")
        );
    }

    #[test]
    fn says_its_status_as_the_page_reads_it() {
        let json = |status| serde_json::to_string(&status).unwrap();
        assert_eq!(json(Status::Missing), r#"{"state":"missing"}"#);
        let failed = Status::InstallFailed(install::Failed {
            updating: true,
            said: "offline".into(),
            keep: false,
        });
        assert_eq!(
            json(failed.clone()),
            r#"{"state":"install-failed","detail":{"updating":true,"said":"offline","keep":false}}"#
        );
        // As the page hands back what it drew last.
        assert_eq!(
            serde_json::from_str::<Status>(&json(failed.clone())).unwrap(),
            failed
        );
        assert_eq!(
            json(Status::Failed("no".into())),
            r#"{"state":"failed","detail":"no"}"#
        );
    }
}
