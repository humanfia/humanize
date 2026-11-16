//! A fence, as the JSON `hmz` hands it over. Port of `Fence` in `hmz.coganchor.fence`.
//! [Unit 4]
//!
//! Besides reading and writing the JSON, this is where a fence is drawn from scope levels
//! ([`Fence::of`], for [`crate::fence::abroad`]) and where what it writes is reached, one name
//! at a time and through no link a fenced program could have made ([`Fence::reach`]), just
//! before a program is walled in.

use std::collections::{HashSet, VecDeque};
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::io;
use std::os::fd::{AsFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::path::Path;

use nix::errno::Errno;
use nix::fcntl::{AtFlags, OFlag, openat};
use nix::sys::stat::{FileStat, Mode, fstat, fstatat, mkdirat};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// How much of one scope a fence grants, narrowest first (`NONE`, `READ`, `ALL`).
pub const NONE: &str = "none";
pub const READ: &str = "read";
pub const ALL: &str = "all";
pub const LEVELS: [&str; 3] = [NONE, READ, ALL];

/// What any program needs to read to run at all (`LINUX_SYSTEM`).
pub const LINUX_SYSTEM: &[&str] = &[
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib32",
    "/lib64",
    "/libx32",
    "/etc/ssl",
    "/etc/ca-certificates",
    "/etc/pki",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/host.conf",
    "/etc/gai.conf",
    "/etc/nsswitch.conf",
    "/etc/passwd",
    "/etc/group",
    "/etc/localtime",
    "/etc/timezone",
    "/etc/os-release",
    "/etc/ld.so.cache",
    "/etc/ld.so.conf",
    "/etc/ld.so.conf.d",
    "/etc/alternatives",
    "/sys",
];

/// The same on a Mac (`DARWIN_SYSTEM`).
pub const DARWIN_SYSTEM: &[&str] = &[
    "/usr",
    "/bin",
    "/sbin",
    "/System",
    "/private/var/select",
    "/private/var/db/timezone",
    "/etc/ssl",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/services",
    "/etc/protocols",
    "/etc/passwd",
    "/etc/group",
    "/etc/shells",
    "/etc/localtime",
];

/// What any program needs to write to run at all (`LINUX_DEVICES`).
pub const LINUX_DEVICES: &[&str] = &[
    "/dev/null",
    "/dev/zero",
    "/dev/full",
    "/dev/random",
    "/dev/urandom",
    "/dev/tty",
    "/dev/pts",
    "/dev/ptmx",
    "/dev/shm",
    "/proc",
];

/// The same on a Mac (`DARWIN_DEVICES`).
pub const DARWIN_DEVICES: &[&str] = &[
    "/dev/null",
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "/dev/tty",
    "/dev/ptmx",
    "/dev/fd",
    "/dev/dtracehelper",
];

/// Where every user may write scratch, granted with a workdir that may be written.
pub const TEMPORARY: &[&str] = &["/tmp", "/var/tmp"];

/// This machine's minimum to read.
#[cfg(target_os = "macos")]
pub const SYSTEM: &[&str] = DARWIN_SYSTEM;
#[cfg(not(target_os = "macos"))]
pub const SYSTEM: &[&str] = LINUX_SYSTEM;

/// This machine's minimum to write.
#[cfg(target_os = "macos")]
pub const DEVICES: &[&str] = DARWIN_DEVICES;
#[cfg(not(target_os = "macos"))]
pub const DEVICES: &[&str] = LINUX_DEVICES;

/// How many links one path may lead through, as Linux counts them (`MAXSYMLINKS`).
const LINKS: usize = 40;

/// Why a path a fence writes is granted nothing rather than refused (`_UNREACHED`).
pub(crate) const UNREACHED: [i32; 4] = [libc::ENOENT, libc::ENOTDIR, libc::EACCES, libc::ELOOP];

/// Whether this machine opens a descriptor to grant (`O_PATH`, Linux).
const HAS_O_PATH: bool = cfg!(target_os = "linux");

/// How a directory on the way to a path a fence writes is opened: to search it, never to
/// read it (`_SEARCH`).
fn search() -> OFlag {
    #[cfg(target_os = "linux")]
    let how = OFlag::O_PATH;
    #[cfg(target_os = "macos")]
    let how = OFlag::from_bits_retain(libc::O_SEARCH);
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    let how = OFlag::O_RDONLY;
    how | OFlag::O_CLOEXEC
}

/// An operating-system error spelled as Python spells an `OSError`, so that what
/// `hmz internal fence` says matches: `[Errno N] message: 'filename'`.
#[derive(Debug)]
pub struct OsError {
    pub errno: i32,
    pub message: String,
    pub filename: Option<String>,
}

impl fmt::Display for OsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[Errno {}] {}", self.errno, self.message)?;
        if let Some(name) = &self.filename {
            write!(f, ": '{name}'")?;
        }
        Ok(())
    }
}

