//! `coganchor internal fence`: running a program inside a fence and waiting for it. Port of
//! `hmz.coganchor.fence.wrap`. [Unit 4; the macOS branch calls [`crate::fence::seatbelt`]]
//!
//! Exits 126 (`hmz internal fence: <why>`) where the fence cannot be put up, 127 where the
//! program cannot be run, and otherwise with the program's own status.
//!
//! On Linux the program is forked, and the child walls itself in just before `execve`, the
//! only place it can be: where the network is cut, the socket filter and the `bind`/`listen`
//! filter are loaded and the latter's listener handed up to the parent
//! ([`crate::fence::loopback`]); then the Landlock ruleset is applied. A step that fails is a
//! program that does not run, never one that runs with less of the wall than was asked for.
//! The parent stays outside: serving the proxy, answering binds, passing signals on, and --
//! where the network is cut -- reaping every orphan as the subreaper of the tree. On a Mac the
//! child is `sandbox-exec` with the fence's Seatbelt profile.

use std::ffi::{OsStr, OsString};
use std::os::unix::ffi::OsStrExt;
use std::path::Path;
use std::sync::atomic::{AtomicI32, Ordering};

use crate::cli::FenceArgs;
use crate::exit;
use crate::fence::Fence;
use crate::fence::policy::spelled;
use crate::fence::proxy::Proxy;

/// The variables every common HTTP client reads its proxy from, in both spellings.
pub const PROXIES: [&str; 6] = [
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
];

/// The variables that say where a build keeps its caches, each with where it keeps them when
/// nothing is said.
pub const CACHES: [(&str, &str); 5] = [
    ("XDG_CACHE_HOME", "~/.cache"),
    ("UV_CACHE_DIR", "~/.cache/uv"),
    ("npm_config_cache", "~/.npm"),
    ("PIP_CACHE_DIR", "~/.cache/pip"),
    ("GOCACHE", "~/.cache/go-build"),
];

/// Runs `coganchor internal fence`.
pub fn main(args: FenceArgs) -> i32 {
    let mut argv = args.command;
    if argv.first().is_some_and(|one| one == "--") {
        argv.remove(0);
    }
    if argv.is_empty() {
        eprintln!(
            "hmz internal fence: error: no program given; try `hmz internal fence \
             --policy=... -- claude`"
        );
        return exit::USAGE;
    }
    // Refused rather than run without it: a program the fence was meant to hold, run
    // unfenced, would be one reaching whatever it liked while the flow believed it held.
    match Fence::loads(&args.policy).and_then(|fence| run(&fence, &argv)) {
        Ok(status) => status,
        Err(why) => {
            eprintln!("hmz internal fence: {why}");
            exit::UNFENCED
        }
    }
}

/// The command line that runs `argv` inside `fence`: this binary's own `internal fence`.
pub fn command(fence: &Fence, argv: &[OsString]) -> Vec<OsString> {
    let mut line: Vec<OsString> = vec![
        std::env::current_exe().map_or_else(|_| "coganchor".into(), OsString::from),
        "internal".into(),
        "fence".into(),
        format!("--policy={}", fence.dumps()).into(),
        "--".into(),
    ];
    line.extend(argv.iter().cloned());
    line
}

/// `~` as `os.path.expanduser` reads it: `$HOME`, else the password database.
pub fn home() -> String {
    if let Some(home) = std::env::var_os("HOME") {
        let home = home.to_string_lossy().trim_end_matches('/').to_owned();
        return if home.is_empty() { "/".into() } else { home };
    }
    nix::unistd::User::from_uid(nix::unistd::getuid())
        .ok()
        .flatten()
        .map(|user| user.dir.to_string_lossy().trim_end_matches('/').to_owned())
        .filter(|home| !home.is_empty())
        .unwrap_or_else(|| "/".into())
}

fn expanduser(path: &str) -> String {
    match path.strip_prefix('~') {
        Some(rest) if rest.is_empty() || rest.starts_with('/') => format!("{}{rest}", home()),
        _ => path.to_owned(),
    }
}

