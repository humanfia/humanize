//! Putting coganchor on a target. [Unit 7]
//!
//! The target is asked its `uname -sm` once; the binary built for that OS and architecture is
//! found beside this one (`$COGANCHOR_BINARIES/<os>-<arch>/coganchor`, which `hmz` sets to the
//! wheel's `bin/` directory) and piped down the road into `<cache>/coganchor-<digest16>`,
//! written aside and renamed, mode 0700, unless a file of that name is already there; files of
//! that pattern untouched for 14 days are swept.

use std::ffi::OsString;
use std::io;

use crate::transport::Road;

/// Where coganchor is on the target behind `road`, shipping it there first if need be.
pub fn installed(road: &Road) -> io::Result<String> {
    todo!("unit 7")
}

/// The command line running `coganchor <args>` on the target behind `road`.
pub fn command(road: &Road, args: &[OsString]) -> io::Result<Vec<OsString>> {
    todo!("unit 7")
}
