//! coganchor: running a coding agent on one machine and having it act on another.
//!
//! One program, three places. [`cog`] runs beside the agent on its harness machine: a
//! seccomp-filtered ptrace supervisor intercepts the cold syscalls that name a path, start a
//! program or open a socket, answers them from a mirror of the workspace, and sends what must
//! happen on the target there. [`anchor`] runs on the machine the work lands on and carries
//! those requests out. [`broker`] introduces the two when neither can dial the other. They
//! speak [`proto`], the same wire `hmz.coganchor.proto` speaks, over a pipe as it is and over a
//! network inside [`tls`].
//!
//! Linux-only parts (ptrace, seccomp, Landlock) are compiled only for Linux; the anchor and
//! the broker build for macOS as well.

pub mod anchor;
pub mod broker;
pub mod cli;
pub mod client;
pub mod cog;
#[cfg(target_os = "linux")]
pub mod cred;
pub mod exit;
pub mod fence;
pub mod log;
pub mod proto;
#[cfg(target_os = "linux")]
pub mod sys;
pub mod tls;
pub mod transport;