impl std::error::Error for OsError {}

/// The calling thread's last error, naming the call that failed, as the Python's
/// `OSError(code, strerror, what)`.
pub fn last_os_error(what: &str) -> io::Error {
    let errno = io::Error::last_os_error()
        .raw_os_error()
        .unwrap_or(libc::EIO);
    os_error(errno, what)
}

/// An `io::Error` carrying `errno` and the file it concerns, as [`OsError`].
pub fn os_error(errno: i32, filename: impl Into<String>) -> io::Error {
    os_said(errno, Errno::from_raw(errno).desc(), filename)
}

/// As [`os_error`], with a message of its own.
pub fn os_said(errno: i32, message: &str, filename: impl Into<String>) -> io::Error {
    io::Error::new(
        io::Error::from_raw_os_error(errno).kind(),
        OsError {
            errno,
            message: message.to_owned(),
            filename: Some(filename.into()),
        },
    )
}

/// The errno an error carries, whether raw or as an [`OsError`].
pub fn errno_of(error: &io::Error) -> Option<i32> {
    error.raw_os_error().or_else(|| {
        error
            .get_ref()
            .and_then(|inner| inner.downcast_ref::<OsError>())
            .map(|said| said.errno)
    })
}

/// An error spelled as Python spells it: `[Errno N] message` for a bare errno, else its own
/// words.
pub fn spelled(error: &io::Error) -> String {
    match error.raw_os_error() {
        Some(errno) => format!("[Errno {errno}] {}", Errno::from_raw(errno).desc()),
        None => error.to_string(),
    }
}

fn naming(errno: Errno, filename: &str) -> io::Error {
    os_error(errno as i32, filename)
}

/// The whole of what a program's process tree may still reach. Serialised with these keys in
/// this order, unknown keys refused, exactly as `dataclasses.asdict(Fence)`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct Fence {
    pub read: Vec<String>,
    pub write: Vec<String>,
    pub online: bool,
    pub hosts: Vec<String>,
    pub tmp: String,
    pub scopes: Vec<String>,
    pub listen: Vec<u16>,
}

impl Default for Fence {
    /// A fence of nothing: online, as Python's `Fence()` is.
    fn default() -> Fence {
        Fence {
            read: Vec::new(),
            write: Vec::new(),
            online: true,
            hosts: Vec::new(),
            tmp: String::new(),
            scopes: Vec::new(),
            listen: Vec::new(),
        }
    }
}

