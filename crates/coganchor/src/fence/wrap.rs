//! `coganchor internal fence`: running a program inside a fence and waiting for it. Port of
//! `hmz.coganchor.fence.wrap`. [Unit 4; the macOS branch calls [`crate::fence::seatbelt`]]
//!
//! Exits 126 (`hmz internal fence: <why>`) where the fence cannot be put up, 127 where the
//! program cannot be run, and otherwise with the program's own status.

use std::ffi::OsString;

use crate::cli::FenceArgs;
use crate::fence::Fence;

/// Runs `coganchor internal fence`.
pub fn main(args: FenceArgs) -> i32 {
    todo!("unit 4")
}

/// The command line that runs `argv` inside `fence`: this binary's own `internal fence`.
pub fn command(fence: &Fence, argv: &[OsString]) -> Vec<OsString> {
    let mut line: Vec<OsString> = vec![
        std::env::current_exe().map_or_else(|_| "coganchor".into(), OsString::from),
        "internal".into(),
        "fence".into(),
        format!("--policy={}", fence.dumps()).into(),
        "--".into(),
    ];
    line.extend(argv.iter().cloned());
    line
}
