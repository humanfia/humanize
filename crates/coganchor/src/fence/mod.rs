//! Fences: holding a program to the paths and hosts its flow permits. Port of
//! `hmz.coganchor.fence` and `hmz internal fence`.
//!
//! [`policy::Fence`] is what a fence is, as JSON. On Linux it is put up with one of two
//! backends, which `--sandbox` chooses between ([`backend`]): Landlock, a socket filter and a
//! `bind`/`listen` user-notification filter answered from outside ([`landlock`], [`netfilter`],
//! [`loopback`]); or bubblewrap, where Landlock cannot hold it ([`bubblewrap`], [`relay`]). On a
//! Mac it is Seatbelt ([`seatbelt`]). Where the network is cut, [`proxy`] is the one way out,
//! passing only the hosts the fence names.
//! [`abroad`] draws a fence again on the target for a command a fenced agent runs there.

pub mod abroad;
pub mod bubblewrap;
#[cfg(target_os = "linux")]
pub mod landlock;
#[cfg(target_os = "linux")]
pub mod loopback;
#[cfg(target_os = "linux")]
pub mod netfilter;
pub mod policy;
pub mod proxy;
pub mod relay;
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

/// What `--sandbox` asks a fence to be put up with on Linux, as `sandbox.backend` in the
/// settings of the machine hmz runs on says it: Landlock where it can hold the fence and
/// bubblewrap otherwise, or one of them alone. A machine nobody told chooses for itself.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Sandbox {
    #[default]
    Auto,
    Landlock,
    Bwrap,
}

impl Sandbox {
    /// As `sandbox.backend` is read: `landlock` or `bwrap`, and anything else `auto`.
    pub fn of(said: Option<&str>) -> Sandbox {
        match said {
            Some("landlock") => Sandbox::Landlock,
            Some("bwrap") => Sandbox::Bwrap,
            _ => Sandbox::Auto,
        }
    }
}

/// What puts a fence up here.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Backend {
    Landlock,
    Bwrap,
    Seatbelt,
}

impl Backend {
    /// The name it is written by, as a report says it.
    pub fn name(self) -> &'static str {
        match self {
            Backend::Landlock => "landlock",
            Backend::Bwrap => "bwrap",
            Backend::Seatbelt => "seatbelt",
        }
    }
}

/// What puts a fence up on this machine (one cutting the network too, where `net`), as
/// `asked` chooses; `None` where nothing can. Never one that was not asked for in place of one
/// that was: a machine pinned to a backend is refused rather than held some other way.
pub fn backend(net: bool, asked: Sandbox) -> Option<Backend> {
    #[cfg(target_os = "linux")]
    {
        let landlocked = || {
            let able = landlock::able();
            if net { able.net } else { able.fs }
        };
        if asked != Sandbox::Bwrap && landlocked() {
            return Some(Backend::Landlock);
        }
        if asked != Sandbox::Landlock && bubblewrap::available(net) {
            return Some(Backend::Bwrap);
        }
        None
    }
    #[cfg(target_os = "macos")]
    {
        let _ = asked;
        let able = seatbelt::able();
        (if net { able.net } else { able.fs }).then_some(Backend::Seatbelt)
    }
}

/// What this machine can fence, as `asked` chooses.
pub fn able_with(asked: Sandbox) -> Able {
    Able {
        fs: backend(false, asked).is_some(),
        net: backend(true, asked).is_some(),
    }
}

/// What this machine can fence, choosing for itself: what a `HELLO` reply says of it.
pub fn able() -> Able {
    able_with(Sandbox::Auto)
}

/// What `coganchor internal able` says: what this machine can fence, as `asked` chooses, as
/// `{"fs": bool, "net": bool}`; and where a `policy` is given, as `"unheld"`, why the backend
/// that would put it up cannot hold what it carves out of its grants -- Landlock, which grants
/// what is around a carve-out instead ([`wrap::expanded`]), or bubblewrap, which mounts over
/// one and so needs it there ([`bubblewrap::carves`]) -- or null where it can. A Mac carves out
/// of a grant with Seatbelt itself, and holds every carve-out.
pub fn said(policy: Option<&str>, asked: Sandbox) -> serde_json::Value {
    let able = able_with(asked);
    let mut said = serde_json::json!({"fs": able.fs, "net": able.net});
    said["backend"] = serde_json::json!({
        "fs": backend(false, asked).map(Backend::name),
        "net": backend(true, asked).map(Backend::name),
    });
    #[cfg(target_os = "linux")]
    {
        said["landlock"] = serde_json::json!({
            "abi": landlock::abi(),
            "network": landlock::available(true),
            "scope": landlock::scopes_sockets(),
        });
        said["seccomp"] = serde_json::json!({"notify": netfilter::notifiable()});
        said["loopback"] = serde_json::json!({
            "pidfd_getfd": loopback::pidfd_getfd(),
            "ptrace_scope": loopback::ptrace_scope(),
        });
        said["bubblewrap"] = serde_json::json!({
            "fs": bubblewrap::available(false),
            "net": bubblewrap::available(true),
        });
    }
    #[cfg(target_os = "macos")]
    {
        let told = seatbelt::able();
        said["seatbelt"] = serde_json::json!({"fs": told.fs, "net": told.net});
    }
    if let Some(policy) = policy {
        let unheld = match Fence::loads(policy) {
            Err(why) => Some(why),
            Ok(_) if cfg!(target_os = "macos") => None,
            Ok(fence) if backend(!fence.online, asked) == Some(Backend::Bwrap) => {
                bubblewrap::carves(&fence)
                    .err()
                    .map(|why| policy::spelled(&why))
            }
            Ok(fence) => wrap::expanded(&fence)
                .err()
                .map(|why| policy::spelled(&why)),
        };
        said["unheld"] = serde_json::Value::from(unheld);
    }
    said
}

/// `coganchor internal fence`: run a program inside a fence and exit with its status.
pub fn main(args: FenceArgs) -> i32 {
    wrap::main(args)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn said_reports_the_probes_it_answers_with() {
        let told = said(None, Sandbox::Auto);
        let able = able_with(Sandbox::Auto);
        assert_eq!(told["fs"], serde_json::json!(able.fs));
        assert_eq!(told["net"], serde_json::json!(able.net));
        assert!(told.get("unheld").is_none());
        #[cfg(target_os = "linux")]
        {
            assert_eq!(told["landlock"]["abi"], serde_json::json!(landlock::abi()));
            assert_eq!(
                told["landlock"]["network"],
                serde_json::json!(landlock::available(true))
            );
            assert_eq!(
                told["landlock"]["scope"],
                serde_json::json!(landlock::scopes_sockets())
            );
            assert_eq!(
                told["seccomp"]["notify"],
                serde_json::json!(netfilter::notifiable())
            );
            assert_eq!(
                told["loopback"]["pidfd_getfd"],
                serde_json::json!(loopback::pidfd_getfd())
            );
            assert_eq!(
                told["loopback"]["ptrace_scope"],
                serde_json::json!(loopback::ptrace_scope())
            );
            assert_eq!(
                told["bubblewrap"]["fs"],
                serde_json::json!(bubblewrap::available(false))
            );
            assert!(told["backend"]["fs"].is_string() || told["backend"]["fs"].is_null());
        }
        #[cfg(target_os = "macos")]
        {
            assert!(told["seatbelt"].is_object());
        }
    }
}
