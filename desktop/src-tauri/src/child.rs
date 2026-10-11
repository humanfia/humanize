//! Every process the app starts -- uv, `hmz --version`, `hmz web` -- kept until it is done, so
//! that quitting stops each one still going, wherever starting had got to, and starts no more.

use std::io;
use std::os::unix::process::CommandExt;
use std::process::{Command, ExitStatus};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use shared_child::SharedChild;
use shared_child::unix::SharedChildExt;

use crate::lock;

/// How long a child may take to stop once interrupted, before it is killed.
pub const STOPPING: Duration = Duration::from_secs(3);

/// The children going, and whether the app is quitting.
static GOING: Mutex<Vec<Arc<SharedChild>>> = Mutex::new(Vec::new());
static QUITTING: AtomicBool = AtomicBool::new(false);

/// A child the app keeps: dropped from what quitting stops once it is dropped itself.
pub struct Child(Arc<SharedChild>);

impl std::ops::Deref for Child {
    type Target = SharedChild;
    fn deref(&self) -> &SharedChild {
        &self.0
    }
}

impl Drop for Child {
    fn drop(&mut self) {
        lock(&GOING).retain(|going| !Arc::ptr_eq(going, &self.0));
    }
}

/// Starts a command, with the signals that stop it as they are by default, and keeps it until it
/// is dropped; none once the app is quitting.
pub fn spawn(command: &mut Command) -> io::Result<Child> {
    // A signal ignored is ignored in a child too, and `hmz web` keeps one it was handed ignored --
    // so an app started where Ctrl+C is ignored, as from a script's background job, would have
    // Quit kill it rather than stop it.
    // SAFETY: `signal` is async-signal-safe, which is all that may run between fork and exec.
    unsafe {
        command.pre_exec(|| {
            for signal in [libc::SIGINT, libc::SIGTERM, libc::SIGHUP] {
                libc::signal(signal, libc::SIG_DFL);
            }
            Ok(())
        });
    }
    // Held while it is spawned, so that a quit in between waits for it and then stops it.
    let mut going = lock(&GOING);
    if QUITTING.load(Ordering::SeqCst) {
        return Err(io::Error::new(
            io::ErrorKind::Interrupted,
            "the app is quitting",
        ));
    }
    let child = Arc::new(SharedChild::spawn(command)?);
    going.push(child.clone());
    Ok(Child(child))
}

/// Interrupts a child, as Ctrl+C would, and kills it if it has not stopped in time. Reaped
/// either way.
pub fn ended(child: &SharedChild) -> Option<ExitStatus> {
    let _ = child.send_signal(libc::SIGINT);
    if let Ok(Some(status)) = child.wait_timeout(STOPPING) {
        return Some(status);
    }
    log::warn!(
        "{} did not stop in {} s; killing it",
        child.id(),
        STOPPING.as_secs()
    );
    let _ = child.kill();
    child.wait().ok()
}

/// Stops every child still going, and starts none from now on: the app is quitting.
pub fn quit() {
    let going: Vec<_> = {
        let mut going = lock(&GOING);
        QUITTING.store(true, Ordering::SeqCst);
        going.drain(..).collect()
    };
    for child in going {
        ended(&child);
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::process::Stdio;
    use std::time::Instant;

    /// Quitting is for the whole process, so a test of it runs apart, in a test process of its
    /// own: true where this is the one that ran it there, and is done.
    pub fn apart(test: &str) -> bool {
        if std::env::var_os("HUMANIZE_QUIT_TEST").is_some() {
            return false;
        }
        let status = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", test])
            .env("HUMANIZE_QUIT_TEST", "1")
            .stdout(Stdio::null())
            .status()
            .unwrap();
        assert!(status.success(), "{test} failed apart");
        true
    }

    /// The pid a fake writes once it is going, waited for: a script run the first time is
    /// checked by macOS first, which can take a while.
    pub fn written(path: &std::path::Path) -> u32 {
        let began = Instant::now();
        loop {
            if let Some(pid) = std::fs::read_to_string(path)
                .ok()
                .and_then(|pid| pid.trim().parse().ok())
            {
                return pid;
            }
            assert!(began.elapsed() < Duration::from_secs(10), "no pid");
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    pub fn gone(pid: u32) -> bool {
        (unsafe { libc::kill(pid as libc::pid_t, 0) }) != 0
    }

    #[test]
    fn quitting_stops_what_is_going_and_starts_nothing() {
        if apart("child::tests::quitting_stops_what_is_going_and_starts_nothing") {
            return;
        }
        // One that stops when interrupted, and one that will not.
        let polite = spawn(Command::new("/bin/sleep").arg("30")).unwrap();
        let stubborn =
            spawn(Command::new("/bin/sh").args(["-c", "trap '' INT; sleep 30"])).unwrap();
        let (polite_pid, stubborn_pid) = (polite.id(), stubborn.id());
        // Time for the shell to set its trap.
        std::thread::sleep(Duration::from_millis(300));
        let began = Instant::now();
        quit();
        // The stubborn one waited for, then killed.
        let took = began.elapsed();
        assert!(
            took >= STOPPING && took < STOPPING + Duration::from_secs(1),
            "{took:?}"
        );
        assert!(gone(polite_pid) && gone(stubborn_pid));
        assert!(spawn(&mut Command::new("/bin/sleep")).is_err());
    }

    #[test]
    fn forgets_a_child_once_it_is_dropped() {
        let child = spawn(&mut Command::new("/usr/bin/true")).unwrap();
        let _ = child.wait();
        let raw = child.0.clone();
        drop(child);
        assert!(!lock(&GOING).iter().any(|going| Arc::ptr_eq(going, &raw)));
    }
}
