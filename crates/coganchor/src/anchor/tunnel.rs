//! TCP tunnels opened for a client. Port of the tunnel half of
//! `hmz.coganchor.serve.sessions`. [Unit 2]
//!
//! `CONNECT {host, port}` connects from this machine (30 s timeout, every address tried),
//! relays the client's `CHUNK`s out and the socket's bytes back as `CHUNK`s on `Data`, shuts
//! the socket's writing half on the client's `END`, and closes with `RSP {}` when the remote
//! side ends.

use std::sync::Arc;

use crate::anchor::{Outbox, Sink};
use crate::proto::{Meta, RemoteError};

/// Opens the tunnel `request` asks for, as exchange `id`.
pub fn connect(
    id: u64,
    request: &Meta,
    outbox: Arc<dyn Outbox>,
) -> Result<Box<dyn Sink>, RemoteError> {
    todo!("unit 2")
}
