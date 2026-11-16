//! `coganchor anchor`: the three ways a session reaches this machine. Port of the `serve`
//! half of `hmz.cli.anchor` and of `hmz.coganchor.serve.listener`. [Unit 1]
//!
//! `--stdio` serves one session on standard input and output (which are then pointed at
//! `/dev/null`); `--listen` serves many, writing `hmz internal anchor serve listening HOST
//! PORT` to standard error once bound, and refusing a non-loopback address without a token;
//! `--peer` meets one through a broker ([`crate::broker::dial`]).

use crate::cli::AnchorArgs;

/// Runs `coganchor anchor`, returning its exit status.
pub fn main(args: AnchorArgs) -> i32 {
    todo!("unit 1")
}
