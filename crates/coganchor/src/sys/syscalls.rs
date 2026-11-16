//! Syscall numbers and the facts about an architecture the tracers need. [Unit 6]

/// What differs between architectures, written down once.
#[derive(Debug)]
pub struct Arch {
    /// `AUDIT_ARCH_*` as seccomp sees it.
    pub audit: u32,
    /// Bytes below the stack pointer the ABI lets a leaf function use (128 on x86-64).
    pub red_zone: u64,
    /// `O_DIRECTORY`, which aarch64 spells differently.
    pub o_directory: i32,
    /// Whether a syscall-entry stop already holds `-ENOSYS` in the result register.
    pub entry_plants_enosys: bool,
}

#[cfg(target_arch = "x86_64")]
pub const ARCH: Arch = Arch {
    audit: 0xC000_003E,
    red_zone: 128,
    o_directory: 0o200000,
    entry_plants_enosys: true,
};

#[cfg(target_arch = "aarch64")]
pub const ARCH: Arch = Arch {
    audit: 0xC000_00B7,
    red_zone: 0,
    o_directory: 0o40000,
    entry_plants_enosys: false,
};

#[cfg(not(any(target_arch = "x86_64", target_arch = "aarch64")))]
compile_error!("coganchor's tracers know the register maps of x86-64 and aarch64 only");

/// The number of the syscall `name` on this architecture, `None` where it has none (aarch64
/// has no `open`, `stat`, `readlink`, ...).
pub fn number(name: &str) -> Option<i64> {
    todo!("unit 6")
}

/// The name of syscall `number`, for logs and dispatch.
pub fn name(number: i64) -> Option<&'static str> {
    todo!("unit 6")
}

/// Every syscall the cog's trap filter stops: those naming a path, starting a program, or
/// opening a connection, by name, whether or not this architecture has them.
pub const TRAPPED: &[&str] = &[];
