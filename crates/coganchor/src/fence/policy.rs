//! A fence, as the JSON `hmz` hands it over. Port of `Fence` in `hmz.coganchor.fence`.
//! [Unit 4]
//!
//! Besides reading and writing the JSON, this is where a fence is drawn from last-wins rules
//! ([`Fence::of`], for [`crate::fence::abroad`]), where a path's level is read off its grants and
//! carve-outs ([`Fence::level`]), and where what it writes is reached, one name at a time and
//! through no link a fenced program could have made ([`Fence::reach`]), just before a program is
//! walled in.

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

use super::seatbelt::realpath;

/// How much of a path a fence grants, narrowest first (`NONE`, `READ`, `WRITE`): the words a
/// rule's access is spelled with.
pub const NONE: &str = "none";
pub const READ: &str = "read";
pub const WRITE: &str = "write";
pub const LEVELS: [&str; 3] = [NONE, READ, WRITE];

/// How a rule's path is anchored: at the root, at the home of the user the agent runs as, or
/// at the workdir (`_ROOT`, `_HOME`, `_WORKDIR`).
const ROOT: &str = "/";
const HOMED: &str = "~";
const WORKDIR: &str = ".";

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

/// The same on a Mac (`DARWIN_SYSTEM`), the developer tools Apple's `xcrun` shims load
/// included: the link `xcode-select` keeps, the Command Line Tools, and the whole of Xcode with
/// the plist its license is checked against.
pub const DARWIN_SYSTEM: &[&str] = &[
    "/usr",
    "/bin",
    "/sbin",
    "/System",
    "/private/var/select",
    "/private/var/db/timezone",
    XCODE_SELECT,
    "/Library/Developer/CommandLineTools",
    "/Library/Preferences/com.apple.dt.Xcode.plist",
    "/Applications/Xcode.app",
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

/// The link `xcode-select` keeps to the developer directory it chose (`_XCODE_SELECT`).
const XCODE_SELECT: &str = "/private/var/db/xcode_select_link";

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
///
/// A path grants everything beneath it: `read` to read, list and run, `write` to change as
/// well. Beneath them, `keep` holds a path to reading and `deny` keeps it out of reach. A
/// path's level is read from the paths in all four it is at or beneath ([`Fence::level`]).
/// `drawn` is the rules it was drawn from, each `(path, access)` anchored at `/`, `~` or `.`,
/// which another machine draws it again from.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct Fence {
    pub read: Vec<String>,
    pub write: Vec<String>,
    pub keep: Vec<String>,
    pub deny: Vec<String>,
    pub online: bool,
    pub hosts: Vec<String>,
    pub tmp: String,
    pub drawn: Vec<(String, String)>,
    pub listen: Vec<u16>,
}

impl Default for Fence {
    /// A fence of nothing: online, as Python's `Fence()` is.
    fn default() -> Fence {
        Fence {
            read: Vec::new(),
            write: Vec::new(),
            keep: Vec::new(),
            deny: Vec::new(),
            online: true,
            hosts: Vec::new(),
            tmp: String::new(),
            drawn: Vec::new(),
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
            "read", "write", "keep", "deny", "online", "hosts", "tmp", "drawn", "listen",
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
        let (read, write, keep, deny, hosts) = (
            strings("read")?,
            strings("write")?,
            strings("keep")?,
            strings("deny")?,
            strings("hosts")?,
        );
        let drawn = match held.get("drawn") {
            None => Vec::new(),
            Some(said) => rules(said).ok_or("a fence's drawn is a list of [path, access]")?,
        };
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
            keep,
            deny,
            online,
            hosts,
            tmp,
            drawn,
            listen,
        }
        .settled()
    }

    /// The fence as JSON.
    pub fn dumps(&self) -> String {
        serde_json::to_string(self).expect("a fence always serialises")
    }

    /// What `Fence.__post_init__` makes of one: the paths absolute, normal and each once, a
    /// path to write taken out of those to read and a path denied out of those kept, hosts and
    /// ports each once, and each rule's path anchored and its access one of [`LEVELS`].
    pub fn settled(mut self) -> Result<Fence, String> {
        self.write = normal(&self.write);
        self.read = normal(&self.read)
            .into_iter()
            .filter(|one| !self.write.contains(one))
            .collect();
        self.deny = normal(&self.deny);
        self.keep = normal(&self.keep)
            .into_iter()
            .filter(|one| !self.deny.contains(one))
            .collect();
        self.hosts = once(self.hosts);
        self.drawn = self
            .drawn
            .into_iter()
            .map(|(path, access)| {
                rank(&access)?;
                Ok((anchored(&path)?, access))
            })
            .collect::<Result<_, String>>()?;
        self.listen = once(self.listen);
        Ok(self)
    }

