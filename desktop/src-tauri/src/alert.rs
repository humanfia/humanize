//! An alert above every window, the app's hidden or not, and without holding up its quit as a
//! sheet would -- so an alert nobody answered never stops a shutdown. Each is taken back as the
//! app quits, never left behind it. On macOS, one put up for a process, `CFUserNotification`; on
//! Windows, a task dialog of no window's.

#[cfg(target_os = "macos")]
use std::sync::Arc;
use std::sync::Mutex;

#[cfg(target_os = "macos")]
use objc2_core_foundation::{
    CFDictionary, CFOptionFlags, CFRetained, CFString, CFType, CFURL, CFUserNotification,
    kCFUserNotificationAlertHeaderKey, kCFUserNotificationAlertMessageKey,
    kCFUserNotificationAlternateButtonTitleKey, kCFUserNotificationAlternateResponse,
    kCFUserNotificationDefaultButtonTitleKey, kCFUserNotificationDefaultResponse,
    kCFUserNotificationIconURLKey, kCFUserNotificationNoteAlertLevel,
    kCFUserNotificationStopAlertLevel,
};
#[cfg(windows)]
use windows_sys::Win32::Foundation::{HWND, LPARAM, S_OK, WPARAM};
#[cfg(windows)]
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
#[cfg(windows)]
use windows_sys::Win32::UI::Controls::{
    TASKDIALOG_BUTTON, TASKDIALOGCONFIG, TASKDIALOGCONFIG_0, TD_ERROR_ICON,
    TDF_ALLOW_DIALOG_CANCELLATION, TDF_SIZE_TO_CONTENT, TDF_USE_HICON_MAIN, TDN_CREATED,
    TDN_DESTROYED, TaskDialogIndirect,
};
#[cfg(windows)]
use windows_sys::Win32::UI::WindowsAndMessaging::{
    HWND_TOPMOST, IDI_APPLICATION, LoadIconW, PostMessageW, SWP_NOMOVE, SWP_NOSIZE,
    SetForegroundWindow, SetWindowPos, WM_CLOSE,
};
#[cfg(windows)]
use windows_sys::core::HRESULT;

use crate::lock;

/// Every alert up, to take back as the app quits; None once it has, so that none goes up after.
#[cfg(target_os = "macos")]
static UP: Mutex<Option<Vec<Arc<Alert>>>> = Mutex::new(Some(Vec::new()));

/// Every alert up, by its window, to take back as the app quits; None once it has, so that none
/// stays up after.
#[cfg(windows)]
static UP: Mutex<Option<Vec<usize>>> = Mutex::new(Some(Vec::new()));

#[cfg(target_os = "macos")]
struct Alert(CFRetained<CFUserNotification>);

// SAFETY: a CFUserNotification is made to be waited on in one thread and cancelled from another.
#[cfg(target_os = "macos")]
unsafe impl Send for Alert {}
#[cfg(target_os = "macos")]
unsafe impl Sync for Alert {}

/// What an alert is about.
#[derive(Clone, Copy)]
pub enum Level {
    Note,
    Failure,
}

/// Puts up an alert with one button or two, the first the default, and blocks until one is
/// pressed: which, or None where it was taken back or could not be put up.
#[cfg(target_os = "macos")]
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
#[cfg(target_os = "macos")]
pub fn withdraw() {
    for alert in lock(&UP).take().unwrap_or_default() {
        alert.0.cancel();
    }
}

/// The first button's identifier, past every one Windows gives its own buttons.
#[cfg(windows)]
const FIRST: i32 = 100;

/// Puts up an alert with one button or two, the first the default, and blocks until one is
/// pressed: which, or None where it was taken back or could not be put up.
#[cfg(windows)]
pub fn ask(level: Level, title: &str, said: &str, buttons: &[&str]) -> Option<usize> {
    lock(&UP).as_ref()?;
    let wide = |text: &str| text.encode_utf16().chain([0]).collect::<Vec<u16>>();
    let (app, title, said) = (wide("Humanize Desktop"), wide(title), wide(said));
    let labels: Vec<_> = buttons.iter().map(|button| wide(button)).collect();
    let buttons: Vec<_> = labels
        .iter()
        .zip(FIRST..)
        .map(|(label, id)| TASKDIALOG_BUTTON {
            nButtonID: id,
            pszButtonText: label.as_ptr(),
        })
        .collect();
    // A note under the app's own icon, as on macOS; a failure under Windows' own.
    let (icon, main) = match level {
        // SAFETY: the icon the app's executable carries, by the identifier tauri-build gives it.
        Level::Note => (
            TDF_USE_HICON_MAIN,
            TASKDIALOGCONFIG_0 {
                hMainIcon: unsafe {
                    LoadIconW(GetModuleHandleW(std::ptr::null()), IDI_APPLICATION)
                },
            },
        ),
        Level::Failure => (
            0,
            TASKDIALOGCONFIG_0 {
                pszMainIcon: TD_ERROR_ICON,
            },
        ),
    };
    let config = TASKDIALOGCONFIG {
        cbSize: size_of::<TASKDIALOGCONFIG>() as u32,
        // Closed by WM_CLOSE, as it is taken back, with no button pressed.
        dwFlags: TDF_ALLOW_DIALOG_CANCELLATION | TDF_SIZE_TO_CONTENT | icon,
        pszWindowTitle: app.as_ptr(),
        pszMainInstruction: title.as_ptr(),
        pszContent: said.as_ptr(),
        Anonymous1: main,
        pButtons: buttons.as_ptr(),
        cButtons: buttons.len() as u32,
        nDefaultButton: FIRST,
        pfCallback: Some(told),
        ..Default::default()
    };
    let mut pressed = 0;
    // SAFETY: a configuration whose strings and buttons outlive the call, and somewhere to say
    // the button pressed.
    let result = unsafe {
        TaskDialogIndirect(
            &config,
            &mut pressed,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    };
    if result != S_OK {
        log::warn!("an alert could not be put up: {result:#x}");
        return None;
    }
    usize::try_from(pressed - FIRST)
        .ok()
        .filter(|&button| button < buttons.len())
}

/// Told as an alert's window comes and goes: kept while it is up, above every window and in
/// front where Windows lets it, and closed at once where the app quits as it comes.
#[cfg(windows)]
unsafe extern "system" fn told(window: HWND, note: u32, _: WPARAM, _: LPARAM, _: isize) -> HRESULT {
    let mut up = lock(&UP);
    match (note as i32, up.as_mut()) {
        (TDN_CREATED, Some(up)) => {
            up.push(window as usize);
            // SAFETY: the alert's own window, up.
            unsafe {
                SetWindowPos(window, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE);
                SetForegroundWindow(window);
            }
        }
        // SAFETY: as above.
        (TDN_CREATED, None) => unsafe {
            PostMessageW(window, WM_CLOSE, 0, 0);
        },
        (TDN_DESTROYED, Some(up)) => up.retain(|&up| up != window as usize),
        _ => {}
    }
    S_OK
}

/// Takes back every alert up, and puts none up from now on.
#[cfg(windows)]
pub fn withdraw() {
    for window in lock(&UP).take().unwrap_or_default() {
        // SAFETY: an alert's window, or one gone since, which ignores it.
        unsafe { PostMessageW(window as HWND, WM_CLOSE, 0, 0) };
    }
}