impl Fence {
    /// Reads a fence from JSON, or from the file `@PATH` names. Refuses what `Fence.loads`
    /// refuses, in its words: a field that is not a fence's, or one of the wrong kind.
    pub fn loads(said: &str) -> Result<Fence, String> {
        let text = match said.strip_prefix('@') {
            Some(path) => std::fs::read_to_string(path).map_err(|why| {
                let errno = why.raw_os_error().unwrap_or(libc::EIO);
                os_error(errno, path).to_string()
            })?,
            None => said.to_owned(),
        };
        let loaded: Value = serde_json::from_str(&text).map_err(|why| why.to_string())?;
        let Value::Object(held) = loaded else {
            return Err("a fence is a JSON object".into());
        };
        let names = [
            "read", "write", "online", "hosts", "tmp", "scopes", "listen",
        ];
        let mut unknown: Vec<&str> = held
            .keys()
            .map(String::as_str)
            .filter(|key| !names.contains(key))
            .collect();
        if !unknown.is_empty() {
            unknown.sort_unstable();
            return Err(format!("not a fence's: {}", unknown.join(", ")));
        }
        let strings = |name: &str| -> Result<Vec<String>, String> {
            match held.get(name) {
                None => Ok(Vec::new()),
                Some(Value::Array(listed)) => listed
                    .iter()
                    .map(|one| one.as_str().map(str::to_owned).ok_or(()))
                    .collect::<Result<_, _>>()
                    .map_err(|()| format!("a fence's {name} is a list of strings")),
                Some(_) => Err(format!("a fence's {name} is a list of strings")),
            }
        };
        let (read, write, hosts, scopes) = (
            strings("read")?,
            strings("write")?,
            strings("hosts")?,
            strings("scopes")?,
        );
        let listen = match held.get("listen") {
            None => Vec::new(),
            Some(Value::Array(ports)) => ports
                .iter()
                .map(|one| one.as_u64().and_then(|port| u16::try_from(port).ok()))
                .collect::<Option<Vec<u16>>>()
                .ok_or("a fence's listen is a list of ports")?,
            Some(_) => return Err("a fence's listen is a list of ports".into()),
        };
        let online = match held.get("online") {
            None => true,
            Some(Value::Bool(online)) => *online,
            Some(_) => return Err("a fence's online is true or false".into()),
        };
        let tmp = match held.get("tmp") {
            None => String::new(),
            Some(Value::String(tmp)) => tmp.clone(),
            Some(_) => return Err("a fence's tmp is a path".into()),
        };
        Fence {
            read,
            write,
            online,
            hosts,
            tmp,
            scopes,
            listen,
        }
        .settled()
    }

    /// The fence as JSON.
    pub fn dumps(&self) -> String {
        serde_json::to_string(self).expect("a fence always serialises")
    }

    /// What `Fence.__post_init__` makes of one: the paths absolute, normal and each once, a
    /// path to write taken out of those to read, hosts and ports each once, and the scopes
    /// either none or three levels.
    pub fn settled(mut self) -> Result<Fence, String> {
        self.write = normal(&self.write);
        let read = normal(&self.read);
        self.read = read
            .into_iter()
            .filter(|one| !self.write.contains(one))
            .collect();
        self.hosts = once(self.hosts);
        if !self.scopes.is_empty()
            && (self.scopes.len() != LEVELS.len()
                || !self.scopes.iter().all(|one| LEVELS.contains(&one.as_str())))
        {
            return Err(format!(
                "a fence's scopes are three of {}, not {}",
                LEVELS.join(", "),
                python_tuple(&self.scopes)
            ));
        }
        self.listen = once(self.listen);
        Ok(self)
    }

    /// The fence four scopes come to, with the minimum every program needs to run
    /// (`Fence.of`). The levels must each be one of [`LEVELS`] and nest, local at least user
    /// and user at least system.
    #[allow(clippy::too_many_arguments)]
    pub fn of(
        local: &str,
        user: &str,
        system: &str,
        online: bool,
        workdir: &str,
        home: &str,
        hosts: &[String],
        read: &[String],
        write: &[String],
    ) -> Result<Fence, String> {
        let rank = |level: &str| {
            LEVELS
                .iter()
                .position(|one| *one == level)
                .ok_or_else(|| format!("a scope is one of {}, not '{level}'", LEVELS.join(", ")))
        };
        let ranks = [rank(local)?, rank(user)?, rank(system)?];
        if !(ranks[0] >= ranks[1] && ranks[1] >= ranks[2]) {
            return Err(format!(
                "scopes must nest, local >= user >= system; got local={local}, user={user}, \
                 system={system}"
            ));
        }
        let scopes = [("/", system), (home, user), (workdir, local)];
        let mut reading: Vec<String> = SYSTEM.iter().map(|one| (*one).to_owned()).collect();
        reading.extend(ours());
        reading.extend(
            scopes
                .iter()
                .filter(|(_, level)| *level == READ)
                .map(|(root, _)| (*root).to_owned()),
        );
        reading.extend(read.iter().cloned());
        let mut writing: Vec<String> = DEVICES.iter().map(|one| (*one).to_owned()).collect();
        writing.extend(accelerators());
        writing.extend(
            scopes
                .iter()
                .filter(|(_, level)| *level == ALL)
                .map(|(root, _)| (*root).to_owned()),
        );
        if local == ALL {
            writing.extend(temporary());
        }
        if user == ALL {
            writing.extend(users());
        }
        writing.extend(write.iter().cloned());
        Fence {
            read: normal(&reading),
            write: normal(&writing),
            online,
            hosts: hosts.to_vec(),
            tmp: String::new(),
            scopes: vec![local.to_owned(), user.to_owned(), system.to_owned()],
            listen: Vec::new(),
        }
        .settled()
    }

