//! What the supervisor does with each trapped syscall. Port of `hmz.coganchor.handlers`.
//! [Unit 10]

/// What becomes of one stopped syscall.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    /// Let it run as (possibly rewritten) now.
    Allow,
    /// Cancel it, returning `-errno`.
    Fail(i32),
    /// Leave the tracee stopped: a remote command is standing in for it.
    Stall,
}
