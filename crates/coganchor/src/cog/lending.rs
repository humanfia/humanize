//! A sign-in that refreshes itself, held by one machine's turns at a time. Port of
//! `hmz.coganchor._lending` (the Python module stays for its other callers; the lock must
//! interoperate with it). [Unit 12]
//!
//! `flock` on the directory of each credential file holding a refresh token: shared for turns
//! here, exclusive for the one copy lent away; never waited for (`EBUSY` instead).

use std::io;
use std::path::PathBuf;

/// The locks held for a session; released when dropped.
pub struct Lent {
    held: Vec<std::fs::File>,
}

/// Takes the locks for `files` that hold refresh tokens: exclusive where `away`.
pub fn lent(files: &[PathBuf], away: bool) -> io::Result<Lent> {
    todo!("unit 12")
}
