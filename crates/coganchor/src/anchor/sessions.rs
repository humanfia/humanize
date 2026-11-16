//! Commands run for a client. Port of the exec half of `hmz.coganchor.serve.sessions`.
//! [Unit 2]
//!
//! `EXEC {argv, program, cwd, env, tty, winsize, fence}` starts a command in a new session
//! (pipes, or a pty with the window size given), streams its output as `CHUNK`s on `Stdout`
//! and `Stderr` (everything on `Stdout` under a pty), takes `Stdin` chunks and `END`, and
//! closes with one `RSP` of `{exit_code}` or `{signal}` once every output descriptor has
//! reached end of file. No `END` is sent for output. A command asking for a fence runs under
//! `coganchor internal fence` ([`crate::fence::abroad::fenced`]).

use std::sync::Arc;

use crate::anchor::{ExportTable, Outbox, Sink};
use crate::proto::{Meta, RemoteError};

/// Starts the command `request` asks for, as exchange `id`. Errors the request itself makes
/// (no `argv`, no `cwd`) are `EINVAL`; failing to start the program is that errno.
pub fn exec(
    id: u64,
    request: &Meta,
    exports: Arc<ExportTable>,
    outbox: Arc<dyn Outbox>,
) -> Result<Box<dyn Sink>, RemoteError> {
    todo!("unit 2")
}
