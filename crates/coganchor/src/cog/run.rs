//! Running a cog session end to end. Port of `connect`, `check` and `_supervised` in
//! `hmz.coganchor.anchor`, and the agent half of `hmz.cli.anchor`. [Unit 12]
//!
//! `--check` prints what the target is and exits 0; `--native` hands over to [`drive`];
//! otherwise: build the virtual home, resolve the agent and its state paths, prepare the
//! mirror, connect, and run the agent under the supervisor inside the lent credentials,
//! walled where a fence is asked for. Exit statuses: the agent's own; 1 (`hmz: <reason>`) on a
//! connection, protocol, OS or value error; 127 where the native CLI is missing; 130 on ^C.
//!
//! [`drive`]: crate::cog::drive

use crate::cli::CogArgs;

/// Runs `coganchor cog`.
pub fn main(args: CogArgs) -> i32 {
    todo!("unit 12")
}
