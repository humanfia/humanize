//! The trap filter: which syscalls stop for the tracer. Port of `build_program` and `install`
//! of `hmz.coganchor.linux.seccomp`. [Unit 6]
//!
//! `SECCOMP_RET_TRACE` for the cold syscalls named, `SECCOMP_RET_ALLOW` for everything else
//! (and for a foreign architecture), so hot syscalls never pay a ptrace stop.
//!
//! Hand-assembled rather than built with `seccompiler`, whose actions stop short of
//! `RET_TRACE` with no data; the program is a flat run of compares, four instructions and two
//! per number.

use std::io;

const LD_W_ABS: u16 = (libc::BPF_LD | libc::BPF_W | libc::BPF_ABS) as u16;
const JMP_JEQ_K: u16 = (libc::BPF_JMP | libc::BPF_JEQ | libc::BPF_K) as u16;
const RET_K: u16 = (libc::BPF_RET | libc::BPF_K) as u16;
#[cfg(target_arch = "x86_64")]
const JMP_JGE_K: u16 = (libc::BPF_JMP | libc::BPF_JGE | libc::BPF_K) as u16;
/// x32's syscalls on x86-64: the same numbers with this bit set, under the same audit arch.
#[cfg(target_arch = "x86_64")]
const X32_SYSCALL_BIT: u32 = 0x4000_0000;

/// Offsets into `struct seccomp_data`.
const OFFSET_NR: u32 = 0;
const OFFSET_ARCH: u32 = 4;

const RET_ALLOW: u32 = libc::SECCOMP_RET_ALLOW;
const RET_TRACE: u32 = libc::SECCOMP_RET_TRACE;

/// The ceiling `build_program` holds a flat filter to (`_MAX_JUMP`, one conditional jump's
/// reach). Every jump here is 0 or 1, so it is conservative; kept so the two refuse alike.
const MAX_JUMP: usize = 255;

fn insn(code: u16, jt: u8, jf: u8, k: u32) -> libc::sock_filter {
    libc::sock_filter { code, jt, jf, k }
}

/// Assembles the program that traps `numbers` (`build_program`).
///
/// A foreign architecture -- a 32-bit entry point -- is let through untouched: the cog is a
/// redirector, not a sandbox, so failing open keeps an unexpected personality working rather
/// than killing the agent. A number below zero, which no process can make, is dropped, and
/// the rest are sorted and deduplicated.
///
/// Fails with `E2BIG` if the set is too large for a flat filter to jump over.
pub fn build(numbers: &[i64]) -> io::Result<Vec<libc::sock_filter>> {
    let mut ordered: Vec<u32> = numbers
        .iter()
        .filter_map(|&n| u32::try_from(n).ok())
        .collect();
    ordered.sort_unstable();
    ordered.dedup();
    if ordered.len() * 2 + 6 > MAX_JUMP {
        return Err(io::Error::from_raw_os_error(libc::E2BIG));
    }
    let mut program = vec![
        insn(LD_W_ABS, 0, 0, OFFSET_ARCH),
        insn(JMP_JEQ_K, 1, 0, super::ARCH.audit),
        insn(RET_K, 0, 0, RET_ALLOW),
        insn(LD_W_ABS, 0, 0, OFFSET_NR),
    ];
    // An x32 call is the x86-64 one with a bit set, under the same audit arch, and none of
    // them would match a number below: let through, it would name a path nobody answered.
    // Refused instead, as `ENOSYS`, which is what a kernel without x32 says of them anyway.
    #[cfg(target_arch = "x86_64")]
    program.extend([
        insn(JMP_JGE_K, 0, 1, X32_SYSCALL_BIT),
        insn(RET_K, 0, 0, libc::SECCOMP_RET_ERRNO | libc::ENOSYS as u32),
    ]);
    for number in ordered {
        program.push(insn(JMP_JEQ_K, 0, 1, number));
        program.push(insn(RET_K, 0, 0, RET_TRACE));
    }
    program.push(insn(RET_K, 0, 0, RET_ALLOW));
    Ok(program)
}

