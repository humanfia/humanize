//! The app updating itself from each release: quietly a few seconds after launch and every 6
//! hours, or by hand from the menu. It reads the `latest.json` of the newest release it may take
//! -- a pre-release only where it is one -- since GitHub's latest release is never a
//! pre-release, and may predate the app. What it finds it downloads in the background, accepts
//! only signed with the key in tauri.conf.json, and offers once: Restart installs it and
//! relaunches, Later installs it as the app quits. A development build, version 0.0.0, never
//! looks. A look by hand, and an install, show in a small window of their own as they go. On
//! Windows its setup replaces the app only once the app has quit: Restart quits into it, and it
//! relaunches the app.

use std::mem;
use std::path::Path;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, SystemTime};

use semver::Version;
use serde::Deserialize;
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Manager, Runtime, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_updater::{Update, UpdaterExt};
use url::Url;

use crate::alert::{self, Level};
use crate::lock;

/// How long after launch the first look waits, so that it never slows the start.
const FIRST: Duration = Duration::from_secs(5);

/// How long between one look and the next, by the wall clock, which goes on while the Mac
/// sleeps -- unlike the clock a timer runs on, which stops.
const EVERY: Duration = Duration::from_secs(6 * 60 * 60);

/// How often the timer wakes to see whether a look is due.
const TICK: Duration = Duration::from_secs(10 * 60);

/// How long a look, or a download, may take before it is given up.
const PATIENCE: Duration = Duration::from_secs(5 * 60);

/// The releases, newest first: drafts never among them.
const RELEASES: &str = "https://api.github.com/repos/humanfia/humanize/releases?per_page=30";

/// What a release offers its update in.
const LATEST: &str = "latest.json";

/// What `fetch` says where `replaceable` refuses.
#[cfg(target_os = "macos")]
const ELSEWHERE: &str = "Move it to Applications, and open it from there.";
#[cfg(windows)]
const ELSEWHERE: &str = "Install it for yourself with its setup, and open it from there.";

/// What the prompt's buttons say.
const RESTART: &str = "Restart";
const LATER: &str = "Later";

/// The progress window's label.
pub const WINDOW: &str = "update";

/// What the progress window says, kept so that it says it once it loads.
static VIEW: Mutex<View> = Mutex::new(View::Checking);

/// An update, downloaded and its signature verified, with what to install it from.
type Ready = (Update, Vec<u8>);

/// Who asked for a look.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum By {
    /// The timer: it never says anything but to the log.
    Schedule,
    /// Check for Updates…: it says what it found, up to date or failed.
    Hand,
}

/// Where the updater stands, with the update it holds where it holds one.
#[derive(Debug, Default, PartialEq)]
enum Stage<T> {
    #[default]
    Idle,
    /// Looking and downloading; to say what it found where one asked by hand.
    Checking { by_hand: bool },
    /// Downloaded, and its prompt up.
    Offering(T),
    /// Downloaded, and Later chosen: it installs as the app quits.
    Deferred(T),
    /// Restart chosen: installing, then relaunching. On Windows it holds what goes in as the app
    /// quits.
    Installing(Option<T>),
}

/// What a look asked for does, from where the updater stands.
#[derive(Debug, PartialEq)]
enum Step {
    Check,
    /// One is under way already: say what it finds, since a hand asked.
    Report,
    /// One is downloaded already: offer it again.
    Offer,
    Skip,
}

fn step<T>(stage: &Stage<T>, by: By) -> Step {
    match (stage, by) {
        (Stage::Idle, _) => Step::Check,
        (Stage::Checking { .. }, By::Hand) => Step::Report,
        (Stage::Deferred(_), By::Hand) => Step::Offer,
        // Its prompt is up already, or what it holds goes in as the app quits.
        (Stage::Checking { .. } | Stage::Offering(_) | Stage::Deferred(_), By::Schedule)
        | (Stage::Offering(_) | Stage::Installing(_), _) => Step::Skip,
    }
}

/// Whether the progress window is up: while a look asked by hand runs, and while installing.
fn shows<T>(stage: &Stage<T>) -> bool {
    matches!(
        stage,
        Stage::Checking { by_hand: true } | Stage::Installing(_)
    )
}

/// What the progress window says.
#[derive(Clone, Debug, PartialEq)]
enum View {
    /// Looking: a bar that only says it is going.
    Checking,
    /// Downloading, how far where the size is known.
    Downloading {
        version: String,
        percent: Option<u8>,
    },
    Installing(String),
}

