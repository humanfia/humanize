//! `coganchor internal cred`: running a CLI with the paths it keeps its credentials at
//! answered from an account's directory. Port of `hmz.coganchor.providers.{_trace,_staging}`
//! and the tracer of `hmz.coganchor.providers.redirect`. [Unit 15]
//!
//! The tracer stands outside the program's tree (double fork, `setsid`, `PTRACE_SEIZE`), the
//! program installs the trap filter on itself, and matched paths are rewritten in place;
//! read-only lookups are answered from a `/dev/shm` copy.

pub mod staging;
pub mod tracer;

use crate::cli::CredArgs;

/// Runs `coganchor internal cred`, returning the program's status.
pub fn main(args: CredArgs) -> i32 {
    tracer::main(args)
}

/// Whether this machine lets the tracer run (probed once by running `true` under it).
pub fn supervises() -> bool {
    tracer::supervises()
}
