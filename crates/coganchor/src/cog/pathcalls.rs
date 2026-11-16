//! The syscalls that name a path, and where each keeps them. Port of
//! `hmz.coganchor.pathcalls`. [Unit 8]

/// Where one path argument of a call is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PathArg {
    /// The argument holding the path.
    pub path: usize,
    /// The argument holding the directory descriptor it is relative to, if the call has one.
    pub dirfd: Option<usize>,
}

/// One call that names paths.
#[derive(Clone, Copy, Debug)]
pub struct PathCall {
    pub name: &'static str,
    pub args: &'static [PathArg],
    /// Only looks a path up (stat, access, readlink, ...).
    pub looks: bool,
    /// Makes something at the path (creat, mkdir, symlink, ...).
    pub makes: bool,
}

/// Every call that names a path, by name, whether or not this architecture has it.
pub fn table() -> &'static [PathCall] {
    todo!("unit 8")
}

/// The entry for `name`.
pub fn find(name: &str) -> Option<&'static PathCall> {
    table().iter().find(|call| call.name == name)
}
