//! A notification as the system posts one for an app -- on macOS through
//! `UNUserNotificationCenter`, on Windows a toast: what `hmz web`'s page asks for when an epic
//! ends, a flow asks, or a chat turn is done while the window is not looked at. Clicking one
//! brings the window forward, and opens on `hmz web`'s page the address it was given -- a hash
//! of that page, and never anywhere else.

use std::sync::OnceLock;
#[cfg(target_os = "macos")]
use std::sync::atomic::{AtomicU64, Ordering};
#[cfg(target_os = "macos")]
use std::time::{SystemTime, UNIX_EPOCH};

#[cfg(target_os = "macos")]
use block2::{DynBlock, RcBlock};
#[cfg(target_os = "macos")]
use objc2::rc::Retained;
#[cfg(target_os = "macos")]
use objc2::runtime::{Bool, NSObject, NSObjectProtocol, ProtocolObject};
#[cfg(target_os = "macos")]
use objc2::{AnyThread, define_class, msg_send};
#[cfg(target_os = "macos")]
use objc2_foundation::{NSError, NSString};
#[cfg(target_os = "macos")]
use objc2_user_notifications::{
    UNAuthorizationOptions, UNMutableNotificationContent, UNNotification,
    UNNotificationPresentationOptions, UNNotificationRequest, UNNotificationResponse,
    UNNotificationSound, UNUserNotificationCenter, UNUserNotificationCenterDelegate,
};
#[cfg(windows)]
use std::{fs, path::PathBuf};
use tauri::AppHandle;

#[cfg(windows)]
use tauri_winrt_notification::{IconCrop, Toast};
use url::Url;

use crate::{lock, on_main, reveal, show};

/// The longest address a notification opens: one of the page's own is far shorter.
const LONGEST: usize = 2048;

/// The app, for a notification clicked.
static APP: OnceLock<AppHandle> = OnceLock::new();

/// Notifications posted this launch, numbering each apart from the others.
#[cfg(target_os = "macos")]
static POSTED: AtomicU64 = AtomicU64::new(0);

#[cfg(target_os = "macos")]
define_class!(
    // SAFETY: NSObject has no subclassing requirements, and the delegate keeps no state.
    #[unsafe(super(NSObject))]
    #[name = "HumanizeNotifications"]
    struct Delegate;

    unsafe impl NSObjectProtocol for Delegate {}

    unsafe impl UNUserNotificationCenterDelegate for Delegate {
        /// Shown even while the app is in front: the page asks only while its window is not
        /// looked at.
        #[unsafe(method(userNotificationCenter:willPresentNotification:withCompletionHandler:))]
        fn will_present(
            &self,
            _center: &UNUserNotificationCenter,
            _notification: &UNNotification,
            handler: &DynBlock<dyn Fn(UNNotificationPresentationOptions)>,
        ) {
            handler.call((UNNotificationPresentationOptions::Banner
                | UNNotificationPresentationOptions::List
                | UNNotificationPresentationOptions::Sound,));
        }

        #[unsafe(method(userNotificationCenter:didReceiveNotificationResponse:withCompletionHandler:))]
        fn did_receive(
            &self,
            _center: &UNUserNotificationCenter,
            response: &UNNotificationResponse,
            handler: &DynBlock<dyn Fn()>,
        ) {
            let identifier = response.notification().request().identifier().to_string();
            clicked(address(&identifier).to_owned());
            handler.call(());
        }
    }
);

/// Listens for notifications clicked, those of an earlier launch too. On the main thread, as
/// the app sets up.
#[cfg(target_os = "macos")]
pub fn init(app: &AppHandle) {
    let _ = APP.set(app.clone());
    if !bundled() {
        return;
    }
    // SAFETY: NSObject's own init, on an instance just allocated.
    let delegate: Retained<Delegate> = unsafe { msg_send![Delegate::alloc(), init] };
    UNUserNotificationCenter::currentNotificationCenter()
        .setDelegate(Some(ProtocolObject::from_ref(&*delegate)));
    // The centre holds its delegate weakly: this one is kept for as long as the app runs.
    std::mem::forget(delegate);
}

/// Listens for notifications clicked, while the app runs: Windows tells a toast clicked to the
/// launch that posted it alone.
#[cfg(windows)]
pub fn init(app: &AppHandle) {
    let _ = APP.set(app.clone());
}