    /// This fence with more let through (`Fence.granting`).
    pub fn granting(
        &self,
        read: &[String],
        write: &[String],
        hosts: &[String],
        listen: &[u16],
    ) -> Fence {
        let mut wider = self.clone();
        wider.read.extend(normal(read));
        wider.write.extend(normal(write));
        wider.hosts.extend(hosts.iter().cloned());
        wider.listen.extend(listen.iter().copied());
        wider
            .settled()
            .expect("a fence widened keeps the scopes it had")
    }

    /// Whether a path, taken as it is written, is inside what this fence grants.
    pub fn allows(&self, path: &str, write: bool) -> bool {
        let held = absolute(path);
        let mut roots = self
            .write
            .iter()
            .chain(if write { [].iter() } else { self.read.iter() });
        roots.any(|root| under(&held, root))
    }

    /// Opens every directory the fence lets be written, and its tmp, as `O_PATH` descriptors,
    /// refusing a symbolic link where a fenced program could have made one (`reach`).
    pub fn ready(&self) -> io::Result<Vec<OwnedFd>> {
        Ok(self
            .reached()?
            .into_iter()
            .filter_map(|(_, fd)| fd)
            .collect())
    }

    /// What [`Fence::ready`] reaches, as `Fence.ready` returns it: each path as it was
    /// reached, links followed, in order and each once, with the descriptor holding it where
    /// this machine opens one. A path that cannot be reached is left out; the scratch is made
    /// where it is missing, and must be reached.
    pub fn reached(&self) -> io::Result<Vec<(String, Option<OwnedFd>)>> {
        let everything = self.write.iter().any(|one| one == "/");
        let mut paths: Vec<&str> = if everything {
            vec!["/"]
        } else {
            self.write.iter().map(String::as_str).collect()
        };
        if !self.tmp.is_empty() {
            paths.push(&self.tmp);
        }
        let mut reached: Vec<(String, Option<OwnedFd>)> = Vec::new();
        for path in paths {
            let scratch = path == self.tmp;
            let (fd, at) = match self.reach(path, scratch) {
                Ok(done) => done,
                Err(why) => {
                    if scratch || !errno_of(&why).is_some_and(|errno| UNREACHED.contains(&errno)) {
                        return Err(why);
                    }
                    continue;
                }
            };
            match reached.iter_mut().find(|(one, _)| *one == at) {
                Some(slot) => slot.1 = fd,
                None => reached.push((at, fd)),
            }
        }
        Ok(reached)
    }

