//! Standing in for a process that should have run on the target. Port of
//! `hmz.coganchor.execproxy`. [Unit 11]
//!
//! The command runs on the target; its output is pumped into the stand-in's own stolen
//! descriptors, its stdin pumped from them, and its end reported on a channel plus a byte on
//! the supervisor's wake pipe.

use std::ffi::OsString;
use std::io;
use std::os::fd::{OwnedFd, RawFd};
use std::sync::Arc;
use std::sync::mpsc::Sender;

use nix::unistd::Pid;

use crate::client::RemoteClient;

/// The command to run on the target.
#[derive(Clone, Debug)]
pub struct ExecRequest {
    pub argv: Vec<OsString>,
    pub program: Option<OsString>,
    /// The working directory, as the target names it.
    pub cwd: String,
    pub env: Vec<(OsString, OsString)>,
    /// The fence's levels, where the agent is fenced.
    pub fence: Option<serde_json::Value>,
}

/// How a remote command ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Ending {
    Exited(i32),
    Signalled(i32),
    /// It never started: 127 for `ENOENT`, 126 otherwise (`hmz: argv0: strerror` written).
    Failed(i32),
}

/// A remote command finished, for the stand-in `pid`.
#[derive(Clone, Copy, Debug)]
pub struct Completion {
    pub pid: Pid,
    pub ending: Ending,
}

/// A remote command in progress.
pub struct ExecProxy {
    pub pid: Pid,
}

impl ExecProxy {
    /// Starts `request` on the target for stand-in `pid`, pumping through `fds` (its stdin,
    /// stdout, stderr). `tty` and the window size come from `fds[0]`; stdin is `/dev/null`
    /// where `borrow_stdin` is false.
    pub fn start(
        client: Arc<RemoteClient>,
        pid: Pid,
        request: ExecRequest,
        fds: [OwnedFd; 3],
        borrow_stdin: bool,
        done: Sender<Completion>,
        wake: RawFd,
    ) -> io::Result<ExecProxy> {
        todo!("unit 11")
    }

    /// Forwards a signal to the remote command's process group.
    pub fn signal(&self, signal: i32) {
        todo!("unit 11")
    }
}