/// Posts a notification, asking the first time on macOS whether the app may.
pub fn post(title: &str, body: &str, address: &str) {
    // Kept with the notification for as long as the system keeps it: only what a click may open.
    display(title, body, hash(address).map_or("", |_| address));
}

#[cfg(target_os = "macos")]
fn display(title: &str, body: &str, address: &str) {
    if !bundled() {
        log::info!("a notification is not posted outside the app's bundle");
        return;
    }
    let content = UNMutableNotificationContent::new();
    content.setTitle(&NSString::from_str(title));
    content.setBody(&NSString::from_str(body));
    content.setSound(Some(&UNNotificationSound::defaultSound()));
    let request = UNNotificationRequest::requestWithIdentifier_content_trigger(
        &NSString::from_str(&identifier(address)),
        &content,
        None,
    );
    let center = UNUserNotificationCenter::currentNotificationCenter();
    let posting = center.clone();
    // Asked once: macOS answers at once from then on, as the user last said.
    let posted = RcBlock::new(|error: *mut NSError| {
        // SAFETY: an NSError the centre made and holds through the call, or none.
        if let Some(error) = unsafe { error.as_ref() } {
            log::warn!("a notification could not be posted: {error}");
        }
    });
    let granted = RcBlock::new(move |granted: Bool, error: *mut NSError| {
        // SAFETY: as above.
        if let Some(error) = unsafe { error.as_ref() } {
            log::warn!("notifications could not be asked for: {error}");
        } else if granted.as_bool() {
            posting.addNotificationRequest_withCompletionHandler(&request, Some(&posted));
        } else {
            log::info!("notifications are not allowed");
        }
    });
    center.requestAuthorizationWithOptions_completionHandler(
        UNAuthorizationOptions::Alert | UNAuthorizationOptions::Sound,
        &granted,
    );
}

#[cfg(windows)]
fn display(title: &str, body: &str, address: &str) {
    let Some(app) = APP.get() else { return };
    // Installed, the app is known to Windows by its identifier, which its Start menu shortcut
    // carries; run by `tauri dev`, it is not, and posts as PowerShell.
    let id = if tauri::is_dev() {
        Toast::POWERSHELL_APP_ID
    } else {
        &app.config().identifier
    };
    let address = address.to_owned();
    let mut toast = Toast::new(id).title(title).text1(body);
    if let Some(logo) = logo(app) {
        toast = toast.icon(&logo, IconCrop::Square, "");
    }
    let shown = toast
        .on_activated(move |_| {
            clicked(address.clone());
            Ok(())
        })
        .show();
    if let Err(why) = shown {
        log::warn!("a notification could not be posted: {why}");
    }
}

/// The logo a toast shows beside what it says, as a file, which is all a toast takes: Windows
/// draws an app's own icon in the toast's corner only where it has made out its shortcut, and
/// not always then. Under ProgramData, which every account reads: Windows leaves out a toast's
/// picture kept under a user's AppData where that is shut to all but the user.
#[cfg(windows)]
fn logo(app: &AppHandle) -> Option<PathBuf> {
    const LOGO: &[u8] = include_bytes!("../icons/128x128@2x.png");
    let path = PathBuf::from(std::env::var_os("ProgramData")?)
        .join(&app.config().identifier)
        .join("logo.png");
    if fs::read(&path).ok().as_deref() != Some(LOGO) {
        fs::create_dir_all(path.parent()?).ok()?;
        fs::write(&path, LOGO).ok()?;
    }
    Some(path)
}

/// Brings the window forward, on `hmz web`'s page at the address clicked where it is one: on
/// the page it shows, by its hash alone; or, where it shows none yet -- a click that launched
/// the app -- on the page it opens once there is one.
fn clicked(address: String) {
    let Some(app) = APP.get() else { return };
    on_main(app, move |app, shell| {
        let page = lock(&shell.page).clone();
        match page {
            Some(mut page) => {
                // Signed in already: the hash changes, and the page is not loaded again.
                page.set_query(None);
                if let Some(url) = target(&page, &address) {
                    show(app, url);
                }
            }
            None => *lock(&shell.notified) = Some(address),
        }
        reveal(app);
    });
}

/// Whether the app runs from its bundle, `….app/Contents/MacOS/…`: the notification centre
/// throws for a process that is not, as one `cargo` runs.
#[cfg(target_os = "macos")]
fn bundled() -> bool {
    std::env::current_exe().is_ok_and(|exe| in_bundle(&exe))
}

