//! Request dispatch for one connection. Port of `hmz.coganchor.serve.server`. [Unit 1]
//!
//! The handshake (`HELLO`: version, token, and the reply naming this machine, its exports and
//! what it can fence), routing `CHUNK`/`END`/`SIGNAL` to the [`Sink`] of their exchange, and
//! the mapping of failures onto errnos (`ENOSYS` for an unknown op, `EACCES` before the
//! handshake, `EINVAL` for a malformed request, `EIO` otherwise).

use std::sync::Arc;

use crate::anchor::ExportTable;
use crate::proto::Channel;

/// One connection being served.
pub struct Server {
    channel: Arc<Channel>,
    exports: Arc<ExportTable>,
    token: Option<String>,
}

impl Server {
    /// A server for one connection; requests are refused until a `HELLO` presents `token`
    /// (none needed when `token` is `None`).
    pub fn new(channel: Arc<Channel>, exports: Arc<ExportTable>, token: Option<String>) -> Server {
        Server {
            channel,
            exports,
            token,
        }
    }

    /// Serves until the client goes, then shuts down every sink, killing what they started.
    pub fn run(self) {
        todo!("unit 1")
    }
}
