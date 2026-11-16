//! Exit statuses, as `hmz internal anchor` and its siblings have always used them.

/// The operation failed: a connection, protocol, operating-system or value error.
pub const FAILED: i32 = 1;
/// The command line was malformed (what argument parsing exits with).
pub const USAGE: i32 = 2;
/// A fence could not be put up around a program.
pub const UNFENCED: i32 = 126;
/// The program to run is not installed, or could not be started.
pub const NOT_INSTALLED: i32 = 127;
/// Interrupted from the keyboard.
pub const INTERRUPTED: i32 = 130;

/// The status a shell reports for a child: its exit code, or 128 plus the signal that ended it.
pub fn of_wait(status: nix::sys::wait::WaitStatus) -> i32 {
    use nix::sys::wait::WaitStatus;
    match status {
        WaitStatus::Exited(_, code) => code,
        WaitStatus::Signaled(_, signal, _) => 128 + signal as i32,
        _ => FAILED,
    }
}

/// Writes `hmz: <reason>` to standard error and returns [`FAILED`].
pub fn failed(reason: impl std::fmt::Display) -> i32 {
    crate::log::say(reason);
    FAILED
}