/// How far a download is, of `total` where it is known.
fn percent(got: u64, total: Option<u64>) -> Option<u8> {
    let total = total.filter(|&total| total > 0)?;
    Some((got.saturating_mul(100) / total).min(100) as u8)
}

/// What draws `view` on the progress window's page.
fn script(view: &View) -> String {
    let (title, percent) = match view {
        View::Checking => ("Checking for Updates…".to_owned(), None),
        View::Downloading { version, percent } => {
            (format!("Downloading Humanize Desktop {version}…"), *percent)
        }
        View::Installing(version) => (format!("Installing Humanize Desktop {version}…"), None),
    };
    format!(
        "draw({})",
        serde_json::json!({ "title": title, "percent": percent })
    )
}

/// Says `view` in the progress window, where it is up, and once it is.
fn show<R: Runtime>(app: &AppHandle<R>, view: View) {
    let mut shown = lock(&VIEW);
    if *shown == view {
        return;
    }
    *shown = view;
    if let Some(window) = app.get_webview_window(WINDOW) {
        let _ = window.eval(script(&shown));
    }
}

/// Puts the progress window up, or takes it down, and Check for Updates… with it, as the
/// updater stands, then does `then`: on the main thread after each change, so that the last
/// change has its way, and an alert goes up only once the window is down.
fn present<R: Runtime>(app: &AppHandle<R>, then: impl FnOnce() + Send + 'static) {
    let on = app.clone();
    let presented = app.run_on_main_thread(move || {
        let (up, looking) = {
            let stage = on.state::<Mutex<Stage<Ready>>>();
            let stage = lock(&stage);
            (
                shows(&stage),
                matches!(*stage, Stage::Checking { by_hand: true }),
            )
        };
        crate::menu::checking(&on, looking);
        match (up, on.get_webview_window(WINDOW)) {
            (true, Some(window)) => {
                let _ = window.show();
                let _ = window.set_focus();
            }
            (true, None) => {
                if let Err(why) = open(&on) {
                    log::warn!("the update's window could not be opened: {why}");
                }
            }
            (false, Some(window)) => {
                let _ = window.destroy();
            }
            (false, None) => {}
        }
        then();
    });
    if let Err(why) = presented {
        log::warn!("the update's window could not be told: {why}");
    }
}

/// The progress window: small, its size its own, drawn in the page's paper before anything is.
fn open<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let window = WebviewWindowBuilder::new(app, WINDOW, WebviewUrl::App("update.html".into()))
        .title("Software Update")
        .inner_size(400.0, 104.0)
        .resizable(false)
        .closable(false)
        .minimizable(false)
        .maximizable(false)
        .center()
        .visible(false)
        .on_page_load(|window, page| {
            if page.event() == PageLoadEvent::Finished {
                let said = script(&lock(&VIEW));
                let _ = window.eval(said);
            }
        })
        .build()?;
    window.set_background_color(Some(crate::paper(window.theme()?)))?;
    window.show()?;
    window.set_focus()
}

/// Whether a look is due, the one before having been at `last`: a clock set back makes it due.
fn due(last: SystemTime, now: SystemTime) -> bool {
    !matches!(now.duration_since(last), Ok(since) if since < EVERY)
}

/// Whether this build looks for updates at all: a development build never does.
pub fn checks(version: &Version) -> bool {
    *version != Version::new(0, 0, 0)
}

/// Whether `remote` replaces `current`: only a newer one, and a pre-release only one already on
/// a pre-release. `latest` picks the release by the same rule, so this is the second guard.
fn newer(current: &Version, remote: &Version) -> bool {
    remote > current && (remote.pre.is_empty() || !current.pre.is_empty())
}

/// A release, as GitHub lists it.
#[derive(Debug, Deserialize)]
struct Release {
    tag_name: String,
    assets: Vec<Asset>,
}

#[derive(Debug, Deserialize)]
struct Asset {
    name: String,
    browser_download_url: Url,
}

/// The `latest.json` of the newest release `current` may take, of those that carry one: a
/// pre-release only where `current` is one. Whether it is newer than `current` is the
/// updater's to say.
fn latest(current: &Version, releases: Vec<Release>) -> Option<Url> {
    releases
        .into_iter()
        .filter_map(|release| {
            let version = Version::parse(release.tag_name.strip_prefix('v')?).ok()?;
            let asset = release
                .assets
                .into_iter()
                .find(|asset| asset.name == LATEST)?;
            (version.pre.is_empty() || !current.pre.is_empty())
                .then_some((version, asset.browser_download_url))
        })
        .max_by(|(one, _), (other, _)| one.cmp(other))
        .map(|(_, url)| url)
}

