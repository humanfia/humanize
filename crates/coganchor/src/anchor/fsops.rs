//! The filesystem operations, carried out here on real paths. Port of
//! `hmz.coganchor.serve.fsops`. [Unit 1]
//!
//! Each takes a request's metadata, resolves its virtual paths through the [`ExportTable`],
//! and returns the reply's metadata or this machine's exact errno.

use std::sync::Arc;

use crate::anchor::{ExportTable, Outbox, Sink};
use crate::proto::{Meta, Op, RemoteError};

/// Carries out one short operation (everything but `read`, `write`, `exec`, `signal`,
/// `connect` and `hello`), returning the reply's metadata.
pub fn run(op: Op, request: &Meta, exports: &ExportTable) -> Result<Meta, RemoteError> {
    todo!("unit 1")
}

/// `read`: streams the file as `CHUNK`s on `Data`, then replies `{size, mode, mtime_ns}`.
pub fn read(
    id: u64,
    request: &Meta,
    exports: &ExportTable,
    outbox: &dyn Outbox,
) -> Result<(), RemoteError> {
    todo!("unit 1")
}

/// `write`: a sink taking the file's content (the request's body first), replying with the
/// written file's `stat` once the client sends `END`.
pub fn write(
    id: u64,
    request: &Meta,
    body: &[u8],
    exports: &ExportTable,
    outbox: Arc<dyn Outbox>,
) -> Result<Box<dyn Sink>, RemoteError> {
    todo!("unit 1")
}