    /// Reaches a path this fence writes from `/`, one name at a time (`Fence.reach`).
    ///
    /// A symbolic link is followed only where no fenced program could have made it: in a
    /// directory that neither this fence writes, nor holds one it writes, nor is
    /// [`TEMPORARY`], `$TMPDIR` or the scratch, told by device and inode. A fence that writes
    /// `/` follows every link. `make` makes what is missing on the way, `0700`.
    ///
    /// Returns a descriptor holding what was reached (`O_PATH`, Linux only; `None` elsewhere
    /// or where the last name is not there) and the path it was reached at.
    pub fn reach(&self, path: &str, make: bool) -> io::Result<(Option<OwnedFd>, String)> {
        let mut todo: VecDeque<OsString> = names(OsStr::new(path)).into();
        let mut at: Vec<OsString> = Vec::new();
        // What this fence writes, looked up once, the first time a link is met.
        let mut written: Option<HashSet<(u64, u64)>> = None;
        let mut fd =
            openat(cwd(), "/", search(), Mode::empty()).map_err(|errno| naming(errno, "/"))?;
        let mut chain = vec![identity(&fstat(&fd).map_err(io::Error::from)?)];
        let mut links = 0;
        let everything = self.write.iter().any(|one| one == "/");
        while let Some(name) = todo.pop_front() {
            if name == ".." {
                if !at.is_empty() {
                    fd = openat(&fd, "..", search(), Mode::empty())
                        .map_err(|errno| naming(errno, ".."))?;
                    at.pop();
                    chain.pop();
                }
                continue;
            }
            let shown = name.to_string_lossy().into_owned();
            let held = match fstatat(&fd, name.as_os_str(), AtFlags::AT_SYMLINK_NOFOLLOW) {
                Ok(held) => held,
                Err(Errno::ENOENT) => {
                    if !make {
                        // Landlock grants only what is there; Seatbelt, a name to be made.
                        if !todo.is_empty() && HAS_O_PATH {
                            return Err(naming(Errno::ENOENT, &shown));
                        }
                        let mut whole = vec![OsString::new()];
                        whole.extend(at.iter().cloned());
                        whole.push(name);
                        whole.extend(todo);
                        let whole = whole.join(OsStr::new("/"));
                        return Ok((None, normpath(&whole.to_string_lossy())));
                    }
                    match mkdirat(&fd, name.as_os_str(), Mode::from_bits_truncate(0o700)) {
                        Ok(()) | Err(Errno::EEXIST) => {}
                        Err(errno) => return Err(naming(errno, &shown)),
                    }
                    todo.push_front(name);
                    continue;
                }
                Err(errno) => return Err(naming(errno, &shown)),
            };
            if held.st_mode & libc::S_IFMT == libc::S_IFLNK {
                let written = written.get_or_insert_with(|| self.written());
                if !everything && chain.iter().any(|one| written.contains(one)) {
                    let through = if todo.is_empty() && links == 0 {
                        "it is a link".to_owned()
                    } else {
                        format!("it leads through {}, a link", joined(&at, Some(&name)))
                    };
                    return Err(io::Error::other(format!(
                        "{path}: {through} where a fenced program could have made one, which \
                         no fence follows to write"
                    )));
                }
                links += 1;
                if links > LINKS {
                    return Err(naming(Errno::ELOOP, path));
                }
                let led = nix::fcntl::readlinkat(&fd, name.as_os_str())
                    .map_err(|errno| naming(errno, &shown))?;
                if led.as_bytes().starts_with(b"/") {
                    fd = openat(cwd(), "/", search(), Mode::empty())
                        .map_err(|errno| naming(errno, "/"))?;
                    at.clear();
                    chain.truncate(1);
                }
                for one in names(&led).into_iter().rev() {
                    todo.push_front(one);
                }
                continue;
            }
            if todo.is_empty() {
                let fd = holding(&name, &shown, &fd, &held)?;
                return Ok((fd, joined(&at, Some(&name))));
            }
            // Not following a link swapped in since it was looked at: that fails here.
            fd = openat(
                &fd,
                name.as_os_str(),
                search() | OFlag::O_DIRECTORY | OFlag::O_NOFOLLOW,
                Mode::empty(),
            )
            .map_err(|errno| naming(errno, &shown))?;
            at.push(name);
            chain.push(identity(&fstat(&fd).map_err(io::Error::from)?));
        }
        let seen = fstat(&fd).map_err(io::Error::from)?;
        let held = holding(OsStr::new("."), ".", &fd, &seen)?;
        Ok((held, joined(&at, None)))
    }

