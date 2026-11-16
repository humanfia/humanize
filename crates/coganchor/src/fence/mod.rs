//! Fences: holding a program to the paths and hosts its flow permits. Port of
//! `hmz.coganchor.fence` and `hmz internal fence`.
//!
//! [`policy::Fence`] is what a fence is, as JSON. On Linux it is put up with Landlock, a
//! socket filter and a `bind`/`listen` user-notification filter answered from outside
//! ([`landlock`], [`netfilter`], [`loopback`]); on a Mac with Seatbelt ([`seatbelt`]). Where the
//! network is cut, [`proxy`] is the one way out, passing only the hosts the fence names.
//! [`abroad`] draws a fence again on the target for a command a fenced agent runs there.

pub mod abroad;
#[cfg(target_os = "linux")]
pub mod landlock;
#[cfg(target_os = "linux")]
pub mod loopback;
#[cfg(target_os = "linux")]
pub mod netfilter;
pub mod policy;
pub mod proxy;
pub mod seatbelt;
pub mod wrap;

pub use policy::Fence;

use crate::cli::FenceArgs;

/// What this machine can hold around a command, as a `HELLO` reply's `fence` says it.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Able {
    /// Paths: Landlock ABI 1 or Seatbelt.
    pub fs: bool,
    /// The network as well: Landlock ABI 4, the socket filter and loopback supervision, or
    /// Seatbelt.
    pub net: bool,
}

/// What this machine can fence, asked once.
pub fn able() -> Able {
    #[cfg(target_os = "linux")]
    {
        landlock::able()
    }
    #[cfg(target_os = "macos")]
    {
        seatbelt::able()
    }
}

/// `coganchor internal fence`: run a program inside a fence and exit with its status.
pub fn main(args: FenceArgs) -> i32 {
    wrap::main(args)
}
