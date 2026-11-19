//! Humanize Desktop, for macOS and Windows (Section 3 of [DESKTOP]): one window on the page the
//! app carries -- the files of `src/hmz/web/static`, built into it -- and the pipes that page
//! reaches every daemon through. No server runs: the app serves the page itself.
//! The window opens on the splash at once, and goes on to the page -- on Windows once hmz is
//! installed in WSL, the splash saying how that goes, and what went wrong where it cannot be. A
//! `.hmzepic` opened with the app, or dropped on its window, is imported by the page, which reads
//! it with `file_read`.

mod alert;
mod child;
mod chrome;
mod hmz;
#[cfg(windows)]
mod install;
mod menu;
mod notify;
mod pipes;
mod shell_env;
mod update;
#[cfg(windows)]
mod wsl;

use std::borrow::Cow;
use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard, OnceLock, PoisonError};
#[cfg(windows)]
use std::thread;
#[cfg(windows)]
use std::time::Duration;

use base64::Engine;
use base64::engine::general_purpose::STANDARD as BASE64;
use serde::{Deserialize, Serialize};
use tauri::http::header::{ACCESS_CONTROL_ALLOW_ORIGIN, HeaderValue, ORIGIN};
use tauri::http::{Request, Response};
use tauri::webview::{DownloadEvent, NewWindowResponse, PageLoadEvent};
use tauri::window::Color;
use tauri::{
    AppHandle, DragDropEvent, Manager, RunEvent, Runtime, State, Theme, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_window_state::StateFlags;
use tokio::sync::watch;
use url::{Position, Url};

#[cfg(windows)]
use install::{Chosen, How};

/// The one window's label.
const MAIN: &str = "main";

/// The page the app carries, as the app serves it.
#[cfg(target_os = "macos")]
const OWN: &str = "tauri://localhost/";
#[cfg(windows)]
const OWN: &str = "http://tauri.localhost/";

/// The splash, beside the page: `desktop/ui/app` built in with it.
const SPLASH: &str = "app/index.html";

/// The page's paper, `--paper` in hmz's style.css, light and dark: what the window is drawn in
/// before a page is, so it never flashes white.
const PAPER: (Color, Color) = (Color(0xf4, 0xf8, 0xf9, 0xff), Color(0x0f, 0x14, 0x18, 0xff));

/// What an epic's archive is named with.
const EPIC: &str = "hmzepic";

/// The most `file_read` reads at once (Section 3.12.7 of [DESKTOP]).
const READING: u64 = 1 << 20;

/// How often an update waiting for epics to end looks whether they have.
#[cfg(windows)]
const WAITING: Duration = Duration::from_secs(2);

/// Where starting stands, as the splash draws it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "state", content = "detail", rename_all = "kebab-case")]
enum Status {
    Starting,
    #[cfg(windows)]
    Installing(install::Progress),
    /// An `hmz` of this version, too old to serve the app, holds running epics: it is updated
    /// once they end.
    #[cfg(windows)]
    Waiting(String),
    #[cfg(windows)]
    InstallFailed(install::Failed),
    /// No `hmz` in WSL, where nothing installs one.
    #[cfg(windows)]
    Missing,
    /// The page is shown.
    Running,
}

/// What the app keeps while it runs.
struct Shell {
    status: watch::Sender<Status>,
    /// The login shell's environment, asked once a launch.
    env: OnceLock<shell_env::Env>,
    /// The `hmz` in WSL Local runs, once it is chosen.
    #[cfg(windows)]
    hmz: Mutex<Option<String>>,
    zoom: Mutex<f64>,
    /// Each download in flight, by its address, and where it goes: macOS does not say where
    /// once it is done, and two at once must not be given one name.
    downloads: Mutex<Vec<(String, PathBuf)>>,
    /// The page, once the window is sent to it. Set and read on the main thread, where a file
    /// is opened, so that one opened as it is set is never missed.
    page: Mutex<Option<Url>>,
    /// An epic's archive opened before then, imported once it is set.
    opening: Mutex<Option<PathBuf>>,
    /// The address of a notification clicked before then, opened once it is set.
    notified: Mutex<Option<String>>,
    /// Every epic's archive opened with the app or dropped on it: what `file_read` reads.
    opened: Mutex<Vec<PathBuf>>,
}

/// Where starting stands, once it is anything but starting, and other than the splash drew last.
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

/// Posts a notification from the page; clicking it brings the window forward, on the page's
/// hash `address` where it is one.
#[tauri::command]
fn notify(title: String, body: String, address: Option<String>) {
    notify::post(&title, &body, address.as_deref().unwrap_or_default());
}

/// Bytes of an epic's archive opened with the app, in base64, and whether they are its last.
#[derive(Debug, PartialEq, Serialize)]
struct Chunk {
    data: String,
    eof: bool,
}

/// Reads up to `length` bytes, at most [`READING`], from `offset` of an epic's archive opened
/// with the app, and nothing else (Section 3.12.7 of [DESKTOP]).
#[tauri::command]
async fn file_read(
    path: String,
    offset: u64,
    length: u64,
    shell: State<'_, Shell>,
) -> Result<Chunk, String> {
    let path = PathBuf::from(path);
    if !lock(&shell.opened).contains(&path) {
        return Err(format!("{} was not opened with the app.", path.display()));
    }
    // Off the runtime the pipes are carried on.
    let reading = path.clone();
    tokio::task::spawn_blocking(move || read(&reading, offset, length))
        .await
        .map_err(|why| why.to_string())?
        .map_err(|why| format!("{} could not be read: {why}", path.display()))
}

fn read(path: &Path, offset: u64, length: u64) -> io::Result<Chunk> {
    let mut file = File::open(path)?;
    let size = file.metadata()?.len();
    file.seek(SeekFrom::Start(offset.min(size)))?;
    let mut data = Vec::new();
    file.take(length.min(READING)).read_to_end(&mut data)?;
    Ok(Chunk {
        eof: offset.saturating_add(data.len() as u64) >= size,
        data: BASE64.encode(&data),
    })
}

/// Starts again where installing stopped short.
#[cfg(windows)]
#[tauri::command]
fn retry(app: AppHandle, shell: State<'_, Shell>) {
    again(app, &shell, How::Usual, |status| {
        matches!(status, Status::InstallFailed(_) | Status::Missing)
    });
}

/// Shows the page with the `hmz` there, where installing the app's own failed.
#[cfg(windows)]
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
#[cfg(windows)]
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
#[cfg(windows)]
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

/// On macOS, shows the page at once: it reaches Local over `stdio:local`, and says so where no
/// `hmz` is found (Section 3.5.5 of [DESKTOP]).
#[cfg(not(windows))]
fn start(app: &AppHandle) {
    shown(app);
}

/// On Windows, installs the app's `hmz` in WSL where it must, in the background, then shows the
/// page, or on the splash why it cannot (Section 3.4 and Section 3.5.6 of [DESKTOP]).
#[cfg(windows)]
fn start(app: AppHandle, how: How) {
    thread::spawn(move || {
        let shell = app.state::<Shell>();
        let env = shell.env.get_or_init(shell_env::login);
        let version = app.package_info().version.to_string();
        let tell = |progress| {
            shell.status.send_replace(Status::Installing(progress));
        };
        let mut how = how;
        let chosen = loop {
            match install::choose(env, &version, how, &tell) {
                // Too old to serve the app, and holding running epics: updated once they end,
                // or once Update now is pressed.
                Ok(Chosen::Held(hmz, held)) if !install::serves(&hmz, env) => {
                    log::info!("hmz {held} cannot serve the app; waiting for its epics");
                    let waiting = Status::Waiting(held);
                    shell.status.send_replace(waiting.clone());
                    loop {
                        let still = *shell.status.borrow() == waiting;
                        if !still || !install::busy(env) {
                            break;
                        }
                        thread::sleep(WAITING);
                    }
                    shell.status.send_replace(Status::Starting);
                    how = How::Now;
                }
                // Of another version that serves the app, while its epics run: replaced on a
                // later launch.
                Ok(Chosen::Ready(hmz) | Chosen::Held(hmz, _)) => break Ok(hmz),
                Ok(Chosen::Missing) => break Err(Status::Missing),
                Err(failed) => break Err(Status::InstallFailed(failed)),
            }
        };
        match chosen {
            Ok(hmz) => {
                *lock(&shell.hmz) = Some(hmz.to_string_lossy().into_owned());
                shown(&app);
            }
            // The window is on the splash already: it opens on it, and only it retries.
            Err(status) => {
                log::warn!("hmz is not ready in WSL: {status:?}");
                shell.status.send_replace(status);
            }
        }
    });
}

/// Takes the window from the splash to the page: on the epic's archive opened before then, or
/// the notification clicked, where there is one.
fn shown(app: &AppHandle) {
    app.state::<Shell>().status.send_replace(Status::Running);
    on_main(app, |app, shell| {
        let Some(page) = own(app) else { return };
        *lock(&shell.page) = Some(page.clone());
        let opening = lock(&shell.opening).take();
        let opening = opening.and_then(|path| importing(&page, &path));
        let notified = lock(&shell.notified).take();
        let notified = notified.and_then(|address| notify::target(&page, &address));
        show(app, opening.or(notified).unwrap_or(page));
    });
}

/// Runs on the main thread, after whatever this thread sent there before.
fn on_main(app: &AppHandle, run: impl FnOnce(&AppHandle, &Shell) + Send + 'static) {
    let on = app.clone();
    if let Err(why) = app.run_on_main_thread(move || run(&on, &on.state::<Shell>())) {
        log::error!("the window could not be told: {why}");
    }
}

/// Opens an address in the window: where it is on it already -- the same epic's archive opened
/// again -- the page is told its hash changed, so that it goes there again.
fn show(app: &AppHandle, url: Url) {
    let Some(window) = app.get_webview_window(MAIN) else {
        return;
    };
    let shown = if window.url().is_ok_and(|at| at == url) {
        window.eval("dispatchEvent(new HashChangeEvent('hashchange'))")
    } else {
        window.navigate(url)
    };
    if let Err(why) = shown {
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

/// The page's import address (Section 3.6.8 of [WEB]), naming an epic's archive by its path, on
/// the daemon the address the page is at names: Local where it names none.
fn importing(page: &Url, path: &Path) -> Option<Url> {
    let path: String = url::form_urlencoded::byte_serialize(path.to_str()?.as_bytes()).collect();
    let at = page.fragment().unwrap_or_default();
    let at = at.strip_prefix('/').unwrap_or(at);
    let daemon = match at.starts_with('@') {
        true => format!("/{}", at.split(['/', '?']).next().unwrap_or_default()),
        false => String::new(),
    };
    let mut url = page.clone();
    url.set_fragment(Some(&format!("{daemon}/epics/import?path={path}")));
    Some(url)
}

/// The page at the address the window is on, where the window is on the app's own.
fn at(app: &AppHandle, mut page: Url) -> Url {
    let at = app
        .get_webview_window(MAIN)
        .and_then(|window| window.url().ok());
    if let Some(at) = at.filter(|at| allowed(at, Some(&page))) {
        page.set_fragment(at.fragment());
    }
    page
}

/// Imports an epic's archive in the page, or once the window is on it, and brings the window
/// forward. On the main thread, where a file is opened or dropped.
fn open(app: &AppHandle, path: PathBuf) {
    let shell = app.state::<Shell>();
    {
        let mut opened = lock(&shell.opened);
        if !opened.contains(&path) {
            opened.push(path.clone());
        }
    }
    let page = lock(&shell.page).clone();
    match page.and_then(|page| importing(&at(app, page), &path)) {
        Some(url) => show(app, url),
        None => *lock(&shell.opening) = Some(path),
    }
    reveal(app);
}

/// Of a launch's arguments, after its own path, the epic's archive Windows opens it with:
/// where it is from where it was launched.
fn argued<A: Into<PathBuf>>(args: impl IntoIterator<Item = A>, from: &Path) -> Option<PathBuf> {
    epic(args.into_iter().skip(1).map(|arg| from.join(arg.into())))
}

/// A launch, the first or a second one handed over: the epic's archive it was opened with is
/// imported, and the window brought forward.
fn launched(app: &AppHandle, epic: Option<PathBuf>) {
    match epic {
        Some(path) => open(app, path),
        None => reveal(app),
    }
}

/// The page the app carries: bundled, or served by `tauri dev` where it is told to.
fn own(app: &AppHandle) -> Option<Url> {
    app.config()
        .build
        .dev_url
        .clone()
        .or_else(|| Url::parse(OWN).ok())
}

/// Whether the window may load an address: the splash and the page the app carries, alone.
/// Anything else opens in the browser.
fn allowed(url: &Url, own: Option<&Url>) -> bool {
    // By scheme, host and port: `tauri:` is no scheme `url` gives an origin that can match.
    own.is_some_and(|place| {
        place.scheme() == url.scheme()
            && place.host_str() == url.host_str()
            && place.port_or_known_default() == url.port_or_known_default()
    })
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

/// Lets a face import the page's files under `vendor/` (Section 4.5.9 of [WEB]): its frame is
/// sandboxed, so it asks with `Origin: null`, which the origin the web view stamps on every
/// answer would refuse.
fn share(request: &Request<Vec<u8>>, response: &mut Response<Cow<'static, [u8]>>) {
    let null = request.headers().get(ORIGIN).is_some_and(|by| by == "null");
    if null && request.uri().path().starts_with("/vendor/") {
        let headers = response.headers_mut();
        headers.insert(
            ACCESS_CONTROL_ALLOW_ORIGIN,
            HeaderValue::from_static("null"),
        );
    }
}

/// The one window, on the splash, drawn in the page's paper before anything is.
fn window(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    let guarded = app.clone();
    let downloads = app.clone();
    let version = app.package_info().version.to_string();
    let window = WebviewWindowBuilder::new(app, MAIN, WebviewUrl::App(SPLASH.into()));
    let window = chrome::dress(window, &version)
        .title("Humanize Desktop")
        .inner_size(1280.0, 820.0)
        .min_inner_size(640.0, 480.0)
        .visible(false)
        .on_navigation(move |url| {
            let allowed = allowed(url, own(&guarded).as_ref());
            if !allowed {
                browse(url.as_str());
            }
            allowed
        })
        .on_new_window(|url, _| {
            browse(url.as_str());
            NewWindowResponse::Deny
        })
        .on_web_resource_request(|request, response| share(&request, response))
        .on_document_title_changed(|window, title| {
            let _ = window.set_title(&title);
        })
        .on_page_load(|window, page| match page.event() {
            // A page gone or loaded again takes its pipes with it.
            PageLoadEvent::Started => pipes::close_all(),
            PageLoadEvent::Finished => {
                log::info!("the window shows {}", &page.url()[..Position::AfterPath]);
                chrome::tell(&window);
            }
        })
        .on_download(move |_, event| {
            let shell = downloads.state::<Shell>();
            match event {
                // Into the Downloads folder, under the name the page suggested.
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

/// Brings the window back: from the Dock or the tray, or from a second launch.
fn reveal<R: Runtime>(app: &AppHandle<R>) {
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
        .plugin(tauri_plugin_single_instance::init(|app, args, cwd| {
            launched(app, argued(args, Path::new(&cwd)))
        }))
        // To stdout and ~/Library/Logs/ai.humanfia.humanize, or on Windows
        // %LOCALAPPDATA%\ai.humanfia.humanize\logs.
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
            env: OnceLock::new(),
            #[cfg(windows)]
            hmz: Mutex::default(),
            zoom: Mutex::new(1.0),
            downloads: Mutex::default(),
            page: Mutex::default(),
            opening: Mutex::default(),
            notified: Mutex::default(),
            opened: Mutex::default(),
        })
        .on_menu_event(menu::handle)
        // Each granted to the window by capabilities/default.json, which build.rs lists.
        .invoke_handler(tauri::generate_handler![
            status,
            #[cfg(windows)]
            retry,
            #[cfg(windows)]
            keep,
            #[cfg(windows)]
            update_now,
            notify,
            file_read,
            pipes::pipe_open,
            pipes::pipe_send,
            pipes::pipe_close,
            pipes::easytier_list,
            pipes::easytier_set,
            pipes::easytier_remove
        ])
        .setup(|app| {
            menu::init(app.handle())?;
            window(app.handle())?;
            let here = std::env::current_dir().unwrap_or_default();
            launched(app.handle(), argued(std::env::args_os(), &here));
            notify::init(app.handle());
            #[cfg(not(windows))]
            start(app.handle());
            #[cfg(windows)]
            start(app.handle().clone(), How::Usual);
            update::init(app.handle())?;
            Ok(())
        })
        .on_window_event(|window, event| match event {
            // Closing the window only hides it: the app stays in the Dock or the tray, its
            // pipes with it.
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
            log::error!("Humanize Desktop could not start: {why}");
            eprintln!("Humanize Desktop could not start: {why}");
            std::process::exit(1);
        }
    };
    app.run(|app, event| match event {
        // Whether or not the update's window shows.
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => reveal(app),
        // Double-clicked in the Finder, or Open With: at launch too, before the page is shown.
        #[cfg(target_os = "macos")]
        RunEvent::Opened { urls } => {
            if let Some(path) = epic(urls.iter().filter_map(|url| url.to_file_path().ok())) {
                open(app, path);
            }
        }
        RunEvent::Exit => {
            // Every pipe's processes, and whatever starting had got to: an install, a version
            // asked.
            pipes::close_all();
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
    fn shares_the_vendor_files_with_a_face_alone() {
        // What the web view answers every file with: the window's own origin.
        let own = OWN.trim_end_matches('/');
        let allow = |path: &str, origin: Option<&str>| {
            let mut request = Request::builder().uri(format!("{OWN}{path}"));
            if let Some(origin) = origin {
                request = request.header(ORIGIN, origin);
            }
            let mut response = Response::builder()
                .header(ACCESS_CONTROL_ALLOW_ORIGIN, own)
                .body(Cow::Borrowed(&[][..]))
                .unwrap();
            share(&request.body(Vec::new()).unwrap(), &mut response);
            let allow = &response.headers()[ACCESS_CONTROL_ALLOW_ORIGIN];
            allow.to_str().unwrap().to_owned()
        };
        assert_eq!(allow("vendor/markdown.js", Some("null")), "null");
        assert_eq!(allow("vendor/vega.js?v=1", Some("null")), "null");
        assert_eq!(allow("vendor/markdown.js", Some(own)), own);
        assert_eq!(allow("vendor/markdown.js", None), own);
        assert_eq!(allow("app.js", Some("null")), own);
        assert_eq!(allow("faces/vendor/x.js", Some("null")), own);
    }

    #[test]
    fn allows_the_page_it_carries_alone() {
        let own = Url::parse(OWN).ok();
        let at = |url: &str| allowed(&Url::parse(url).unwrap(), own.as_ref());
        #[cfg(target_os = "macos")]
        {
            assert!(at("tauri://localhost/index.html"));
            assert!(at("tauri://localhost/app/index.html"));
            assert!(at("tauri://localhost/#/epics/x"));
        }
        #[cfg(windows)]
        {
            assert!(at("http://tauri.localhost/index.html"));
            assert!(at("http://tauri.localhost/#/epics/x"));
            assert!(!at("https://tauri.localhost/index.html"));
            assert!(!at("tauri://localhost/index.html"));
        }
        assert!(!at("http://127.0.0.1:8765/"));
        assert!(!at("http://localhost/"));
        assert!(!at("https://humanfia.ai/humanize/"));
        assert!(!at("file:///etc/passwd"));
        assert!(!at("tauri://elsewhere/"));
        // While it is developed, the one `tauri dev` serves.
        let dev = Url::parse("http://localhost:1430/").ok();
        let served = Url::parse("http://localhost:1430/index.html").unwrap();
        assert!(allowed(&served, dev.as_ref()));
        assert!(!allowed(&served, None));
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
        #[cfg(target_os = "macos")]
        {
            let url = Url::parse("file:///Users/me/My%20Epics/1T2.3Z-a.hmzepic").unwrap();
            assert_eq!(
                epic(url.to_file_path()),
                Some(PathBuf::from("/Users/me/My Epics/1T2.3Z-a.hmzepic"))
            );
            let exe = "/Applications/Humanize Desktop.app/Contents/MacOS/humanize";
            assert_eq!(
                argued([exe, "a.hmzepic"], Path::new("/Users/me")),
                Some(PathBuf::from("/Users/me/a.hmzepic"))
            );
        }
        // As Explorer hands them over, after the app's own path; and from a terminal, where it
        // was launched.
        #[cfg(windows)]
        {
            let exe = r"C:\Program Files\Humanize Desktop\humanize.exe";
            let opened = r"C:\Users\me\My Epics\1T2.3Z-a.hmzepic";
            let from = Path::new(r"D:\work");
            assert_eq!(argued([exe, opened], from), Some(PathBuf::from(opened)));
            assert_eq!(
                argued([exe, r"epics\a.hmzepic"], from),
                Some(PathBuf::from(r"D:\work\epics\a.hmzepic"))
            );
            assert_eq!(argued([opened], from), None);
            assert_eq!(argued([exe], from), None);
        }
    }

    #[test]
    fn imports_by_its_path_on_the_page() {
        let path = Path::new("/Users/me/My Epics/a&b=c#d+e%.hmzepic");
        let page = Url::parse("http://tauri.localhost/").unwrap();
        let url = importing(&page, path).unwrap();
        assert_eq!(
            url.as_str(),
            "http://tauri.localhost/#/epics/import?path=%2FUsers%2Fme%2FMy+Epics%2Fa%26b%3Dc%23d%2Be%25.hmzepic"
        );
        // Read back as the page reads its hash.
        let hash = Url::parse(&format!("http://page{}", url.fragment().unwrap())).unwrap();
        let read: Vec<_> = hash.query_pairs().collect();
        assert_eq!(read, [("path".into(), path.to_str().unwrap().into())]);
        assert!(allowed(&url, Some(&page)));
        // A Windows path as it is: the page reads the file by it (Section 3.8.6 of [DESKTOP]).
        let url = importing(&page, Path::new(r"C:\Users\me\a b.hmzepic")).unwrap();
        assert_eq!(
            url.fragment(),
            Some("/epics/import?path=C%3A%5CUsers%5Cme%5Ca+b.hmzepic")
        );
    }

    #[test]
    fn imports_into_the_daemon_shown() {
        let path = Path::new("/a.hmzepic");
        let on = |at: &str| {
            let page = Url::parse(&format!("http://tauri.localhost/{at}")).unwrap();
            importing(&page, path).unwrap().fragment().map(String::from)
        };
        let local = Some("/epics/import?path=%2Fa.hmzepic".to_string());
        let gpu = Some("/@gpu/epics/import?path=%2Fa.hmzepic".to_string());
        assert_eq!(on("#/@gpu/live?workspace=%2Fhome%2Fme"), gpu);
        assert_eq!(on("#/@gpu/epics/import?path=%2Fb.hmzepic"), gpu);
        assert_eq!(on("#/@gpu"), gpu);
        assert_eq!(on("#@gpu?x"), gpu);
        assert_eq!(
            on("#/@my%20box/epics/a/exomyth"),
            Some("/@my%20box/epics/import?path=%2Fa.hmzepic".to_string())
        );
        assert_eq!(on(""), local);
        assert_eq!(on("#/live"), local);
        assert_eq!(on("#/epics/@gpu/exomyth"), local);
    }

    #[test]
    fn reads_an_opened_file_a_chunk_at_a_time() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("a.hmzepic");
        let bytes: Vec<u8> = (0..(READING + 10)).map(|n| n as u8).collect();
        std::fs::write(&path, &bytes).unwrap();
        let chunk = |offset, length| {
            let chunk = read(&path, offset, length).unwrap();
            (BASE64.decode(chunk.data).unwrap(), chunk.eof)
        };
        assert_eq!(chunk(0, 4), (bytes[..4].to_vec(), false));
        // No more than a mebibyte a call.
        let (first, eof) = chunk(0, u64::MAX);
        assert_eq!((first.len() as u64, eof), (READING, false));
        assert_eq!(
            chunk(READING, READING),
            (bytes[READING as usize..].to_vec(), true)
        );
        assert_eq!(chunk(READING + 10, 5), (Vec::new(), true));
        assert_eq!(chunk(u64::MAX, 5), (Vec::new(), true));
        assert!(read(&dir.path().join("gone.hmzepic"), 0, 1).is_err());
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
    fn says_its_status_as_the_splash_reads_it() {
        let json = |status| serde_json::to_string(&status).unwrap();
        assert_eq!(json(Status::Running), r#"{"state":"running"}"#);
        assert_eq!(
            serde_json::from_str::<Status>(r#"{"state":"starting"}"#).unwrap(),
            Status::Starting
        );
        #[cfg(windows)]
        {
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
            // As the splash hands back what it drew last.
            assert_eq!(
                serde_json::from_str::<Status>(&json(failed.clone())).unwrap(),
                failed
            );
        }
    }
}
