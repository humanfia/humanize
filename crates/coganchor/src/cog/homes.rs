//! A CLI's virtual home: a directory standing in for `$HOME` for one session. Port of
//! `hmz.coganchor.homes` (build, drop, records) and the mergers it calls by name. [Unit 14]

use std::ffi::OsString;
use std::io;
use std::path::{Path, PathBuf};

use serde_json::Value;

/// A virtual home as `hmz` describes it (`Virtual.dumps`), kept as JSON until built.
#[derive(Clone, Debug, PartialEq)]
pub struct Virtual {
    pub raw: Value,
}

impl Virtual {
    /// Reads `--home JSON`.
    pub fn loads(said: &str) -> Result<Virtual, String> {
        todo!("unit 14")
    }
}

/// A virtual home built on this machine.
pub struct Home {
    dir: PathBuf,
}

/// Builds `virtual_home` under this machine's temporary directory.
pub fn build(virtual_home: &Virtual) -> io::Result<Home> {
    todo!("unit 14")
}

impl Home {
    /// Its directory.
    pub fn dir(&self) -> &Path {
        &self.dir
    }

    /// The variables pointing the CLI at it.
    pub fn environ(&self) -> Vec<(OsString, OsString)> {
        todo!("unit 14")
    }

    /// Arguments to put after the program's name.
    pub fn argv(&self) -> Vec<OsString> {
        todo!("unit 14")
    }

    /// Writes back what the session changed, respells its records, and removes the directory.
    pub fn drop_home(self) -> io::Result<()> {
        todo!("unit 14")
    }
}