/// The releases, from GitHub.
fn releases() -> Result<Vec<Release>, String> {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(PATIENCE))
        // What the system trusts, a company's own authority included.
        .tls_config(
            ureq::tls::TlsConfig::builder()
                .root_certs(ureq::tls::RootCerts::PlatformVerifier)
                .build(),
        )
        .build()
        .into();
    let failed = |why: &dyn std::fmt::Display| format!("the releases could not be listed: {why}");
    let said = agent
        .get(RELEASES)
        .header("Accept", "application/vnd.github+json")
        .call()
        .map_err(|why| failed(&why))?
        .body_mut()
        .read_to_string()
        .map_err(|why| failed(&why))?;
    serde_json::from_str(&said).map_err(|why| failed(&why))
}

/// The app bundle the executable `exe` is in, where the app may replace it: not one run
/// read-only -- from its disk image, or moved aside by Gatekeeper -- nor one only an
/// administrator could replace, which would ask for a password as the app quits.
#[cfg(target_os = "macos")]
fn replaceable(exe: &Path) -> Option<&Path> {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;

    let writable = |path: &Path| {
        CString::new(path.as_os_str().as_bytes())
            // SAFETY: a path, NUL-terminated, that `access` only reads.
            .is_ok_and(|path| unsafe { libc::access(path.as_ptr(), libc::W_OK) } == 0)
    };
    // Humanize Desktop.app/Contents/MacOS/humanize
    let bundle = exe.ancestors().nth(3)?;
    let ours = bundle.extension().is_some_and(|ext| ext == "app");
    (ours && writable(bundle) && writable(bundle.parent()?)).then_some(bundle)
}

/// The folder the executable `exe` is in, where the app may replace it: one its setup installed
/// it in, which leaves the uninstaller beside it, and one this user may write -- not a build, nor
/// a copy run from elsewhere, nor one only an administrator could replace.
#[cfg(windows)]
fn replaceable(exe: &Path) -> Option<&Path> {
    let folder = exe.parent()?;
    // Opened to write, and written nothing.
    std::fs::OpenOptions::new()
        .append(true)
        .open(folder.join("uninstall.exe"))
        .is_ok()
        .then_some(folder)
}

/// Sets the updater up, and starts looking where this build looks.
pub fn init<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    app.plugin(tauri_plugin_updater::Builder::new().build())?;
    app.manage(Mutex::new(Stage::<Ready>::Idle));
    if checks(&app.package_info().version) {
        let app = app.clone();
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep(FIRST).await;
            let mut last = SystemTime::now();
            check(&app, By::Schedule);
            loop {
                tokio::time::sleep(TICK).await;
                let now = SystemTime::now();
                if due(last, now) {
                    last = now;
                    check(&app, By::Schedule);
                }
            }
        });
    }
    Ok(())
}

/// Looks for an update, or offers the one downloaded already.
pub fn check<R: Runtime>(app: &AppHandle<R>, by: By) {
    let stage = app.state::<Mutex<Stage<Ready>>>();
    let mut stage = lock(&stage);
    match step(&stage, by) {
        Step::Check => {
            *stage = Stage::Checking {
                by_hand: by == By::Hand,
            };
            *lock(&VIEW) = View::Checking;
            let app = app.clone();
            tauri::async_runtime::spawn(async move {
                let found = fetch(&app).await;
                settle(&app, found);
            });
        }
        Step::Report => *stage = Stage::Checking { by_hand: true },
        Step::Offer => {
            if let Stage::Deferred(ready) = mem::take(&mut *stage) {
                offer(app.clone(), ready.0.version.clone());
                *stage = Stage::Offering(ready);
            }
        }
        Step::Skip => {}
    }
    drop(stage);
    present(app, || {});
}