/// Sets a variable, keeping its place where it was already set.
fn set(env: &mut Vec<(OsString, OsString)>, name: &str, value: impl Into<OsString>) {
    let value = value.into();
    match env.iter_mut().find(|(one, _)| one == name) {
        Some(slot) => slot.1 = value,
        None => env.push((name.into(), value)),
    }
}

/// The environment the program is run with inside the fence (`environ`): the scratch as the
/// temporary directory, every cache the fence would not let it write pointed into the
/// scratch, and -- where the network is cut -- the proxy as every client's proxy, with nothing
/// exempted from it.
pub fn environ(
    fence: &Fence,
    given: impl IntoIterator<Item = (OsString, OsString)>,
    tmp: &str,
    port: Option<u16>,
) -> Vec<(OsString, OsString)> {
    let mut held: Vec<(OsString, OsString)> = given.into_iter().collect();
    for name in ["TMPDIR", "TMP", "TEMP"] {
        set(&mut held, name, tmp);
    }
    for (name, usual) in CACHES {
        let named = held
            .iter()
            .find(|(one, _)| one == name)
            .map(|(_, value)| value.to_string_lossy().into_owned())
            .filter(|value| !value.is_empty());
        let at = named.unwrap_or_else(|| expanduser(usual));
        if !(at.starts_with('/') && fence.allows(&at, true)) {
            let moved = Path::new(tmp).join("cache").join(name.to_lowercase());
            set(&mut held, name, moved.into_os_string());
        }
    }
    if let Some(port) = port {
        let proxy = format!("http://127.0.0.1:{port}");
        for name in PROXIES {
            set(&mut held, name, proxy.as_str());
        }
        // Emptied rather than removed: a `NO_PROXY` somebody exported would otherwise send
        // the hosts it names around the proxy, into a wall.
        set(&mut held, "NO_PROXY", "");
        set(&mut held, "no_proxy", "");
        set(&mut held, "NODE_USE_ENV_PROXY", "1");
    }
    held
}

/// A scratch made for one run, removed when it is dropped.
struct Scratch {
    path: String,
    made: bool,
}

impl Scratch {
    /// The fence's own, or a fresh `hmz-fence-XXXXXX` under the temporary directory.
    fn of(fence: &Fence) -> Result<Scratch, String> {
        if !fence.tmp.is_empty() {
            return Ok(Scratch {
                path: fence.tmp.clone(),
                made: false,
            });
        }
        let template = std::env::temp_dir().join("hmz-fence-XXXXXX");
        let mut bytes = template.as_os_str().as_bytes().to_vec();
        bytes.push(0);
        // SAFETY: `bytes` is a NUL-terminated template mkdtemp rewrites in place.
        if unsafe { libc::mkdtemp(bytes.as_mut_ptr().cast()) }.is_null() {
            return Err(spelled(&std::io::Error::last_os_error()));
        }
        bytes.pop();
        Ok(Scratch {
            path: OsStr::from_bytes(&bytes).to_string_lossy().into_owned(),
            made: true,
        })
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        if self.made {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }
}

/// Why this machine cannot hold a fence around a `what` (one cutting the network too where
/// `net`), as `wrap.run` and `fencing.fenced` say it; `None` where it can.
pub(crate) fn unable(net: bool, what: &str) -> Option<String> {
    let able = crate::fence::able();
    if if net { able.net } else { able.fs } {
        return None;
    }
    let needs = if cfg!(target_os = "macos") {
        "Seatbelt, which a process already inside a sandbox cannot apply"
    } else if net {
        "Landlock ABI 4 and seccomp"
    } else {
        "Landlock"
    };
    Some(format!(
        "this machine cannot fence a {what}: it needs {needs}"
    ))
}

/// The proxy, where the network is cut, stopped however `put_up` ends (the Python's
/// `finally`).
struct Serving(Option<Proxy>);

impl Serving {
    fn start(fence: &Fence) -> Result<Serving, String> {
        if fence.online {
            return Ok(Serving(None));
        }
        Proxy::start(&fence.hosts)
            .map(|proxy| Serving(Some(proxy)))
            .map_err(|why| spelled(&why))
    }

