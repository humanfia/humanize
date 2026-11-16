//! Answering a fenced tree's `bind` and `listen` from outside it: loopback only. Port of
//! `hmz.coganchor.fence.loopback`. [Unit 4]

use std::os::fd::OwnedFd;
use std::thread::JoinHandle;

/// Answers the notifications arriving on `listener` from a thread of its own until the fenced
/// tree is gone.
pub fn supervise(listener: OwnedFd) -> JoinHandle<()> {
    todo!("unit 4")
}

/// Whether this machine lets a supervisor take a tracee's descriptor (`ptrace_scope` < 2 and a
/// working `pidfd_getfd`).
pub fn supervisable() -> bool {
    todo!("unit 4")
}
