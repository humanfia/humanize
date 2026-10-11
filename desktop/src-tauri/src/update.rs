//! The app updating itself from each release: quietly a few seconds after launch and every 6
//! hours, or by hand from the menu. What it finds it downloads in the background, accepts only
//! signed with the key in tauri.conf.json, and offers once: Restart installs it and relaunches,
//! Later installs it as the app quits. A development build, version 0.0.0, never looks.

use std::ffi::CString;
use std::mem;
use std::os::unix::ffi::OsStrExt;
use std::path::Path;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, SystemTime};

use semver::Version;
use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_updater::{Update, UpdaterExt};

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

/// What the prompt's buttons say.
const RESTART: &str = "Restart";
const LATER: &str = "Later";

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
        | (Stage::Offering(_), By::Hand) => Step::Skip,
    }
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
/// a pre-release. `latest.json` is never a pre-release's, so this is the second guard.
fn newer(current: &Version, remote: &Version) -> bool {
    remote > current && (remote.pre.is_empty() || !current.pre.is_empty())
}

/// The app bundle the executable `exe` is in, where the app may replace it: not one run
/// read-only -- from its disk image, or moved aside by Gatekeeper -- nor one only an
/// administrator could replace, which would ask for a password as the app quits.
fn replaceable(exe: &Path) -> Option<&Path> {
    let writable = |path: &Path| {
        CString::new(path.as_os_str().as_bytes())
            // SAFETY: a path, NUL-terminated, that `access` only reads.
            .is_ok_and(|path| unsafe { libc::access(path.as_ptr(), libc::W_OK) } == 0)
    };
    // humanize.app/Contents/MacOS/humanize
    let bundle = exe.ancestors().nth(3)?;
    let ours = bundle.extension().is_some_and(|ext| ext == "app");
    (ours && writable(bundle) && writable(bundle.parent()?)).then_some(bundle)
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
}

/// The newer release, downloaded, its signature verified.
async fn fetch<R: Runtime>(app: &AppHandle<R>) -> Result<Option<Ready>, String> {
    let exe = std::env::current_exe().map_err(|why| why.to_string())?;
    if replaceable(&exe).is_none() {
        return Err(
            "humanize cannot replace itself where it is. Move it to Applications, and \
                    open it from there."
                .into(),
        );
    }
    let updater = app
        .updater_builder()
        .timeout(PATIENCE)
        .version_comparator(|current, remote| newer(&current, &remote.version))
        .build()
        .map_err(|why| why.to_string())?;
    let Some(mut update) = updater.check().await.map_err(|why| why.to_string())? else {
        return Ok(None);
    };
    // The look's patience is not handed on to the download.
    update.timeout = Some(PATIENCE);
    log::info!("humanize {} is out, downloading it", update.version);
    let bytes = update
        .download(|_, _| {}, || {})
        .await
        .map_err(|why| why.to_string())?;
    log::info!(
        "humanize {} is downloaded, its signature verified",
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
    match found {
        Ok(Some(ready)) => {
            offer(app.clone(), ready.0.version.clone());
            *stage = Stage::Offering(ready);
        }
        Ok(None) => {
            log::info!("humanize is up to date");
            if by_hand {
                let version = &app.package_info().version;
                let said = format!("{version} is the newest version.");
                tell(Level::Note, "humanize is up to date", said);
            }
        }
        Err(why) => {
            log::warn!("humanize could not check for updates: {why}");
            if by_hand {
                tell(Level::Failure, "Update failed", why);
            }
        }
    }
}

/// Asks once whether to restart into `version` now, and does what is chosen.
fn offer<R: Runtime>(app: AppHandle<R>, version: String) {
    thread::spawn(move || {
        let said = format!(
            "humanize {version} is ready. Restart to use it now, or it installs as humanize quits."
        );
        let title = format!("humanize {version}");
        let restart = alert::ask(Level::Note, &title, &said, &[RESTART, LATER]) == Some(0);
        let stage = app.state::<Mutex<Stage<Ready>>>();
        let mut stage = lock(&stage);
        let Stage::Offering(ready) = mem::take(&mut *stage) else {
            return;
        };
        if !restart {
            log::info!("humanize {version} installs as humanize quits");
            *stage = Stage::Deferred(ready);
            return;
        }
        drop(stage);
        let (update, bytes) = ready;
        match update.install(bytes) {
            Ok(()) => {
                log::info!("humanize {version} is installed, restarting");
                app.request_restart();
            }
            Err(why) => {
                log::error!("humanize {version} could not be installed: {why}");
                tell(Level::Failure, "Update failed", why.to_string());
            }
        }
    });
}

/// Takes back an alert still up, and installs what was downloaded and not yet installed, as the
/// app quits.
pub fn on_exit<R: Runtime>(app: &AppHandle<R>) {
    alert::withdraw();
    let Some(stage) = app.try_state::<Mutex<Stage<Ready>>>() else {
        return;
    };
    let (Stage::Offering((update, bytes)) | Stage::Deferred((update, bytes))) =
        mem::take(&mut *lock(&stage))
    else {
        return;
    };
    match update.install(bytes) {
        Ok(()) => log::info!("humanize {} is installed", update.version),
        Err(why) => log::error!("humanize {} could not be installed: {why}", update.version),
    }
}

/// Says something in an alert with one button, and goes on.
fn tell(level: Level, title: &'static str, said: String) {
    thread::spawn(move || alert::ask(level, title, &said, &["OK"]));
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

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

    #[test]
    fn replaces_only_a_bundle_it_may_write() {
        let dir = tempfile::tempdir().unwrap();
        let bundle = dir.path().join("humanize.app");
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
}