    fn port(&self) -> Option<u16> {
        self.0.as_ref().map(|proxy| proxy.port)
    }
}

impl Drop for Serving {
    fn drop(&mut self) {
        if let Some(proxy) = self.0.take() {
            proxy.stop();
        }
    }
}

/// Runs a program inside a fence and waits for it: its status, or why the fence could not be
/// put up.
fn run(fence: &Fence, argv: &[OsString]) -> Result<i32, String> {
    if let Some(why) = unable(!fence.online, "program") {
        return Err(why);
    }
    let tmp = Scratch::of(fence)?;
    let walled = Fence {
        tmp: tmp.path.clone(),
        ..fence.clone()
    };
    let status = put_up(fence, &walled, argv);
    drop(tmp);
    status
}

/// The process the signals meant for the program are passed on to.
static PROGRAM: AtomicI32 = AtomicI32::new(0);

extern "C" fn passed(signal: libc::c_int) {
    let pid = PROGRAM.load(Ordering::SeqCst);
    if pid > 0 {
        // SAFETY: kill is async-signal-safe.
        unsafe { libc::kill(pid, signal) };
    }
}

/// Waits for the program, passing on the signals meant for it, collecting every orphan as it
/// goes (`_waited`, `_reaped`); returns the status a shell reports for it. `SIGINT` is ignored
/// rather than passed: a ctrl-c at a terminal already reaches the whole group.
fn waited(pid: libc::pid_t) -> i32 {
    use nix::sys::signal::{SaFlags, SigAction, SigHandler, SigSet, Signal, sigaction};
    PROGRAM.store(pid, Ordering::SeqCst);
    let mut was = Vec::new();
    for (signal, handler) in [
        (Signal::SIGINT, SigHandler::SigIgn),
        (Signal::SIGTERM, SigHandler::Handler(passed)),
        (Signal::SIGQUIT, SigHandler::Handler(passed)),
        (Signal::SIGHUP, SigHandler::Handler(passed)),
    ] {
        let action = SigAction::new(handler, SaFlags::SA_RESTART, SigSet::empty());
        // SAFETY: the handler only calls kill, which is async-signal-safe.
        if let Ok(before) = unsafe { sigaction(signal, &action) } {
            was.push((signal, before));
        }
    }
    let status = loop {
        let mut status = 0;
        // Any child rather than the program alone: an orphan handed to this subreaper is
        // collected as it exits, rather than left a zombie until the wrapper goes.
        // SAFETY: `status` is a valid out-pointer.
        let done = unsafe { libc::waitpid(-1, &mut status, 0) };
        if done < 0 {
            match std::io::Error::last_os_error().raw_os_error() {
                Some(libc::EINTR) => continue,
                _ => break exit::FAILED,
            }
        }
        if done == pid && (libc::WIFEXITED(status) || libc::WIFSIGNALED(status)) {
            break match nix::sys::wait::WaitStatus::from_raw(
                nix::unistd::Pid::from_raw(done),
                status,
            ) {
                Ok(said) => exit::of_wait(said),
                Err(_) => exit::FAILED,
            };
        }
    };
    for (signal, before) in was {
        // SAFETY: putting back what was there.
        let _ = unsafe { sigaction(signal, &before) };
    }
    PROGRAM.store(0, Ordering::SeqCst);
    status
}

/// Linux: `run` from the scratch on, the proxy, the fork and the wall.
#[cfg(target_os = "linux")]
fn put_up(fence: &Fence, walled: &Fence, argv: &[OsString]) -> Result<i32, String> {
    use std::ffi::CString;
    use std::io::IoSliceMut;
    use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
    use std::path::PathBuf;

    use nix::sys::socket::{
        AddressFamily, ControlMessage, ControlMessageOwned, MsgFlags, SockFlag, SockType, recvmsg,
        sendmsg, socketpair,
    };

    use crate::fence::landlock::{self, Ruleset};
    use crate::fence::{loopback, netfilter};

    landlock::abi();
    // Made and opened here, where it is put up, and handed down open: what the child grants
    // is what was checked, never a link put at one of its names since.
    let held = walled.ready().map_err(|why| spelled(&why))?;
    let proxy = Serving::start(fence)?;
    let port = proxy.port();
    // The subreaper of everything inside, where binds are answered: a process that left its
    // parent behind is still a descendant, which pidfd_getfd asks of it.
    // SAFETY: integer arguments only.
    if port.is_some() && unsafe { libc::prctl(libc::PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) } != 0 {
        return Err(
            crate::fence::policy::last_os_error("prctl(PR_SET_CHILD_SUBREAPER)").to_string(),
        );
    }
    let env = environ(fence, std::env::vars_os(), &walled.tmp, port);
    let ruleset = Ruleset {
        read: fence.read.iter().map(PathBuf::from).collect(),
        write: held,
        connect_ports: port.into_iter().collect(),
        // A port the kernel picks is a listener only, which reaches nothing: a CLI that
        // serves itself on loopback cannot start without one. A CLI that has to be found at
        // a port of its own names it in `listen`.
        bind_ports: port
            .map(|_| {
                std::iter::once(0)
                    .chain(fence.listen.iter().copied())
                    .collect()
            })
            .unwrap_or_default(),
        net: port.is_some(),
    };
    // What the child needs is made before the fork where it can be: a child of a process
    // with threads -- the proxy's -- should do as little as it can before it becomes the
    // program. (What it still allocates relies on the C library's malloc being fork-safe, as
    // glibc's and musl's are.)
    let cstring =
        |one: &OsStr| CString::new(one.as_bytes()).map_err(|_| "a NUL in the command".to_owned());
    let program = cstring(&argv[0])?;
    let args: Vec<CString> = argv
        .iter()
        .map(|one| cstring(one))
        .collect::<Result<_, _>>()?;
    let envs: Vec<CString> = env
        .iter()
        .filter_map(|(name, value)| {
            let mut pair = name.as_bytes().to_vec();
            pair.push(b'=');
            pair.extend(value.as_bytes());
            CString::new(pair).ok()
        })
        .collect();
    let mut arg_ptrs: Vec<*const libc::c_char> = args.iter().map(|one| one.as_ptr()).collect();
    arg_ptrs.push(std::ptr::null());
    let mut env_ptrs: Vec<*const libc::c_char> = envs.iter().map(|one| one.as_ptr()).collect();
    env_ptrs.push(std::ptr::null());
    let name = argv[0].to_string_lossy().into_owned();
    let handoff = if port.is_some() {
        Some(
            socketpair(
                AddressFamily::Unix,
                SockType::Stream,
                None,
                SockFlag::SOCK_CLOEXEC,
            )
            .map_err(|errno| spelled(&errno.into()))?,
        )
    } else {
        None
    };
    // SAFETY: getpid has no preconditions.
    let parent = unsafe { libc::getpid() };
    // SAFETY: the child only walls itself in and execs, never returning into this code.
    let pid = unsafe { libc::fork() };
    if pid < 0 {
        return Err(spelled(&std::io::Error::last_os_error()));
    }
    if pid == 0 {
        // The child's half: wall itself in and become the program. Never returns.
        let theirs = handoff.as_ref().map(|(_, theirs)| theirs);
        let walled_in = (|| -> Result<(), String> {
            // It goes when the wrapper does, however the wrapper went.
            // SAFETY: integer arguments only.
            unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) };
            // SAFETY: getppid has no preconditions.
            if unsafe { libc::getppid() } != parent {
                // SAFETY: leaving the forked child at once.
                unsafe { libc::_exit(exit::UNFENCED) };
            }
            if let Some(theirs) = theirs {
                netfilter::install_socket_filter().map_err(|why| spelled(&why))?;
                let listener = match netfilter::install_listener() {
                    Ok(listener) => listener,
                    Err(why) if crate::fence::policy::errno_of(&why) == Some(libc::EBUSY) => {
                        // A thread answers to one supervisor, and this one already has.
                        return Err("it is already inside a fence that cuts the network".into());
                    }
                    Err(why) => return Err(spelled(&why)),
                };
                let fds = [listener.as_raw_fd()];
                sendmsg::<()>(
                    theirs.as_raw_fd(),
                    &[std::io::IoSlice::new(b"!")],
                    &[ControlMessage::ScmRights(&fds)],
                    MsgFlags::empty(),
                    None,
                )
                .map_err(|errno| spelled(&errno.into()))?;
                // Closed before the program runs, not merely on exec: a program holding the
                // listener could answer its own calls.
                drop(listener);
            }
            ruleset.restrict_self().map_err(|why| spelled(&why))
        })();
        if let Some((ours, theirs)) = handoff {
            drop(ours);
            drop(theirs);
        }
        if let Err(why) = walled_in {
            let said = format!("hmz internal fence: cannot fence {name}: {why}\n");
            // SAFETY: writing a buffer we own to standard error, then leaving.
            unsafe {
                libc::write(2, said.as_ptr().cast(), said.len());
                libc::_exit(exit::UNFENCED);
            }
        }
        // SAFETY: NULL-terminated arrays of NUL-terminated strings, alive for the call.
        unsafe { libc::execvpe(program.as_ptr(), arg_ptrs.as_ptr(), env_ptrs.as_ptr()) };
        let why = std::io::Error::last_os_error();
        let said = format!("hmz internal fence: cannot run {name}: {}\n", spelled(&why));
        // SAFETY: as above.
        unsafe {
            libc::write(2, said.as_ptr().cast(), said.len());
            libc::_exit(exit::NOT_INSTALLED);
        }
    }
    drop(ruleset);
    let mut supervisor = None;
    if let Some((ours, theirs)) = handoff {
        drop(theirs);
        let mut byte = [0u8; 1];
        let mut space = nix::cmsg_space!([std::os::fd::RawFd; 1]);
        let mut iov = [IoSliceMut::new(&mut byte)];
        // Nothing where the child failed before it could hand the listener up, and then it
        // exits unfenced rather than runs: it is waited for as it is.
        if let Ok(said) = recvmsg::<()>(
            ours.as_raw_fd(),
            &mut iov,
            Some(&mut space),
            MsgFlags::MSG_CMSG_CLOEXEC,
        ) && let Ok(mut messages) = said.cmsgs()
            && let Some(ControlMessageOwned::ScmRights(fds)) = messages.next()
            && let Some(&fd) = fds.first()
        {
            // SAFETY: the descriptor was just received, and nothing else owns it.
            supervisor = Some(loopback::supervise(unsafe { OwnedFd::from_raw_fd(fd) }));
        }
    }
    let status = waited(pid);
    // The supervisor ends with the process: every call left is answered `ENOSYS` once its
    // listener closes on exit.
    drop(supervisor);
    drop(proxy);
    Ok(status)
}

