//! `--native`: the CLI installed on the target runs, and this side carries its streams. Port
//! of `drive` and its helpers in `hmz.coganchor.anchor` (lines 885-1692). [Unit 13]

use std::ffi::OsString;

use crate::cog::config::AnchorConfig;

/// Runs `command` natively on the target, returning its status (127 where it is not installed
/// there).
pub fn drive(config: &AnchorConfig, command: &[OsString]) -> anyhow::Result<i32> {
    todo!("unit 13")
}