/// The newer release, downloaded, its signature verified.
async fn fetch<R: Runtime>(app: &AppHandle<R>) -> Result<Option<Ready>, String> {
    let exe = std::env::current_exe().map_err(|why| why.to_string())?;
    if replaceable(&exe).is_none() {
        return Err(format!(
            "Humanize Desktop cannot replace itself where it is. {ELSEWHERE}"
        ));
    }
    let current = app.package_info().version.clone();
    let listed = tauri::async_runtime::spawn_blocking(releases)
        .await
        .map_err(|why| why.to_string())??;
    let Some(endpoint) = latest(&current, listed) else {
        return Ok(None);
    };
    let updater = app
        .updater_builder()
        .endpoints(vec![endpoint])
        .map_err(|why| why.to_string())?
        .timeout(PATIENCE)
        // On Windows, where its setup would relaunch the app: only after Restart.
        .restart_after_install(false)
        .version_comparator(|current, remote| newer(&current, &remote.version))
        .build()
        .map_err(|why| why.to_string())?;
    let Some(mut update) = updater.check().await.map_err(|why| why.to_string())? else {
        return Ok(None);
    };
    // The look's patience is not handed on to the download.
    update.timeout = Some(PATIENCE);
    log::info!("Humanize Desktop {} is out, downloading it", update.version);
    let version = update.version.clone();
    let (mut got, mut was) = (0, None);
    let bytes = update
        .download(
            |chunk, total| {
                got += chunk as u64;
                let percent = percent(got, total);
                if was.replace(percent) != Some(percent) {
                    let version = version.clone();
                    show(app, View::Downloading { version, percent });
                }
            },
            || {},
        )
        .await
        .map_err(|why| why.to_string())?;
    log::info!(
        "Humanize Desktop {} is downloaded, its signature verified",
        update.version
    );
    Ok(Some((update, bytes)))
}

/// Keeps what a look found, and says so: to the log always, and in an alert where there is
/// something to install or one asked by hand.
fn settle<R: Runtime>(app: &AppHandle<R>, found: Result<Option<Ready>, String>) {
    let stage = app.state::<Mutex<Stage<Ready>>>();
    let mut stage = lock(&stage);
    let by_hand = matches!(*stage, Stage::Checking { by_hand: true });
    *stage = Stage::Idle;
    let on = app.clone();
    let say: Box<dyn FnOnce() + Send> = match found {
        Ok(Some(ready)) => {
            let version = ready.0.version.clone();
            *stage = Stage::Offering(ready);
            Box::new(move || offer(on, version))
        }
        Ok(None) => {
            log::info!("Humanize Desktop is up to date");
            let said = format!("{} is the newest version.", app.package_info().version);
            Box::new(move || {
                if by_hand {
                    tell(Level::Note, "Humanize Desktop is up to date", said);
                }
            })
        }
        Err(why) => {
            log::warn!("Humanize Desktop could not check for updates: {why}");
            Box::new(move || {
                if by_hand {
                    tell(Level::Failure, "Update failed", why);
                }
            })
        }
    };
    drop(stage);
    present(app, say);
}

/// Asks once whether to restart into `version` now, and does what is chosen.
fn offer<R: Runtime>(app: AppHandle<R>, version: String) {
    thread::spawn(move || {
        let said = format!(
            "Humanize Desktop {version} is ready. Restart to use it now, or it installs as Humanize Desktop quits."
        );
        let title = format!("Humanize Desktop {version}");
        let restart = alert::ask(Level::Note, &title, &said, &[RESTART, LATER]) == Some(0);
        let stage = app.state::<Mutex<Stage<Ready>>>();
        let mut stage = lock(&stage);
        let Stage::Offering(ready) = mem::take(&mut *stage) else {
            return;
        };
        if !restart {
            log::info!("Humanize Desktop {version} installs as Humanize Desktop quits");
            *stage = Stage::Deferred(ready);
            return;
        }
        // Its setup runs as the app quits, and relaunches it.
        #[cfg(windows)]
        {
            log::info!("Humanize Desktop {version} installs as Humanize Desktop restarts");
            let (update, bytes) = ready;
            *stage = Stage::Installing(Some((update.restart_after_install(true), bytes)));
            drop(stage);
            show(&app, View::Installing(version));
            present(&app, || {});
            app.request_restart();
        }
        #[cfg(target_os = "macos")]
        {
            *stage = Stage::Installing(None);
            drop(stage);
            show(&app, View::Installing(version.clone()));
            present(&app, || {});
            let (update, bytes) = ready;
            match update.install(bytes) {
                Ok(()) => {
                    log::info!("Humanize Desktop {version} is installed, restarting");
                    app.request_restart();
                }
                Err(why) => {
                    log::error!("Humanize Desktop {version} could not be installed: {why}");
                    *lock(&app.state::<Mutex<Stage<Ready>>>()) = Stage::Idle;
                    present(&app, move || {
                        tell(Level::Failure, "Update failed", why.to_string());
                    });
                }
            }
        }
    });
}