    /// The fence last-wins rules come to, with the minimum every program needs to run
    /// (`Fence.of`).
    ///
    /// Each rule is a path anchored at `/`, `~` (`home`) or `.` (`workdir`, and `cwd` as well
    /// where it is given), and an access, one of [`LEVELS`]; the last rule that holds a path
    /// decides it. What is left is put in the fence by longest prefix, then the minimum is
    /// granted over it: [`SYSTEM`], the developer directory a Mac's `xcode-select` chose and
    /// this program to read, [`DEVICES`] and the GPUs' nodes to
    /// write; [`TEMPORARY`] to write where the workdir is written, and everything the user may
    /// change where the home is written by a rule at it or above it.
    #[allow(clippy::too_many_arguments)]
    pub fn of(
        rules: &[(String, String)],
        online: bool,
        workdir: &str,
        home: &str,
        cwd: &str,
        hosts: &[String],
        read: &[String],
        write: &[String],
    ) -> Result<Fence, String> {
        let drawn: Vec<(String, String)> = rules
            .iter()
            .map(|(path, access)| Ok((anchored(path)?, access.clone())))
            .collect::<Result<_, String>>()?;
        let mut dots = vec![workdir.to_owned()];
        if !cwd.is_empty() {
            dots.push(cwd.to_owned());
        }
        let dots = normal(&dots);
        let homed = if home.is_empty() {
            String::new()
        } else {
            absolute(home)
        };
        let held = compiled(&drawn, &dots, &homed)?;
        let mut writing: Vec<String> = Vec::new();
        if deepest(&held, &dots[0]) == WRITE {
            writing.extend(temporary());
        }
        // The home written as the home, and not as a workdir it happens to be inside.
        let users_rules: Vec<(String, String)> = drawn
            .iter()
            .filter(|(path, _)| anchor_of(path) != WORKDIR)
            .cloned()
            .collect();
        if !homed.is_empty()
            && deepest(&held, &homed) == WRITE
            && deepest(&compiled(&users_rules, &dots, &homed)?, &homed) == WRITE
        {
            writing.extend(users());
        }
        // Granted before the rules are set against them, so that a rule carves out what it
        // holds beneath them and loses to them at their own path: the deeper decides, and at
        // one depth the wider.
        let fence = Fence {
            online,
            hosts: hosts.to_vec(),
            drawn,
            ..Fence::default()
        }
        .settled()?
        .granting(&[], &writing, &[], &[]);
        let mut reading: Vec<String> = SYSTEM.iter().map(|one| (*one).to_owned()).collect();
        reading.extend(developer());
        reading.extend(ours());
        reading.extend(read.iter().cloned());
        let mut writing: Vec<String> = DEVICES.iter().map(|one| (*one).to_owned()).collect();
        writing.extend(accelerators());
        writing.extend(write.iter().cloned());
        Ok(fence.at(&held).granting(&reading, &writing, &[], &[]))
    }

    /// This fence with each path compiled rules land on held at their access (`Fence._at`).
    ///
    /// Shallowest first, so that each is set against what those above it already gave: a level
    /// wider than that is granted, one narrower is carved out, and one the same needs nothing.
    fn at(&self, held: &[(String, String)]) -> Fence {
        let mut order: Vec<&(String, String)> = held.iter().collect();
        order.sort_by_key(|(path, _)| depth(path));
        let mut fence = self.clone();
        for (path, access) in order {
            let want = rank(access).unwrap_or(0);
            let now = rank(fence.level(path)).unwrap_or(0);
            let one = std::slice::from_ref(path);
            if want > now {
                fence = if LEVELS[want] == WRITE {
                    fence.granting(&[], one, &[], &[])
                } else {
                    fence.granting(one, &[], &[], &[])
                };
            } else if fence.write.contains(path) {
                // Written at that very path, which a carve-out there could not take back.
            } else if want < now && LEVELS[want] == READ {
                fence.keep.push(path.clone());
                fence = fence.settled().expect("a fence carved keeps its rules");
            } else if want < now {
                fence.deny.push(path.clone());
                fence = fence.settled().expect("a fence carved keeps its rules");
            }
        }
        fence
    }

