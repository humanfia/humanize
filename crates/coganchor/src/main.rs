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
        Mode::Internal(Internal::Able(args)) => {
            println!("{}", coganchor::fence::said(args.policy.as_deref()));
            0
        }
    };
    std::process::exit(status);
}

#[cfg(target_os = "linux")]
fn cred(args: coganchor::cli::CredArgs) -> i32 {
    coganchor::cred::main(args)
}

#[cfg(not(target_os = "linux"))]
fn cred(args: coganchor::cli::CredArgs) -> i32 {
    // No tracer here: the line is still read as on Linux, so a malformed one is a usage error,
    // and a well-formed one is refused rather than run with the wrong account's credentials.
    const USAGE: &str = "usage: hmz internal cred [-h] [--map FROM=TO] [--keep FROM=TO] ...";
    let usage = |why: &str| {
        eprintln!("{USAGE}\nhmz internal cred: error: {why}");
        coganchor::exit::USAGE
    };
    let command = match args.command.split_first() {
        Some((first, rest)) if first == "--" => rest,
        _ => &args.command[..],
    };
    if command.is_empty() {
        return usage("no program given; try `hmz internal cred --map FROM=TO -- claude`");
    }
    for one in args.maps.iter().chain(&args.keeps) {
        match one.split_once('=') {
            Some((named, instead)) if named.starts_with('/') && instead.starts_with('/') => {}
            _ => return usage(&format!("'{one}' is not FROM=TO, of two absolute paths")),
        }
    }
    if args.maps.is_empty() && args.keeps.is_empty() {
        return usage("nothing to answer with anything: give at least one --map or --keep");
    }
    eprintln!("hmz internal cred: nothing could supervise it: the tracer needs Linux");
    coganchor::exit::FAILED
}
