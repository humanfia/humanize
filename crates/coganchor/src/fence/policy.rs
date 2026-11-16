//! A fence, as the JSON `hmz` hands it over. Port of `Fence` in `hmz.coganchor.fence`.
//! [Unit 4]

use std::io;
use std::os::fd::OwnedFd;

use serde::{Deserialize, Serialize};

/// The whole of what a program's process tree may still reach. Serialised with these keys in
/// this order, unknown keys refused, exactly as `dataclasses.asdict(Fence)`.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Fence {
    pub read: Vec<String>,
    pub write: Vec<String>,
    pub online: bool,
    pub hosts: Vec<String>,
    pub tmp: String,
    pub scopes: Vec<String>,
    pub listen: Vec<u16>,
}

impl Fence {
    /// Reads a fence from JSON, or from the file `@PATH` names.
    pub fn loads(said: &str) -> Result<Fence, String> {
        todo!("unit 4")
    }

    /// The fence as JSON.
    pub fn dumps(&self) -> String {
        serde_json::to_string(self).expect("a fence always serialises")
    }

    /// Opens every directory the fence lets be written, and its tmp, as `O_PATH` descriptors,
    /// refusing a symbolic link where a fenced program could have made one (`reach`).
    pub fn ready(&self) -> io::Result<Vec<OwnedFd>> {
        todo!("unit 4")
    }
}