/// Takes back an alert and the progress window still up, and installs what was downloaded and
/// not yet installed, as the app quits: on Windows, by starting its setup and exiting at once.
pub fn on_exit<R: Runtime>(app: &AppHandle<R>) {
    alert::withdraw();
    if let Some(window) = app.get_webview_window(WINDOW) {
        let _ = window.destroy();
    }
    let Some(stage) = app.try_state::<Mutex<Stage<Ready>>>() else {
        return;
    };
    let (Stage::Offering((update, bytes))
    | Stage::Deferred((update, bytes))
    | Stage::Installing(Some((update, bytes)))) = mem::take(&mut *lock(&stage))
    else {
        return;
    };
    match update.install(bytes) {
        Ok(()) => log::info!("Humanize Desktop {} is installed", update.version),
        Err(why) => log::error!(
            "Humanize Desktop {} could not be installed: {why}",
            update.version
        ),
    }
}

/// Says something in an alert with one button, and goes on.
fn tell(level: Level, title: &'static str, said: String) {
    thread::spawn(move || alert::ask(level, title, &said, &["OK"]));
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    fn version(text: &str) -> Version {
        Version::parse(text).unwrap()
    }

    #[test]
    fn a_development_build_never_looks() {
        assert!(!checks(&version("0.0.0")));
        assert!(checks(&version("0.0.1")));
        assert!(checks(&version("0.2.0-rc.1")));
    }

    #[test]
    fn takes_only_a_newer_release() {
        let newer = |current, remote| newer(&version(current), &version(remote));
        assert!(newer("0.2.0", "0.2.1"));
        assert!(newer("0.2.1", "0.3.0"));
        assert!(!newer("0.2.1", "0.2.1"));
        assert!(!newer("0.3.0", "0.2.1"));
        // A release after its own pre-releases.
        assert!(newer("0.3.0-rc.1", "0.3.0"));
        assert!(newer("0.3.0-rc.1", "0.3.0-rc.2"));
        // A pre-release never for one on a release, and never back from one.
        assert!(!newer("0.2.1", "0.3.0-rc.1"));
        assert!(!newer("0.3.0-rc.1", "0.2.1"));
    }

    #[test]
    fn reads_the_newest_latest_json_it_may_take() {
        let release = |tag: &str, assets: &[&str]| Release {
            tag_name: tag.into(),
            assets: assets
                .iter()
                .map(|name| Asset {
                    name: (*name).into(),
                    browser_download_url: Url::parse(&format!("https://x/{tag}/{name}")).unwrap(),
                })
                .collect(),
        };
        let releases = || {
            vec![
                release("v0.3.0-beta.1", &["latest.json"]),
                release("v0.2.1", &["x.dmg", "latest.json"]),
                release("v0.2.0", &["latest.json"]),
                // Before the app: no update in it.
                release("v0.4.0", &["hmz-0.4.0.tar.gz"]),
                release("nightly", &["latest.json"]),
            ]
        };
        let latest = |current| latest(&version(current), releases()).map(String::from);
        assert_eq!(
            latest("0.2.0").as_deref(),
            Some("https://x/v0.2.1/latest.json")
        );
        assert_eq!(
            latest("0.2.0-beta.2").as_deref(),
            Some("https://x/v0.3.0-beta.1/latest.json")
        );
        assert_eq!(super::latest(&version("0.2.0"), vec![]), None);
        assert_eq!(
            super::latest(&version("0.2.0"), vec![release("v0.1.0", &["hmz.whl"])]),
            None
        );
    }

    #[test]
    fn looks_once_at_a_time_and_offers_once() {
        use By::{Hand, Schedule};
        let checking = Stage::<()>::Checking { by_hand: false };
        assert_eq!(step(&Stage::<()>::Idle, Schedule), Step::Check);
        assert_eq!(step(&Stage::<()>::Idle, Hand), Step::Check);
        assert_eq!(step(&checking, Schedule), Step::Skip);
        assert_eq!(step(&checking, Hand), Step::Report);
        assert_eq!(step(&Stage::Offering(()), Schedule), Step::Skip);
        assert_eq!(step(&Stage::Offering(()), Hand), Step::Skip);
        // Later: the timer leaves it be, a hand asks again.
        assert_eq!(step(&Stage::Deferred(()), Schedule), Step::Skip);
        assert_eq!(step(&Stage::Deferred(()), Hand), Step::Offer);
        // Installing, then relaunching: nothing more to look for.
        assert_eq!(step(&Stage::<()>::Installing(None), Schedule), Step::Skip);
        assert_eq!(step(&Stage::<()>::Installing(None), Hand), Step::Skip);
    }

    #[test]
    fn shows_its_progress_only_for_a_look_by_hand_and_an_install() {
        assert!(!shows(&Stage::<()>::Idle));
        assert!(!shows(&Stage::<()>::Checking { by_hand: false }));
        assert!(shows(&Stage::<()>::Checking { by_hand: true }));
        assert!(!shows(&Stage::Offering(())));
        assert!(!shows(&Stage::Deferred(())));
        assert!(shows(&Stage::<()>::Installing(None)));
    }

    #[test]
    fn says_how_far_a_download_is_where_its_size_is_known() {
        assert_eq!(percent(0, Some(200)), Some(0));
        assert_eq!(percent(50, Some(200)), Some(25));
        assert_eq!(percent(200, Some(200)), Some(100));
        assert_eq!(percent(300, Some(200)), Some(100));
        assert_eq!(percent(50, None), None);
        assert_eq!(percent(50, Some(0)), None);
    }

    #[test]
    fn draws_what_the_progress_window_says() {
        assert_eq!(
            script(&View::Checking),
            r#"draw({"percent":null,"title":"Checking for Updates…"})"#
        );
        let downloading = |percent| View::Downloading {
            version: "0.3.0".into(),
            percent,
        };
        assert_eq!(
            script(&downloading(Some(42))),
            r#"draw({"percent":42,"title":"Downloading Humanize Desktop 0.3.0…"})"#
        );
        assert_eq!(
            script(&downloading(None)),
            r#"draw({"percent":null,"title":"Downloading Humanize Desktop 0.3.0…"})"#
        );
        assert_eq!(
            script(&View::Installing("0.3.0".into())),
            r#"draw({"percent":null,"title":"Installing Humanize Desktop 0.3.0…"})"#
        );
    }

    #[test]
    fn looks_every_6_hours_of_the_wall_clock() {
        let last = SystemTime::UNIX_EPOCH + Duration::from_secs(1_000_000);
        assert!(!due(last, last));
        assert!(!due(last, last + EVERY - Duration::from_secs(1)));
        assert!(due(last, last + EVERY));
        // A night asleep counts.
        assert!(due(last, last + Duration::from_secs(9 * 60 * 60)));
        assert!(due(last, last - Duration::from_secs(1)));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn replaces_only_a_bundle_it_may_write() {
        use std::os::unix::fs::PermissionsExt;

        let dir = tempfile::tempdir().unwrap();
        let bundle = dir.path().join("Humanize Desktop.app");
        let exe = bundle.join("Contents/MacOS/humanize");
        fs::create_dir_all(exe.parent().unwrap()).unwrap();
        fs::write(&exe, "").unwrap();
        assert_eq!(replaceable(&exe), Some(bundle.as_path()));
        // Not in a bundle, as while it is developed.
        assert_eq!(replaceable(&dir.path().join("target/debug/humanize")), None);
        // Where it may not be replaced.
        let mode = |path: &Path, mode| fs::set_permissions(path, fs::Permissions::from_mode(mode));
        mode(dir.path(), 0o555).unwrap();
        assert_eq!(replaceable(&exe), None);
        mode(dir.path(), 0o755).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn replaces_only_an_install_it_may_write() {
        let dir = tempfile::tempdir().unwrap();
        // %LOCALAPPDATA%\Humanize Desktop, where its setup installs it for one user.
        let folder = dir.path().join("Humanize Desktop");
        let exe = folder.join("humanize.exe");
        let uninstaller = folder.join("uninstall.exe");
        fs::create_dir_all(&folder).unwrap();
        fs::write(&exe, "").unwrap();
        // Not installed: while it is developed, or a copy unpacked.
        assert_eq!(replaceable(&exe), None);
        fs::write(&uninstaller, "").unwrap();
        assert_eq!(replaceable(&exe), Some(folder.as_path()));
        assert_eq!(fs::read(&uninstaller).unwrap(), b"");
        // Where it may not be replaced.
        let readonly = |readonly| {
            let mut permissions = fs::metadata(&uninstaller).unwrap().permissions();
            permissions.set_readonly(readonly);
            fs::set_permissions(&uninstaller, permissions).unwrap();
        };
        readonly(true);
        assert_eq!(replaceable(&exe), None);
        readonly(false);
    }
}