    /// What a fenced program could change, a directory or one above it being among which
    /// makes a link in it one such a program could have made: the directories this fence
    /// writes, looked up as they stand now (`Fence._written`).
    fn written(&self) -> HashSet<(u64, u64)> {
        let tmp = (!self.tmp.is_empty()).then(|| self.tmp.clone());
        self.write
            .iter()
            .cloned()
            .chain(temporary())
            .chain(tmp)
            .filter_map(|root| nix::sys::stat::stat(root.as_str()).ok())
            .map(|seen| identity(&seen))
            .collect()
    }
}

/// The working directory, as a descriptor `openat` takes for an absolute path.
fn cwd() -> std::os::fd::BorrowedFd<'static> {
    // SAFETY: AT_FDCWD is a sentinel the kernel reads as "the working directory", never
    // closed.
    unsafe { std::os::fd::BorrowedFd::borrow_raw(libc::AT_FDCWD) }
}

/// A descriptor holding what was looked at, where this machine opens one to grant; opened
/// without following a link, so one swapped in since is refused (`_held`).
fn holding(
    name: &OsStr,
    shown: &str,
    directory: &impl AsFd,
    seen: &FileStat,
) -> io::Result<Option<OwnedFd>> {
    #[cfg(target_os = "linux")]
    {
        let fd = openat(
            directory,
            name,
            OFlag::O_PATH | OFlag::O_NOFOLLOW | OFlag::O_CLOEXEC,
            Mode::empty(),
        )
        .map_err(|errno| naming(errno, shown))?;
        if identity(&fstat(&fd).map_err(io::Error::from)?) != identity(seen) {
            return Err(os_said(
                libc::ELOOP,
                "it was replaced while it was reached",
                shown,
            ));
        }
        Ok(Some(fd))
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = (name, shown, directory, seen);
        Ok(None)
    }
}

#[allow(clippy::unnecessary_cast)] // the types differ by platform
fn identity(seen: &FileStat) -> (u64, u64) {
    (seen.st_dev as u64, seen.st_ino as u64)
}

/// `/` followed by `at` and `last`, as `str(Path("/", *at, last))`.
fn joined(at: &[OsString], last: Option<&OsString>) -> String {
    let mut whole = String::new();
    for one in at.iter().chain(last) {
        whole.push('/');
        whole.push_str(&one.to_string_lossy());
    }
    if whole.is_empty() { "/".into() } else { whole }
}

/// The names a path is looked up by, in order, `..` kept as the kernel keeps it (`_names`).
fn names(path: &OsStr) -> Vec<OsString> {
    path.as_bytes()
        .split(|byte| *byte == b'/')
        .filter(|one| !one.is_empty() && *one != b".")
        .map(|one| OsStr::from_bytes(one).to_owned())
        .collect()
}

/// `os.path.normpath`, as POSIX Python spells it.
pub fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".into();
    }
    let initial = if path.starts_with("//") && !path.starts_with("///") {
        2
    } else if path.starts_with('/') {
        1
    } else {
        0
    };
    let mut kept: Vec<&str> = Vec::new();
    for one in path.split('/') {
        if one.is_empty() || one == "." {
            continue;
        }
        if one != ".." || (initial == 0 && kept.is_empty()) || kept.last() == Some(&"..") {
            kept.push(one);
        } else if !kept.is_empty() {
            kept.pop();
        }
    }
    let whole = format!("{}{}", "/".repeat(initial), kept.join("/"));
    if whole.is_empty() { ".".into() } else { whole }
}

/// `os.path.normpath(os.path.abspath(path))`.
pub fn absolute(path: &str) -> String {
    if path.starts_with('/') {
        return normpath(path);
    }
    let here = std::env::current_dir()
        .map(|dir| dir.to_string_lossy().into_owned())
        .unwrap_or_else(|_| "/".into());
    normpath(&format!("{here}/{path}"))
}

/// Paths as a fence holds them: absolute, with no `..`, each once, in order (`_normal`).
pub fn normal(paths: &[String]) -> Vec<String> {
    once(paths.iter().map(|one| absolute(one)).collect())
}

fn once<T: PartialEq>(items: Vec<T>) -> Vec<T> {
    let mut kept: Vec<T> = Vec::with_capacity(items.len());
    for one in items {
        if !kept.contains(&one) {
            kept.push(one);
        }
    }
    kept
}