/// Installs an assembled `program` on the calling thread after setting `no_new_privs`, which
/// a filter needs without `CAP_SYS_ADMIN` (and which keeps set-uid programs below the agent
/// from gaining privileges, the right posture for a redirected session). Allocates nothing,
/// so it is safe between `fork` and `execve` in a threaded parent.
pub fn load(program: &[libc::sock_filter]) -> io::Result<()> {
    // SAFETY: plain prctl with integer arguments.
    if unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // The kernel's own ceiling, checked here so that a longer program is refused rather than
    // installed cut down to what a `c_ushort` length holds.
    if program.is_empty() || program.len() > libc::BPF_MAXINSNS as usize {
        return Err(io::Error::from_raw_os_error(libc::EINVAL));
    }
    let fprog = libc::sock_fprog {
        len: program.len() as libc::c_ushort,
        filter: program.as_ptr().cast_mut(),
    };
    // SAFETY: `fprog` points at `program`, which outlives the call; the kernel copies it.
    let done = unsafe {
        libc::syscall(
            libc::SYS_seccomp,
            libc::SECCOMP_SET_MODE_FILTER,
            0 as libc::c_uint,
            &raw const fprog,
        )
    };
    if done < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

/// Installs, on the calling thread, a filter stopping exactly `numbers` for the tracer, after
/// setting `no_new_privs`. Call in a freshly forked child just before `execve`; a parent with
/// other threads should [`build`] before forking and [`load`] in the child instead.
pub fn install(numbers: &[i64]) -> io::Result<()> {
    load(&build(numbers)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The instructions every program has besides the two per number: the architecture check,
    /// its allow and the load of the number, the final allow, and on x86-64 the x32 refusal.
    const AROUND: usize = if cfg!(target_arch = "x86_64") { 7 } else { 5 };

    /// Runs `program` over one `seccomp_data` the way the kernel would, for the instructions
    /// this module emits.
    fn run(program: &[libc::sock_filter], nr: u32, arch: u32) -> u32 {
        let mut acc = 0u32;
        let mut pc = 0usize;
        loop {
            let i = program[pc];
            match i.code {
                LD_W_ABS => acc = if i.k == OFFSET_NR { nr } else { arch },
                JMP_JEQ_K => {
                    pc += usize::from(if acc == i.k { i.jt } else { i.jf });
                }
                #[cfg(target_arch = "x86_64")]
                JMP_JGE_K => {
                    pc += usize::from(if acc >= i.k { i.jt } else { i.jf });
                }
                RET_K => return i.k,
                code => panic!("unexpected instruction {code:#x}"),
            }
            pc += 1;
        }
    }

    #[test]
    fn the_trap_filter_traps_what_it_is_given_and_nothing_else() {
        let program = build(&[59, 257, 2, 257]).unwrap();
        let audit = super::super::ARCH.audit;
        for nr in [2, 59, 257] {
            assert_eq!(run(&program, nr, audit), RET_TRACE);
        }
        for nr in [0, 1, 3, 58, 60, 256, 258, 1000] {
            assert_eq!(run(&program, nr, audit), RET_ALLOW);
        }
    }

    #[test]
    fn the_trap_filter_lets_a_foreign_architecture_through() {
        let program = build(&[59]).unwrap();
        assert_eq!(run(&program, 59, 0x4000_0003), RET_ALLOW);
    }

    #[test]
    fn the_whole_trap_set_fits() {
        let numbers = crate::sys::syscalls::trapped();
        let program = build(&numbers).unwrap();
        assert_eq!(program.len(), numbers.len() * 2 + AROUND);
    }

    #[test]
    fn an_empty_trap_set_traps_nothing_and_negatives_are_dropped() {
        let program = build(&[-1, -1000]).unwrap();
        assert_eq!(program.len(), AROUND);
        assert_eq!(run(&program, 1000, super::super::ARCH.audit), RET_ALLOW);
    }

    #[cfg(target_arch = "x86_64")]
    #[test]
    fn an_x32_call_is_refused_rather_than_let_through_untrapped() {
        let program = build(&[2]).unwrap();
        let refused = libc::SECCOMP_RET_ERRNO | libc::ENOSYS as u32;
        assert_eq!(
            run(&program, X32_SYSCALL_BIT | 2, super::super::ARCH.audit),
            refused
        );
        assert_eq!(run(&program, 2, super::super::ARCH.audit), RET_TRACE);
    }

    #[test]
    fn a_trap_set_too_large_to_jump_over_is_refused() {
        let numbers: Vec<i64> = (0..200).collect();
        assert_eq!(
            build(&numbers).unwrap_err().raw_os_error(),
            Some(libc::E2BIG)
        );
    }
}
