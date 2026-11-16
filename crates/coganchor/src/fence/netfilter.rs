//! The seccomp filters that finish cutting the network: one refusing every socket but Unix,
//! netlink and TCP, and one stopping `bind` and `listen` for a supervisor outside to decide.
//! Port of the socket and listen filters of `hmz.coganchor.linux.seccomp`. [Unit 4]

use std::io;
use std::os::fd::OwnedFd;

/// Installs the socket filter on the calling thread.
pub fn install_socket_filter() -> io::Result<()> {
    todo!("unit 4")
}

/// Installs the `bind`/`listen` user-notification filter, returning its listener descriptor.
/// `EBUSY` means the caller is already inside a fence that cuts the network.
pub fn install_listener() -> io::Result<OwnedFd> {
    todo!("unit 4")
}

/// Whether this kernel has user notifications of the sizes this build was written against.
pub fn notifiable() -> bool {
    todo!("unit 4")
}
