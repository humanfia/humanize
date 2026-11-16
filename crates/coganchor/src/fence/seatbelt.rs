//! Seatbelt: macOS's sandbox. Port of `hmz.coganchor.darwin.seatbelt` and the macOS branch
//! of `hmz.coganchor.fence.wrap`. [Unit 5]
//!
//! The profile is built on every platform (so it can be tested anywhere); only a Mac runs it.

use std::ffi::OsString;

use crate::fence::{Able, Fence};

/// The profile text and its `-D` parameters for `fence`, with the loopback proxy `port` the
/// one outbound connection allowed where the network is cut.
pub fn profile(fence: &Fence, port: Option<u16>) -> (String, Vec<(String, String)>) {
    todo!("unit 5")
}

/// The `/usr/bin/sandbox-exec` command line running `argv` inside `fence`.
pub fn command(fence: &Fence, port: Option<u16>, argv: &[OsString]) -> Vec<OsString> {
    todo!("unit 5")
}

/// Whether `sandbox-exec` works here, asked once.
pub fn able() -> Able {
    todo!("unit 5")
}