#[cfg(target_os = "macos")]
fn in_bundle(exe: &std::path::Path) -> bool {
    let mut up = exe.ancestors().skip(1);
    up.next().and_then(|dir| dir.file_name()) == Some("MacOS".as_ref())
        && up.next().and_then(|dir| dir.file_name()) == Some("Contents".as_ref())
        && up
            .next()
            .and_then(|dir| dir.extension())
            .is_some_and(|ext| ext == "app")
}

/// A notification's identifier: unique, so that none replaces another, and carrying the address
/// it opens, so that one of an earlier launch opens it too.
#[cfg(target_os = "macos")]
fn identifier(address: &str) -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let n = POSTED.fetch_add(1, Ordering::Relaxed);
    format!("{now}.{n} {address}")
}

/// The address a notification's identifier carries.
#[cfg(target_os = "macos")]
fn address(identifier: &str) -> &str {
    identifier
        .split_once(' ')
        .map_or("", |(_, address)| address)
}

/// The hash a notification may open, `#/…`, without its `#`; nothing for anything else.
fn hash(address: &str) -> Option<&str> {
    address.strip_prefix('#').filter(|hash| {
        hash.starts_with('/') && address.len() <= LONGEST && !hash.chars().any(char::is_control)
    })
}

/// Where a notification clicked opens: the hash it was given, `#/…`, at the root of `hmz web`'s
/// page -- its origin, and its key where it is given one -- and nowhere else; nothing for
/// anything but such a hash.
pub fn target(page: &Url, address: &str) -> Option<Url> {
    let hash = hash(address)?;
    let mut url = page.clone();
    url.set_path("/");
    url.set_fragment(Some(hash));
    Some(url)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn opens_a_hash_of_the_servers_page_alone() {
        let server = Url::parse("http://127.0.0.1:8765/").unwrap();
        let at = |address: &str| target(&server, address).map(String::from);
        assert_eq!(
            at("#/@gpu/live?workspace=%2Fhome%2Fme").as_deref(),
            Some("http://127.0.0.1:8765/#/@gpu/live?workspace=%2Fhome%2Fme")
        );
        assert_eq!(at("#/").as_deref(), Some("http://127.0.0.1:8765/#/"));
        // From the address with the key, as the window first opens on, keeping it to sign in.
        let first = Url::parse("http://127.0.0.1:8765/?key=secret#/epics").unwrap();
        assert_eq!(
            target(&first, "#/@local/live").map(String::from).as_deref(),
            Some("http://127.0.0.1:8765/?key=secret#/@local/live")
        );
        // Never another origin, path or scheme.
        for address in [
            "",
            "#",
            "#epics",
            "/#/epics",
            "epics",
            "http://evil.example/#/epics",
            "//evil.example/#/epics",
            "javascript:alert(1)",
            "#/epics\n",
            "#/\u{7f}",
        ] {
            assert_eq!(at(address), None, "{address:?}");
        }
        assert_eq!(at(&format!("#/{}", "a".repeat(LONGEST))), None);
        // Whatever the hash says, the origin stays the server's.
        let odd = target(&server, "#/x#@evil.example:80/ y").unwrap();
        assert_eq!(odd.origin(), server.origin());
        assert_eq!(odd.path(), "/");
        assert_eq!(odd.query(), None);
    }

    #[test]
    #[cfg(target_os = "macos")]
    fn carries_its_address_in_a_unique_identifier() {
        let one = identifier("#/@local/live?workspace=a b");
        let two = identifier("#/@local/live?workspace=a b");
        assert_ne!(one, two);
        assert_eq!(address(&one), "#/@local/live?workspace=a b");
        assert_eq!(address(&identifier("")), "");
        assert_eq!(address("elsewhere"), "");
    }

    #[test]
    #[cfg(target_os = "macos")]
    fn posts_only_from_its_bundle() {
        let at = |path: &str| in_bundle(std::path::Path::new(path));
        assert!(at(
            "/Applications/Humanize Desktop.app/Contents/MacOS/humanize"
        ));
        assert!(!at("/repo/desktop/src-tauri/target/debug/humanize"));
        assert!(!at("/x/Contents/MacOS/humanize"));
        assert!(!at("/x.app/MacOS/humanize"));
        assert!(!at("humanize"));
    }
}
