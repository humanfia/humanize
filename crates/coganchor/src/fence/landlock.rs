//! Landlock: the paths and TCP ports a process tree may use. Port of
//! `hmz.coganchor.linux.landlock`. [Unit 4]

use std::io;
use std::os::fd::OwnedFd;
use std::path::PathBuf;

use crate::fence::Able;

/// The ABI version this kernel speaks, 0 where it has no Landlock.
pub fn abi() -> u32 {
    todo!("unit 4")
}

/// What this machine can fence: ABI 1 for paths; ABI 4, the socket filter and loopback
/// supervision for the network too.
pub fn able() -> Able {
    todo!("unit 4")
}

/// A ruleset to restrict the calling thread, and everything it later starts, to.
#[derive(Debug, Default)]
pub struct Ruleset {
    /// Paths that may be read and executed.
    pub read: Vec<PathBuf>,
    /// Directories (opened `O_PATH`) that may also be written.
    pub write: Vec<OwnedFd>,
    /// TCP ports that may be connected to, where `net` governs the network.
    pub connect_ports: Vec<u16>,
    /// TCP ports that may be bound (0 for any ephemeral one), where `net` governs it.
    pub bind_ports: Vec<u16>,
    /// Whether to govern TCP at all.
    pub net: bool,
}

impl Ruleset {
    /// Applies the ruleset to the calling thread, after setting `no_new_privs`. Call in a
    /// freshly forked child just before `execve`.
    pub fn restrict_self(&self) -> io::Result<()> {
        todo!("unit 4")
    }
}
