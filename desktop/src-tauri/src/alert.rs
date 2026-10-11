//! An alert as macOS puts one up for a process, `CFUserNotification`: above every window, the
//! app's hidden or not, and without holding up its quit as a sheet would -- so an alert nobody
//! answered never stops a shutdown. Each is taken back as the app quits, never left behind it.

use std::sync::{Arc, Mutex};

use objc2_core_foundation::{
    CFDictionary, CFOptionFlags, CFRetained, CFString, CFType, CFURL, CFUserNotification,
    kCFUserNotificationAlertHeaderKey, kCFUserNotificationAlertMessageKey,
    kCFUserNotificationAlternateButtonTitleKey, kCFUserNotificationAlternateResponse,
    kCFUserNotificationDefaultButtonTitleKey, kCFUserNotificationDefaultResponse,
    kCFUserNotificationIconURLKey, kCFUserNotificationNoteAlertLevel,
    kCFUserNotificationStopAlertLevel,
};

use crate::lock;

/// Every alert up, to take back as the app quits; None once it has, so that none goes up after.
static UP: Mutex<Option<Vec<Arc<Alert>>>> = Mutex::new(Some(Vec::new()));

struct Alert(CFRetained<CFUserNotification>);

// SAFETY: a CFUserNotification is made to be waited on in one thread and cancelled from another.
unsafe impl Send for Alert {}
unsafe impl Sync for Alert {}

/// What an alert is about.
#[derive(Clone, Copy)]
pub enum Level {
    Note,
    Failure,
}

/// Puts up an alert with one button or two, the first the default, and blocks until one is
/// pressed: which, or None where it was taken back or could not be put up.
pub fn ask(level: Level, title: &str, said: &str, buttons: &[&str]) -> Option<usize> {
    // SAFETY: CoreFoundation's own constants, set as it loads, and only read.
    let [header, message, default, alternate, icon] = unsafe {
        [
            kCFUserNotificationAlertHeaderKey,
            kCFUserNotificationAlertMessageKey,
            kCFUserNotificationDefaultButtonTitleKey,
            kCFUserNotificationAlternateButtonTitleKey,
            kCFUserNotificationIconURLKey,
        ]
    };
    let text = |text: &str| -> CFRetained<CFType> { CFString::from_str(text).into() };
    let mut entries = vec![(header, text(title)), (message, text(said))];
    for (key, button) in [default, alternate].into_iter().zip(buttons) {
        entries.push((key, text(button)));
    }
    // The app's own icon, which it would not have otherwise.
    if let Some(url) = std::env::current_exe()
        .ok()
        .map(|exe| exe.with_file_name("../Resources/icon.icns"))
        .filter(|path| path.exists())
        .and_then(CFURL::from_file_path)
    {
        entries.push((icon, url.into()));
    }
    let (keys, values): (Vec<&CFString>, Vec<&CFType>) = entries
        .iter()
        .filter_map(|(key, value)| Some(((*key)?, &**value)))
        .unzip();
    let dictionary = CFDictionary::<CFString, CFType>::from_slices(&keys, &values);
    let flags = match level {
        Level::Note => kCFUserNotificationNoteAlertLevel,
        Level::Failure => kCFUserNotificationStopAlertLevel,
    };
    // Up and kept at once, so that it is never put up as the app quits and missed.
    let alert = {
        let mut up = lock(&UP);
        let up = up.as_mut()?;
        let mut error = 0;
        // SAFETY: no timeout, a dictionary of the keys it reads, and somewhere to say an error.
        let note = unsafe {
            CFUserNotification::new(None, 0.0, flags, &mut error, Some(dictionary.as_opaque()))
        };
        let Some(note) = note.filter(|_| error == 0) else {
            log::warn!("an alert could not be put up: {error}");
            return None;
        };
        let alert = Arc::new(Alert(note));
        up.push(alert.clone());
        alert
    };
    let mut response: CFOptionFlags = 0;
    // SAFETY: waits for as long as it takes, and says the button where it was given.
    let answered = unsafe { alert.0.receive_response(0.0, &mut response) } == 0;
    if let Some(up) = lock(&UP).as_mut() {
        up.retain(|up| !Arc::ptr_eq(up, &alert));
    }
    let pressed = response & 0x3;
    [
        kCFUserNotificationDefaultResponse,
        kCFUserNotificationAlternateResponse,
    ]
    .iter()
    .position(|&button| answered && pressed == button)
}

/// Takes back every alert up, and puts none up from now on.
pub fn withdraw() {
    for alert in lock(&UP).take().unwrap_or_default() {
        alert.0.cancel();
    }
}
