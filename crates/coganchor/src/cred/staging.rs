//! Read-only copies of credential files under `/dev/shm`, for lookups the tracer answers
//! without touching the account's own files. Port of `hmz.coganchor.providers._staging`.
//! [Unit 15]
//!
//! A CLI asks about its credential hundreds of times a turn (pi reads its `auth.json` six to
//! eight hundred times), and the answer is the same every time. So the file is copied once into
//! a directory of this run's own on `/dev/shm`, which is memory, and the reads are answered
//! there. A call that could change a credential is not: a refreshed token has to be durable the
//! moment it is written, so writes reach the account's own file and drop the copy, and the next
//! read makes a new one.
//!
//! A copy is held against the file it was made from once a second ([`FRESH`]), for the writer
//! this run cannot see: another agent of the same account refreshing the same token.
//!
//! It is a cache of a secret: the directory is `0700`, the copies `0600`, under a name nobody
//! can guess, and removed when the run ends ([`Staging::close`]). A tracer killed outright runs
//! no teardown, so the next run sweeps what such a run left ([`swept`]) before it makes a
//! directory of its own.

use std::collections::HashMap;
use std::fs::{self, DirBuilder, FileTimes, OpenOptions};
use std::io::{self, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

/// Where copies are kept: a tmpfs wherever Linux has POSIX shared memory (`_ROOT`).
pub const ROOT: &str = "/dev/shm";

/// What a run's own directory is called before its process id (`_CALLED`); `_MINE` reads it
/// back as `hmz-<pid>-`.
const CALLED: &str = "hmz-";

/// How large a credential can be before it is left where it is (`_MOST`): a token is hundreds
/// of bytes, and something of megabytes is a CLI's history rather than its account.
pub const MOST: u64 = 1 << 20;

/// How long a copy is trusted without looking at the file it was made from (`_FRESH`).
pub const FRESH: Duration = Duration::from_secs(1);

/// What is never copied (`_LOCK`): a lock file is a rendezvous between processes, and a copy
/// of one is a lock the other process cannot see.
const LOCK: &str = ".lock";

/// What the account's own file was when a decision was made about it: inode, size, and the
/// moment it last changed in nanoseconds. `None` is `_NOTHING`, a path that was not there (or
/// could not be looked at), which no real file equals.
type Was = Option<(u64, u64, i128)>;

/// One credential as this run last found it (`_Held`).
#[derive(Debug, Clone)]
struct Held {
    /// The copy, or `None` for a path answered with itself: a directory, a link, a lock,
    /// something too large, something that could not be copied, or nothing at all.
    at: Option<PathBuf>,
    was: Was,
    looked: Instant,
}

/// The copies one redirected run answers reads from, and the directory they are in.
#[derive(Debug)]
pub struct Staging {
    /// Where this run's directories go: [`ROOT`] outside tests.
    root: PathBuf,
    /// This run's directory, made with the first copy.
    at: Option<PathBuf>,
    /// What is known about each credential, by the account's own path to it.
    held: HashMap<String, Held>,
    /// How many copies have been made, which names the next: a copy is never written over,
    /// so a process holding the old one open goes on reading the token it opened.
    made: u64,
    /// Whether copying is possible here at all (no `/dev/shm`, or a full one, is not).
    can: bool,
}

impl Default for Staging {
    fn default() -> Self {
        Self::new()
    }
}

impl Staging {
    /// A run that has copied nothing and made no directory, copying under [`ROOT`].
    pub fn new() -> Self {
        Self::under(ROOT)
    }

    /// The same, copying under `root`.
    pub fn under(root: impl Into<PathBuf>) -> Self {
        Staging {
            root: root.into(),
            at: None,
            held: HashMap::new(),
            made: 0,
            can: true,
        }
    }

    /// The copy to answer a read of the credential at `path` (the account's own path) with,
    /// or `None` to answer it with `path` itself.
    pub fn reading(&mut self, path: &str) -> Option<PathBuf> {
        self.reading_at(path, Instant::now())
    }

    /// [`Staging::reading`] at the moment `now`.
    pub fn reading_at(&mut self, path: &str, now: Instant) -> Option<PathBuf> {
        if let Some(held) = self.held.get(path)
            && now.saturating_duration_since(held.looked) < FRESH
        {
            return held.at.clone();
        }
        self.copy(path, now)
    }

    /// Drops the copy of a credential something is about to change: the write reaches the
    /// account's own file, and a copy kept afterwards would serve the token it replaced.
    pub fn wrote(&mut self, path: &str) {
        if let Some(Held { at: Some(at), .. }) = self.held.remove(path) {
            let _ = fs::remove_file(at);
        }
    }

    /// Takes this run's directory and every copy in it away; copies nothing after.
    pub fn close(&mut self) {
        self.held.clear();
        self.can = false;
        if let Some(at) = self.at.take() {
            let _ = fs::remove_dir_all(at);
        }
    }

    /// This run's directory, if one has been made.
    pub fn directory(&self) -> Option<&Path> {
        self.at.as_deref()
    }

    /// Makes the copy of one credential, or decides there is not one to make (`_copy`).
    fn copy(&mut self, path: &str, now: Instant) -> Option<PathBuf> {
        let status = match fs::symlink_metadata(path) {
            Ok(status) => status,
            Err(_) => {
                // Nothing there, or nothing this process may look at: answered with the
                // account's own path, which fails there, and held so it is not asked again.
                self.wrote(path);
                self.held.insert(
                    path.to_owned(),
                    Held {
                        at: None,
                        was: None,
                        looked: now,
                    },
                );
                return None;
            }
        };
        let was = Some((
            status.ino(),
            status.size(),
            i128::from(status.mtime()) * 1_000_000_000 + i128::from(status.mtime_nsec()),
        ));
        if let Some(held) = self.held.get_mut(path)
            && held.was == was
        {
            held.looked = now;
            return held.at.clone();
        }
        self.wrote(path);
        // A directory is listed and written into, a link is asked about rather than read, and
        // a lock is other processes' business: each is answered with the real one.
        let at = if !status.file_type().is_file() || status.size() > MOST || path.ends_with(LOCK) {
            None
        } else {
            let name = Path::new(path)
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default();
            // A credential that could not be copied is one to read where it is.
            fs::read(path)
                .and_then(|blob| self.planted(&name, &blob, &status))
                .ok()
                .flatten()
        };
        self.held.insert(
            path.to_owned(),
            Held {
                at: at.clone(),
                was,
                looked: now,
            },
        );
        at
    }

    /// Writes one credential into this run's directory at `0600`, named as the account names
    /// it, with the times of the file it was copied from (`_planted`): a CLI that decides
    /// whether to read a credential again by when it changed would read a copy as a rotation.
    fn planted(
        &mut self,
        name: &str,
        blob: &[u8],
        status: &fs::Metadata,
    ) -> io::Result<Option<PathBuf>> {
        let Some(where_) = self.place() else {
            return Ok(None);
        };
        self.made += 1;
        let at = where_.join(format!("{}.{name}", self.made));
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&at)?;
        let mut times = FileTimes::new();
        if let Ok(accessed) = status.accessed() {
            times = times.set_accessed(accessed);
        }
        if let Ok(modified) = status.modified() {
            times = times.set_modified(modified);
        }
        match file.write_all(blob).and_then(|()| file.set_times(times)) {
            Ok(()) => Ok(Some(at)),
            Err(why) => {
                // A half-written copy of a secret is nothing this run tracks: taken away now.
                let _ = fs::remove_file(&at);
                Err(why)
            }
        }
    }

    /// This run's directory, made the first time there is something to put in it (`_where`):
    /// `hmz-<pid>-<16 hex>-<8 hex>`, `0700`, made rather than opened, so a name somebody got
    /// in first with is refused and another is taken.
    fn place(&mut self) -> Option<PathBuf> {
        if self.at.is_some() || !self.can {
            return self.at.clone();
        }
        swept(&self.root);
        let pid = std::process::id();
        for _ in 0..100 {
            let at = self.root.join(format!(
                "{CALLED}{pid}-{}-{}",
                hex::encode(rand::random::<[u8; 8]>()),
                hex::encode(rand::random::<[u8; 4]>()),
            ));
            match DirBuilder::new().mode(0o700).create(&at) {
                Ok(()) => {
                    self.at = Some(at);
                    return self.at.clone();
                }
                Err(why) if why.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(_) => break,
            }
        }
        self.can = false;
        None
    }
}