    /// This fence with another directory drawn as its workdir is, too (`Fence.beside`): the
    /// access `.` has, at `path`, and every rule beneath `.`, beneath it. What a mirror of the
    /// workspace, or a second directory a target exports, is drawn with. A fence drawn path by
    /// path is this one.
    pub fn beside(&self, path: &str, home: &str) -> Fence {
        if self.drawn.is_empty() {
            return self.clone();
        }
        let at = absolute(path);
        let homed = if home.is_empty() {
            String::new()
        } else {
            absolute(home)
        };
        let held = compiled(&self.drawn, std::slice::from_ref(&at), &homed)
            .expect("a fence's rules are settled");
        let mut beneath: Vec<(String, String)> = held
            .iter()
            .filter(|(one, _)| under(one, &at))
            .cloned()
            .collect();
        let level = deepest(&held, &at).to_owned();
        match beneath.iter_mut().find(|(one, _)| *one == at) {
            Some(slot) => slot.1 = level,
            None => beneath.push((at, level)),
        }
        self.at(&beneath)
    }

    /// Whether this fences nothing at all: the whole filesystem to write, nothing carved out
    /// of it, and the network (`Fence.open`).
    pub fn open(&self) -> bool {
        self.online
            && self.write.iter().any(|one| one == "/")
            && self.keep.is_empty()
            && self.deny.is_empty()
    }