/// macOS's `confstr` selector for its per-user cache, `_CS_DARWIN_USER_CACHE_DIR`.
#[cfg(target_os = "macos")]
const DARWIN_USER_CACHE_DIR: libc::c_int = 65538;

/// The Mac: the program run under `sandbox-exec`, and waited for (`_seatbelted`).
#[cfg(target_os = "macos")]
fn put_up(fence: &Fence, walled: &Fence, argv: &[OsString]) -> Result<i32, String> {
    use crate::fence::seatbelt;

    // Granted as the paths they were reached at, every link on the way followed where it may
    // be: a link put at one of them since leads nowhere granted.
    let reached: Vec<String> = walled
        .reached()
        .map_err(|why| spelled(&why))?
        .into_iter()
        .map(|(path, _)| path)
        .collect();
    let proxy = Serving::start(fence)?;
    let port = proxy.port();
    let mut write = reached;
    // Native TLS needs the module database's lock writable even when the program only reads
    // the keychains; granted nothing where it is a link.
    if let Some(cache) = user_cache() {
        let mds = Path::new(&cache).join("mds");
        if !mds.is_symlink()
            && let Ok((_, at)) = fence.reach(&mds.to_string_lossy(), false)
        {
            write.push(at);
        }
    }
    let profiled = Fence {
        write,
        ..walled.clone()
    };
    let line = seatbelt::command(&profiled, port, argv);
    let env = environ(fence, std::env::vars_os(), &walled.tmp, port);
    let spawned = std::process::Command::new(&line[0])
        .args(&line[1..])
        .env_clear()
        .envs(env)
        .spawn();
    let status = match spawned {
        Ok(child) => Ok(waited(child.id() as libc::pid_t)),
        Err(why) => Err(spelled(&why)),
    };
    drop(proxy);
    status
}

