//! Which files belong to the agent rather than to the project. Port of
//! `hmz.coganchor.statepaths`. [Unit 8]

use std::ffi::OsString;
use std::io;
use std::path::PathBuf;

/// The agent, found, with what of this machine it needs to keep.
#[derive(Clone, Debug)]
pub struct Resolved {
    /// The real path of the program to execute.
    pub program: PathBuf,
    /// Its argv, `argv[0]` as found on `PATH`.
    pub argv: Vec<OsString>,
    /// Its state and runtime directories, which stay here.
    pub state: Vec<String>,
    /// Programs of its own (interpreter, vendored binaries), which run here.
    pub programs: Vec<String>,
}

/// Finds `argv[0]` on `PATH` and what it keeps; `"X: not found on PATH"` otherwise.
pub fn resolve(argv: &[OsString]) -> io::Result<Resolved> {
    todo!("unit 8")
}