/// Whether `path` is `root` or beneath it (`_under`).
pub fn under(path: &str, root: &str) -> bool {
    path == root || path.starts_with(&format!("{}/", root.trim_end_matches('/')))
}

/// A list of strings as Python's `repr` of a tuple spells it.
fn python_tuple(items: &[String]) -> String {
    let inner: Vec<String> = items.iter().map(|one| format!("'{one}'")).collect();
    if inner.len() == 1 {
        format!("({},)", inner[0])
    } else {
        format!("({})", inner.join(", "))
    }
}

/// [`TEMPORARY`], and the directory `TMPDIR` names where it is absolute (`_temporary`).
pub fn temporary() -> Vec<String> {
    let mut held: Vec<String> = TEMPORARY.iter().map(|one| (*one).to_owned()).collect();
    if let Ok(named) = std::env::var("TMPDIR")
        && named.starts_with('/')
    {
        held.push(named);
    }
    held
}

/// Everything the user the fence is drawn as may change (`_users`): the whole filesystem,
/// held by its own permissions, for anyone but root; for root, its scratch and runtime
/// directory.
fn users() -> Vec<String> {
    let uid = nix::unistd::geteuid().as_raw();
    if uid != 0 {
        return vec!["/".into()];
    }
    let mut held = temporary();
    held.push(format!("/run/user/{uid}"));
    held
}

/// The GPUs' device nodes on this machine (`_accelerators`).
fn accelerators() -> Vec<String> {
    let mut nodes: Vec<String> = std::fs::read_dir("/dev")
        .map(|entries| {
            entries
                .filter_map(Result::ok)
                .map(|entry| entry.file_name().to_string_lossy().into_owned())
                .filter(|name| name.starts_with("nvidia"))
                .map(|name| format!("/dev/{name}"))
                .collect()
        })
        .unwrap_or_default();
    nodes.sort();
    nodes.extend(
        ["/dev/dri", "/dev/kfd", "/dev/infiniband"]
            .iter()
            .map(|one| (*one).to_owned()),
    );
    nodes
}

/// Where this program is, read inside every fence (`_ours`): coganchor runs inside the
/// fences it draws, as `internal cred` around a CLI or as a fence nested in one. Python
/// granted its interpreter and the `hmz` package; this program is one file, and the directory
/// it was installed in.
fn ours() -> Vec<String> {
    let Ok(exe) = std::env::current_exe() else {
        return Vec::new();
    };
    let real = std::fs::canonicalize(&exe).unwrap_or(exe);
    // Never `/` or the home themselves, as `_tree` grants a program's: a binary put there
    // would otherwise open the whole of either.
    let home = crate::fence::wrap::home();
    match real.parent() {
        Some(dir) if dir != Path::new("/") && dir != Path::new(&home) => {
            vec![dir.to_string_lossy().into_owned()]
        }
        _ => vec![real.to_string_lossy().into_owned()],
    }
}