#[cfg(target_os = "macos")]
fn user_cache() -> Option<String> {
    let mut buffer = vec![0u8; 1024];
    // SAFETY: `buffer` is as long as said.
    let length = unsafe {
        libc::confstr(
            DARWIN_USER_CACHE_DIR,
            buffer.as_mut_ptr().cast(),
            buffer.len(),
        )
    };
    if length == 0 || length > buffer.len() {
        return None;
    }
    buffer.truncate(length - 1);
    String::from_utf8(buffer).ok().filter(|one| !one.is_empty())
}

#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn put_up(_: &Fence, _: &Fence, _: &[OsString]) -> Result<i32, String> {
    Err("this machine cannot fence a program".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value<'a>(env: &'a [(OsString, OsString)], name: &str) -> Option<&'a OsStr> {
        env.iter()
            .find(|(one, _)| one == name)
            .map(|(_, value)| value.as_os_str())
    }

    #[test]
    fn the_environment_points_scratch_caches_and_proxies_inward() {
        let fence = Fence {
            write: vec!["/w".into()],
            ..Fence::default()
        };
        let given = vec![
            (OsString::from("XDG_CACHE_HOME"), OsString::from("/w/cache")),
            (OsString::from("GOCACHE"), OsString::from("/elsewhere")),
            (OsString::from("NO_PROXY"), OsString::from("x")),
        ];
        let env = environ(&fence, given, "/s", Some(9));
        assert_eq!(value(&env, "TMPDIR"), Some(OsStr::new("/s")));
        assert_eq!(value(&env, "TEMP"), Some(OsStr::new("/s")));
        assert_eq!(value(&env, "XDG_CACHE_HOME"), Some(OsStr::new("/w/cache")));
        assert_eq!(value(&env, "GOCACHE"), Some(OsStr::new("/s/cache/gocache")));
        assert_eq!(
            value(&env, "npm_config_cache"),
            Some(OsStr::new("/s/cache/npm_config_cache"))
        );
        assert_eq!(value(&env, "NO_PROXY"), Some(OsStr::new("")));
        assert_eq!(
            value(&env, "all_proxy"),
            Some(OsStr::new("http://127.0.0.1:9"))
        );
        assert_eq!(value(&env, "NODE_USE_ENV_PROXY"), Some(OsStr::new("1")));
        assert_eq!(env[0].0, "XDG_CACHE_HOME");
        let online = environ(&fence, Vec::new(), "/s", None);
        assert_eq!(value(&online, "HTTPS_PROXY"), None);
    }

    #[test]
    fn the_command_is_this_binarys_own_fence() {
        let line = command(&Fence::default(), &["true".into()]);
        assert_eq!(&line[1..3], &[OsString::from("internal"), "fence".into()]);
        assert!(line[3].to_string_lossy().starts_with("--policy={\"read\""));
        assert_eq!(&line[4..], &[OsString::from("--"), "true".into()]);
    }
}