    /// This fence with more let through (`Fence.granting`). A path granted here is granted
    /// whatever is carved out above it, being the deeper.
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
            .expect("a fence widened keeps the rules it had")
    }

    /// How much of a path this fence grants, carve-outs and all (`Fence.level`): the paths in
    /// all four it is at or beneath, shallowest first and at one depth a carve-out before a
    /// grant, each grant raising it and each carve-out holding it down. The path is taken as it
    /// is written: a link in it is not followed.
    pub fn level(&self, path: &str) -> &'static str {
        let held = absolute(path);
        let mut over: Vec<(usize, bool, usize)> = [
            (&self.deny, false, 0),
            (&self.keep, false, 1),
            (&self.read, true, 1),
            (&self.write, true, 2),
        ]
        .into_iter()
        .flat_map(|(roots, granted, given)| {
            roots
                .iter()
                .filter(|root| under(&held, root))
                .map(move |root| (depth(root), granted, given))
        })
        .collect();
        over.sort_by_key(|(depth, granted, _)| (*depth, *granted));
        let mut level = 0;
        for (_, granted, given) in over {
            level = if granted {
                level.max(given)
            } else {
                level.min(given)
            };
        }
        LEVELS[level]
    }

    /// Whether a path, taken as it is written, is inside what this fence grants and not carved
    /// out of it (`Fence.allows`).
    pub fn allows(&self, path: &str, write: bool) -> bool {
        rank(self.level(path)).unwrap_or(0) >= if write { 2 } else { 1 }
    }

    /// Opens every directory the fence lets be written -- or `paths` in its place, the entries
    /// a wall that cannot carve out of a grant grants instead ([`crate::fence::wrap::expanded`])
    /// -- and its tmp, as `O_PATH` descriptors, refusing a symbolic link where a fenced program
    /// could have made one (`reach`).
    pub fn ready(&self, paths: Option<&[String]>) -> io::Result<Vec<OwnedFd>> {
        Ok(self
            .reached(paths)?
            .into_iter()
            .filter_map(|(_, fd)| fd)
            .collect())
    }

    /// What [`Fence::ready`] reaches, as `Fence.ready` returns it: each path as it was
    /// reached, links followed, in order and each once, with the descriptor holding it where
    /// this machine opens one. A path that cannot be reached is left out; the scratch is made
    /// where it is missing, and must be reached. A fence that writes `/` reaches `/`, and what
    /// is granted again beneath a carve-out.
    pub fn reached(&self, paths: Option<&[String]>) -> io::Result<Vec<(String, Option<OwnedFd>)>> {
        let granted = paths.map_or_else(|| self.write.clone(), normal);
        let carved: Vec<&String> = self.keep.iter().chain(&self.deny).collect();
        let mut paths: Vec<&str> = if granted.iter().any(|one| one == "/") {
            std::iter::once("/")
                .chain(
                    granted
                        .iter()
                        .filter(|one| carved.iter().any(|cut| under(one, cut)))
                        .map(String::as_str),
                )
                .collect()
        } else {
            granted.iter().map(String::as_str).collect()
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
    /// `/` follows every link -- but where it carves something out, a link made anywhere could
    /// lead into that, so what it leads to has to be what this fence writes, as it is spelled
    /// once reached. `make` makes what is missing on the way, `0700`.
    ///
    /// Returns a descriptor holding what was reached (`O_PATH`, Linux only; `None` elsewhere
    /// or where the last name is not there) and the path it was reached at.
    pub fn reach(&self, path: &str, make: bool) -> io::Result<(Option<OwnedFd>, String)> {
        let (fd, at) = self.reached_at(path, make)?;
        if self.write.iter().any(|one| one == "/")
            && !(self.keep.is_empty() && self.deny.is_empty())
            && self.level(&at) != WRITE
        {
            return Err(io::Error::other(format!(
                "{path}: it leads to {at}, which is carved out of this fence"
            )));
        }
        Ok((fd, at))
    }

    /// [`Fence::reach`], less what it asks of where it led (`Fence._reach`).
    fn reached_at(&self, path: &str, make: bool) -> io::Result<(Option<OwnedFd>, String)> {
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

/// Where a level stands among [`LEVELS`], or a refusal of what is not one (`_rank`).
pub fn rank(level: &str) -> Result<usize, String> {
    LEVELS.iter().position(|one| *one == level).ok_or_else(|| {
        format!(
            "a rule's access is one of {}, not '{level}'",
            LEVELS.join(", ")
        )
    })
}

/// What a rule's path is anchored at: `""` for `/`, `~` or `.`.
fn anchor_of(path: &str) -> &str {
    path.split_once('/').map_or(path, |(head, _)| head)
}

/// A rule's path as a fence holds it, tidied; or a refusal of one that is not anchored
/// (`_anchored`): `/abs`, `~` or `~/...`, `.` or `./...`, naming no `..`.
pub fn anchored(said: &str) -> Result<String, String> {
    let (head, rest) = said.split_once('/').unwrap_or((said, ""));
    if said.is_empty()
        || !["", HOMED, WORKDIR].contains(&head)
        || said.split('/').any(|one| one == "..")
    {
        return Err(format!(
            "a rule's path is /..., ~, ~/..., . or ./..., with no '..'; not '{said}'"
        ));
    }
    let tidy = if rest.trim_matches('/').is_empty() {
        String::new()
    } else {
        normpath(rest).trim_matches('/').to_owned()
    };
    let tidy = if tidy == "." { String::new() } else { tidy };
    Ok(if head.is_empty() {
        format!("{ROOT}{tidy}")
    } else if tidy.is_empty() {
        head.to_owned()
    } else {
        format!("{head}/{tidy}")
    })
}

/// Where an anchored path lies on this machine: one path, or one per workdir for `.`
/// (`_resolved`).
fn resolved(path: &str, dots: &[String], home: &str) -> Vec<String> {
    let (head, rest) = path.split_once('/').unwrap_or((path, ""));
    if head.is_empty() {
        return vec![normpath(path)];
    }
    let roots: Vec<&str> = if head == WORKDIR {
        dots.iter().map(String::as_str).collect()
    } else if home.is_empty() {
        Vec::new()
    } else {
        vec![home]
    };
    roots
        .into_iter()
        .map(|root| normpath(&joined_to(root, rest)))
        .collect()
}

/// How many names deep a path is (`_depth`).
pub(crate) fn depth(path: &str) -> usize {
    names(OsStr::new(path)).len()
}

/// What last-wins rules come to: each path a rule lands on, with its access, in the order
/// they were last set (`_compiled`). A rule decides its path and everything beneath it, so a
/// later one takes away every earlier one at or beneath where it lands.
fn compiled(
    rules: &[(String, String)],
    dots: &[String],
    home: &str,
) -> Result<Vec<(String, String)>, String> {
    let mut held: Vec<(String, String)> = Vec::new();
    for (path, access) in rules {
        rank(access)?;
        for root in resolved(path, dots, home) {
            held.retain(|(one, _)| !under(one, &root));
            held.push((root, access.clone()));
        }
    }
    Ok(held)
}

/// The access compiled rules give a path: that of the deepest one it is at or beneath, and
/// none beneath none (`_deepest`).
fn deepest<'a>(held: &'a [(String, String)], path: &str) -> &'a str {
    held.iter()
        .filter(|(one, _)| under(path, one))
        .max_by_key(|(one, _)| depth(one))
        .map_or(NONE, |(_, access)| access.as_str())
}

/// Rules as JSON says them, `[[path, access], ...]`; None for anything else.
pub(crate) fn rules(said: &Value) -> Option<Vec<(String, String)>> {
    said.as_array()?
        .iter()
        .map(|one| match one.as_array()?.as_slice() {
            [Value::String(path), Value::String(access)] => Some((path.clone(), access.clone())),
            _ => None,
        })
        .collect()
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
    normpath(&joined_to(&here, path))
}

/// `os.path.join(root, rest)` for a relative `rest`: no second `/` after a root that ends in
/// one, which `normpath` would keep as POSIX's `//`.
fn joined_to(root: &str, rest: &str) -> String {
    if root.ends_with('/') {
        format!("{root}{rest}")
    } else {
        format!("{root}/{rest}")
    }
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

/// [`TEMPORARY`], and the directory `TMPDIR` names where it is absolute (`_temporary`): each
/// as it is spelled and with its links followed, which is how the kernel holds it and how a
/// path found beneath it is spelled -- a Mac's `/tmp` is `/private/tmp` -- so that a rule
/// spelled either way is beneath the grant and carves out of it.
pub fn temporary() -> Vec<String> {
    let mut spelled: Vec<String> = TEMPORARY.iter().map(|one| (*one).to_owned()).collect();
    if let Ok(named) = std::env::var("TMPDIR")
        && named.starts_with('/')
    {
        spelled.push(named);
    }
    let mut held: Vec<String> = Vec::new();
    for path in spelled {
        for one in [path.clone(), realpath(&path)] {
            if !held.contains(&one) {
                held.push(one);
            }
        }
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

/// The developer directory `xcode-select` chose, on a Mac, where it is not already read
/// (`_developer`): read off the link rather than by running `xcode-select -p`, and the whole
/// app where it is inside one.
fn developer() -> Vec<String> {
    if !cfg!(target_os = "macos") {
        return Vec::new();
    }
    let Ok(chosen) = std::fs::canonicalize(XCODE_SELECT) else {
        return Vec::new();
    };
    let chosen = chosen.to_string_lossy().into_owned();
    if DARWIN_SYSTEM.iter().any(|one| under(&chosen, one)) {
        return Vec::new();
    }
    match chosen.split_once(".app/") {
        Some((app, _)) => vec![format!("{app}.app")],
        None => vec![chosen],
    }
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

    const HOME: &str = "/home/someone";
    const WORK: &str = "/home/someone/work";
    const ELSEWHERE: &str = "/srv/elsewhere/file";

    fn ruled(rules: &[(&str, &str)]) -> Vec<(String, String)> {
        rules
            .iter()
            .map(|(path, access)| ((*path).to_owned(), (*access).to_owned()))
            .collect()
    }

    fn drawn(rules: &[(&str, &str)]) -> Fence {
        Fence::of(&ruled(rules), true, WORK, HOME, "", &[], &[], &[]).unwrap()
    }

    fn paths(list: &[&str]) -> Vec<String> {
        list.iter().map(|one| (*one).to_owned()).collect()
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn a_mac_fence_reads_the_developer_tools_xcrun_loads() {
        let fence = drawn(&[(".", READ)]);
        for one in [
            "/private/var/db/xcode_select_link",
            "/Library/Developer/CommandLineTools/usr/lib/libxcrun.dylib",
            "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
        ] {
            assert!(fence.allows(one, false), "{one}");
            assert!(!fence.allows(one, true), "{one}");
        }
        if let Ok(chosen) = std::fs::canonicalize(XCODE_SELECT) {
            assert!(fence.allows(&chosen.to_string_lossy(), false));
        }
    }

    #[test]
    fn keys_keep_python_order_and_defaults() {
        let fence = Fence::loads("{}").unwrap();
        assert_eq!(
            fence.dumps(),
            r#"{"read":[],"write":[],"keep":[],"deny":[],"online":true,"hosts":[],"tmp":"","drawn":[],"listen":[]}"#
        );
        let fence = drawn(&[("/", READ), ("./secret", NONE)]);
        assert!(
            fence
                .dumps()
                .contains(r#""drawn":[["/","read"],["./secret","none"]]"#)
        );
        assert_eq!(Fence::loads(&fence.dumps()).unwrap(), fence);
    }

    #[test]
    fn unknown_keys_and_wrong_types_are_refused() {
        assert_eq!(
            Fence::loads(r#"{"x":1,"a":2}"#).unwrap_err(),
            "not a fence's: a, x"
        );
        assert_eq!(
            Fence::loads(r#"{"scopes":[]}"#).unwrap_err(),
            "not a fence's: scopes"
        );
        assert_eq!(
            Fence::loads(r#"{"read":"/"}"#).unwrap_err(),
            "a fence's read is a list of strings"
        );
        assert_eq!(
            Fence::loads(r#"{"deny":[1]}"#).unwrap_err(),
            "a fence's deny is a list of strings"
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
        for drawn in [r#""/""#, r#"[["/"]]"#, r#"[["/", 1]]"#, r#"["/"]"#] {
            assert_eq!(
                Fence::loads(&format!(r#"{{"drawn":{drawn}}}"#)).unwrap_err(),
                "a fence's drawn is a list of [path, access]"
            );
        }
        assert_eq!(
            Fence::loads(r#"{"drawn":[["/","all"]]}"#).unwrap_err(),
            "a rule's access is one of none, read, write, not 'all'"
        );
        assert!(
            Fence::loads(r#"{"drawn":[["relative","read"]]}"#)
                .unwrap_err()
                .starts_with("a rule's path is")
        );
    }

    #[test]
    fn paths_are_settled_as_post_init_settles_them() {
        let fence = Fence::loads(
            r#"{"read":["/a/../b","/c","/c/"],"write":["/c"],"keep":["/k","/d"],"deny":["/d/"],
                "hosts":["h","h"],"listen":[8,8]}"#,
        )
        .unwrap();
        assert_eq!(fence.read, vec!["/b"]);
        assert_eq!(fence.write, vec!["/c"]);
        assert_eq!(fence.keep, vec!["/k"]);
        assert_eq!(fence.deny, vec!["/d"]);
        assert_eq!(fence.hosts, vec!["h"]);
        assert_eq!(fence.listen, vec![8]);
    }

    #[test]
    fn a_rules_path_is_held_tidy_or_refused() {
        for (said, held) in [
            ("/", "/"),
            ("//a//b/", "/a/b"),
            ("~", "~"),
            ("~/", "~"),
            ("~/a/./b", "~/a/b"),
            (".", "."),
            ("./", "."),
            ("./a//b/", "./a/b"),
        ] {
            assert_eq!(
                drawn(&[(said, READ)]).drawn,
                ruled(&[(held, READ)]),
                "{said}"
            );
        }
        for said in ["a", "a/b", "~user", "~user/x", "../x", "./a/../b", ""] {
            let why = Fence::of(&ruled(&[(said, READ)]), true, WORK, HOME, "", &[], &[], &[])
                .unwrap_err();
            assert!(why.starts_with("a rule's path"), "{said}: {why}");
        }
        let why =
            Fence::of(&ruled(&[("/", "all")]), true, WORK, HOME, "", &[], &[], &[]).unwrap_err();
        assert!(why.contains("none, read, write"), "{why}");
    }

    #[test]
    fn each_anchor_grants_its_root_at_its_access() {
        let fence = drawn(&[("/", READ), ("~", READ), (".", WRITE)]);
        assert_eq!(fence.level(&format!("{WORK}/a")), WRITE);
        assert_eq!(fence.level(&format!("{HOME}/a")), READ);
        assert_eq!(fence.level(ELSEWHERE), READ);
        assert!(
            fence.write.contains(&"/tmp".to_owned()),
            "a written workdir writes /tmp"
        );
        let none = drawn(&[("/", NONE), ("~", NONE), (".", READ)]);
        assert_eq!(none.level(ELSEWHERE), NONE);
        assert_eq!(none.level(&format!("{WORK}/a")), READ);
        assert!(none.allows("/usr/bin/env", false), "the minimum is granted");
        assert!(none.allows("/dev/null", true));
    }

    #[test]
    fn the_last_rule_that_holds_a_path_decides_it() {
        let fence = drawn(&[
            ("/", READ),
            (".", WRITE),
            ("./secret", NONE),
            ("./ro", READ),
            ("./ro/scratch", WRITE),
            ("~/.ssh", NONE),
        ]);
        assert_eq!(fence.level(&format!("{WORK}/src/main.py")), WRITE);
        assert_eq!(fence.level(&format!("{WORK}/secret/key")), NONE);
        assert_eq!(fence.level(&format!("{WORK}/ro/notes")), READ);
        assert_eq!(fence.level(&format!("{WORK}/ro/scratch/out")), WRITE);
        assert_eq!(fence.level(&format!("{HOME}/.ssh/id_ed25519")), NONE);
        assert_eq!(fence.level(&format!("{HOME}/.bashrc")), READ);
        assert_eq!(fence.keep, paths(&[&format!("{WORK}/ro")]));
        assert_eq!(
            fence.deny,
            paths(&[&format!("{HOME}/.ssh"), &format!("{WORK}/secret")])
        );
    }

    #[test]
    fn a_later_rule_takes_away_every_earlier_one_beneath_it() {
        let fence = drawn(&[("./secret", NONE), (".", WRITE), ("/", READ)]);
        assert_eq!(fence.level(&format!("{WORK}/secret/key")), READ);
        assert_eq!(fence.level(&format!("{WORK}/src")), READ);
        assert!(fence.keep.is_empty() && fence.deny.is_empty());
        assert!(!fence.allows("/tmp/x", true));
        // The home's rule takes the workdir beneath it with it.
        assert_eq!(
            drawn(&[("/", READ), (".", WRITE), ("~", READ)]).level(WORK),
            READ
        );
        assert_eq!(
            drawn(&[("/", READ), ("~", READ), (".", WRITE)]).level(WORK),
            WRITE
        );
    }

    #[test]
    fn a_rule_at_a_temporary_loses_to_it_and_one_beneath_it_wins() {
        let at = drawn(&[("/", READ), (".", WRITE), ("/tmp", NONE)]);
        let beneath = drawn(&[
            ("/", READ),
            (".", WRITE),
            ("/tmp", NONE),
            ("/tmp/x", NONE),
            ("/var/tmp/y", READ),
        ]);
        assert!(at.allows("/tmp/a", true));
        assert!(beneath.allows("/tmp/a", true));
        assert_eq!(beneath.level("/tmp/x/key"), NONE);
        assert_eq!(beneath.level("/var/tmp/y/z"), READ);
        assert!(beneath.allows("/var/tmp/z", true));
    }

    #[test]
    fn a_rule_beneath_a_temporary_as_its_links_lead_is_carved_out_of_it() {
        for held in temporary() {
            let real = realpath(&held);
            assert!(temporary().contains(&real), "{held} is {real}");
            let fence = drawn(&[
                ("/", NONE),
                (&format!("{real}/kept"), READ),
                (&format!("{real}/shut"), NONE),
                (".", WRITE),
            ]);
            assert!(fence.keep.contains(&format!("{real}/kept")), "{real}");
            assert!(fence.deny.contains(&format!("{real}/shut")), "{real}");
            assert!(fence.allows(&format!("{real}/a"), true));
        }
    }

    #[test]
    fn a_deny_beneath_nothing_granted_carves_nothing() {
        let fence = drawn(&[("~/.ssh", NONE)]);
        assert!(fence.deny.is_empty());
        assert_eq!(fence.level(&format!("{HOME}/.ssh")), NONE);
        let again = drawn(&[("/", WRITE), ("~", NONE), ("~/docs", READ)]);
        assert_eq!(again.level(&format!("{HOME}/docs/a")), READ);
        assert_eq!(again.level(&format!("{HOME}/.bashrc")), NONE);
        assert!(again.read.contains(&format!("{HOME}/docs")));
    }

    #[test]
    fn the_session_directory_is_the_workdir_as_well_and_no_home_is_nothing() {
        let rules = ruled(&[(".", WRITE), ("./out", READ)]);
        let fence = Fence::of(&rules, true, WORK, HOME, "/srv/session", &[], &[], &[]).unwrap();
        assert!(fence.allows("/srv/session/x.txt", true));
        assert_eq!(fence.level("/srv/session/out/y"), READ);
        let rules = ruled(&[("~", WRITE), (".", READ)]);
        let homeless = Fence::of(&rules, true, WORK, "", "", &[], &[], &[]).unwrap();
        assert_eq!(homeless.level(WORK), READ);
        assert_eq!(homeless.level("/home/someone/x"), NONE);
    }

    #[test]
    fn a_workdir_or_home_at_the_root_carves_out_beneath_it() {
        let rules = ruled(&[(".", WRITE), ("./secret", NONE), ("~/.ssh", NONE)]);
        let fence = Fence::of(&rules, true, "/", "/", "", &[], &[], &[]).unwrap();
        assert_eq!(fence.level("/secret/key"), NONE);
        assert_eq!(fence.level("/.ssh/id"), NONE);
        assert_eq!(fence.level("/src"), WRITE);
        assert_eq!(fence.beside("/", "/").level("/secret/key"), NONE);
    }

    #[test]
    fn a_carve_out_takes_back_what_the_grants_above_it_gave() {
        let fence = Fence {
            read: paths(&["/w/d/g"]),
            write: paths(&["/w", "/w/k/g", "/w/both"]),
            keep: paths(&["/w/k"]),
            deny: paths(&["/w/d", "/w/both"]),
            ..Fence::default()
        }
        .settled()
        .unwrap();
        for (path, level) in [
            ("/w/x", WRITE),
            ("/w/k/x", READ),
            ("/w/k/g/x", WRITE),
            ("/w/d/x", NONE),
            ("/w/d/g/x", READ),
            ("/w/both", WRITE),
            ("/elsewhere", NONE),
        ] {
            assert_eq!(fence.level(path), level, "{path}");
            assert_eq!(fence.allows(path, false), level != NONE, "{path}");
            assert_eq!(fence.allows(path, true), level == WRITE, "{path}");
        }
    }

    #[test]
    fn only_the_whole_filesystem_online_with_nothing_carved_is_open() {
        let everything = Fence {
            write: paths(&["/"]),
            ..Fence::default()
        };
        assert!(everything.open());
        assert!(
            !Fence {
                online: false,
                ..everything.clone()
            }
            .open()
        );
        assert!(
            !Fence {
                deny: paths(&["/x"]),
                ..everything.clone()
            }
            .open()
        );
        assert!(drawn(&[("/", WRITE)]).open());
        assert!(!drawn(&[("/", WRITE), ("~/.ssh", NONE)]).open());
    }

    #[test]
    fn granting_beneath_a_carve_out_grants_it_and_nothing_else() {
        let fence =
            drawn(&[("/", READ), ("~", NONE)]).granting(&[], &[format!("{HOME}/.cli")], &[], &[]);
        assert!(fence.allows(&format!("{HOME}/.cli/state"), true));
        assert!(!fence.allows(&format!("{HOME}/.bashrc"), false));
    }

    #[test]
    fn beside_draws_another_directory_as_the_workdir() {
        let fence = drawn(&[
            ("/", READ),
            (".", WRITE),
            ("./secret", NONE),
            ("./ro", READ),
        ]);
        let mirrored = fence.beside("/mirror", HOME);
        assert_eq!(mirrored.level("/mirror/src"), WRITE);
        assert_eq!(mirrored.level("/mirror/secret/key"), NONE);
        assert_eq!(mirrored.level("/mirror/ro/x"), READ);
        assert_eq!(mirrored.level(&format!("{WORK}/secret")), NONE);

        let wider = drawn(&[("/", READ), ("~", WRITE), (".", READ)]);
        let narrowed = wider.beside(&format!("{HOME}/.cache/mirror"), HOME);
        assert_eq!(narrowed.level(&format!("{HOME}/.cache/mirror/x")), READ);
        assert_eq!(narrowed.level(&format!("{HOME}/.cache/other")), WRITE);

        let path_by_path = Fence {
            write: paths(&["/w"]),
            ..Fence::default()
        };
        assert_eq!(path_by_path.beside("/mirror", HOME), path_by_path);
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

    /// A directory of the test's own, not under a temporary directory, which every fence
    /// counts as written.
    fn reachable() -> (tempfile::TempDir, std::path::PathBuf) {
        let dir = tempfile::tempdir_in(env!("CARGO_MANIFEST_DIR")).unwrap();
        let root = std::fs::canonicalize(dir.path()).unwrap();
        (dir, root)
    }

    fn shown(path: &Path) -> String {
        path.to_string_lossy().into_owned()
    }

    #[test]
    fn reach_follows_no_link_into_what_a_fence_of_everything_carves_out() {
        let (_dir, root) = reachable();
        std::fs::create_dir(root.join("kept")).unwrap();
        std::os::unix::fs::symlink(root.join("kept"), root.join("link")).unwrap();
        let carved = Fence {
            write: paths(&["/", &shown(&root)]),
            deny: paths(&[&shown(&root.join("kept"))]),
            ..Fence::default()
        };
        let why = carved.reach(&shown(&root.join("link")), false).unwrap_err();
        assert!(
            why.to_string().contains("carved out of this fence"),
            "{why}"
        );
        // A link to somewhere nothing is carved out of is followed.
        let elsewhere = Fence {
            write: paths(&["/"]),
            deny: paths(&[&shown(&root.join("other"))]),
            ..Fence::default()
        };
        let (_, at) = elsewhere.reach(&shown(&root.join("link")), false).unwrap();
        assert_eq!(at, shown(&root.join("kept")));
    }

    #[test]
    fn reached_reaches_what_is_granted_again_beneath_a_carve_out_of_everything() {
        let (_dir, root) = reachable();
        let state = root.join("home/.cli");
        std::fs::create_dir_all(&state).unwrap();
        let fence = Fence {
            write: paths(&["/", &shown(&state)]),
            deny: paths(&[&shown(&root.join("home"))]),
            ..Fence::default()
        };
        let reached: Vec<String> = fence
            .reached(None)
            .unwrap()
            .into_iter()
            .map(|(at, _)| at)
            .collect();
        assert_eq!(reached, paths(&["/", &shown(&state)]));
    }

    #[test]
    fn reached_reaches_the_paths_it_is_given_in_place_of_what_it_writes() {
        let (_dir, root) = reachable();
        std::fs::create_dir(root.join("a")).unwrap();
        std::fs::create_dir(root.join("b")).unwrap();
        let fence = Fence {
            write: paths(&[&shown(&root)]),
            deny: paths(&[&shown(&root.join("b"))]),
            ..Fence::default()
        };
        let given = paths(&[&shown(&root.join("a"))]);
        let reached: Vec<String> = fence
            .reached(Some(&given))
            .unwrap()
            .into_iter()
            .map(|(at, _)| at)
            .collect();
        assert_eq!(reached, given);
    }
}
