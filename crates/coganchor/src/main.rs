//! `coganchor`: the command line, routed to the part of a session it names.

use clap::Parser;
use coganchor::cli::{Cli, Internal, Mode};

fn main() {
    let cli = Cli::parse();
    let status = match cli.mode {
        Mode::Cog(args) => coganchor::cog::main(args),
        Mode::Anchor(args) => coganchor::anchor::main(args),
        Mode::Broker(args) => coganchor::broker::main(args),
        Mode::Internal(Internal::Fence(args)) => coganchor::fence::main(args),
        Mode::Internal(Internal::Cred(args)) => cred(args),
    };
    std::process::exit(status);
}

#[cfg(target_os = "linux")]
fn cred(args: coganchor::cli::CredArgs) -> i32 {
    coganchor::cred::main(args)
}

#[cfg(not(target_os = "linux"))]
fn cred(_: coganchor::cli::CredArgs) -> i32 {
    coganchor::exit::failed("internal cred needs Linux")
}
