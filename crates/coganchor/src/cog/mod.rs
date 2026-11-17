//! The cog: beside the agent, on its harness machine. Port of `hmz internal anchor` (not
//! `serve`): `hmz.coganchor.anchor` and everything it runs.
//!
//! Under the default arrangement the agent runs here under [`supervisor`] (Linux only),
//! keeping its credentials, state directory and model connection, while its work is answered
//! from a [`shadow`] mirror of the workspace and every command it starts runs on the target.
//! Under `--native` ([`drive`]) the target's own CLI runs and this side carries its streams.

pub mod config;
pub mod drive;
#[cfg(target_os = "linux")]
pub mod execproxy;
#[cfg(target_os = "linux")]
pub mod handlers;
pub mod homes;
pub mod lending;
pub mod mergers;
pub mod netproxy;
pub mod pathcalls;
pub mod policy;
pub mod router;
pub mod run;
pub mod shadow;
#[cfg(target_os = "linux")]
pub mod standin;
pub mod statepaths;
#[cfg(target_os = "linux")]
pub mod supervisor;
#[cfg(target_os = "linux")]
pub mod walls;

use crate::cli::CogArgs;

/// `coganchor cog`: run the agent, returning its status.
pub fn main(args: CogArgs) -> i32 {
    run::main(args)
}
