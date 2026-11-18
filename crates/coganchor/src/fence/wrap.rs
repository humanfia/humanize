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
//! Landlock only allows, so what a fence carves out of a grant is held by granting what is
//! around it instead ([`expanded`]), worked out before the fork; a carve-out that cannot be
//! held so is a program that does not run either. The parent stays outside: serving the proxy, answering binds, passing signals on, and --
//! where the network is cut -- reaping every orphan as the subreaper of the tree. Where
//! Landlock cannot hold the fence, or `--sandbox` names it, the wall on Linux is bubblewrap
//! instead ([`crate::fence::bubblewrap`]). On a Mac the child is `sandbox-exec` with the
//! fence's Seatbelt profile.

use std::ffi::{OsStr, OsString};
use std::os::unix::ffi::OsStrExt;
use std::path::Path;
use std::sync::atomic::{AtomicI32, Ordering};

use crate::cli::FenceArgs;
use crate::exit;
use crate::fence::policy::spelled;
use crate::fence::proxy::Proxy;
use crate::fence::{Fence, Sandbox};

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
    if let Some(through) = &args.relay {
        return crate::fence::relay::main(through, &argv);
    }
    let asked = Sandbox::of(args.sandbox.as_deref());
    let policy = args.policy.unwrap_or_default();
    // Refused rather than run without it: a program the fence was meant to hold, run
    // unfenced, would be one reaching whatever it liked while the flow believed it held.
    match Fence::loads(&policy).and_then(|fence| run(&fence, &argv, asked)) {
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

/// What Landlock grants to read, and to write, to hold a fence's carve-outs (`expanded`): the
/// fence's own grants where nothing is carved out of them.
///
/// Landlock only allows: a rule grants a directory and everything beneath it, and nothing a
/// rule beneath it says takes any of that back. So a grant that holds a path carved out
/// narrower than it is not granted itself. Its entries are, one by one -- each as it is, but
/// one on the way to such a path, which is taken apart the same way, down to the path itself,
/// which is granted at its own level or not at all. A path granted beneath a carve-out is
/// granted on its own, being in the fence's grants -- but one granted to read where the fence
/// writes, which the grant above it holds as it holds every other entry.
///
/// What is granted is what is there as this is asked: an entry made later in a directory that
/// was taken apart is in nothing granted, and so out of reach -- the fence failing closed. So
/// is the directory itself, which can be neither listed nor added to, only gone through. Nor
/// is a symbolic link among the entries granted, a rule on a link being a rule on wherever it
/// leads.
///
/// # Errors
/// Where a directory that has to be taken apart cannot be listed, or a grant holding a
/// carve-out is not a directory: the carve-out cannot be held.
pub fn expanded(fence: &Fence) -> std::io::Result<(Vec<String>, Vec<String>)> {
    use crate::fence::policy::{LEVELS, WRITE, os_error, os_said, rank};

    if fence.keep.is_empty() && fence.deny.is_empty() {
        return Ok((fence.read.clone(), fence.write.clone()));
    }
    let mut ranked: Vec<(String, usize)> = Vec::new();
    for one in fence
        .read
        .iter()
        .chain(&fence.write)
        .chain(&fence.keep)
        .chain(&fence.deny)
    {
        let level = rank(fence.level(one)).unwrap_or(0);
        // What is read inside what is written is written, as all around it is: an entry like
        // any other of the grant above it, and no path of its own for a wall to reach.
        if LEVELS[level] == WRITE && !fence.write.contains(one) {
            continue;
        }
        if !ranked.iter().any(|(path, _)| path == one) {
            ranked.push((one.clone(), level));
        }
    }
    let mut read: Vec<String> = Vec::new();
    let mut write: Vec<String> = Vec::new();
    let mut granted = |path: String, level: usize| {
        let into = if LEVELS[level] == WRITE {
            &mut write
        } else {
            &mut read
        };
        if !into.contains(&path) {
            into.push(path);
        }
    };
    fn apart(
        directory: &str,
        level: usize,
        narrower: &[&str],
        ranked: &[(String, usize)],
        granted: &mut dyn FnMut(String, usize),
    ) -> std::io::Result<()> {
        let unlisted =
            |why: std::io::Error| os_error(why.raw_os_error().unwrap_or(libc::EIO), directory);
        let mut entries: Vec<std::fs::DirEntry> = std::fs::read_dir(directory)
            .map_err(unlisted)?
            .collect::<Result<_, _>>()
            .map_err(unlisted)?;
        entries.sort_by_key(std::fs::DirEntry::file_name);
        for entry in entries {
            let path = format!(
                "{}/{}",
                directory.trim_end_matches('/'),
                entry.file_name().to_string_lossy()
            );
            if ranked.iter().any(|(one, _)| *one == path)
                || entry.file_type().is_ok_and(|kind| kind.is_symlink())
            {
                continue;
            }
            let beneath: Vec<&str> = narrower
                .iter()
                .copied()
                .filter(|one| strictly(one, &path))
                .collect();
            if beneath.is_empty() {
                granted(path, level);
            } else {
                apart(&path, level, &beneath, ranked, granted)?;
            }
        }
        Ok(())
    }
    for (path, level) in &ranked {
        if *level == 0 {
            continue;
        }
        let narrower: Vec<&str> = ranked
            .iter()
            .filter(|(one, below)| strictly(one, path) && below < level)
            .map(|(one, _)| one.as_str())
            .collect();
        if narrower.is_empty() {
            granted(path.clone(), *level);
        } else if Path::new(path).is_dir() {
            apart(path, *level, &narrower, &ranked, &mut granted)?;
        } else if std::fs::symlink_metadata(path).is_ok() {
            return Err(os_said(
                libc::ENOTDIR,
                "a path carved out beneath it cannot be held, it not being a directory",
                path.clone(),
            ));
        }
    }
    Ok((read, write))
}

/// Whether `path` is strictly beneath `root`.
fn strictly(path: &str, root: &str) -> bool {
    path.starts_with(&format!("{}/", root.trim_end_matches('/')))
}

/// A scratch made for one run, removed when it is dropped.
pub(crate) struct Scratch {
    pub(crate) path: String,
    made: bool,
}

impl Scratch {
    /// A fresh directory `<prefix>XXXXXX` under the temporary directory, `0700`.
    pub(crate) fn fresh(prefix: &str) -> Result<Scratch, String> {
        let template = std::env::temp_dir().join(format!("{prefix}XXXXXX"));
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

    /// The fence's own, or a fresh `hmz-fence-XXXXXX` under the temporary directory.
    fn of(fence: &Fence) -> Result<Scratch, String> {
        if !fence.tmp.is_empty() {
            return Ok(Scratch {
                path: fence.tmp.clone(),
                made: false,
            });
        }
        Scratch::fresh("hmz-fence-")
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
    unable_with(net, what, Sandbox::Auto)
}

/// [`unable`], as `asked` chooses the backend.
pub(crate) fn unable_with(net: bool, what: &str, asked: Sandbox) -> Option<String> {
    if crate::fence::backend(net, asked).is_some() {
        return None;
    }
    let landlock = if net {
        "Landlock ABI 4 and seccomp"
    } else {
        "Landlock"
    };
    let bwrap = if net {
        "a bwrap that starts here with a network namespace of its own"
    } else {
        "a bwrap that starts here"
    };
    let needs = if cfg!(target_os = "macos") {
        "Seatbelt, which a process already inside a sandbox cannot apply".to_owned()
    } else {
        match asked {
            Sandbox::Landlock => landlock.to_owned(),
            Sandbox::Bwrap => bwrap.to_owned(),
            Sandbox::Auto => format!("{landlock}, or {bwrap}"),
        }
    };
    Some(format!(
        "this machine cannot fence a {what}: it needs {needs}"
    ))
}

/// The proxy, where the network is cut, stopped however `put_up` ends (the Python's
/// `finally`).
pub(crate) struct Serving(Option<Proxy>);

impl Serving {
    pub(crate) fn start(fence: &Fence) -> Result<Serving, String> {
        if fence.online {
            return Ok(Serving(None));
        }
        Proxy::start(&fence.hosts)
            .map(|proxy| Serving(Some(proxy)))
            .map_err(|why| spelled(&why))
    }

    pub(crate) fn port(&self) -> Option<u16> {
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
fn run(fence: &Fence, argv: &[OsString], asked: Sandbox) -> Result<i32, String> {
    if let Some(why) = unable_with(!fence.online, "program", asked) {
        return Err(why);
    }
    let tmp = Scratch::of(fence)?;
    let walled = Fence {
        tmp: tmp.path.clone(),
        ..fence.clone()
    };
    #[cfg(target_os = "linux")]
    let status =
        if crate::fence::backend(!fence.online, asked) == Some(crate::fence::Backend::Bwrap) {
            crate::fence::bubblewrap::put_up(fence, &walled, argv)
        } else {
            put_up(fence, &walled, argv)
        };
    #[cfg(not(target_os = "linux"))]
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
pub(crate) fn waited(pid: libc::pid_t) -> i32 {
    waited_aimed(pid, pid)
}

/// [`waited`], passing the signals to `aimed` rather than to the child waited for: the program
/// a `bwrap` child started, which `bwrap` going would take with it.
pub(crate) fn waited_aimed(pid: libc::pid_t, aimed: libc::pid_t) -> i32 {
    use nix::sys::signal::{SaFlags, SigAction, SigHandler, SigSet, Signal, sigaction};
    PROGRAM.store(aimed, Ordering::SeqCst);
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
    // Taken apart around what is carved out of it, which Landlock cannot say.
    let (read, write) = expanded(fence).map_err(|why| spelled(&why))?;
    // Made and opened here, where it is put up, and handed down open: what the child grants
    // is what was checked, never a link put at one of its names since.
    let held = walled.ready(Some(&write)).map_err(|why| spelled(&why))?;
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
        read: read.iter().map(PathBuf::from).collect(),
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
        .reached(None)
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

    fn strings(list: &[&str]) -> Vec<String> {
        list.iter().map(|one| (*one).to_owned()).collect()
    }

    /// Lays out `names` under `root`: a directory where the name ends in `/`, else a file.
    fn tree(root: &Path, names: &[&str]) -> String {
        for name in names {
            let at = root.join(name.trim_end_matches('/'));
            if name.ends_with('/') {
                std::fs::create_dir_all(&at).unwrap();
            } else {
                std::fs::create_dir_all(at.parent().unwrap()).unwrap();
                std::fs::write(&at, "").unwrap();
            }
        }
        root.to_string_lossy().into_owned()
    }

    fn sorted(mut paths: Vec<String>) -> Vec<String> {
        paths.sort();
        paths
    }

    #[test]
    fn expanded_leaves_a_fence_with_nothing_carved_out_as_it_is() {
        let fence = Fence {
            read: strings(&["/r"]),
            write: strings(&["/w"]),
            ..Fence::default()
        };
        assert_eq!(
            expanded(&fence).unwrap(),
            (strings(&["/r"]), strings(&["/w"]))
        );
    }

    #[test]
    fn expanded_takes_a_grant_apart_down_to_what_is_carved_out_of_it() {
        let dir = tempfile::tempdir().unwrap();
        let w = tree(
            &std::fs::canonicalize(dir.path()).unwrap(),
            &[
                "ok",
                "src/",
                "a/secret/key",
                "a/b",
                "a/c/",
                "ro/notes",
                "ro/d/x",
            ],
        );
        std::os::unix::fs::symlink(format!("{w}/a/secret"), format!("{w}/link")).unwrap();
        let fence = Fence {
            write: vec![w.clone()],
            keep: vec![format!("{w}/ro")],
            deny: vec![format!("{w}/a/secret"), format!("{w}/ro/d")],
            ..Fence::default()
        };
        let (read, write) = expanded(&fence).unwrap();
        assert_eq!(
            sorted(write),
            vec![
                format!("{w}/a/b"),
                format!("{w}/a/c"),
                format!("{w}/ok"),
                format!("{w}/src"),
            ]
        );
        assert_eq!(read, vec![format!("{w}/ro/notes")]);
    }

    #[test]
    fn expanded_grants_again_what_is_granted_beneath_a_carve_out() {
        let dir = tempfile::tempdir().unwrap();
        let w = tree(
            &std::fs::canonicalize(dir.path()).unwrap(),
            &["home/.cli/state", "home/.bashrc", "etc/hosts"],
        );
        let fence = Fence {
            read: vec![w.clone()],
            write: vec![format!("{w}/home/.cli")],
            deny: vec![format!("{w}/home")],
            ..Fence::default()
        };
        let (read, write) = expanded(&fence).unwrap();
        assert_eq!(read, vec![format!("{w}/etc")]);
        assert_eq!(write, vec![format!("{w}/home/.cli")]);
    }

    #[test]
    fn expanded_takes_apart_every_grant_above_a_carve_out() {
        let dir = tempfile::tempdir().unwrap();
        let w = tree(
            &std::fs::canonicalize(dir.path()).unwrap(),
            &["x/secret/key", "x/y"],
        );
        let fence = Fence {
            read: vec![w.clone()],
            write: vec![format!("{w}/x")],
            deny: vec![format!("{w}/x/secret")],
            ..Fence::default()
        };
        let (read, write) = expanded(&fence).unwrap();
        assert!(read.is_empty(), "{read:?}");
        assert_eq!(write, vec![format!("{w}/x/y")]);
    }

    #[test]
    fn expanded_leaves_what_is_read_inside_what_is_written_to_the_grant_above_it() {
        let dir = tempfile::tempdir().unwrap();
        let w = tree(
            &std::fs::canonicalize(dir.path()).unwrap(),
            &["bin/real", "lib/", "secret/key"],
        );
        std::os::unix::fs::symlink(format!("{w}/bin/real"), format!("{w}/bin/cli")).unwrap();
        std::os::unix::fs::symlink(format!("{w}/lib"), format!("{w}/python")).unwrap();
        let fence = Fence {
            read: vec![
                format!("{w}/bin/cli"),
                format!("{w}/bin/real"),
                format!("{w}/python"),
                format!("{w}/lib"),
            ],
            write: vec![w.clone()],
            deny: vec![format!("{w}/secret")],
            ..Fence::default()
        };
        let (read, write) = expanded(&fence).unwrap();
        assert!(read.is_empty(), "{read:?}");
        assert_eq!(
            sorted(write.clone()),
            vec![format!("{w}/bin"), format!("{w}/lib")]
        );
        // No link among them, so the fence can be put up.
        fence.ready(Some(&write)).unwrap();
    }

    #[test]
    fn expanded_refuses_a_carve_out_it_cannot_hold() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let w = tree(
            &std::fs::canonicalize(dir.path()).unwrap(),
            &["shut/secret/key", "shut/other", "file"],
        );
        let not_a_directory = Fence {
            write: vec![format!("{w}/file")],
            deny: vec![format!("{w}/file/x")],
            ..Fence::default()
        };
        let why = expanded(&not_a_directory).unwrap_err();
        assert_eq!(
            why.to_string(),
            format!(
                "[Errno {}] a path carved out beneath it cannot be held, it not being a \
                 directory: '{w}/file'",
                libc::ENOTDIR
            )
        );
        let shut = format!("{w}/shut");
        std::fs::set_permissions(&shut, std::fs::Permissions::from_mode(0o0)).unwrap();
        // Root lists anything.
        if std::fs::read_dir(&shut).is_err() {
            let fence = Fence {
                write: vec![w.clone()],
                deny: vec![format!("{shut}/secret")],
                ..Fence::default()
            };
            let why = expanded(&fence).unwrap_err();
            assert_eq!(
                why.to_string(),
                format!("[Errno 13] Permission denied: '{shut}'")
            );
        }
        std::fs::set_permissions(&shut, std::fs::Permissions::from_mode(0o700)).unwrap();
    }

    #[test]
    fn the_command_is_this_binarys_own_fence() {
        let line = command(&Fence::default(), &["true".into()]);
        assert_eq!(&line[1..3], &[OsString::from("internal"), "fence".into()]);
        assert!(line[3].to_string_lossy().starts_with("--policy={\"read\""));
        assert_eq!(&line[4..], &[OsString::from("--"), "true".into()]);
    }
}
