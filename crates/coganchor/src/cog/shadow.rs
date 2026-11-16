//! A lazily materialised mirror of the target's workspace. Port of `hmz.coganchor.shadow`.
//! [Unit 9]
//!
//! Directories and links are real; files are sparse placeholders of the target's size, mode
//! and mtime until first opened for reading. Several turns may share one mirror, each a cog of
//! its own, through the ledger beside the mirror's registry entry (`<base>.journal` and
//! `<base>.live`, `flock`ed), in the line format `hmz.coganchor.shadow._Ledger` writes.

use std::io;
use std::path::Path;
use std::sync::Arc;

use crate::client::RemoteClient;
use crate::cog::router::Router;
use crate::proto::RemoteError;

/// The mirror one turn works in.
pub struct ShadowTree {
    client: Arc<RemoteClient>,
    router: Arc<Router>,
}

impl ShadowTree {
    /// The mirror at `mirror`, joining its ledger.
    pub fn new(
        client: Arc<RemoteClient>,
        router: Arc<Router>,
        mirror: &Path,
    ) -> io::Result<ShadowTree> {
        todo!("unit 9")
    }

    /// Makes the directories leading to `local` exist, listed from the target.
    pub fn ensure_path(&self, local: &Path) -> Result<(), RemoteError> {
        todo!("unit 9")
    }

    /// Makes `local` a listed directory (removing it here where the target lacks it).
    pub fn ensure_directory(&self, local: &Path) -> Result<(), RemoteError> {
        todo!("unit 9")
    }

    /// Fetches `local`'s content if it is still a placeholder.
    pub fn ensure_content(&self, local: &Path) -> Result<(), RemoteError> {
        todo!("unit 9")
    }

    /// Notes that `local` may be written, so the next flush compares and pushes it.
    pub fn note_write(&self, local: &Path) {
        todo!("unit 9")
    }

    /// Notes that `local` (and everything under it) was removed on the target.
    pub fn note_removed(&self, local: &Path) {
        todo!("unit 9")
    }

    /// Notes that `from` was renamed to `to` on the target.
    pub fn note_renamed(&self, from: &Path, to: &Path) {
        todo!("unit 9")
    }

    /// Pushes every written file whose size or mtime changed.
    pub fn flush(&self) -> Result<(), RemoteError> {
        todo!("unit 9")
    }

    /// Forgets every cached listing (a remote command may have changed anything).
    pub fn invalidate(&self) {
        todo!("unit 9")
    }
}

/// Guards and records a mirror directory: refuses one holding files that was never a mirror,
/// or was one of another target, unless `force` (protocol/core.md 6.6.5).
pub fn prepare_shadow_root(root: &Path, force: bool, target: &str) -> io::Result<()> {
    todo!("unit 9")
}
