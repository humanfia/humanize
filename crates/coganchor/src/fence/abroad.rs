//! A fence drawn again on the target, around a command a fenced agent runs there. Port of
//! `hmz.coganchor.fence.abroad` and `hmz.coganchor.serve.fencing`. [Unit 4]

use std::ffi::OsString;

use serde_json::Value;

use crate::anchor::ExportTable;
use crate::proto::RemoteError;

/// The command line running `argv` (or `program`, where it is on this machine) inside the
/// fence the `EXEC` request's `fence` levels draw around this machine's own paths: the
/// exports, this user's home, this machine's minimum. `EPERM` where this machine cannot hold
/// it; `EIO` where the levels are malformed.
pub fn fenced(
    argv: &[OsString],
    program: Option<&OsString>,
    said: &Value,
    exports: &ExportTable,
) -> Result<Vec<OsString>, RemoteError> {
    todo!("unit 4")
}