/// A JSON object's member as Python's truthiness reads it.
pub(crate) fn truthy(said: &Map<String, Value>, name: &str) -> bool {
    match said.get(name) {
        None | Some(Value::Null) => false,
        Some(Value::Bool(one)) => *one,
        Some(Value::Number(one)) => one.as_f64() != Some(0.0),
        Some(Value::String(one)) => !one.is_empty(),
        Some(Value::Array(one)) => !one.is_empty(),
        Some(Value::Object(one)) => !one.is_empty(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keys_keep_python_order_and_defaults() {
        let fence = Fence::loads("{}").unwrap();
        assert_eq!(
            fence.dumps(),
            r#"{"read":[],"write":[],"online":true,"hosts":[],"tmp":"","scopes":[],"listen":[]}"#
        );
    }

    #[test]
    fn unknown_keys_and_wrong_types_are_refused() {
        assert_eq!(
            Fence::loads(r#"{"x":1,"a":2}"#).unwrap_err(),
            "not a fence's: a, x"
        );
        assert_eq!(
            Fence::loads(r#"{"read":"/"}"#).unwrap_err(),
            "a fence's read is a list of strings"
        );
        assert_eq!(
            Fence::loads(r#"{"listen":[true]}"#).unwrap_err(),
            "a fence's listen is a list of ports"
        );
        assert_eq!(
            Fence::loads(r#"{"online":1}"#).unwrap_err(),
            "a fence's online is true or false"
        );
        assert_eq!(
            Fence::loads(r#"{"tmp":1}"#).unwrap_err(),
            "a fence's tmp is a path"
        );
        assert_eq!(Fence::loads("[]").unwrap_err(), "a fence is a JSON object");
        assert!(
            Fence::loads(r#"{"scopes":["all"]}"#)
                .unwrap_err()
                .starts_with("a fence's scopes are three of none, read, all")
        );
    }

    #[test]
    fn paths_are_settled_as_post_init_settles_them() {
        let fence = Fence::loads(
            r#"{"read":["/a/../b","/c","/c/"],"write":["/c"],"hosts":["h","h"],"listen":[8,8]}"#,
        )
        .unwrap();
        assert_eq!(fence.read, vec!["/b"]);
        assert_eq!(fence.write, vec!["/c"]);
        assert_eq!(fence.hosts, vec!["h"]);
        assert_eq!(fence.listen, vec![8]);
    }

    #[test]
    fn a_policy_is_read_from_a_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("p.json");
        std::fs::write(&path, r#"{"online":false}"#).unwrap();
        let fence = Fence::loads(&format!("@{}", path.display())).unwrap();
        assert!(!fence.online);
    }

    #[test]
    fn normpath_matches_python() {
        assert_eq!(normpath("//a//b/../c/."), "//a/c");
        assert_eq!(normpath("///a"), "/a");
        assert_eq!(normpath("/.."), "/");
        assert_eq!(normpath("a/../.."), "..");
        assert_eq!(normpath(""), ".");
    }

    #[test]
    fn scopes_must_nest() {
        let none: [String; 0] = [];
        assert!(Fence::of("read", "all", "none", true, "/w", "/h", &none, &none, &none).is_err());
        let fence =
            Fence::of("all", "read", "none", true, "/w", "/h", &none, &none, &none).unwrap();
        assert!(fence.write.contains(&"/w".to_owned()));
        assert!(fence.write.contains(&"/tmp".to_owned()));
        assert!(fence.read.contains(&"/h".to_owned()));
        assert_eq!(fence.scopes, vec!["all", "read", "none"]);
        assert!(fence.allows("/w/x", true));
        assert!(!fence.allows("/h/x", true));
        assert!(fence.allows("/h/x", false));
    }

    #[test]
    fn reach_refuses_a_link_in_a_directory_the_fence_writes() {
        // Not under a temporary directory, which every fence counts as written.
        let dir = tempfile::tempdir_in(env!("CARGO_MANIFEST_DIR")).unwrap();
        let root = std::fs::canonicalize(dir.path()).unwrap();
        let state = root.join("state");
        std::fs::create_dir(&state).unwrap();
        std::fs::create_dir(root.join("elsewhere")).unwrap();
        std::os::unix::fs::symlink(root.join("elsewhere"), state.join("scratch")).unwrap();
        let fence = Fence {
            write: vec![state.to_string_lossy().into_owned()],
            ..Fence::default()
        };
        let why = fence
            .reach(&state.join("scratch").to_string_lossy(), false)
            .unwrap_err();
        assert!(
            why.to_string()
                .contains("a link where a fenced program could have made one"),
            "{why}"
        );
        // Outside what the fence writes, the same link is followed.
        let (_, at) = Fence::default()
            .reach(&state.join("scratch").to_string_lossy(), false)
            .unwrap();
        assert_eq!(at, root.join("elsewhere").to_string_lossy());
    }

    #[test]
    fn reach_makes_what_is_missing() {
        let dir = tempfile::tempdir().unwrap();
        let root = std::fs::canonicalize(dir.path()).unwrap();
        let path = root.join("a/b");
        let (_, at) = Fence::default()
            .reach(&path.to_string_lossy(), true)
            .unwrap();
        assert_eq!(at, path.to_string_lossy());
        assert!(path.is_dir());
    }
}
