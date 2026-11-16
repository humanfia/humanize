//! How a command is run on a target. Port of `Road` in `hmz.coganchor.transport`. [Unit 7]
//!
//! `ssh` (with connection reuse under a private control directory), `docker exec -i` (with the
//! endpoint, user, variables and wrapper words the target names), `container exec -i`, and an
//! `srun` step sharing a Slurm job's allocation; `local` has no prefix.

use std::ffi::OsString;

use crate::transport::Target;

/// The road to one target.
#[derive(Clone, Debug)]
pub struct Road {
    pub target: Target,
}

impl Road {
    /// The road to `target`.
    pub fn to(target: &Target) -> Road {
        Road {
            target: target.clone(),
        }
    }

    /// The full command line that runs `argv` on the target.
    pub fn line(&self, argv: &[OsString]) -> Vec<OsString> {
        todo!("unit 7")
    }

    /// The directory coganchor keeps its binaries in on the target (protocol/files.md 9.2.3).
    pub fn cache(&self) -> String {
        todo!("unit 7")
    }

    /// The directory mirrors are kept in on the target (protocol/files.md 9.2.4).
    pub fn mirrors(&self) -> String {
        todo!("unit 7")
    }
}