/// The process id a directory name under [`ROOT`] says made it (`_MINE`: `hmz-(\d+)-`).
pub fn maker(name: &str) -> Option<&str> {
    let rest = name.strip_prefix(CALLED)?;
    let digits = rest.len() - rest.trim_start_matches(|c: char| c.is_ascii_digit()).len();
    (digits > 0 && rest[digits..].starts_with('-')).then(|| &rest[..digits])
}

/// Takes away what a run killed outright left under `root` (`swept`): a directory of this
/// user's whose name says it was made by a process that is gone. A pid that has come round to
/// somebody else is left alone, which leaks one directory rather than risk taking credentials
/// from a run reading them this moment.
pub fn swept(root: &Path) {
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    // SAFETY: getuid cannot fail.
    let me = unsafe { libc::getuid() };
    for entry in entries.flatten() {
        let name = entry.file_name();
        let Some(pid) = name.to_str().and_then(maker) else {
            continue;
        };
        let Ok(status) = fs::symlink_metadata(entry.path()) else {
            continue;
        };
        if !status.is_dir() || status.uid() != me {
            continue;
        }
        let Ok(pid) = pid.parse::<libc::pid_t>() else {
            continue;
        };
        // SAFETY: signal 0 only asks whether the process exists.
        if unsafe { libc::kill(pid, 0) } != 0
            && io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH)
        {
            let _ = fs::remove_dir_all(entry.path());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn staged() -> (tempfile::TempDir, tempfile::TempDir, Staging) {
        let shm = tempfile::tempdir().unwrap();
        let home = tempfile::tempdir().unwrap();
        let staging = Staging::under(shm.path());
        (shm, home, staging)
    }

    fn file(home: &tempfile::TempDir, name: &str, blob: &str) -> String {
        let path = home.path().join(name);
        fs::write(&path, blob).unwrap();
        path.to_str().unwrap().to_owned()
    }

    #[test]
    fn a_read_is_answered_with_a_private_copy_of_the_same_bytes_and_times() {
        let (_shm, home, mut staging) = staged();
        let path = file(&home, "auth.json", "{\"token\": 1}");

        let copy = staging.reading(&path).unwrap();

        assert_eq!(fs::read_to_string(&copy).unwrap(), "{\"token\": 1}");
        assert!(
            copy.file_name()
                .unwrap()
                .to_str()
                .unwrap()
                .ends_with(".auth.json")
        );
        let meta = fs::metadata(&copy).unwrap();
        assert_eq!(meta.permissions().mode() & 0o777, 0o600);
        assert_eq!(
            meta.modified().unwrap(),
            fs::metadata(&path).unwrap().modified().unwrap()
        );
        let dir = staging.directory().unwrap();
        assert_eq!(
            fs::metadata(dir).unwrap().permissions().mode() & 0o777,
            0o700
        );
        let name = dir.file_name().unwrap().to_str().unwrap();
        assert_eq!(maker(name), Some(std::process::id().to_string().as_str()));
    }

    #[test]
    fn a_second_read_is_the_same_copy() {
        let (_shm, home, mut staging) = staged();
        let path = file(&home, "auth.json", "a");
        let now = Instant::now();

        let first = staging.reading_at(&path, now).unwrap();
        // Past the freshness window but unchanged: the copy is kept.
        let again = staging.reading_at(&path, now + FRESH * 2).unwrap();

        assert_eq!(first, again);
    }

    #[test]
    fn a_change_seen_after_the_window_makes_a_new_copy_and_drops_the_old() {
        let (_shm, home, mut staging) = staged();
        let path = file(&home, "auth.json", "old");
        let now = Instant::now();
        let first = staging.reading_at(&path, now).unwrap();

        fs::write(&path, "newer").unwrap();
        // Within the window the copy is trusted without looking.
        assert_eq!(staging.reading_at(&path, now).unwrap(), first);
        let second = staging.reading_at(&path, now + FRESH).unwrap();

        assert_ne!(first, second);
        assert!(!first.exists());
        assert_eq!(fs::read_to_string(second).unwrap(), "newer");
    }

    #[test]
    fn a_write_drops_the_copy_and_the_next_read_makes_another() {
        let (_shm, home, mut staging) = staged();
        let path = file(&home, "auth.json", "a");
        let first = staging.reading(&path).unwrap();

        staging.wrote(&path);

        assert!(!first.exists());
        let second = staging.reading(&path).unwrap();
        assert_ne!(first, second);
    }

    #[test]
    fn what_is_not_a_small_regular_file_is_answered_with_itself() {
        let (_shm, home, mut staging) = staged();
        let lock = file(&home, "auth.json.lock", "");
        let big = file(&home, "history", &"x".repeat(MOST as usize + 1));
        let dir = home.path().join("creds");
        fs::create_dir(&dir).unwrap();
        let link = home.path().join("link");
        std::os::unix::fs::symlink(&big, &link).unwrap();
        let missing = home.path().join("missing");

        for path in [
            &lock,
            &big,
            dir.to_str().unwrap(),
            link.to_str().unwrap(),
            missing.to_str().unwrap(),
        ] {
            assert_eq!(staging.reading(path), None, "{path}");
        }
        // Nothing was copied, so no directory was made.
        assert_eq!(staging.directory(), None);
    }

    #[test]
    fn a_missing_file_that_appears_is_copied_once_the_window_passes() {
        let (_shm, home, mut staging) = staged();
        let path = home.path().join("auth.json").to_str().unwrap().to_owned();
        let now = Instant::now();
        assert_eq!(staging.reading_at(&path, now), None);

        fs::write(&path, "a").unwrap();

        assert_eq!(staging.reading_at(&path, now), None);
        assert!(staging.reading_at(&path, now + FRESH).is_some());
    }

    #[test]
    fn closing_takes_every_copy_away_and_copies_nothing_after() {
        let (_shm, home, mut staging) = staged();
        let path = file(&home, "auth.json", "a");
        staging.reading(&path).unwrap();
        let dir = staging.directory().unwrap().to_owned();

        staging.close();

        assert!(!dir.exists());
        assert_eq!(staging.reading(&path), None);
    }

    #[test]
    fn a_directory_left_by_a_dead_run_is_swept_and_a_live_ones_is_not() {
        let shm = tempfile::tempdir().unwrap();
        let dead = shm.path().join(format!("hmz-{}-abc-x", i32::MAX - 1));
        let live = shm.path().join(format!("hmz-{}-abc-x", std::process::id()));
        let other = shm.path().join("hmz-x-abc");
        let huge = shm.path().join("hmz-99999999999999999999-abc");
        for dir in [&dead, &live, &other, &huge] {
            fs::create_dir(dir).unwrap();
        }

        swept(shm.path());

        assert!(!dead.exists());
        assert!(live.exists() && other.exists() && huge.exists());
    }

    #[test]
    fn the_maker_is_read_off_the_name() {
        assert_eq!(maker("hmz-123-abc"), Some("123"));
        assert_eq!(maker("hmz-123"), None);
        assert_eq!(maker("hmz--1-"), None);
        assert_eq!(maker("xhmz-1-"), None);
    }
}
